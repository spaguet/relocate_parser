"""Telethon-backed Telegram client adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from relocate_helper.common.config import Settings
from relocate_helper.common.logging import get_logger
from relocate_helper.ingestion.telegram.adapter import (
    TelegramClientAdapter,
    TelegramMediaMeta,
    TelegramMessage,
    TelegramPage,
    TelegramPeer,
)
from relocate_helper.ingestion.telegram.exceptions import TelegramFloodWaitError

logger = get_logger(__name__)


class TelethonClientAdapter:
    """Production adapter using Telethon and a session file outside the repo."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def resolve_peer(self, ref: str) -> TelegramPeer:
        client = await self._connect()
        try:
            entity = await client.get_entity(ref)
            username = getattr(entity, "username", None)
            title = getattr(entity, "title", None) or getattr(entity, "first_name", ref)
            return TelegramPeer(peer_id=int(entity.id), username=username, title=str(title))
        finally:
            await client.disconnect()

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
        client = await self._connect()
        try:
            entity = await client.get_entity(peer_id)
            kwargs: dict[str, Any] = {
                "limit": limit,
                "reverse": True,
            }
            if min_date is not None:
                kwargs["offset_date"] = min_date
            if max_date is not None:
                kwargs["max_date"] = max_date
            if min_message_id is not None:
                kwargs["min_id"] = min_message_id
            if cursor is not None:
                kwargs["min_id"] = max(int(cursor), min_message_id or 0)

            raw_messages = await self._call(client.get_messages(entity, **kwargs))
            converted = tuple(_convert_message(message) for message in reversed(raw_messages))
            has_more = len(converted) >= limit
            next_cursor = str(converted[-1].message_id) if converted and has_more else None
            return TelegramPage(messages=converted, next_cursor=next_cursor, has_more=has_more)
        finally:
            await client.disconnect()

    async def list_message_ids(
        self,
        peer_id: int,
        *,
        min_message_id: int,
        max_message_id: int,
    ) -> frozenset[int]:
        client = await self._connect()
        try:
            entity = await client.get_entity(peer_id)
            ids: set[int] = set()
            async for message in client.iter_messages(
                entity,
                min_id=min_message_id - 1,
                max_id=max_message_id + 1,
            ):
                if min_message_id <= message.id <= max_message_id:
                    ids.add(message.id)
            return frozenset(ids)
        finally:
            await client.disconnect()

    async def _connect(self) -> Any:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        api_id = self._settings.telegram_api_id
        api_hash = self._settings.telegram_api_hash.get_secret_value()
        session_path = self._settings.telethon_session_path

        if session_path and session_path.exists():
            client = TelegramClient(str(session_path), api_id, api_hash)
        else:
            session_string = self._settings.telethon_session_string
            if session_string is None:
                msg = "Telethon session is not configured"
                raise RuntimeError(msg)
            client = TelegramClient(
                StringSession(session_string.get_secret_value()),
                api_id,
                api_hash,
            )
        await client.connect()
        if not await client.is_user_authorized():
            msg = "Telethon session is not authorized; run relocate-helper-telegram-auth"
            raise RuntimeError(msg)
        return client

    async def _call(self, awaitable: Any) -> Any:
        try:
            return await awaitable
        except Exception as exc:
            from telethon.errors import FloodWaitError

            if isinstance(exc, FloodWaitError):
                raise TelegramFloodWaitError(int(exc.seconds)) from exc
            raise


def _convert_message(message: Any) -> TelegramMessage:
    text = message.message or message.text or ""
    edit_date = message.edit_date
    if edit_date is not None and edit_date.tzinfo is None:
        edit_date = edit_date.replace(tzinfo=UTC)
    message_date = message.date
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=UTC)

    reply_to = getattr(message, "reply_to", None)
    reply_id = getattr(reply_to, "reply_to_msg_id", None) if reply_to else None
    thread_id = getattr(reply_to, "forum_topic_id", None) if reply_to else None

    reactions = None
    message_reactions = getattr(message, "reactions", None)
    if message_reactions is not None:
        results = getattr(message_reactions, "results", None) or []
        reactions = {}
        for item in results:
            emoticon = getattr(getattr(item, "reaction", None), "emoticon", None)
            if emoticon:
                reactions[str(emoticon)] = int(getattr(item, "count", 0))

    links = tuple(_extract_links(message))
    media = tuple(_extract_media(message))
    return TelegramMessage(
        message_id=int(message.id),
        text=str(text),
        date=message_date,
        edit_date=edit_date,
        reply_to_message_id=reply_id,
        thread_id=thread_id,
        reactions=reactions,
        links=links,
        media=media,
    )


def _extract_links(message: Any) -> list[str]:
    entities = getattr(message, "entities", None) or []
    text = message.message or message.text or ""
    links: list[str] = []
    for entity in entities:
        cls_name = entity.__class__.__name__
        if cls_name == "MessageEntityUrl":
            offset = entity.offset
            length = entity.length
            links.append(text[offset : offset + length])
        elif cls_name == "MessageEntityTextUrl":
            url = getattr(entity, "url", None)
            if url:
                links.append(str(url))
    return links


def _extract_media(message: Any) -> list[TelegramMediaMeta]:
    media = getattr(message, "media", None)
    if media is None:
        return []
    cls_name = media.__class__.__name__
    if cls_name == "MessageMediaPhoto":
        return [TelegramMediaMeta(kind="photo")]
    if cls_name == "MessageMediaDocument":
        document = getattr(media, "document", None)
        mime_type = getattr(document, "mime_type", None) if document else None
        file_name = None
        for attr in getattr(document, "attributes", []) or []:
            if attr.__class__.__name__ == "DocumentAttributeFilename":
                file_name = getattr(attr, "file_name", None)
        size = getattr(document, "size", None) if document else None
        return [
            TelegramMediaMeta(
                kind="document",
                mime_type=mime_type,
                file_name=file_name,
                file_size=int(size) if size is not None else None,
            )
        ]
    return [TelegramMediaMeta(kind=cls_name.removeprefix("MessageMedia").lower())]


def create_telegram_adapter(settings: Settings) -> TelegramClientAdapter:
    return TelethonClientAdapter(settings)
