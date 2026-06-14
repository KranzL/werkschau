from __future__ import annotations

import json

import pytest

from werkschau.org import load_org


def _write_org(tmp_path, data):
    path = tmp_path / "org.json"
    path.write_text(json.dumps(data))
    return path


def test_minimal_org_loads(tmp_path):
    path = _write_org(tmp_path, {
        "vp": {"github": "janevp", "name": "Jane VP"},
        "directors": [
            {
                "github": "ddir",
                "name": "Dana Dir",
                "level": "l7",
                "role": "swe",
                "managers": [
                    {
                        "github": "mmgr",
                        "name": "Mark Mgr",
                        "level": "l5",
                        "role": "swe",
                        "employees": [
                            {"github": "alice", "name": "Alice", "level": "l4", "role": "swe"},
                            {"github": "bob", "name": "Bob", "level": "l3", "role": "swe"},
                        ],
                    }
                ],
            }
        ],
    })
    org = load_org(path)
    assert org.vp.github == "janevp"
    assert org.vp.is_vp is True
    assert len(org.directors()) == 1
    assert len(org.managers()) == 1
    handles = {p.github for p in org.people}
    assert handles == {"ddir", "mmgr", "alice", "bob"}
    alice = org.by_handle("alice")
    assert alice is not None
    assert alice.manager == "mmgr"
    assert alice.level == "l4"


def test_offgrid_person_recognized(tmp_path):
    path = _write_org(tmp_path, {
        "vp": {"github": "janevp", "name": "Jane"},
        "directors": [
            {
                "github": "ddir",
                "name": "Dana",
                "level": "l7",
                "role": "swe",
                "managers": [
                    {
                        "github": "mmgr",
                        "name": "Mark",
                        "level": "l5",
                        "role": "swe",
                        "employees": [
                            {"name": "Mona Lisa", "level": "l3", "role": "swe"},
                        ],
                    }
                ],
            }
        ],
    })
    org = load_org(path)
    offgrid = org.offgrid_people()
    assert len(offgrid) == 1
    assert offgrid[0].name == "Mona Lisa"
    assert offgrid[0].github is None


def test_scored_people_excludes_vp(tmp_path):
    path = _write_org(tmp_path, {
        "vp": {"github": "janevp", "name": "Jane"},
        "directors": [
            {"github": "ddir", "name": "Dana", "level": "l7", "role": "swe"},
        ],
    })
    org = load_org(path)
    scored = org.scored_people()
    assert all(p.github != "janevp" for p in scored)
    assert any(p.github == "ddir" for p in scored)


def test_nested_director_subtree(tmp_path):
    path = _write_org(tmp_path, {
        "vp": {"github": "janevp", "name": "Jane"},
        "directors": [
            {
                "github": "srdir",
                "name": "Sr Dir",
                "level": "l8",
                "role": "swe",
                "directors": [
                    {
                        "github": "subdir",
                        "name": "Sub Dir",
                        "level": "l7",
                        "role": "swe",
                        "employees": [
                            {"github": "alice", "name": "Alice", "level": "l4", "role": "swe"},
                        ],
                    }
                ],
            }
        ],
    })
    org = load_org(path)
    alice = org.by_handle("alice")
    assert alice is not None
    assert alice.director == "subdir"
    assert alice.manager == "subdir"
    assert {d.github for d in org.directors()} == {"srdir", "subdir"}


def test_duplicate_handle_raises(tmp_path):
    path = _write_org(tmp_path, {
        "vp": {"github": "janevp", "name": "Jane"},
        "directors": [
            {
                "github": "ddir",
                "name": "Dana",
                "level": "l7",
                "role": "swe",
                "employees": [
                    {"github": "alice", "name": "Alice One", "level": "l4", "role": "swe"},
                    {"github": "alice", "name": "Alice Two", "level": "l3", "role": "swe"},
                ],
            }
        ],
    })
    with pytest.raises(ValueError, match="duplicate"):
        load_org(path)
