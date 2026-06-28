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


def test_inactive_callout_suppressed_when_meeting_heavy(tmp_path):
    org = _build_org(tmp_path)
    alice = org.by_handle("alice")
    scores = score_user(_payload("alice", []), alice.level, alice.role, 7, calendar={"meeting_minutes": 1000.0, "window_days": 7})
    block = UserBlock(person=alice, scores=scores, narrative="")
    assert scores.inactive is True
    assert scores.meeting_heavy is True
    assert _is_inactive_for_callout(block) is False


def test_inactive_callout_present_when_not_meeting_heavy(tmp_path):
    org = _build_org(tmp_path)
    alice = org.by_handle("alice")
    scores = score_user(_payload("alice", []), alice.level, alice.role, 7, calendar={"meeting_minutes": 0.0, "window_days": 7})
    block = UserBlock(person=alice, scores=scores, narrative="")
    assert scores.inactive is True
    assert scores.meeting_heavy is False
    assert _is_inactive_for_callout(block) is True


def test_calendar_panel_present_with_breakdown(tmp_path):
    org = _build_org(tmp_path)
    blocks = []
    for person in org.scored_people():
        cal = None
        if person.github == "alice":
            cal = {
                "meeting_minutes": 480.0,
                "meeting_count": 12,
                "focus_minutes": 60.0,
                "ooo_minutes": 0.0,
                "recurring_count": 9,
                "adhoc_count": 3,
                "one_on_one_count": 4,
                "group_count": 8,
                "window_days": 7,
            }
        scores = score_user(_payload(person.github, []), person.level, person.role, 7, calendar=cal)
        blocks.append(UserBlock(person=person, scores=scores, narrative=""))
    for person in org.offgrid_people():
        blocks.append(UserBlock(person=person, scores=offgrid_scores(), narrative=""))
    html = render_html(
        org,
        blocks,
        since_iso="2026-06-07T00:00:00+00:00",
        until_iso="2026-06-14T00:00:00+00:00",
        issue_number=1,
        skip_briefs=False,
    )
    assert 'class="brief-person-calendar"' in html
    assert "min in meetings" in html
    assert "recurring" in html
    assert "one-on-one" in html


def test_calendar_panel_absent_when_no_calendar_data(tmp_path):
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
        skip_briefs=False,
    )
    assert 'class="brief-person-calendar"' not in html


def test_calendar_schema_keys_are_only_numeric():
    calendar = {
        "meeting_minutes": 480.0,
        "meeting_count": 12,
        "focus_minutes": 120.0,
        "ooo_minutes": 0.0,
        "recurring_count": 9,
        "adhoc_count": 3,
        "one_on_one_count": 4,
        "group_count": 8,
        "window_days": 7,
    }
    expected_keys = {
        "meeting_minutes", "meeting_count", "focus_minutes", "ooo_minutes",
        "recurring_count", "adhoc_count", "one_on_one_count", "group_count", "window_days",
    }
    assert set(calendar.keys()) == expected_keys
    for v in calendar.values():
        assert isinstance(v, (int, float))
