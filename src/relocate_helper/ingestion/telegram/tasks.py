"""RQ worker tasks for Telegram ingestion."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

from relocate_helper.admin.sources import SourceRegistryService
from relocate_helper.common.config import Settings, get_settings
from relocate_helper.common.logging import configure_logging, get_logger
from relocate_helper.db.enums import IngestionJobType
from relocate_helper.db.repository import Database
from relocate_helper.db.session import create_session_factory
from relocate_helper.ingestion.jobs import IngestionJobService
from relocate_helper.ingestion.telegram.adapter import FakeTelegramClient
from relocate_helper.ingestion.telegram.sync import TelegramSyncRequest, TelegramSyncService
from relocate_helper.storage.document_service import DocumentStorageService
from relocate_helper.storage.factory import create_object_storage
from relocate_helper.workers.queue import get_default_queue

logger = get_logger(__name__)


def run_telegram_sync_job(
    job_id: int,
    source_id: int,
    job_type: str,
    *,
    since_iso: str | None = None,
    until_iso: str | None = None,
    use_fake_adapter: bool = False,
    fake_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """RQ entrypoint — runs async sync in a fresh event loop."""
    configure_logging(log_level=get_settings().log_level, json_logs=get_settings().log_json)
    return asyncio.run(
        _run_telegram_sync_job_async(
            job_id=job_id,
            source_id=source_id,
            job_type=job_type,
            since_iso=since_iso,
            until_iso=until_iso,
            use_fake_adapter=use_fake_adapter,
            fake_state=fake_state,
        )
    )


async def _run_telegram_sync_job_async(
    *,
    job_id: int,
    source_id: int,
    job_type: str,
    since_iso: str | None,
    until_iso: str | None,
    use_fake_adapter: bool,
    fake_state: dict[str, Any] | None,
) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    database = Database(session_factory)
    storage = create_object_storage(settings)
    document_service = DocumentStorageService(storage, settings)
    source_registry = SourceRegistryService(database, settings)
    job_service = IngestionJobService()

    adapter = FakeTelegramClient() if use_fake_adapter else _create_production_adapter(settings)
    if use_fake_adapter and isinstance(adapter, FakeTelegramClient) and fake_state:
        _hydrate_fake(adapter, fake_state)

    sync_service = TelegramSyncService(
        settings=settings,
        adapter=adapter,
        document_service=document_service,
        source_registry=source_registry,
        job_service=job_service,
    )

    since = _parse_iso(since_iso)
    until = _parse_iso(until_iso)
    parsed_type = IngestionJobType(job_type)

    try:
        async with session_factory() as session, session.begin():
            result = await sync_service.run(
                session,
                TelegramSyncRequest(
                    source_id=source_id,
                    job_id=job_id,
                    job_type=parsed_type,
                    since=since,
                    until=until,
                ),
            )
    finally:
        await engine.dispose()

    if result.flood_wait_seconds is not None:
        queue = get_default_queue(settings)
        delay = min(result.flood_wait_seconds, settings.telegram_flood_wait_max_seconds)
        queue.enqueue_in(
            timedelta(seconds=delay),
            run_telegram_sync_job,
            job_id=job_id,
            source_id=source_id,
            job_type=job_type,
            since_iso=since_iso,
            until_iso=until_iso,
            use_fake_adapter=use_fake_adapter,
            fake_state=fake_state,
        )
        logger.info(
            "telegram_sync_requeued_after_flood_wait",
            job_id=job_id,
            source_id=source_id,
            delay_seconds=delay,
        )

    return {
        "completed": result.completed,
        "imported": result.imported,
        "updated": result.updated,
        "deleted": result.deleted,
        "skipped": result.skipped,
        "flood_wait_seconds": result.flood_wait_seconds,
        "events_count": len(result.events),
    }


def enqueue_telegram_sync(
    *,
    job_id: int,
    source_id: int,
    job_type: IngestionJobType,
    since_iso: str | None = None,
    until_iso: str | None = None,
    settings: Settings | None = None,
) -> str:
    queue = get_default_queue(settings)
    job = queue.enqueue(
        run_telegram_sync_job,
        job_id=job_id,
        source_id=source_id,
        job_type=job_type.value,
        since_iso=since_iso,
        until_iso=until_iso,
        job_timeout=3600,
    )
    return str(job.id)


def _parse_iso(value: str | None) -> Any:
    if value is None:
        return None
    from datetime import datetime

    return datetime.fromisoformat(value)


def _hydrate_fake(adapter: FakeTelegramClient, state: dict[str, Any]) -> None:
    from relocate_helper.ingestion.telegram.adapter import (
        TelegramMediaMeta,
        TelegramMessage,
        TelegramPeer,
    )

    for ref, peer_data in state.get("peers", {}).items():
        peer = TelegramPeer(
            peer_id=int(peer_data["peer_id"]),
            username=peer_data.get("username"),
            title=str(peer_data.get("title", ref)),
        )
        adapter.register_peer(ref, peer)

    for peer_id_str, messages in state.get("messages", {}).items():
        peer_id = int(peer_id_str)
        converted: list[TelegramMessage] = []
        for item in messages:
            media = tuple(
                TelegramMediaMeta(**media_item) for media_item in item.get("media", [])
            )
            converted.append(
                TelegramMessage(
                    message_id=int(item["message_id"]),
                    text=str(item["text"]),
                    date=_parse_iso(item["date"]),
                    edit_date=_parse_iso(item.get("edit_date")),
                    reply_to_message_id=item.get("reply_to_message_id"),
                    thread_id=item.get("thread_id"),
                    reactions=item.get("reactions"),
                    links=tuple(item.get("links", [])),
                    media=media,
                )
            )
        adapter.set_messages(peer_id, converted)

    if state.get("flood_wait_on_call") is not None:
        adapter.flood_wait_on_call = int(state["flood_wait_on_call"])
    if state.get("fail_after_messages") is not None:
        adapter.fail_after_messages = int(state["fail_after_messages"])


def _create_production_adapter(settings: Settings) -> Any:
    from relocate_helper.ingestion.telegram.telethon_client import create_telegram_adapter

    return create_telegram_adapter(settings)
