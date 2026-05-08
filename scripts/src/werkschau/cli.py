from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from .discover import discover_repos
from .extract import extract_commit_detail, extract_commits
from .features import commit_features
from .levels import LEVELS, normalize_level, parse_user_spec
from .team_config import list_teams, load_team, save_team, team_path

_DURATION_RE = re.compile(r"^(\d+)([hdwmy])$")


def _parse_since(value: str) -> datetime:
    cleaned = value.strip().lower()
    match = _DURATION_RE.match(cleaned)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
            "w": timedelta(weeks=amount),
            "m": timedelta(days=amount * 30),
            "y": timedelta(days=amount * 365),
        }[unit]
        return datetime.now(timezone.utc) - delta
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise click.BadParameter(
            f"can't parse {value!r}; use durations like 7d, 30d, 1y, or an ISO8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_until(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_members(
    user_specs: tuple[str, ...],
    team: str | None,
    org_path: str | None = None,
) -> list[tuple[str, str | None]]:
    inputs = sum(bool(x) for x in (user_specs, team, org_path))
    if inputs > 1:
        raise click.UsageError("specify exactly one of --user, --team, or --org")
    if org_path:
        from .org import load_org
        org = load_org(org_path)
        return [(p.github, p.level) for p in org.scored_people()]
    if team:
        try:
            return load_team(team)
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc
    if not user_specs:
        raise click.UsageError("specify --user (one or more), --team, or --org")
    return [parse_user_spec(spec) for spec in user_specs]


def _extract_for_user(
    user: str,
    level: str | None,
    since_dt: datetime,
    until_dt: datetime,
    max_repos: int,
    max_commits_per_repo: int,
    include_merges: bool,
) -> dict:
    click.echo(f"[{user}] discovering repos", err=True)
    repos = discover_repos(user, since_dt, until_dt)
    if not repos:
        click.echo(f"[{user}] no authored commits found in window", err=True)
    if len(repos) > max_repos:
        click.echo(f"[{user}] found {len(repos)} repos; truncating to first {max_repos}", err=True)
        repos = repos[:max_repos]
    else:
        click.echo(f"[{user}] found {len(repos)} repos", err=True)
    out_commits: list[dict] = []
    repos_visited: list[str] = []
    for owner, repo in repos:
        full = f"{owner}/{repo}"
        click.echo(f"[{user}]   -> {full}", err=True)
        repos_visited.append(full)
        try:
            commits = extract_commits(owner, repo, user, since_dt, until_dt)
        except Exception as exc:
            click.echo(f"[{user}]      extract failed: {exc}", err=True)
            continue
        if len(commits) > max_commits_per_repo:
            click.echo(f"[{user}]      truncating {len(commits)} commits to {max_commits_per_repo}", err=True)
            commits = commits[:max_commits_per_repo]
        for commit in commits:
            sha = commit.get("sha")
            if not sha:
                continue
            try:
                detail = extract_commit_detail(owner, repo, sha)
            except Exception as exc:
                click.echo(f"[{user}]      {sha[:8]} detail failed: {exc}", err=True)
                continue
            features = commit_features(detail)
            if features["is_merge"] and not include_merges:
                continue
            features["repo"] = full
            out_commits.append(features)
    out_commits.sort(key=lambda c: c.get("committer_date_utc", ""), reverse=True)
    return {
        "user": user,
        "level": level,
        "repos_visited": repos_visited,
        "repo_count": len(repos_visited),
        "commit_count": len(out_commits),
        "total_churn": sum(c["churn"] for c in out_commits),
        "total_heuristic_effort_minutes": sum(c["heuristic_effort_minutes"] for c in out_commits),
        "commits": out_commits,
    }


_GROUP_HELP = """\
Audit a developer's GitHub activity and produce a narrative retrospective.

\b
Two ways to run this:
  /werkschau              -- inside Claude Code / Codex; no API key needed.
  werkschau report        -- cron / CI; needs ANTHROPIC_API_KEY or OPENAI_API_KEY.
"""


@click.group(help=_GROUP_HELP)
def main() -> None:
    pass


def _require_llm_api_key(provider: str) -> None:
    scoped = f"WERKSCHAU_{provider.upper()}_API_KEY"
    generic = f"{provider.upper()}_API_KEY"
    other = "openai" if provider == "anthropic" else "anthropic"

    if os.environ.get(scoped):
        return
    if os.environ.get(generic):
        click.echo(
            f"Warning: using {generic}; prefer {scoped} to avoid collisions with Claude Code.",
            err=True,
        )
        return
    click.echo(
        f"Missing {scoped}. Set it, run --provider {other}, "
        f"or use /werkschau inside Claude Code (no key needed).",
        err=True,
    )
    sys.exit(1)


@main.command(help="Pull commits + diff features for one or more users across every repo they touched in the window.")
@click.option(
    "--user",
    "users",
    multiple=True,
    help="GitHub username, optionally USER:LEVEL (e.g. KranzL:staff). Repeat for multi-user.",
)
@click.option("--team", default=None, help="Load members from ~/.werkschau/teams/<name>.toml")
@click.option("--org", "org_path", default=None, type=click.Path(exists=True, dir_okay=False), help="Load members from an org.json (every non-VP person).")
@click.option("--since", default="7d", show_default=True, help="window start (e.g. 7d, 30d, 1y, or ISO8601)")
@click.option("--until", default=None, help="window end (ISO8601, default = now)")
@click.option("--output", default=None, type=click.Path(dir_okay=False), help="write JSON here, default stdout")
@click.option("--max-repos", default=50, show_default=True, type=int, help="cap on repos per user")
@click.option("--max-commits-per-repo", default=200, show_default=True, type=int)
@click.option("--include-merges/--no-merges", default=False, show_default=True, help="include merge commits")
def extract(
    users: tuple[str, ...],
    team: str | None,
    org_path: str | None,
    since: str,
    until: str | None,
    output: str | None,
    max_repos: int,
    max_commits_per_repo: int,
    include_merges: bool,
) -> None:
    members = _resolve_members(users, team, org_path)
    since_dt = _parse_since(since)
    until_dt = _parse_until(until)
    if until_dt <= since_dt:
        raise click.BadParameter("--until must be after --since")
    click.echo(f"Window: {since_dt.isoformat()} -> {until_dt.isoformat()}", err=True)
    click.echo(
        "Members: " + ", ".join(f"{u}:{l or '?'}" for u, l in members),
        err=True,
    )
    user_payloads = [
        _extract_for_user(
            user,
            level,
            since_dt,
            until_dt,
            max_repos,
            max_commits_per_repo,
            include_merges,
        )
        for user, level in members
    ]
    payload = {
        "since": since_dt.isoformat(),
        "until": until_dt.isoformat(),
        "team": team,
        "user_count": len(user_payloads),
        "users": user_payloads,
    }
    text = json.dumps(payload, indent=2)
    if output:
        Path(output).write_text(text)
        total_commits = sum(u["commit_count"] for u in user_payloads)
        click.echo(
            f"Wrote {total_commits} commits across {len(user_payloads)} users to {output}",
            err=True,
        )
    else:
        click.echo(text)


@main.command(help="""Generate the narrative retrospective from a werkschau extract via an LLM.
For cron / CI. Reads ANTHROPIC_API_KEY or OPENAI_API_KEY (also accepts the
WERKSCHAU_-prefixed forms). For interactive use, run /werkschau instead.""")
@click.option("--input", "input_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Path to extract JSON. Reads stdin if omitted.")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None, help="Write markdown narrative here. Default stdout.")
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), default="anthropic", show_default=True)
@click.option("--model", default=None, help="Override the provider default model.")
@click.option("--base-url", "base_url", default=None, help="Override the LLM API base URL (proxy / Bedrock / OpenAI-compatible endpoint).")
def report(
    input_path: str | None,
    output: str | None,
    provider: str,
    model: str | None,
    base_url: str | None,
) -> None:
    _require_llm_api_key(provider)

    if input_path:
        raw = Path(input_path).read_text()
    else:
        if sys.stdin.isatty():
            raise click.UsageError("provide --input or pipe extract JSON on stdin")
        raw = sys.stdin.read()

    try:
        extract_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"input is not valid JSON: {exc}") from exc

    if not isinstance(extract_data, dict) or "users" not in extract_data:
        raise click.ClickException(
            "input does not look like a werkschau extract (missing 'users' field)"
        )

    from .reporter import generate_narrative

    click.echo(f"Generating narrative via {provider}...", err=True)
    narrative = generate_narrative(
        extract_data,
        provider=provider,
        model=model,
        base_url=base_url,
    )

    if output:
        Path(output).write_text(narrative)
        click.echo(f"Narrative written to {output}", err=True)
    else:
        click.echo(narrative)


@main.command("report-org", help="""End-to-end org report. Reads org.json, runs extract for every non-VP person via gh auth, scores each one, fetches diff samples for the most substantive commits, generates per-person briefs (via LLM API or pre-baked --narratives), and emits a single HTML file ready to email.""")
@click.option("--org", "org_path", type=click.Path(exists=True, dir_okay=False), required=True, help="Path to org.json")
@click.option("--since", default="7d", show_default=True, help="window start (e.g. 7d, 30d, 1y, or ISO8601)")
@click.option("--until", default=None, help="window end (ISO8601, default = now)")
@click.option("--output", "-o", type=click.Path(dir_okay=False), required=True, help="Output HTML path")
@click.option("--extract", "extract_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Pre-computed extract JSON (skips extraction step)")
@click.option("--narratives", "narratives_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Pre-baked narratives JSON: {handle: paragraph, ...}. Skips LLM call and API key requirement.")
@click.option("--no-narrative", is_flag=True, default=False, help="Skip narratives entirely. Renders without 'The Breakdown' section. No LLM call needed.")
@click.option("--max-repos", default=50, show_default=True, type=int)
@click.option("--max-commits-per-repo", default=200, show_default=True, type=int)
@click.option("--include-merges/--no-merges", default=False, show_default=True)
@click.option("--diff-samples-per-user", default=3, show_default=True, type=int, help="Number of substantive commits to fetch full diffs for per user (used when calling LLM).")
@click.option("--issue", default=1, type=int, show_default=True, help="Issue number for the nameplate (Vol. I · No. N)")
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), default="anthropic", show_default=True)
@click.option("--model", default=None, help="Override the provider default model.")
@click.option("--base-url", "base_url", default=None, help="Override the LLM API base URL.")
def report_org(
    org_path: str,
    since: str,
    until: str | None,
    output: str,
    extract_path: str | None,
    narratives_path: str | None,
    no_narrative: bool,
    max_repos: int,
    max_commits_per_repo: int,
    include_merges: bool,
    diff_samples_per_user: int,
    issue: int,
    provider: str,
    model: str | None,
    base_url: str | None,
) -> None:
    from .org import load_org
    from .render import UserBlock, render_html
    from .scoring import score_user

    use_llm = not no_narrative and not narratives_path
    if use_llm:
        _require_llm_api_key(provider)

    pre_narratives: dict[str, str] = {}
    if narratives_path:
        pre_narratives = json.loads(Path(narratives_path).read_text())

    pre_extract: dict | None = None
    if extract_path:
        pre_extract = json.loads(Path(extract_path).read_text())

    org = load_org(org_path)
    since_dt = _parse_since(since)
    until_dt = _parse_until(until)
    if until_dt <= since_dt:
        raise click.BadParameter("--until must be after --since")
    window_seconds = (until_dt - since_dt).total_seconds()
    window_days = max(1.0, window_seconds / 86400.0)

    click.echo(f"Window: {since_dt.isoformat()} -> {until_dt.isoformat()}", err=True)
    scored_people = org.scored_people()
    click.echo(f"Org: {len(scored_people)} contributors (VP {org.vp.github} excluded)", err=True)

    blocks: list[UserBlock] = []
    for person in scored_people:
        user_payload = _user_payload(
            person, pre_extract, since_dt, until_dt,
            max_repos, max_commits_per_repo, include_merges,
        )
        scores = score_user(user_payload, person.level, person.role, int(window_days))

        if no_narrative:
            narrative = ""
        elif person.github in pre_narratives:
            narrative = pre_narratives[person.github].strip()
        elif user_payload["commit_count"] == 0:
            narrative = "No commit-visible activity this week."
        else:
            from .reporter import generate_brief
            sample_diffs = _gather_sample_diffs(user_payload, diff_samples_per_user)
            click.echo(f"[{person.github}] writing brief from {len(sample_diffs)} sampled diffs", err=True)
            narrative = generate_brief(
                user_payload,
                role=person.role,
                level=person.level,
                sample_diffs=sample_diffs,
                provider=provider,
                model=model,
                base_url=base_url,
            ).strip()

        blocks.append(UserBlock(person=person, scores=scores, narrative=narrative))

    click.echo("Rendering HTML", err=True)
    html_text = render_html(
        org,
        blocks,
        since_iso=since_dt.isoformat(),
        until_iso=until_dt.isoformat(),
        issue_number=issue,
        skip_briefs=no_narrative,
    )
    Path(output).write_text(html_text)
    click.echo(f"Wrote {output}", err=True)


def _user_payload(person, pre_extract, since_dt, until_dt, max_repos, max_commits_per_repo, include_merges):
    if pre_extract:
        for u in pre_extract.get("users", []):
            if u.get("user") == person.github:
                return u
        return {
            "user": person.github, "level": person.level, "repos_visited": [],
            "repo_count": 0, "commit_count": 0, "total_churn": 0,
            "total_heuristic_effort_minutes": 0, "commits": [],
        }
    click.echo(f"[{person.github}] extracting", err=True)
    return _extract_for_user(
        person.github, person.level, since_dt, until_dt,
        max_repos, max_commits_per_repo, include_merges,
    )


def _gather_sample_diffs(user_payload: dict, n: int) -> list[dict]:
    from .extract import extract_commit_detail
    from .scoring import _complexity_weighted_effort

    commits = user_payload.get("commits", []) or []
    ranked = sorted(commits, key=lambda c: _complexity_weighted_effort(c), reverse=True)
    samples: list[dict] = []
    for c in ranked[:n]:
        repo = c.get("repo") or ""
        sha = c.get("sha") or ""
        if "/" not in repo or not sha:
            continue
        owner, name = repo.split("/", 1)
        try:
            detail = extract_commit_detail(owner, name, sha)
        except Exception as exc:
            click.echo(f"      diff fetch failed for {sha[:8]}: {exc}", err=True)
            continue
        files = []
        for f in (detail.get("files") or [])[:8]:
            patch = f.get("patch") or ""
            if len(patch) > 1200:
                patch = patch[:1200] + "\n[... truncated ...]"
            files.append({
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "patch": patch,
            })
        samples.append({
            "sha": sha,
            "repo": repo,
            "message": (detail.get("commit") or {}).get("message"),
            "files": files,
        })
    return samples


@main.group(help="Manage saved teams (~/.werkschau/teams/*.toml).")
def team() -> None:
    pass


@team.command(name="save", help="Save a team. Pass --user USER[:LEVEL] one or more times.")
@click.argument("name")
@click.option(
    "--user",
    "users",
    multiple=True,
    required=True,
    help=f"GitHub username, optionally USER:LEVEL. Levels: {', '.join(LEVELS)}.",
)
def team_save(name: str, users: tuple[str, ...]) -> None:
    members = [parse_user_spec(spec) for spec in users]
    path = save_team(name, members)
    click.echo(f"Saved {len(members)}-member team {name!r} to {path}")


@team.command(name="list", help="List saved teams.")
def team_list() -> None:
    teams = list_teams()
    if not teams:
        click.echo(
            "No saved teams. Create one with: werkschau team save <name> --user USER[:LEVEL] ..."
        )
        return
    for entry in teams:
        click.echo(entry)


@team.command(name="show", help="Show the members of a saved team.")
@click.argument("name")
def team_show(name: str) -> None:
    try:
        members = load_team(name)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"# {team_path(name)}")
    for user, level in members:
        click.echo(f"  {user} = {level or '(no level set)'}")


@team.command(name="delete", help="Delete a saved team.")
@click.argument("name")
@click.confirmation_option(prompt="Delete this team file?")
def team_delete(name: str) -> None:
    path = team_path(name)
    if not path.exists():
        raise click.ClickException(f"team {name!r} not found")
    path.unlink()
    click.echo(f"Deleted {path}")


if __name__ == "__main__":
    main()
