"""Billing: users, plans, subscriptions, payments, promo codes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import Base, TimestampMixin
from relocate_helper.db.enums import PaymentStatus, SubscriptionStatus
from relocate_helper.db.types import JsonDict


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, server_default="ru")
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")
    payments: Mapped[list[Payment]] = relationship(back_populates="user")


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limits: Mapped[JsonDict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="plan")
    payments: Mapped[list[Payment]] = relationship(back_populates="plan")
    promo_codes: Mapped[list[PromoCode]] = relationship(back_populates="plan")

    __table_args__ = (
        CheckConstraint("duration_days > 0", name="plans_duration_positive"),
        CheckConstraint(
            "price_stars IS NULL OR price_stars > 0",
            name="plans_price_stars_positive",
        ),
    )


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False, length=32),
        nullable=False,
        server_default=SubscriptionStatus.ACTIVE.value,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship(back_populates="subscriptions")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="subscriptions_valid_period"),
        Index("ix_subscriptions_user_status", "user_id", "status"),
        Index("ix_subscriptions_ends_at", "ends_at"),
    )


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    telegram_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False, length=32),
        nullable=False,
        server_default=PaymentStatus.PENDING.value,
    )
    metadata_: Mapped[JsonDict | None] = mapped_column("metadata", JSONB, nullable=True)

    user: Mapped[User] = relationship(back_populates="payments")
    plan: Mapped[Plan] = relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount_stars > 0", name="payments_amount_positive"),
        Index("ix_payments_user_status", "user_id", "status"),
    )


class PromoCode(Base, TimestampMixin):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    plan: Mapped[Plan] = relationship(back_populates="promo_codes")

    __table_args__ = (
        CheckConstraint("used_count >= 0", name="promo_codes_used_non_negative"),
        CheckConstraint(
            "max_uses IS NULL OR max_uses > 0",
            name="promo_codes_max_uses_positive",
        ),
    )
