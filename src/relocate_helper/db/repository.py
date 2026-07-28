"""Transactional database access layer."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relocate_helper.db.enums import TombstoneEntityType
from relocate_helper.db.models.admin import AdminAuditLog, Tombstone
from relocate_helper.db.models.documents import Document
from relocate_helper.db.types import JsonDict

T = TypeVar("T")


class Database:
    """Application database gateway with explicit transaction boundaries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def run_in_transaction(
        self,
        callback: Callable[[AsyncSession], Awaitable[T]],
    ) -> T:
        async with self.transaction() as session:
            return await callback(session)

    async def record_tombstone(
        self,
        session: AsyncSession,
        *,
        entity_type: TombstoneEntityType,
        entity_id: str,
        reason: str,
        source_id: int | None = None,
        metadata: JsonDict | None = None,
    ) -> Tombstone:
        tombstone = Tombstone(
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            source_id=source_id,
            metadata_=metadata,
        )
        session.add(tombstone)
        await session.flush()
        return tombstone

    async def record_admin_audit(
        self,
        session: AsyncSession,
        *,
        admin_user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: str,
        details: JsonDict | None = None,
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def mark_document_deleted(
        self,
        session: AsyncSession,
        document: Document,
        *,
        reason: str,
        admin_user_id: int | None = None,
    ) -> Tombstone:
        """Physical content removal path: tombstone + audit, document status update."""
        from relocate_helper.db.enums import DocumentStatus, TombstoneEntityType

        document.status = DocumentStatus.REDACTED
        tombstone = await self.record_tombstone(
            session,
            entity_type=TombstoneEntityType.DOCUMENT,
            entity_id=str(document.id),
            reason=reason,
            source_id=document.source_id,
            metadata={"external_id": document.external_id},
        )
        await self.record_admin_audit(
            session,
            admin_user_id=admin_user_id,
            action="document_content_deleted",
            entity_type="document",
            entity_id=str(document.id),
            details={"reason": reason, "tombstone_id": tombstone.id},
        )
        return tombstone
