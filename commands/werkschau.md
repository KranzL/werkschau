---
description: Audit one or more developers' GitHub activity over a window and write a narrative retrospective with effort estimates per initiative
argument-hint: "[--team <name>] [--since 7d|30d|1y|ISO8601] [--include-merges]"
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
  - Write
  - AskUserQuestion
---

# Werkschau: GitHub Activity Retrospective

> Note: For cron / CI use, run `werkschau report` directly (needs an LLM API key). The slash command is for interactive use inside Claude Code.

Discover every repo each user touched in the window, pull their commits + diff features, then cluster the work into themes and write a per-person narrative with effort estimates calibrated to each person's level.

## Step 1: Verify setup

```bash
test -f "${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau" && echo "READY" || echo "SETUP_NEEDED"
```

If `SETUP_NEEDED`, run the installer yourself (do not ask the user to run pip/python -- just do it):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/install.sh"
```

Then confirm `gh` is authenticated:

```bash
gh auth status
```

If `gh` is not authenticated, stop and tell the user to run `gh auth login` before continuing.

## Step 2: Resolve the team

There are three ways the team is decided. Pick the first one that applies:

### 2a. Shortcut: `--team <name>` was passed

Skip Step 2 entirely and use the saved team:

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau team show <name>
```

If the team file does not exist, surface the error and continue to 2b.

### 2b. Interactive: collect the team

Use **AskUserQuestion** for the first decision:

**Question: "Who do you want to audit?"**
Header: "Scope"
Options:
- "Just me / one person" -- single user, prompt conversationally for the username
- "A team in a single GitHub org" -- list org members and pick from them
- "A team across multiple orgs / arbitrary list" -- collect usernames conversationally

**If "single GitHub org":**
1. Ask conversationally: "Which org?"
2. Enumerate members:
   ```bash
   gh api /orgs/<org>/members --paginate --jq '.[].login'
   ```
3. If the list is short (<= 25), use **AskUserQuestion** with multiSelect=true and one option per login:
   - Header: "Team"
   - Question: "Pick the team members"
   - Options: one per login from the gh output
4. If the list is long (>25), ask conversationally instead: "I see {N} members in {org}. Drop the GitHub usernames you want to audit, comma-separated or one per line."

**If "arbitrary list" or "single person":**
Ask conversationally: "Drop the GitHub usernames you want to audit, comma-separated or one per line." Accept the next message as the answer; trim whitespace, split on whitespace and commas, deduplicate.

### 2c. Collect levels

Once the team is collected (>= 1 username), ask for the level of each member. Use **a single AskUserQuestion call** with one question per teammate:

For each user, add a question:
- Header: `<username>` (truncated to 12 chars if longer; AskUserQuestion headers are short)
- Question: `"Level for <username>?"`
- Options:
  - "Junior" -- 0-3 yrs, mostly guided work
  - "Mid" -- 3-6 yrs, autonomous on features
  - "Senior" -- 6-10 yrs, owns areas, drives reviews
  - "Staff" -- cross-team, mostly RFCs / leverage / mentorship
  - "Principal" -- strategy / architecture, low commit volume by design
  - "Skip / unknown" -- no level calibration for this user

If the user picks "Skip / unknown", store level as `null` for that user.

### 2d. Offer to save

If 2 or more members were collected via interactive flow, **AskUserQuestion**:

**Question: "Save this team for future runs?"**
Header: "Save"
Options:
- "Yes, save as a named team"
- "No, run this once"

If yes, ask conversationally for a team name (alphanumeric + `-`/`_`), then save:

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau team save <name> \
  --user <user1>:<level1> \
  --user <user2>:<level2> ...
```

Tell the user how to reuse it: `/werkschau --team <name> --since <window>`.

## Step 3: Extract

Build one `--user USER:LEVEL` flag per member (or `--user USER` if level is null):

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau extract \
  --user "<u1>:<l1>" \
  --user "<u2>:<l2>" \
  --since "<since>" \
  --output "/tmp/werkschau-$(id -u).json"
```

If `--team <name>` was passed, use `--team <name>` instead of repeated `--user` flags.

Stream the stderr to the user so they see discovery progress.

If the extractor reports no authored commits for a user, surface that explicitly -- it usually means the username is wrong, that user commits under a different login, or your auth doesn't have visibility into the repos they pushed to (search/commits will only return private repos the authenticated user can see).

## Step 4: Load results

Read the JSON at `/tmp/werkschau-$(id -u).json`. Resolve `$(id -u)` first via `Bash`. The payload shape:

- `since`, `until` -- the window
- `team` -- the team name (or null if ad-hoc)
- `users[]` -- one entry per user, each with:
  - `user`, `level`
  - `repos_visited`, `repo_count`, `commit_count`
  - `total_churn`, `total_heuristic_effort_minutes`
  - `commits[]` -- per-commit features (see the skill for fields)

## Step 5: Read the skill

Read `${CLAUDE_PLUGIN_ROOT}/skills/werkschau-analysis/SKILL.md` for clustering rules, level calibration, comparative report format, and the perf-management guardrails.

## Step 6: Cluster + estimate per user

For each user in `users[]`:
1. Cluster their commits into 2-8 initiatives (default key = repo, split when work clearly diverges).
2. For each initiative, read 2-4 of the most substantive commits in full via `gh api /repos/{owner}/{repo}/commits/{sha}` to write specific narrative.
3. Estimate effort hours per initiative, calibrated to the user's level using the calibration table in the skill. Honor the inversion: at Staff/Principal, low commit volume is often expected and not a red flag.
4. Sum to a per-user total estimated effort.

Skip per-commit deep-reads for trivial commits (dependency bumps, lockfile-only, single-line typos) -- the heuristic features are sufficient.

## Step 7: Generate the combined report

Follow the multi-user format in the skill:

1. **Header** -- window, team name (if any), member count
2. **Comparative summary table** -- one row per user with level, commit count, estimated effort, and a "tracking high / on pace / tracking low *for level*" tag. **Never emit a thumbs-up/thumbs-down rating per person -- only describe what's visible and how it compares to that level's typical commit-visible output.**
3. **Per-user sections** -- one section per user with their initiatives ordered by effort descending, plus an "Activity profile" subsection (cadence, weekend work, time-of-day pattern)
4. **Cross-team observations** -- coauthorship pairs, shared initiatives if multiple users worked on the same repo, week-over-week trends if the window is long enough
5. **Caveats** -- the standard ones from v0.1, plus the level-calibration disclaimer

Display the report inline.

## Step 8: Save the report

Save to `werkschau_<team-or-first-user>_<YYYYMMDD>_<HHMMSS>.md` in the current working directory:

```bash
date +%Y%m%d_%H%M%S
```

Confirm to the user with the saved filename.

## Step 9: Cleanup

```bash
rm -f "/tmp/werkschau-$(id -u).json"
```
