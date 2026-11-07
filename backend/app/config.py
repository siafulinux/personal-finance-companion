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

    # --- Phase 2: financial connectivity ---
    # Dedicated key for provider-token encryption. When unset, a key is derived from
    # SECRET_KEY with HKDF, which is safe for development but ties the ciphertext to
    # that secret: set this in any real deployment so SECRET_KEY can rotate.
    provider_encryption_key: str | None = None
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_environment: str = "sandbox"
    plaid_base_url: str | None = None
    plaid_webhook_url: str | None = None
    # The bundled simulated institution. On by default: it needs no credentials.
    sandbox_provider_enabled: bool = True
    sync_page_size: int = 100
    sync_max_pages: int = 50
    # Minimum spacing between scheduled syncs for one link, in minutes.
    sync_min_interval_minutes: int = 60

    # --- Self-hosting / Docker deployment ---
    # The address clients should use when it differs from the request's own host
    # (a reverse proxy on a domain, a tunnel, a NAT). Per-install overrides set in
    # the setup wizard take precedence over this.
    public_base_url: str | None = None
    # Until the first-run wizard finishes, may strangers create an account? Local
    # development leaves this true so tests and seeds can register freely; the
    # Docker deployment sets it false, so an exposed install cannot be claimed by
    # whoever finds it first.
    open_registration_until_setup: bool = True
    # Comma-separated Host header allowlist. "*" permits any, which a LAN install
    # reached by IP needs; set an explicit host list on a public domain.
    trusted_hosts: str = "*"

    # --- Phase 2: AI assistant (optional; the app is fully usable without it) ---
    ai_provider: str = "disabled"  # disabled | openai_compatible
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: int = 30

    @field_validator("public_base_url", mode="before")
    @classmethod
    def _blank_url(cls, value):
        # Compose passes an empty string when the setting is unused; treat it as unset.
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
    def trusted_host_list(self) -> list[str]:
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()] or ["*"]

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
