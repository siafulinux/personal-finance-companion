"""Server-level configuration and one-time pairing codes.

These are the only tables that are *not* per-user: they describe the installation
itself (its name, whether strangers may register, and who created it). A Docker
deployment has exactly one of each, so the settings table is a singleton row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

SETTINGS_ID = 1


class ServerSettings(Base, TimestampMixin):
    """One row per installation. Created by the first-run setup flow."""

    __tablename__ = "server_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SETTINGS_ID)
    server_name: Mapped[str] = mapped_column(
        String(120), nullable=False, server_default="Personal Finance Companion"
    )
    #: Whether people who are not the owner may create their own account.
    registration_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    #: Set once the first-run wizard finished; this is what closes the wizard.
    setup_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The account created by the wizard. Only it may change server settings.
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: Owner-supplied public address, e.g. https://finance.example.com. When empty
    #: the server derives URLs from the request instead of guessing.
    public_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Whether the server picks a financial provider per institution. With this off a
    #: user must use whatever the administrator pinned first, and an institution the
    #: primary cannot serve is reported as unavailable instead of falling back.
    provider_auto_select: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class PairingToken(Base, UUIDPrimaryKey):
    """A short-lived, single-use code that hands a phone this server's address.

    Only the SHA-256 hash is stored, so a database leak cannot be replayed into a
    pairing. Codes carry no credentials and grant no session: they reveal the same
    public information as ``/server/info``.
    """

    __tablename__ = "pairing_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
