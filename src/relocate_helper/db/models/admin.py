"""Admin users, audit log and tombstones."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from relocate_helper.db.base import Base, TimestampMixin
from relocate_helper.db.enums import TombstoneEntityType
from relocate_helper.db.types import JsonDict


class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[JsonDict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_admin_audit_log_created", "created_at"),
        Index("ix_admin_audit_log_entity", "entity_type", "entity_id"),
    )


class Tombstone(Base):
    """Minimal record after physical content deletion (right to erasure)."""

    __tablename__ = "tombstones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entity_type: Mapped[TombstoneEntityType] = mapped_column(
        Enum(TombstoneEntityType, name="tombstone_entity_type", native_enum=False, length=32),
        nullable=False,
    )
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("ix_tombstones_entity", "entity_type", "entity_id"),
        Index("ix_tombstones_deleted_at", "deleted_at"),
    )
