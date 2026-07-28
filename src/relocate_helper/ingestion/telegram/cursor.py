"""Checkpoint cursor encoding for Telegram sync."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TelegramSyncCursor:
    peer_id: int
    last_message_id: int | None = None
    page_cursor: str | None = None
    min_date: datetime | None = None
    max_date: datetime | None = None
    tracked_min_message_id: int | None = None
    tracked_max_message_id: int | None = None

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "peer_id": self.peer_id,
            "last_message_id": self.last_message_id,
            "page_cursor": self.page_cursor,
            "min_date": self.min_date.isoformat() if self.min_date else None,
            "max_date": self.max_date.isoformat() if self.max_date else None,
            "tracked_min_message_id": self.tracked_min_message_id,
            "tracked_max_message_id": self.tracked_max_message_id,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str | None) -> TelegramSyncCursor | None:
        if not raw:
            return None
        data = json.loads(raw)
        return cls(
            peer_id=int(data["peer_id"]),
            last_message_id=data.get("last_message_id"),
            page_cursor=data.get("page_cursor"),
            min_date=_parse_dt(data.get("min_date")),
            max_date=_parse_dt(data.get("max_date")),
            tracked_min_message_id=data.get("tracked_min_message_id"),
            tracked_max_message_id=data.get("tracked_max_message_id"),
        )

    def with_updates(self, **kwargs: Any) -> TelegramSyncCursor:
        current = asdict(self)
        current.update(kwargs)
        return TelegramSyncCursor(**current)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
