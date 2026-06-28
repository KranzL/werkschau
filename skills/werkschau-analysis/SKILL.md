---
name: werkschau-analysis
description: >
  Activate when the user asks to audit an engineering org's GitHub activity,
  write per-person retrospective briefs from commit history, or build the
  weekly Werkschau HTML org snapshot. The org tree comes from an org.json
  (VP / directors / managers / employees). The output is per-person bullets
  grounded in commits + sampled diffs.
version: 0.4.0
---

# Werkschau Analysis

You are writing per-person briefs that feed the Werkschau HTML org snapshot. Each brief becomes one card in "The Breakdown" section. The chart and callouts are computed deterministically in Python from per-commit features; your job is to read the commits + sampled diffs for one person and write the narrative that goes on their card.

## What the extract JSON contains

Top-level: `since`, `until`, `user_count`, `users[]`.

Per user: `user`, `level`, `repos_visited`, `repo_count`, `commit_count`, `total_churn`, `total_heuristic_effort_minutes`, `commits[]`, `inferred_initiatives[]`, `calendar` (optional — absent when calendar fetch was skipped or on the CLI path).

`calendar` subfields (all aggregate numeric totals; no event titles, attendee names, or emails):
- `meeting_minutes` — total scheduled-event duration; excludes focus and OOO blocks
- `meeting_count` — total number of events counted in meeting_minutes
- `focus_minutes` — total duration of focus/deep-work blocks
- `ooo_minutes` — total duration of OOO/out-of-office blocks
- `recurring_count` — events part of a recurring series; `recurring_count + adhoc_count == meeting_count`
- `adhoc_count` — non-recurring (ad-hoc) events; `recurring_count + adhoc_count == meeting_count`
- `one_on_one_count` — events with exactly 2 attendees including organizer; `one_on_one_count + group_count == meeting_count`
- `group_count` — events with 3 or more attendees; `one_on_one_count + group_count == meeting_count`
- `window_days` — the report window length in days

When `meeting_minutes >= 480 * (max(1, window_days) / 7.0)` (MEETING_HEAVY_MINUTES_PER_WEEK = 480 min/week = 8 hours, prorated), `meeting_heavy` is True and the person is suppressed from the Inactive callout while still plotting bottom-left on the chart.

Per commit in `commits[]`: `sha`, `repo`, `committer_date_utc`, `hour_utc`, `weekday`, `message_first_line`, `additions`, `deletions`, `churn`, `files_changed`, `unique_top_dirs`, `file_paths_sample`, `file_status_counts`, `test_ratio`, `is_merge`, `is_revert`, `is_dependency_bump`, `is_docs_only`, `change_kind` (one of `addition / deletion / refactor / rename / tweak / noise`), `is_substantive`, `heuristic_effort_minutes`, `co_authors`.

Per initiative in `inferred_initiatives[]`: `name`, `weighted_minutes`, `commit_count`, `repos`, `sample_messages`, `sample_shas`. These come from Python's clustering pass (48h time window + shared scope, message token, or top-level directory). Use the top 1–3 by `weighted_minutes` as your bullet candidates unless the diffs make a better name obvious.

To pull a full diff for a specific commit:

```bash
gh api /repos/<owner>/<repo>/commits/<sha>
```

Do this for the 2–4 most substantive commits per initiative; do not deep-read every commit.

## How to read a person's week

1. Glance at `inferred_initiatives[]` — those are the candidate bullets.
2. Look at `change_kind` distribution. A week that's mostly `noise` (dep bumps, merges, docs touches, single-line tweaks) is genuinely a low-substance week — don't dress it up.
3. For each initiative you'll write a bullet about, read the diffs of the top commits in it. Name specific files, functions, schemas, or behaviors that changed.

## Brief format (strict)

```
<summary line: 1-2 sentences capturing the shape of the week>

- **<Initiative or subsystem name>**: <2-3 sentences: what the subsystem is briefly, which files / functions / schemas / configs changed and how, concrete impact if visible from the diffs>
- **<Initiative or subsystem name>**: <2-3 sentences, same depth>
```

Up to **four** bullets. Most weeks have 2–3. Target ~80–150 words for an active week.

**Specificity rules:**

- *"Swapped the per-row linear scan in `match_user` for a `set` membership check, cutting the hot-path from O(n) to O(1)"* is right.
- *"Improved performance"* is wrong.
- If the diff snippets don't support that level of specificity, hedge (*"touched the auth middleware in ways the available diff snippets don't fully reveal"*) rather than invent.
- Roll dependabot bumps, README touch-ups, lockfile-only commits, and version pins into a single `**Maintenance**` bullet, kept to one sentence.

**Low-output framing:**

- For SWE / MLE / AE / Manager, be direct: *"Did very little this week — one small commit to X."* / *"Light week. The single commit touched only the test fixture."* / *"Not enough commit-visible activity to evaluate."* No softening. No "probably blocked", no "leverage likely lives outside commits", no invented excuses.
- DS / DA roles get one exception — their work genuinely lives in notebooks, BI tools, and dashboards that don't commit. You may append one short clause acknowledging that.
- Directors get a pass — they aren't expected to commit much. For a director with low or zero output, describe what little they did (or write `"No commit-visible activity this week."`) without judgment in either direction.

**Zero-commit cases:**

- SWE / MLE / AE / Manager / Director: write exactly `"No commit-visible activity this week."` Nothing else.
- DS / DA: that line plus one short clause about notebook / BI / dashboard work.

**Use the person's `description` (their "owns" string) as ground truth** for what subsystems they're responsible for. Use it to disambiguate which subsystem a commit touches. Don't restate it verbatim — go deeper.

**Tone:**

- No thumbs-up praise on the high end ("great work").
- Direct factual framing is allowed for low output.
- No headers, no code fences around the brief, no preamble, no closing recap.

## Example brief (Alice, L4 SWE, owns auth subsystem)

```
Three concurrent threads this week, anchored on a token-rotation rewrite that retired a fragile cron job.

- **Token rotation**: the auth subsystem stores refresh tokens in Redis with a 30-day TTL. This week Alice replaced the every-15-minutes cron that swept expired tokens with event-driven invalidation: `src/auth/tokens.py` now publishes a `token.expired` message on Redis pub/sub, and a worker in `src/auth/cleanup.py` listens and deletes. Two integration tests (`tests/auth/test_rotation.py`) cover the new flow. The cron job is removed in the same PR; downstream services keep working without changes.
- **Search**: scoped the new Postgres FTS index for the catalog service. The schema migration in `migrations/0042_fts.sql` adds a `tsvector` column with a GIN index; query path in `src/search/handler.py` not yet rewritten — expected next week.
- **Maintenance**: lockfile bumps and a CI matrix update for Python 3.12.
```

## What not to do

- **Never invent commits or shas.** If a commit isn't in the JSON, it didn't exist for this run.
- **Never describe work in vague terms** (*"improved performance"*, *"fixed bugs"*) — if you can't be specific from the available signal, hedge or omit.
- **Never aggregate co-authored commits into both authors' totals naively.** If commit X is authored by alice and co-authored by bob, write it as alice's primary; mention in bob's brief that he co-authored on alice's initiative.
- **Never include private repo contents in a "shareable" version.** Repo names alone are usually fine; commit messages and file paths can leak info.
- **Werkschau is not a performance-management tool.** Don't write thumbs-up / thumbs-down assessments. Describe what shipped.
