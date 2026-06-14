# Werkschau

Audit an engineering org's GitHub activity over a window and produce a single HTML retrospective — nameplate, callouts, quadrant chart, manager rollups, per-contributor ledger, and per-manager breakdown pages. Designed to land in a VP's inbox as one self-contained file.

The score axes are **effort** (complexity-weighted commit minutes vs. a fixed reference) and **substance** (share of that effort that came from real changes, not from dependency bumps, merges, lockfile updates, docs touches, or one-line tweaks). The top-right quadrant is *locked in*; the bottom-left is *inactive*, and a hard rule populates the Inactive callout independent of where the dot lands.

## Two entry points

- **`/werkschau` slash command** — runs inside Claude Code, uses your local `gh` auth, no Anthropic API key needed. Walks you through building or loading an `org.json`, runs the extractor, writes per-person briefs from the in-conversation model, and renders the HTML.
- **`werkschau report-org` CLI** — standalone Python. Same pipeline but calls the Anthropic or an OpenAI-compatible API for the briefs. Runs anywhere, including cron / CI.

## Install

Inside Claude Code:

```
/plugin marketplace add KranzL/werkschau
/plugin install werkschau@werkschau
/werkschau
```

First `/werkschau` invocation provisions a local Python venv on its own. You only need `gh` authenticated (`gh auth login`).

## Quickstart

```
/werkschau
```

Walks through org bootstrap (if you don't have an `org.json` yet), pulls the window, writes the briefs, and saves `werkschau-YYYY-MM-DD.html` in the current directory plus a sidecar `.meta.json` for the index.

For repeat weekly runs:

```
/werkschau --since 7d
```

For a monthly archive:

```
/werkschau --backfill 6
```

Renders six complete calendar months plus an `index.html` linking them.

## Pipeline

```
events + search -> repo list -> commits -> per-commit features
  -> per-commit change_kind classification (addition / deletion /
     refactor / rename / tweak / noise)
  -> initiative clustering (48h + scope/token/dir heuristic)
  -> effort and substance scoring + Inactive flag
  -> per-person brief (LLM)
  -> HTML render
```

## What goes in the score

Per commit, Werkschau extracts: additions / deletions / file count / file paths / file `status` (added/modified/renamed) / test ratio / merge flag / revert flag / dependency-bump flag / docs-only flag / conventional-commit scope. From those it derives a **change_kind** (`addition`, `deletion`, `refactor`, `rename`, `tweak`, or `noise`) and a heuristic effort in minutes.

The user-level scores roll those up:

- **Effort** — log-ratio of complexity-weighted, file-kind-weighted minutes to a 600 min/week reference. Code, SQL/Airflow/dbt, tests, and infrastructure count at full weight; generic configuration at 60%; documentation at 20%; lockfile-only commits at 10%.
- **Substance** — share of effort that came from non-noise commits, mapped to [−1, +1].
- **Inactive** (boolean) — fires when the user has zero substantive commits, *or* fewer than 60 substantive minutes per week of window. Used to populate the Inactive callout independent of where the dot lands on the chart.

The Inactive callout excludes off-grid contributors (no GitHub handle) and directors, since directors aren't expected to commit much.

## CLI

```bash
werkschau extract --org ~/.werkschau/org.json --since 7d --output /tmp/wk.json
werkschau report-org \
  --org ~/.werkschau/org.json \
  --extract /tmp/wk.json \
  --narratives /tmp/narratives.json \
  --since 7d --output werkschau-$(date +%Y-%m-%d).html
```

For cron / CI without a pre-baked narrative:

```bash
WERKSCHAU_ANTHROPIC_API_KEY=<key> \
werkschau report-org --org ~/.werkschau/org.json --since 7d --output report.html
```

Or against an OpenAI-compatible endpoint:

```bash
WERKSCHAU_OPENAI_API_KEY=<key> \
werkschau report-org \
  --org ~/.werkschau/org.json --since 7d --output report.html \
  --provider openai \
  --base-url https://api.openai.com/v1 \
  --model gpt-5
```

The `pull` / `slice` / `backfill` commands maintain a window-agnostic local store at `~/.werkschau/store.json` so re-slicing into multiple windows doesn't re-hit GitHub. The `cache info` / `cache purge` commands maintain the per-commit diff cache at `~/.cache/werkschau/diffs/`.

## Extract JSON shape

The `users[]` array has one entry per contributor with `user`, `level`, `repos_visited`, `repo_count`, `commit_count`, `total_churn`, `total_heuristic_effort_minutes`, `commits[]`, and `inferred_initiatives[]`. Per commit: `sha`, `repo`, `committer_date_utc`, `hour_utc`, `weekday`, `message_first_line`, `additions`, `deletions`, `churn`, `files_changed`, `unique_top_dirs`, `file_paths_sample`, `file_status_counts`, `test_ratio`, `is_merge`, `is_revert`, `is_dependency_bump`, `is_docs_only`, `change_kind`, `is_substantive`, `heuristic_effort_minutes`, `co_authors`.

## Why "Werkschau"

German for "showing of one's work" — a portfolio review. Sibling to [Überblick](https://github.com/KranzL/uberblick) (Snowflake role topology) and [Einblick](https://github.com/KranzL/einblick) (query history audit). Same shape, different domain.

## What this is not

A performance-management input. The chart and callouts describe commit-visible work; code review, debugging, design, mentorship, and notebook / BI work are intentionally invisible here. Senior+ ICs and DS/DA roles especially carry leverage that doesn't surface in `git log`.

## License

MIT.
