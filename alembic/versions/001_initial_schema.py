"""Initial PostgreSQL schema with pgvector, FTS and reference seed.

Revision ID: 001_initial
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op

import relocate_helper.db.models  # noqa: F401 — register metadata
from relocate_helper.db.base import Base

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops)
        """
    )
    _seed_reference_data()


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
    op.execute("DROP EXTENSION IF EXISTS vector")


def _seed_reference_data() -> None:
    op.execute(
        """
        INSERT INTO countries (code, name)
        VALUES ('BR', 'Brazil')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO cities (country_id, name, slug)
        SELECT c.id, 'Florianópolis', 'florianopolis'
        FROM countries c
        WHERE c.code = 'BR'
        ON CONFLICT ON CONSTRAINT uq_cities_country_slug DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO geo_aliases (city_id, district_id, alias, language)
        SELECT ci.id, NULL, v.alias, v.language
        FROM cities ci
        JOIN countries co ON co.id = ci.country_id
        CROSS JOIN (VALUES
            ('Florianópolis', 'pt'),
            ('Флорианопolis', 'ru'),
            ('Floripa', 'pt')
        ) AS v(alias, language)
        WHERE co.code = 'BR' AND ci.slug = 'florianopolis'
        ON CONFLICT ON CONSTRAINT uq_geo_aliases_scope DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO topics (slug, name, freshness_days, version)
        VALUES
            ('housing_rent', 'Аренда жилья', 365, 1),
            ('districts', 'Районы', 365, 1),
            ('groceries', 'Продукты и покупки', 180, 1),
            ('services_prices', 'Услуги и цены', 180, 1),
            ('healthcare', 'Здравоохранение', 90, 1),
            ('transport', 'Транспорт', 180, 1),
            ('daily_life', 'Быт и условия жизни', 180, 1),
            ('mobile_internet', 'Связь и интернет', 180, 1)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO topic_aliases (topic_id, alias, language)
        SELECT t.id, v.alias, v.language
        FROM topics t
        JOIN (VALUES
            ('housing_rent', 'аренда', 'ru'),
            ('housing_rent', 'жильё', 'ru'),
            ('housing_rent', 'rent', 'en'),
            ('districts', 'район', 'ru'),
            ('districts', 'district', 'en'),
            ('districts', 'bairro', 'pt'),
            ('groceries', 'продукты', 'ru'),
            ('groceries', 'супермаркет', 'ru'),
            ('groceries', 'groceries', 'en'),
            ('services_prices', 'услуги', 'ru'),
            ('services_prices', 'цены', 'ru'),
            ('services_prices', 'services', 'en'),
            ('healthcare', 'врач', 'ru'),
            ('healthcare', 'клиника', 'ru'),
            ('healthcare', 'healthcare', 'en'),
            ('transport', 'автобус', 'ru'),
            ('transport', 'transport', 'en'),
            ('transport', 'transporte', 'pt'),
            ('daily_life', 'быт', 'ru'),
            ('daily_life', 'жизнь', 'ru'),
            ('daily_life', 'daily life', 'en'),
            ('mobile_internet', 'интернет', 'ru'),
            ('mobile_internet', 'сим-карта', 'ru'),
            ('mobile_internet', 'mobile', 'en')
        ) AS v(slug, alias, language) ON t.slug = v.slug
        ON CONFLICT ON CONSTRAINT uq_topic_aliases_topic_alias DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO plans (slug, name, duration_days, price_stars, limits, is_active, is_trial)
        VALUES
            (
                'trial',
                'Пробный доступ',
                7,
                NULL,
                '{"successful_answers_per_period": 3, "rate_per_minute": 5}'::jsonb,
                true,
                true
            ),
            (
                'day_1',
                '1 день',
                1,
                NULL,
                '{"successful_answers_per_24h": 30, "rate_per_minute": 5}'::jsonb,
                true,
                false
            ),
            (
                'day_7',
                '7 дней',
                7,
                NULL,
                '{"successful_answers_per_24h": 30, "rate_per_minute": 5}'::jsonb,
                true,
                false
            ),
            (
                'day_30',
                '30 дней',
                30,
                NULL,
                '{"successful_answers_per_24h": 30, "rate_per_minute": 5}'::jsonb,
                true,
                false
            )
        ON CONFLICT (slug) DO NOTHING
        """
    )
