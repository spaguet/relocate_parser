"""Background task queue (RQ) configuration."""

from __future__ import annotations

from redis import Redis
from rq import Queue

from relocate_helper.common.config import Settings, get_settings


def get_redis_connection(settings: Settings | None = None) -> Redis[bytes]:
    resolved = settings or get_settings()
    return Redis.from_url(resolved.redis_url)


def get_default_queue(settings: Settings | None = None) -> Queue:
    resolved = settings or get_settings()
    return Queue(
        name=resolved.rq_default_queue,
        connection=get_redis_connection(resolved),
        default_timeout=600,
    )
