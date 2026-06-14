from __future__ import annotations

from werkschau.features import commit_features

from .conftest import make_detail


def test_default_fixture_is_classified_and_metric_rich():
    out = commit_features(make_detail())
    assert out["is_substantive"] is True
    assert out["additions"] == 120
    assert out["deletions"] == 30
    assert out["test_ratio"] == 0.5
    assert out["file_status_counts"] == {"modified": 1, "added": 1}
    assert out["is_dependency_bump"] is False
    assert out["is_docs_only"] is False


def test_balanced_addel_with_multiple_files_is_refactor():
    detail = make_detail(
        files=[
            {"filename": "src/auth/tokens.py", "status": "modified", "additions": 60, "deletions": 55},
            {"filename": "src/auth/cleanup.py", "status": "modified", "additions": 40, "deletions": 45},
        ],
        message="refactor(auth): split tokens / cleanup",
    )
    out = commit_features(detail)
    assert out["change_kind"] == "refactor"


def test_lockfile_only_is_noise_dep_bump():
    detail = make_detail(
        files=[{"filename": "package-lock.json", "status": "modified", "additions": 200, "deletions": 200}],
        message="chore: bump deps",
    )
    out = commit_features(detail)
    assert out["is_dependency_bump"] is True
    assert out["change_kind"] == "noise"
    assert out["is_substantive"] is False
    assert out["heuristic_effort_minutes"] == 5


def test_docs_only_is_noise():
    detail = make_detail(
        files=[
            {"filename": "README.md", "status": "modified", "additions": 30, "deletions": 5},
            {"filename": "docs/intro.md", "status": "modified", "additions": 20, "deletions": 2},
        ],
        message="docs: clean up",
    )
    out = commit_features(detail)
    assert out["is_docs_only"] is True
    assert out["change_kind"] == "noise"
    assert out["is_substantive"] is False


def test_merge_is_noise():
    detail = make_detail(parents=2, message="Merge branch 'main' into feature")
    out = commit_features(detail)
    assert out["is_merge"] is True
    assert out["change_kind"] == "noise"
    assert out["heuristic_effort_minutes"] == 5


def test_revert_is_noise():
    detail = make_detail(message="Revert \"feat(auth): add token rotation\"")
    out = commit_features(detail)
    assert out["is_revert"] is True
    assert out["change_kind"] == "noise"


def test_pure_addition():
    detail = make_detail(
        files=[
            {"filename": "src/search/handler.py", "status": "added", "additions": 220, "deletions": 0},
            {"filename": "src/search/index.py", "status": "added", "additions": 60, "deletions": 0},
        ],
        message="feat(search): add FTS handler",
    )
    out = commit_features(detail)
    assert out["change_kind"] == "addition"


def test_pure_deletion():
    detail = make_detail(
        files=[
            {"filename": "src/legacy/cron.py", "status": "removed", "additions": 0, "deletions": 180},
        ],
        message="chore: drop legacy cron",
    )
    out = commit_features(detail)
    assert out["change_kind"] == "deletion"
    assert out["file_status_counts"] == {"removed": 1}


def test_rename_classification():
    detail = make_detail(
        files=[
            {"filename": "src/auth/new_tokens.py", "status": "renamed", "additions": 5, "deletions": 5},
            {"filename": "src/auth/new_helpers.py", "status": "renamed", "additions": 2, "deletions": 2},
            {"filename": "src/auth/__init__.py", "status": "modified", "additions": 3, "deletions": 1},
        ],
        message="chore: rename auth modules",
    )
    out = commit_features(detail)
    assert out["change_kind"] == "rename"


def test_tiny_tweak_is_noise():
    detail = make_detail(
        files=[{"filename": "src/util.py", "status": "modified", "additions": 1, "deletions": 1}],
        message="fix: typo",
    )
    out = commit_features(detail)
    assert out["change_kind"] == "noise"
    assert out["is_substantive"] is False


def test_co_authors_extracted():
    detail = make_detail(
        message="feat: shared work\n\nCo-Authored-By: Bob Clark <bob@example.com>\nCo-Authored-By: Carol Lee <carol@example.com>",
    )
    out = commit_features(detail)
    assert out["co_authors"] == ["Bob Clark", "Carol Lee"]
