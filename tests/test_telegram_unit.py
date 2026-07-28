"""Unit tests for Telegram ingestion helpers (no database)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from relocate_helper.ingestion.telegram.adapter import (
    FakeTelegramClient,
    TelegramMessage,
    TelegramPeer,
)
from relocate_helper.ingestion.telegram.cursor import TelegramSyncCursor
from relocate_helper.ingestion.telegram.exceptions import TelegramFloodWaitError
from relocate_helper.ingestion.telegram.resolver import normalize_telegram_ref
from relocate_helper.ingestion.telegram.serialization import message_metadata, message_to_bytes


def test_normalize_telegram_ref_variants() -> None:
    assert normalize_telegram_ref("@channel") == "channel"
    assert normalize_telegram_ref("https://t.me/my_chat/") == "my_chat"
    assert normalize_telegram_ref("-100123") == "-100123"


def test_sync_cursor_roundtrip() -> None:
    cursor = TelegramSyncCursor(
        peer_id=100,
        last_message_id=42,
        page_cursor="41",
        min_date=datetime(2026, 1, 1, tzinfo=UTC),
        max_date=datetime(2026, 6, 1, tzinfo=UTC),
        tracked_min_message_id=10,
        tracked_max_message_id=42,
    )
    restored = TelegramSyncCursor.from_json(cursor.to_json())
    assert restored == cursor


def test_message_serialization() -> None:
    message = TelegramMessage(
        message_id=7,
        text="hello Floripa",
        date=datetime(2026, 3, 1, tzinfo=UTC),
        edit_date=datetime(2026, 3, 2, tzinfo=UTC),
        reply_to_message_id=3,
        thread_id=99,
        reactions={"👍": 2},
        links=("https://example.com",),
        media=(),
    )
    payload = message_to_bytes(message)
    assert b"hello Floripa" in payload
    meta = message_metadata(message)
    assert meta["telegram"]["message_id"] == 7
    assert meta["telegram"]["text_length"] == len(message.text)


@pytest.mark.asyncio
async def test_fake_adapter_pagination() -> None:
    client = FakeTelegramClient()
    peer = TelegramPeer(peer_id=1, username="test", title="Test")
    client.register_peer("@test", peer)
    messages = [
        TelegramMessage(
            message_id=i,
            text=f"msg-{i}",
            date=datetime(2026, 1, i, tzinfo=UTC),
        )
        for i in range(1, 6)
    ]
    client.set_messages(1, messages)

    first = await client.fetch_messages(1, limit=2)
    assert [item.message_id for item in first.messages] == [1, 2]
    assert first.has_more is True

    second = await client.fetch_messages(1, cursor=first.next_cursor, limit=2)
    assert [item.message_id for item in second.messages] == [3, 4]
    assert second.has_more is True

    third = await client.fetch_messages(1, cursor=second.next_cursor, limit=2)
    assert [item.message_id for item in third.messages] == [5]
    assert third.has_more is False


@pytest.mark.asyncio
async def test_fake_adapter_flood_wait() -> None:
    client = FakeTelegramClient()
    client.flood_wait_on_call = 30
    with pytest.raises(TelegramFloodWaitError) as exc:
        await client.resolve_peer("@missing")
    assert exc.value.seconds == 30
