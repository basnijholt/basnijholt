# notebook_to_module.py
from __future__ import annotations

import asyncio
import logging
import os
import json
from collections import defaultdict
from collections.abc import Iterable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, TypeAlias, TypedDict, NamedTuple

import gidgethub.httpx
import httpx
import tenacity

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger(__name__)
ME = "basnijholt"
orgs = (ME, "python-adaptive", "topocm", "python-kasa", "kwant-project", "pipefunc")
RepoDict: TypeAlias = dict[str, Any]
OrgRepoDict: TypeAlias = dict[str, Any]


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


def split(x: list, at_index: int = 5) -> tuple[list, list]:
    return x[:at_index], x[at_index:]


class StargazersDict(TypedDict):
    full_name: str
    dates: list[str]
    stargazer_count: int
    stargazers_count: int


async def generate_stargazers_data(
    repos: list[RepoDict],
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
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
        },
        timeout=60,
    ) as client:
        results = []
        for repo in most_stars:
            full_name = repo["full_name"]
            owner, name = full_name.split("/", 1)
            known_dates = sorted(set(existing.get(full_name, [])))
            latest_known = known_dates[-1] if known_dates else None
            new_dates = await fetch_new_stargazer_dates(
                client, owner, name, latest_known
            )
            if new_dates:
                known_dates = sorted(set(known_dates + new_dates))
            results.append(
                {
                    "full_name": full_name,
                    "dates": known_dates,
                    "stargazer_count": len(known_dates),
                    "stargazers_count": len(known_dates),
                }
            )

    stargazers = results
    with open("data/stargazers.json", "w") as f:
        json.dump(stargazers, f, indent=2)

    return stargazers


class Data(NamedTuple):
    repos: list[RepoDict]
    stargazers: list[StargazersDict]


async def generate_data() -> Data:
    # Create data folder if it doesn't exist
    os.makedirs("data", exist_ok=True)
    async with gh_client(TOKEN) as gh:
        repos = await generate_repos_data(gh)
        stargazers = await generate_stargazers_data(repos)
    return Data(
        repos=repos,
        stargazers=stargazers,
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

    return Data(
        repos=repos,
        stargazers=stargazers,
    )


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
