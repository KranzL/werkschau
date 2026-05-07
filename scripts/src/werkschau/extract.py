from __future__ import annotations

from datetime import datetime
from typing import Any

from .cache import get_cached_commit, set_cached_commit
from .gh_api import gh_api


def extract_commits(owner: str, repo: str, user: str, since: datetime, until: datetime) -> list[dict]:
    fields = {
        "author": user,
        "since": _to_iso_z(since),
        "until": _to_iso_z(until),
        "per_page": "100",
    }
    return gh_api(f"/repos/{owner}/{repo}/commits", paginate=True, fields=fields)


def extract_commit_detail(owner: str, repo: str, sha: str) -> Any:
    cached = get_cached_commit(owner, repo, sha)
    if cached is not None:
        return cached
    detail = gh_api(f"/repos/{owner}/{repo}/commits/{sha}")
    set_cached_commit(owner, repo, sha, detail)
    return detail


def _to_iso_z(dt: datetime) -> str:
    s = dt.isoformat()
    return s.replace("+00:00", "Z")
