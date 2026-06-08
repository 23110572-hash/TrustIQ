"""Centralised configuration loaded from environment variables.

All tunable parameters (thresholds, connection strings, secrets) are read
from the environment / .env file so nothing is hard-coded in business logic.
"""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the .env at the project root (one level above /backend) so the file
# is found no matter which directory the server is started from.
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=_ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    app_name: str = "TrustIQ"
    app_version: str = "1.0.0"
    model_version: str = "2026.06.01"
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_ttl_seconds: int = 900

    # PostgreSQL
    # A full DATABASE_URL (e.g. a hosted Neon/Render/RDS DSN) takes precedence
    # over the individual parts below when set.
    database_url: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "trustiq"
    postgres_user: str = "trustiq"
    postgres_password: str = "trustiq_secret"

    # JWT
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Integration API key — channels (e.g. the Bank of Baroda core simulator)
    # must present this in the `X-API-Key` header to call /api/trust/evaluate.
    trustiq_api_key: str = "bob-trustiq-live-key-2026"

    # Privacy
    dp_epsilon: float = 1.0
    dp_sensitivity: float = 1.0
    pii_salt: str = "trustiq-static-salt"

    # Risk thresholds
    risk_threshold_low: int = 30
    risk_threshold_medium: int = 60
    risk_threshold_high: int = 80

    @property
    def postgres_dsn(self) -> str:
        """Return a psycopg2/SQLAlchemy compatible connection string.

        Prefers an explicit ``DATABASE_URL`` (e.g. a hosted Neon DSN) when
        provided, otherwise assembles one from the individual settings.
        """
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
