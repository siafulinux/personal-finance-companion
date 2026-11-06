"""Personalised spending behaviour, with evidence attached to every claim.

Design rules that matter more than the heuristics:

* **No judgement without history.** A merchant- or category-level statement requires at
  least three distinct months *and* five transactions. Below that, the service returns
  nothing rather than guessing from one or two rows.
* **Every insight carries its evidence**, so the UI can show the numbers that produced it.
* **Sensitivity is the user's.** ``insight_sensitivity`` widens or narrows the thresholds,
  and ``personalized_insights_enabled`` turns the whole surface off.
* All money comes from the deterministic engine; nothing is recomputed here except the
  averages this module is explicitly about.
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.normalize import normalize_merchant
from app.models import Budget, BudgetAllocation, Category, Transaction, User, UserPreference
from app.models.enums import InsightSensitivity, TransactionStatus, TransactionType
from app.services.balances import spending_by_category
from app.utils.dates import add_months, month_bounds, today_in
from app.utils.money import ZERO, format_money, quantize

MIN_MONTHS = 3
MIN_TRANSACTIONS = 5
LOOKBACK_MONTHS = 6

# How far over a budget counts as noteworthy, by sensitivity.
_THRESHOLDS = {
    InsightSensitivity.LOW.value: Decimal("0.20"),
    InsightSensitivity.NORMAL.value: Decimal("0.00"),
    InsightSensitivity.HIGH.value: Decimal("-0.10"),
}


def _month_starts(today: date, months: int) -> list[date]:
    starts: list[date] = []
    cursor = today.replace(day=1)
    for _ in range(months):
        starts.append(cursor)
        cursor = add_months(cursor, -1)
    return starts


def _prefs(db: Session, user: User) -> UserPreference | None:
    return db.get(UserPreference, user.id)


def merchant_profile(
    db: Session, user: User, merchant: str | None, *, months: int = LOOKBACK_MONTHS
) -> dict[str, object]:
    """Monthly spend history for one merchant. Empty-ish when history is insufficient."""
    key = normalize_merchant(merchant)
    today = today_in(user.timezone)
    empty = {
        "merchant": merchant,
        "merchant_key": key,
        "has_enough_history": False,
        "months_of_history": 0,
        "transaction_count": 0,
        "monthly_average": None,
        "monthly_median": None,
        "current_month_spend": None,
        "current_month_transactions": 0,
        "typical_amount": None,
        "months": [],
    }
    if not key:
        return empty

    start = _month_starts(today, months)[-1]
    rows = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.tx_type == TransactionType.PURCHASE.value,
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date >= start,
                Transaction.txn_date <= today,
            )
        )
    )
    mine = [t for t in rows if normalize_merchant(t.merchant or t.description) == key]
    if not mine:
        return empty

    by_month: dict[str, Decimal] = defaultdict(lambda: ZERO)
    counts: dict[str, int] = defaultdict(int)
    for txn in mine:
        label = f"{txn.txn_date.year}-{txn.txn_date.month:02d}"
        by_month[label] += quantize(txn.amount)
        counts[label] += 1

    monthly_values = [float(v) for v in by_month.values()]
    current_label = f"{today.year}-{today.month:02d}"
    enough = len(by_month) >= MIN_MONTHS and len(mine) >= MIN_TRANSACTIONS

    return {
        "merchant": merchant,
        "merchant_key": key,
        "has_enough_history": enough,
        "months_of_history": len(by_month),
        "transaction_count": len(mine),
        "monthly_average": (
            str(quantize(Decimal(str(sum(monthly_values) / len(monthly_values))))) if enough else None
        ),
        "monthly_median": (
            str(quantize(Decimal(str(statistics.median(monthly_values))))) if enough else None
        ),
        "current_month_spend": str(quantize(by_month.get(current_label, ZERO))),
        "current_month_transactions": counts.get(current_label, 0),
        "typical_amount": str(quantize(Decimal(str(statistics.median(float(t.amount) for t in mine))))),
        "months": [
            {"month": label, "spent": str(quantize(value)), "transactions": counts[label]}
            for label, value in sorted(by_month.items())
        ],
    }


def _category_averages(
    db: Session, user: User, months: int = 3
) -> dict[uuid.UUID, dict[str, object]]:
    today = today_in(user.timezone)
    starts = _month_starts(today, months)
    per_category: dict[uuid.UUID, list[Decimal]] = defaultdict(list)
    for start in starts:
        first, last = month_bounds(start.year, start.month)
        for category_id, spent in spending_by_category(db, user.id, first, last).items():
            if category_id is not None:
                per_category[category_id].append(quantize(spent))
    out: dict[uuid.UUID, dict[str, object]] = {}
    for category_id, values in per_category.items():
        non_zero = [float(v) for v in values if v > ZERO]
        out[category_id] = {
            "months": len(values),
            "average": quantize(Decimal(str(sum(values) / len(values)))),
            "peak": max(values),
            "volatile": bool(non_zero and statistics.pstdev(non_zero) > (sum(non_zero) / len(non_zero)) * 0.5),
        }
    return out


def _current_budget(db: Session, user_id: uuid.UUID, today: date) -> dict[uuid.UUID, Decimal]:
    budget = db.scalar(
        select(Budget).where(
            Budget.user_id == user_id, Budget.year == today.year, Budget.month == today.month
        )
    )
    if budget is None:
        return {}
    rows = db.execute(
        select(BudgetAllocation.category_id, BudgetAllocation.amount).where(
            BudgetAllocation.budget_id == budget.id
        )
    ).all()
    return {category_id: quantize(amount) for category_id, amount in rows}


def spending_insights(db: Session, user: User) -> dict[str, object]:
    """Explainable, evidence-backed observations about this user's spending."""
    prefs = _prefs(db, user)
    enabled = bool(prefs.personalized_insights_enabled) if prefs else True
    sensitivity = (
        prefs.insight_sensitivity if prefs else InsightSensitivity.NORMAL.value
    )
    today = today_in(user.timezone)

    if not enabled:
        return {
            "enabled": False,
            "sensitivity": sensitivity,
            "insights": [],
            "minimum_history": {
                "months": MIN_MONTHS,
                "transactions": MIN_TRANSACTIONS,
            },
            "note": "Personalised insights are turned off in your preferences.",
        }

    threshold = _THRESHOLDS.get(sensitivity, Decimal("0.00"))
    categories = {
        c.id: c
        for c in db.scalars(
            select(Category).where(
                Category.user_id == user.id, Category.is_archived.is_(False)
            )
        )
    }
    allocations = _current_budget(db, user.id, today)
    averages = _category_averages(db, user, 3)
    first_of_month, last_of_month = month_bounds(today.year, today.month)
    spent_now = spending_by_category(db, user.id, first_of_month, today)

    insights: list[dict[str, object]] = []

    for category_id, allocation in allocations.items():
        category = categories.get(category_id)
        if category is None or allocation <= ZERO:
            continue
        spent = quantize(spent_now.get(category_id, ZERO))
        history = averages.get(category_id)
        remaining = quantize(allocation - spent)
        usage = (spent / allocation) if allocation > ZERO else ZERO

        if remaining < ZERO or (usage >= (Decimal("0.9") if sensitivity == "high" else Decimal("1"))):
            insights.append(
                {
                    "type": "category_over_budget",
                    "severity": "high" if remaining < ZERO else "medium",
                    "category_id": str(category_id),
                    "title": f"{category.name} is over budget",
                    "message": (
                        f"You have spent {format_money(spent)} of your {format_money(allocation)} {category.name} budget "
                        f"this month ({quantize(usage * 100)}%)."
                        if remaining < ZERO
                        else (
                            f"You have used {quantize(usage * 100)}% of your {category.name} "
                            f"budget with {format_money(remaining)} left."
                        )
                    ),
                    "evidence": {
                        "allocated": str(allocation),
                        "spent": str(spent),
                        "remaining": str(remaining),
                        "usage_percent": str(quantize(usage * 100)),
                    },
                }
            )
        elif history and history["months"] >= MIN_MONTHS:
            average = history["average"]
            assert isinstance(average, Decimal)
            if average > allocation * (Decimal("1") + threshold):
                overage = quantize(average - allocation)
                insights.append(
                    {
                        "type": "category_habitually_over",
                        "severity": "medium",
                        "category_id": str(category_id),
                        "title": f"{category.name} usually costs more than you budget",
                        "message": (
                            f"Your {category.name} spending has averaged {format_money(average)} over the "
                            f"last {history['months']} months, but this month's budget is "
                            f"{format_money(allocation)}. That is {format_money(overage)} short each month."
                        ),
                        "evidence": {
                            "three_month_average": str(average),
                            "allocated": str(allocation),
                            "monthly_shortfall": str(overage),
                            "months_observed": history["months"],
                        },
                    }
                )

    # Recurring small purchases: the "death by a thousand cuts" pattern.
    window_start = today - timedelta(days=30)
    recent = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.tx_type == TransactionType.PURCHASE.value,
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date >= window_start,
                Transaction.txn_date <= today,
            )
        )
    )
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for txn in recent:
        key = normalize_merchant(txn.merchant or txn.description)
        if key:
            by_merchant[key].append(txn)

    for key, items in by_merchant.items():
        if len(items) < 8:
            continue
        total = quantize(sum((quantize(t.amount) for t in items), ZERO))
        average = quantize(total / len(items))
        if average > Decimal("20.00"):
            continue
        display = items[0].merchant or items[0].description
        insights.append(
            {
                "type": "repeated_small_purchases",
                "severity": "low",
                "merchant": display,
                "title": f"Frequent small purchases at {display}",
                "message": (
                    f"{len(items)} purchases at {display} in the last 30 days, averaging "
                    f"{format_money(average)} — {format_money(total)} in total."
                ),
                "evidence": {
                    "transaction_count": len(items),
                    "total": str(total),
                    "average": str(average),
                    "window_days": 30,
                },
            }
        )

    insights.sort(key=lambda i: ({"high": 0, "medium": 1, "low": 2}[str(i["severity"])]))
    return {
        "enabled": True,
        "sensitivity": sensitivity,
        "minimum_history": {"months": MIN_MONTHS, "transactions": MIN_TRANSACTIONS},
        "insights": insights[:12],
        "as_of": today.isoformat(),
        "note": (
            "Insights are computed from your own history with the deterministic engine. "
            "They are observations, not instructions."
        ),
    }


def merchant_advice(
    db: Session,
    user: User,
    *,
    merchant: str | None,
    category_id: uuid.UUID | None,
    category_remaining: Decimal | None,
) -> dict[str, object]:
    """Merchant-level context for Shopping Check, including a suggested visit limit."""
    profile = merchant_profile(db, user, merchant)
    if not profile["has_enough_history"]:
        return {
            "merchant": profile["merchant"],
            "has_enough_history": False,
            "message": (
                "Not enough history at this merchant yet to describe a pattern. "
                f"{MIN_MONTHS} months and {MIN_TRANSACTIONS} purchases are needed."
            ),
            "profile": profile,
            "suggested_limit": None,
            "tendency": "unknown",
        }

    typical = Decimal(str(profile["typical_amount"]))
    monthly = Decimal(str(profile["monthly_average"]))
    spent_this_month = Decimal(str(profile["current_month_spend"]))
    current_count = int(profile["current_month_transactions"])

    suggested_limit: Decimal | None = None
    if category_remaining is not None:
        room = quantize(category_remaining)
        suggested_limit = min(typical, room) if room > ZERO else ZERO

    tendency = "typical"
    message = f"Your typical purchase at {profile['merchant']} is {format_money(typical)}."
    if spent_this_month >= monthly * Decimal("1.25") and monthly > ZERO:
        tendency = "overspending"
        message = (
            f"You usually spend about {format_money(monthly)} a month at this merchant, and you have "
            f"already spent {format_money(spent_this_month)} this month across {current_count} visits."
        )

    return {
        "merchant": profile["merchant"],
        "has_enough_history": True,
        "profile": profile,
        "suggested_limit": str(suggested_limit) if suggested_limit is not None else None,
        "tendency": tendency,
        "message": message,
    }
