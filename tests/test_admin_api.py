"""Admin API tests for sources and documents."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from relocate_helper.api.app import create_app
from relocate_helper.common.config import AppEnv, Settings, reset_settings_cache
from relocate_helper.common.health import ComponentHealth
from relocate_helper.db.enums import SourceType
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


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    reset_settings_cache()


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
        pytest.skip("PostgreSQL is not available for admin API tests")
    command.upgrade(alembic_config, "head")
    return database_url


@pytest.fixture
def test_settings(migrated_db: str) -> Settings:
    return Settings(
        app_env=AppEnv.TEST,
        database_url=migrated_db,
        log_level="WARNING",
    )


@pytest.fixture
def app(test_settings: Settings):
    application = create_app(test_settings)
    application.state.object_storage = InMemoryObjectStorage()
    return application


@pytest.mark.asyncio
async def test_create_and_get_source(app, test_settings: Settings) -> None:
    with patch(
        "relocate_helper.api.app.gather_readiness",
        new=AsyncMock(
            return_value=[
                ComponentHealth("postgresql", "ok"),
                ComponentHealth("redis", "ok"),
                ComponentHealth("s3", "ok"),
            ]
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create = await client.post(
                "/admin/sources",
                json={
                    "source_type": SourceType.TELEGRAM.value,
                    "name": "Test TG channel",
                    "city_id": 1,
                    "legal_basis": "public channel",
                    "sync_config": {"username": "@test", "api_token": "secret-token"},
                },
            )
            assert create.status_code == 201
            body = create.json()
            assert body["sync_config"]["api_token"] == "***"
            source_id = body["id"]

            fetched = await client.get(f"/admin/sources/{source_id}")
            assert fetched.status_code == 200
            assert fetched.json()["name"] == "Test TG channel"


@pytest.mark.asyncio
async def test_list_sources(app) -> None:
    with patch(
        "relocate_helper.api.app.gather_readiness",
        new=AsyncMock(
            return_value=[
                ComponentHealth("postgresql", "ok"),
                ComponentHealth("redis", "ok"),
                ComponentHealth("s3", "ok"),
            ]
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/admin/sources")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_missing_source_returns_404(app) -> None:
    with patch(
        "relocate_helper.api.app.gather_readiness",
        new=AsyncMock(
            return_value=[
                ComponentHealth("postgresql", "ok"),
                ComponentHealth("redis", "ok"),
                ComponentHealth("s3", "ok"),
            ]
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/admin/sources/999999")
    assert response.status_code == 404
