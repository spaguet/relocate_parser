"""Privacy-safe logging helpers for Telegram ingestion."""

from __future__ import annotations

import hashlib


def message_log_fields(*, message_id: int, text: str) -> dict[str, object]:
    """Return log-safe fields without full message body."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return {
        "message_id": message_id,
        "text_length": len(text),
        "text_hash_prefix": digest,
    }
