---
name: werkschau-analysis
description: >
  Activate when the user asks to audit GitHub activity, summarize what
  someone or a team worked on, build a weekly retrospective from commits,
  estimate developer effort from commit history, compare a team's output
  against level expectations, or mentions werkschau.
version: 0.2.0
---

# Werkschau Analysis

Cluster one or more users' commits over a window into coherent initiatives, then write a per-person narrative retrospective with calibrated effort estimates. Supports comparing a team's output against level expectations.

## Pipeline

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau extract \
  --user <u1>:<level1> --user <u2>:<level2> ... \
  --since <window> \
  --output "/tmp/werkschau-$(id -u).json"
```

Or with a saved team:

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau extract --team <name> --since <window> --output "/tmp/werkschau-$(id -u).json"
```

Then read `/tmp/werkschau-$(id -u).json`. Resolve `$(id -u)` via `Bash` first and substitute the numeric value when calling `Read`.

## What the JSON contains

Top-level: `since`, `until`, `team`, `user_count`, `users[]`.

Per user in `users[]`: `user`, `level`, `repos_visited`, `repo_count`, `commit_count`, `total_churn`, `total_heuristic_effort_minutes`, `commits[]`.

Per commit in `commits[]`: `sha`, `url`, `repo`, `author_login`, `author_name`, `co_authors`, `committer_date_utc`, `hour_utc`, `weekday`, `message_first_line`, `message_length`, `additions`, `deletions`, `churn`, `files_changed`, `unique_top_dirs`, `file_paths_sample`, `test_ratio`, `is_merge`, `is_revert`, `is_dependency_bump`, `heuristic_effort_minutes`.

To inspect a full diff, `gh api /repos/{owner}/{repo}/commits/{sha}`. Do this for the 2-4 most substantive commits per initiative; do not deep-read every commit.

## Clustering into initiatives (per user)

Default grouping key: `repo`. Split a single repo's commits into multiple initiatives when work clearly diverges by subsystem or theme. Heuristics:

- Different top-level dirs touched and unrelated commit messages -> different initiatives
- A run of commits sharing a feature keyword in messages and overlapping file paths -> one initiative
- Dependabot / Renovate-style commits, single-file typo fixes, README touch-ups -> roll into a "Maintenance" bucket

Aim for between 2 and 8 initiatives per user.

## Level calibration

The heuristic effort numbers are inputs, not answers. Use these anchors to calibrate. Each level has both a typical commit-visible work range AND an "invisible" workload that does not surface in `git log`. **The relationship inverts at the top: senior+ engineers should have less commit-visible volume, not more, because their leverage shifts toward review, design, mentorship, and unblocking others.**

| Level | Typical commit-visible h/wk | What's invisible | Red flags |
|---|---|---|---|
| Junior | 10-15h | Onboarding, learning, paired work | <5h sustained may indicate blockers, not laziness |
| Mid | 15-25h | Some review, debugging, ad-hoc help | Sustained <10h may indicate scope confusion |
| Senior | 15-25h | Heavier review, design discussions, cross-team alignment | <10h *with low review activity* is the concern, not low commits alone |
| Staff | 8-18h | RFCs, mentorship, cross-team work, hiring, code review | High commit-volume (>30h) often means under-leveraging |
| Principal | 5-12h | Strategy, architecture, hiring, organizational work | Same as Staff -- high commit volume is a smell |

For a user with `level: null`, do not emit a level-relative tag in the comparative table. Just report what's visible.

The "h/wk" ranges assume a 5-day workweek. Scale linearly for windows shorter or longer than 7 days. For a 14-day window, double the ranges.

## Calibration adjustments beyond level

- A **single-file dependency bump** is 5-10 minutes regardless of LOC.
- A **clean refactor with tests** at 500 LOC churn is 2-4 hours, not the 8-10 the raw formula suggests.
- A **bug fix** that is 30 lines changed but spans 4 unrelated files is often 2-3 hours of debugging time (not visible in churn).
- **Merge commits** and **reverts** count for almost nothing on their own.
- A run of small commits in a single afternoon clustered in one subsystem usually represents one continuous focused session. Don't sum them naively.
- **Test-heavy commits** (`test_ratio > 0.4`) usually represent more deliberate engineering than the churn alone implies. Lean *up* on the estimate.
- **Weekend / late-night clusters** are signal but not necessarily of effort -- they often reflect side-project or hobby work, not work-week intensity. Note in the activity profile, do not double-count.

## Comparative report format (multi-user)

```markdown
# Werkschau -- <team-name-or-ad-hoc>
**Window:** <since> -> <until> (<N> days)
**Members:** <C> users

## Comparative summary

| User | Level | Commits | Repos | Est. effort | Vs. level |
|---|---|---|---|---|---|
| KranzL | Staff | 53 | 4 | ~22h | tracking *high* for Staff (commit-heavy week) |
| alice | Senior | 18 | 3 | ~17h | on pace for Senior |
| bob | Junior | 6 | 1 | ~8h | tracking *low* for Junior; check for blockers |

> "Vs. level" describes commit-visible output relative to that level's typical range -- not a performance judgment. Senior+ engineers' real output (review, mentorship, design) is intentionally invisible here.

## KranzL (Staff) -- ~22h, 53 commits, 4 repos

### 1. <Initiative name> -- ~Xh, Y commits
*<owner/repo>*

<1-3 sentences. Concrete, specific. Mention the actual subsystem and
the actual change. If you read the diff, name what specifically
changed -- not "auth changes" but "switched the auth middleware from
session cookies to JWT".>

Key commits:
- `<sha7>` <message_first_line>
- `<sha7>` <message_first_line>

### 2. ...

### Maintenance & noise -- ~Xh, Y commits
<one paragraph: lockfiles, READMEs, formatting>

### Activity profile
<short paragraph: most active weekday, time-of-day, weekend work, gaps, coauthors>

## alice (Senior) -- ~17h, 18 commits, 3 repos

(same shape as KranzL section)

## Cross-team observations

- <coauthorship pairs, e.g. "KranzL and alice co-authored 4 commits in services/api during the auth migration">
- <shared initiatives across users>
- <week-over-week trend if window >= 14d>

## Caveats

- Werkschau only counts commit-visible work. Code review, debugging without commits, design discussions, meetings, and pair programming where you weren't the committer are invisible here. This is especially load-bearing for Senior+ engineers.
- Effort estimates are calibrated guesses, not measurements. Treat per-initiative numbers as ranges, not point values.
- Discovery unions `/users/{user}/events` (recent, public-only for non-self users) with `/search/commits?author=...` (covers private repos the authenticated user can see). Search is subject to GitHub's indexing lag (commits within the last few minutes may not appear) and a 1000-result cap per query.
- "Vs. level" tags compare commit volume only. They are not performance assessments. Do not use this report as a primary input to performance management decisions.
```

## Single-user report format

If `users[]` has length 1, drop the comparative table and the "Cross-team observations" section. Use the Werkschau v0.1 single-user shape with the per-user sections becoming the body.

## What to never do

- **Never emit a thumbs-up/thumbs-down rating on a person.** "Tracking low for Senior" is descriptive (commit volume sits below the typical range for that level). "Underperforming" or "needs improvement" is a judgment, and Werkschau is not a performance-management tool. The comparative tag is *for context*, not *for evaluation*.
- Never invent commits or shas. If a commit isn't in the JSON, it didn't exist for this run.
- Never describe work in vague terms ("improved performance", "fixed bugs") -- if you can't be specific, fetch the diff.
- Never treat heuristic effort as a final number. Calibration is the whole point of this step.
- Never punish Staff/Principal engineers for low commit volume. Re-read the inversion table above before tagging Staff "tracking low" -- you almost always want "on pace" or "leverage-mode" for Staff with modest commit volume.
- Never include private repo contents in a "shareable" version of the report. Repo names alone are usually fine; commit messages and file paths can leak info.
- Never aggregate co-authored commits into both authors' totals naively. If commit X is authored by alice and co-authored by bob, count it as alice's primary and note in bob's section ("co-authored Y commits with alice").
