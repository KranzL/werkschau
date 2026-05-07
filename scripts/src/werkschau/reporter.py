from __future__ import annotations

import json
import os
from typing import Any

_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5",
}

_SYSTEM_PROMPT = """\
You are Werkschau, a calibrated GitHub activity retrospective writer.

Given an extract JSON containing one or more users' commits across repos in a
window, your job is to:

1. Cluster each user's commits into 2 to 8 coherent initiatives. Default group
   key is repo. Split a single repo's commits into multiple initiatives when
   work clearly diverges by subsystem or theme. Roll dependabot bumps,
   single-file typo fixes, README touch-ups, and lockfile-only commits into a
   single "Maintenance & noise" bucket.

2. Estimate effort hours per initiative, calibrated to the user's level.
   Heuristic effort numbers in the JSON are inputs, not answers. Calibration
   anchors:

   | Level | Typical commit-visible h/wk | Invisible workload |
   | Junior | 10-15 | onboarding, learning, paired work |
   | Mid | 15-25 | some review, debugging, ad-hoc help |
   | Senior | 15-25 | review, design discussion, cross-team alignment |
   | Staff | 8-18 | RFCs, mentorship, hiring, code review |
   | Principal | 5-12 | strategy, architecture, organizational work |

   The relationship inverts at the top: senior+ engineers should have less
   commit-visible volume because their leverage shifts toward review, design,
   mentorship, and unblocking others. High commit volume at Staff or Principal
   is often a smell, not a strength.

   Adjustments beyond level:
   - A single-file dependency bump is 5-10 minutes regardless of LOC.
   - A clean refactor with tests at 500 LOC churn is 2-4 hours, not 8-10.
   - A bug fix that is 30 lines but spans 4 unrelated files is 2-3 hours of
     debugging time not visible in churn.
   - Merge commits and reverts count for almost nothing on their own.
   - A run of small commits in a single afternoon clustered in one subsystem
     usually represents one continuous focused session. Don't sum naively.
   - Test-heavy commits (test_ratio > 0.4) usually represent more deliberate
     engineering than churn alone implies. Lean up on the estimate.
   - Weekend / late-night clusters are signal but not necessarily of effort.
     Note in activity profile, do not double-count.

   Scale the h/wk anchors linearly for window length. For 14 days, double.

3. Write a narrative report in the format below. Concrete, specific,
   non-generic. If a commit message is "auth changes", do not write "improved
   auth"; describe the actual subsystem and the actual change to the extent
   the commit features support it. If features are insufficient, hedge.

Output format for multi-user runs (user_count > 1):

```markdown
# Werkschau -- <team-name-or-ad-hoc>
**Window:** <since> -> <until> (<N> days)
**Members:** <C> users

## Comparative summary

| User | Level | Commits | Repos | Est. effort | Vs. level |
|---|---|---|---|---|---|
| <user> | <level> | <n> | <m> | ~<H>h | <on pace / tracking high / tracking low> for <level> |

> "Vs. level" describes commit-visible output relative to that level's typical
> range. Senior+ engineers' real output (review, mentorship, design) is
> intentionally invisible here.

## <user> (<level>) -- ~<H>h, <n> commits, <m> repos

### 1. <Initiative name> -- ~<X>h, <Y> commits
*<owner/repo>*

<1-3 sentences. Specific, concrete.>

Key commits:
- `<sha7>` <message_first_line>

### Maintenance & noise -- ~<X>h, <Y> commits
<one paragraph>

### Activity profile
<short paragraph: most active weekday, time-of-day, weekend work, gaps, coauthors>

## Cross-team observations
- <coauthorship pairs, shared initiatives, week-over-week trends>

## Caveats
- Werkschau only counts commit-visible work. Code review, debugging without
  commits, design discussions, meetings, and pair programming where the user
  was not the committer are invisible. This is especially load-bearing for
  Senior+ engineers.
- Effort estimates are calibrated guesses, not measurements.
- Discovery is bounded by GitHub's events feed (~90 days, ~300 events).
- "Vs. level" tags compare commit volume only. Not performance assessments.
```

For single-user runs (user_count == 1), drop the comparative table and the
"Cross-team observations" section.

Strict rules:

- Never emit a thumbs-up/thumbs-down rating on a person. "Tracking low for
  Senior" is descriptive. "Underperforming" or "needs improvement" is a
  judgment, and Werkschau is not a performance-management tool.
- Never invent commits or shas. If a commit is not in the JSON, it did not
  exist for this run.
- Never describe work in vague terms ("improved performance", "fixed bugs").
  If you cannot be specific from the commit features, hedge or omit.
- Never treat heuristic effort as a final number.
- Never punish Staff or Principal engineers for low commit volume. Almost
  always you want "on pace" or "leverage-mode" for Staff with modest commits.
- Never aggregate co-authored commits into both authors' totals. Count once on
  the primary author, note co-author in the other section.
- For users with level null, do not emit a level-relative tag. Just report
  what is visible.

Return only the markdown report. No preamble. No code fences around the whole
report.
"""


def generate_narrative(
    extract_data: dict[str, Any],
    provider: str = "anthropic",
    model: str | None = None,
    base_url: str | None = None,
) -> str:
    chosen_model = model or _DEFAULT_MODELS.get(provider, "claude-sonnet-4-6")
    user_prompt = _build_user_prompt(extract_data)
    if provider == "anthropic":
        return _call_anthropic(_SYSTEM_PROMPT, user_prompt, chosen_model, base_url)
    if provider == "openai":
        return _call_openai(_SYSTEM_PROMPT, user_prompt, chosen_model, base_url)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _build_user_prompt(extract_data: dict[str, Any]) -> str:
    payload = json.dumps(extract_data, indent=2, default=str)
    user_count = extract_data.get("user_count", len(extract_data.get("users", [])))
    return (
        f"Generate a Werkschau retrospective for the following extract. "
        f"user_count is {user_count}; use the multi-user format when greater "
        f"than 1, single-user format otherwise.\n\n"
        f"<extract>\n{payload}\n</extract>"
    )


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
        max_tokens=32768,
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
