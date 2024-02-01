# notebook_to_module.py
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, TypeAlias, TypedDict

import gidgethub.httpx
import httpx
import tenacity

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
ME = "basnijholt"
orgs = (ME, "python-adaptive", "topocm", "python-kasa", "kwant-project")
RepoDict: TypeAlias = dict[str, Any]
OrgRepoDict: TypeAlias = dict[str, Any]
CommitDict: TypeAlias = dict[str, Any]


def load_token() -> str:
    token_path = ".TOKEN"
    if os.path.exists(token_path):
        with open(token_path) as f:
            return f.read().strip()
    return os.environ["TOKEN"]


TOKEN = load_token()
RETRY_KW = {
    "stop": tenacity.stop_after_attempt(10),
    "wait": tenacity.wait_fixed(180),
    "before": tenacity.before_log(log, logging.DEBUG),
}


@asynccontextmanager
async def gh_client(token: str) -> gidgethub.httpx.GitHubAPI:
    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, ME, oauth_token=token)
        yield gh


@tenacity.retry(**RETRY_KW)
async def get_org_repos(org: str, token: str) -> list[OrgRepoDict]:
    repos = []
    async with gh_client(token) as gh:
        url = f"/users/{ME}/repos" if org == ME else f"/orgs/{org}/repos"
        async for repo in gh.getiter(f"{url}?type=sources"):
            repos.append(repo)
    return repos


async def get_all_repos_in_orgs(orgs: list[str], token: str) -> list[dict[OrgRepoDict]]:
    tasks = [get_org_repos(org, token) for org in orgs]
    all_repos = await asyncio.gather(*tasks)
    return sum(all_repos, [])


@tenacity.retry(**RETRY_KW)
async def get_repo(full_repo_name: str, token: str) -> RepoDict:
    async with gh_client(token) as gh:
        owner, name = full_repo_name.split("/")
        return await getitem(gh, f"/repos/{owner}/{name}")


async def get_repos(full_repo_names: list[str], token: str) -> list[RepoDict]:
    tasks = [get_repo(full_repo_name, token) for full_repo_name in full_repo_names]
    return await asyncio.gather(*tasks)


async def getitem(
    gh: gidgethub.httpx.GitHubAPI,
    url: str,
    n_tries: int = 5,
) -> Any:
    for _ in range(n_tries):
        status_response = await gh.getstatus(url)
        if status_response == 200:
            # Data is ready, retrieve it
            return await gh.getitem(url)
        elif status_response == 202:
            # Data is not ready yet, wait and then retry
            await asyncio.sleep(20)
        else:
            # Handle other HTTP response statuses appropriately
            msg = f"Received unexpected status code: {status_response.status_code}"
            raise Exception(
                msg,
            )
    return None


@tenacity.retry(**RETRY_KW)
async def get_n_commits(full_repo_name: str, user: str = ME) -> tuple[str, int]:
    async with gh_client(TOKEN) as gh:
        owner, name = full_repo_name.split("/")
        try:
            stats_contributors = await getitem(
                gh,
                f"/repos/{owner}/{name}/stats/contributors",
            )
        except Exception:
            return None

        if stats_contributors is None:
            return None

        total_commits = next(
            (s["total"] for s in stats_contributors if s["author"]["login"] == user),
            0,
        )
        return full_repo_name, total_commits


@tenacity.retry(**RETRY_KW)
async def get_stargazers_page_with_dates(
    gh: gidgethub.httpx.GitHubAPI,
    owner: str,
    name: str,
    page: int,
    headers: dict[str, str],
) -> list[datetime.datetime]:
    stats_contributors = await getitem(
        gh,
        f"/repos/{owner}/{name}/stargazers?per_page=100&page={page}",
        extra_headers=headers,
    )
    return [
        datetime.strptime(s["starred_at"], "%Y-%m-%dT%H:%M:%SZ")
        for s in stats_contributors
    ]


@tenacity.retry(**RETRY_KW)
async def get_stargazers_with_dates(full_repo_name: str) -> list[datetime.datetime]:
    headers = {"Accept": "application/vnd.github.v3.star+json"}
    starred = []
    async with gh_client(TOKEN) as gh:
        owner, name = full_repo_name.split("/")
        page = 1
        while True:
            starred_at = await get_stargazers_page_with_dates(
                gh,
                owner,
                name,
                page,
                headers,
            )
            if not starred_at:
                break
            starred.extend(starred_at)
            page += 1
    return starred


@tenacity.retry(**RETRY_KW)
async def get_commits(full_repo_name: str, author: str = ME) -> list[CommitDict]:
    async with gh_client(TOKEN) as gh:
        owner, name = full_repo_name.split("/")
        commits = []
        async for commit in gh.getiter(
            f"/repos/{owner}/{name}/commits?author={author}&per_page=100",
        ):
            commits.append(commit)
        return commits


def split(x: list, at_index: int = 5) -> tuple[list, list]:
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


async def generate_repos_data() -> list[RepoDict]:
    org_repos = await get_all_repos_in_orgs(orgs, TOKEN)
    full_repo_names = [repo["full_name"] for repo in org_repos]
    repos = await get_repos(full_repo_names, TOKEN)

    with open("data/repos.json", "w") as f:
        json.dump(list(repos), f, indent=2)

    return repos


def generate_most_stars_data(repos: list[RepoDict]) -> list[dict[str, str | int]]:
    mapping = defaultdict(list)
    for repo in repos:
        namespace, name = repo["full_name"].split("/", 1)
        mapping[namespace].append(repo)

    most_stars = sorted(
        (repo for project in orgs for repo in mapping[project]),
        key=lambda r: r["stargazers_count"],
        reverse=True,
    )
    return [
        {"full_name": repo["full_name"], "stargazers_count": repo["stargazers_count"]}
        for repo in most_stars
    ]


async def generate_most_committed_data(repos: list[RepoDict]) -> list[tuple[str, int]]:
    to_check = []
    for repo in repos:
        full_name = (
            repo["full_name"] if not repo["fork"] else repo["source"]["full_name"]
        )
        if full_name in (
            "regro/cf-graph-countyfair",
            "volumio/Volumio2",
            "CJ-Wright/cf-graph-countyfair",
        ):
            continue
        to_check.append(full_name)

    commits = await asyncio.gather(
        *[get_n_commits(full_name) for full_name in to_check],
    )
    commits = [c for c in commits if c is not None]
    most_committed = sorted(set(commits), key=lambda x: x[1], reverse=True)

    with open("data/most_committed.json", "w") as f:
        json.dump(list(most_committed), f, indent=2)

    return most_committed


class StargazersDict(TypedDict):
    full_name: str
    dates: list[str]
    stargazer_count: int


async def generate_stargazers_data(repos: list[RepoDict]) -> list[StargazersDict]:
    most_stars = generate_most_stars_data(repos)
    stargazers = await asyncio.gather(
        *[get_stargazers_with_dates(r["full_name"]) for r in most_stars[:20]],
    )
    stargazers = [
        {**r, "dates": [date.isoformat() for date in date_list]}
        for r, date_list in zip(most_stars, stargazers)
    ]
    with open("data/stargazers.json", "w") as f:
        json.dump(stargazers, f, indent=2)

    return stargazers


async def generate_commit_dates_data(
    most_committed: list[tuple[str, int]],
) -> list[datetime.datetime]:
    all_commits = await asyncio.gather(
        *[get_commits(full_name) for full_name, _ in most_committed[:5]],
    )
    all_commits = sum(all_commits, [])
    all_commit_dates = [
        datetime.strptime(c["commit"]["author"]["date"], "%Y-%m-%dT%H:%M:%SZ")
        for c in all_commits
    ]

    with open("data/all_commit_dates.json", "w") as f:
        json.dump([str(date) for date in all_commit_dates], f, indent=2)

    return all_commit_dates


def generate_day_hour_histograms(
    all_commit_dates: list[datetime.datetime],
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    day_hist = [
        (weekdays[i], n)
        for i, n in sorted(Counter([d.weekday() for d in all_commit_dates]).items())
    ]

    hour_hist = [
        (f"{i:02d}", n)
        for i, n in sorted(Counter([d.hour for d in all_commit_dates]).items())
    ]

    return day_hist, hour_hist


async def generate_data() -> dict[str, Any]:
    # Create data folder if it doesn't exist
    os.makedirs("data", exist_ok=True)
    repos = await generate_repos_data()
    most_committed = await generate_most_committed_data(repos)
    stargazers = await generate_stargazers_data(repos)
    all_commit_dates = await generate_commit_dates_data(most_committed)
    day_hist, hour_hist = generate_day_hour_histograms(all_commit_dates)
    return {
        "repos": repos,
        "most_committed": most_committed,
        "stargazers": stargazers,
        "all_commit_dates": all_commit_dates,
        "day_hist": day_hist,
        "hour_hist": hour_hist,
    }


def to_plotly_json() -> None:
    with open("data/stargazers.json") as f:
        stargazers = json.load(f)

    traces = []
    for repo_data in stargazers:
        full_name = repo_data["full_name"]
        dates = sorted(repo_data["dates"])
        cumulative_count = list(range(1, len(dates) + 1))

        trace = {
            "x": dates,
            "y": cumulative_count,
            "mode": "lines",
            "name": full_name,
        }
        traces.append(trace)

    with open("data/traces_data.json", "w") as outfile:
        json.dump(traces, outfile)
