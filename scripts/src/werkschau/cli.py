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


@main.command(help="Pull a wide commit history into a window-agnostic local store. Idempotent — re-running merges new commits into the existing store by (user, repo, sha). Use with `report-org --store` or `backfill` to slice the same data into multiple windows without re-hitting GitHub.")
@click.option("--org", "org_path", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to org.json")
@click.option("--since", default="6m", show_default=True, help="how far back to pull (e.g. 6m, 1y, ISO8601)")
@click.option("--until", default=None, help="window end (ISO8601, default = now)")
@click.option("--store", "store_path", default=None, type=click.Path(dir_okay=False), help="Store path. Default ~/.werkschau/store.json")
@click.option("--max-repos", default=50, show_default=True, type=int)
@click.option("--max-commits-per-repo", default=200, show_default=True, type=int)
@click.option("--include-merges/--no-merges", default=False, show_default=True)
def pull(
    org_path: str,
    since: str,
    until: str | None,
    store_path: str | None,
    max_repos: int,
    max_commits_per_repo: int,
    include_merges: bool,
) -> None:
    from .org import load_org

    org = load_org(org_path)
    since_dt = _parse_since(since)
    until_dt = _parse_until(until)
    if until_dt <= since_dt:
        raise click.BadParameter("--until must be after --since")

    resolved_store = Path(store_path).expanduser() if store_path else Path.home() / ".werkschau" / "store.json"
    resolved_store.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if resolved_store.exists():
        try:
            existing = json.loads(resolved_store.read_text())
        except json.JSONDecodeError:
            click.echo(f"Store at {resolved_store} is malformed; rebuilding from scratch.", err=True)
            existing = {}

    click.echo(f"Pulling {since_dt.isoformat()} -> {until_dt.isoformat()}", err=True)
    members = [(p.github, p.level) for p in org.scored_people()]
    click.echo(f"Members: {len(members)}", err=True)

    fresh_payloads = [
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

    merged_users = _merge_users(existing.get("users", []), fresh_payloads)
    covered_since, covered_until = _union_window(existing, since_dt, until_dt)

    payload = {
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "since": covered_since.isoformat(),
        "until": covered_until.isoformat(),
        "user_count": len(merged_users),
        "users": merged_users,
    }
    resolved_store.write_text(json.dumps(payload, indent=2))
    total_commits = sum(u["commit_count"] for u in merged_users)
    click.echo(
        f"Store now covers {covered_since.date()} -> {covered_until.date()}: "
        f"{total_commits} commits across {len(merged_users)} users at {resolved_store}",
        err=True,
    )


def _merge_users(existing_users: list[dict], fresh_users: list[dict]) -> list[dict]:
    by_handle: dict[str, dict] = {u.get("user"): dict(u) for u in existing_users if u.get("user")}
    for fresh in fresh_users:
        handle = fresh.get("user")
        if not handle:
            continue
        prior = by_handle.get(handle)
        if prior is None:
            by_handle[handle] = dict(fresh)
            continue
        commits_by_sha: dict[str, dict] = {}
        for commit in prior.get("commits", []) or []:
            sha = commit.get("sha")
            if sha:
                commits_by_sha[sha] = commit
        for commit in fresh.get("commits", []) or []:
            sha = commit.get("sha")
            if sha:
                commits_by_sha[sha] = commit
        merged_commits = sorted(
            commits_by_sha.values(),
            key=lambda c: c.get("committer_date_utc", ""),
            reverse=True,
        )
        repos_visited = sorted({*(prior.get("repos_visited") or []), *(fresh.get("repos_visited") or [])})
        by_handle[handle] = {
            "user": handle,
            "level": fresh.get("level") or prior.get("level"),
            "repos_visited": repos_visited,
            "repo_count": len(repos_visited),
            "commit_count": len(merged_commits),
            "total_churn": sum(int(c.get("churn") or 0) for c in merged_commits),
            "total_heuristic_effort_minutes": sum(int(c.get("heuristic_effort_minutes") or 0) for c in merged_commits),
            "commits": merged_commits,
        }
    return list(by_handle.values())


def _union_window(existing: dict, new_since: datetime, new_until: datetime) -> tuple[datetime, datetime]:
    covered_since = new_since
    covered_until = new_until
    prior_since = existing.get("since")
    prior_until = existing.get("until")
    if prior_since:
        prior_since_dt = datetime.fromisoformat(prior_since.replace("Z", "+00:00"))
        if prior_since_dt.tzinfo is None:
            prior_since_dt = prior_since_dt.replace(tzinfo=timezone.utc)
        if prior_since_dt < covered_since:
            covered_since = prior_since_dt
    if prior_until:
        prior_until_dt = datetime.fromisoformat(prior_until.replace("Z", "+00:00"))
        if prior_until_dt.tzinfo is None:
            prior_until_dt = prior_until_dt.replace(tzinfo=timezone.utc)
        if prior_until_dt > covered_until:
            covered_until = prior_until_dt
    return covered_since, covered_until


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
@click.option("--store", "store_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Pre-pulled store JSON (filters by --since/--until without hitting GitHub). Mutually exclusive with --extract.")
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
    store_path: str | None,
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

    if extract_path and store_path:
        raise click.UsageError("--extract and --store are mutually exclusive")

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

    if store_path:
        store_data = json.loads(Path(store_path).read_text())
        pre_extract = _slice_store(store_data, since_dt, until_dt)
        click.echo(
            f"Sliced store to {since_dt.date()} -> {until_dt.date()}: "
            f"{sum(u['commit_count'] for u in pre_extract['users'])} commits",
            err=True,
        )

    _render_one_report(
        org=org,
        since_dt=since_dt,
        until_dt=until_dt,
        output_path=Path(output),
        pre_extract=pre_extract,
        pre_narratives=pre_narratives,
        no_narrative=no_narrative,
        max_repos=max_repos,
        max_commits_per_repo=max_commits_per_repo,
        include_merges=include_merges,
        diff_samples_per_user=diff_samples_per_user,
        issue=issue,
        provider=provider,
        model=model,
        base_url=base_url,
    )


def _render_one_report(
    *,
    org,
    since_dt: datetime,
    until_dt: datetime,
    output_path: Path,
    pre_extract: dict | None,
    pre_narratives: dict[str, str],
    no_narrative: bool,
    max_repos: int,
    max_commits_per_repo: int,
    include_merges: bool,
    diff_samples_per_user: int,
    issue: int,
    provider: str,
    model: str | None,
    base_url: str | None,
) -> dict:
    from .render import UserBlock, render_html
    from .scoring import offgrid_scores, score_user

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
            cluster_hints = [
                {
                    "name": i.name,
                    "weighted_minutes": round(i.weighted_minutes),
                    "commit_count": i.commit_count,
                    "repos": list(i.repos),
                    "sample_messages": list(i.sample_messages),
                }
                for i in scores.initiatives[:6]
            ]
            click.echo(f"[{person.github}] writing brief from {len(sample_diffs)} sampled diffs, {len(cluster_hints)} inferred initiatives", err=True)
            narrative = generate_brief(
                user_payload,
                role=person.role,
                level=person.level,
                sample_diffs=sample_diffs,
                description=person.description,
                initiatives=cluster_hints,
                provider=provider,
                model=model,
                base_url=base_url,
            ).strip()

        blocks.append(UserBlock(person=person, scores=scores, narrative=narrative))

    for person in org.offgrid_people():
        blocks.append(UserBlock(person=person, scores=offgrid_scores(), narrative=""))

    click.echo("Rendering HTML", err=True)
    html_text = render_html(
        org,
        blocks,
        since_iso=since_dt.isoformat(),
        until_iso=until_dt.isoformat(),
        issue_number=issue,
        skip_briefs=no_narrative,
    )
    output_path.write_text(html_text)
    click.echo(f"Wrote {output_path}", err=True)

    from .render import NOT_LOCKED_THRESHOLD
    locked = sum(1 for b in blocks if b.scores.output > 0 and b.scores.focus > 0)
    not_locked = sum(
        1 for b in blocks
        if b.scores.output <= NOT_LOCKED_THRESHOLD
        and b.scores.focus <= NOT_LOCKED_THRESHOLD
        and not b.person.is_director
    )
    return {
        "contributor_count": len(scored_people),
        "locked_in_count": locked,
        "not_locked_in_count": not_locked,
    }


@main.command("slice", help="Filter a pre-pulled store by date window and write an extract JSON for one slice. Used by the /werkschau slash command to feed Claude one month's commits at a time without re-reading the full store.")
@click.option("--store", "store_path", default=None, type=click.Path(dir_okay=False), help="Store path. Default ~/.werkschau/store.json")
@click.option("--since", required=True, help="window start (ISO8601 or duration like 30d)")
@click.option("--until", default=None, help="window end (ISO8601, default = now)")
@click.option("--output", "-o", required=True, type=click.Path(dir_okay=False), help="Write filtered extract JSON here.")
def slice_cmd(store_path: str | None, since: str, until: str | None, output: str) -> None:
    resolved_store = Path(store_path).expanduser() if store_path else Path.home() / ".werkschau" / "store.json"
    if not resolved_store.exists():
        raise click.ClickException(f"no store at {resolved_store}; run `werkschau pull` first")

    since_dt = _parse_since(since)
    until_dt = _parse_until(until)
    if until_dt <= since_dt:
        raise click.BadParameter("--until must be after --since")

    store_data = json.loads(resolved_store.read_text())
    extract = _slice_store(store_data, since_dt, until_dt)
    Path(output).write_text(json.dumps(extract, indent=2))
    total = sum(u["commit_count"] for u in extract["users"])
    click.echo(f"Sliced {total} commits across {len(extract['users'])} users -> {output}", err=True)


@main.command("render-index", help="Render an index.html linking every werkschau-YYYY-MM.html in a directory. Used after a slash-command backfill to produce a navigable archive.")
@click.option("--dir", "report_dir", required=True, type=click.Path(exists=True, file_okay=False), help="Directory containing werkschau-YYYY-MM.html files.")
@click.option("--org", "org_path", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to org.json (used for the org name on the index).")
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False), help="Output path. Default <dir>/index.html")
def render_index_cmd(report_dir: str, org_path: str, output: str | None) -> None:
    from .org import load_org
    from .render import IndexEntry, render_index

    org = load_org(org_path)
    directory = Path(report_dir)
    pattern = re.compile(r"^werkschau-(\d{4})-(\d{2})\.html$")
    entries: list[IndexEntry] = []
    for path in sorted(directory.glob("werkschau-*.html")):
        m = pattern.match(path.name)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        entries.append(IndexEntry(
            filename=path.name,
            month_label=month_start.strftime("%B %Y"),
            since_iso=month_start.isoformat(),
            until_iso=month_end.isoformat(),
            contributor_count=0,
            locked_in_count=0,
            not_locked_in_count=0,
        ))

    if not entries:
        raise click.ClickException(f"no werkschau-YYYY-MM.html files found in {directory}")

    output_path = Path(output) if output else directory / "index.html"
    html_text = render_index(
        entries,
        org_name=org.vp.name or org.vp.github,
        generated_iso=datetime.now(timezone.utc).isoformat(),
    )
    output_path.write_text(html_text)
    click.echo(f"Wrote {output_path} ({len(entries)} reports)", err=True)


@main.command(help="Pull a wide window and render one HTML per complete calendar month. Output goes into a dated subdirectory with an index.html linking each month.")
@click.option("--org", "org_path", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to org.json")
@click.option("--months", default=6, show_default=True, type=int, help="Number of complete calendar months to backfill (ending with the most recent complete month).")
@click.option("--store", "store_path", default=None, type=click.Path(dir_okay=False), help="Store path. Default ~/.werkschau/store.json")
@click.option("--output-dir", "output_dir", default=None, type=click.Path(file_okay=False), help="Output directory. Default ./werkschau-backfill-YYYY-MM-DD/")
@click.option("--narratives-dir", "narratives_dir", default=None, type=click.Path(file_okay=False), help="Directory with per-month pre-baked narratives (narratives-YYYY-MM.json). Skips LLM for months that have a file.")
@click.option("--no-narrative", is_flag=True, default=False, help="Skip narratives entirely.")
@click.option("--skip-pull", is_flag=True, default=False, help="Use the existing store as-is; do not re-pull from GitHub.")
@click.option("--max-repos", default=50, show_default=True, type=int)
@click.option("--max-commits-per-repo", default=200, show_default=True, type=int)
@click.option("--include-merges/--no-merges", default=False, show_default=True)
@click.option("--diff-samples-per-user", default=3, show_default=True, type=int)
@click.option("--issue-start", default=1, show_default=True, type=int, help="Issue number for the oldest month (increments by 1 each month).")
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), default="anthropic", show_default=True)
@click.option("--model", default=None)
@click.option("--base-url", "base_url", default=None)
def backfill(
    org_path: str,
    months: int,
    store_path: str | None,
    output_dir: str | None,
    narratives_dir: str | None,
    no_narrative: bool,
    skip_pull: bool,
    max_repos: int,
    max_commits_per_repo: int,
    include_merges: bool,
    diff_samples_per_user: int,
    issue_start: int,
    provider: str,
    model: str | None,
    base_url: str | None,
) -> None:
    from .org import load_org
    from .render import IndexEntry, render_index

    if months < 1:
        raise click.BadParameter("--months must be >= 1")

    use_llm = not no_narrative and not narratives_dir
    if use_llm:
        _require_llm_api_key(provider)

    org = load_org(org_path)
    now = datetime.now(timezone.utc)
    month_windows = _complete_month_windows(now, months)
    oldest_start = month_windows[0][0]
    newest_end = month_windows[-1][1]

    resolved_store = Path(store_path).expanduser() if store_path else Path.home() / ".werkschau" / "store.json"
    resolved_store.parent.mkdir(parents=True, exist_ok=True)

    if not skip_pull:
        click.echo(f"Pulling commits for {oldest_start.date()} -> {newest_end.date()}", err=True)
        existing: dict = {}
        if resolved_store.exists():
            try:
                existing = json.loads(resolved_store.read_text())
            except json.JSONDecodeError:
                existing = {}
        members = [(p.github, p.level) for p in org.scored_people()]
        fresh_payloads = [
            _extract_for_user(
                user, level, oldest_start, newest_end,
                max_repos, max_commits_per_repo, include_merges,
            )
            for user, level in members
        ]
        merged_users = _merge_users(existing.get("users", []), fresh_payloads)
        covered_since, covered_until = _union_window(existing, oldest_start, newest_end)
        resolved_store.write_text(json.dumps({
            "pulled_at": datetime.now(timezone.utc).isoformat(),
            "since": covered_since.isoformat(),
            "until": covered_until.isoformat(),
            "user_count": len(merged_users),
            "users": merged_users,
        }, indent=2))
        click.echo(f"Store updated at {resolved_store}", err=True)
    elif not resolved_store.exists():
        raise click.ClickException(f"--skip-pull set but no store at {resolved_store}")

    store_data = json.loads(resolved_store.read_text())

    resolved_dir = Path(output_dir).expanduser() if output_dir else Path.cwd() / f"werkschau-backfill-{now.date().isoformat()}"
    resolved_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Output dir: {resolved_dir}", err=True)

    narratives_root = Path(narratives_dir).expanduser() if narratives_dir else None
    entries: list[IndexEntry] = []

    for idx, (month_start, month_end) in enumerate(month_windows):
        month_label = month_start.strftime("%B %Y")
        filename = f"werkschau-{month_start.strftime('%Y-%m')}.html"
        output_path = resolved_dir / filename
        click.echo(f"\n=== {month_label} ({month_start.date()} -> {month_end.date()}) ===", err=True)

        pre_narratives: dict[str, str] = {}
        if narratives_root:
            n_path = narratives_root / f"narratives-{month_start.strftime('%Y-%m')}.json"
            if n_path.exists():
                pre_narratives = json.loads(n_path.read_text())
                click.echo(f"Using pre-baked narratives from {n_path}", err=True)

        pre_extract = _slice_store(store_data, month_start, month_end)
        meta = _render_one_report(
            org=org,
            since_dt=month_start,
            until_dt=month_end,
            output_path=output_path,
            pre_extract=pre_extract,
            pre_narratives=pre_narratives,
            no_narrative=no_narrative,
            max_repos=max_repos,
            max_commits_per_repo=max_commits_per_repo,
            include_merges=include_merges,
            diff_samples_per_user=diff_samples_per_user,
            issue=issue_start + idx,
            provider=provider,
            model=model,
            base_url=base_url,
        )
        entries.append(IndexEntry(
            filename=filename,
            month_label=month_label,
            since_iso=month_start.isoformat(),
            until_iso=month_end.isoformat(),
            contributor_count=meta["contributor_count"],
            locked_in_count=meta["locked_in_count"],
            not_locked_in_count=meta["not_locked_in_count"],
        ))

    index_html = render_index(entries, org_name=org.vp.name or org.vp.github, generated_iso=now.isoformat())
    index_path = resolved_dir / "index.html"
    index_path.write_text(index_html)
    click.echo(f"\nWrote index: {index_path}", err=True)
    click.echo(f"Backfill complete: {len(entries)} months in {resolved_dir}", err=True)


def _complete_month_windows(now: datetime, months: int) -> list[tuple[datetime, datetime]]:
    current_month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    windows: list[tuple[datetime, datetime]] = []
    end = current_month_start
    for _ in range(months):
        start = _prev_month_start(end)
        windows.append((start, end))
        end = start
    return list(reversed(windows))


def _prev_month_start(month_start: datetime) -> datetime:
    if month_start.month == 1:
        return datetime(month_start.year - 1, 12, 1, tzinfo=month_start.tzinfo)
    return datetime(month_start.year, month_start.month - 1, 1, tzinfo=month_start.tzinfo)


def _slice_store(store_data: dict, since_dt: datetime, until_dt: datetime) -> dict:
    sliced_users: list[dict] = []
    for user in store_data.get("users", []) or []:
        kept: list[dict] = []
        repos: set[str] = set()
        for commit in user.get("commits", []) or []:
            iso = commit.get("committer_date_utc") or ""
            if not iso:
                continue
            when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if since_dt <= when < until_dt:
                kept.append(commit)
                repo = commit.get("repo")
                if repo:
                    repos.add(repo)
        sliced_users.append({
            "user": user.get("user"),
            "level": user.get("level"),
            "repos_visited": sorted(repos),
            "repo_count": len(repos),
            "commit_count": len(kept),
            "total_churn": sum(int(c.get("churn") or 0) for c in kept),
            "total_heuristic_effort_minutes": sum(int(c.get("heuristic_effort_minutes") or 0) for c in kept),
            "commits": kept,
        })
    return {
        "since": since_dt.isoformat(),
        "until": until_dt.isoformat(),
        "user_count": len(sliced_users),
        "users": sliced_users,
    }


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
