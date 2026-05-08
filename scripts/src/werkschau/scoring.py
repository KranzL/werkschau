from __future__ import annotations

import math
import os
from collections import defaultdict
from dataclasses import dataclass

from .levels import baseline_minutes


WORK_CATEGORIES: tuple[str, ...] = (
    "Features",
    "Bug fixes",
    "Refactor",
    "Infrastructure",
    "Tests",
    "Documentation",
)


@dataclass(frozen=True)
class Scores:
    output: float
    focus: float
    work_label: str
    weighted_minutes: float
    commit_count: int
    repo_count: int


def score_user(user_payload: dict, level: str | None, role: str | None, window_days: int) -> Scores:
    commits = user_payload.get("commits", []) or []
    weighted = sum(_complexity_weighted_effort(c) for c in commits)
    base = baseline_minutes(role, level)
    if base is None or base <= 0:
        output = 0.0
    else:
        scaled_base = base * (window_days / 7.0)
        output = _clip(_log2(weighted, scaled_base), -1.0, 1.0)

    focus = _focus_score(commits)
    label = _dominant_work_label(commits)
    return Scores(
        output=output,
        focus=focus,
        work_label=label,
        weighted_minutes=weighted,
        commit_count=len(commits),
        repo_count=len({c.get("repo") for c in commits if c.get("repo")}),
    )


def _complexity_weighted_effort(commit: dict) -> float:
    base = float(commit.get("heuristic_effort_minutes") or 0)
    if base <= 0:
        return 0.0
    mult = 1.0
    dirs = int(commit.get("unique_top_dirs") or 0)
    if dirs >= 5:
        mult *= 1.4
    elif dirs >= 3:
        mult *= 1.2
    files = int(commit.get("files_changed") or 0)
    additions = int(commit.get("additions") or 0)
    deletions = int(commit.get("deletions") or 0)
    churn = additions + deletions
    if files >= 10 and churn > 0 and 0.3 < (additions / churn) < 0.7:
        mult *= 1.3
    if commit.get("test_ratio") and float(commit.get("test_ratio")) > 0.3:
        mult *= 1.15
    if commit.get("is_dependency_bump"):
        mult *= 0.3
    if commit.get("is_merge") or commit.get("is_revert"):
        mult *= 0.4
    if files <= 1 and churn <= 5:
        mult *= 0.6
    mult = max(0.25, min(2.0, mult))
    return base * mult


def _focus_score(commits: list[dict]) -> float:
    if not commits:
        return 0.0
    churn_per_repo: dict[str, float] = defaultdict(float)
    for c in commits:
        repo = c.get("repo") or ""
        if not repo:
            continue
        churn_per_repo[repo] += float(c.get("churn") or 0)
    total = sum(churn_per_repo.values())
    if total <= 0:
        return 0.0
    h = sum((v / total) ** 2 for v in churn_per_repo.values())
    return _clip(2.0 * h - 1.0, -1.0, 1.0)


def _dominant_work_label(commits: list[dict]) -> str:
    if not commits:
        return "—"
    weighted_by_cat: dict[str, float] = defaultdict(float)
    total = 0.0
    for c in commits:
        cat = classify_commit(c)
        w = _complexity_weighted_effort(c)
        weighted_by_cat[cat] += w
        total += w
    if total <= 0:
        return "—"
    top_cat, top_w = max(weighted_by_cat.items(), key=lambda kv: kv[1])
    pct = top_w / total
    if pct < 0.5:
        return "Mixed"
    return f"{top_cat}|{round(pct * 100)}"


def classify_commit(commit: dict) -> str:
    msg = (commit.get("message_first_line") or "").lower().strip()
    files = commit.get("file_paths_sample") or []
    if commit.get("is_dependency_bump"):
        return "Infrastructure"
    if msg.startswith(("feat:", "feat(", "feature:", "feat ", "feature ")):
        return "Features"
    if msg.startswith(("fix:", "fix(", "bug:", "fix ", "bug ", "hotfix")):
        return "Bug fixes"
    if msg.startswith(("refactor:", "refactor(", "refactor ", "cleanup", "refactor ")):
        return "Refactor"
    if msg.startswith(("test:", "test(", "tests:", "tests(", "test ", "tests ")):
        return "Tests"
    if msg.startswith(("docs:", "docs(", "doc:", "doc ", "docs ", "readme", "documentation")):
        return "Documentation"
    if msg.startswith(("ci:", "ci(", "build:", "build(", "chore:", "chore(", "perf:", "perf(")):
        return "Infrastructure"
    test_ratio = float(commit.get("test_ratio") or 0)
    if test_ratio > 0.6:
        return "Tests"
    if files and all(_looks_doc(p) for p in files):
        return "Documentation"
    if files and all(_looks_infra(p) for p in files):
        return "Infrastructure"
    if files and all(_looks_test(p) for p in files):
        return "Tests"
    return "Features"


def _looks_doc(path: str) -> bool:
    p = path.lower()
    return p.endswith((".md", ".rst", ".txt")) or "/docs/" in p or p.startswith("docs/")


def _looks_infra(path: str) -> bool:
    p = path.lower()
    if p.startswith((".github/", "ci/", "ops/", "infra/", "deploy/", "k8s/", "kubernetes/")):
        return True
    base = os.path.basename(p)
    return base in {"dockerfile", "makefile", "pyproject.toml", "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "go.mod", "go.sum", ".gitignore", ".dockerignore", ".gitlab-ci.yml", ".circleci"} or p.endswith((".yml", ".yaml")) and ("github" in p or "ci" in p)


def _looks_test(path: str) -> bool:
    p = path.lower()
    return ("/tests/" in p or "/test/" in p or "/__tests__/" in p
            or p.startswith(("tests/", "test/"))
            or p.endswith((".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx"))
            or "_test.py" in os.path.basename(p)
            or "test_" in os.path.basename(p))


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _log2(observed: float, baseline: float) -> float:
    if observed <= 0:
        return -1.0
    return math.log2(observed / baseline)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
