from __future__ import annotations

LEVELS: tuple[str, ...] = (
    "l1",
    "l2",
    "l3",
    "senior",
    "staff",
    "senior staff",
    "principal",
    "senior principal",
    "distinguished",
)

LEVEL_BASELINE_MINUTES: dict[str, int] = {
    "l1": 600,
    "l2": 700,
    "l3": 700,
    "senior": 600,
    "staff": 400,
    "senior staff": 300,
    "principal": 250,
    "senior principal": 180,
    "distinguished": 120,
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
        "junior": "l1",
        "jr": "l1",
        "intern": "l1",
        "engineer 1": "l1",
        "swe 1": "l1",
        "de1": "l1",
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
        "l4": "senior",
        "sr": "senior",
        "l5": "senior",
        "staff+": "staff",
        "l6": "staff",
        "sr staff": "senior staff",
        "sr. staff": "senior staff",
        "senior-staff": "senior staff",
        "l7": "senior staff",
        "principal+": "principal",
        "l8": "principal",
        "sr principal": "senior principal",
        "sr. principal": "senior principal",
        "senior-principal": "senior principal",
        "l9": "senior principal",
        "distinguished engineer": "distinguished",
        "l10": "distinguished",
        "manager": "staff",
        "engineering manager": "staff",
        "em": "staff",
        "senior manager": "senior staff",
        "sr manager": "senior staff",
        "sr. manager": "senior staff",
        "senior-manager": "senior staff",
        "director": "principal",
        "senior director": "senior principal",
        "sr director": "senior principal",
        "sr. director": "senior principal",
        "senior-director": "senior principal",
        "vp": "distinguished",
        "vice president": "distinguished",
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
