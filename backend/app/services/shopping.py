"""Shopping Check: deterministic answers from the financial engine."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculations.safe_to_spend import evaluate_purchase
from app.models import IncomeSource, NotificationPreference, User
from app.models.enums import AccountType
from app.services.bills import horizon_candidates, next_payday_date, occurrence_dict
from app.services.personal import merchant_advice
from app.services.safe_to_spend import category_availability, compute
from app.utils.dates import today_in
from app.utils.money import ZERO, format_money, quantize


def shopping_check(
    db: Session,
    user: User,
    *,
    store_name: str,
    category_id: uuid.UUID,
    expected_amount: Decimal | None = None,
    note: str | None = None,
) -> dict[str, object]:
    today = today_in(user.timezone)
    safe = compute(db, user)
    availability = category_availability(db, user, category_id, overall=safe)

    upcoming = [
        occurrence_dict(o, today)
        for o in horizon_candidates(db, user.id, today, safe.horizon_end)
    ]
    payday = next_payday_date(db, user.id, today)
    notifications = db.get(NotificationPreference, user.id)

    bills_covered = safe.projected_shortfall == ZERO
    bills_sentence = (
        "Your upcoming bills are covered under the current plan."
        if bills_covered
        else f"You are projected short by {format_money(safe.projected_shortfall)} before your next payday."
    )

    purchase = None
    if expected_amount is not None:
        purchase = evaluate_purchase(
            amount=quantize(expected_amount),
            category_available=availability,
            safe_to_spend=safe.safe_to_spend,
        )

    if purchase:
        message = (
            f"{purchase['message']} {bills_sentence}"
        )
    else:
        message = (
            f"You have {format_money(safe.safe_to_spend)} available overall and "
            f"{format_money(availability.remaining)} remaining in {availability.category_name}. {bills_sentence}"
        )

    # Merchant history, with a minimum-history guard inside the service: an unknown
    # merchant produces an explicit "not enough history" rather than a guess.
    advice = merchant_advice(
        db,
        user,
        merchant=store_name,
        category_id=category_id,
        category_remaining=availability.remaining,
    )
    if advice.get("has_enough_history"):
        message = f"{message} {advice['message']}"
        if advice.get("suggested_limit") is not None:
            message = (
                f"{message} A limit of {format_money(advice['suggested_limit'])} this visit keeps you "
                "inside both your usual spend and the remaining budget."
            )

    warnings = list(safe.warnings)
    if availability.upcoming_commitments > availability.remaining:
        warnings.append(
            f"Upcoming {availability.category_name} bills exceed the remaining category budget."
        )
    if expected_amount is not None and purchase and not purchase["allowed"]:
        warnings.append("This purchase is not recommended under your current plan.")
    if advice.get("has_enough_history") and advice.get("tendency") == "overspending":
        warnings.append(
            f"You are ahead of your usual monthly spending at {advice['merchant']}."
        )

    return {
        "store_name": store_name.strip(),
        "category": availability.as_dict(),
        "safe_to_spend": safe.as_dict(),
        "expected_amount": str(quantize(expected_amount)) if expected_amount is not None else None,
        "purchase": purchase,
        "merchant_advice": advice,
        "message": message,
        "upcoming_bills": upcoming,
        "next_payday": payday.isoformat() if payday else None,
        "bills_covered": bills_covered,
        "projected_shortfall": str(safe.projected_shortfall),
        "warnings": warnings,
        "note": note,
        "notification_context": {
            "shopping_assistant_enabled": bool(
                notifications and notifications.shopping_assistant_enabled
            ),
            "quiet_hours_start": notifications.quiet_hours_start if notifications else None,
            "quiet_hours_end": notifications.quiet_hours_end if notifications else None,
            "quiet_hours_timezone": notifications.quiet_hours_timezone if notifications else None,
            "location_opt_in": bool(notifications and notifications.location_features_opted_in),
        },
        "as_of": safe.as_of.isoformat(),
    }


def shopping_defaults(db: Session, user: User) -> dict[str, object]:
    """Context the future Android geofence worker can fetch before showing a prompt."""
    safe = compute(db, user)
    payday = next_payday_date(db, user.id, today_in(user.timezone))
    income = list(
        db.scalars(
            select(IncomeSource).where(
                IncomeSource.user_id == user.id, IncomeSource.is_active.is_(True)
            )
        )
    )
    notifications = db.get(NotificationPreference, user.id)
    return {
        "safe_to_spend": str(safe.safe_to_spend),
        "currency": user.currency,
        "next_payday": payday.isoformat() if payday else None,
        "warnings": safe.warnings,
        "income_sources": [
            {
                "name": source.name,
                "amount": str(quantize(source.amount)),
                "frequency": source.frequency,
                "next_payday": source.next_payday.isoformat() if source.next_payday else None,
            }
            for source in income
        ],
        "notification_context": {
            "shopping_assistant_enabled": bool(
                notifications and notifications.shopping_assistant_enabled
            ),
            "quiet_hours_start": notifications.quiet_hours_start if notifications else None,
            "quiet_hours_end": notifications.quiet_hours_end if notifications else None,
            "quiet_hours_timezone": notifications.quiet_hours_timezone if notifications else None,
        },
        "as_of": safe.as_of.isoformat(),
    }
