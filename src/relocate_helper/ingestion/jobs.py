"""Ingestion job lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relocate_helper.db.enums import IngestionJobStatus, IngestionJobType
from relocate_helper.db.models.jobs import IngestionJob


class IngestionJobNotFoundError(LookupError):
    pass


class IngestionJobConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IngestionJobCreateInput:
    source_id: int
    job_type: IngestionJobType
    idempotency_key: str
    cursor: str | None = None
    metadata: dict[str, Any] | None = None


class IngestionJobService:
    """Create and update ingestion job rows with idempotent enqueue semantics."""

    async def get_job(self, session: AsyncSession, job_id: int) -> IngestionJob:
        job = await session.get(IngestionJob, job_id)
        if job is None:
            raise IngestionJobNotFoundError(f"Ingestion job {job_id} not found")
        return job

    async def get_by_idempotency_key(
        self,
        session: AsyncSession,
        idempotency_key: str,
    ) -> IngestionJob | None:
        return cast(IngestionJob | None, await session.scalar(
            select(IngestionJob).where(IngestionJob.idempotency_key == idempotency_key)
        ))

    async def get_active_job_for_source(
        self,
        session: AsyncSession,
        source_id: int,
    ) -> IngestionJob | None:
        return cast(
            IngestionJob | None,
            await session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.source_id == source_id,
                    IngestionJob.status.in_(
                        (IngestionJobStatus.PENDING, IngestionJobStatus.RUNNING)
                    ),
                )
                .order_by(IngestionJob.id.desc())
                .limit(1)
            ),
        )

    async def create_job(
        self,
        session: AsyncSession,
        payload: IngestionJobCreateInput,
        *,
        allow_existing: bool = False,
    ) -> IngestionJob:
        existing = await self.get_by_idempotency_key(session, payload.idempotency_key)
        if existing is not None:
            if allow_existing:
                return existing
            msg = f"Ingestion job already exists: {payload.idempotency_key}"
            raise IngestionJobConflictError(msg)

        job = IngestionJob(
            source_id=payload.source_id,
            job_type=payload.job_type,
            idempotency_key=payload.idempotency_key,
            status=IngestionJobStatus.PENDING,
            cursor=payload.cursor,
            metadata_=payload.metadata,
        )
        session.add(job)
        await session.flush()
        return job

    async def start_job(self, session: AsyncSession, job: IngestionJob) -> IngestionJob:
        if job.status == IngestionJobStatus.CANCELLED:
            msg = f"Job {job.id} is cancelled"
            raise IngestionJobConflictError(msg)
        job.status = IngestionJobStatus.RUNNING
        job.started_at = datetime.now(tz=UTC)
        job.error_message = None
        await session.flush()
        return job

    async def update_progress(
        self,
        session: AsyncSession,
        job: IngestionJob,
        *,
        cursor: str | None = None,
        progress: dict[str, Any] | None = None,
    ) -> IngestionJob:
        if cursor is not None:
            job.cursor = cursor
        if progress is not None:
            job.progress = progress
        await session.flush()
        return job

    async def complete_job(self, session: AsyncSession, job: IngestionJob) -> IngestionJob:
        job.status = IngestionJobStatus.COMPLETED
        job.finished_at = datetime.now(tz=UTC)
        await session.flush()
        return job

    async def fail_job(
        self,
        session: AsyncSession,
        job: IngestionJob,
        error_message: str,
    ) -> IngestionJob:
        job.status = IngestionJobStatus.FAILED
        job.error_message = error_message[:4000]
        job.finished_at = datetime.now(tz=UTC)
        await session.flush()
        return job

    async def cancel_job(self, session: AsyncSession, job: IngestionJob) -> IngestionJob:
        job.status = IngestionJobStatus.CANCELLED
        job.finished_at = datetime.now(tz=UTC)
        await session.flush()
        return job

    async def is_cancelled(self, session: AsyncSession, job_id: int) -> bool:
        job = await self.get_job(session, job_id)
        return job.status == IngestionJobStatus.CANCELLED
