from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .levels import normalize_level, normalize_role


@dataclass(frozen=True)
class Person:
    id: str
    github: str | None
    name: str
    level: str | None
    role: str | None
    manager: str | None
    director: str | None
    description: str | None = None
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

    def by_id(self, person_id: str) -> Person | None:
        if self.vp.id == person_id:
            return self.vp
        for p in self.people:
            if p.id == person_id:
                return p
        return None

    def reports_of(self, leader_id: str | None) -> tuple[Person, ...]:
        if not leader_id:
            return ()
        return tuple(p for p in self.people if p.manager == leader_id)

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


def _person_id(handle: str | None, name: str) -> str:
    if handle:
        return handle
    return f"name:{name}"


def _normalize_handle(raw: dict[str, Any]) -> str | None:
    handle = (raw.get("github") or "").strip()
    return handle or None


def _description(raw: dict[str, Any]) -> str | None:
    d = (raw.get("description") or "").strip()
    return d or None


def _build_org(raw: dict[str, Any]) -> Org:
    vp_raw = raw.get("vp")
    if not vp_raw or not (vp_raw.get("github") or vp_raw.get("name")):
        raise ValueError("org.json must have a 'vp' object with at least a 'name' or 'github' field")
    vp_handle = _normalize_handle(vp_raw)
    vp_name = (vp_raw.get("name") or vp_handle or "VP").strip()
    vp_id = _person_id(vp_handle, vp_name)
    vp = Person(
        id=vp_id,
        github=vp_handle,
        name=vp_name,
        level=None,
        role=None,
        manager=None,
        director=None,
        description=_description(vp_raw),
        is_vp=True,
    )

    people: list[Person] = []
    seen_ids: set[str] = {vp_id}

    for e_raw in vp_raw.get("employees", []) or []:
        emp = _build_employee(e_raw, manager_id=vp_id, director_id=None)
        _check_duplicate(emp, seen_ids)
        people.append(emp)

    top_directors = list(vp_raw.get("directors", []) or []) + list(raw.get("directors", []) or [])
    for d_raw in top_directors:
        _add_director_subtree(d_raw, parent_id=vp_id, people=people, seen_ids=seen_ids)

    for m_raw in vp_raw.get("managers", []) or []:
        _add_manager_subtree(m_raw, parent_id=vp_id, director_id=None, people=people, seen_ids=seen_ids)

    return Org(vp=vp, people=tuple(people))


def _add_director_subtree(
    raw: dict[str, Any],
    parent_id: str,
    people: list[Person],
    seen_ids: set[str],
) -> None:
    director = _build_director(raw, parent_id=parent_id)
    _check_duplicate(director, seen_ids)
    people.append(director)

    for e_raw in raw.get("employees", []) or []:
        emp = _build_employee(e_raw, manager_id=director.id, director_id=director.id)
        _check_duplicate(emp, seen_ids)
        people.append(emp)

    for nested_d in raw.get("directors", []) or []:
        _add_director_subtree(nested_d, parent_id=director.id, people=people, seen_ids=seen_ids)

    for m_raw in raw.get("managers", []) or []:
        _add_manager_subtree(
            m_raw, parent_id=director.id, director_id=director.id,
            people=people, seen_ids=seen_ids,
        )


def _add_manager_subtree(
    raw: dict[str, Any],
    parent_id: str,
    director_id: str | None,
    people: list[Person],
    seen_ids: set[str],
) -> None:
    manager = _build_manager(raw, parent_id=parent_id, director_id=director_id)
    _check_duplicate(manager, seen_ids)
    people.append(manager)

    for e_raw in raw.get("employees", []) or []:
        emp = _build_employee(e_raw, manager_id=manager.id, director_id=director_id)
        _check_duplicate(emp, seen_ids)
        people.append(emp)


def _check_duplicate(person: Person, seen_ids: set[str]) -> None:
    if person.id in seen_ids:
        raise ValueError(f"duplicate person id: {person.id}")
    seen_ids.add(person.id)


def _build_director(raw: dict[str, Any], parent_id: str) -> Person:
    handle = _normalize_handle(raw)
    name = (raw.get("name") or handle or "").strip()
    if not name:
        raise ValueError("director entry needs at least a name or github handle")
    own_id = _person_id(handle, name)
    return Person(
        id=own_id,
        github=handle,
        name=name,
        level=normalize_level(raw.get("level")) if handle else None,
        role=normalize_role(raw.get("role")) if handle else None,
        manager=parent_id,
        director=own_id,
        description=_description(raw),
        is_director=True,
    )


def _build_manager(raw: dict[str, Any], parent_id: str, director_id: str | None) -> Person:
    handle = _normalize_handle(raw)
    name = (raw.get("name") or handle or "").strip()
    if not name:
        raise ValueError("manager entry needs at least a name or github handle")
    own_id = _person_id(handle, name)
    return Person(
        id=own_id,
        github=handle,
        name=name,
        level=normalize_level(raw.get("level")) if handle else None,
        role=normalize_role(raw.get("role")) if handle else None,
        manager=parent_id,
        director=director_id,
        description=_description(raw),
        is_manager=True,
    )


def _build_employee(raw: dict[str, Any], manager_id: str | None, director_id: str | None) -> Person:
    handle = _normalize_handle(raw)
    name = (raw.get("name") or handle or "").strip()
    if not name:
        raise ValueError("employee entry needs at least a name or github handle")
    return Person(
        id=_person_id(handle, name),
        github=handle,
        name=name,
        level=normalize_level(raw.get("level")) if handle else None,
        role=normalize_role(raw.get("role")) if handle else None,
        manager=manager_id,
        director=director_id,
        description=_description(raw),
    )
