from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _cache_root() -> Path:
    override = os.environ.get("WERKSCHAU_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "werkschau" / "diffs"


def _path(owner: str, repo: str, sha: str) -> Path:
    safe_owner = owner.replace("/", "_")
    safe_repo = repo.replace("/", "_")
    return _cache_root() / f"{safe_owner}--{safe_repo}--{sha}.json"


def get_cached_commit(owner: str, repo: str, sha: str) -> Any | None:
    path = _path(owner, repo, sha)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def set_cached_commit(owner: str, repo: str, sha: str, detail: Any) -> None:
    path = _path(owner, repo, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(detail))
