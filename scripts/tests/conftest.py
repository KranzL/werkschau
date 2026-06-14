from __future__ import annotations

from datetime import datetime, timezone


def make_detail(
    sha: str = "a" * 40,
    message: str = "feat(auth): add token rotation",
    files: list[dict] | None = None,
    parents: int = 1,
    when: datetime | None = None,
    author_login: str = "alice",
    author_name: str = "Alice Doe",
) -> dict:
    files = files if files is not None else [
        {"filename": "src/auth/tokens.py", "status": "modified", "additions": 80, "deletions": 30},
        {"filename": "tests/auth/test_tokens.py", "status": "added", "additions": 40, "deletions": 0},
    ]
    when = when or datetime(2026, 6, 10, 14, 0, tzinfo=timezone.utc)
    return {
        "sha": sha,
        "html_url": f"https://github.com/foo/bar/commit/{sha}",
        "author": {"login": author_login},
        "commit": {
            "message": message,
            "author": {"name": author_name},
            "committer": {"date": when.strftime("%Y-%m-%dT%H:%M:%SZ")},
        },
        "parents": [{"sha": "p" * 40}] * parents,
        "files": files,
    }


def make_commit(
    sha: str = "a" * 40,
    repo: str = "foo/bar",
    when: datetime | None = None,
    message: str = "feat(auth): add token rotation",
    additions: int = 80,
    deletions: int = 30,
    files_changed: int = 2,
    unique_top_dirs: int = 1,
    file_paths: list[str] | None = None,
    change_kind: str = "refactor",
    is_substantive: bool = True,
    heuristic_effort_minutes: int = 120,
    is_merge: bool = False,
    is_revert: bool = False,
    is_dependency_bump: bool = False,
    is_docs_only: bool = False,
    test_ratio: float = 0.5,
) -> dict:
    when = when or datetime(2026, 6, 10, 14, 0, tzinfo=timezone.utc)
    return {
        "sha": sha,
        "repo": repo,
        "committer_date_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hour_utc": when.hour,
        "weekday": when.strftime("%A"),
        "message_first_line": message,
        "additions": additions,
        "deletions": deletions,
        "churn": additions + deletions,
        "files_changed": files_changed,
        "unique_top_dirs": unique_top_dirs,
        "file_paths_sample": file_paths or ["src/auth/tokens.py"],
        "test_ratio": test_ratio,
        "is_merge": is_merge,
        "is_revert": is_revert,
        "is_dependency_bump": is_dependency_bump,
        "is_docs_only": is_docs_only,
        "change_kind": change_kind,
        "is_substantive": is_substantive,
        "heuristic_effort_minutes": heuristic_effort_minutes,
    }
