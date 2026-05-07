from __future__ import annotations

LEVELS: tuple[str, ...] = ("junior", "mid", "senior", "staff", "principal")


def normalize_level(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned in LEVELS:
        return cleaned
    aliases = {
        "jr": "junior",
        "intern": "junior",
        "l1": "junior",
        "l2": "junior",
        "middle": "mid",
        "mid-level": "mid",
        "midlevel": "mid",
        "l3": "mid",
        "l4": "mid",
        "sr": "senior",
        "l5": "senior",
        "staff+": "staff",
        "l6": "staff",
        "principal+": "principal",
        "l7": "principal",
        "l8": "principal",
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
