---
description: Generate the weekly engineering org snapshot HTML report from org.json. Uses your gh auth and Claude Code as the LLM (no API key needed).
argument-hint: "[--org <path>] [--since 7d|30d|ISO8601] [--issue N]"
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
  - Write
  - AskUserQuestion
---

# Werkschau: Weekly Engineering Org Snapshot

Generates the NYT-style HTML report (nameplate, callouts, quadrant chart, manager rollups, per-contributor ledger, per-manager Breakdown pages, methodology colophon) from an `org.json` defining the VP / directors / managers / employees and their levels + roles.

This slash command uses your `gh` auth for GitHub and Claude (this conversation) for narrative writing — no API key needed. For automated cron use, run `werkschau report-org` directly with an Anthropic or OpenAI-compatible key.

**Argument parsing.** Before doing anything else, parse `$ARGUMENTS` (the user's text after `/werkschau`) for these flags. Treat them as optional:

- `--org <path>` — explicit path to org.json
- `--since <window>` — e.g. `7d`, `14d`, `30d`, or ISO8601
- `--issue <N>` — issue number for the nameplate

Anything not passed will be asked or defaulted in the steps below.

## Step 1: Verify setup

```bash
test -f "${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau" && echo "READY" || echo "SETUP_NEEDED"
```

If `SETUP_NEEDED`, run the installer yourself (do not ask the user):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/install.sh"
```

Confirm `gh` is authenticated:

```bash
gh auth status
```

If `gh` is not authenticated, stop and tell the user to run `gh auth login`.

## Step 2: Resolve org.json

Pick the first that applies:

1. If `--org <path>` was passed and the file exists, use it.
2. Else if `~/.werkschau/org.json` exists, use it.
3. Else: **AskUserQuestion** with header "Org file" and question "No org.json found. How should we proceed?":
   - Option 1: "Build interactively from a GitHub org (recommended)"
   - Option 2: "Copy template to ~/.werkschau/org.json and edit manually"
   - Option 3: "Point to an existing org.json elsewhere"

   ### Option 1: Interactive bootstrap

   Use this sub-flow. **Conversational input** for lists of people (faster than per-person AskUserQuestion). **AskUserQuestion** only for the structural confirmations.

   **2.1.** Ask conversationally: *"What's the GitHub org handle? (e.g. `fanatics-gaming`)"*

   Verify it exists:
   ```bash
   gh api /orgs/<HANDLE>
   ```
   If 404, tell the user the org wasn't found and ask again. Otherwise continue.

   **2.2.** (Helpful but optional) Show member count for context:
   ```bash
   gh api /orgs/<HANDLE>/members --paginate --jq '. | length'
   ```
   "I see N members in `<HANDLE>`. We won't pull all of them — you'll specify the people you want in the report."

   **2.3.** Ask conversationally: *"What's the VP's GitHub handle and full name? Format: `handle:Full Name`. Example: `janevp:Jane Smith`"*

   Validate the handle:
   ```bash
   gh api /users/<HANDLE>
   ```

   **2.4. Format conventions for every people-list prompt below:**

   - `handle:Full Name` — person has a GitHub account. Validate with `gh api /users/<handle>`.
   - `:Full Name` or just `Full Name` (no colon) — person has no GitHub account. Skip handle validation and skip the level/role question for them. They'll appear in the org tree but not in the chart, ledger, or scoring.
   - `none` on its own line — there are no people in this category.

   For each parsed line that has a `handle`, validate via `gh api /users/<handle>`. If invalid, surface the error and ask the user to fix that one line.

   **2.5. Directors reporting to the VP.**

   Ask conversationally: *"List the directors reporting to `<VP>`. One per line in `handle:Full Name` format (or just `Full Name` if no GitHub). Type `none` if there are no directors."*

   For **each** parsed director **with a GitHub handle**, ask level and role via **AskUserQuestion** (one call with two questions). Use the **director-track level** options:

   - Question 1 — header `"Level"`, question `"Level for <Full Name> (<handle>)?"`. Options:
     - `"L7"` — desc: "Director (Principal-equivalent)"
     - `"L8"` — desc: "Senior Director (Senior Principal-equivalent)"
     - `"L7 IC"` — desc: "Principal IC track"
     - `"L9"` — desc: "Distinguished"
   - Question 2 — header `"Role"`, question `"Role for <Full Name> (<handle>)?"`. Options:
     - `"SWE"` — desc: "Software Engineer"
     - `"AE"` — desc: "Analytics Engineer"
     - `"MLE"` — desc: "ML Engineer"
     - `"DS"` — desc: "Data Scientist"

   For **each** parsed director **without a GitHub handle**, skip both questions — they don't get extracted.

   **2.6. ICs reporting directly to the VP (skip-level).**

   Ask conversationally: *"Are there any ICs reporting directly to `<VP>` (not through a director)? List them in `handle:Full Name` format, one per line. Type `none` if no skip-level reports."*

   For each, ask the level/role pair using the **IC-track level** options below.

   **2.7. For each director with a GitHub handle:**

   **2.7a. Direct ICs reporting to the director (skip-level under that director).**

   Ask conversationally: *"Are there any ICs reporting directly to `<director>` (no manager between them)? `handle:Full Name`, one per line. Type `none`."*

   For each, ask level/role with the **IC-track level** options.

   **2.7b. Managers reporting to the director.**

   Ask conversationally: *"Who reports to `<director>` as managers? `handle:Full Name`, one per line. Type `none`."*

   For **each** manager **with a GitHub handle**, ask level and role via AskUserQuestion. Use the **manager-track level** options:

   - Question 1 — header `"Level"`, question `"Level for <Full Name> (<handle>)?"`. Options:
     - `"L5"` — desc: "Manager (Staff-equivalent)"
     - `"L6"` — desc: "Senior Manager (Senior Staff-equivalent)"
     - `"L7"` — desc: "Director (Principal-equivalent)"
     - `"L8"` — desc: "Senior Director (Senior Principal-equivalent)"
   - Question 2 — header `"Role"`. Same role options as 2.5.

   **2.8. For each manager with a GitHub handle: their employees.**

   Ask conversationally: *"Who reports to `<manager>` as employees? `handle:Full Name`, one per line. Type `none`."*

   For **each** employee **with a GitHub handle**, ask level and role using the **IC-track level** options:

   - Question 1 — header `"Level"`, question `"Level for <Full Name> (<handle>)?"`. Options:
     - `"L2"` — desc: "Junior, autonomous on routine work"
     - `"L3"` — desc: "Pre-senior, autonomous on features"
     - `"L4"` — desc: "Senior, owns areas, drives reviews"
     - `"L5"` — desc: "Staff, cross-team leverage"
   - Question 2 — header `"Role"`. Same role options.

   The auto-added **Other** option (free text) captures anything outside the four explicit choices — L1 (intern), L6 (Senior Staff), L7 (Principal), L8 (Senior Principal), L9 (Distinguished), or any internal alias your org uses. For "Other" responses, normalize against the canonical L-numbers:

   - Canonical levels: `l1, l2, l3, l4, l5, l6, l7, l8, l9`
   - IC-track aliases: `junior` / `jr` / `mid` → `l2`; `senior` → `l4`; `staff` → `l5`; `senior staff` → `l6`; `principal` → `l7`; `senior principal` → `l8`; `distinguished` → `l9`.
   - Manager-track aliases: `manager` / `engineering manager` / `em` → `l5`; `senior manager` → `l6`; `director` → `l7`; `senior director` → `l8`; `vp` → `l9`.
   - Legacy aliases: `de1` / `de2` / `de3` → `l1` / `l2` / `l3`.
   - Roles: `swe, ae, mle, ds, da`

   If a typed value can't be normalized, re-ask just that field.

   **2.7.** Build the org JSON tree in memory matching the schema in `${CLAUDE_PLUGIN_ROOT}/org.example.json`.

   Print a compact tree preview to the user — for example:

   ```
   Jane Smith (vp · janevp)
   └─ Alice Smith (principal swe · alice-dir)
      ├─ Bob Manager (senior staff swe · bob-mgr)
      │  ├─ carol (DE3 swe)
      │  └─ dave (DE1 swe)
      └─ Erin Manager (staff mle · erin-mgr)
         └─ frank (senior mle)
   ```

   **2.8. AskUserQuestion** with header "Confirm" and question "Save this org structure?":
   - Option 1: "Yes, save to ~/.werkschau/org.json and run the report"
   - Option 2: "Save and stop (I want to verify the file before running)"
   - Option 3: "Edit and rebuild"

   If option 3, loop back to 2.4 with the existing tree as the starting point.

   If option 1 or 2: write the JSON to `~/.werkschau/org.json` via the `Write` tool. If option 1, continue to Step 3. If option 2, tell the user to run `/werkschau` again when ready. **Stop here.**

   ### Option 2: Copy template

   ```bash
   mkdir -p ~/.werkschau && cp "${CLAUDE_PLUGIN_ROOT}/org.example.json" ~/.werkschau/org.json
   ```
   Tell the user to edit `~/.werkschau/org.json` with real handles + levels + roles, then re-run `/werkschau`. **Stop here.**

   ### Option 3: Point to existing

   Ask conversationally for the path. Validate it exists. Use that path for `<ORG_PATH>` and continue to Step 3.

Confirm the resolved path before continuing:

```bash
test -f <ORG_PATH> && echo "OK" || echo "MISSING"
```

## Step 3: Resolve window

If `--since <window>` was passed, use it.

Else **AskUserQuestion** with header "Window" and question "What time window should this report cover?":

- Option 1: "Past 7 days (recommended weekly cadence)"
- Option 2: "Past 14 days"
- Option 3: "Past 30 days"

Map the answer to `7d`, `14d`, `30d`, or whatever the user types in "Other". Store as `<SINCE>`.

## Step 4: Resolve issue number

The issue number appears in the masthead ("Vol. I · No. N").

1. If `--issue <N>` was passed, use it.
2. Else, count existing reports in cwd to auto-detect:
   ```bash
   ls werkschau-*.html 2>/dev/null | wc -l
   ```
   If the count is 0, default `<ISSUE>=1` silently.
3. If the count is `>=1`, **AskUserQuestion** with header "Issue No." and question "What issue number is this?":
   - Option 1: "<auto-suggested N+1> (next in sequence)"
   - Option 2: "Same as last (overwrite)"
   - Option 3: "Custom"

   Default to the auto-suggested value if the user picks option 1.

## Step 5: Extract

Resolve a tmp prefix tied to the user's id, then run extract for every non-VP person in the org in one shot:

```bash
TMPID=$(id -u)
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau extract \
  --org <ORG_PATH> \
  --since "<SINCE>" \
  --output "/tmp/werkschau-extract-${TMPID}.json"
```

Stream stderr so the user sees discovery progress per person.

If a person reports "no authored commits found in window," note it but continue — the report still includes them with a "No commit-visible activity this week." narrative.

## Step 6: Load extract + org

Read both JSON files via `Read`:

- `/tmp/werkschau-extract-${TMPID}.json` — the extract payload, with `users[]`
- `<ORG_PATH>` — the org tree

For each person, you'll need: github handle, level, role, manager, director.

## Step 7: Sample diffs per user

For each user with `commit_count > 0`, identify the top 3 most substantive commits (highest `heuristic_effort_minutes`, prefer those with `unique_top_dirs >= 3` or `files_changed >= 5`). Skip dependency-bumps and merges.

For each selected commit, fetch the full diff:

```bash
gh api "/repos/<owner>/<repo>/commits/<sha>" --jq '{
  sha: .sha,
  message: .commit.message,
  files: [.files[] | {filename, status, additions, deletions, patch: (.patch // "" | .[:1500])}]
}'
```

Cap each commit's `patch` at ~1500 chars. Keep up to 8 files per commit.

Skip diff-fetching entirely for users with `commit_count == 0`.

## Step 8: Write per-person briefs

For each scored person (every non-VP — directors, managers, ICs, all of them), write a 2 to 5 sentence narrative paragraph grounded in their commits + sampled diffs.

**Format rules (strict):**

- Be specific. Name what they built or changed, not how they felt about it.
  *"Added a search/commits fallback so discovery works in all-private orgs"* is right.
  *"Improved discovery"* is wrong.
- Cite actual subsystem, file path, function name, or commit-message phrase when the diff supports it. If the data doesn't support specificity, hedge ("touched the X module") rather than invent.
- Note temporal patterns only when load-bearing (a Friday-night burst, weekend release, single-afternoon focused session). Don't list every weekday.
- For Senior+ ICs, managers, directors: if commit volume is low, note that this is expected and most of their week likely lives outside commits (review, design, mentorship). Do not read low volume as a red flag.
- For Data Scientists, ML Engineers, Data Analysts: low commit volume is normal — much of their week is in notebooks, BI tools, or dashboards that don't commit.
- If `commit_count == 0`: write `"No commit-visible activity this week."` plus one short sentence noting that's normal for their role/level.
- Never emit a thumbs-up/thumbs-down. No "great work" / "needs improvement". Describe what the commits show; the reader decides.
- Never invent commit content the diffs don't support.
- Output is plain prose — no bullets, no markdown, no headers, no code fences.

Build a JSON object mapping handle → narrative paragraph and write it to `/tmp/werkschau-narratives-${TMPID}.json`:

```json
{
  "alice": "Lead engineer on...",
  "carol": "Continued the platform/api authorization-layer work...",
  "...": "..."
}
```

Use `Write` to save it.

## Step 9: Render

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau report-org \
  --org <ORG_PATH> \
  --extract "/tmp/werkschau-extract-${TMPID}.json" \
  --narratives "/tmp/werkschau-narratives-${TMPID}.json" \
  --since "<SINCE>" \
  --issue <ISSUE> \
  --output "werkschau-$(date +%Y-%m-%d).html"
```

The `--narratives` flag tells `report-org` to use the pre-baked paragraphs and skip the LLM API call. No key needed.

## Step 10: Confirm and cleanup

Tell the user the saved filename. Show a one-line summary: how many contributors, how many in "locked in" / "not locked in", median output of the org.

Cleanup:

```bash
rm -f "/tmp/werkschau-extract-${TMPID}.json" "/tmp/werkschau-narratives-${TMPID}.json"
```

Tell the user they can attach the HTML directly to their VP's email.

## Notes for automated runs

For cron / CI / scheduled runs, skip this slash command and run `werkschau report-org` directly with an LLM API key:

```bash
WERKSCHAU_OPENAI_API_KEY=<key> \
werkschau report-org \
  --org ~/.werkschau/org.json \
  --since 7d \
  --output report-$(date +%Y-%m-%d).html \
  --provider openai \
  --base-url https://api.venice.ai/api/v1 \
  --model qwen3-coder-480b-a35b-instruct-turbo
```

Or with Anthropic:

```bash
WERKSCHAU_ANTHROPIC_API_KEY=<key> \
werkschau report-org --org ~/.werkschau/org.json --since 7d --output report.html
```
