"""Telegram client adapter protocol and test fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class TelegramMediaMeta:
    kind: str
    mime_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    message_id: int
    text: str
    date: datetime
    edit_date: datetime | None = None
    reply_to_message_id: int | None = None
    thread_id: int | None = None
    reactions: dict[str, int] | None = None
    links: tuple[str, ...] = ()
    media: tuple[TelegramMediaMeta, ...] = ()


@dataclass(frozen=True, slots=True)
class TelegramPage:
    messages: tuple[TelegramMessage, ...]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class TelegramPeer:
    peer_id: int
    username: str | None
    title: str


@runtime_checkable
class TelegramClientAdapter(Protocol):
    """Abstraction over Telethon for tests and production."""

    async def resolve_peer(self, ref: str) -> TelegramPeer:
        """Resolve @username, t.me link or numeric peer id."""

    async def fetch_messages(
        self,
        peer_id: int,
        *,
        min_date: datetime | None = None,
        max_date: datetime | None = None,
        min_message_id: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> TelegramPage:
        """Fetch one page of messages ordered from oldest to newest within bounds."""

    async def list_message_ids(
        self,
        peer_id: int,
        *,
        min_message_id: int,
        max_message_id: int,
    ) -> frozenset[int]:
        """Return message ids present in the inclusive id range."""


@dataclass
class FakeTelegramClient:
    """In-memory Telegram adapter for unit and integration tests."""

    peers: dict[str, TelegramPeer] = field(default_factory=dict)
    messages: dict[int, list[TelegramMessage]] = field(default_factory=dict)
    flood_wait_on_call: int | None = None
    call_count: int = 0
    fail_after_messages: int | None = None

    def register_peer(self, ref: str, peer: TelegramPeer) -> None:
        self.peers[ref.lower()] = peer
        self.peers[str(peer.peer_id)] = peer
        if peer.username:
            self.peers[f"@{peer.username.lower()}"] = peer

    def set_messages(self, peer_id: int, messages: list[TelegramMessage]) -> None:
        self.messages[peer_id] = sorted(messages, key=lambda item: item.message_id)

    async def resolve_peer(self, ref: str) -> TelegramPeer:
        self._maybe_flood()
        normalized = ref.strip().lower()
        if normalized.startswith("https://t.me/"):
            normalized = normalized.removeprefix("https://t.me/").split("/")[0]
        if normalized.startswith("@"):
            normalized = normalized
        peer = self.peers.get(normalized) or self.peers.get(ref.strip())
        if peer is None:
            msg = f"Unknown peer ref: {ref}"
            raise LookupError(msg)
        return peer

    async def fetch_messages(
        self,
        peer_id: int,
        *,
        min_date: datetime | None = None,
        max_date: datetime | None = None,
        min_message_id: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> TelegramPage:
        self._maybe_flood()
        self.call_count += 1
        if self.fail_after_messages is not None and self.call_count > 1:
            msg = "Simulated failure mid-sync"
            raise RuntimeError(msg)

        all_messages = list(self.messages.get(peer_id, []))
        filtered: list[TelegramMessage] = []
        for message in all_messages:
            if min_date is not None and message.date < min_date:
                continue
            if max_date is not None and message.date > max_date:
                continue
            if min_message_id is not None and message.message_id <= min_message_id:
                continue
            if cursor is not None and message.message_id <= int(cursor):
                continue
            filtered.append(message)

        start = 0
        page = filtered[start : start + limit]
        has_more = len(filtered) > len(page)
        next_cursor = str(page[-1].message_id) if page and has_more else None
        return TelegramPage(
            messages=tuple(page),
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def list_message_ids(
        self,
        peer_id: int,
        *,
        min_message_id: int,
        max_message_id: int,
    ) -> frozenset[int]:
        self._maybe_flood()
        ids = {
            message.message_id
            for message in self.messages.get(peer_id, [])
            if min_message_id <= message.message_id <= max_message_id
        }
        return frozenset(ids)

    def _maybe_flood(self) -> None:
        if self.flood_wait_on_call is not None:
            seconds = self.flood_wait_on_call
            self.flood_wait_on_call = None
            from relocate_helper.ingestion.telegram.exceptions import TelegramFloodWaitError

            raise TelegramFloodWaitError(seconds)
