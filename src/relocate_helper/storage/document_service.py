"""Document version storage with content deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from relocate_helper.db.enums import DocumentStatus
from relocate_helper.db.models.documents import Document, DocumentVersion
from relocate_helper.storage.exceptions import ObjectTooLargeError
from relocate_helper.storage.hashing import sha256_digest
from relocate_helper.storage.keys import object_key, quarantine_key
from relocate_helper.storage.mime import MimeValidationResult, validate_content
from relocate_helper.storage.protocol import ObjectStorage

if TYPE_CHECKING:
    from relocate_helper.common.config import Settings


@dataclass(frozen=True, slots=True)
class StoreContentResult:
    document: Document
    version: DocumentVersion | None
    created_new_version: bool
    deduplicated_storage: bool
    quarantined: bool


class DocumentStorageService:
    """Persist raw document bytes and manage version rows."""

    def __init__(self, storage: ObjectStorage, settings: Settings) -> None:
        self._storage = storage
        self._settings = settings

    def _ensure_size(self, size_bytes: int) -> None:
        if size_bytes > self._settings.max_upload_bytes:
            raise ObjectTooLargeError(
                f"Content size {size_bytes} exceeds limit {self._settings.max_upload_bytes}"
            )

    async def store_content(
        self,
        session: AsyncSession,
        document: Document,
        data: bytes,
        *,
        filename: str | None = None,
        source_published_at: datetime | None = None,
        source_updated_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
        force_quarantine: bool = False,
    ) -> StoreContentResult:
        """Create a new document version when content changed; deduplicate blob storage."""
        self._ensure_size(len(data))
        digest = sha256_digest(data)
        mime_result = validate_content(
            data,
            filename=filename,
            allowed_mime_types=self._settings.allowed_mime_types_set,
        )
        quarantined = force_quarantine or mime_result.quarantined

        current = document.current_version
        if current is not None and current.content_hash == digest.hex_digest and not quarantined:
            return StoreContentResult(
                document=document,
                version=current,
                created_new_version=False,
                deduplicated_storage=True,
                quarantined=False,
            )

        prefix = self._settings.storage_key_prefix
        key = (
            quarantine_key(prefix, digest.hex_digest)
            if quarantined
            else object_key(prefix, digest.hex_digest)
        )

        deduplicated_storage = await self._storage.exists(key)
        if not deduplicated_storage:
            await self._storage.put(
                key,
                data,
                mime_type=mime_result.mime_type,
                content_hash=digest.hex_digest,
                server_side_encryption=self._settings.s3_server_side_encryption,
            )

        if quarantined:
            document.status = DocumentStatus.QUARANTINED
            version = await self._create_version(
                session,
                document,
                digest.hex_digest,
                key,
                mime_result,
                digest.size_bytes,
                source_published_at,
                source_updated_at,
                metadata,
            )
            return StoreContentResult(
                document=document,
                version=version,
                created_new_version=True,
                deduplicated_storage=deduplicated_storage,
                quarantined=True,
            )

        if current is not None and current.content_hash == digest.hex_digest:
            return StoreContentResult(
                document=document,
                version=current,
                created_new_version=False,
                deduplicated_storage=deduplicated_storage,
                quarantined=False,
            )

        document.status = DocumentStatus.ACTIVE
        version = await self._create_version(
            session,
            document,
            digest.hex_digest,
            key,
            mime_result,
            digest.size_bytes,
            source_published_at,
            source_updated_at,
            metadata,
        )
        document.current_version_id = version.id
        return StoreContentResult(
            document=document,
            version=version,
            created_new_version=True,
            deduplicated_storage=deduplicated_storage,
            quarantined=False,
        )

    async def _create_version(
        self,
        session: AsyncSession,
        document: Document,
        content_hash: str,
        storage_key: str,
        mime_result: MimeValidationResult,
        size_bytes: int,
        source_published_at: datetime | None,
        source_updated_at: datetime | None,
        metadata: dict[str, object] | None,
    ) -> DocumentVersion:
        next_number = await session.scalar(
            select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                DocumentVersion.document_id == document.id
            )
        )
        version = DocumentVersion(
            document_id=document.id,
            version_number=int(next_number or 0) + 1,
            content_hash=content_hash,
            storage_key=storage_key,
            mime_type=mime_result.mime_type,
            size_bytes=size_bytes,
            source_published_at=source_published_at,
            source_updated_at=source_updated_at or datetime.now(tz=UTC),
            metadata_=metadata,
        )
        session.add(version)
        await session.flush()
        return version

    async def get_or_create_document(
        self,
        session: AsyncSession,
        *,
        source_id: int,
        external_id: str,
        idempotency_key: str,
        city_id: int | None = None,
        language: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[Document, bool]:
        """Return existing document by idempotency key or create a new row."""
        existing = await session.scalar(
            select(Document).where(Document.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False

        document = Document(
            source_id=source_id,
            external_id=external_id,
            idempotency_key=idempotency_key,
            city_id=city_id,
            language=language,
            metadata_=metadata,
        )
        session.add(document)
        await session.flush()
        return document, True
