"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relocate_helper.admin.sources import SourceRegistryService
from relocate_helper.common.config import Settings
from relocate_helper.db.repository import Database
from relocate_helper.storage.deletion import ContentDeletionService
from relocate_helper.storage.document_service import DocumentStorageService
from relocate_helper.storage.protocol import ObjectStorage


def get_settings_dep(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_object_storage(request: Request) -> ObjectStorage:
    return cast(ObjectStorage, request.app.state.object_storage)


def get_database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        yield session


def get_source_registry(
    settings: Settings = Depends(get_settings_dep),
    database: Database = Depends(get_database),
) -> SourceRegistryService:
    return SourceRegistryService(database, settings)


def get_document_storage_service(
    settings: Settings = Depends(get_settings_dep),
    storage: ObjectStorage = Depends(get_object_storage),
) -> DocumentStorageService:
    return DocumentStorageService(storage, settings)


def get_deletion_service(
    storage: ObjectStorage = Depends(get_object_storage),
    database: Database = Depends(get_database),
) -> ContentDeletionService:
    return ContentDeletionService(storage, database)
