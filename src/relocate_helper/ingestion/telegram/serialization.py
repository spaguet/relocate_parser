"""Serialize Telegram messages for object storage."""

from __future__ import annotations

import json
from typing import Any

from relocate_helper.ingestion.telegram.adapter import TelegramMediaMeta, TelegramMessage


def message_to_bytes(message: TelegramMessage) -> bytes:
    payload = {
        "message_id": message.message_id,
        "text": message.text,
        "date": message.date.isoformat(),
        "edit_date": message.edit_date.isoformat() if message.edit_date else None,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def message_metadata(message: TelegramMessage) -> dict[str, Any]:
    media = [
        {
            "kind": item.kind,
            "mime_type": item.mime_type,
            "file_name": item.file_name,
            "file_size": item.file_size,
        }
        for item in message.media
    ]
    return {
        "telegram": {
            "message_id": message.message_id,
            "reply_to_message_id": message.reply_to_message_id,
            "thread_id": message.thread_id,
            "reactions": message.reactions,
            "links": list(message.links),
            "media": media,
            "text_length": len(message.text),
        }
    }


def media_from_dict(raw: dict[str, Any]) -> TelegramMediaMeta:
    return TelegramMediaMeta(
        kind=str(raw.get("kind", "unknown")),
        mime_type=raw.get("mime_type"),
        file_name=raw.get("file_name"),
        file_size=raw.get("file_size"),
    )
