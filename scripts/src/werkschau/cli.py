from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from .discover import discover_repos
from .extract import extract_commit_detail, extract_commits
from .features import commit_features

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


@click.group(help="Audit a developer's GitHub activity and produce a narrative retrospective.")
def main() -> None:
    pass


@main.command(help="Pull commits + diff features for a user across every repo they touched in the window.")
@click.option("--user", required=True, help="GitHub username to audit")
@click.option("--since", default="7d", show_default=True, help="window start (e.g. 7d, 30d, 1y, or ISO8601)")
@click.option("--until", default=None, help="window end (ISO8601, default = now)")
@click.option("--output", default=None, type=click.Path(dir_okay=False), help="write JSON here, default stdout")
@click.option("--max-repos", default=50, show_default=True, type=int, help="cap on repos to extract from")
@click.option("--max-commits-per-repo", default=200, show_default=True, type=int)
@click.option("--include-merges/--no-merges", default=False, show_default=True, help="include merge commits in output")
def extract(user: str, since: str, until: str | None, output: str | None, max_repos: int, max_commits_per_repo: int, include_merges: bool) -> None:
    since_dt = _parse_since(since)
    until_dt = _parse_until(until)
    if until_dt <= since_dt:
        raise click.BadParameter("--until must be after --since")
    click.echo(f"Discovering repos for {user} from {since_dt.isoformat()} to {until_dt.isoformat()}", err=True)
    repos = discover_repos(user, since_dt, until_dt)
    if not repos:
        click.echo("No PushEvent activity in window. The events feed only covers the last ~90 days.", err=True)
    if len(repos) > max_repos:
        click.echo(f"Found {len(repos)} repos; truncating to first {max_repos}", err=True)
        repos = repos[:max_repos]
    else:
        click.echo(f"Found {len(repos)} repos", err=True)
    out_commits: list[dict] = []
    repos_visited: list[str] = []
    for owner, repo in repos:
        full = f"{owner}/{repo}"
        click.echo(f"  -> {full}", err=True)
        repos_visited.append(full)
        try:
            commits = extract_commits(owner, repo, user, since_dt, until_dt)
        except Exception as exc:
            click.echo(f"     extract failed: {exc}", err=True)
            continue
        if len(commits) > max_commits_per_repo:
            click.echo(f"     truncating {len(commits)} commits to {max_commits_per_repo}", err=True)
            commits = commits[:max_commits_per_repo]
        for commit in commits:
            sha = commit.get("sha")
            if not sha:
                continue
            try:
                detail = extract_commit_detail(owner, repo, sha)
            except Exception as exc:
                click.echo(f"     {sha[:8]} detail failed: {exc}", err=True)
                continue
            features = commit_features(detail)
            if features["is_merge"] and not include_merges:
                continue
            features["repo"] = full
            out_commits.append(features)
    out_commits.sort(key=lambda c: c.get("committer_date_utc", ""), reverse=True)
    payload = {
        "user": user,
        "since": since_dt.isoformat(),
        "until": until_dt.isoformat(),
        "repos_visited": repos_visited,
        "repo_count": len(repos_visited),
        "commit_count": len(out_commits),
        "total_churn": sum(c["churn"] for c in out_commits),
        "total_heuristic_effort_minutes": sum(c["heuristic_effort_minutes"] for c in out_commits),
        "commits": out_commits,
    }
    text = json.dumps(payload, indent=2)
    if output:
        Path(output).write_text(text)
        click.echo(f"Wrote {len(out_commits)} commits across {len(repos_visited)} repos to {output}", err=True)
    else:
        click.echo(text)


if __name__ == "__main__":
    main()
