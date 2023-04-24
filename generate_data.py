# notebook_to_module.py
import asyncio
import json
import logging
import os
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime

import gidgethub.httpx
import httpx
import jinja2
import tenacity

logging.basicConfig(level=logging.INFO)


ME = "basnijholt"
orgs = (ME, "python-adaptive", "topocm", "python-kasa", "kwant-project")


def load_token():
    token_path = ".TOKEN"
    if os.path.exists(token_path):
        with open(token_path) as f:
            return f.read().strip()
    return os.environ["TOKEN"]


token = load_token()
retry_kw = dict(stop=tenacity.stop_after_attempt(10), wait=tenacity.wait_fixed(180))


@asynccontextmanager
async def gh_client(token):
    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, ME, oauth_token=token)
        yield gh


@tenacity.retry(**retry_kw)
async def get_org_repos(org, token):
    repos = []
    async with gh_client(token) as gh:
        url = f"/users/{ME}/repos" if org == ME else f"/orgs/{org}/repos"
        async for repo in gh.getiter(f"{url}?type=sources"):
            repos.append(repo)
    return repos


async def get_all_repos_in_orgs(orgs, token):
    tasks = [get_org_repos(org, token) for org in orgs]
    all_repos = await asyncio.gather(*tasks)
    return sum(all_repos, [])


@tenacity.retry(**retry_kw)
async def get_repo(full_repo_name, token):
    async with gh_client(token) as gh:
        owner, name = full_repo_name.split("/")
        return await gh.getitem(f"/repos/{owner}/{name}")


async def get_repos(full_repo_names, token):
    tasks = [get_repo(full_repo_name, token) for full_repo_name in full_repo_names]
    return await asyncio.gather(*tasks)


@tenacity.retry(**retry_kw)
async def get_n_commits(full_repo_name, user=ME):
    async with gh_client(token) as gh:
        owner, name = full_repo_name.split("/")
        try:
            stats_contributors = await gh.getitem(
                f"/repos/{owner}/{name}/stats/contributors"
            )
        except Exception:
            print(f"Error: {full_repo_name}")
            return None

        if stats_contributors is None:
            print(f"API returned None for {full_repo_name}")
            return None

        total_commits = next(
            (s["total"] for s in stats_contributors if s["author"]["login"] == user),
            0,
        )
        return full_repo_name, total_commits


@tenacity.retry(**retry_kw)
async def get_stargazers_page_with_dates(gh, owner, name, page, headers):
    stats_contributors = await gh.getitem(
        f"/repos/{owner}/{name}/stargazers?per_page=100&page={page}",
        extra_headers=headers,
    )
    starred_at = [
        datetime.strptime(s["starred_at"], "%Y-%m-%dT%H:%M:%SZ")
        for s in stats_contributors
    ]

    return starred_at


@tenacity.retry(**retry_kw)
async def get_stargazers_with_dates(full_repo_name):
    headers = {"Accept": "application/vnd.github.v3.star+json"}
    starred = []
    async with gh_client(token) as gh:
        owner, name = full_repo_name.split("/")
        page = 1
        while True:
            logging.info(f"Fetching stargazers for {owner}/{name}, page {page}")
            starred_at = await get_stargazers_page_with_dates(
                gh, owner, name, page, headers
            )
            if not starred_at:
                break
            starred.extend(starred_at)
            page += 1
    return starred


@tenacity.retry(**retry_kw)
async def get_commits(full_repo_name, author=ME):
    async with gh_client(token) as gh:
        owner, name = full_repo_name.split("/")
        commits = []
        async for commit in gh.getiter(
            f"/repos/{owner}/{name}/commits?author={author}&per_page=100"
        ):
            commits.append(commit)
        return commits


def split(x, at_index=5):
    return x[:at_index], x[at_index:]


weekdays = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


async def generate_repos_data():
    repos = await get_all_repos_in_orgs(orgs, token)
    full_repo_names = [repo["full_name"] for repo in repos]
    repos = await get_repos(full_repo_names, token)

    with open("data/repos.json", "w") as f:
        json.dump([repo for repo in repos], f)

    return repos


async def generate_most_stars_data(repos):
    mapping = defaultdict(list)
    for repo in repos:
        namespace, name = repo["full_name"].split("/", 1)
        mapping[namespace].append(repo)

    most_stars = sorted(
        (repo for project in orgs for repo in mapping[project]),
        key=lambda r: r["stargazers_count"],
        reverse=True,
    )

    with open("data/most_stars.json", "w") as f:
        json.dump([repo for repo in most_stars], f)

    return most_stars


async def generate_most_committed_data(repos):
    to_check = []
    for repo in repos:
        full_name = (
            repo["full_name"] if not repo["fork"] else repo["source"]["full_name"]
        )
        if full_name in ("regro/cf-graph-countyfair", "volumio/Volumio2"):
            continue
        to_check.append(full_name)

    commits = await asyncio.gather(
        *[get_n_commits(full_name) for full_name in to_check]
    )
    commits = [c for c in commits if c is not None]
    most_committed = sorted(set(commits), key=lambda x: x[1], reverse=True)

    with open("data/most_committed.json", "w") as f:
        json.dump(
            [(full_name, n_commits) for full_name, n_commits in most_committed], f
        )

    return most_committed


async def generate_stargazers_data(most_stars):
    stargazers = await asyncio.gather(
        *[get_stargazers_with_dates(r["full_name"]) for r in most_stars[:20]]
    )

    with open("data/stargazers.json", "w") as f:
        json.dump([[str(date) for date in dates] for dates in stargazers], f)

    return stargazers


async def generate_commit_dates_data(most_committed):
    all_commits = await asyncio.gather(
        *[get_commits(full_name) for full_name, _ in most_committed[:5]]
    )
    all_commits = sum(all_commits, [])
    all_commit_dates = [
        datetime.strptime(c["commit"]["author"]["date"], "%Y-%m-%dT%H:%M:%SZ")
        for c in all_commits
    ]

    with open("data/all_commit_dates.json", "w") as f:
        json.dump([str(date) for date in all_commit_dates], f)

    return all_commit_dates


async def generate_day_hour_histograms(all_commit_dates):
    day_hist = [
        (weekdays[i], n)
        for i, n in sorted(Counter([d.weekday() for d in all_commit_dates]).items())
    ]

    with open("data/day_hist.json", "w") as f:
        json.dump(day_hist, f)

    hour_hist = [
        (f"{i:02d}", n)
        for i, n in sorted(Counter([d.hour for d in all_commit_dates]).items())
    ]

    with open("data/hour_hist.json", "w") as f:
        json.dump(hour_hist, f)

    return day_hist, hour_hist


async def generate_data():
    # Create data folder if it doesn't exist
    os.makedirs("data", exist_ok=True)

    repos = await generate_repos_data()
    most_stars = await generate_most_stars_data(repos)
    most_committed = await generate_most_committed_data(repos)
    stargazers = await generate_stargazers_data(most_stars)
    all_commit_dates = await generate_commit_dates_data(most_committed)
    day_hist, hour_hist = await generate_day_hour_histograms(all_commit_dates)
    return dict(
        repos=repos,
        most_stars=most_stars,
        most_committed=most_committed,
        stargazers=stargazers,
        all_commit_dates=all_commit_dates,
        day_hist=day_hist,
        hour_hist=hour_hist,
    )
