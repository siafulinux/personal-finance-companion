"""Shopping locations and the visits detected at them.

Coordinates are stored only for places the user deliberately tracks, because the
Android client needs them to register a geofence. A detected visit stores the
business name and the day, not the user's position: the history screen never
needs a coordinate and keeping one would turn a useful feature into a movement
log.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import NUMERIC, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import MONEY, TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import LocationSource, VisitStatus

LATITUDE = NUMERIC(9, 6)
LONGITUDE = NUMERIC(9, 6)


class TrackedLocation(Base, UUIDPrimaryKey, TimestampMixin):
    """A store the user chose to monitor, with its own optional budget."""

    __tablename__ = "tracked_locations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(160), nullable=True)
    merchant_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    address: Mapped[str | None] = mapped_column(String(240), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(LATITUDE, nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(LONGITUDE, nullable=True)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default="150")
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # A per-store spending cap. Null means "use the category budget only".
    monthly_budget: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    notify_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    source: Mapped[str] = mapped_column(
        str_enum(LocationSource, "location_source_enum"),
        nullable=False,
        server_default=LocationSource.MANUAL.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    visits: Mapped[list["ShoppingVisit"]] = relationship(back_populates="location")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tracked_locations_user_name"),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="tracked_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="tracked_longitude_range",
        ),
        CheckConstraint("radius_m BETWEEN 50 AND 2000", name="tracked_radius_range"),
        CheckConstraint(
            "monthly_budget IS NULL OR monthly_budget >= 0",
            name="tracked_budget_non_negative",
        ),
        Index("ix_tracked_locations_user_active", "user_id", "is_active"),
    )


class ShoppingVisit(Base, UUIDPrimaryKey, TimestampMixin):
    """One detection. A visit is not a purchase and never becomes a transaction."""

    __tablename__ = "shopping_visits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tracked_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracked_locations.id", ondelete="SET NULL"), nullable=True
    )
    business_name: Mapped[str] = mapped_column(String(160), nullable=False)
    merchant_key: Mapped[str] = mapped_column(String(160), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visit_day: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        str_enum(VisitStatus, "visit_status_enum"),
        nullable=False,
        server_default=VisitStatus.DETECTED.value,
    )
    confidence: Mapped[Decimal] = mapped_column(
        NUMERIC(4, 3), nullable=False, server_default="1.000"
    )
    distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(
        str_enum(LocationSource, "visit_source_enum"),
        nullable=False,
        server_default=LocationSource.GEOFENCE.value,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    location: Mapped[TrackedLocation | None] = relationship(back_populates="visits")

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="visit_confidence_range"
        ),
        # One row per place per day: a phone that re-detects the same shop after a
        # reboot, or two devices on one account, cannot spam the notification.
        UniqueConstraint(
            "user_id", "merchant_key", "visit_day", name="uq_shopping_visits_user_place_day"
        ),
        Index("ix_shopping_visits_user_visited", "user_id", "visited_at"),
        Index("ix_shopping_visits_user_status", "user_id", "status"),
    )
