"""Geography reference models."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relocate_helper.db.base import Base, TimestampMixin


class Country(Base, TimestampMixin):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    cities: Mapped[list[City]] = relationship(back_populates="country")


class City(Base, TimestampMixin):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(
        ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)

    country: Mapped[Country] = relationship(back_populates="cities")
    districts: Mapped[list[District]] = relationship(back_populates="city")
    aliases: Mapped[list[GeoAlias]] = relationship(back_populates="city")

    __table_args__ = (UniqueConstraint("country_id", "slug", name="uq_cities_country_slug"),)


class District(Base, TimestampMixin):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)

    city: Mapped[City] = relationship(back_populates="districts")
    aliases: Mapped[list[GeoAlias]] = relationship(back_populates="district")

    __table_args__ = (UniqueConstraint("city_id", "slug", name="uq_districts_city_slug"),)


class GeoAlias(Base, TimestampMixin):
    __tablename__ = "geo_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE"), nullable=False
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"),
        nullable=True,
    )
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, server_default="und")

    city: Mapped[City] = relationship(back_populates="aliases")
    district: Mapped[District | None] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint(
            "city_id",
            "district_id",
            "alias",
            "language",
            name="uq_geo_aliases_scope",
            postgresql_nulls_not_distinct=True,
        ),
    )
