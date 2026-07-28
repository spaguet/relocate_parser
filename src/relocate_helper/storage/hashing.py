"""Content hashing utilities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContentDigest:
    """SHA-256 digest of raw bytes."""

    hex_digest: str
    size_bytes: int

    @property
    def prefix(self) -> str:
        return self.hex_digest[:2]


def sha256_digest(data: bytes) -> ContentDigest:
    """Compute SHA-256 hex digest and byte length."""
    digest = hashlib.sha256(data).hexdigest()
    return ContentDigest(hex_digest=digest, size_bytes=len(data))
