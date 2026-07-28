"""FastAPI application factory and HTTP routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from relocate_helper.common.config import Settings, get_settings
from relocate_helper.common.health import gather_readiness
from relocate_helper.common.logging import configure_logging, get_logger
from relocate_helper.common.middleware import CorrelationIdMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.log_json)
    logger.info("application_starting", app_env=settings.app_env.value)
    yield
    logger.info("application_stopping")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application with health endpoints."""
    resolved = settings or get_settings()

    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not resolved.is_production else None,
        redoc_url="/redoc" if not resolved.is_production else None,
    )
    app.state.settings = resolved
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, str]:
        """Liveness probe — process is running."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> dict[str, object]:
        """Readiness probe — dependencies are reachable."""
        checks = await gather_readiness(resolved)
        all_ok = all(check.status == "ok" for check in checks)
        body: dict[str, object] = {
            "status": "ok" if all_ok else "degraded",
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks],
        }
        return body

    return app
