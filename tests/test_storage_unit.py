"""Unit tests for storage primitives."""

from __future__ import annotations

import pytest

from relocate_helper.storage.exceptions import (
    ObjectNotFoundError,
    QuarantinedContentError,
    UnsupportedContentError,
)
from relocate_helper.storage.hashing import sha256_digest
from relocate_helper.storage.keys import object_key, quarantine_key
from relocate_helper.storage.memory import InMemoryObjectStorage
from relocate_helper.storage.mime import validate_content


def test_sha256_digest() -> None:
    digest = sha256_digest(b"hello")
    assert len(digest.hex_digest) == 64
    assert digest.size_bytes == 5


def test_content_addressed_keys() -> None:
    h = "a" * 64
    assert object_key("raw", h) == f"raw/objects/aa/{h}"
    assert quarantine_key("raw", h) == f"raw/quarantine/aa/{h}"


def test_validate_plain_text() -> None:
    result = validate_content(b"hello world", filename="notes.txt")
    assert result.mime_type == "text/plain"
    assert result.quarantined is False


def test_validate_quarantine_html() -> None:
    result = validate_content(b"<html><script>alert(1)</script></html>", filename="page.html")
    assert result.quarantined is True


def test_validate_unsupported_binary() -> None:
    with pytest.raises(UnsupportedContentError):
        validate_content(bytes(range(256)))


@pytest.mark.asyncio
async def test_memory_storage_put_get_delete() -> None:
    storage = InMemoryObjectStorage()
    meta = await storage.put(
        "raw/objects/ab/" + "b" * 64,
        b"payload",
        mime_type="text/plain",
        content_hash="b" * 64,
    )
    assert meta.size_bytes == 7
    assert await storage.get(meta.key) == b"payload"
    await storage.delete(meta.key)
    with pytest.raises(ObjectNotFoundError):
        await storage.get(meta.key)


@pytest.mark.asyncio
async def test_memory_storage_deduplicates_same_hash() -> None:
    storage = InMemoryObjectStorage()
    key = "raw/objects/ab/" + "c" * 64
    await storage.put(key, b"same", mime_type="text/plain", content_hash="c" * 64)
    await storage.put(key, b"same", mime_type="text/plain", content_hash="c" * 64)
    assert storage.put_calls == 2
    assert len(storage.payloads) == 1


@pytest.mark.asyncio
async def test_memory_storage_put_failure() -> None:
    storage = InMemoryObjectStorage(fail_on_put=True)
    with pytest.raises(RuntimeError, match="simulated storage failure"):
        await storage.put("k", b"x", mime_type="text/plain", content_hash="d" * 64)


def test_quarantined_content_error_message() -> None:
    with pytest.raises(QuarantinedContentError):
        result = validate_content(b"<html></html>", filename="index.html")
        if result.quarantined:
            raise QuarantinedContentError(result.reason or "quarantined")
