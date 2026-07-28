"""Telegram message import orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relocate_helper.admin.sources import SourceRegistryService
from relocate_helper.common.config import Settings
from relocate_helper.common.logging import get_logger
from relocate_helper.db.enums import DocumentStatus, IngestionJobType, SourceStatus, SourceType
from relocate_helper.db.models.documents import Document
from relocate_helper.db.models.jobs import IngestionJob
from relocate_helper.db.models.sources import Source
from relocate_helper.ingestion.events import (
    DocumentChanged,
    DocumentCreated,
    DocumentDeleted,
    IngestionEvent,
)
from relocate_helper.ingestion.jobs import IngestionJobService
from relocate_helper.ingestion.telegram.adapter import TelegramClientAdapter, TelegramMessage
from relocate_helper.ingestion.telegram.cursor import TelegramSyncCursor
from relocate_helper.ingestion.telegram.exceptions import (
    TelegramFloodWaitError,
    TelegramJobCancelledError,
    TelegramSourceConfigError,
)
from relocate_helper.ingestion.telegram.logging_helpers import message_log_fields
from relocate_helper.ingestion.telegram.resolver import normalize_telegram_ref
from relocate_helper.ingestion.telegram.serialization import message_metadata, message_to_bytes
from relocate_helper.storage.document_service import DocumentStorageService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TelegramSyncRequest:
    source_id: int
    job_id: int
    job_type: IngestionJobType
    since: datetime | None = None
    until: datetime | None = None


@dataclass
class TelegramSyncResult:
    imported: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    events: list[IngestionEvent] = field(default_factory=list)
    cursor: TelegramSyncCursor | None = None
    completed: bool = False
    flood_wait_seconds: int | None = None


def build_job_idempotency_key(
    source_id: int,
    job_type: IngestionJobType,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> str:
    since_part = since.isoformat() if since else "none"
    until_part = until.isoformat() if until else "none"
    return f"telegram-sync:{source_id}:{job_type.value}:{since_part}:{until_part}"


def document_idempotency_key(source_id: int, message_id: int) -> str:
    return f"telegram:{source_id}:{message_id}"


class TelegramSyncService:
    """Import Telegram messages into document storage."""

    def __init__(
        self,
        *,
        settings: Settings,
        adapter: TelegramClientAdapter,
        document_service: DocumentStorageService,
        source_registry: SourceRegistryService,
        job_service: IngestionJobService,
    ) -> None:
        self._settings = settings
        self._adapter = adapter
        self._documents = document_service
        self._sources = source_registry
        self._jobs = job_service

    async def run(
        self,
        session: AsyncSession,
        request: TelegramSyncRequest,
    ) -> TelegramSyncResult:
        source = await self._sources.get_source(session, request.source_id)
        self._validate_source(source)

        job = await self._jobs.get_job(session, request.job_id)
        if job.status.value == "cancelled":
            raise TelegramJobCancelledError(f"Job {job.id} cancelled")

        await self._jobs.start_job(session, job)

        peer_ref = normalize_telegram_ref(source.external_ref or "")
        try:
            peer = await self._adapter.resolve_peer(peer_ref)
        except LookupError as exc:
            msg = f"Cannot resolve Telegram peer: {peer_ref}"
            raise TelegramSourceConfigError(msg) from exc

        cursor = TelegramSyncCursor.from_json(source.sync_cursor or job.cursor)
        if cursor is None:
            cursor = TelegramSyncCursor(
                peer_id=peer.peer_id,
                min_date=request.since,
                max_date=request.until,
            )
        elif cursor.peer_id != peer.peer_id:
            cursor = cursor.with_updates(peer_id=peer.peer_id)

        if request.job_type == IngestionJobType.INCREMENTAL_SYNC and cursor.last_message_id:
            window = self._settings.telegram_edit_check_window
            min_message_id = max(0, cursor.last_message_id - window)
            page_cursor = None
        else:
            min_message_id = None
            page_cursor = cursor.page_cursor

        result = TelegramSyncResult(cursor=cursor)
        page_size = self._settings.telegram_sync_page_size

        try:
            while True:
                if await self._jobs.is_cancelled(session, job.id):
                    raise TelegramJobCancelledError(f"Job {job.id} cancelled")

                page = await self._adapter.fetch_messages(
                    peer.peer_id,
                    min_date=cursor.min_date or request.since,
                    max_date=cursor.max_date or request.until,
                    min_message_id=min_message_id,
                    cursor=page_cursor,
                    limit=page_size,
                )

                for message in page.messages:
                    event = await self._upsert_message(session, source, message, result)
                    if event is not None:
                        result.events.append(event)
                    cursor = cursor.with_updates(
                        last_message_id=message.message_id,
                        tracked_min_message_id=min(
                            cursor.tracked_min_message_id or message.message_id,
                            message.message_id,
                        ),
                        tracked_max_message_id=max(
                            cursor.tracked_max_message_id or message.message_id,
                            message.message_id,
                        ),
                    )

                deleted_events = await self._detect_deletions(session, source, cursor)
                result.events.extend(deleted_events)
                result.deleted += len(deleted_events)

                cursor = cursor.with_updates(page_cursor=page.next_cursor)
                page_cursor = page.next_cursor
                await self._checkpoint(session, source, job, cursor, result)

                if not page.has_more:
                    result.completed = True
                    break

            if result.completed:
                source.last_synced_at = datetime.now(tz=UTC)
                await self._jobs.complete_job(session, job)
            return result

        except TelegramFloodWaitError as exc:
            result.flood_wait_seconds = exc.seconds
            await self._checkpoint(session, source, job, cursor, result)
            logger.warning(
                "telegram_flood_wait",
                source_id=source.id,
                job_id=job.id,
                wait_seconds=exc.seconds,
            )
            return result
        except Exception as exc:
            await self._jobs.fail_job(session, job, str(exc))
            raise

    async def _upsert_message(
        self,
        session: AsyncSession,
        source: Source,
        message: TelegramMessage,
        result: TelegramSyncResult,
    ) -> IngestionEvent | None:
        logger.info(
            "telegram_message_upsert",
            source_id=source.id,
            **message_log_fields(message_id=message.message_id, text=message.text),
        )

        external_id = str(message.message_id)
        idempotency = document_idempotency_key(source.id, message.message_id)
        document, created = await self._documents.get_or_create_document(
            session,
            source_id=source.id,
            external_id=external_id,
            idempotency_key=idempotency,
            city_id=source.city_id,
            metadata=message_metadata(message),
        )

        if document.status == DocumentStatus.DELETED_AT_SOURCE:
            document.status = DocumentStatus.ACTIVE

        payload = message_to_bytes(message)
        store_result = await self._documents.store_content(
            session,
            document,
            payload,
            filename="message.json",
            source_published_at=message.date,
            source_updated_at=message.edit_date or message.date,
            metadata=message_metadata(message),
        )

        if created:
            result.imported += 1
            return DocumentCreated(
                document_id=document.id,
                source_id=source.id,
                external_id=external_id,
            )
        if store_result.created_new_version:
            result.updated += 1
            assert store_result.version is not None
            return DocumentChanged(
                document_id=document.id,
                source_id=source.id,
                external_id=external_id,
                version_id=store_result.version.id,
            )

        result.skipped += 1
        return None

    async def _detect_deletions(
        self,
        session: AsyncSession,
        source: Source,
        cursor: TelegramSyncCursor,
    ) -> list[DocumentDeleted]:
        if cursor.tracked_min_message_id is None or cursor.tracked_max_message_id is None:
            return []

        live_ids = await self._adapter.list_message_ids(
            cursor.peer_id,
            min_message_id=cursor.tracked_min_message_id,
            max_message_id=cursor.tracked_max_message_id,
        )

        rows = await session.scalars(
            select(Document).where(
                Document.source_id == source.id,
                Document.status == DocumentStatus.ACTIVE,
                Document.external_id.in_(
                    [str(message_id) for message_id in range(
                        cursor.tracked_min_message_id,
                        cursor.tracked_max_message_id + 1,
                    )]
                ),
            )
        )

        events: list[DocumentDeleted] = []
        for document in rows:
            message_id = int(document.external_id)
            if message_id in live_ids:
                continue
            document.status = DocumentStatus.DELETED_AT_SOURCE
            events.append(
                DocumentDeleted(
                    document_id=document.id,
                    source_id=source.id,
                    external_id=document.external_id,
                )
            )
            logger.info(
                "telegram_message_deleted_at_source",
                source_id=source.id,
                message_id=message_id,
            )
        return events

    async def _checkpoint(
        self,
        session: AsyncSession,
        source: Source,
        job: IngestionJob,
        cursor: TelegramSyncCursor,
        result: TelegramSyncResult,
    ) -> None:
        cursor_json = cursor.to_json()
        source.sync_cursor = cursor_json
        progress: dict[str, Any] = {
            "imported": result.imported,
            "updated": result.updated,
            "deleted": result.deleted,
            "skipped": result.skipped,
            "events_count": len(result.events),
        }
        await self._jobs.update_progress(
            session,
            job,
            cursor=cursor_json,
            progress=progress,
        )

    def _validate_source(self, source: Source) -> None:
        if source.source_type != SourceType.TELEGRAM:
            msg = f"Source {source.id} is not a Telegram source"
            raise TelegramSourceConfigError(msg)
        if source.status not in (SourceStatus.ACTIVE, SourceStatus.PAUSED):
            msg = f"Source {source.id} is not active"
            raise TelegramSourceConfigError(msg)
        if not source.legal_basis:
            msg = f"Source {source.id} has no legal_basis"
            raise TelegramSourceConfigError(msg)
        if not source.external_ref:
            msg = f"Source {source.id} has no external_ref"
            raise TelegramSourceConfigError(msg)
