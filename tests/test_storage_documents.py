"""Document storage service tests (DB + in-memory storage)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from relocate_helper.common.config import AppEnv, Settings
from relocate_helper.db.enums import DocumentStatus, SourceStatus, SourceType
from relocate_helper.db.models.documents import Document
from relocate_helper.db.models.geo import City
from relocate_helper.db.models.sources import Source
from relocate_helper.db.repository import Database
from relocate_helper.storage.deletion import ContentDeletionService
from relocate_helper.storage.document_service import DocumentStorageService
from relocate_helper.storage.exceptions import ObjectTooLargeError
from relocate_helper.storage.memory import InMemoryObjectStorage

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://relocate:relocate@localhost:5432/relocate_helper_test",
)


def _async_database_url(sync_url: str) -> str:
    if sync_url.startswith("postgresql+asyncpg://"):
        return sync_url
    if sync_url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + sync_url.removeprefix("postgresql://")
    return sync_url


async def _postgres_available(url: str) -> bool:
    try:
        conn = await asyncio.wait_for(asyncpg.connect(url), timeout=3.0)
    except Exception:
        return False
    await conn.close()
    return True


@pytest.fixture(scope="module")
def database_url() -> str:
    return DEFAULT_DATABASE_URL


@pytest.fixture(scope="module")
def alembic_config(database_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _async_database_url(database_url))
    return cfg


@pytest.fixture(scope="module")
def migrated_db(database_url: str, alembic_config: Config) -> str:
    if not asyncio.run(_postgres_available(database_url)):
        pytest.skip("PostgreSQL is not available for document storage tests")
    command.upgrade(alembic_config, "head")
    return database_url


@pytest.fixture
async def session(migrated_db: str) -> AsyncSession:
    engine = create_async_engine(_async_database_url(migrated_db))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(app_env=AppEnv.TEST, max_upload_bytes=1024)


@pytest.fixture
def memory_storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()


@pytest.fixture
def doc_service(
    memory_storage: InMemoryObjectStorage, test_settings: Settings
) -> DocumentStorageService:
    return DocumentStorageService(memory_storage, test_settings)


async def _create_source(session: AsyncSession) -> Source:
    city = await session.get(City, 1)
    assert city is not None
    source = Source(
        source_type=SourceType.FILE,
        name="Upload test",
        city_id=city.id,
        status=SourceStatus.ACTIVE,
    )
    session.add(source)
    await session.flush()
    return source


@pytest.mark.asyncio
async def test_store_content_creates_version(
    session: AsyncSession,
    doc_service: DocumentStorageService,
) -> None:
    source = await _create_source(session)
    document, created = await doc_service.get_or_create_document(
        session,
        source_id=source.id,
        external_id="file-1",
        idempotency_key="upload:file-1",
    )
    assert created is True

    result = await doc_service.store_content(session, document, b"hello world", filename="a.txt")
    await session.commit()

    assert result.created_new_version is True
    assert result.version is not None
    assert result.version.content_hash
    assert result.version.storage_key is not None
    assert document.status == DocumentStatus.ACTIVE


@pytest.mark.asyncio
async def test_store_content_deduplicates_unchanged(
    session: AsyncSession,
    doc_service: DocumentStorageService,
    memory_storage: InMemoryObjectStorage,
) -> None:
    source = await _create_source(session)
    document, _ = await doc_service.get_or_create_document(
        session,
        source_id=source.id,
        external_id="file-2",
        idempotency_key="upload:file-2",
    )
    first = await doc_service.store_content(session, document, b"same body", filename="a.txt")
    second = await doc_service.store_content(session, document, b"same body", filename="a.txt")
    await session.commit()

    assert first.created_new_version is True
    assert second.created_new_version is False
    assert memory_storage.put_calls == 1


@pytest.mark.asyncio
async def test_store_content_new_version_on_change(
    session: AsyncSession,
    doc_service: DocumentStorageService,
) -> None:
    source = await _create_source(session)
    document, _ = await doc_service.get_or_create_document(
        session,
        source_id=source.id,
        external_id="file-3",
        idempotency_key="upload:file-3",
    )
    await doc_service.store_content(session, document, b"v1", filename="a.txt")
    result = await doc_service.store_content(session, document, b"v2", filename="a.txt")
    await session.commit()

    assert result.created_new_version is True
    assert result.version is not None
    assert result.version.version_number == 2


@pytest.mark.asyncio
async def test_store_content_quarantines_html(
    session: AsyncSession,
    doc_service: DocumentStorageService,
) -> None:
    source = await _create_source(session)
    document, _ = await doc_service.get_or_create_document(
        session,
        source_id=source.id,
        external_id="file-4",
        idempotency_key="upload:file-4",
    )
    result = await doc_service.store_content(
        session,
        document,
        b"<html><body>x</body></html>",
        filename="page.html",
    )
    await session.commit()

    assert result.quarantined is True
    assert document.status == DocumentStatus.QUARANTINED
    assert result.version is not None
    assert "quarantine" in (result.version.storage_key or "")


@pytest.mark.asyncio
async def test_store_content_rejects_oversized(
    session: AsyncSession,
    doc_service: DocumentStorageService,
) -> None:
    source = await _create_source(session)
    document, _ = await doc_service.get_or_create_document(
        session,
        source_id=source.id,
        external_id="file-5",
        idempotency_key="upload:file-5",
    )
    with pytest.raises(ObjectTooLargeError):
        await doc_service.store_content(session, document, b"x" * 2048, filename="big.txt")


@pytest.mark.asyncio
async def test_delete_document_content_removes_blobs(
    session: AsyncSession,
    doc_service: DocumentStorageService,
    memory_storage: InMemoryObjectStorage,
    migrated_db: str,
) -> None:
    source = await _create_source(session)
    document, _ = await doc_service.get_or_create_document(
        session,
        source_id=source.id,
        external_id="file-6",
        idempotency_key="upload:file-6",
    )
    result = await doc_service.store_content(session, document, b"delete me", filename="a.txt")
    await session.commit()
    storage_key = result.version.storage_key
    assert storage_key is not None
    assert await memory_storage.exists(storage_key)

    engine = create_async_engine(_async_database_url(migrated_db))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    db = Database(factory)
    deletion = ContentDeletionService(memory_storage, db)

    async with factory() as tx:
        doc = await tx.get(Document, document.id)
        assert doc is not None
        await deletion.delete_document_content(tx, doc, reason="test_cleanup")
        await tx.commit()

    assert memory_storage.delete_calls >= 1
    assert not await memory_storage.exists(storage_key)

    async with factory() as tx:
        doc = await tx.get(Document, document.id)
        assert doc is not None
        assert doc.status == DocumentStatus.REDACTED
    await engine.dispose()
