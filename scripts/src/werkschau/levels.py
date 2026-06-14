from __future__ import annotations

_LEVELS: frozenset[str] = frozenset({
    "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9",
})

_ROLES: frozenset[str] = frozenset({"swe", "ae", "mle", "ds", "da"})


def normalize_role(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().lower().split())
    if not cleaned:
        return None
    if cleaned in _ROLES:
        return cleaned
    aliases = {
        "software engineer": "swe",
        "software": "swe",
        "engineer": "swe",
        "analytics engineer": "ae",
        "analytics": "ae",
        "ml engineer": "mle",
        "ml": "mle",
        "machine learning engineer": "mle",
        "machine learning": "mle",
        "data scientist": "ds",
        "data science": "ds",
        "data analyst": "da",
        "analyst": "da",
    }
    if cleaned in aliases:
        return aliases[cleaned]
    raise ValueError(f"unknown role {value!r}; expected one of {sorted(_ROLES)}")


def normalize_level(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().lower().split())
    if not cleaned:
        return None
    if cleaned in _LEVELS:
        return cleaned
    aliases = {
        "intern": "l1",
        "engineer 1": "l1",
        "swe 1": "l1",
        "de1": "l1",
        "junior": "l2",
        "jr": "l2",
        "mid": "l2",
        "middle": "l2",
        "mid-level": "l2",
        "midlevel": "l2",
        "engineer 2": "l2",
        "swe 2": "l2",
        "de2": "l2",
        "engineer 3": "l3",
        "swe 3": "l3",
        "de3": "l3",
        "senior": "l4",
        "sr": "l4",
        "staff": "l5",
        "staff+": "l5",
        "senior staff": "l6",
        "sr staff": "l6",
        "sr. staff": "l6",
        "senior-staff": "l6",
        "principal": "l7",
        "principal+": "l7",
        "senior principal": "l8",
        "sr principal": "l8",
        "sr. principal": "l8",
        "senior-principal": "l8",
        "distinguished": "l9",
        "distinguished engineer": "l9",
        "manager": "l5",
        "engineering manager": "l5",
        "em": "l5",
        "senior manager": "l6",
        "sr manager": "l6",
        "sr. manager": "l6",
        "senior-manager": "l6",
        "director": "l7",
        "senior director": "l8",
        "sr director": "l8",
        "sr. director": "l8",
        "senior-director": "l8",
        "vp": "l9",
        "vice president": "l9",
    }
    if cleaned in aliases:
        return aliases[cleaned]
    raise ValueError(f"unknown level {value!r}; expected one of {sorted(_LEVELS)}")
