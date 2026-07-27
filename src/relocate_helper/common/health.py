"""Infrastructure health probes for readiness checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import asyncpg
import redis.asyncio as redis
from aiobotocore.session import get_session

from relocate_helper.common.config import Settings

CheckStatus = Literal["ok", "error", "skipped"]


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    name: str
    status: CheckStatus
    detail: str | None = None


async def check_postgres(settings: Settings) -> ComponentHealth:
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(settings.database_url),
            timeout=settings.health_check_timeout_seconds,
        )
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
        return ComponentHealth(name="postgresql", status="ok")
    except Exception as exc:  # noqa: BLE001 — health probe must not crash
        return ComponentHealth(name="postgresql", status="error", detail=str(exc))


async def check_redis(settings: Settings) -> ComponentHealth:
    client = redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        decode_responses=True,
    )
    try:
        pong = await asyncio.wait_for(
            client.ping(),
            timeout=settings.health_check_timeout_seconds,
        )
        if pong is True:
            return ComponentHealth(name="redis", status="ok")
        return ComponentHealth(name="redis", status="error", detail="unexpected ping response")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(name="redis", status="error", detail=str(exc))
    finally:
        await client.close()


async def check_s3(settings: Settings) -> ComponentHealth:
    session = get_session()
    try:
        async with session.create_client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
            use_ssl=settings.s3_use_ssl,
        ) as client:
            await asyncio.wait_for(
                client.head_bucket(Bucket=settings.s3_bucket),
                timeout=settings.health_check_timeout_seconds,
            )
        return ComponentHealth(name="s3", status="ok")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(name="s3", status="error", detail=str(exc))


async def gather_readiness(settings: Settings) -> list[ComponentHealth]:
    """Run all readiness probes concurrently."""
    results = await asyncio.gather(
        check_postgres(settings),
        check_redis(settings),
        check_s3(settings),
        return_exceptions=False,
    )
    return list(results)
