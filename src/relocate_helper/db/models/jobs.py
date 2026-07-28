"""Ingestion jobs and model run tracking."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import Base, TimestampMixin
from relocate_helper.db.enums import IngestionJobStatus, IngestionJobType, ModelRunPurpose
from relocate_helper.db.types import JsonDict

if TYPE_CHECKING:
    from relocate_helper.db.models.sources import Source


class IngestionJob(Base, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_type: Mapped[IngestionJobType] = mapped_column(
        Enum(IngestionJobType, name="ingestion_job_type", native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[IngestionJobStatus] = mapped_column(
        Enum(IngestionJobStatus, name="ingestion_job_status", native_enum=False, length=32),
        nullable=False,
        server_default=IngestionJobStatus.PENDING.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    progress: Mapped[JsonDict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    source: Mapped[Source | None] = relationship(back_populates="ingestion_jobs")

    __table_args__ = (
        Index("ix_ingestion_jobs_source_status", "source_id", "status"),
        Index("ix_ingestion_jobs_status_created", "status", "created_at"),
    )


class ModelRun(Base, TimestampMixin):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    purpose: Mapped[ModelRunPurpose] = mapped_column(
        Enum(ModelRunPurpose, name="model_run_purpose", native_enum=False, length=32),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="model_runs_input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="model_runs_output_tokens_non_negative",
        ),
        CheckConstraint(
            "cost_usd IS NULL OR cost_usd >= 0",
            name="model_runs_cost_non_negative",
        ),
        Index("ix_model_runs_purpose_created", "purpose", "created_at"),
    )
