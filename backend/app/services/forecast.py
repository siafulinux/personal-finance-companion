"""Deterministic cash-flow projection (expected income is labelled, never spent)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, BillOccurrence, IncomeSource, User
from app.models.enums import OccurrenceStatus
from app.services.balance_lookup import eligible_cash_available
from app.services.bills import ensure_bill_occurrences, next_payday_date
from app.services.safe_to_spend import compute
from app.utils.dates import add_months, clamp_day, today_in, utc_now
from app.utils.money import ZERO, quantize

MAX_FORECAST_DAYS = 365


def _income_dates(source: IncomeSource, start: date, end: date) -> list[date]:
    dates: list[date] = []
    cursor = source.next_payday
    if cursor is None:
        return dates
    guard = 0
    while cursor < start and guard < 60:
        cursor = _advance(source, cursor)
        guard += 1
    guard = 0
    while cursor and cursor <= end and guard < 120:
        if cursor >= start:
            dates.append(cursor)
        cursor = _advance(source, cursor)
        guard += 1
    return dates


def _advance(source: IncomeSource, value: date) -> date:
    match source.frequency:
        case "weekly":
            return value + timedelta(days=7)
        case "biweekly":
            return value + timedelta(days=14)
        case "semimonthly":
            first = clamp_day(value.year, value.month, source.next_payday.day if source.next_payday else 15)
            if value.day < 15:
                return value.replace(day=15)
            return add_months(value.replace(day=1), 1).replace(day=1) + timedelta(days=14)
        case "monthly":
            return add_months(value, 1)
        case _:
            return value + timedelta(days=30)


def cash_flow_forecast(db: Session, user: User, days: int = 60) -> dict[str, object]:
    days = max(7, min(days, MAX_FORECAST_DAYS))
    today = today_in(user.timezone)
    end = today + timedelta(days=days)
    safe = compute(db, user)
    starting = eligible_cash_available(db, user)

    bills = list(
        db.scalars(select(Bill).where(Bill.user_id == user.id, Bill.is_active.is_(True)))
    )
    for bill in bills:
        ensure_bill_occurrences(db, bill, end)
    db.flush()

    occurrences = list(
        db.scalars(
            select(BillOccurrence).where(
                BillOccurrence.user_id == user.id,
                BillOccurrence.due_date >= today,
                BillOccurrence.due_date <= end,
                BillOccurrence.status.in_(
                    [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
                ),
            )
        )
    )
    sources = list(
        db.scalars(
            select(IncomeSource).where(
                IncomeSource.user_id == user.id, IncomeSource.is_active.is_(True)
            )
        )
    )

    days_out: list[dict[str, object]] = []
    balance = starting
    for offset in range(days + 1):
        current = today + timedelta(days=offset)
        income_due = sum(
            (source.amount for source in sources if current in _income_dates(source, current, current)),
            ZERO,
        )
        bills_due = sum(
            (o.remaining_amount for o in occurrences if o.due_date == current), ZERO
        )
        balance = quantize(balance + income_due - bills_due)
        if income_due or bills_due or offset == 0 or offset == days:
            days_out.append(
                {
                    "date": current.isoformat(),
                    "expected_income": str(quantize(income_due)),
                    "bills_due": str(quantize(bills_due)),
                    "projected_balance": str(balance),
                }
            )

    lowest = min(
        (Decimal(str(row["projected_balance"])) for row in days_out), default=starting
    )
    warnings: list[str] = []
    if lowest < ZERO:
        warnings.append(
            f"Projected balance falls below zero (lowest {quantize(lowest)}) within {days} days."
        )
    elif lowest < safe.minimum_buffer:
        warnings.append(
            f"Projected balance drops below your {safe.minimum_buffer} buffer within {days} days."
        )

    return {
        "start_date": today.isoformat(),
        "end_date": end.isoformat(),
        "starting_available_cash": str(starting),
        "expected_income_total": str(
            quantize(
                sum(
                    (source.amount for source in sources for _ in _income_dates(source, today, end)),
                    ZERO,
                )
            )
        ),
        "bills_total": str(
            quantize(sum((o.remaining_amount for o in occurrences), ZERO))
        ),
        "projected_end_balance": str(quantize(balance)),
        "lowest_projected_balance": str(quantize(lowest)),
        "next_payday": (
            next_payday_date(db, user.id, today).isoformat()
            if next_payday_date(db, user.id, today)
            else None
        ),
        "safe_to_spend_now": str(safe.safe_to_spend),
        "warnings": warnings,
        "points": days_out,
        "generated_at": utc_now().isoformat(),
        "assumption": (
            "Expected income is only counted on its scheduled date and is excluded from "
            "Safe-to-Spend until it arrives. Only unpaid bill occurrences are deducted."
        ),
    }
