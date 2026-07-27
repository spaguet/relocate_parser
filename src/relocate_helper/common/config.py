"""Typed application settings loaded from environment variables."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    """Central configuration with fail-fast validation for production."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_name: str = "relocate_helper"
    log_level: str = "INFO"
    log_json: bool = False
    secret_key: SecretStr = SecretStr("dev-only-change-me-in-production")
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql://relocate:relocate@localhost:5432/relocate_helper"
    database_pool_min_size: int = 1
    database_pool_max_size: int = 5
    database_connect_timeout_seconds: float = 5.0

    redis_url: str = "redis://localhost:6379/0"
    redis_connect_timeout_seconds: float = 3.0

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: SecretStr = SecretStr("minioadmin")
    s3_secret_key: SecretStr = SecretStr("minioadmin")
    s3_bucket: str = "relocate-helper"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    rq_default_queue: str = "default"
    rq_worker_health_port: int = 9191

    health_check_timeout_seconds: float = 3.0

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_production_requirements(self) -> Self:
        if self.app_env != AppEnv.PRODUCTION:
            return self

        missing: list[str] = []
        if self.secret_key.get_secret_value() in {
            "",
            "dev-only-change-me-in-production",
            "change-me",
        }:
            missing.append("SECRET_KEY")

        if self.database_url.startswith("postgresql://relocate:relocate@"):
            missing.append("DATABASE_URL (must not use development default)")

        if self.redis_url == "redis://localhost:6379/0":
            missing.append("REDIS_URL (must not use development default)")

        if self.s3_access_key.get_secret_value() == "minioadmin":
            missing.append("S3_ACCESS_KEY (must not use development default)")

        if self.s3_secret_key.get_secret_value() == "minioadmin":
            missing.append("S3_SECRET_KEY (must not use development default)")

        if missing:
            raise ValueError(
                "Production configuration is incomplete. Set: " + ", ".join(missing)
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == AppEnv.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance (safe to call repeatedly)."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear settings cache — intended for tests only."""
    get_settings.cache_clear()
