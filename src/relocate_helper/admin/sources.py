"""Source registry service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import SecretStr

from relocate_helper.admin.crypto import (
    decrypt_sync_config,
    encrypt_sync_config,
    redact_sync_config,
)
from relocate_helper.common.config import Settings
from relocate_helper.db.enums import SourceStatus, SourceType
from relocate_helper.db.models.geo import City
from relocate_helper.db.models.sources import Source
from relocate_helper.db.repository import Database


@dataclass(frozen=True, slots=True)
class SourceCreateInput:
    source_type: SourceType
    name: str
    legal_basis: str | None = None
    city_id: int | None = None
    status: SourceStatus = SourceStatus.ACTIVE
    external_ref: str | None = None
    sync_config: dict[str, Any] | None = None
    retention_policy: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SourceUpdateInput:
    name: str | None = None
    legal_basis: str | None = None
    city_id: int | None = None
    status: SourceStatus | None = None
    external_ref: str | None = None
    sync_config: dict[str, Any] | None = None
    retention_policy: dict[str, Any] | None = None
    sync_cursor: str | None = None
    last_synced_at: datetime | None = None


class SourceNotFoundError(LookupError):
    pass


class SourceRegistryService:
    """Transactional CRUD for ingestion sources."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings

    @property
    def _secrets_key(self) -> SecretStr:
        return self._settings.source_secrets_key

    async def list_sources(
        self,
        session: AsyncSession,
        *,
        city_id: int | None = None,
        status: SourceStatus | None = None,
    ) -> list[Source]:
        query = select(Source).order_by(Source.id)
        if city_id is not None:
            query = query.where(Source.city_id == city_id)
        if status is not None:
            query = query.where(Source.status == status)
        return list(await session.scalars(query))

    async def get_source(self, session: AsyncSession, source_id: int) -> Source:
        source = await session.get(Source, source_id)
        if source is None:
            raise SourceNotFoundError(f"Source {source_id} not found")
        return source

    async def create_source(
        self,
        session: AsyncSession,
        payload: SourceCreateInput,
        *,
        admin_user_id: int | None = None,
    ) -> Source:
        await self._validate_city(session, payload.city_id)
        encrypted_sync = encrypt_sync_config(payload.sync_config, self._secrets_key)
        source = Source(
            source_type=payload.source_type,
            name=payload.name,
            legal_basis=payload.legal_basis,
            city_id=payload.city_id,
            status=payload.status,
            external_ref=payload.external_ref,
            sync_config=encrypted_sync,
            retention_policy=payload.retention_policy,
        )
        session.add(source)
        await session.flush()
        await self._database.record_admin_audit(
            session,
            admin_user_id=admin_user_id,
            action="source_created",
            entity_type="source",
            entity_id=str(source.id),
            details={"source_type": payload.source_type.value, "name": payload.name},
        )
        return source

    async def update_source(
        self,
        session: AsyncSession,
        source_id: int,
        payload: SourceUpdateInput,
        *,
        admin_user_id: int | None = None,
    ) -> Source:
        source = await self.get_source(session, source_id)
        if payload.city_id is not None:
            await self._validate_city(session, payload.city_id)
            source.city_id = payload.city_id
        if payload.name is not None:
            source.name = payload.name
        if payload.legal_basis is not None:
            source.legal_basis = payload.legal_basis
        if payload.status is not None:
            source.status = payload.status
        if payload.external_ref is not None:
            source.external_ref = payload.external_ref
        if payload.sync_config is not None:
            source.sync_config = encrypt_sync_config(payload.sync_config, self._secrets_key)
        if payload.retention_policy is not None:
            source.retention_policy = payload.retention_policy
        if payload.sync_cursor is not None:
            source.sync_cursor = payload.sync_cursor
        if payload.last_synced_at is not None:
            source.last_synced_at = payload.last_synced_at

        await self._database.record_admin_audit(
            session,
            admin_user_id=admin_user_id,
            action="source_updated",
            entity_type="source",
            entity_id=str(source.id),
            details={"updated": True},
        )
        return source

    async def disable_source(
        self,
        session: AsyncSession,
        source_id: int,
        *,
        admin_user_id: int | None = None,
    ) -> Source:
        source = await self.get_source(session, source_id)
        source.status = SourceStatus.DISABLED
        await self._database.record_admin_audit(
            session,
            admin_user_id=admin_user_id,
            action="source_disabled",
            entity_type="source",
            entity_id=str(source.id),
            details={},
        )
        return source

    def public_sync_config(self, source: Source) -> dict[str, Any] | None:
        return redact_sync_config(source.sync_config)

    def internal_sync_config(self, source: Source) -> dict[str, Any] | None:
        return decrypt_sync_config(source.sync_config, self._secrets_key)

    async def _validate_city(self, session: AsyncSession, city_id: int | None) -> None:
        if city_id is None:
            return
        city = await session.get(City, city_id)
        if city is None:
            msg = f"City {city_id} not found"
            raise ValueError(msg)
