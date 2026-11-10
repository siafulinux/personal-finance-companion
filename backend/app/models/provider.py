"""Administrator-managed financial provider configuration.

One row per aggregator. The row decides whether the provider may be used at all, the
order the selection service tries providers in, which environment it talks to, and
holds its credentials as AES-GCM ciphertext.

Credentials live here rather than only in the environment because a self-hosted owner
should be able to rotate a Plaid secret from the admin screen without rebuilding a
container. The environment still works as the fallback, so a Docker deployment can be
configured entirely with ``PLAID_SECRET`` / ``TELLER_APPLICATION_ID`` and never touch
the UI. The database wins when it holds a value, because that is the value the owner
last chose deliberately.

The encryption key is deliberately *not* in this table: it comes from
``PROVIDER_ENCRYPTION_KEY`` (or is derived from ``SECRET_KEY``). A leaked database
dump therefore does not expose provider secrets.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.base import TimestampMixin

#: Providers the application knows how to drive. The selection service walks these.
PROVIDER_NAMES = ("teller", "plaid")


class ProviderConfig(Base, TimestampMixin):
    __tablename__ = "provider_configs"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    #: Disabled providers are skipped by selection but their links keep syncing, so
    #: turning a provider off never strands a user's existing connection.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    #: Lower runs first. Teller is seeded at 10 and Plaid at 20 (Teller primary).
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    #: sandbox | development | production, validated per provider by the service.
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="sandbox"
    )
    #: AES-GCM ciphertext of `{"public": {...}, "secret": {...}}`.
    credentials_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Extra facts from the last test (institution counts, missing fields, …).
    last_test_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


__all__ = ["PROVIDER_NAMES", "ProviderConfig"]
