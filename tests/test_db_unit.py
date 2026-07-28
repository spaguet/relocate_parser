"""Unit tests for database layer without PostgreSQL."""

from __future__ import annotations

from relocate_helper.common.config import Settings
from relocate_helper.db.base import Base, DEFAULT_EMBEDDING_DIMENSION
import relocate_helper.db.models  # noqa: F401


def test_all_expected_tables_registered() -> None:
    expected = {
        "countries",
        "cities",
        "districts",
        "geo_aliases",
        "topics",
        "topic_aliases",
        "sources",
        "documents",
        "document_versions",
        "chunks",
        "facts",
        "fact_evidence",
        "knowledge_cards",
        "ingestion_jobs",
        "model_runs",
        "users",
        "plans",
        "subscriptions",
        "payments",
        "promo_codes",
        "usage_events",
        "answer_cache",
        "queries",
        "answer_feedback",
        "admin_users",
        "admin_audit_log",
        "tombstones",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_database_url_async_conversion() -> None:
    settings = Settings(database_url="postgresql://user:pass@localhost:5432/db")
    assert settings.database_url_async == "postgresql+asyncpg://user:pass@localhost:5432/db"


def test_embedding_dimension_default() -> None:
    settings = Settings()
    assert settings.embedding_dimension == DEFAULT_EMBEDDING_DIMENSION
