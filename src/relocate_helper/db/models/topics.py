"""Topic reference models."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import Base, TimestampMixin, VersionMixin


class Topic(Base, TimestampMixin, VersionMixin):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    freshness_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="180")

    aliases: Mapped[list[TopicAlias]] = relationship(back_populates="topic")

    __table_args__ = (CheckConstraint("freshness_days > 0", name="topics_freshness_days_positive"),)


class TopicAlias(Base, TimestampMixin):
    __tablename__ = "topic_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, server_default="und")

    topic: Mapped[Topic] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("topic_id", "alias", "language", name="uq_topic_aliases_topic_alias"),
    )
