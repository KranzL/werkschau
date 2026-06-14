from __future__ import annotations

from datetime import datetime, timedelta, timezone

from werkschau.scoring import (
    INACTIVE_SUBSTANTIVE_MINUTES_PER_WEEK,
    cluster_initiatives,
    offgrid_scores,
    score_user,
)

from .conftest import make_commit


def _payload(commits):
    return {
        "user": "alice",
        "level": "l4",
        "commits": commits,
        "commit_count": len(commits),
        "total_churn": sum(c.get("churn", 0) for c in commits),
        "total_heuristic_effort_minutes": sum(c.get("heuristic_effort_minutes", 0) for c in commits),
        "repos_visited": sorted({c.get("repo") for c in commits if c.get("repo")}),
        "repo_count": len({c.get("repo") for c in commits if c.get("repo")}),
    }


def test_busy_substantive_week_is_not_inactive():
    commits = [
        make_commit(sha=f"a{i:039x}") for i in range(6)
    ]
    scores = score_user(_payload(commits), level="l4", role="swe", window_days=7)
    assert scores.inactive is False
    assert scores.substance > 0.5
    assert scores.substantive_minutes > INACTIVE_SUBSTANTIVE_MINUTES_PER_WEEK


def test_all_dep_bumps_is_inactive():
    commits = [
        make_commit(
            sha=f"b{i:039x}",
            message="chore: bump deps",
            change_kind="noise",
            is_substantive=False,
            is_dependency_bump=True,
            file_paths=["package-lock.json"],
            additions=20,
            deletions=20,
            heuristic_effort_minutes=5,
        )
        for i in range(8)
    ]
    scores = score_user(_payload(commits), level="l4", role="swe", window_days=7)
    assert scores.inactive is True
    assert scores.substantive_commit_count == 0
    assert scores.substance < 0.2


def test_one_substantive_commit_above_threshold_is_not_inactive():
    commits = [
        make_commit(
            sha="c" * 40,
            message="feat(auth): rewrite",
            additions=300,
            deletions=200,
            files_changed=8,
            heuristic_effort_minutes=200,
        )
    ]
    scores = score_user(_payload(commits), level="l4", role="swe", window_days=7)
    assert scores.inactive is False
    assert scores.substance > 0


def test_zero_commits_is_inactive():
    scores = score_user(_payload([]), level="l4", role="swe", window_days=7)
    assert scores.inactive is True
    assert scores.substance == -1.0
    assert scores.output == -1.0


def test_substance_below_substantive_threshold_scales_with_window():
    light = [
        make_commit(
            sha="d" * 40,
            additions=10,
            deletions=5,
            heuristic_effort_minutes=15,
            change_kind="tweak",
            is_substantive=True,
        )
    ]
    week_scores = score_user(_payload(light), level="l4", role="swe", window_days=7)
    fortnight_scores = score_user(_payload(light), level="l4", role="swe", window_days=14)
    assert week_scores.inactive is True
    assert fortnight_scores.inactive is True


def test_change_kind_mix_reflects_weighted_minutes():
    commits = [
        make_commit(sha="e1" + "0" * 38, change_kind="refactor", heuristic_effort_minutes=120),
        make_commit(sha="e2" + "0" * 38, change_kind="refactor", heuristic_effort_minutes=120),
        make_commit(
            sha="e3" + "0" * 38,
            change_kind="noise",
            is_substantive=False,
            is_dependency_bump=True,
            file_paths=["package-lock.json"],
            heuristic_effort_minutes=5,
        ),
    ]
    scores = score_user(_payload(commits), level="l4", role="swe", window_days=7)
    assert "refactor" in scores.change_kind_mix
    assert scores.change_kind_mix["refactor"] > scores.change_kind_mix.get("noise", 0)


def test_offgrid_scores_are_inactive():
    s = offgrid_scores()
    assert s.inactive is True
    assert s.substance == -1.0
    assert s.output == -1.0
    assert s.commit_count == 0


def test_cluster_initiatives_groups_by_shared_token_within_48h():
    base = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
    commits = [
        make_commit(sha="a" * 40, when=base, message="feat(auth): rotate tokens", file_paths=["src/auth/x.py"]),
        make_commit(sha="b" * 40, when=base + timedelta(hours=4), message="feat(auth): rotate cleanup", file_paths=["src/auth/y.py"]),
        make_commit(sha="c" * 40, when=base + timedelta(days=10), message="chore(search): add index", file_paths=["src/search/index.py"]),
    ]
    initiatives = cluster_initiatives(commits)
    assert len(initiatives) == 2
    top = initiatives[0]
    assert "auth" in top.name or top.commit_count == 2


def test_cluster_initiatives_drops_merges():
    base = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
    commits = [
        make_commit(sha="a" * 40, when=base, is_merge=True, message="Merge branch 'x'"),
        make_commit(sha="b" * 40, when=base + timedelta(hours=2), message="feat(auth): real change"),
    ]
    initiatives = cluster_initiatives(commits)
    assert len(initiatives) == 1
    assert initiatives[0].commit_count == 1
