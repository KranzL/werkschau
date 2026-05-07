# Werkschau

Audit a developer's GitHub activity over a window and produce a narrative report of what they actually worked on, with effort estimates per initiative.

Think `git log` -> human-readable retrospective. Discovers every repo a user touched (including org repos they're not formally listed on), pulls their commits + diffs, and clusters the work into themes.

## Two entry points

- **`/werkschau` slash command** -- runs inside Claude Code, uses your local `gh` auth, no Anthropic API key needed. Claude analyzes the extracted features in-conversation and writes the report.
- **`werkschau analyze` CLI** *(planned)* -- standalone Python that calls the GitHub API and Anthropic API directly. Runs anywhere, including CI / cron.

## Pipeline

```
events + search -> repo list -> commits -> diff features
  -> heuristic prefilter -> theme clustering -> narrative report
```

Discovery uses `GET /users/{user}/events` for the last 90 days (covers public + the user's own private activity when authenticated as them) and falls back to `GET /search/commits?q=author:{user}` for older windows.

## Quickstart (slash command)

```
/werkschau KranzL --since 7d
```

First run installs a local venv under the plugin (~30 seconds). All GitHub access goes through `gh`, so whatever `gh auth` is logged in as decides what's visible.

## CLI (extractor only, today)

```bash
werkschau extract --user KranzL --since 7d --output /tmp/werkschau.json
```

Outputs one JSON record per commit with heuristic features (additions, deletions, files, churn, test ratio, time-of-day, day-of-week, message quality, is_merge, is_revert). The slash command pipes this into Claude for theme clustering and narrative generation.

## Why "Werkschau"

German for "showing of one's work" -- a portfolio review. Sibling to [Überblick](https://github.com/KranzL/uberblick) (Snowflake role topology) and [Einblick](https://github.com/KranzL/einblick) (query history audit). Same shape, different domain.

## License

MIT.
