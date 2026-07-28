"""Pydantic schemas for admin API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from relocate_helper.db.enums import (
    DocumentStatus,
    IngestionJobStatus,
    IngestionJobType,
    SourceStatus,
    SourceType,
)


class SourceCreateRequest(BaseModel):
    source_type: SourceType
    name: str = Field(min_length=1, max_length=256)
    legal_basis: str | None = None
    city_id: int | None = None
    status: SourceStatus = SourceStatus.ACTIVE
    external_ref: str | None = Field(default=None, max_length=512)
    sync_config: dict[str, Any] | None = None
    retention_policy: dict[str, Any] | None = None


class SourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    legal_basis: str | None = None
    city_id: int | None = None
    status: SourceStatus | None = None
    external_ref: str | None = Field(default=None, max_length=512)
    sync_config: dict[str, Any] | None = None
    retention_policy: dict[str, Any] | None = None
    sync_cursor: str | None = Field(default=None, max_length=512)
    last_synced_at: datetime | None = None


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: SourceType
    name: str
    legal_basis: str | None
    city_id: int | None
    status: SourceStatus
    external_ref: str | None
    sync_config: dict[str, Any] | None
    retention_policy: dict[str, Any] | None
    last_synced_at: datetime | None
    sync_cursor: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    content_hash: str
    storage_key: str | None
    mime_type: str | None
    size_bytes: int | None
    source_published_at: datetime | None
    source_updated_at: datetime | None
    created_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    external_id: str
    status: DocumentStatus
    language: str | None
    city_id: int | None
    current_version_id: int | None
    metadata: dict[str, Any] | None = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime
    current_version: DocumentVersionResponse | None = None


class TelegramSyncRequest(BaseModel):
    job_type: IngestionJobType = IngestionJobType.INCREMENTAL_SYNC
    since: datetime | None = None
    until: datetime | None = None


class TelegramSyncResponse(BaseModel):
    job_id: int
    rq_job_id: str
    idempotency_key: str
    created: bool


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int | None
    job_type: IngestionJobType
    status: IngestionJobStatus
    idempotency_key: str
    cursor: str | None
    progress: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class DeleteDocumentContentRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=128)


class ErrorResponse(BaseModel):
    detail: str
