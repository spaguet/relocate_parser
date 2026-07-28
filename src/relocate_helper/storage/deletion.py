"""Physical content deletion with blob cleanup and tombstones."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from relocate_helper.db.enums import ChunkStatus, DocumentStatus, TombstoneEntityType
from relocate_helper.db.models.documents import Chunk, Document, DocumentVersion
from relocate_helper.db.repository import Database
from relocate_helper.storage.protocol import ObjectStorage


class ContentDeletionService:
    """Remove stored bytes, derived chunks and record audit trail."""

    def __init__(self, storage: ObjectStorage, database: Database) -> None:
        self._storage = storage
        self._database = database

    async def delete_document_content(
        self,
        session: AsyncSession,
        document: Document,
        *,
        reason: str,
        admin_user_id: int | None = None,
        delete_blobs: bool = True,
    ) -> None:
        """Delete S3 objects, mark chunks deleted, tombstone document."""
        versions = (
            await session.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == document.id)
            )
        ).all()

        storage_keys = {version.storage_key for version in versions if version.storage_key}
        if delete_blobs:
            for key in storage_keys:
                await self._storage.delete(key)

        version_ids = [version.id for version in versions]
        if version_ids:
            await session.execute(
                delete(Chunk).where(
                    Chunk.document_version_id.in_(version_ids),
                    Chunk.status != ChunkStatus.DELETED,
                )
            )

        document.status = DocumentStatus.REDACTED
        document.current_version_id = None
        await self._database.record_tombstone(
            session,
            entity_type=TombstoneEntityType.DOCUMENT,
            entity_id=str(document.id),
            reason=reason,
            source_id=document.source_id,
            metadata={
                "external_id": document.external_id,
                "storage_keys_deleted": sorted(storage_keys),
            },
        )
        await self._database.record_admin_audit(
            session,
            admin_user_id=admin_user_id,
            action="document_content_deleted",
            entity_type="document",
            entity_id=str(document.id),
            details={"reason": reason, "storage_keys": sorted(storage_keys)},
        )
