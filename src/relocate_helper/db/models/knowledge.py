"""Knowledge extraction models: facts, evidence, cards."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import Base, TimestampMixin, VersionMixin
from relocate_helper.db.enums import FactType, PublicationStatus, ValidityPeriodType
from relocate_helper.db.types import JsonDict

if TYPE_CHECKING:
    from relocate_helper.db.models.documents import Chunk


class Fact(Base, TimestampMixin, VersionMixin):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fact_type: Mapped[FactType] = mapped_column(
        Enum(FactType, name="fact_type", native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status", native_enum=False, length=32),
        nullable=False,
        server_default=PublicationStatus.DRAFT.value,
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    payload: Mapped[JsonDict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    validity_type: Mapped[ValidityPeriodType] = mapped_column(
        Enum(ValidityPeriodType, name="validity_period_type", native_enum=False, length=16),
        nullable=False,
        server_default=ValidityPeriodType.UNKNOWN.value,
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    needs_review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence: Mapped[list[FactEvidence]] = relationship(back_populates="fact")

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="facts_confidence_range"),
        CheckConstraint(
            "price_amount IS NULL OR price_amount > 0",
            name="facts_price_positive",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="facts_validity_range",
        ),
        Index("ix_facts_city_topic_status", "city_id", "topic_id", "status"),
        Index("ix_facts_status_confidence", "status", "confidence"),
        Index("ix_facts_validity", "valid_from", "valid_to"),
    )


class FactEvidence(Base, TimestampMixin):
    __tablename__ = "fact_evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fact_id: Mapped[int] = mapped_column(
        ForeignKey("facts.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    relevance_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    fact: Mapped[Fact] = relationship(back_populates="evidence")
    chunk: Mapped[Chunk] = relationship(back_populates="evidence_links")

    __table_args__ = (
        UniqueConstraint("fact_id", "chunk_id", name="uq_fact_evidence_fact_chunk"),
        CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 1",
            name="fact_evidence_relevance_range",
        ),
        Index("ix_fact_evidence_fact_id", "fact_id"),
        Index("ix_fact_evidence_chunk_id", "chunk_id"),
    )


class KnowledgeCard(Base, TimestampMixin, VersionMixin):
    __tablename__ = "knowledge_cards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status", native_enum=False, length=32),
        nullable=False,
        server_default=PublicationStatus.DRAFT.value,
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    fact_ids: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="knowledge_cards_confidence_range"
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="knowledge_cards_validity_range",
        ),
        Index("ix_knowledge_cards_city_topic_status", "city_id", "topic_id", "status"),
    )
