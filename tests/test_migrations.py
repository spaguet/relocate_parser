"""Migration upgrade/downgrade integration tests."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from relocate_helper.db.models.billing import Plan
from relocate_helper.db.models.geo import City, Country
from relocate_helper.db.models.topics import Topic
from relocate_helper.db.seed import seed_reference_data

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
def require_postgres(database_url: str) -> str:
    if not asyncio.run(_postgres_available(database_url)):
        pytest.skip("PostgreSQL is not available for migration tests")
    return database_url


def test_migration_upgrade_and_downgrade(
    require_postgres: str,
    alembic_config: Config,
) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    async def _verify_seed() -> None:
        engine = create_async_engine(_async_database_url(require_postgres))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            country = await session.scalar(select(Country).where(Country.code == "BR"))
            city = await session.scalar(select(City).where(City.slug == "florianopolis"))
            topics = (await session.scalars(select(Topic))).all()
            plans = (await session.scalars(select(Plan))).all()
            assert country is not None
            assert city is not None
            assert len(topics) >= 8
            assert len(plans) >= 4
        await engine.dispose()

    asyncio.run(_verify_seed())

    command.downgrade(alembic_config, "base")

    async def _verify_empty() -> None:
        engine = create_async_engine(_async_database_url(require_postgres))
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
            )
            count = result.scalar_one()
            assert count == 0
        await engine.dispose()

    asyncio.run(_verify_empty())
    command.upgrade(alembic_config, "head")


def test_seed_reference_data_idempotent(require_postgres: str) -> None:
    async def _run() -> None:
        engine = create_async_engine(_async_database_url(require_postgres))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await seed_reference_data(session)
            await session.commit()
            topic_count = len((await session.scalars(select(Topic))).all())
            plan_count = len((await session.scalars(select(Plan))).all())
            await seed_reference_data(session)
            await session.commit()
            assert len((await session.scalars(select(Topic))).all()) == topic_count
            assert len((await session.scalars(select(Plan))).all()) == plan_count
        await engine.dispose()

    asyncio.run(_run())
