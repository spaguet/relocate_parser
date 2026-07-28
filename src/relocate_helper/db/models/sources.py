"""Source registry models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import Base, TimestampMixin, VersionMixin
from relocate_helper.db.enums import SourceStatus, SourceType
from relocate_helper.db.types import JsonDict

if TYPE_CHECKING:
    from relocate_helper.db.models.documents import Document
    from relocate_helper.db.models.geo import City
    from relocate_helper.db.models.jobs import IngestionJob


class Source(Base, TimestampMixin, VersionMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", native_enum=False, length=32),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, name="source_status", native_enum=False, length=32),
        nullable=False,
        server_default=SourceStatus.ACTIVE.value,
    )
    external_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sync_config: Mapped[JsonDict | None] = mapped_column(JSONB, nullable=True)
    retention_policy: Mapped[JsonDict | None] = mapped_column(JSONB, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)

    city: Mapped[City | None] = relationship()
    documents: Mapped[list[Document]] = relationship(back_populates="source")
    ingestion_jobs: Mapped[list[IngestionJob]] = relationship(back_populates="source")
