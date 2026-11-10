"""Structured recommendations the UI can render and an LLM may explain.

Every figure here is read from the deterministic engine (Safe-to-Spend, the
obligations list, loan projections, savings goals). This module only decides which
facts matter enough to mention and how to phrase them; it never performs financial
arithmetic that the engine does not already own.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.normalize import normalize_merchant
from app.models import Transaction, User
from app.models.enums import TransactionStatus, TransactionType
from app.services.balances import spending_by_category
from app.services.budgets import budget_category_row
from app.services.merchant_intelligence import merchant_findings, merchant_overview
from app.services.obligations import unified_obligations
from app.services.safe_to_spend import compute, last_transaction_date
from app.services.savings import summary as savings_summary
from app.utils.dates import month_bounds, today_in
from app.utils.money import ZERO, format_money, quantize

LOW_SAFE_TO_SPEND = Decimal("50.00")


def _freshness(db: Session, user: User, today: date) -> dict[str, object]:
    latest = last_transaction_date(db, user.id)
    return {
        "last_transaction_date": latest.isoformat() if latest else None,
        "stale": latest is None or (today - latest).days > 45,
        "checked_at": today.isoformat(),
    }


def build_recommendations(db: Session, user: User, *, limit: int = 8) -> dict[str, object]:
    today = today_in(user.timezone)
    safe = compute(db, user)
    obligations = unified_obligations(db, user, days=45)
    savings = savings_summary(db, user, today=today)
    freshness = _freshness(db, user, today)

    items: list[dict[str, object]] = []

    if safe.safe_to_spend <= ZERO:
        items.append(
            {
                "key": "safe-to-spend-zero",
                "kind": "cash",
                "severity": "high",
                "title": "Nothing is safe to spend right now",
                "message": (
                    "Every dollar in your spending accounts is already committed to bills, loan "
                    "repayments, savings or pending debits. New spending would come out of money "
                    "you have promised elsewhere."
                ),
                "confidence": "high",
                "facts": {
                    "safe_to_spend": str(safe.safe_to_spend),
                    "obligations_total": str(safe.obligations_total),
                    "pending_debits": str(safe.pending_debits),
                },
                "period": {"horizon_end": safe.horizon_end.isoformat()},
                "suggested_limit": "0.00",
            }
        )
    elif safe.safe_to_spend < LOW_SAFE_TO_SPEND:
        items.append(
            {
                "key": "safe-to-spend-low",
                "kind": "cash",
                "severity": "medium",
                "title": "Your spending room is thin",
                "message": (
                    f"Only {format_money(safe.safe_to_spend)} is safe to spend before "
                    f"{safe.horizon_end.isoformat()}, with {format_money(safe.obligations_total)} "
                    "of obligations already reserved."
                ),
                "confidence": "high",
                "facts": {
                    "safe_to_spend": str(safe.safe_to_spend),
                    "obligations_total": str(safe.obligations_total),
                },
                "period": {"horizon_end": safe.horizon_end.isoformat()},
                "suggested_limit": str(safe.safe_to_spend),
            }
        )

    overdue = obligations["totals"]["overdue"]
    if Decimal(str(overdue)) > ZERO:
        items.append(
            {
                "key": "obligations-overdue",
                "kind": "obligation",
                "severity": "high",
                "title": "An obligation is overdue",
                "message": (
                    f"{format_money(Decimal(str(overdue)))} of due payments has passed its date. "
                    "Paying it will reduce what is available for everything else."
                ),
                "confidence": "high",
                "facts": {"overdue_total": str(overdue)},
                "period": {"today": today.isoformat()},
            }
        )

    before_payday = Decimal(str(obligations["totals"]["due_before_payday"]))
    if before_payday > ZERO and obligations["next_payday"]:
        items.append(
            {
                "key": "obligations-before-payday",
                "kind": "obligation",
                "severity": "medium",
                "title": "Payments are due before your next payday",
                "message": (
                    f"{format_money(before_payday)} is due by {obligations['next_payday']}. "
                    "Safe-to-Spend already holds this money back."
                ),
                "confidence": "high",
                "facts": {
                    "due_before_payday": str(before_payday),
                    "next_payday": obligations["next_payday"],
                },
                "period": {"until": obligations["next_payday"]},
            }
        )

    for loan in safe.loans[:2]:
        if loan.get("is_estimate"):
            items.append(
                {
                    "key": f"loan-estimate:{loan['loan_id']}",
                    "kind": "loan",
                    "severity": "low",
                    "title": f"{loan['name']} balance is an estimate",
                    "message": (
                        "The repayment schedule or the principal/interest split is incomplete, so "
                        "the remaining balance is calculated rather than confirmed by the lender."
                    ),
                    "confidence": "medium",
                    "facts": {
                        "remaining_balance": str(loan["remaining_balance"]),
                        "due_date": str(loan["due_date"]),
                    },
                    "period": {"due_date": str(loan["due_date"])},
                }
            )

    for goal in savings["goals"]:
        if goal["status"] != "active":
            continue
        required = goal["required_per_period"]
        planned = goal["contribution_amount"]
        if required is not None and (planned is None or Decimal(str(planned)) < Decimal(str(required))):
            items.append(
                {
                    "key": f"savings-behind:{goal['id']}",
                    "kind": "savings",
                    "severity": "medium",
                    "title": f"{goal['name']} is behind its target date",
                    "message": (
                        f"You need {format_money(Decimal(str(required)))} per period to reach "
                        f"{goal['name']} by {goal['target_date']}"
                        + (
                            f", but the plan contributes {format_money(Decimal(str(planned)))}."
                            if planned is not None
                            else ", but no contribution is planned."
                        )
                    ),
                    "confidence": "high",
                    "facts": {
                        "required_per_period": str(required),
                        "planned_per_period": str(planned) if planned is not None else None,
                        "remaining_to_target": goal["remaining_to_target"],
                    },
                    "period": {"target_date": goal["target_date"]},
                }
            )

    first_of_month, _ = month_bounds(today.year, today.month)
    spent_now = spending_by_category(db, user.id, first_of_month, today)
    for category_id, spent in sorted(spent_now.items(), key=lambda pair: pair[1], reverse=True)[:3]:
        if category_id is None:
            continue
        row = budget_category_row(db, user.id, today.year, today.month, category_id)
        if row is None or row.allocated <= ZERO:
            continue
        if row.remaining < ZERO:
            items.append(
                {
                    "key": f"category-over:{category_id}:{today.year}-{today.month:02d}",
                    "kind": "category",
                    "severity": "medium",
                    "title": f"{row.category_name} is over budget",
                    "message": (
                        f"You have spent {format_money(row.spent)} of a "
                        f"{format_money(row.allocated)} {row.category_name} budget this month."
                    ),
                    "confidence": "high",
                    "facts": {
                        "allocated": str(row.allocated),
                        "spent": str(row.spent),
                        "over_by": str(quantize(-row.remaining)),
                    },
                    "category_id": str(category_id),
                    "period": {"month": f"{today.year}-{today.month:02d}"},
                }
            )

    for finding in merchant_findings(db, user)[:3]:
        items.append(
            {
                "key": str(finding["key"]),
                "kind": "merchant",
                "severity": finding["severity"],
                "title": finding["title"],
                "message": finding["message"],
                "confidence": finding["confidence"],
                "facts": finding["evidence"],
                "merchant": finding["merchant"],
                "category_id": finding.get("category_id"),
                "period": {"window_days": 90},
            }
        )

    if freshness["stale"]:
        items.append(
            {
                "key": "data-stale",
                "kind": "data",
                "severity": "low",
                "title": "Your data may be out of date",
                "message": (
                    "No transactions have been recorded recently, so balances and Safe-to-Spend "
                    "may not reflect reality."
                ),
                "confidence": "high",
                "facts": {"last_transaction_date": freshness["last_transaction_date"]},
            }
        )

    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: order.get(str(item["severity"]), 3))
    return {
        "generated_at": safe.as_of.isoformat(),
        "today": today.isoformat(),
        "data_freshness": freshness,
        "safe_to_spend": str(safe.safe_to_spend),
        "obligations_due": str(safe.obligations_total),
        "savings_protected": str(safe.savings_reserves),
        "items": items[:limit],
        "note": (
            "Recommendations are generated from your ledger by fixed rules. They explain your "
            "position; they never move money or change a record."
        ),
    }


def store_guidance(
    db: Session,
    user: User,
    *,
    merchant: str,
    category_id: uuid.UUID | None,
    store_budget: Decimal | None = None,
) -> dict[str, object]:
    """The numbers behind a location-aware Shopping Check prompt."""
    today = today_in(user.timezone)
    safe = compute(db, user)
    obligations = unified_obligations(db, user, days=14)

    overview = merchant_overview(db, user, days=180)
    key = normalize_merchant(merchant)
    profile = next(
        (row for row in overview["merchants"] if row["merchant_key"] == key), None
    )

    category_remaining = None
    category_name = None
    if category_id is not None:
        row = budget_category_row(db, user.id, today.year, today.month, category_id)
        if row is not None:
            category_remaining = row.remaining
            category_name = row.category_name

    store_remaining = None
    if store_budget is not None:
        # The store's own month-to-date spend, matched on the normalised merchant
        # key rather than on the category: another shop in the same category must
        # not consume this store's budget.
        first_of_month, _ = month_bounds(today.year, today.month)
        month_rows = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.tx_type == TransactionType.PURCHASE.value,
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date >= first_of_month,
                Transaction.txn_date <= today,
            )
        )
        store_spent = quantize(
            sum(
                (
                    quantize(row.amount)
                    for row in month_rows
                    if normalize_merchant(row.merchant or row.description) == key
                ),
                ZERO,
            )
        )
        store_remaining = quantize(max(quantize(store_budget) - store_spent, ZERO))

    typical = Decimal(str(profile["average"])) if profile and profile["has_enough_history"] else None
    candidates = [safe.safe_to_spend]
    if category_remaining is not None:
        candidates.append(quantize(category_remaining))
    if store_remaining is not None:
        candidates.append(store_remaining)
    if typical is not None:
        candidates.append(typical)
    suggested = quantize(min(candidates)) if candidates else ZERO

    parts: list[str] = []
    parts.append(f"Your Safe-to-Spend is {format_money(safe.safe_to_spend)}.")
    if category_remaining is not None and category_name:
        parts.append(f"You have {format_money(category_remaining)} left in {category_name} this month.")
    if store_remaining is not None:
        parts.append(f"Your {merchant} budget has {format_money(store_remaining)} remaining.")
    if typical is not None:
        parts.append(f"Visits here average {format_money(typical)}.")
    if Decimal(str(obligations["totals"]["due_within_7_days"])) > ZERO:
        parts.append(
            f"{format_money(Decimal(str(obligations['totals']['due_within_7_days'])))} of payments "
            "are due within a week."
        )

    return {
        "safe_to_spend": safe.safe_to_spend,
        "store_budget": quantize(store_budget) if store_budget is not None else None,
        "store_remaining": store_remaining,
        "typical_spend": typical,
        "suggested_limit": suggested,
        "upcoming_obligations_total": Decimal(str(obligations["totals"]["due_within_7_days"])),
        "message": " ".join(parts),
        "facts": {
            "safe_to_spend": str(safe.safe_to_spend),
            "category_remaining": str(category_remaining) if category_remaining is not None else "unknown",
            "store_remaining": str(store_remaining) if store_remaining is not None else "unknown",
            "typical_spend": str(typical) if typical is not None else "not enough history",
            "suggested_limit": str(suggested),
            "due_within_7_days": str(obligations["totals"]["due_within_7_days"]),
        },
        "has_history": bool(profile and profile["has_enough_history"]),
        "data_is_stale": safe.stale_information,
        "period": {"today": today.isoformat(), "horizon_end": safe.horizon_end.isoformat()},
    }
