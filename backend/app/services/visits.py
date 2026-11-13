"""Shopping locations, detected visits and the guidance shown for them.

Design constraints, in the order they bind:

* Location features are opt-in and can be paused; nothing is recorded while they
  are off.
* A visit is **not** a purchase. It never creates a transaction, and the only
  financial link is a read-only match to purchases the user already has.
* One row per place per day, so repeated detections and phone reboots cannot spam
  notifications.
* A coordinate is used once, to name the place, and is not stored. Tracked places
  keep coordinates because the phone needs them for geofences.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.matching.normalize import normalize_merchant
from app.models import (
    NotificationPreference,
    ShoppingVisit,
    TrackedLocation,
    Transaction,
    User,
    UserPreference,
)
from app.models.enums import (
    LocationSource,
    TransactionStatus,
    TransactionType,
    VisitStatus,
)
from app.schemas.location import (
    LocationSettingsPatch,
    TrackedLocationCreate,
    TrackedLocationUpdate,
    VisitDetectRequest,
)
from app.services.balances import spending_by_category
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.places import haversine_m, resolve_place
from app.services.recommendations import store_guidance
from app.utils.dates import month_bounds, resolve_timezone, today_in, utc_now
from app.utils.money import ZERO, quantize

UNRECOGNISED = "Unrecognised location"


# --------------------------------------------------------------------- helpers
def notification_prefs(db: Session, user: User) -> NotificationPreference:
    prefs = db.get(NotificationPreference, user.id)
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)
        db.flush()
    return prefs


def _in_quiet_hours(prefs: NotificationPreference, user: User, now: datetime) -> bool:
    if not prefs.quiet_hours_start or not prefs.quiet_hours_end:
        return False
    try:
        start_h, start_m = (int(part) for part in prefs.quiet_hours_start.split(":"))
        end_h, end_m = (int(part) for part in prefs.quiet_hours_end.split(":"))
    except ValueError:
        return False
    zone = resolve_timezone(prefs.quiet_hours_timezone or user.timezone)
    local = now.astimezone(zone)
    current = local.hour * 60 + local.minute
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _is_paused(prefs: NotificationPreference, now: datetime) -> bool:
    return prefs.location_paused_until is not None and prefs.location_paused_until > now


def _expire_history(db: Session, user: User, prefs: NotificationPreference) -> None:
    cutoff = utc_now() - timedelta(days=max(1, prefs.visit_history_retention_days))
    rows = db.scalars(
        select(ShoppingVisit).where(
            ShoppingVisit.user_id == user.id, ShoppingVisit.visited_at < cutoff
        )
    )
    for row in rows:
        db.delete(row)


def _month_spend_for_merchant(db: Session, user: User, key: str, today: date) -> Decimal:
    first, _ = month_bounds(today.year, today.month)
    rows = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.tx_type == TransactionType.PURCHASE.value,
            Transaction.status == TransactionStatus.POSTED.value,
            Transaction.txn_date >= first,
            Transaction.txn_date <= today,
        )
    )
    return quantize(
        sum(
            (
                quantize(row.amount)
                for row in rows
                if normalize_merchant(row.merchant or row.description) == key
            ),
            ZERO,
        )
    )


# -------------------------------------------------------------------- locations
def list_locations(db: Session, user: User) -> list[dict[str, object]]:
    today = today_in(user.timezone)
    rows = list(
        db.scalars(
            select(TrackedLocation)
            .where(TrackedLocation.user_id == user.id)
            .order_by(TrackedLocation.sort_order, TrackedLocation.name)
        )
    )
    out: list[dict[str, object]] = []
    for row in rows:
        key = row.merchant_key or normalize_merchant(row.merchant or row.name)
        visits = db.scalar(
            select(func.count(ShoppingVisit.id)).where(
                ShoppingVisit.user_id == user.id,
                ShoppingVisit.tracked_location_id == row.id,
            )
        )
        last_visit = db.scalar(
            select(func.max(ShoppingVisit.visited_at)).where(
                ShoppingVisit.user_id == user.id,
                ShoppingVisit.tracked_location_id == row.id,
            )
        )
        spend = _month_spend_for_merchant(db, user, key, today) if key else ZERO
        out.append(
            {
                "id": row.id,
                "name": row.name,
                "merchant": row.merchant,
                "merchant_key": row.merchant_key,
                "address": row.address,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "radius_m": row.radius_m,
                "category_id": row.category_id,
                "monthly_budget": row.monthly_budget,
                "notify_enabled": row.notify_enabled,
                "is_active": row.is_active,
                "source": row.source,
                "notes": row.notes,
                "created_at": row.created_at,
                "visit_count": int(visits or 0),
                "last_visit_at": last_visit,
                "month_spend": spend,
                "budget_remaining": (
                    quantize(max(quantize(row.monthly_budget) - spend, ZERO))
                    if row.monthly_budget is not None
                    else None
                ),
            }
        )
    return out


def get_location(db: Session, user_id: uuid.UUID, location_id: uuid.UUID) -> TrackedLocation:
    row = db.scalar(
        select(TrackedLocation).where(
            TrackedLocation.id == location_id, TrackedLocation.user_id == user_id
        )
    )
    if row is None:
        raise NotFoundError("Location not found.")
    return row


def create_location(
    db: Session, user: User, payload: TrackedLocationCreate
) -> TrackedLocation:
    row = TrackedLocation(
        user_id=user.id,
        name=payload.name.strip(),
        merchant=payload.merchant,
        merchant_key=normalize_merchant(payload.merchant or payload.name),
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_m=payload.radius_m,
        category_id=payload.category_id,
        monthly_budget=quantize(payload.monthly_budget) if payload.monthly_budget is not None else None,
        notify_enabled=payload.notify_enabled,
        is_active=payload.is_active,
        source=LocationSource.MANUAL.value,
        notes=payload.notes,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A location with that name already exists.") from exc
    return row


def update_location(
    db: Session, user: User, location_id: uuid.UUID, payload: TrackedLocationUpdate
) -> TrackedLocation:
    row = get_location(db, user.id, location_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if isinstance(value, Decimal):
            value = quantize(value)
        if hasattr(value, "value"):
            value = value.value
        setattr(row, field, value)
    if (row.latitude is None) != (row.longitude is None):
        raise ValidationError("Provide both a latitude and a longitude, or neither.")
    if "name" in data or "merchant" in data:
        row.merchant_key = normalize_merchant(row.merchant or row.name)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Another location already uses that name.") from exc
    return row


def delete_location(db: Session, user_id: uuid.UUID, location_id: uuid.UUID) -> None:
    row = get_location(db, user_id, location_id)
    db.delete(row)
    db.flush()


def match_tracked_location(
    db: Session, user: User, latitude: Decimal, longitude: Decimal
) -> TrackedLocation | None:
    best: tuple[float, TrackedLocation] | None = None
    for row in db.scalars(
        select(TrackedLocation).where(
            TrackedLocation.user_id == user.id,
            TrackedLocation.is_active.is_(True),
            TrackedLocation.latitude.is_not(None),
            TrackedLocation.longitude.is_not(None),
        )
    ):
        distance = haversine_m(
            float(latitude), float(longitude), float(row.latitude), float(row.longitude)
        )
        if distance <= row.radius_m and (best is None or distance < best[0]):
            best = (distance, row)
    return best[1] if best else None


# ----------------------------------------------------------------------- visits
def _visit_payload(
    db: Session, user: User, visit: ShoppingVisit, *, today: date
) -> dict[str, object]:
    count = db.scalar(
        select(func.count(ShoppingVisit.id)).where(
            ShoppingVisit.user_id == user.id,
            ShoppingVisit.merchant_key == visit.merchant_key,
        )
    )
    purchases = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.tx_type == TransactionType.PURCHASE.value,
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date == visit.visit_day,
            )
        )
    )
    matched = [
        txn
        for txn in purchases
        if normalize_merchant(txn.merchant or txn.description) == visit.merchant_key
    ]
    return {
        "id": visit.id,
        "tracked_location_id": visit.tracked_location_id,
        "business_name": visit.business_name,
        "merchant_key": visit.merchant_key,
        "category_id": visit.category_id,
        "visited_at": visit.visited_at,
        "visit_day": visit.visit_day,
        "status": visit.status,
        "confidence": visit.confidence,
        "distance_m": visit.distance_m,
        "source": visit.source,
        "note": visit.note,
        "is_new_place": int(count or 0) <= 1,
        "visit_count": int(count or 0),
        "transaction_count": len(matched),
        "spend_total": quantize(sum((quantize(txn.amount) for txn in matched), ZERO)),
    }


def list_visits(db: Session, user: User, *, days: int = 90, limit: int = 200) -> dict[str, object]:
    prefs = notification_prefs(db, user)
    _expire_history(db, user, prefs)
    db.flush()
    today = today_in(user.timezone)
    cutoff = utc_now() - timedelta(days=max(1, min(days, 365)))
    rows = list(
        db.scalars(
            select(ShoppingVisit)
            .where(ShoppingVisit.user_id == user.id, ShoppingVisit.visited_at >= cutoff)
            .order_by(ShoppingVisit.visited_at.desc())
            .limit(limit)
        )
    )
    items = [_visit_payload(db, user, visit, today=today) for visit in rows]
    return {
        "items": items,
        "count": len(items),
        "suggested": len([item for item in items if item["status"] == VisitStatus.SUGGESTED.value]),
        "tracked_locations": len(
            list(
                db.scalars(
                    select(TrackedLocation.id).where(TrackedLocation.user_id == user.id)
                )
            )
        ),
        "retention_days": prefs.visit_history_retention_days,
        "note": (
            "A visit records that the app noticed you somewhere. It is not a purchase, and no "
            "coordinates are stored."
        ),
    }


def _suppressed_reason(
    db: Session,
    user: User,
    prefs: NotificationPreference,
    visited_at: datetime,
    *,
    visit_id: uuid.UUID,
) -> str | None:
    if prefs.location_paused_until and prefs.location_paused_until > utc_now():
        return "Shopping Intelligence is paused."
    if not prefs.shopping_intelligence_enabled:
        return "Shopping Intelligence is turned off."
    if _in_quiet_hours(prefs, user, visited_at):
        return "Quiet hours are active."
    cooldown_start = visited_at - timedelta(minutes=prefs.notification_cooldown_minutes)
    recent = db.scalar(
        select(func.count(ShoppingVisit.id)).where(
            ShoppingVisit.user_id == user.id,
            ShoppingVisit.visited_at > cooldown_start,
            ShoppingVisit.visited_at <= visited_at,
            # The visit being decided is already flushed, so it is one of the rows this
            # counts. It is excluded by id, not by time: two detections can carry the
            # same instant (a retry, or two places seen within the same second), and
            # `< visited_at` dropped both of those, announcing the second place inside
            # the window the first had just opened.
            ShoppingVisit.id != visit_id,
        )
    )
    if recent:
        return "You were notified about another place recently."
    return None


def detect_visit(
    db: Session, user: User, payload: VisitDetectRequest
) -> dict[str, object]:
    prefs = notification_prefs(db, user)
    now = utc_now()
    if not prefs.location_features_opted_in:
        return {
            "recorded": False,
            "reason": "Location features have not been enabled on this account.",
            "visit": None,
            "prompt": None,
            "notify": False,
        }

    tracked = match_tracked_location(db, user, payload.latitude, payload.longitude)
    confidence = float(payload.confidence) if payload.confidence is not None else None
    ambiguous = False
    name: str
    distance: int | None = None
    source = payload.source.value

    if tracked is not None:
        name = tracked.name
        distance = haversine_m(
            float(payload.latitude), float(payload.longitude),
            float(tracked.latitude), float(tracked.longitude),
        )
        confidence = max(confidence or 0, 0.9)
        source = LocationSource.GEOFENCE.value
    elif payload.business_name:
        name = payload.business_name.strip()[:160]
        confidence = confidence if confidence is not None else 0.75
    else:
        best, _candidates, ambiguous = resolve_place(
            float(payload.latitude), float(payload.longitude)
        )
        if best is None:
            name = UNRECOGNISED
            confidence = 0.2
        else:
            name = best.name
            distance = best.distance_m
            # An ambiguous fix (mall, overlapping shops) must not be announced.
            confidence = min(confidence or best.confidence, best.confidence)
            if ambiguous:
                confidence = min(confidence, 0.4)
            source = LocationSource.DISCOVERY.value

    key = normalize_merchant(name) or f"place-{float(payload.latitude):.3f}-{float(payload.longitude):.3f}"
    visited_at = payload.visited_at or now
    visit_day = visited_at.astimezone(resolve_timezone(user.timezone)).date()

    existing = db.scalar(
        select(ShoppingVisit).where(
            ShoppingVisit.user_id == user.id,
            ShoppingVisit.merchant_key == key,
            ShoppingVisit.visit_day == visit_day,
        )
    )
    if existing is not None:
        return {
            "recorded": False,
            "reason": "Already recorded for today.",
            "visit": _visit_payload(db, user, existing, today=visit_day),
            "prompt": None,
            "notify": False,
        }

    ignored = db.scalar(
        select(ShoppingVisit.id).where(
            ShoppingVisit.user_id == user.id,
            ShoppingVisit.merchant_key == key,
            ShoppingVisit.status == VisitStatus.IGNORED.value,
        )
    )
    if ignored is not None:
        return {
            "recorded": False,
            "reason": "This location was dismissed and will not be suggested again.",
            "visit": None,
            "prompt": None,
            "notify": False,
        }

    confidence_value = quantize(Decimal(str(min(max(confidence or 0, 0), 1))))
    if tracked is not None:
        status = VisitStatus.CONFIRMED.value
    elif (
        prefs.discovery_enabled
        and confidence_value >= quantize(Decimal(str(settings.visit_notification_min_confidence)))
        and not ambiguous
        and name != UNRECOGNISED
    ):
        status = VisitStatus.SUGGESTED.value
    else:
        status = VisitStatus.DETECTED.value

    visit = ShoppingVisit(
        user_id=user.id,
        tracked_location_id=tracked.id if tracked is not None else None,
        business_name=name,
        merchant_key=key,
        category_id=tracked.category_id if tracked is not None else None,
        visited_at=visited_at,
        visit_day=visit_day,
        status=status,
        confidence=confidence_value,
        distance_m=distance,
        source=source,
        note=None if not ambiguous else "Several businesses are within a few metres of this point.",
    )
    db.add(visit)
    try:
        db.flush()
    except IntegrityError:
        # Another device won the race for today's row; that is the desired outcome.
        db.rollback()
        existing = db.scalar(
            select(ShoppingVisit).where(
                ShoppingVisit.user_id == user.id,
                ShoppingVisit.merchant_key == key,
                ShoppingVisit.visit_day == visit_day,
            )
        )
        return {
            "recorded": False,
            "reason": "Already recorded on another device today.",
            "visit": _visit_payload(db, user, existing, today=visit_day) if existing else None,
            "prompt": None,
            "notify": False,
        }

    suppress = _suppressed_reason(db, user, prefs, visited_at, visit_id=visit.id)
    if tracked is not None and not tracked.notify_enabled:
        suppress = "Notifications are off for this location."

    prompt = None
    notify = False
    if status in (VisitStatus.SUGGESTED.value, VisitStatus.CONFIRMED.value):
        category_id = tracked.category_id if tracked is not None else None
        guidance = store_guidance(
            db,
            user,
            merchant=name,
            category_id=category_id,
            store_budget=tracked.monthly_budget if tracked is not None else None,
        )
        notify = suppress is None
        prompt = {
            "visit_id": visit.id,
            "business_name": name,
            "tracked": tracked is not None,
            "message": guidance["message"],
            "safe_to_spend": guidance["safe_to_spend"],
            "store_budget": guidance["store_budget"],
            "store_remaining": guidance["store_remaining"],
            "typical_spend": guidance["typical_spend"],
            "suggested_limit": guidance["suggested_limit"],
            "upcoming_obligations_total": guidance["upcoming_obligations_total"],
            "facts": guidance["facts"],
            "data_is_stale": guidance["data_is_stale"],
            "suppress_reason": suppress,
        }

    return {
        "recorded": True,
        "reason": None,
        "visit": _visit_payload(db, user, visit, today=visit_day),
        "prompt": prompt,
        "notify": notify,
    }


def record_arrival(db: Session, user: User, location_id: uuid.UUID) -> dict[str, object]:
    """A geofence fired for a place the user already tracks.

    The phone sends an identifier, not a coordinate: the server already knows where
    the place is, so an arrival never transmits a position.
    """
    prefs = notification_prefs(db, user)
    if not prefs.location_features_opted_in:
        return {
            "recorded": False,
            "reason": "Location features have not been enabled on this account.",
            "visit": None,
            "prompt": None,
            "notify": False,
        }
    location = get_location(db, user.id, location_id)
    if not location.is_active:
        return {
            "recorded": False,
            "reason": "This place is no longer monitored.",
            "visit": None,
            "prompt": None,
            "notify": False,
        }

    now = utc_now()
    visit_day = now.astimezone(resolve_timezone(user.timezone)).date()
    key = location.merchant_key or normalize_merchant(location.merchant or location.name)

    existing = db.scalar(
        select(ShoppingVisit).where(
            ShoppingVisit.user_id == user.id,
            ShoppingVisit.merchant_key == key,
            ShoppingVisit.visit_day == visit_day,
        )
    )
    if existing is not None:
        return {
            "recorded": False,
            "reason": "Already recorded for today.",
            "visit": _visit_payload(db, user, existing, today=visit_day),
            "prompt": None,
            "notify": False,
        }

    visit = ShoppingVisit(
        user_id=user.id,
        tracked_location_id=location.id,
        business_name=location.name,
        merchant_key=key,
        category_id=location.category_id,
        visited_at=now,
        visit_day=visit_day,
        status=VisitStatus.CONFIRMED.value,
        confidence=Decimal("0.950"),
        distance_m=0,
        source=LocationSource.GEOFENCE.value,
    )
    db.add(visit)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ShoppingVisit).where(
                ShoppingVisit.user_id == user.id,
                ShoppingVisit.merchant_key == key,
                ShoppingVisit.visit_day == visit_day,
            )
        )
        return {
            "recorded": False,
            "reason": "Already recorded on another device today.",
            "visit": _visit_payload(db, user, existing, today=visit_day) if existing else None,
            "prompt": None,
            "notify": False,
        }

    suppress = _suppressed_reason(db, user, prefs, now, visit_id=visit.id)
    if not location.notify_enabled:
        suppress = "Notifications are off for this location."
    guidance = store_guidance(
        db,
        user,
        merchant=location.name,
        category_id=location.category_id,
        store_budget=location.monthly_budget,
    )
    prompt = {
        "visit_id": visit.id,
        "business_name": location.name,
        "tracked": True,
        "message": guidance["message"],
        "safe_to_spend": guidance["safe_to_spend"],
        "store_budget": guidance["store_budget"],
        "store_remaining": guidance["store_remaining"],
        "typical_spend": guidance["typical_spend"],
        "suggested_limit": guidance["suggested_limit"],
        "upcoming_obligations_total": guidance["upcoming_obligations_total"],
        "facts": guidance["facts"],
        "data_is_stale": guidance["data_is_stale"],
        "suppress_reason": suppress,
    }
    return {
        "recorded": True,
        "reason": None,
        "visit": _visit_payload(db, user, visit, today=visit_day),
        "prompt": prompt,
        "notify": suppress is None,
    }


def set_visit_status(
    db: Session, user: User, visit_id: uuid.UUID, status: VisitStatus
) -> ShoppingVisit:
    visit = db.scalar(
        select(ShoppingVisit).where(
            ShoppingVisit.id == visit_id, ShoppingVisit.user_id == user.id
        )
    )
    if visit is None:
        raise NotFoundError("Visit not found.")
    visit.status = status.value
    if status == VisitStatus.IGNORED:
        # Ignoring is permanent for this place: every future detection is dropped.
        siblings = db.scalars(
            select(ShoppingVisit).where(
                ShoppingVisit.user_id == user.id,
                ShoppingVisit.merchant_key == visit.merchant_key,
            )
        )
        for sibling in siblings:
            sibling.status = VisitStatus.IGNORED.value
    db.flush()
    return visit


def delete_visit(db: Session, user_id: uuid.UUID, visit_id: uuid.UUID) -> None:
    visit = db.scalar(
        select(ShoppingVisit).where(
            ShoppingVisit.id == visit_id, ShoppingVisit.user_id == user_id
        )
    )
    if visit is None:
        raise NotFoundError("Visit not found.")
    db.delete(visit)
    db.flush()


def clear_history(db: Session, user_id: uuid.UUID) -> int:
    rows = list(
        db.scalars(select(ShoppingVisit).where(ShoppingVisit.user_id == user_id))
    )
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)


def location_settings(db: Session, user: User) -> dict[str, object]:
    prefs = notification_prefs(db, user)
    count = db.scalar(
        select(func.count(TrackedLocation.id)).where(TrackedLocation.user_id == user.id)
    )
    return {
        "location_features_opted_in": prefs.location_features_opted_in,
        "shopping_intelligence_enabled": prefs.shopping_intelligence_enabled,
        "discovery_enabled": prefs.discovery_enabled,
        "paused": _is_paused(prefs, utc_now()),
        "location_paused_until": prefs.location_paused_until,
        "quiet_hours_start": prefs.quiet_hours_start,
        "quiet_hours_end": prefs.quiet_hours_end,
        "quiet_hours_timezone": prefs.quiet_hours_timezone,
        "notification_cooldown_minutes": prefs.notification_cooldown_minutes,
        "visit_history_retention_days": prefs.visit_history_retention_days,
        "tracked_location_count": int(count or 0),
        "supported": {
            "business_lookup": settings.places_provider,
            "lookup_attribution": (
                "Business names from OpenStreetMap contributors (ODbL)."
                if settings.places_provider == "osm"
                else "Business lookup is disabled; detections are recorded unnamed."
            ),
        },
    }


def update_location_settings(
    db: Session, user: User, payload: LocationSettingsPatch
) -> dict[str, object]:
    prefs = notification_prefs(db, user)
    data = payload.model_dump(exclude_unset=True)
    pause_minutes = data.pop("pause_minutes", None)
    for field, value in data.items():
        setattr(prefs, field, value)
    if pause_minutes is not None:
        prefs.location_paused_until = (
            utc_now() + timedelta(minutes=pause_minutes) if pause_minutes > 0 else None
        )
    # Consent and the master switch move together: turning the feature on without
    # consent would be recording location against an unanswered question.
    if data.get("location_features_opted_in") is False:
        prefs.shopping_intelligence_enabled = False
        prefs.discovery_enabled = False
    if data.get("shopping_intelligence_enabled") is True and not prefs.location_features_opted_in:
        prefs.location_features_opted_in = True
    if data.get("discovery_enabled") is True and not prefs.shopping_intelligence_enabled:
        prefs.discovery_enabled = False
    db.flush()
    return location_settings(db, user)


def add_tracked_from_visit(
    db: Session, user: User, visit_id: uuid.UUID, payload: TrackedLocationCreate
) -> TrackedLocation:
    """Turn a suggested visit into a monitored place.

    Never automatic: the user explicitly adds the location, and this is the only
    path from a detection to the tracked list.
    """
    visit = db.scalar(
        select(ShoppingVisit).where(
            ShoppingVisit.id == visit_id, ShoppingVisit.user_id == user.id
        )
    )
    if visit is None:
        raise NotFoundError("Visit not found.")
    location = create_location(db, user, payload)
    visit.tracked_location_id = location.id
    visit.status = VisitStatus.CONFIRMED.value
    visit.category_id = location.category_id
    db.flush()
    return location


def spending_by_store(db: Session, user: User, *, days: int = 90) -> dict[str, object]:
    """Month-to-date spend for each tracked location (actual transactions only)."""
    today = today_in(user.timezone)
    rows = list_locations(db, user)
    return {
        "today": today.isoformat(),
        "locations": [
            {
                "location_id": row["id"],
                "name": row["name"],
                "month_spend": str(row["month_spend"]),
                "monthly_budget": str(row["monthly_budget"]) if row["monthly_budget"] is not None else None,
                "budget_remaining": str(row["budget_remaining"]) if row["budget_remaining"] is not None else None,
                "transaction_backed": True,
            }
            for row in rows
        ],
    }
