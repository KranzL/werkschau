from __future__ import annotations

import json
import os
from typing import Any

_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5",
}


_BRIEF_SYSTEM_PROMPT = """\
You are Werkschau, a calibrated GitHub activity retrospective writer.

Given one engineer's commit-level data plus selected diff samples for the most
substantive commits, write a substantive, specific brief of their week's
commit-visible work. Target ~80-150 words for an active week. The format is
rigid:

  <summary line: 1-2 sentences capturing the shape of the week>

  - **<Initiative or subsystem name>**: <2-3 sentence description: what the
    code actually does, what was changed this week, and the concrete impact
    if visible from the diffs>
  - **<Initiative or subsystem name>**: <same — 2-3 sentences, specific>

Up to FOUR bullets; most weeks have 2-3. Bullets are the substance — each one
should give the reader a real understanding of what shipped, not a label.

Strict rules:

- Each bullet starts with the initiative or subsystem name in **bold**, then
  a colon, then 2-3 sentences. Read the diffs and describe:
    1. What the subsystem is (briefly, if the reader might not know).
    2. What changed in this commit-set: which functions, classes, files,
       behaviors, schemas, or configs got touched and how.
    3. Concrete impact if you can see it from the diffs: a perf win, a new
       capability unlocked, a bug squashed, an external surface added.
  Do not write "improved performance"; write "swapped the per-row linear
  scan in `match_user` for a `set` membership check, cutting the request
  hot-path from O(n) to O(1)".
- If the diffs don't support a level of specificity, hedge ("touched the
  auth middleware in ways the available diff snippets don't fully reveal")
  rather than invent.
- Roll dependabot bumps, README touch-ups, lockfile-only commits, version
  pins, and similar small noise into a single "Maintenance" bullet at most,
  and keep that bullet to one sentence.
- If the engineer's "owns" description is provided, treat it as ground truth
  for what they're responsible for. Use it to disambiguate which subsystem
  a commit touches. Don't restate the description verbatim — go deeper than
  it does.
- The data also contains `inferred_initiatives`: clusters the scoring system
  inferred from commit timestamps, conventional-commit scopes, message
  tokens, and shared directories. Each cluster has a name, weighted minutes,
  commit count, and sample messages. Use these as a starting point for your
  bullets — usually the top 1-3 clusters by weighted_minutes are the right
  bullets. Override the inferred names when the diffs make a more specific
  name obvious; you have richer signal than the heuristic does.
- The data also contains `change_kind_mix`: the share of effort by change
  kind (addition / deletion / refactor / rename / tweak / noise). A week
  dominated by `noise` (merges, reverts, dep bumps, docs-only, single-line
  tweaks) is genuinely a low-substance week — say so directly and don't
  fish for ways to dress it up.
- Be direct about low output. If a Software Engineer, ML Engineer, or
  Analytics Engineer shipped very little this week, just say so:
    * "Did very little this week — one small commit to X."
    * "Light week. The single commit touched only the test fixture."
    * "Not enough commit-visible activity to evaluate."
  No softening. No "probably blocked", no "leverage likely lives outside
  commits", no "review and mentorship", no invented excuses.
- The ONLY roles that get a role-based caveat for low/zero commit activity
  are Data Scientists (DS) and Data Analysts (DA), because most of their
  work genuinely happens in notebooks, BI tools, and dashboards that don't
  commit to git. For these two roles only, you may append a single short
  clause noting that.
- Directors are not expected to commit much; for directors with low or
  zero output, just describe what little they did (or write "No commit-
  visible activity this week.") without judgment in either direction.
  Do not flag directors as below pace.
- If commit_count == 0:
    * For SWE / MLE / AE / Manager: write exactly "No commit-visible
      activity this week." Nothing else.
    * For Director: write exactly "No commit-visible activity this week."
    * For DS / DA: write "No commit-visible activity this week." plus one
      short clause acknowledging notebook / BI / dashboard work.
- If commit_count is low but nonzero: describe what shipped specifically.
  For SWE / MLE / AE / Manager, you may add a direct one-sentence framing
  like "Did very little this week" or "Light week" alongside the
  description if the volume warrants it. Don't speculate about why.
- Don't emit thumbs-up praise on the high end ("great work"). For the
  low end, direct factual framing is fine.
- Never invent commit content the diff data does not support.
- No headers. No code fences. No preamble. No closing recap after the
  bullets.
"""


def generate_brief(
    user_payload: dict[str, Any],
    role: str | None,
    level: str | None,
    sample_diffs: list[dict[str, Any]],
    description: str | None = None,
    initiatives: list[dict[str, Any]] | None = None,
    provider: str = "anthropic",
    model: str | None = None,
    base_url: str | None = None,
) -> str:
    chosen_model = model or _DEFAULT_MODELS.get(provider, "claude-sonnet-4-6")
    user_prompt = _build_brief_prompt(user_payload, role, level, sample_diffs, description, initiatives)
    if provider == "anthropic":
        return _call_anthropic(_BRIEF_SYSTEM_PROMPT, user_prompt, chosen_model, base_url)
    if provider == "openai":
        return _call_openai(_BRIEF_SYSTEM_PROMPT, user_prompt, chosen_model, base_url)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _build_brief_prompt(
    user_payload: dict[str, Any],
    role: str | None,
    level: str | None,
    sample_diffs: list[dict[str, Any]],
    description: str | None = None,
    initiatives: list[dict[str, Any]] | None = None,
) -> str:
    change_kind_mix = _aggregate_change_kind_mix(user_payload.get("commits") or [])
    summary = {
        "user": user_payload.get("user"),
        "role": role,
        "level": level,
        "owns": description,
        "commit_count": user_payload.get("commit_count", 0),
        "repo_count": user_payload.get("repo_count", 0),
        "repos_visited": user_payload.get("repos_visited", []),
        "total_churn": user_payload.get("total_churn", 0),
        "total_heuristic_effort_minutes": user_payload.get("total_heuristic_effort_minutes", 0),
        "change_kind_mix": change_kind_mix,
        "inferred_initiatives": initiatives or [],
    }
    commits_compact = []
    for c in user_payload.get("commits", []) or []:
        commits_compact.append({
            "sha": (c.get("sha") or "")[:8],
            "repo": c.get("repo"),
            "message": c.get("message_first_line"),
            "weekday": c.get("weekday"),
            "additions": c.get("additions"),
            "deletions": c.get("deletions"),
            "files_changed": c.get("files_changed"),
            "change_kind": c.get("change_kind"),
            "test_ratio": c.get("test_ratio"),
        })
    diffs_compact = []
    for d in sample_diffs:
        diffs_compact.append({
            "sha": (d.get("sha") or "")[:8],
            "repo": d.get("repo"),
            "message": d.get("message"),
            "files": d.get("files", []),
        })
    payload = {
        "summary": summary,
        "commits": commits_compact,
        "sample_diffs": diffs_compact,
    }
    return (
        "Write a brief-format narrative paragraph for this engineer's week. "
        "Use the sample diffs to be specific about what they built or changed.\n\n"
        f"<data>\n{json.dumps(payload, indent=2, default=str)}\n</data>"
    )


def _aggregate_change_kind_mix(commits: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    grand_total = 0.0
    for c in commits:
        minutes = float(c.get("heuristic_effort_minutes") or 0)
        if minutes <= 0:
            continue
        kind = c.get("change_kind") or "tweak"
        totals[kind] = totals.get(kind, 0.0) + minutes
        grand_total += minutes
    if grand_total <= 0:
        return {}
    return {k: round(v / grand_total, 3) for k, v in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)}


def _resolve_api_key(provider: str) -> str | None:
    scoped = f"WERKSCHAU_{provider.upper()}_API_KEY"
    generic = f"{provider.upper()}_API_KEY"
    return os.environ.get(scoped) or os.environ.get(generic)


def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str | None = None,
) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "anthropic package not installed. Run: pip install werkschau[llm]"
        ) from exc

    api_key = _resolve_api_key("anthropic")
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**kwargs)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return _extract_anthropic_content(response)


def _extract_anthropic_content(response: Any) -> str:
    text_parts: list[str] = []
    for block in response.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
    return "\n".join(text_parts)


def _call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str | None = None,
) -> str:
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "openai package not installed. Run: pip install werkschau[llm]"
        ) from exc

    api_key = _resolve_api_key("openai")
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _extract_openai_content(response)


def _extract_openai_content(response: Any) -> str:
    message = response.choices[0].message
    return message.content or ""
