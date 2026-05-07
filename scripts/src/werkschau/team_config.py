from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .levels import normalize_level


def teams_dir() -> Path:
    override = os.environ.get("WERKSCHAU_TEAMS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".werkschau" / "teams"


def team_path(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
    if safe != name or not safe:
        raise ValueError(f"team name {name!r} must be alphanumeric with - or _")
    return teams_dir() / f"{safe}.toml"


def load_team(name: str) -> list[tuple[str, str | None]]:
    path = team_path(name)
    if not path.exists():
        raise FileNotFoundError(f"team file not found: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    members_raw = data.get("members") or {}
    members: list[tuple[str, str | None]] = []
    for user, level in members_raw.items():
        members.append((user, normalize_level(level) if level else None))
    return members


def save_team(name: str, members: list[tuple[str, str | None]]) -> Path:
    path = team_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[members]"]
    for user, level in members:
        value = level if level else ""
        lines.append(f'{user} = "{value}"')
    path.write_text("\n".join(lines) + "\n")
    return path


def list_teams() -> list[str]:
    directory = teams_dir()
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.toml"))
