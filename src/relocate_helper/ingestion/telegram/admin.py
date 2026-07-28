"""Admin operations for Telegram sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from relocate_helper.admin.sources import SourceNotFoundError, SourceRegistryService
from relocate_helper.db.enums import IngestionJobType, SourceType
from relocate_helper.ingestion.jobs import (
    IngestionJobConflictError,
    IngestionJobCreateInput,
    IngestionJobService,
)
from relocate_helper.ingestion.telegram.exceptions import TelegramSourceConfigError
from relocate_helper.ingestion.telegram.sync import build_job_idempotency_key
from relocate_helper.ingestion.telegram.tasks import enqueue_telegram_sync


@dataclass(frozen=True, slots=True)
class TelegramSyncEnqueueResult:
    job_id: int
    rq_job_id: str
    idempotency_key: str
    created: bool


class TelegramIngestionAdminService:
    """Create ingestion jobs and enqueue Telegram sync worker tasks."""

    def __init__(
        self,
        source_registry: SourceRegistryService,
        job_service: IngestionJobService,
    ) -> None:
        self._sources = source_registry
        self._jobs = job_service

    async def enqueue_sync(
        self,
        session: AsyncSession,
        *,
        source_id: int,
        job_type: IngestionJobType,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> TelegramSyncEnqueueResult:
        source = await self._sources.get_source(session, source_id)
        if source.source_type != SourceType.TELEGRAM:
            msg = f"Source {source_id} is not Telegram"
            raise TelegramSourceConfigError(msg)
        if not source.external_ref:
            msg = f"Source {source_id} has no external_ref"
            raise TelegramSourceConfigError(msg)
        if not source.legal_basis:
            msg = f"Source {source_id} requires legal_basis before import"
            raise TelegramSourceConfigError(msg)

        active = await self._jobs.get_active_job_for_source(session, source_id)
        if active is not None:
            msg = f"Source {source_id} already has active job {active.id}"
            raise IngestionJobConflictError(msg)

        idempotency_key = build_job_idempotency_key(
            source_id,
            job_type,
            since=since,
            until=until,
        )
        existing = await self._jobs.get_by_idempotency_key(session, idempotency_key)
        if existing is not None and existing.status.value in {"pending", "running", "completed"}:
            rq_job_id = ""
            if existing.metadata_:
                rq_job_id = str(existing.metadata_.get("rq_job_id", ""))
            return TelegramSyncEnqueueResult(
                job_id=existing.id,
                rq_job_id=rq_job_id,
                idempotency_key=idempotency_key,
                created=False,
            )

        job = await self._jobs.create_job(
            session,
            IngestionJobCreateInput(
                source_id=source_id,
                job_type=job_type,
                idempotency_key=idempotency_key,
                cursor=source.sync_cursor,
                metadata={
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                },
            ),
            allow_existing=True,
        )

        rq_job_id = enqueue_telegram_sync(
            job_id=job.id,
            source_id=source_id,
            job_type=job_type,
            since_iso=since.isoformat() if since else None,
            until_iso=until.isoformat() if until else None,
        )
        job.metadata_ = {**(job.metadata_ or {}), "rq_job_id": rq_job_id}
        await session.flush()

        return TelegramSyncEnqueueResult(
            job_id=job.id,
            rq_job_id=rq_job_id,
            idempotency_key=idempotency_key,
            created=True,
        )


__all__ = [
    "SourceNotFoundError",
    "TelegramIngestionAdminService",
    "TelegramSyncEnqueueResult",
]
