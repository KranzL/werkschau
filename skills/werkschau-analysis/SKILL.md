---
name: werkschau-analysis
description: >
  Activate when the user asks to audit GitHub activity, summarize what
  someone worked on, build a weekly retrospective from commits, estimate
  developer effort from commit history, or mentions werkschau.
version: 0.1.0
---

# Werkschau Analysis

Cluster a user's commits over a window into coherent initiatives, then write a narrative retrospective with calibrated effort estimates.

## Pipeline

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau extract --user <username> --since <window> --output "/tmp/werkschau-$(id -u).json"
```

Then read `/tmp/werkschau-$(id -u).json`. Resolve `$(id -u)` via `Bash` first and substitute the numeric value when calling `Read`. The uid suffix avoids cross-user collisions on shared boxes.

## What you receive per commit

Heuristic features only, not the full diff. To inspect a diff, call `gh api /repos/{owner}/{repo}/commits/{sha}` for that commit. Do this for the 2-4 most substantive commits per initiative; do not deep-read every commit -- it's wasteful and the heuristics already filter noise.

Useful signals at a glance:
- `churn` (`additions + deletions`) -- crude size proxy
- `files_changed`, `unique_top_dirs` -- breadth proxy
- `test_ratio` -- fraction of touched files matching test patterns; high ratios suggest deliberate, validated work
- `is_dependency_bump`, `is_merge`, `is_revert` -- noise filters
- `message_first_line` -- the conventional summary line
- `file_paths_sample` -- first 25 file paths, enough to infer subsystem
- `weekday`, `hour_utc` -- cadence signals

## Clustering into initiatives

Default grouping key: `repo`. Split a single repo's commits into multiple initiatives when the work clearly diverges by subsystem or theme. Heuristics:

- Different top-level dirs touched and unrelated commit messages -> different initiatives
- A run of commits sharing a feature keyword in messages and overlapping file paths -> one initiative
- Dependabot / renovate-style commits, single-file typo fixes, README touch-ups -> roll into a "Maintenance" bucket

Aim for between 2 and 8 initiatives in the final report. Fewer feels lossy; more loses the narrative.

## Effort calibration

The heuristic effort numbers are inputs, not answers. They over-count dependency bumps and under-count subtle but high-stakes changes. Calibrate using these anchors:

- A typical IC produces **15-30 hours of werkschau-visible work** in a 5-day week. The rest goes to meetings, design, code review, debugging without commits, communication. If your numbers sum to 60 hours for a single week, scale down -- you are double-counting churn.
- A **single-file dependency bump** is 5-10 minutes regardless of LOC.
- A **clean refactor with tests** at 500 LOC churn is 2-4 hours, not the 8-10 the raw formula suggests.
- A **bug fix** that is 30 lines changed but spans 4 unrelated files is often 2-3 hours of debugging time (not visible in churn).
- **Merge commits** and **reverts** count for almost nothing on their own; the work is in the commits they reference.
- A run of small commits in a single afternoon clustered in one subsystem usually represents one continuous focused session. Don't sum them naively -- the cognitive overhead of context switching is what makes parallel work expensive, not concurrent work.

## Report format

```markdown
# Werkschau -- <username>
**Window:** <since> -> <until>
**Estimated effort:** ~<H> hours across <N> initiatives
**Commits:** <C> across <R> repos

## Initiatives

### 1. <Initiative name> -- ~<H>h, <C> commits
*<owner/repo> (or multiple repos if the work spans them)*

<1-3 sentences. What they actually built or fixed, in concrete terms.
Mention the subsystem by name. If you read the diff, mention what
specifically changed -- "switched the auth middleware from session
cookies to JWT" beats "auth changes". If there's a meaningful
before/after, note it.>

Key commits:
- `<sha7>` <message_first_line>
- `<sha7>` <message_first_line>

### 2. <Initiative name> -- ~<H>h, <C> commits
...

## Maintenance & noise -- ~<H>h, <C> commits
<one paragraph or bullet list of bumped lockfiles, README fixes,
formatting changes, etc>

## Activity profile

<one short paragraph: most active weekday, typical time-of-day,
weekend work, longest gap, co-authored commits if relevant>

## Caveats

- This report only counts work that produced commits. Code review, debugging without commits, design discussions, and meetings are invisible here.
- Effort estimates are calibrated guesses, not measurements. Treat the per-initiative numbers as ranges, not point values.
- Discovery is bounded by GitHub's `/users/{user}/events` feed (~90 days, ~300 events). Heavily active users may have older or higher-volume work that did not surface.
```

## What to never do

- Never invent commits or shas. If a commit isn't in the JSON, it did not exist for this run.
- Never describe work in vague terms ("improved performance", "fixed bugs") -- if you can't be specific, fetch the diff.
- Never treat heuristic effort as a final number. The whole point of the LLM step is calibration.
- Never include private repo contents in the report if the user asks for a "shareable" version. Repo names alone are usually fine; commit messages and file paths can leak info.
