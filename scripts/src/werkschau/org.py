from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .levels import normalize_level, normalize_role


@dataclass(frozen=True)
class Person:
    github: str | None
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
        return tuple(p for p in self.people if not p.is_vp and p.github)

    def offgrid_people(self) -> tuple[Person, ...]:
        return tuple(p for p in self.people if not p.is_vp and not p.github)


def load_org(path: str | Path) -> Org:
    raw = json.loads(Path(path).read_text())
    return _build_org(raw)


def _build_org(raw: dict[str, Any]) -> Org:
    vp_raw = raw.get("vp")
    if not vp_raw or not (vp_raw.get("github") or vp_raw.get("name")):
        raise ValueError("org.json must have a 'vp' object with at least a 'name' or 'github' field")
    vp_handle = (vp_raw.get("github") or "").strip() or None
    vp_name = (vp_raw.get("name") or vp_handle or "VP").strip()
    vp = Person(
        github=vp_handle,
        name=vp_name,
        level=None,
        role=None,
        manager=None,
        director=None,
        is_vp=True,
    )

    people: list[Person] = []
    seen: set[str] = set()
    if vp_handle:
        seen.add(vp_handle)

    for e_raw in vp_raw.get("employees", []) or []:
        employee = _build_employee(e_raw, manager_github=None, director_github=None)
        _check_duplicate(employee, seen)
        people.append(employee)

    for d_raw in raw.get("directors", []) or []:
        director = _build_director(d_raw)
        _check_duplicate(director, seen)
        people.append(director)

        for e_raw in d_raw.get("employees", []) or []:
            employee = _build_employee(e_raw, manager_github=None, director_github=director.github)
            _check_duplicate(employee, seen)
            people.append(employee)

        for m_raw in d_raw.get("managers", []) or []:
            manager = _build_manager(m_raw, director.github)
            _check_duplicate(manager, seen)
            people.append(manager)

            for e_raw in m_raw.get("employees", []) or []:
                employee = _build_employee(e_raw, manager.github, director.github)
                _check_duplicate(employee, seen)
                people.append(employee)

    return Org(vp=vp, people=tuple(people))


def _check_duplicate(person: Person, seen: set[str]) -> None:
    if person.github:
        if person.github in seen:
            raise ValueError(f"duplicate github handle: {person.github}")
        seen.add(person.github)


def _normalize_handle(raw: dict[str, Any]) -> str | None:
    handle = (raw.get("github") or "").strip()
    return handle or None


def _build_director(raw: dict[str, Any]) -> Person:
    handle = _normalize_handle(raw)
    name = (raw.get("name") or handle or "").strip()
    if not name:
        raise ValueError("director entry needs at least a name or github handle")
    return Person(
        github=handle,
        name=name,
        level=normalize_level(raw.get("level")) if handle else None,
        role=normalize_role(raw.get("role")) if handle else None,
        manager=None,
        director=handle,
        is_director=True,
    )


def _build_manager(raw: dict[str, Any], director_github: str | None) -> Person:
    handle = _normalize_handle(raw)
    name = (raw.get("name") or handle or "").strip()
    if not name:
        raise ValueError("manager entry needs at least a name or github handle")
    return Person(
        github=handle,
        name=name,
        level=normalize_level(raw.get("level")) if handle else None,
        role=normalize_role(raw.get("role")) if handle else None,
        manager=handle,
        director=director_github,
        is_manager=True,
    )


def _build_employee(raw: dict[str, Any], manager_github: str | None, director_github: str | None) -> Person:
    handle = _normalize_handle(raw)
    name = (raw.get("name") or handle or "").strip()
    if not name:
        raise ValueError("employee entry needs at least a name or github handle")
    return Person(
        github=handle,
        name=name,
        level=normalize_level(raw.get("level")) if handle else None,
        role=normalize_role(raw.get("role")) if handle else None,
        manager=manager_github,
        director=director_github,
    )
