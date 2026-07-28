"""In-memory ObjectStorage implementation for unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from relocate_helper.storage.exceptions import ObjectNotFoundError
from relocate_helper.storage.protocol import StoredObjectMeta


@dataclass
class InMemoryObjectStorage:
    """Process-local blob store keyed by storage path."""

    objects: dict[str, StoredObjectMeta] = field(default_factory=dict)
    payloads: dict[str, bytes] = field(default_factory=dict)
    put_calls: int = 0
    delete_calls: int = 0
    fail_on_put: bool = False

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        mime_type: str,
        content_hash: str,
        server_side_encryption: bool = True,
    ) -> StoredObjectMeta:
        if self.fail_on_put:
            msg = "simulated storage failure"
            raise RuntimeError(msg)

        self.put_calls += 1
        if key in self.payloads:
            existing = self.objects[key]
            if existing.content_hash != content_hash:
                msg = f"key {key} already holds different content"
                raise ValueError(msg)
            return existing

        meta = StoredObjectMeta(
            key=key,
            content_hash=content_hash,
            mime_type=mime_type,
            size_bytes=len(data),
            etag=content_hash[:16],
        )
        self.objects[key] = meta
        self.payloads[key] = data
        return meta

    async def get(self, key: str) -> bytes:
        if key not in self.payloads:
            raise ObjectNotFoundError(key)
        return self.payloads[key]

    async def head(self, key: str) -> StoredObjectMeta:
        if key not in self.objects:
            raise ObjectNotFoundError(key)
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.delete_calls += 1
        self.objects.pop(key, None)
        self.payloads.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.payloads
