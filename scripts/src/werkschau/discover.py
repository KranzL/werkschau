from __future__ import annotations

from datetime import datetime

from .gh_api import gh_api


def discover_repos(user: str, since: datetime, until: datetime) -> list[tuple[str, str]]:
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
    return sorted(repos)


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
