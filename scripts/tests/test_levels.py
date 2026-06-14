from __future__ import annotations

import pytest

from werkschau.levels import normalize_level, normalize_role


@pytest.mark.parametrize("value,expected", [
    ("l4", "l4"),
    ("L4", "l4"),
    ("senior", "l4"),
    ("Sr", "l4"),
    ("staff", "l5"),
    ("staff+", "l5"),
    ("Senior Manager", "l6"),
    ("director", "l7"),
    ("VP", "l9"),
    ("distinguished engineer", "l9"),
    ("de2", "l2"),
    ("junior", "l2"),
    ("intern", "l1"),
    ("  Senior  ", "l4"),
])
def test_normalize_level_aliases(value, expected):
    assert normalize_level(value) == expected


def test_normalize_level_none_or_empty_returns_none():
    assert normalize_level(None) is None
    assert normalize_level("") is None
    assert normalize_level("   ") is None


def test_normalize_level_unknown_raises():
    with pytest.raises(ValueError, match="unknown level"):
        normalize_level("warlord")


@pytest.mark.parametrize("value,expected", [
    ("swe", "swe"),
    ("Software Engineer", "swe"),
    ("Analytics Engineer", "ae"),
    ("ML", "mle"),
    ("Data Scientist", "ds"),
    ("Data Analyst", "da"),
])
def test_normalize_role_aliases(value, expected):
    assert normalize_role(value) == expected


def test_normalize_role_unknown_raises():
    with pytest.raises(ValueError, match="unknown role"):
        normalize_role("philosopher")
