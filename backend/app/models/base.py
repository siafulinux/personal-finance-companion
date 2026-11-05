"""Shared model helpers: money type, timezone-aware timestamps, enums."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SAEnum, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

MONEY = Numeric(18, 2)
QUANTITY = Numeric(12, 4)


def money(value: str | int | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def str_enum(enum_cls, name: str) -> SAEnum:
    """Portable VARCHAR-backed enum so migrations stay simple and readable."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
        validate_strings=True,
        length=40,
    )


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
