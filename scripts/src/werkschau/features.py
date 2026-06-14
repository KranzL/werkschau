from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import PurePosixPath

_TEST_PATTERN = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs)(/|$)|(_test|\.test|\.spec)\.[a-zA-Z]+$"
)

_LOCKFILE_NAMES = frozenset({
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "uv.lock",
    "bun.lockb",
    "requirements.txt",
})

_DOCS_EXTS = (".md", ".rst", ".txt", ".adoc")


def commit_features(detail: dict) -> dict:
    files = detail.get("files") or []
    file_paths = [f.get("filename", "") for f in files]
    additions = sum(int(f.get("additions") or 0) for f in files)
    deletions = sum(int(f.get("deletions") or 0) for f in files)
    churn = additions + deletions
    parents = detail.get("parents") or []
    is_merge = len(parents) > 1
    commit_obj = detail.get("commit") or {}
    message = commit_obj.get("message") or ""
    first_line = message.split("\n", 1)[0]
    is_revert = first_line.lower().startswith("revert")
    test_count = sum(1 for p in file_paths if _TEST_PATTERN.search(p))
    test_ratio = (test_count / len(file_paths)) if file_paths else 0.0
    is_dep_bump = bool(file_paths) and all(
        PurePosixPath(p).name in _LOCKFILE_NAMES for p in file_paths
    )
    is_docs_only = bool(file_paths) and all(_is_docs_path(p) for p in file_paths)
    unique_top_dirs = len({
        (PurePosixPath(p).parts[0] if PurePosixPath(p).parts else "")
        for p in file_paths
    })
    file_status_counts = dict(Counter(
        (f.get("status") or "modified") for f in files
    ))
    committer = commit_obj.get("committer") or {}
    iso = committer.get("date") or ""
    if iso:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    else:
        when = datetime.now(timezone.utc)
    author_login = (detail.get("author") or {}).get("login")
    author_name = (commit_obj.get("author") or {}).get("name")
    co_authors = _co_authors(message)
    change_kind = _classify_change_kind(
        additions=additions,
        deletions=deletions,
        files=len(files),
        is_merge=is_merge,
        is_revert=is_revert,
        is_dep_bump=is_dep_bump,
        is_docs_only=is_docs_only,
        test_ratio=test_ratio,
        file_status_counts=file_status_counts,
    )
    return {
        "sha": detail.get("sha", ""),
        "url": detail.get("html_url", ""),
        "author_login": author_login,
        "author_name": author_name,
        "co_authors": co_authors,
        "committer_date_utc": iso,
        "hour_utc": when.hour,
        "weekday": when.strftime("%A"),
        "message_first_line": first_line[:240],
        "message_length": len(message),
        "additions": additions,
        "deletions": deletions,
        "churn": churn,
        "files_changed": len(files),
        "unique_top_dirs": unique_top_dirs,
        "file_paths_sample": file_paths[:25],
        "file_status_counts": file_status_counts,
        "test_ratio": round(test_ratio, 3),
        "is_merge": is_merge,
        "is_revert": is_revert,
        "is_dependency_bump": is_dep_bump,
        "is_docs_only": is_docs_only,
        "change_kind": change_kind,
        "is_substantive": change_kind not in {"noise"},
        "heuristic_effort_minutes": _heuristic_effort_minutes(
            churn=churn,
            files=len(files),
            is_merge=is_merge,
            is_revert=is_revert,
            is_dep_bump=is_dep_bump,
            is_docs_only=is_docs_only,
            change_kind=change_kind,
        ),
    }


def _is_docs_path(path: str) -> bool:
    if not path:
        return False
    p = path.lower()
    if p.endswith(_DOCS_EXTS):
        return True
    if "/docs/" in p or p.startswith("docs/"):
        return True
    return False


def _classify_change_kind(
    *,
    additions: int,
    deletions: int,
    files: int,
    is_merge: bool,
    is_revert: bool,
    is_dep_bump: bool,
    is_docs_only: bool,
    test_ratio: float,
    file_status_counts: dict[str, int],
) -> str:
    if is_merge or is_revert or is_dep_bump or is_docs_only:
        return "noise"
    churn = additions + deletions
    renamed = file_status_counts.get("renamed", 0)
    if files > 0 and renamed / files >= 0.6:
        return "rename"
    if files <= 1 and churn <= 5 and test_ratio == 0.0:
        return "noise"
    if churn == 0:
        return "noise"
    add_share = additions / churn if churn else 0.0
    if files >= 2 and 0.3 <= add_share <= 0.7:
        return "refactor"
    if add_share >= 0.85 and additions >= 20:
        return "addition"
    if add_share <= 0.15 and deletions >= 20:
        return "deletion"
    return "tweak"


def _heuristic_effort_minutes(
    *,
    churn: int,
    files: int,
    is_merge: bool,
    is_revert: bool,
    is_dep_bump: bool,
    is_docs_only: bool,
    change_kind: str,
) -> int:
    if is_dep_bump:
        return 5
    if is_merge:
        return 5
    if is_revert:
        return 15
    if is_docs_only:
        return max(5, min(int(round(2 + churn * 0.05)), 30))
    base = 10.0
    base += min(churn * 0.3, 120.0)
    base += max(files - 1, 0) * 3.0
    return int(round(base))


_CO_AUTHOR_RE = re.compile(r"^Co-Authored-By:\s*(.+?)\s*<", re.IGNORECASE | re.MULTILINE)


def _co_authors(message: str) -> list[str]:
    return [m.strip() for m in _CO_AUTHOR_RE.findall(message)]
