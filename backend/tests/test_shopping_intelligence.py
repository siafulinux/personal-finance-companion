"""Phase 4: location-aware Shopping Check, merchant intelligence and recommendations."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import ShoppingVisit, TrackedLocation, Transaction, User
from app.models.enums import VisitStatus
from app.schemas.location import (
    LocationSettingsPatch,
    TrackedLocationCreate,
    TrackedLocationUpdate,
    VisitDetectRequest,
)
from app.services import visits as visit_service
from app.services.merchant_intelligence import (
    dismiss,
    merchant_findings,
    merchant_overview,
)
from app.services.recommendations import build_recommendations, store_guidance
from app.services.users import register_user
from app.utils.dates import add_months, today_in, utc_now
from tests.conftest import make_transaction

HOME = (Decimal("30.451500"), Decimal("-91.187100"))


def _enable(db, user, **overrides) -> dict:
    """Opt in the way the app does: consent, then the master switch."""
    visit_service.update_location_settings(
        db, user, LocationSettingsPatch(location_features_opted_in=True)
    )
    visit_service.update_location_settings(
        db, user, LocationSettingsPatch(shopping_intelligence_enabled=True)
    )
    overrides.setdefault("discovery_enabled", True)
    overrides.setdefault("notification_cooldown_minutes", 120)
    result = visit_service.update_location_settings(
        db, user, LocationSettingsPatch(**overrides)
    )
    db.commit()
    return result


def _detect(db, user, **kwargs) -> dict:
    payload = VisitDetectRequest(
        latitude=kwargs.pop("latitude", HOME[0]),
        longitude=kwargs.pop("longitude", HOME[1]),
        **kwargs,
    )
    return visit_service.detect_visit(db, user, payload)


# ----------------------------------------------------------------- preferences
def test_location_features_are_off_until_the_user_opts_in(db, user):
    result = _detect(db, user, business_name="Target")
    assert result["recorded"] is False
    assert "not been enabled" in result["reason"]
    assert db.scalar(select(func.count(ShoppingVisit.id))) == 0


def test_consent_and_master_switch_move_together(db, user):
    settings_row = visit_service.update_location_settings(
        db, user, LocationSettingsPatch(shopping_intelligence_enabled=True)
    )
    assert settings_row["location_features_opted_in"] is True
    assert settings_row["shopping_intelligence_enabled"] is True

    off = visit_service.update_location_settings(
        db, user, LocationSettingsPatch(location_features_opted_in=False)
    )
    assert off["shopping_intelligence_enabled"] is False
    assert off["discovery_enabled"] is False


# ----------------------------------------------------------------------- visits
def test_new_place_is_suggested_and_not_announced_twice(db, user, account, prefs):
    _enable(db, user)
    first = _detect(db, user, business_name="Target", confidence=Decimal("0.8"))
    assert first["recorded"] is True
    assert first["visit"]["status"] == VisitStatus.SUGGESTED.value
    assert first["notify"] is True
    assert first["prompt"]["business_name"] == "Target"
    assert Decimal(first["prompt"]["suggested_limit"]) > Decimal("0")

    second = _detect(db, user, business_name="Target", confidence=Decimal("0.8"))
    assert second["recorded"] is False
    assert "Already recorded" in second["reason"]
    assert second["notify"] is False
    assert db.scalar(select(func.count(ShoppingVisit.id))) == 1


def test_a_visit_is_never_a_transaction(db, user, account, prefs):
    _enable(db, user)
    before = db.scalar(select(func.count(Transaction.id)))
    _detect(db, user, business_name="Kroger")
    db.commit()
    assert db.scalar(select(func.count(Transaction.id))) == before


def test_cooldown_suppresses_a_second_notification(db, user, account, prefs):
    _enable(db, user, notification_cooldown_minutes=120)
    first = _detect(db, user, business_name="Target")
    assert first["notify"] is True
    second = _detect(db, user, business_name="Kroger")
    assert second["recorded"] is True
    assert second["notify"] is False
    assert second["prompt"]["suppress_reason"]


def test_two_visits_at_the_same_instant_still_suppress_the_second(db, user, account, prefs):
    """The cooldown is about the pair of visits, not about their order.

    Two detections can carry an identical `visited_at` -- a retried request, or two
    places seen inside the same second. The row under decision is excluded by id, so
    `<= visited_at` still sees the other one; excluding by time instead dropped both
    and announced the second place inside the window the first had just opened.
    """
    _enable(db, user, notification_cooldown_minutes=120)
    moment = utc_now().replace(microsecond=0)

    first = _detect(db, user, business_name="Target", visited_at=moment)
    assert first["notify"] is True

    second = _detect(db, user, business_name="Kroger", visited_at=moment)
    assert second["recorded"] is True
    assert second["notify"] is False
    assert "another place recently" in (second["prompt"]["suppress_reason"] or "")


def test_quiet_hours_suppress_the_notification_but_keep_the_history(db, user, account, prefs):
    _enable(db, user, quiet_hours_start="00:00", quiet_hours_end="23:59", quiet_hours_timezone="UTC")
    result = _detect(db, user, business_name="Target")
    assert result["recorded"] is True
    assert result["notify"] is False
    assert "Quiet hours" in (result["prompt"]["suppress_reason"] or "")


def test_pausing_stops_new_visits(db, user, account, prefs):
    _enable(db, user)
    visit_service.update_location_settings(db, user, LocationSettingsPatch(pause_minutes=60))
    db.commit()
    result = _detect(db, user, business_name="Target")
    assert result["recorded"] is True
    assert result["notify"] is False
    assert "paused" in (result["prompt"]["suppress_reason"] or "").lower()


def test_ignoring_a_place_stops_future_suggestions(db, user, account, prefs):
    _enable(db, user)
    first = _detect(db, user, business_name="Spirit Halloween")
    visit_service.set_visit_status(db, user, first["visit"]["id"], VisitStatus.IGNORED)
    db.commit()

    tomorrow = utc_now() + timedelta(days=1)
    result = _detect(db, user, business_name="Spirit Halloween", visited_at=tomorrow)
    assert result["recorded"] is False
    assert "dismissed" in result["reason"]


def test_ambiguous_locations_are_not_announced(db, user, account, prefs, monkeypatch):
    _enable(db, user)
    # A fix the app itself reports as low confidence must stay a quiet detection.
    result = _detect(db, user, latitude=Decimal("30.40"), longitude=Decimal("-91.10"), confidence=Decimal("0.2"))
    assert result["recorded"] is True
    assert result["visit"]["status"] == VisitStatus.DETECTED.value
    assert result["notify"] is False


def test_known_place_is_recognised_without_a_business_lookup(db, user, account, prefs, monkeypatch):
    monkeypatch.setattr(settings, "places_provider", "none")
    _enable(db, user)
    location = visit_service.create_location(
        db,
        user,
        TrackedLocationCreate(
            name="Target Perkins",
            latitude=HOME[0],
            longitude=HOME[1],
            radius_m=150,
            monthly_budget=Decimal("200.00"),
        ),
    )
    db.commit()

    result = _detect(db, user)
    assert result["recorded"] is True
    assert result["visit"]["status"] == VisitStatus.CONFIRMED.value
    assert result["visit"]["tracked_location_id"] == location.id
    assert result["prompt"]["tracked"] is True
    assert Decimal(result["prompt"]["store_budget"]) == Decimal("200.00")
    assert result["notify"] is True


def test_lookup_failure_records_an_unnamed_detection(db, user, account, prefs, monkeypatch):
    monkeypatch.setattr(settings, "places_provider", "none")
    _enable(db, user)
    result = _detect(db, user)
    assert result["recorded"] is True
    assert result["visit"]["business_name"] == "Unrecognised location"
    assert result["visit"]["status"] == VisitStatus.DETECTED.value
    assert result["notify"] is False


def test_history_can_be_cleared_and_is_scoped_to_one_user(db, user, account, prefs):
    _enable(db, user)
    _detect(db, user, business_name="Target")
    db.commit()

    other = register_user(
        db,
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123",
        display_name="Other",
        timezone="UTC",
    )
    db.commit()
    assert visit_service.list_visits(db, other)["count"] == 0
    extra = _detect(db, user, business_name="Kroger")["visit"]["id"]
    with pytest.raises(Exception):
        visit_service.delete_visit(db, other.id, extra)

    assert visit_service.clear_history(db, user.id) >= 2
    db.commit()
    assert visit_service.list_visits(db, user)["count"] == 0


# -------------------------------------------------------------------- locations
def test_location_crud_and_coordinate_validation(db, user, account):
    # Half a coordinate is not a location, and the schema refuses it up front.
    with pytest.raises(Exception):
        TrackedLocationCreate(name="Half a place", latitude=Decimal("30.4"))

    location = visit_service.create_location(
        db, user, TrackedLocationCreate(name="Corner Store", monthly_budget=Decimal("80.00"))
    )
    db.commit()
    updated = visit_service.update_location(
        db, user, location.id, TrackedLocationUpdate(notify_enabled=False)
    )
    assert updated.notify_enabled is False
    assert updated.monthly_budget == Decimal("80.00")


def test_duplicate_location_names_are_rejected(db, user, account):
    visit_service.create_location(db, user, TrackedLocationCreate(name="Target"))
    db.commit()
    with pytest.raises(Exception):
        visit_service.create_location(db, user, TrackedLocationCreate(name="Target"))


# ------------------------------------------------------- merchant intelligence
def test_insufficient_history_produces_no_behavioural_claim(db, user, account):
    make_transaction(db, user, account, amount="40.00", merchant="Target", description="TARGET")
    db.commit()
    overview = merchant_overview(db, user)
    row = overview["merchants"][0]
    assert row["has_enough_history"] is False
    assert row["confidence"] == "low"
    assert merchant_findings(db, user) == []


def test_merchant_spending_increase_is_reported_with_evidence(db, user, account):
    today = today_in(user.timezone)
    # Prior 90-day window: one purchase. Current window: four, much larger.
    make_transaction(
        db, user, account, amount="20.00", merchant="Target", description="TARGET",
        txn_date=today - timedelta(days=120),
    )
    for days_ago in (88, 68, 48, 28, 8):
        make_transaction(
            db, user, account, amount="60.00", merchant="Target", description="TARGET STORE",
            txn_date=today - timedelta(days=days_ago),
        )
    db.commit()

    overview = merchant_overview(db, user)
    row = next(item for item in overview["merchants"] if item["merchant_key"] == "target")
    assert row["has_enough_history"] is True
    assert Decimal(row["change_percent"]) > Decimal("25")

    findings = merchant_findings(db, user)
    growth = next(item for item in findings if item["type"] == "merchant_spending_increase")
    assert growth["merchant"] == "Target" or growth["merchant"] == "TARGET"
    assert growth["evidence"]["current_window_total"]
    assert growth["confidence"] in {"medium", "high"}

    dismiss(db, user.id, growth["key"])
    db.commit()
    assert growth["key"] not in {item["key"] for item in merchant_findings(db, user)}


def test_budget_pressure_uses_the_real_budget(db, user, account, prefs):
    from app.models import Category
    from app.schemas.planning import BudgetAllocationInput, BudgetCreate
    from app.services.budgets import create_budget

    # Registration seeds the default categories.
    groceries = db.scalar(
        select(Category).where(Category.user_id == user.id, Category.name == "Groceries")
    )
    assert groceries is not None
    today = today_in(user.timezone)
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[BudgetAllocationInput(category_id=groceries.id, amount=Decimal("50.00"))],
        ),
    )
    # Enough months of history to clear the evidence floor, with the current
    # month already over its 50.00 allocation.
    # Anchored to calendar months rather than "N days ago": the finding needs
    # spend in the current month, and day offsets land entirely in the previous
    # month when the suite runs on the 1st or 2nd. Three purchases today (all on
    # the 1st at worst, so still this month) plus one in each of the two
    # preceding months clears the three-month floor, and the oldest is at most
    # ~77 days back, inside the 90-day window the profile reads.
    month_start = today.replace(day=1)
    dates = [
        today,
        max(month_start, today - timedelta(days=1)),
        max(month_start, today - timedelta(days=2)),
        add_months(month_start, -1) + timedelta(days=14),
        add_months(month_start, -2) + timedelta(days=14),
    ]
    for when in dates:
        make_transaction(
            db, user, account, amount="40.00", merchant="Kroger", description="KROGER",
            txn_date=when, category_id=groceries.id,
        )
    db.commit()

    findings = merchant_findings(db, user)
    pressure = [item for item in findings if item["type"] == "merchant_budget_pressure"]
    assert pressure, "an over-budget category with a dominant merchant should be reported"
    assert pressure[0]["evidence"]["share_of_category_percent"]


# --------------------------------------------------------------- recommendations
def test_recommendations_are_structured_and_explainable(db, user, account, prefs):
    payload = build_recommendations(db, user)
    assert payload["items"]
    item = payload["items"][0]
    for field in ("key", "kind", "title", "message", "confidence", "facts", "severity"):
        assert field in item
    assert payload["data_freshness"]["stale"] in (True, False)
    # No item ever claims to have changed a record.
    assert "never move money" in payload["note"]


def test_store_guidance_reports_missing_history_honestly(db, user, account, prefs):
    guidance = store_guidance(db, user, merchant="Never Visited Co", category_id=None)
    assert guidance["has_history"] is False
    assert guidance["facts"]["typical_spend"] == "not enough history"
    assert Decimal(guidance["suggested_limit"]) <= Decimal(guidance["facts"]["safe_to_spend"])


def test_shopping_prompt_uses_live_figures(db, user, account, prefs):
    _enable(db, user)
    result = _detect(db, user, business_name="Target")
    prompt = result["prompt"]
    assert Decimal(prompt["safe_to_spend"]) >= Decimal("0")
    assert Decimal(prompt["facts"]["safe_to_spend"]) == Decimal(prompt["safe_to_spend"])
