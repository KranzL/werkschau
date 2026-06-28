from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


__all__: list[str] = [
    "WORK_KIND_WEIGHTS",
    "NOISE_CHANGE_KINDS",
    "CLUSTER_TIME_WINDOW",
    "MIN_TOKEN_LENGTH",
    "INACTIVE_SUBSTANTIVE_MINUTES_PER_WEEK",
    "ACTIVITY_TIER_QUIET_MAX",
    "ACTIVITY_TIER_BUSY_MIN",
    "activity_tier",
    "Initiative",
    "OUTPUT_BASELINE_MINUTES",
    "SUBSTANCE_SMOOTHING_MINUTES",
    "Scores",
    "score_user",
    "offgrid_scores",
    "cluster_initiatives",
    "median",
]


WORK_KIND_WEIGHTS: dict[str, float] = {
    "code": 1.0,
    "data_pipeline": 1.0,
    "test": 1.0,
    "infra": 1.0,
    "config": 0.6,
    "docs": 0.2,
    "lockfile": 0.1,
    "other": 0.5,
}

NOISE_CHANGE_KINDS: frozenset[str] = frozenset({"noise"})

CLUSTER_TIME_WINDOW = timedelta(hours=48)
MIN_TOKEN_LENGTH = 4

INACTIVE_SUBSTANTIVE_MINUTES_PER_WEEK = 60.0

ACTIVITY_TIER_QUIET_MAX: int = 10
ACTIVITY_TIER_BUSY_MIN: int = 30


def activity_tier(events: int) -> str:
    if events < ACTIVITY_TIER_QUIET_MAX:
        return "quiet"
    if events >= ACTIVITY_TIER_BUSY_MIN:
        return "busy"
    return "steady"


_STOPWORDS: frozenset[str] = frozenset({
    "feat", "feats", "feature", "features", "fix", "fixes", "fixed", "hotfix",
    "chore", "chores", "refactor", "refactors", "refactored", "refactoring",
    "docs", "doc", "documentation", "test", "tests", "testing",
    "update", "updates", "updated", "updating",
    "add", "adds", "added", "adding",
    "remove", "removes", "removed", "removing",
    "delete", "deletes", "deleted", "deleting",
    "bump", "bumps", "bumped", "version", "versions", "versioning",
    "config", "configs", "configure", "configured", "configuration",
    "build", "builds", "built", "deploy", "deploys", "deployed", "deployment",
    "merge", "merges", "merged", "revert", "reverts", "reverted",
    "improve", "improves", "improved", "improving", "improvement",
    "make", "makes", "made", "making", "use", "uses", "used", "using",
    "support", "supports", "supported", "supporting",
    "create", "creates", "created", "creating",
    "rename", "renames", "renamed", "renaming",
    "from", "into", "with", "this", "that", "these", "those", "their", "them",
    "and", "the", "for", "but", "out", "off", "now", "new", "old", "all",
    "more", "less", "most", "least", "some", "any", "any", "many", "much",
    "small", "big", "tiny", "large",
    "wip", "todo", "fixme",
    "change", "changes", "changed", "changing",
    "tweak", "tweaks", "tweaked", "tidy", "polish", "cleanup", "clean",
    "minor", "major", "patch", "patches", "patched",
    "thing", "things", "stuff", "misc",
})


@dataclass(frozen=True)
class Initiative:
    name: str
    weighted_minutes: float
    commit_count: int
    repos: tuple[str, ...]
    sample_messages: tuple[str, ...]
    sample_shas: tuple[str, ...]


OUTPUT_BASELINE_MINUTES = 600.0
SUBSTANCE_SMOOTHING_MINUTES = 80.0


@dataclass(frozen=True)
class Scores:
    weighted_minutes: float
    substantive_minutes: float
    commit_count: int
    substantive_commit_count: int
    repo_count: int
    output: float
    substance: float
    inactive: bool
    work_kind_mix: dict[str, float]
    change_kind_mix: dict[str, float]
    churn_by_kind: dict[str, int]
    loc_by_language: dict[str, int]
    initiatives: tuple[Initiative, ...]

    @property
    def initiative_count(self) -> int:
        return len(self.initiatives)

    @property
    def top_initiative(self) -> Initiative | None:
        return self.initiatives[0] if self.initiatives else None

    @property
    def top_initiative_share(self) -> float:
        if not self.initiatives or self.weighted_minutes <= 0:
            return 0.0
        return self.initiatives[0].weighted_minutes / self.weighted_minutes


def score_user(user_payload: dict, level: str | None, role: str | None, window_days: int) -> Scores:
    commits = user_payload.get("commits", []) or []
    weighted_total = 0.0
    substantive_total = 0.0
    substantive_commits = 0
    kind_effort: dict[str, float] = defaultdict(float)
    kind_churn: dict[str, float] = defaultdict(float)
    lang_churn: dict[str, float] = defaultdict(float)
    change_kind_effort: dict[str, float] = defaultdict(float)
    for c in commits:
        w = _commit_effort(c)
        weighted_total += w
        if _is_substantive(c):
            substantive_total += w
            substantive_commits += 1
        change_kind_effort[c.get("change_kind") or "tweak"] += w
        churn = float((c.get("additions") or 0) + (c.get("deletions") or 0))
        for kind, share in _commit_kind_mix(c).items():
            kind_effort[kind] += w * share
            kind_churn[kind] += churn * share
        for lang, share in _commit_language_mix(c).items():
            lang_churn[lang] += churn * share

    if weighted_total > 0:
        work_kind_mix = {k: v / weighted_total for k, v in kind_effort.items() if v > 0}
        change_kind_mix = {k: v / weighted_total for k, v in change_kind_effort.items() if v > 0}
    else:
        work_kind_mix = {}
        change_kind_mix = {}
    churn_by_kind = {k: int(round(v)) for k, v in kind_churn.items() if v >= 1}
    loc_by_language = {k: int(round(v)) for k, v in lang_churn.items() if v >= 1}

    initiatives = cluster_initiatives(commits)
    output = _output_score(weighted_total, window_days)
    substance = _substance_score(substantive_total, weighted_total)
    inactive = _is_inactive(
        commit_count=len(commits),
        substantive_minutes=substantive_total,
        substantive_commits=substantive_commits,
        window_days=window_days,
    )

    return Scores(
        weighted_minutes=weighted_total,
        substantive_minutes=substantive_total,
        commit_count=len(commits),
        substantive_commit_count=substantive_commits,
        repo_count=len({c.get("repo") for c in commits if c.get("repo")}),
        output=output,
        substance=substance,
        inactive=inactive,
        work_kind_mix=dict(sorted(work_kind_mix.items(), key=lambda kv: kv[1], reverse=True)),
        change_kind_mix=dict(sorted(change_kind_mix.items(), key=lambda kv: kv[1], reverse=True)),
        churn_by_kind=dict(sorted(churn_by_kind.items(), key=lambda kv: kv[1], reverse=True)),
        loc_by_language=dict(sorted(loc_by_language.items(), key=lambda kv: kv[1], reverse=True)),
        initiatives=tuple(initiatives),
    )


def _output_score(weighted_total: float, window_days: int) -> float:
    if weighted_total <= 0:
        return -1.0
    scaled = OUTPUT_BASELINE_MINUTES * (window_days / 7.0)
    return _clip(math.log2(weighted_total / scaled), -1.0, 1.0)


def _substance_score(substantive_minutes: float, weighted_total: float) -> float:
    if weighted_total <= 0:
        return -1.0
    alpha = SUBSTANCE_SMOOTHING_MINUTES
    smoothed_frac = (substantive_minutes + alpha) / (weighted_total + 2 * alpha)
    return _clip(2.0 * smoothed_frac - 1.0, -1.0, 1.0)


def _is_inactive(
    *,
    commit_count: int,
    substantive_minutes: float,
    substantive_commits: int,
    window_days: int,
) -> bool:
    if commit_count == 0:
        return True
    if substantive_commits == 0:
        return True
    threshold = INACTIVE_SUBSTANTIVE_MINUTES_PER_WEEK * (max(1, window_days) / 7.0)
    return substantive_minutes < threshold


def _is_substantive(commit: dict) -> bool:
    explicit = commit.get("is_substantive")
    if explicit is not None:
        return bool(explicit)
    kind = commit.get("change_kind")
    if kind is not None:
        return kind not in NOISE_CHANGE_KINDS
    return not (
        commit.get("is_merge")
        or commit.get("is_revert")
        or commit.get("is_dependency_bump")
        or commit.get("is_docs_only")
    )


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def offgrid_scores() -> Scores:
    return Scores(
        weighted_minutes=0.0,
        substantive_minutes=0.0,
        commit_count=0,
        substantive_commit_count=0,
        repo_count=0,
        output=-1.0,
        substance=-1.0,
        inactive=True,
        work_kind_mix={},
        change_kind_mix={},
        churn_by_kind={},
        loc_by_language={},
        initiatives=(),
    )


def cluster_initiatives(commits: list[dict]) -> list[Initiative]:
    if not commits:
        return []

    enriched: list[dict] = []
    for c in commits:
        if c.get("is_merge"):
            continue
        msg = (c.get("message_first_line") or "")
        scope = _conventional_scope(msg)
        tokens = _meaningful_tokens(msg)
        dirs = _top_dirs(c.get("file_paths_sample") or [], depth=2)
        ts = _parse_iso(c.get("committer_date_utc"))
        if ts is None:
            continue
        enriched.append({
            "commit": c,
            "scope": scope,
            "tokens": tokens,
            "dirs": dirs,
            "ts": ts,
        })

    if not enriched:
        return []

    enriched.sort(key=lambda e: e["ts"])
    n = len(enriched)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        ei = enriched[i]
        for j in range(i + 1, n):
            ej = enriched[j]
            if ej["ts"] - ei["ts"] > CLUSTER_TIME_WINDOW:
                break
            if ei["scope"] and ei["scope"] == ej["scope"]:
                union(i, j); continue
            if ei["tokens"] and ei["tokens"] & ej["tokens"]:
                union(i, j); continue
            if ei["dirs"] and ei["dirs"] & ej["dirs"]:
                union(i, j); continue

    cluster_members: dict[int, list[dict]] = defaultdict(list)
    for i in range(n):
        cluster_members[find(i)].append(enriched[i])

    initiatives: list[Initiative] = []
    for members in cluster_members.values():
        commits_in = [m["commit"] for m in members]
        weighted = sum(_commit_effort(c) for c in commits_in)
        if weighted <= 0:
            continue
        token_counts: dict[str, int] = defaultdict(int)
        for m in members:
            for t in m["tokens"]:
                token_counts[t] += 1
        scope_counts: dict[str, int] = defaultdict(int)
        for m in members:
            if m["scope"]:
                scope_counts[m["scope"]] += 1
        dir_counts: dict[str, int] = defaultdict(int)
        for m in members:
            for d in m["dirs"]:
                dir_counts[d] += 1
        repos = tuple(sorted({c.get("repo") for c in commits_in if c.get("repo")}))
        name = _initiative_name(token_counts, scope_counts, dir_counts, repos, commits_in)
        initiatives.append(Initiative(
            name=name,
            weighted_minutes=weighted,
            commit_count=len(commits_in),
            repos=repos,
            sample_messages=tuple(
                (c.get("message_first_line") or "")[:120]
                for c in sorted(commits_in, key=lambda c: _commit_effort(c), reverse=True)[:5]
            ),
            sample_shas=tuple(
                (c.get("sha") or "")[:8]
                for c in sorted(commits_in, key=lambda c: _commit_effort(c), reverse=True)[:5]
            ),
        ))

    initiatives.sort(key=lambda i: i.weighted_minutes, reverse=True)
    return initiatives


def _initiative_name(
    token_counts: dict[str, int],
    scope_counts: dict[str, int],
    dir_counts: dict[str, int],
    repos: tuple[str, ...],
    commits: list[dict],
) -> str:
    if scope_counts:
        scope, _ = max(scope_counts.items(), key=lambda kv: kv[1])
        return scope.replace("-", " ").replace("_", " ")
    if token_counts:
        ranked = sorted(token_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top_two = [t for t, c in ranked[:2] if c >= 1]
        if len(top_two) >= 2 and ranked[1][1] >= max(2, ranked[0][1] // 2):
            return f"{top_two[0]} {top_two[1]}"
        return top_two[0]
    if dir_counts:
        d, _ = max(dir_counts.items(), key=lambda kv: kv[1])
        return d.replace("/", " ")
    if repos:
        repo = repos[0]
        return repo.split("/", 1)[1] if "/" in repo else repo
    if commits:
        msg = (commits[0].get("message_first_line") or "").strip()
        return msg[:48] if msg else "untitled"
    return "untitled"


def _commit_effort(commit: dict) -> float:
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
        mult *= 1.1
    if commit.get("is_dependency_bump"):
        mult *= 0.3
    if commit.get("is_docs_only"):
        mult *= 0.5
    if commit.get("is_merge") or commit.get("is_revert"):
        mult *= 0.4
    if files <= 1 and churn <= 5:
        mult *= 0.6
    mult = max(0.2, min(2.0, mult))
    work_weight = _commit_work_kind_weight(commit)
    return base * mult * work_weight


def _commit_work_kind_weight(commit: dict) -> float:
    paths = commit.get("file_paths_sample") or []
    if not paths:
        return WORK_KIND_WEIGHTS["other"]
    if commit.get("is_dependency_bump"):
        return WORK_KIND_WEIGHTS["lockfile"]
    weights = [WORK_KIND_WEIGHTS.get(_file_kind(p), WORK_KIND_WEIGHTS["other"]) for p in paths]
    return sum(weights) / len(weights)


def _commit_kind_mix(commit: dict) -> dict[str, float]:
    paths = commit.get("file_paths_sample") or []
    if not paths:
        return {"other": 1.0}
    if commit.get("is_dependency_bump"):
        return {"lockfile": 1.0}
    counts: dict[str, int] = defaultdict(int)
    for p in paths:
        counts[_file_kind(p)] += 1
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()}


def _commit_language_mix(commit: dict) -> dict[str, float]:
    paths = commit.get("file_paths_sample") or []
    if not paths:
        return {}
    if commit.get("is_dependency_bump"):
        return {"Dependencies": 1.0}
    counts: dict[str, int] = defaultdict(int)
    for p in paths:
        lang = _file_language(p)
        if lang:
            counts[lang] += 1
    if not counts:
        return {}
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()}


_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    "py": "Python", "pyi": "Python",
    "ts": "TypeScript", "tsx": "TypeScript",
    "js": "JavaScript", "jsx": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript",
    "go": "Go",
    "rs": "Rust",
    "java": "Java",
    "kt": "Kotlin", "kts": "Kotlin",
    "scala": "Scala",
    "swift": "Swift",
    "rb": "Ruby",
    "cpp": "C++", "cc": "C++", "cxx": "C++", "hpp": "C++", "hxx": "C++",
    "c": "C", "h": "C",
    "cs": "C#",
    "php": "PHP",
    "clj": "Clojure", "cljs": "Clojure",
    "ex": "Elixir", "exs": "Elixir",
    "elm": "Elm",
    "lua": "Lua",
    "m": "Objective-C", "mm": "Objective-C",
    "dart": "Dart",
    "sol": "Solidity",
    "vue": "Vue",
    "svelte": "Svelte",
    "sql": "SQL",
    "tf": "Terraform", "tfvars": "Terraform",
    "yml": "YAML", "yaml": "YAML",
    "json": "JSON",
    "toml": "TOML",
    "md": "Markdown", "rst": "Markdown", "adoc": "Markdown",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell",
    "lkml": "LookML", "lookml": "LookML",
}


def _file_language(path: str) -> str | None:
    if not path:
        return None
    base = path.rsplit("/", 1)[-1].lower()
    if base == "dockerfile" or base.startswith("dockerfile."):
        return "Dockerfile"
    if base in {"makefile", "rakefile", "gemfile"}:
        return base.capitalize()
    if "." not in base:
        return None
    ext = base.rsplit(".", 1)[1]
    return _LANGUAGE_BY_EXTENSION.get(ext)


def _file_kind(path: str) -> str:
    if not path:
        return "other"
    p = path.lower()
    base = p.rsplit("/", 1)[-1]

    if base in {
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
        "pipfile.lock", "go.sum", "cargo.lock", "gemfile.lock", "composer.lock",
        "uv.lock", "bun.lockb", "requirements.txt",
    }:
        return "lockfile"

    if p.endswith((".md", ".rst", ".txt", ".adoc")) or "/docs/" in p or p.startswith("docs/"):
        return "docs"

    if (
        "/tests/" in p or "/test/" in p or "/__tests__/" in p
        or p.startswith(("tests/", "test/"))
        or p.endswith((
            ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
            ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx",
        ))
        or base.startswith("test_") or base.endswith("_test.py")
        or base.endswith("_test.go") or base.endswith("_spec.rb")
    ):
        return "test"

    if (
        p.startswith((
            ".github/", "ci/", "ops/", "infra/", "deploy/", "k8s/",
            "kubernetes/", "helm/", "terraform/", ".gitlab/", ".circleci/",
        ))
        or p.endswith((".tf", ".tfvars"))
        or base in {"dockerfile", ".dockerignore", ".gitlab-ci.yml", "makefile"}
        or "/dockerfile" in p
    ):
        return "infra"

    if (
        p.endswith(".sql")
        or "/dags/" in p or "/airflow/" in p
        or "/dbt/" in p or "/dbt_project" in p
        or "/models/" in p and (p.endswith((".sql", ".yml", ".yaml")))
        or "/seeds/" in p or "/macros/" in p or "/snapshots/" in p
        or "/looker/" in p or p.endswith((".lkml", ".lookml"))
    ):
        return "data_pipeline"

    if p.endswith((
        ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".swift",
        ".rb", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp",
        ".cs", ".php", ".clj", ".cljs", ".ex", ".exs", ".elm",
        ".lua", ".m", ".mm", ".dart", ".sol", ".vue", ".svelte",
    )):
        return "code"

    if p.endswith((".yml", ".yaml", ".json", ".toml", ".ini", ".env", ".cfg", ".conf")):
        return "config"

    return "other"


def _conventional_scope(message: str) -> str | None:
    m = re.match(r"^([a-zA-Z]+)\(([^)]+)\)\s*:", message.strip())
    if m:
        return m.group(2).strip().lower()
    return None


def _meaningful_tokens(message: str) -> set[str]:
    msg = message.strip()
    msg = re.sub(r"^[a-zA-Z]+(\([^)]*\))?\s*:\s*", "", msg)
    tokens: set[str] = set()
    for raw in re.split(r"[^a-zA-Z0-9_-]+", msg.lower()):
        if not raw:
            continue
        for piece in raw.split("-"):
            for sub in piece.split("_"):
                if len(sub) >= MIN_TOKEN_LENGTH and sub not in _STOPWORDS and not sub.isdigit():
                    tokens.add(sub)
    return tokens


def _top_dirs(paths: list[str], depth: int = 2) -> set[str]:
    out: set[str] = set()
    for p in paths:
        parts = [seg for seg in p.split("/") if seg]
        if len(parts) >= depth + 1:
            out.add("/".join(parts[:depth]))
        elif parts:
            out.add(parts[0])
    return out


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


_complexity_weighted_effort = _commit_effort
