from __future__ import annotations

LEVELS: tuple[str, ...] = (
    "l1",
    "l2",
    "l3",
    "l4",
    "l5",
    "l6",
    "l7",
    "l8",
    "l9",
)

LEVEL_BASELINE_MINUTES: dict[str, int] = {
    "l1": 500,
    "l2": 600,
    "l3": 700,
    "l4": 600,
    "l5": 400,
    "l6": 300,
    "l7": 250,
    "l8": 180,
    "l9": 120,
}

ROLES: tuple[str, ...] = ("swe", "ae", "mle", "ds", "da")

ROLE_MULTIPLIER: dict[str, float] = {
    "swe": 1.0,
    "ae": 0.9,
    "mle": 0.8,
    "ds": 0.55,
    "da": 0.5,
}


def normalize_role(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().lower().split())
    if not cleaned:
        return None
    if cleaned in ROLES:
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
    raise ValueError(f"unknown role {value!r}; expected one of {ROLES}")


def baseline_minutes(role: str | None, level: str | None) -> float | None:
    if level is None:
        return None
    level_norm = normalize_level(level)
    if level_norm is None or level_norm not in LEVEL_BASELINE_MINUTES:
        return None
    base = LEVEL_BASELINE_MINUTES[level_norm]
    if role is None:
        return float(base)
    role_norm = normalize_role(role)
    if role_norm is None:
        return float(base)
    return float(base) * ROLE_MULTIPLIER.get(role_norm, 1.0)


def normalize_level(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().lower().split())
    if not cleaned:
        return None
    if cleaned in LEVELS:
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
    raise ValueError(f"unknown level {value!r}; expected one of {LEVELS}")


def parse_user_spec(spec: str) -> tuple[str, str | None]:
    text = spec.strip()
    if ":" in text:
        user, level_raw = text.split(":", 1)
        return user.strip(), normalize_level(level_raw)
    return text, None
