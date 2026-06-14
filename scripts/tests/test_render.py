from __future__ import annotations

import json

from werkschau.org import load_org
from werkschau.render import UserBlock, _is_inactive_for_callout, _is_locked_in, render_html
from werkschau.scoring import offgrid_scores, score_user

from .conftest import make_commit


def _build_org(tmp_path):
    path = tmp_path / "org.json"
    path.write_text(json.dumps({
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
    }))
    return load_org(path)


def _payload(handle, commits):
    return {
        "user": handle,
        "level": "l4",
        "commits": commits,
        "commit_count": len(commits),
        "total_churn": sum(c.get("churn", 0) for c in commits),
        "total_heuristic_effort_minutes": sum(c.get("heuristic_effort_minutes", 0) for c in commits),
        "repos_visited": ["foo/bar"],
        "repo_count": 1,
    }


def test_render_html_runs_end_to_end(tmp_path):
    org = _build_org(tmp_path)
    blocks = []
    for person in org.scored_people():
        scores = score_user(_payload(person.github, []), person.level, person.role, 7)
        blocks.append(UserBlock(person=person, scores=scores, narrative=""))
    for person in org.offgrid_people():
        blocks.append(UserBlock(person=person, scores=offgrid_scores(), narrative=""))

    html = render_html(
        org,
        blocks,
        since_iso="2026-06-07T00:00:00+00:00",
        until_iso="2026-06-14T00:00:00+00:00",
        issue_number=1,
        skip_briefs=True,
    )
    assert "Werkschau" in html
    assert "Locked in" in html
    assert "Inactive" in html
    assert "SUBSTANCE" in html
    assert "EFFORT" in html


def test_locked_in_classification(tmp_path):
    org = _build_org(tmp_path)
    alice = org.by_handle("alice")
    busy_payload = _payload("alice", [
        make_commit(sha=f"{i:040x}", additions=200, deletions=100, files_changed=6,
                    heuristic_effort_minutes=200)
        for i in range(6)
    ])
    scores = score_user(busy_payload, alice.level, alice.role, 7)
    block = UserBlock(person=alice, scores=scores, narrative="")
    assert _is_locked_in(block) is True
    assert _is_inactive_for_callout(block) is False


def test_director_excluded_from_inactive(tmp_path):
    org = _build_org(tmp_path)
    director = org.by_handle("ddir")
    scores = score_user(_payload("ddir", []), director.level, director.role, 7)
    block = UserBlock(person=director, scores=scores, narrative="")
    assert scores.inactive is True
    assert _is_inactive_for_callout(block) is False


def test_offgrid_excluded_from_inactive(tmp_path):
    org = _build_org(tmp_path)
    offgrid_person = None
    for p in org.scored_people():
        offgrid_person = p
        break
    assert offgrid_person is not None
    from dataclasses import replace
    person_no_github = replace(offgrid_person, github=None)
    block = UserBlock(person=person_no_github, scores=offgrid_scores(), narrative="")
    assert block.scores.inactive is True
    assert _is_inactive_for_callout(block) is False
