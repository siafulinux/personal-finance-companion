"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Personal Finance Companion"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8010
    web_host: str = "127.0.0.1"
    web_port: int = 5183
    cors_origins: str = "http://127.0.0.1:5183,http://localhost:5183"

    postgres_user: str = "finance"
    postgres_password: str = "finance_dev_password"
    postgres_db: str = "finance"
    db_port: int = 55432
    database_url: str = (
        "postgresql+psycopg://finance:finance_dev_password@127.0.0.1:55432/finance"
    )

    secret_key: str = "change-me-dev-only-secret-key-please-generate-your-own"
    access_token_ttl_minutes: int = 720
    session_cookie_name: str = "pfc_session"
    csrf_cookie_name: str = "pfc_csrf"
    cookie_secure: bool = False
    password_min_length: int = 10

    default_currency: str = "USD"
    default_timezone: str = "America/New_York"
    default_safe_to_spend_horizon_days: int = 14
    max_safe_to_spend_horizon_days: int = 45

    demo_user_email: str = "demo@example.com"
    demo_user_password: str = "DemoPassword123!"

    @field_validator("database_url")
    @classmethod
    def _sync_driver(cls, value: str) -> str:
        # Accept the common postgres:// style URLs and normalise to psycopg 3.
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def default_minimum_buffer(self) -> Decimal:
        return Decimal("0.00")

    def validate_runtime(self) -> None:
        """Refuse to start a production deployment with development security."""
        if not self.is_production:
            return
        problems: list[str] = []
        if self.secret_key.startswith("change-me") or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a unique value of at least 32 characters")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if any(origin.strip() == "*" for origin in self.cors_origin_list):
            problems.append("CORS_ORIGINS cannot contain a wildcard with credentialed sessions")
        if problems:
            raise RuntimeError(
                "Unsafe production configuration: " + "; ".join(problems) + "."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
