---
description: Audit a developer's GitHub activity over a window and write a narrative retrospective with effort estimates
argument-hint: "<github-username> [--since 7d|30d|1y|ISO8601] [--include-merges]"
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
  - Write
---

# Werkschau: GitHub Activity Retrospective

Discover every repo a user touched in the window (including org repos they're not formally listed on), pull their commits + diff features, then cluster the work into themes and write a narrative report with effort estimates per initiative.

## Step 1: Verify setup

```bash
test -f "${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau" && echo "READY" || echo "SETUP_NEEDED"
```

If `SETUP_NEEDED`, run the installer yourself (do not ask the user to run pip/python -- just do it):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/install.sh"
```

It creates a local venv under the plugin and installs the package. Takes about 15 seconds.

Also confirm `gh` is authenticated:

```bash
gh auth status
```

If `gh` is not authenticated, stop and tell the user to run `gh auth login` before continuing. The slash command relies entirely on the user's `gh auth` for GitHub access -- there is no token plumbing.

## Step 2: Parse arguments

The first positional argument is the GitHub username. Optional flags:

- `--since` -- duration (`7d`, `14d`, `30d`, `1y`) or ISO8601 timestamp. Default `7d`.
- `--until` -- ISO8601 timestamp. Default `now`.
- `--include-merges` -- include merge commits (off by default; merges add noise to the narrative).

If no username was provided, ask once via the conversation: "Whose GitHub activity should I audit?" and accept the next message as the username.

## Step 3: Extract

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau extract \
  --user "<username>" \
  --since "<since>" \
  --output "/tmp/werkschau-$(id -u).json"
```

Add `--until` and `--include-merges` if the user supplied them. Stream the stderr to the user so they see discovery progress.

If the extractor reports `No PushEvent activity in window`, this almost always means one of:
- The window is older than ~90 days and the events feed has aged out.
- The username is wrong (case matters less for `gh api` but typos are common).
- The user is committing under a different GitHub login than you searched.

Surface that diagnosis and ask the user to clarify before retrying.

## Step 4: Load results

Read the JSON at `/tmp/werkschau-$(id -u).json`. Resolve `$(id -u)` first via `Bash` (`id -u`) and substitute the literal numeric value into the path you pass to `Read`.

The payload has:
- `user`, `since`, `until` -- the window
- `repos_visited` -- every `owner/repo` we pulled commits from
- `repo_count`, `commit_count`, `total_churn`, `total_heuristic_effort_minutes` -- top-line numbers
- `commits[]` -- one record per commit with sha, url, message_first_line, additions/deletions/churn, files_changed, file_paths_sample, test_ratio, is_merge, is_revert, is_dependency_bump, hour_utc, weekday, heuristic_effort_minutes, co_authors

Heuristic effort is a rough prefilter, NOT the final estimate. You will compute the real per-initiative estimates in Step 6.

## Step 5: Read the skill

Read `${CLAUDE_PLUGIN_ROOT}/skills/werkschau-analysis/SKILL.md` for the report format, clustering rules, and effort calibration guidance.

## Step 6: Cluster + estimate

Group commits into **initiatives** -- coherent threads of work that share a theme. The default grouping key is the repo, but split a single repo's commits into multiple initiatives when the work clearly diverges (e.g. one feature in `services/api`, an unrelated bugfix in `services/billing`, a chore in `.github/workflows`). Use commit messages and file paths to decide.

For each initiative:
1. Look at the commits in that group. Read 2-4 of the most substantive ones in full via `gh api /repos/{owner}/{repo}/commits/{sha}` -- you do NOT need to deep-read the dependency bumps or the trivial ones.
2. Write a 1-3 sentence narrative of what they actually did. Be specific (mention the actual subsystem, the actual change), not generic ("worked on backend stuff").
3. Estimate hours of effort. Calibration: a typical IC produces 15-30 hours of `werkschau`-visible work in a 5-day week (the rest is meetings, code review, debugging without commits, design, comms). Use the heuristics as inputs but trust judgment over arithmetic. A 500-line refactor with tests takes longer than a 500-line dependency bump even if churn is identical.
4. Sum the per-commit effort to a per-initiative total.

Initiatives that look like throwaway noise (a single dependency bump, a docs typo) can be collapsed into a "Maintenance" bucket at the end with a single line.

## Step 7: Generate report

Produce a markdown report following the format in the skill. Section order:

1. **Header** -- user, window, total estimated effort, total commits, repo count
2. **Initiatives** -- one section per initiative, ordered by estimated effort descending
3. **Maintenance & noise** -- collapsed bucket (optional)
4. **Activity profile** -- a short paragraph on cadence (most active day, time-of-day pattern, weekend work, coauthored commits)
5. **Caveats** -- explicit note that this only counts commit-visible work and effort estimates are calibrated guesses

Display the report to the user inline.

## Step 8: Save the report

Save the report to `werkschau_<username>_<YYYYMMDD>_<HHMMSS>.md` in the user's current working directory. Get the timestamp with `date +%Y%m%d_%H%M%S`. Confirm to the user with the saved filename.

## Step 9: Cleanup

```bash
rm -f "/tmp/werkschau-$(id -u).json"
```
