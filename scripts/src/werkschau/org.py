from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .levels import normalize_level, normalize_role


@dataclass(frozen=True)
class Person:
    github: str
    name: str
    level: str | None
    role: str | None
    manager: str | None
    director: str | None
    is_vp: bool = False
    is_director: bool = False
    is_manager: bool = False


@dataclass(frozen=True)
class Org:
    vp: Person
    people: tuple[Person, ...]

    def by_handle(self, github: str) -> Person | None:
        for p in self.people:
            if p.github == github:
                return p
        return None

    def reports_of(self, manager_github: str) -> tuple[Person, ...]:
        return tuple(p for p in self.people if p.manager == manager_github)

    def org_under(self, leader_github: str) -> tuple[Person, ...]:
        return tuple(p for p in self.people if p.director == leader_github or p.manager == leader_github)

    def managers(self) -> tuple[Person, ...]:
        return tuple(p for p in self.people if p.is_manager)

    def directors(self) -> tuple[Person, ...]:
        return tuple(p for p in self.people if p.is_director)

    def scored_people(self) -> tuple[Person, ...]:
        return tuple(p for p in self.people if not p.is_vp)


def load_org(path: str | Path) -> Org:
    raw = json.loads(Path(path).read_text())
    return _build_org(raw)


def _build_org(raw: dict[str, Any]) -> Org:
    vp_raw = raw.get("vp")
    if not vp_raw or not vp_raw.get("github"):
        raise ValueError("org.json must have a 'vp' object with at least a 'github' field")
    vp = Person(
        github=vp_raw["github"].strip(),
        name=vp_raw.get("name", vp_raw["github"]).strip(),
        level=None,
        role=None,
        manager=None,
        director=None,
        is_vp=True,
    )

    people: list[Person] = []
    seen: set[str] = {vp.github}

    for d_raw in raw.get("directors", []) or []:
        director = _build_director(d_raw)
        if director.github in seen:
            raise ValueError(f"duplicate github handle: {director.github}")
        seen.add(director.github)
        people.append(director)

        for m_raw in d_raw.get("managers", []) or []:
            manager = _build_manager(m_raw, director.github)
            if manager.github in seen:
                raise ValueError(f"duplicate github handle: {manager.github}")
            seen.add(manager.github)
            people.append(manager)

            for e_raw in m_raw.get("employees", []) or []:
                employee = _build_employee(e_raw, manager.github, director.github)
                if employee.github in seen:
                    raise ValueError(f"duplicate github handle: {employee.github}")
                seen.add(employee.github)
                people.append(employee)

    return Org(vp=vp, people=tuple(people))


def _build_director(raw: dict[str, Any]) -> Person:
    handle = raw["github"].strip()
    return Person(
        github=handle,
        name=(raw.get("name") or handle).strip(),
        level=normalize_level(raw.get("level")),
        role=normalize_role(raw.get("role")),
        manager=None,
        director=handle,
        is_director=True,
    )


def _build_manager(raw: dict[str, Any], director_github: str) -> Person:
    handle = raw["github"].strip()
    return Person(
        github=handle,
        name=(raw.get("name") or handle).strip(),
        level=normalize_level(raw.get("level")),
        role=normalize_role(raw.get("role")),
        manager=handle,
        director=director_github,
        is_manager=True,
    )


def _build_employee(raw: dict[str, Any], manager_github: str, director_github: str) -> Person:
    handle = raw["github"].strip()
    return Person(
        github=handle,
        name=(raw.get("name") or handle).strip(),
        level=normalize_level(raw.get("level")),
        role=normalize_role(raw.get("role")),
        manager=manager_github,
        director=director_github,
    )
