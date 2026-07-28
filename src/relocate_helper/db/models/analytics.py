"""Usage analytics, answer cache, queries and feedback."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import Base, TimestampMixin
from relocate_helper.db.enums import FeedbackRating, UsageEventType
from relocate_helper.db.types import JsonDict


class UsageEvent(Base, TimestampMixin):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[UsageEventType] = mapped_column(
        Enum(UsageEventType, name="usage_event_type", native_enum=False, length=32),
        nullable=False,
    )
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (Index("ix_usage_events_user_created", "user_id", "created_at"),)


class AnswerCache(Base, TimestampMixin):
    __tablename__ = "answer_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    answer_payload: Mapped[JsonDict] = mapped_column(JSONB, nullable=False)
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_answer_cache_expires_at", "expires_at"),)


class Query(Base, TimestampMixin):
    """Obfuscated query diagnostics — no full question text stored."""

    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    query_length: Mapped[int] = mapped_column(Integer, nullable=False)
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )
    retrieval_summary: Mapped[JsonDict | None] = mapped_column(JSONB, nullable=True)
    model_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    had_sufficient_evidence: Mapped[bool | None] = mapped_column(nullable=True)
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    feedback: Mapped[list[AnswerFeedback]] = relationship(back_populates="query")

    __table_args__ = (
        CheckConstraint("query_length >= 0", name="queries_length_non_negative"),
        Index("ix_queries_user_created", "user_id", "created_at"),
        Index("ix_queries_hash_created", "query_hash", "created_at"),
    )


class AnswerFeedback(Base, TimestampMixin):
    __tablename__ = "answer_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[FeedbackRating] = mapped_column(
        Enum(FeedbackRating, name="feedback_rating", native_enum=False, length=16),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    query: Mapped[Query] = relationship(back_populates="feedback")

    __table_args__ = (Index("ix_answer_feedback_query_id", "query_id"),)
