"""Idempotent reference data seed for MVP geography, topics and plans."""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from relocate_helper.db.models.billing import Plan
from relocate_helper.db.models.geo import City, Country, GeoAlias
from relocate_helper.db.models.topics import Topic, TopicAlias


class TopicSeed(TypedDict):
    slug: str
    name: str
    freshness_days: int
    aliases: list[tuple[str, str]]


class PlanSeed(TypedDict):
    slug: str
    name: str
    duration_days: int
    price_stars: int | None
    is_trial: bool
    limits: dict[str, int]


TOPIC_SEED: list[TopicSeed] = [
    {
        "slug": "housing_rent",
        "name": "Аренда жилья",
        "freshness_days": 365,
        "aliases": [("аренда", "ru"), ("жильё", "ru"), ("rent", "en")],
    },
    {
        "slug": "districts",
        "name": "Районы",
        "freshness_days": 365,
        "aliases": [("район", "ru"), ("district", "en"), ("bairro", "pt")],
    },
    {
        "slug": "groceries",
        "name": "Продукты и покупки",
        "freshness_days": 180,
        "aliases": [("продукты", "ru"), ("супермаркет", "ru"), ("groceries", "en")],
    },
    {
        "slug": "services_prices",
        "name": "Услуги и цены",
        "freshness_days": 180,
        "aliases": [("услуги", "ru"), ("цены", "ru"), ("services", "en")],
    },
    {
        "slug": "healthcare",
        "name": "Здравоохранение",
        "freshness_days": 90,
        "aliases": [("врач", "ru"), ("клиника", "ru"), ("healthcare", "en")],
    },
    {
        "slug": "transport",
        "name": "Транспорт",
        "freshness_days": 180,
        "aliases": [("автобус", "ru"), ("transport", "en"), ("transporte", "pt")],
    },
    {
        "slug": "daily_life",
        "name": "Быт и условия жизни",
        "freshness_days": 180,
        "aliases": [("быт", "ru"), ("жизнь", "ru"), ("daily life", "en")],
    },
    {
        "slug": "mobile_internet",
        "name": "Связь и интернет",
        "freshness_days": 180,
        "aliases": [("интернет", "ru"), ("сим-карта", "ru"), ("mobile", "en")],
    },
]

PLAN_SEED: list[PlanSeed] = [
    {
        "slug": "trial",
        "name": "Пробный доступ",
        "duration_days": 7,
        "price_stars": None,
        "is_trial": True,
        "limits": {"successful_answers_per_period": 3, "rate_per_minute": 5},
    },
    {
        "slug": "day_1",
        "name": "1 день",
        "duration_days": 1,
        "price_stars": None,
        "is_trial": False,
        "limits": {"successful_answers_per_24h": 30, "rate_per_minute": 5},
    },
    {
        "slug": "day_7",
        "name": "7 дней",
        "duration_days": 7,
        "price_stars": None,
        "is_trial": False,
        "limits": {"successful_answers_per_24h": 30, "rate_per_minute": 5},
    },
    {
        "slug": "day_30",
        "name": "30 дней",
        "duration_days": 30,
        "price_stars": None,
        "is_trial": False,
        "limits": {"successful_answers_per_24h": 30, "rate_per_minute": 5},
    },
]


async def seed_reference_data(session: AsyncSession) -> None:
    """Insert MVP geography, topics and plans if missing (idempotent)."""
    country_stmt = (
        insert(Country)
        .values(code="BR", name="Brazil")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    await session.execute(country_stmt)

    country = await session.scalar(select(Country).where(Country.code == "BR"))
    if country is None:
        raise RuntimeError("Failed to seed country BR")

    city_stmt = (
        insert(City)
        .values(country_id=country.id, name="Florianópolis", slug="florianopolis")
        .on_conflict_do_nothing(index_elements=["country_id", "slug"])
    )
    await session.execute(city_stmt)

    city = await session.scalar(
        select(City).where(City.country_id == country.id, City.slug == "florianopolis")
    )
    if city is None:
        raise RuntimeError("Failed to seed city Florianópolis")

    for alias, language in [
        ("Florianópolis", "pt"),
        ("Флорианопolis", "ru"),
        ("Floripa", "pt"),
    ]:
        alias_stmt = (
            insert(GeoAlias)
            .values(city_id=city.id, district_id=None, alias=alias, language=language)
            .on_conflict_do_nothing(index_elements=["city_id", "district_id", "alias", "language"])
        )
        await session.execute(alias_stmt)

    for topic_data in TOPIC_SEED:
        topic_stmt = (
            insert(Topic)
            .values(
                slug=topic_data["slug"],
                name=topic_data["name"],
                freshness_days=topic_data["freshness_days"],
            )
            .on_conflict_do_nothing(index_elements=["slug"])
        )
        await session.execute(topic_stmt)

        topic = await session.scalar(select(Topic).where(Topic.slug == topic_data["slug"]))
        if topic is None:
            continue

        for alias, language in topic_data["aliases"]:
            topic_alias_stmt = (
                insert(TopicAlias)
                .values(topic_id=topic.id, alias=alias, language=language)
                .on_conflict_do_nothing(index_elements=["topic_id", "alias", "language"])
            )
            await session.execute(topic_alias_stmt)

    for plan_data in PLAN_SEED:
        plan_stmt = (
            insert(Plan)
            .values(
                slug=plan_data["slug"],
                name=plan_data["name"],
                duration_days=plan_data["duration_days"],
                price_stars=plan_data["price_stars"],
                is_trial=plan_data["is_trial"],
                limits=plan_data["limits"],
            )
            .on_conflict_do_nothing(index_elements=["slug"])
        )
        await session.execute(plan_stmt)

    await session.flush()
