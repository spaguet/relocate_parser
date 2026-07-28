"""Database constraint and repository tests."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from relocate_helper.db.enums import (
    DocumentStatus,
    FactType,
    PublicationStatus,
    SourceStatus,
    SourceType,
    TombstoneEntityType,
)
from relocate_helper.db.models.documents import Document
from relocate_helper.db.models.geo import City
from relocate_helper.db.models.knowledge import Fact
from relocate_helper.db.models.sources import Source
from relocate_helper.db.models.topics import Topic
from relocate_helper.db.repository import Database

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
        pytest.skip("PostgreSQL is not available for constraint tests")
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


@pytest.mark.asyncio
async def test_fact_confidence_out_of_range_rejected(session: AsyncSession) -> None:
    city = await session.get(City, 1)
    topic = await session.scalar(select(Topic).limit(1))
    assert city is not None
    assert topic is not None

    fact = Fact(
        city_id=city.id,
        topic_id=topic.id,
        fact_type=FactType.PRICE,
        status=PublicationStatus.DRAFT,
        confidence=Decimal("1.5"),
        payload={"amount": 100},
    )
    session.add(fact)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_document_idempotency_key_unique(session: AsyncSession) -> None:
    city = await session.get(City, 1)
    assert city is not None

    source = Source(
        source_type=SourceType.TELEGRAM,
        name="Test channel",
        city_id=city.id,
        status=SourceStatus.ACTIVE,
    )
    session.add(source)
    await session.flush()

    doc1 = Document(
        source_id=source.id,
        external_id="msg-1",
        idempotency_key="source-1:msg-1",
        status=DocumentStatus.ACTIVE,
    )
    doc2 = Document(
        source_id=source.id,
        external_id="msg-2",
        idempotency_key="source-1:msg-1",
        status=DocumentStatus.ACTIVE,
    )
    session.add_all([doc1, doc2])
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.fixture
async def db_gateway(migrated_db: str):
    engine = create_async_engine(_async_database_url(migrated_db))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield Database(factory), factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_mark_document_deleted_creates_tombstone(
    db_gateway: tuple[Database, async_sessionmaker[AsyncSession]],
) -> None:
    db, factory = db_gateway
    async with factory() as session:
        city = await session.get(City, 1)
        assert city is not None

        source = Source(
            source_type=SourceType.FILE,
            name="Manual upload",
            city_id=city.id,
            status=SourceStatus.ACTIVE,
        )
        session.add(source)
        await session.flush()

        document = Document(
            source_id=source.id,
            external_id="file-1",
            idempotency_key="file:file-1",
            status=DocumentStatus.ACTIVE,
        )
        session.add(document)
        await session.commit()
        document_id = document.id

    async with db.transaction() as tx:
        doc = await tx.get(Document, document_id)
        assert doc is not None
        tombstone = await db.mark_document_deleted(
            tx,
            doc,
            reason="erasure_request",
        )
        assert tombstone.entity_type == TombstoneEntityType.DOCUMENT
        assert doc.status == DocumentStatus.REDACTED
