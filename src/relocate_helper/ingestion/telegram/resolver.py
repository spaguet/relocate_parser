"""Normalize Telegram source references."""

from __future__ import annotations

import re

_TME_PATTERN = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?P<slug>[\w\d_]+)/?$",
    re.IGNORECASE,
)
_NUMERIC_PATTERN = re.compile(r"^-?\d+$")


def normalize_telegram_ref(external_ref: str) -> str:
    """Return a canonical ref string for adapter lookup."""
    value = external_ref.strip()
    if not value:
        msg = "Telegram external_ref is empty"
        raise ValueError(msg)

    match = _TME_PATTERN.match(value)
    if match:
        return match.group("slug")

    if value.startswith("@"):
        return value[1:]

    if _NUMERIC_PATTERN.match(value):
        return value

    return value
