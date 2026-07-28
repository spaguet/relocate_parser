"""Telegram sync integration tests with fake adapter and PostgreSQL."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from relocate_helper.admin.sources import SourceCreateInput, SourceRegistryService
from relocate_helper.common.config import AppEnv, Settings, reset_settings_cache
from relocate_helper.db.enums import (
    DocumentStatus,
    IngestionJobStatus,
    IngestionJobType,
    SourceType,
)
from relocate_helper.db.models.documents import Document
from relocate_helper.db.models.jobs import IngestionJob
from relocate_helper.db.repository import Database
from relocate_helper.ingestion.events import DocumentChanged, DocumentCreated, DocumentDeleted
from relocate_helper.ingestion.jobs import IngestionJobCreateInput, IngestionJobService
from relocate_helper.ingestion.telegram.adapter import (
    FakeTelegramClient,
    TelegramMessage,
    TelegramPeer,
)
from relocate_helper.ingestion.telegram.sync import TelegramSyncRequest, TelegramSyncService
from relocate_helper.ingestion.telegram.tasks import run_telegram_sync_job
from relocate_helper.storage.document_service import DocumentStorageService
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
        pytest.skip("PostgreSQL is not available for Telegram sync tests")
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
    return Settings(app_env=AppEnv.TEST, telegram_sync_page_size=2)


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    reset_settings_cache()


@pytest.fixture
def fake_client() -> FakeTelegramClient:
    client = FakeTelegramClient()
    peer = TelegramPeer(peer_id=501, username="floripa_chat", title="Floripa Chat")
    client.register_peer("@floripa_chat", peer)
    client.set_messages(
        501,
        [
            TelegramMessage(
                message_id=1,
                text="Rent is 2500 BRL",
                date=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            TelegramMessage(
                message_id=2,
                text="Rent is 2600 BRL",
                date=datetime(2026, 1, 2, tzinfo=UTC),
            ),
            TelegramMessage(
                message_id=3,
                text="Updated rent info",
                date=datetime(2026, 1, 3, tzinfo=UTC),
            ),
        ],
    )
    return client


@pytest.fixture
async def telegram_source(session: AsyncSession, test_settings: Settings):
    database = Database(async_sessionmaker(bind=session.bind))
    registry = SourceRegistryService(database, test_settings)
    async with session.begin():
        source = await registry.create_source(
            session,
            SourceCreateInput(
                source_type=SourceType.TELEGRAM,
                name="Floripa chat",
                legal_basis="Owner authorized import for testing",
                city_id=1,
                external_ref="@floripa_chat",
            ),
        )
    await session.refresh(source)
    return source


def _sync_service(
    session: AsyncSession,
    fake_client: FakeTelegramClient,
    test_settings: Settings,
) -> TelegramSyncService:
    database = Database(async_sessionmaker(bind=session.bind))
    registry = SourceRegistryService(database, test_settings)
    documents = DocumentStorageService(InMemoryObjectStorage(), test_settings)
    jobs = IngestionJobService()
    return TelegramSyncService(
        settings=test_settings,
        adapter=fake_client,
        document_service=documents,
        source_registry=registry,
        job_service=jobs,
    )


async def _create_job(
    session: AsyncSession,
    source_id: int,
    *,
    job_type: IngestionJobType = IngestionJobType.INITIAL_IMPORT,
) -> IngestionJob:
    jobs = IngestionJobService()
    async with session.begin():
        job = await jobs.create_job(
            session,
            IngestionJobCreateInput(
                source_id=source_id,
                job_type=job_type,
                idempotency_key=f"test-job-{source_id}-{job_type.value}",
            ),
        )
    await session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_initial_import_creates_documents(
    session: AsyncSession,
    telegram_source,
    fake_client: FakeTelegramClient,
    test_settings: Settings,
) -> None:
    job = await _create_job(session, telegram_source.id)
    service = _sync_service(session, fake_client, test_settings)

    async with session.begin():
        result = await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job.id,
                job_type=IngestionJobType.INITIAL_IMPORT,
            ),
        )

    assert result.completed is True
    assert result.imported == 3
    assert len(result.events) == 3
    assert all(isinstance(event, DocumentCreated) for event in result.events)

    documents = list(
        await session.scalars(select(Document).where(Document.source_id == telegram_source.id))
    )
    assert len(documents) == 3


@pytest.mark.asyncio
async def test_idempotent_rerun_skips_unchanged(
    session: AsyncSession,
    telegram_source,
    fake_client: FakeTelegramClient,
    test_settings: Settings,
) -> None:
    job1 = await _create_job(session, telegram_source.id)
    service = _sync_service(session, fake_client, test_settings)
    async with session.begin():
        first = await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job1.id,
                job_type=IngestionJobType.INITIAL_IMPORT,
            ),
        )

    job2 = await _create_job(
        session,
        telegram_source.id,
        job_type=IngestionJobType.INCREMENTAL_SYNC,
    )
    async with session.begin():
        second = await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job2.id,
                job_type=IngestionJobType.INCREMENTAL_SYNC,
            ),
        )

    assert first.imported == 3
    assert second.imported == 0
    assert second.skipped >= 3


@pytest.mark.asyncio
async def test_edit_creates_new_version(
    session: AsyncSession,
    telegram_source,
    fake_client: FakeTelegramClient,
    test_settings: Settings,
) -> None:
    job1 = await _create_job(session, telegram_source.id)
    service = _sync_service(session, fake_client, test_settings)
    async with session.begin():
        await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job1.id,
                job_type=IngestionJobType.INITIAL_IMPORT,
            ),
        )

    fake_client.set_messages(
        501,
        [
            TelegramMessage(
                message_id=1,
                text="Rent is 2500 BRL",
                date=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            TelegramMessage(
                message_id=2,
                text="Rent is 2700 BRL edited",
                date=datetime(2026, 1, 2, tzinfo=UTC),
                edit_date=datetime(2026, 1, 5, tzinfo=UTC),
            ),
            TelegramMessage(
                message_id=3,
                text="Updated rent info",
                date=datetime(2026, 1, 3, tzinfo=UTC),
            ),
        ],
    )

    job2 = await _create_job(
        session,
        telegram_source.id,
        job_type=IngestionJobType.INCREMENTAL_SYNC,
    )
    async with session.begin():
        result = await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job2.id,
                job_type=IngestionJobType.INCREMENTAL_SYNC,
            ),
        )

    changed = [event for event in result.events if isinstance(event, DocumentChanged)]
    assert len(changed) == 1
    assert changed[0].external_id == "2"


@pytest.mark.asyncio
async def test_delete_detection(
    session: AsyncSession,
    telegram_source,
    fake_client: FakeTelegramClient,
    test_settings: Settings,
) -> None:
    job1 = await _create_job(session, telegram_source.id)
    service = _sync_service(session, fake_client, test_settings)
    async with session.begin():
        await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job1.id,
                job_type=IngestionJobType.INITIAL_IMPORT,
            ),
        )

    fake_client.set_messages(
        501,
        [
            TelegramMessage(
                message_id=1,
                text="Rent is 2500 BRL",
                date=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            TelegramMessage(
                message_id=3,
                text="Updated rent info",
                date=datetime(2026, 1, 3, tzinfo=UTC),
            ),
        ],
    )

    job2 = await _create_job(
        session,
        telegram_source.id,
        job_type=IngestionJobType.INCREMENTAL_SYNC,
    )
    async with session.begin():
        result = await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job2.id,
                job_type=IngestionJobType.INCREMENTAL_SYNC,
            ),
        )

    deleted = [event for event in result.events if isinstance(event, DocumentDeleted)]
    assert len(deleted) == 1
    assert deleted[0].external_id == "2"

    document = await session.scalar(
        select(Document).where(
            Document.source_id == telegram_source.id,
            Document.external_id == "2",
        )
    )
    assert document is not None
    assert document.status == DocumentStatus.DELETED_AT_SOURCE


@pytest.mark.asyncio
async def test_checkpoint_resume_after_mid_page_failure(
    session: AsyncSession,
    telegram_source,
    fake_client: FakeTelegramClient,
    test_settings: Settings,
) -> None:
    fake_client.fail_after_messages = 1
    job1 = await _create_job(session, telegram_source.id)
    service = _sync_service(session, fake_client, test_settings)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        async with session.begin():
            await service.run(
                session,
                TelegramSyncRequest(
                    source_id=telegram_source.id,
                    job_id=job1.id,
                    job_type=IngestionJobType.INITIAL_IMPORT,
                ),
            )

    await session.refresh(telegram_source)
    assert telegram_source.sync_cursor is not None

    fake_client.fail_after_messages = None
    fake_client.call_count = 0
    job2 = await _create_job(
        session,
        telegram_source.id,
        job_type=IngestionJobType.INCREMENTAL_SYNC,
    )
    async with session.begin():
        result = await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job2.id,
                job_type=IngestionJobType.INCREMENTAL_SYNC,
            ),
        )

    assert result.completed is True
    documents = list(
        await session.scalars(select(Document).where(Document.source_id == telegram_source.id))
    )
    assert len(documents) == 3


@pytest.mark.asyncio
async def test_flood_wait_returns_without_blocking(
    session: AsyncSession,
    telegram_source,
    fake_client: FakeTelegramClient,
    test_settings: Settings,
) -> None:
    fake_client.flood_wait_on_call = 15
    job = await _create_job(session, telegram_source.id)
    service = _sync_service(session, fake_client, test_settings)

    async with session.begin():
        result = await service.run(
            session,
            TelegramSyncRequest(
                source_id=telegram_source.id,
                job_id=job.id,
                job_type=IngestionJobType.INITIAL_IMPORT,
            ),
        )

    assert result.flood_wait_seconds == 15
    assert result.completed is False

    refreshed_job = await session.get(IngestionJob, job.id)
    assert refreshed_job is not None
    assert refreshed_job.status == IngestionJobStatus.RUNNING


@pytest.mark.asyncio
async def test_rq_task_with_fake_adapter(
    session: AsyncSession,
    telegram_source,
    test_settings: Settings,
) -> None:
    jobs = IngestionJobService()
    async with session.begin():
        job = await jobs.create_job(
            session,
            IngestionJobCreateInput(
                source_id=telegram_source.id,
                job_type=IngestionJobType.INITIAL_IMPORT,
                idempotency_key="rq-task-test",
            ),
        )
    await session.commit()

    fake_state = {
        "peers": {
            "@floripa_chat": {
                "peer_id": 501,
                "username": "floripa_chat",
                "title": "Floripa Chat",
            }
        },
        "messages": {
            "501": [
                {
                    "message_id": 10,
                    "text": "hello",
                    "date": "2026-01-01T00:00:00+00:00",
                }
            ]
        },
    }

    with patch("relocate_helper.ingestion.telegram.tasks.get_settings", return_value=test_settings):
        payload = run_telegram_sync_job(
            job_id=job.id,
            source_id=telegram_source.id,
            job_type=IngestionJobType.INITIAL_IMPORT.value,
            use_fake_adapter=True,
            fake_state=fake_state,
        )

    assert payload["completed"] is True
    assert payload["imported"] == 1
