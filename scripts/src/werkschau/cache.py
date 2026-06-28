from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


def _cache_root() -> Path:
    override = os.environ.get("WERKSCHAU_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "werkschau" / "diffs"


def _responses_root() -> Path:
    override = os.environ.get("WERKSCHAU_CACHE_DIR")
    if override:
        return Path(override).expanduser() / "responses"
    return Path.home() / ".cache" / "werkschau" / "responses"


def _default_ttl() -> int:
    raw = os.environ.get("WERKSCHAU_CACHE_TTL")
    if raw:
        return int(raw)
    return 86400


def _response_cache_key(method: str, path: str, paginate: bool, fields: dict | None) -> str:
    payload = json.dumps(
        {
            "method": method,
            "path": path,
            "paginate": paginate,
            "fields": sorted((fields or {}).items()),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def get_cached_response(key: str, root: Path, ttl: int | None = None) -> Any | None:
    file_path = root / f"{key}.json"
    if not file_path.exists():
        return None
    try:
        parsed = json.loads(file_path.read_text())
    except (OSError, ValueError):
        return None
    if (
        isinstance(parsed, dict)
        and isinstance(parsed.get("stored_at"), (int, float))
        and "data" in parsed
    ):
        effective_ttl = ttl if ttl is not None else _default_ttl()
        if effective_ttl >= 0 and time.time() - parsed["stored_at"] >= effective_ttl:
            file_path.unlink(missing_ok=True)
            return None
        return parsed["data"]
    return parsed


def set_cached_response(key: str, root: Path, data: Any) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    envelope = {"stored_at": time.time(), "data": data}
    tmp_path = root / f"{key}.tmp"
    tmp_path.write_text(json.dumps(envelope))
    tmp_path.chmod(0o600)
    os.replace(tmp_path, root / f"{key}.json")


def _path(owner: str, repo: str, sha: str) -> Path:
    safe_owner = owner.replace("/", "_")
    safe_repo = repo.replace("/", "_")
    return _cache_root() / f"{safe_owner}--{safe_repo}--{sha}.json"


def get_cached_commit(owner: str, repo: str, sha: str) -> Any | None:
    key = f"{owner.replace('/', '_')}--{repo.replace('/', '_')}--{sha}"
    return get_cached_response(key, _cache_root(), ttl=-1)


def set_cached_commit(owner: str, repo: str, sha: str, detail: Any) -> None:
    key = f"{owner.replace('/', '_')}--{repo.replace('/', '_')}--{sha}"
    set_cached_response(key, _cache_root(), detail)
