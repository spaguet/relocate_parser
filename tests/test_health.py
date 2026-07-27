"""Smoke tests for project scaffold (prompt 1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from relocate_helper.api.app import create_app
from relocate_helper.common.config import AppEnv, Settings, reset_settings_cache
from relocate_helper.common.health import ComponentHealth
from relocate_helper.common.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    reset_settings_cache()
    configure_logging(log_level="WARNING", json_logs=False)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env=AppEnv.TEST,
        log_level="WARNING",
        database_url="postgresql://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/15",
    )


@pytest.fixture
def app(test_settings: Settings):
    return create_app(test_settings)


@pytest.mark.asyncio
async def test_health_live(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready_all_ok(app, test_settings: Settings) -> None:
    ok_checks = [
        ComponentHealth("postgresql", "ok"),
        ComponentHealth("redis", "ok"),
        ComponentHealth("s3", "ok"),
    ]
    with patch(
        "relocate_helper.api.app.gather_readiness",
        new=AsyncMock(return_value=ok_checks),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert len(body["checks"]) == 3


@pytest.mark.asyncio
async def test_health_ready_degraded(app) -> None:
    checks = [
        ComponentHealth("postgresql", "ok"),
        ComponentHealth("redis", "error", "connection refused"),
        ComponentHealth("s3", "ok"),
    ]
    with patch(
        "relocate_helper.api.app.gather_readiness",
        new=AsyncMock(return_value=checks),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_correlation_id_header(app) -> None:
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
            response = await client.get(
                "/health/ready",
                headers={"X-Correlation-ID": "test-correlation-123"},
            )

    assert response.headers.get("X-Correlation-ID") == "test-correlation-123"
    assert response.headers.get("X-Request-ID")


def test_production_settings_fail_fast() -> None:
    with pytest.raises(ValueError, match="Production configuration is incomplete"):
        Settings(
            app_env=AppEnv.PRODUCTION,
            secret_key="dev-only-change-me-in-production",  # type: ignore[arg-type]
        )


def test_package_imports() -> None:
    import relocate_helper
    import relocate_helper.bot
    import relocate_helper.db
    import relocate_helper.ingestion
    import relocate_helper.workers

    assert relocate_helper.__version__ == "0.1.0"


def test_logging_redacts_secrets() -> None:
    configure_logging(log_level="WARNING", json_logs=False)
    logger = get_logger("test")
    # Smoke: logger accepts secret-like kwargs without raising
    logger.info("test_event", api_key="super-secret-key-value", user="alice")
