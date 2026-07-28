"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from relocate_helper.common.config import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    cfg = settings or get_settings()
    return create_async_engine(
        cfg.database_url_async,
        pool_size=cfg.database_pool_min_size,
        max_overflow=max(cfg.database_pool_max_size - cfg.database_pool_min_size, 0),
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
