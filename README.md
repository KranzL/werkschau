# Werkschau

Audit one or more developers' GitHub activity over a window and produce a narrative retrospective of what they actually worked on, with effort estimates per initiative -- calibrated to each person's level.

Discovers every repo a user touched (including private org repos and repos they're not formally listed on) by unioning `/users/{user}/events` with `/search/commits?author=...`, pulls their commits + diffs, clusters the work into themes, and writes a per-person retrospective with comparative output across the team.

## Two entry points

- **`/werkschau` slash command** -- runs inside Claude Code, uses your local `gh` auth, no Anthropic API key needed. Asks you who's on the team, gathers each person's level via `AskUserQuestion`, then Claude analyzes the extracted features in-conversation and writes the report. Saves teams for reuse.
- **`werkschau analyze` CLI** *(planned)* -- standalone Python that calls the GitHub API and Anthropic API directly. Runs anywhere, including CI / cron.

## Install

Inside Claude Code:

```
/plugin marketplace add KranzL/werkschau
/plugin install werkschau@werkschau
/werkschau
```

First `/werkschau` invocation sets up a local Python venv on its own. You only need `gh` authenticated (`gh auth login`).

## Quickstart

```
/werkschau
```

Walks you through the team setup, runs the extractor, and writes a comparative report.

For repeat runs of the same team:

```
/werkschau --team platform --since 7d
```

## Pipeline

```
events + search -> repo list -> commits -> diff features
  -> heuristic prefilter -> per-user theme clustering
  -> level-calibrated effort estimates -> comparative report
```

## Level calibration

Werkschau models each level's commit-visible output range *and* what's invisible at that level. Senior+ engineers shift leverage toward review, design, and mentorship -- so high commit volume at Staff is often a smell, not a strength. The skill's calibration table is the source of truth.

| Level | Typical commit-visible h/wk | What's invisible |
|---|---|---|
| Junior | 10-15h | Onboarding, learning |
| Mid | 15-25h | Some review, debugging |
| Senior | 15-25h | More review, design discussions |
| Staff | 8-18h | RFCs, mentorship, cross-team work |
| Principal | 5-12h | Strategy, architecture, hiring |

Werkschau emits a "tracking high / on pace / tracking low *for level*" tag per user. **It is not a performance-management tool** -- the tags describe commit-visible volume relative to that level's typical range, not whether the person is performing well. Real performance assessment requires the invisible work.

## CLI (extractor)

Single user:

```bash
werkschau extract --user KranzL:staff --since 7d --output /tmp/werkschau.json
```

Multiple users:

```bash
werkschau extract \
  --user KranzL:staff \
  --user alice:senior \
  --user bob:junior \
  --since 7d \
  --output /tmp/werkschau.json
```

Saved team:

```bash
werkschau team save platform --user KranzL:staff --user alice:senior --user bob:junior
werkschau extract --team platform --since 7d --output /tmp/werkschau.json
```

Output JSON has `users[]`, one entry per member, with per-commit heuristic features (additions, deletions, files, churn, test ratio, time-of-day, weekday, message quality, is_merge, is_revert, co-authors, heuristic effort). The slash command pipes this into Claude for theme clustering and narrative generation.

## Why "Werkschau"

German for "showing of one's work" -- a portfolio review. Sibling to [Überblick](https://github.com/KranzL/uberblick) (Snowflake role topology) and [Einblick](https://github.com/KranzL/einblick) (query history audit). Same shape, different domain.

## License

MIT.
