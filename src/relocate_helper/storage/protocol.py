"""Object storage protocol and metadata types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StoredObjectMeta:
    key: str
    content_hash: str
    mime_type: str
    size_bytes: int
    etag: str | None = None


@runtime_checkable
class ObjectStorage(Protocol):
    """Async object storage backend (S3-compatible or in-memory fake)."""

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        mime_type: str,
        content_hash: str,
        server_side_encryption: bool = True,
    ) -> StoredObjectMeta:
        """Store bytes at key; idempotent if content_hash matches existing object."""
        ...

    async def get(self, key: str) -> bytes:
        """Fetch object bytes."""
        ...

    async def head(self, key: str) -> StoredObjectMeta:
        """Return metadata without downloading body."""
        ...

    async def delete(self, key: str) -> None:
        """Remove object; no-op if missing."""
        ...

    async def exists(self, key: str) -> bool:
        """Return True when object is present."""
        ...
