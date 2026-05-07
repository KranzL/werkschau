from __future__ import annotations

import sys
from datetime import datetime

from .gh_api import GhError, gh_api


def discover_repos(user: str, since: datetime, until: datetime) -> list[tuple[str, str]]:
    repos: set[tuple[str, str]] = set()
    try:
        repos.update(_discover_via_events(user, since, until))
    except GhError as exc:
        print(f"[{user}] events discovery failed: {exc}", file=sys.stderr)
    try:
        repos.update(_discover_via_search(user, since, until))
    except GhError as exc:
        print(f"[{user}] search discovery failed: {exc}", file=sys.stderr)
    return sorted(repos)


def _discover_via_events(user: str, since: datetime, until: datetime) -> set[tuple[str, str]]:
    repos: set[tuple[str, str]] = set()
    events = gh_api(f"/users/{user}/events", paginate=True)
    for event in events:
        if event.get("type") != "PushEvent":
            continue
        created_raw = event.get("created_at")
        if not created_raw:
            continue
        created = _parse_iso(created_raw)
        if created < since or created > until:
            continue
        repo_name = (event.get("repo") or {}).get("name", "")
        if "/" in repo_name:
            owner, name = repo_name.split("/", 1)
            repos.add((owner, name))
    return repos


def _discover_via_search(
    user: str,
    since: datetime,
    until: datetime,
    max_pages: int = 10,
) -> set[tuple[str, str]]:
    repos: set[tuple[str, str]] = set()
    since_iso = _to_iso_z(since)
    until_iso = _to_iso_z(until)
    query = f"author:{user} author-date:{since_iso}..{until_iso}"
    for page in range(1, max_pages + 1):
        result = gh_api(
            "/search/commits",
            fields={"q": query, "per_page": "100", "page": str(page)},
        )
        if not isinstance(result, dict):
            break
        items = result.get("items") or []
        if not items:
            break
        for item in items:
            full = (item.get("repository") or {}).get("full_name", "")
            if "/" in full:
                owner, name = full.split("/", 1)
                repos.add((owner, name))
        total = int(result.get("total_count") or 0)
        if page * 100 >= total:
            break
    return repos


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _to_iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
