"""Shopping location, visit and location-preference schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.models.enums import LocationSource, VisitStatus
from app.schemas.common import APIModel, Money, ORMModel, clean_optional_text

MAX_ACCURACY_M = 500


class TrackedLocationCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    merchant: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=240)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    radius_m: int = Field(default=150, ge=50, le=2000)
    category_id: uuid.UUID | None = None
    monthly_budget: Money | None = Field(default=None, ge=0)
    notify_enabled: bool = True
    is_active: bool = True
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return value.strip()

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @model_validator(mode="after")
    def _coords_together(self):
        # Half a coordinate is not a location. A place may exist without one
        # (the user can add a store before ever standing in it), but never with one.
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both a latitude and a longitude, or neither.")
        return self


class TrackedLocationUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    merchant: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=240)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=50, le=2000)
    category_id: uuid.UUID | None = None
    monthly_budget: Money | None = Field(default=None, ge=0)
    notify_enabled: bool | None = None
    is_active: bool | None = None
    notes: str | None = None
    sort_order: int | None = None


class TrackedLocationOut(ORMModel):
    id: uuid.UUID
    name: str
    merchant: str | None
    merchant_key: str | None
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    radius_m: int
    category_id: uuid.UUID | None
    monthly_budget: Decimal | None
    notify_enabled: bool
    is_active: bool
    source: LocationSource
    notes: str | None
    created_at: datetime
    visit_count: int = 0
    last_visit_at: datetime | None = None
    month_spend: Decimal | None = None
    budget_remaining: Decimal | None = None


class VisitDetectRequest(APIModel):
    """What the phone sends when it thinks the user has stopped somewhere.

    Only one fix is transmitted, only when a place is detected, and it is used to
    resolve a business name. It is not stored.
    """

    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)
    accuracy_m: Decimal | None = Field(default=None, ge=0)
    business_name: str | None = Field(default=None, max_length=160)
    source: LocationSource = LocationSource.DISCOVERY
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    dwell_minutes: int | None = Field(default=None, ge=0, le=600)
    visited_at: datetime | None = None


class VisitOut(ORMModel):
    id: uuid.UUID
    tracked_location_id: uuid.UUID | None
    business_name: str
    merchant_key: str
    category_id: uuid.UUID | None
    visited_at: datetime
    visit_day: date
    status: VisitStatus
    confidence: Decimal
    distance_m: int | None
    source: LocationSource
    note: str | None
    is_new_place: bool = False
    visit_count: int = 0
    transaction_count: int = 0
    spend_total: Decimal = Decimal("0.00")


class VisitUpdate(APIModel):
    status: VisitStatus


class LocationSettingsOut(APIModel):
    location_features_opted_in: bool
    shopping_intelligence_enabled: bool
    discovery_enabled: bool
    paused: bool
    location_paused_until: datetime | None
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    quiet_hours_timezone: str | None
    notification_cooldown_minutes: int
    visit_history_retention_days: int
    tracked_location_count: int
    supported: dict[str, str]


class LocationSettingsPatch(APIModel):
    location_features_opted_in: bool | None = None
    shopping_intelligence_enabled: bool | None = None
    discovery_enabled: bool | None = None
    pause_minutes: int | None = Field(default=None, ge=0, le=10080)
    quiet_hours_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_timezone: str | None = Field(default=None, max_length=64)
    notification_cooldown_minutes: int | None = Field(default=None, ge=15, le=1440)
    visit_history_retention_days: int | None = Field(default=None, ge=1, le=365)


class VisitPromptOut(APIModel):
    """The shopping guidance attached to a detected visit."""

    visit_id: uuid.UUID
    business_name: str
    tracked: bool
    message: str
    safe_to_spend: Decimal
    store_budget: Decimal | None
    store_remaining: Decimal | None
    typical_spend: Decimal | None
    suggested_limit: Decimal | None
    upcoming_obligations_total: Decimal
    facts: dict[str, str]
    data_is_stale: bool
    suppress_reason: str | None = None
