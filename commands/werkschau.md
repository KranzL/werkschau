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

   **2.7. For each director with a GitHub handle, recursively gather their subtree.**

   The schema supports arbitrary depth (Senior Director → Director → Manager → IC, or deeper). At each director node, ask about *all three* possible kinds of report:

   **2.7a. Direct ICs reporting to this director (skip-level under that director).**

   Ask conversationally: *"Are there any ICs reporting directly to `<director>` (no manager between them)? `handle:Full Name`, one per line. Type `none`."*

   For each, ask level/role with the **IC-track level** options.

   **2.7b. Sub-directors reporting to this director.**

   Ask conversationally: *"Are there any directors reporting to `<director>` (e.g. they're a Senior Director with directors below them)? `handle:Full Name`, one per line. Type `none`."*

   For each parsed sub-director with a GitHub handle, ask the level/role pair using the **director-track level** options from 2.5. Then **recurse** back into step 2.7 with this sub-director as the new "director" — gather their direct ICs, their sub-directors, and their managers.

   The recursion ends when a director node has no further `directors` of their own, only `managers` and direct-IC `employees`.

   **2.7c. Managers reporting to this director.**

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

   **2.9. Optional: collect per-person ownership descriptions.**

   Once every person has a level + role, ask the user once (conversationally — no AskUserQuestion):

   *"Optional but very helpful for the Breakdown narratives: give a one-sentence description of what each person owns or focuses on. Format: `handle: short description`, one per line. Skip anyone you want to leave blank. Type `none` or just hit enter to skip this entirely."*

   For non-GitHub people, accept `Full Name: description` as well. Match against the names already collected.

   These descriptions are passed to the brief writer as ground truth so it can disambiguate which subsystem a commit touches. Store them in the JSON under each person's `"description"` field.

   **2.10.** Build the org JSON tree in memory matching the schema in `${CLAUDE_PLUGIN_ROOT}/org.example.json`. The schema supports nested directors — an entry under `directors[]` may have its own `directors[]`, `managers[]`, and `employees[]` arrays.

   Print a compact tree preview to the user — for example:

   ```
   Jane Smith (vp · janevp)
   └─ Sam Senior Director (l8 swe · sam-srdir) — owns Data Platform org
      └─ Jane Director (l7 swe · jane-dir) — owns ingestion + warehouse track
         ├─ Director-Direct IC (l5 swe · dir-direct-ic)
         ├─ Alice Smith (l6 swe · alice-mgr) — manages API platform team
         │  ├─ Alice Doe (l4 swe · alice) — owns auth subsystem
         │  └─ Carol Lee (l3 swe · carol) — owns search service
         └─ Erin Manager (l5 swe · erin-mgr)
            └─ frank (l4 mle)
   ```

   **2.11. AskUserQuestion** with header "Confirm" and question "Save this org structure?":
   - Option 1: "Yes, save to ~/.werkschau/org.json and run the report"
   - Option 2: "Save and stop (I want to verify the file before running)"
   - Option 3: "Edit and rebuild"

   If option 3, loop back to 2.5 with the existing tree as the starting point.

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

## Step 5: Extract (with cache)

Werkschau caches extracts and narratives at `~/.werkschau/extracts/`, keyed by date window, so re-running for the same week doesn't re-pull from GitHub. Resolve the cache paths:

```bash
mkdir -p ~/.werkschau/extracts
# Compute the window's start date in YYYY-MM-DD form. For durations like 7d/14d/30d:
SINCE_DATE=$(date -v-${SINCE_DAYS}d +%Y-%m-%d 2>/dev/null || date -d "${SINCE_DAYS} days ago" +%Y-%m-%d)
UNTIL_DATE=$(date +%Y-%m-%d)
EXTRACT_PATH="$HOME/.werkschau/extracts/extract-${SINCE_DATE}-to-${UNTIL_DATE}.json"
NARRATIVES_PATH="$HOME/.werkschau/extracts/narratives-${SINCE_DATE}-to-${UNTIL_DATE}.json"
```

(For ISO `<SINCE>` values, use the date portion directly.)

**Check the cache:**

```bash
test -f "$EXTRACT_PATH" && echo CACHED || echo NEW
```

If `CACHED`, **AskUserQuestion** with header "Cache" and question "An extract for this window already exists at `~/.werkschau/extracts/`. Reuse it?":
- Option 1: "Reuse cached extract (instant, no GitHub calls)"
- Option 2: "Re-pull fresh from GitHub (overwrites cache, costs API quota)"

If the user picks Option 1, skip the extract command below and proceed to Step 6.

If `NEW` or the user picked Option 2, run the extract:

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau extract \
  --org <ORG_PATH> \
  --since "<SINCE>" \
  --output "$EXTRACT_PATH"
```

Stream stderr so the user sees discovery progress per person. If a person reports "no authored commits found in window," note it but continue — the report still includes them with a "No commit-visible activity this week." narrative.

## Step 6: Load extract + org

Read both JSON files via `Read`:

- `$EXTRACT_PATH` — the extract payload, with `users[]`
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

## Step 7b: Cluster each user's commits into initiatives

Before writing briefs, mentally group each user's commits into 1-4 **initiatives**. The bullet structure of each brief should mirror those clusters.

Use this heuristic: **two commits belong to the same initiative when they happen within 48 hours of each other AND share at least one of**:

1. A conventional-commit scope (`feat(alfredo):` matches `fix(alfredo):` — same scope `alfredo`).
2. A meaningful message token (length ≥4, lowercase, ignoring boilerplate like `feat`, `fix`, `chore`, `update`, `bump`, `change`, `cleanup`, `wip`, etc.).
3. A shared top-2-level directory in the file paths (`src/alfredo/...` matches `src/alfredo/config.py` even across repos).

A coherent change that spans multiple repos (e.g. main code in `src/`, k8s YAML in `deploy/`, terraform in `infra/`, docs in `docs/`) is **one initiative**, not four. The chart's focus axis treats it as +1 focus, and your bullets should match.

A run of small unrelated commits with no shared signal is multiple singleton initiatives. Don't try to invent a unifying narrative — write one bullet per real cluster, plus a `**Maintenance**` bullet for noise if there's a lot of it.

Trust the diffs over the heuristic when the diffs make a more specific cluster name obvious.

## Step 8: Write per-person briefs

For each scored person (every non-VP — directors, managers, ICs, all of them), write a substantive brief grounded in their commits + sampled diffs and the person's `description` from `org.json`. **Target ~80-150 words for an active week.** Bullets are the substance — give the reader a real understanding of what shipped, not just a label.

**The output format is rigid markdown:**

```
<summary line: 1-2 sentences capturing the shape of the week>

- **<Initiative or subsystem name>**: <2-3 sentences: what the subsystem is, what specifically changed, concrete impact if visible from the diffs>
- **<Initiative or subsystem name>**: <2-3 sentences, same depth>
```

Up to **four** bullets. Most weeks have 2–3.

**Format rules (strict):**

- Each bullet is 2-3 sentences. Read the diff snippets and describe: (1) what the subsystem is briefly if the reader might not know, (2) which files, functions, classes, schemas, or configs got touched and how, (3) the concrete impact if visible — a perf win, a new capability, a bug squashed, an external surface added. Cite specific file paths, function names, or commit-message phrases.
- *"Swapped the per-row linear scan in `match_user` for a `set` membership check, cutting the hot-path from O(n) to O(1)"* is right. *"Improved performance"* is wrong.
- If the diff snippets don't support that level of specificity, hedge ("touched the auth middleware in ways the available diff snippets don't fully reveal") rather than invent.
- **Use the person's `description` field as ground truth** for what they own — but go deeper than the description does. Don't restate it verbatim.
- Roll dependabot bumps, README touch-ups, lockfile-only commits, and version pins into a single `**Maintenance**` bullet, kept to one sentence.
- **Be direct about low output.** If a SWE / MLE / AE shipped very little, just say so: *"Did very little this week — one small commit to X."* / *"Light week. The single commit touched only the test fixture."* / *"Not enough commit-visible activity to evaluate."* No "probably blocked", no "leverage likely lives outside commits", no "review and mentorship", no invented excuses.
- **Data Scientists (DS) and Data Analysts (DA) get the exception** — their work genuinely lives in notebooks, BI tools, and dashboards that don't commit. For DS/DA only, you may append one short clause acknowledging that.
- **Directors get a pass.** They aren't expected to commit much. For a director with low or zero commit-visible output, just describe what little they did (or write `"No commit-visible activity this week."`) without judgment in either direction. Don't flag directors as below pace.
- If `commit_count == 0`:
   - **For SWE / MLE / AE / Manager**: write exactly `"No commit-visible activity this week."` Nothing else.
   - **For Director**: write exactly `"No commit-visible activity this week."`
   - **For DS / DA**: write `"No commit-visible activity this week."` plus one short clause about notebook / BI / dashboard work.
- If `commit_count` is low but nonzero: describe what shipped specifically. For SWE / MLE / AE / Manager, a direct one-sentence framing like *"Did very little this week"* or *"Light week"* is fine alongside the description. Don't speculate about why.
- Don't emit thumbs-up praise on the high end (no *"great work"*). On the low end, direct factual framing is allowed.
- Never invent commit content the diffs don't support.
- No headers. No code fences. No preamble. No closing recap after the bullets.

**Example brief** (Alice, L4 SWE, owns auth subsystem):

```
Three concurrent threads this week, anchored on a token-rotation rewrite that retired a fragile cron job.

- **Token rotation**: the auth subsystem stores refresh tokens in Redis with a 30-day TTL. This week Alice replaced the every-15-minutes cron that swept expired tokens with event-driven invalidation: `src/auth/tokens.py` now publishes a `token.expired` message on Redis pub/sub, and a worker in `src/auth/cleanup.py` listens and deletes. Two integration tests (`tests/auth/test_rotation.py`) cover the new flow. The cron job is removed in the same PR; downstream services keep working without changes.
- **Search**: scoped the new Postgres FTS index for the catalog service. The schema migration in `migrations/0042_fts.sql` adds a `tsvector` column with a GIN index; query path in `src/search/handler.py` not yet rewritten — expected next week.
- **Maintenance**: lockfile bumps and a CI matrix update for Python 3.12.
```

**Narrative cache.** If `$NARRATIVES_PATH` already exists, AskUserQuestion: "Reuse cached narratives or re-write from scratch?". Reuse is instant; rewriting takes time but lets you incorporate edits to the brief format or new diff signal.

Build a JSON object mapping handle → markdown brief and write it to `$NARRATIVES_PATH`:

```json
{
  "alice": "Three threads of auth work...\n\n- **Token rotation**: ...\n- **Search**: ...",
  "carol": "Search-service hardening week.\n\n- **Query builder**: ...",
  "eve": "No commit-visible activity this week. L2 onboarding ICs typically pair-program rather than commit solo."
}
```

Use `Write` to save it.

## Step 9: Render

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/werkschau report-org \
  --org <ORG_PATH> \
  --extract "$EXTRACT_PATH" \
  --narratives "$NARRATIVES_PATH" \
  --since "<SINCE>" \
  --issue <ISSUE> \
  --output "werkschau-$(date +%Y-%m-%d).html"
```

The `--narratives` flag tells `report-org` to use the pre-baked paragraphs and skip the LLM API call. No key needed.

## Step 10: Confirm

Tell the user the saved HTML filename. Show a one-line summary: how many contributors, how many in "locked in" / "not locked in", and where the cached extract + narratives live (`~/.werkschau/extracts/`).

The cache is **not** auto-deleted — re-running `/werkschau` for the same window will reuse it and skip both the GitHub re-pull and the brief writing. To force a fresh pull, delete the extract file or pick "Re-pull fresh" when prompted.

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
