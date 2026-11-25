from __future__ import annotations

import asyncio
import json
import logging
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from contextlib import asynccontextmanager
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, NamedTuple, TypeAlias, TypedDict

import gidgethub.httpx
import httpx
import tenacity

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger(__name__)
ME = "basnijholt"
orgs = (
    ME,
    "mindroom-ai",
    "python-adaptive",
    "topocm",
    "python-kasa",
    "kwant-project",
    "pipefunc",
)
EXTRA_REPOS = ("conda-incubator/unidep",)
BLOG_FEED_URL = "https://www.nijho.lt/post/index.xml"
RepoDict: TypeAlias = dict[str, Any]
OrgRepoDict: TypeAlias = dict[str, Any]


def load_token() -> str:
    token_path = ".TOKEN"
    if os.path.exists(token_path):
        with open(token_path) as f:
            return f.read().strip()
    return os.environ["TOKEN"]


RETRY_KW = {
    "stop": tenacity.stop_after_attempt(10),
    "wait": tenacity.wait_fixed(180),
    "before": tenacity.before_log(log, logging.DEBUG),
}

GRAPHQL_URL = "https://api.github.com/graphql"
STARGAZER_QUERY = """
query ($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    stargazers(first: 100, after: $after) {
      edges {
        starredAt
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


@asynccontextmanager
async def gh_client(token: str) -> gidgethub.httpx.GitHubAPI:
    async with httpx.AsyncClient() as client:
        gh = gidgethub.httpx.GitHubAPI(client, ME, oauth_token=token)
        yield gh


@tenacity.retry(**RETRY_KW)
async def get_org_repos(org: str, gh: gidgethub.httpx.GitHubAPI) -> list[OrgRepoDict]:
    repos = []
    url = f"/users/{ME}/repos" if org == ME else f"/orgs/{org}/repos"
    async for repo in gh.getiter(f"{url}?type=sources"):
        if not repo.get("private", False):
            repos.append(repo)
    return repos


async def get_all_repos_in_orgs(
    orgs: Iterable[str], gh: gidgethub.httpx.GitHubAPI
) -> list[OrgRepoDict]:
    tasks = [get_org_repos(org, gh) for org in orgs]
    all_repos = await asyncio.gather(*tasks)
    return sum(all_repos, [])


async def generate_repos_data(gh: gidgethub.httpx.GitHubAPI) -> list[RepoDict]:
    org_repos = await get_all_repos_in_orgs(orgs, gh)
    for full_name in EXTRA_REPOS:
        try:
            repo = await gh.getitem(f"/repos/{full_name}")
            if not repo.get("private", False):
                org_repos.append(repo)
        except Exception:
            log.warning("Failed to fetch extra repo %s", full_name)
    deduped: dict[str, RepoDict] = {}
    for repo in org_repos:
        full_name = repo["full_name"]
        if full_name not in deduped:
            deduped[full_name] = repo
    repos = list(deduped.values())

    with open("data/repos.json", "w") as f:
        json.dump(list(repos), f, indent=2)

    return repos


async def graphql_request(
    client: httpx.AsyncClient,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    response = await client.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
    )
    response.raise_for_status()
    payload = response.json()
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


async def fetch_new_stargazer_dates(
    client: httpx.AsyncClient,
    owner: str,
    name: str,
    latest_known: str | None,
) -> list[str]:
    after: str | None = None
    collected: list[str] = []
    while True:
        data = await graphql_request(
            client,
            STARGAZER_QUERY,
            {"owner": owner, "name": name, "after": after},
        )
        repository = data.get("repository")
        if not repository:
            break
        stargazers = repository["stargazers"]
        edges = stargazers["edges"]
        if not edges:
            break
        stop = False
        for edge in edges:
            starred_at = edge["starredAt"]
            if latest_known and starred_at <= latest_known:
                stop = True
                break
            collected.append(starred_at)
        if stop or not stargazers["pageInfo"]["hasNextPage"]:
            break
        after = stargazers["pageInfo"]["endCursor"]
    return collected


def generate_most_stars_data(repos: list[RepoDict]) -> list[dict[str, str | int]]:
    mapping = defaultdict(list)
    for repo in repos:
        namespace, _ = repo["full_name"].split("/", 1)
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


def fmt_stars(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return f"{n:,}"


def repo_stars_map(repos: list[RepoDict]) -> dict[str, str]:
    return {
        str(repo["full_name"]): fmt_stars(int(repo.get("stargazers_count", 0)))
        for repo in repos
    }


def stars_summary(stargazers: list[StargazersDict]) -> tuple[int, int]:
    from datetime import timedelta

    all_dates = sorted(date for info in stargazers for date in info["dates"])
    total = len(all_dates)
    if not all_dates:
        return 0, 0
    cutoff = all_dates[-1] - timedelta(days=365)
    last_year = sum(1 for d in all_dates if d >= cutoff)
    return total, last_year


def split(x: list, at_index: int = 5) -> tuple[list, list]:
    return x[:at_index], x[at_index:]


class StargazersDict(TypedDict):
    full_name: str
    dates: list[str]
    stargazer_count: int
    stargazers_count: int


class BlogPostDict(TypedDict):
    title: str
    url: str
    date: str


async def generate_stargazers_data(
    repos: list[RepoDict],
    token: str,
) -> list[StargazersDict]:
    most_stars = generate_most_stars_data(repos)[:20]

    existing: dict[str, list[str]] = {}
    try:
        with open("data/stargazers.json", "r") as f:
            for entry in json.load(f):
                existing[entry["full_name"]] = entry["dates"]
    except FileNotFoundError:
        pass

    async with httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=60,
    ) as client:
        results: list[StargazersDict] = []
        for repo in most_stars:
            full_name = str(repo["full_name"])
            owner, name = full_name.split("/", 1)
            known_dates = sorted(set(existing.get(full_name, [])))
            latest_known = known_dates[-1] if known_dates else None
            new_dates = await fetch_new_stargazer_dates(
                client, owner, name, latest_known
            )
            if new_dates:
                known_dates = sorted(set(known_dates + new_dates))
            star_count = max(len(known_dates), int(repo["stargazers_count"]))
            results.append(
                {
                    "full_name": full_name,
                    "dates": known_dates,
                    "stargazer_count": star_count,
                    "stargazers_count": star_count,
                }
            )

    with open("data/stargazers.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


async def fetch_latest_blog_posts(
    feed_url: str = BLOG_FEED_URL,
    limit: int = 15,
) -> tuple[list[BlogPostDict], int]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(feed_url)
        response.raise_for_status()

    root = ET.fromstring(response.content)
    posts: list[tuple[datetime, BlogPostDict]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        dt = parsedate_to_datetime(pub_date) if pub_date else datetime.min
        posts.append(
            (
                dt,
                {
                    "title": title,
                    "url": link,
                    "date": dt.strftime("%Y-%m-%d") if pub_date else "",
                },
            )
        )

    posts.sort(key=lambda pair: pair[0], reverse=True)
    latest = [post for _, post in posts[:limit]]
    total = len(posts)
    with open("data/blog_posts.json", "w") as f:
        json.dump({"total": total, "posts": latest}, f, indent=2)
    return latest, total


class Data(NamedTuple):
    repos: list[RepoDict]
    stargazers: list[StargazersDict]
    blog_posts: list[BlogPostDict]
    total_blog_posts: int


async def generate_data() -> Data:
    os.makedirs("data", exist_ok=True)
    token = load_token()
    async with gh_client(token) as gh:
        repos, (blog_posts, total_blog_posts) = await asyncio.gather(
            generate_repos_data(gh),
            fetch_latest_blog_posts(),
        )
        stargazers = await generate_stargazers_data(repos, token)
    return Data(
        repos=repos,
        stargazers=stargazers,
        blog_posts=blog_posts,
        total_blog_posts=total_blog_posts,
    )


def load_data() -> Data:
    with open("data/repos.json", "r") as f:
        repos = json.load(f)

    with open("data/stargazers.json", "r") as f:
        stargazers = json.load(f)
        for info in stargazers:
            info["dates"] = [datetime.fromisoformat(date) for date in info["dates"]]
            if "stargazers_count" not in info:
                info["stargazers_count"] = info.get(
                    "stargazer_count", len(info["dates"])
                )
            if "stargazer_count" not in info:
                info["stargazer_count"] = len(info["dates"])

    try:
        with open("data/blog_posts.json", "r") as f:
            blog_payload = json.load(f)
        if isinstance(blog_payload, dict):
            blog_posts = blog_payload.get("posts", [])
            total_blog_posts = int(blog_payload.get("total", len(blog_posts)))
        else:
            blog_posts = blog_payload
            total_blog_posts = len(blog_posts)
    except FileNotFoundError:
        blog_posts = []
        total_blog_posts = 0

    return Data(
        repos=repos,
        stargazers=stargazers,
        blog_posts=blog_posts,
        total_blog_posts=total_blog_posts,
    )
