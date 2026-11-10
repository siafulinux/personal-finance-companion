"""Category suggestions, recurring detection and personalised insights."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import CategorySuggestion, RecurringSeries, User, UserPreference
from app.models.enums import RecurringStatus, SuggestionStatus
from app.schemas.common import APIModel
from app.security.deps import get_current_user
from app.services.intelligence import (
    accept_suggestion,
    detect_recurring_series,
    list_recurring,
    list_suggestions,
    reject_suggestion,
    set_recurring_status,
    unusual_transactions,
)
from app.services.merchant_intelligence import (
    dismiss as dismiss_finding,
    list_dismissed,
    merchant_findings,
    merchant_overview,
    restore as restore_finding,
)
from app.services.personal import merchant_profile, spending_insights
from app.services.recommendations import build_recommendations
from app.utils.money import ZERO, quantize

router = APIRouter(tags=["intelligence"])


class PreferencesPatch(APIModel):
    ai_consent: bool | None = None
    personalized_insights_enabled: bool | None = None
    insight_sensitivity: str | None = Field(default=None, max_length=10)
    recurring_detection_enabled: bool | None = None


def _suggestion_payload(db: Session, suggestion: CategorySuggestion) -> dict:
    from app.models import Category, Transaction

    txn = db.get(Transaction, suggestion.transaction_id)
    category = db.get(Category, suggestion.category_id)
    return {
        "id": str(suggestion.id),
        "transaction_id": str(suggestion.transaction_id),
        "category_id": str(suggestion.category_id),
        "category_name": category.name if category else None,
        "category_color": category.color if category else None,
        "confidence": str(suggestion.confidence),
        "source": suggestion.source,
        "status": suggestion.status,
        "reason": suggestion.reason,
        "created_at": suggestion.created_at,
        "transaction": (
            {
                "description": txn.description,
                "merchant": txn.merchant,
                "amount": str(txn.amount),
                "txn_date": txn.txn_date.isoformat(),
            }
            if txn
            else None
        ),
    }


def _series_payload(series: RecurringSeries) -> dict:
    return {
        "id": str(series.id),
        "merchant_key": series.merchant_key,
        "display_name": series.display_name,
        "merchant": series.merchant,
        "category_id": str(series.category_id) if series.category_id else None,
        "average_amount": str(series.average_amount),
        "last_amount": str(series.last_amount),
        "frequency": series.frequency,
        "interval_days": series.interval_days,
        "occurrences": series.occurrences,
        "first_seen": series.first_seen.isoformat(),
        "last_seen": series.last_seen.isoformat(),
        "next_expected_date": (
            series.next_expected_date.isoformat() if series.next_expected_date else None
        ),
        "confidence": str(series.confidence),
        "is_subscription": series.is_subscription,
        "status": series.status,
        "detail": series.detail,
    }


# ------------------------------------------------------------------ suggestions
@router.get("/suggestions")
def get_suggestions(
    status: str = Query(default=SuggestionStatus.SUGGESTED.value, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = list_suggestions(db, user.id, status=status, limit=limit)
    return {
        "items": [_suggestion_payload(db, s) for s in rows],
        "count": len(rows),
    }


@router.post("/suggestions/{suggestion_id}/accept")
def accept(
    suggestion_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    suggestion = accept_suggestion(db, user, suggestion_id)
    return _suggestion_payload(db, suggestion)


@router.post("/suggestions/{suggestion_id}/reject")
def reject(
    suggestion_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    suggestion = reject_suggestion(db, user, suggestion_id)
    return _suggestion_payload(db, suggestion)


# -------------------------------------------------------------------- recurring
@router.get("/recurring")
def get_recurring(
    include_dismissed: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = list_recurring(db, user.id, include_dismissed=include_dismissed)
    subscriptions = [r for r in rows if r.is_subscription]
    return {
        "items": [_series_payload(r) for r in rows],
        "subscriptions": [
            {
                **_series_payload(r),
                "monthly_equivalent": str(r.average_amount),
            }
            for r in subscriptions
        ],
        "subscription_monthly_total": str(
            quantize(sum((r.average_amount for r in subscriptions), ZERO))
        ),
        "note": (
            "Detected from your own transactions over the last 180 days. "
            "'Subscription' is a heuristic based on cadence and amount."
        ),
    }


@router.post("/recurring/detect")
def detect(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    rows = detect_recurring_series(db, user)
    return {"detected": len(rows), "items": [_series_payload(r) for r in rows]}


@router.post("/recurring/{series_id}/confirm")
def confirm_series(
    series_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    series = set_recurring_status(db, user, series_id, RecurringStatus.CONFIRMED)
    return _series_payload(series)


@router.post("/recurring/{series_id}/dismiss")
def dismiss_series(
    series_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    series = set_recurring_status(db, user, series_id, RecurringStatus.DISMISSED)
    return _series_payload(series)


# --------------------------------------------------------------------- insights
@router.get("/insights/personal")
def get_personal_insights(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    payload = spending_insights(db, user)
    payload["unusual_transactions"] = unusual_transactions(db, user)
    return payload


@router.get("/insights/merchant")
def get_merchant_profile(
    merchant: str = Query(min_length=1, max_length=160),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return merchant_profile(db, user, merchant)


@router.get("/insights/merchants")
def get_merchants(
    days: int = Query(default=90, ge=30, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    payload = merchant_overview(db, user, days=days)
    payload["findings"] = merchant_findings(db, user)
    payload["dismissed"] = list_dismissed(db, user.id)
    return payload


class FindingKey(APIModel):
    key: str = Field(min_length=1, max_length=200)


@router.post("/insights/merchants/dismiss")
def dismiss_merchant_finding(
    payload: FindingKey,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    dismiss_finding(db, user.id, payload.key)
    return {"key": payload.key, "dismissed": True}


@router.post("/insights/merchants/restore")
def restore_merchant_finding(
    payload: FindingKey,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    restore_finding(db, user.id, payload.key)
    return {"key": payload.key, "dismissed": False}


@router.get("/recommendations")
def get_recommendations(
    limit: int = Query(default=8, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return build_recommendations(db, user, limit=limit)


# ------------------------------------------------------------------ preferences
@router.patch("/insights/preferences")
def patch_preferences(
    payload: PreferencesPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    prefs = db.get(UserPreference, user.id)
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
    data = payload.model_dump(exclude_unset=True)
    if data.get("insight_sensitivity") is not None:
        from app.models.enums import InsightSensitivity

        if data["insight_sensitivity"] not in {s.value for s in InsightSensitivity}:
            data.pop("insight_sensitivity")
    for key, value in data.items():
        setattr(prefs, key, value)
    db.flush()
    return {
        "ai_consent": prefs.ai_consent,
        "personalized_insights_enabled": prefs.personalized_insights_enabled,
        "insight_sensitivity": prefs.insight_sensitivity,
        "recurring_detection_enabled": prefs.recurring_detection_enabled,
    }
