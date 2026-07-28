"""Content-addressed object key layout."""

from __future__ import annotations


def object_key(prefix: str, content_hash: str) -> str:
    """Build canonical storage key for accepted content."""
    if len(content_hash) != 64:
        msg = "content_hash must be a 64-char SHA-256 hex string"
        raise ValueError(msg)
    return f"{prefix}/objects/{content_hash[:2]}/{content_hash}"


def quarantine_key(prefix: str, content_hash: str) -> str:
    """Build isolated storage key for quarantined content."""
    if len(content_hash) != 64:
        msg = "content_hash must be a 64-char SHA-256 hex string"
        raise ValueError(msg)
    return f"{prefix}/quarantine/{content_hash[:2]}/{content_hash}"
