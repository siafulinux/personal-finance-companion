"""Merchant-level spending intelligence with evidence and a history floor.

Everything here is deterministic: grouped sums, medians and month counts. A
statement about behaviour needs at least ``MIN_MONTHS`` months and
``MIN_TRANSACTIONS`` purchases; below that the module says so instead of
extrapolating from one receipt.

Users can dismiss a finding. Dismissals are stored by a stable key so a dismissed
warning does not come back on the next page load, and nothing here ever edits a
transaction or a user-confirmed category.
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
from app.models import Category, InsightDismissal, Transaction, User, UserPreference
from app.models.enums import TransactionStatus, TransactionType
from app.services.balances import spending_by_category
from app.services.budgets import budget_category_row
from app.utils.dates import month_bounds, today_in
from app.utils.money import ZERO, format_money, quantize

MIN_MONTHS = 3
MIN_TRANSACTIONS = 5
WINDOW_DAYS = 90


def _purchases(db: Session, user_id: uuid.UUID, start: date, end: date) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.tx_type == TransactionType.PURCHASE.value,
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date >= start,
                Transaction.txn_date <= end,
            )
        )
    )


def _confidence(months: int, count: int) -> str:
    if months >= 6 and count >= 12:
        return "high"
    if months >= MIN_MONTHS and count >= MIN_TRANSACTIONS:
        return "medium"
    return "low"


def _dismissed_keys(db: Session, user_id: uuid.UUID) -> set[str]:
    return set(
        db.scalars(select(InsightDismissal.key).where(InsightDismissal.user_id == user_id))
    )


def dismiss(db: Session, user_id: uuid.UUID, key: str) -> None:
    existing = db.scalar(
        select(InsightDismissal).where(
            InsightDismissal.user_id == user_id, InsightDismissal.key == key
        )
    )
    if existing is not None:
        return
    db.add(InsightDismissal(user_id=user_id, key=key[:200]))
    db.flush()


def restore(db: Session, user_id: uuid.UUID, key: str) -> None:
    existing = db.scalar(
        select(InsightDismissal).where(
            InsightDismissal.user_id == user_id, InsightDismissal.key == key
        )
    )
    if existing is not None:
        db.delete(existing)
        db.flush()


def list_dismissed(db: Session, user_id: uuid.UUID) -> list[str]:
    return sorted(_dismissed_keys(db, user_id))


def merchant_overview(db: Session, user: User, *, days: int = WINDOW_DAYS) -> dict[str, object]:
    """Per-merchant totals over a window, with a prior window for comparison."""
    today = today_in(user.timezone)
    start = today - timedelta(days=days)
    prior_start = start - timedelta(days=days)

    recent = _purchases(db, user.id, start, today)
    prior = _purchases(db, user.id, prior_start, start - timedelta(days=1))

    categories = {
        c.id: c
        for c in db.scalars(
            select(Category).where(Category.user_id == user.id, Category.is_archived.is_(False))
        )
    }

    grouped: dict[str, list[Transaction]] = defaultdict(list)
    for txn in recent:
        key = normalize_merchant(txn.merchant or txn.description)
        if key:
            grouped[key].append(txn)

    prior_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for txn in prior:
        key = normalize_merchant(txn.merchant or txn.description)
        if key:
            prior_totals[key] += quantize(txn.amount)

    rows: list[dict[str, object]] = []
    for key, items in grouped.items():
        total = quantize(sum((quantize(t.amount) for t in items), ZERO))
        months = len({(t.txn_date.year, t.txn_date.month) for t in items})
        category_votes: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
        for txn in items:
            if txn.category_id:
                category_votes[txn.category_id] += quantize(txn.amount)
        dominant_category = (
            max(category_votes.items(), key=lambda pair: pair[1])[0] if category_votes else None
        )
        category = categories.get(dominant_category) if dominant_category else None
        previous = quantize(prior_totals.get(key, ZERO))
        change_percent = (
            quantize((total - previous) / previous * Decimal("100")) if previous > ZERO else None
        )
        display = next((t.merchant for t in items if t.merchant), items[0].description)
        rows.append(
            {
                "merchant_key": key,
                "merchant": display,
                "category_id": str(dominant_category) if dominant_category else None,
                "category_name": category.name if category else None,
                "transaction_count": len(items),
                "total": str(total),
                "average": str(quantize(total / len(items))),
                "largest": str(max(quantize(t.amount) for t in items)),
                "last_purchase": max(t.txn_date for t in items).isoformat(),
                "months_observed": months,
                "prior_total": str(previous),
                "change_percent": str(change_percent) if change_percent is not None else None,
                "has_enough_history": months >= MIN_MONTHS and len(items) >= MIN_TRANSACTIONS,
                "confidence": _confidence(months, len(items)),
                "window_days": days,
            }
        )
    rows.sort(key=lambda row: Decimal(str(row["total"])), reverse=True)
    return {
        "window_days": days,
        "start": start.isoformat(),
        "end": today.isoformat(),
        "minimum_history": {"months": MIN_MONTHS, "transactions": MIN_TRANSACTIONS},
        "merchants": rows[:20],
        "note": (
            "Grouped by normalised merchant name from your own posted purchases. "
            "Statements about a pattern require at least three months and five purchases."
        ),
    }


def merchant_findings(db: Session, user: User) -> list[dict[str, object]]:
    """Explainable, dismissible observations about specific merchants."""
    today = today_in(user.timezone)
    prefs = db.get(UserPreference, user.id)
    if prefs is not None and not prefs.personalized_insights_enabled:
        return []
    dismissed = _dismissed_keys(db, user.id)
    overview = merchant_overview(db, user)
    findings: list[dict[str, object]] = []

    first_of_month, _ = month_bounds(today.year, today.month)
    month_spend = spending_by_category(db, user.id, first_of_month, today)
    start = today - timedelta(days=WINDOW_DAYS)
    recent = _purchases(db, user.id, start, today)
    grouped: dict[str, list[Transaction]] = defaultdict(list)
    for txn in recent:
        key = normalize_merchant(txn.merchant or txn.description)
        if key:
            grouped.setdefault(key, []).append(txn)

    for row in overview["merchants"]:
        if not row["has_enough_history"]:
            continue
        key = str(row["merchant_key"])
        display = str(row["merchant"])
        items = grouped.get(key, [])
        if not items:
            continue
        change = row["change_percent"]
        total = Decimal(str(row["total"]))
        count = int(row["transaction_count"])

        if change is not None and Decimal(str(change)) >= Decimal("25") and total >= Decimal("50"):
            finding_key = f"merchant-grew:{key}"
            if finding_key not in dismissed:
                findings.append(
                    {
                        "key": finding_key,
                        "type": "merchant_spending_increase",
                        "severity": "medium",
                        "merchant": display,
                        "merchant_key": key,
                        "title": f"Spending at {display} is up",
                        "message": (
                            f"You have spent {format_money(total)} at {display} in the last "
                            f"{WINDOW_DAYS} days, {quantize(Decimal(str(change)))}% more than the "
                            f"{WINDOW_DAYS} days before."
                        ),
                        "confidence": row["confidence"],
                        "evidence": {
                            "current_window_total": str(total),
                            "prior_window_total": row["prior_total"],
                            "change_percent": str(change),
                            "transaction_count": count,
                        },
                    }
                )

        # Repeated small purchases: a pattern only when it is frequent, not a fluke.
        average = Decimal(str(row["average"]))
        if count >= 8 and average <= Decimal("20") and total >= Decimal("60"):
            finding_key = f"merchant-small-repeat:{key}"
            if finding_key not in dismissed:
                findings.append(
                    {
                        "key": finding_key,
                        "type": "repeated_small_purchases",
                        "severity": "low",
                        "merchant": display,
                        "merchant_key": key,
                        "title": f"Frequent small purchases at {display}",
                        "message": (
                            f"{count} purchases at {display} in {WINDOW_DAYS} days, averaging "
                            f"{format_money(average)} — {format_money(total)} in total."
                        ),
                        "confidence": row["confidence"],
                        "evidence": {
                            "transaction_count": count,
                            "average": str(average),
                            "total": str(total),
                        },
                    }
                )

        # Budget pressure: the merchant's dominant category is already short, and
        # this store is a meaningful share of that spending.
        category_id = row["category_id"]
        if category_id:
            budget_row = budget_category_row(
                db, user.id, today.year, today.month, uuid.UUID(str(category_id))
            )
            if budget_row and budget_row.remaining <= ZERO and budget_row.allocated > ZERO:
                category_spent = quantize(month_spend.get(uuid.UUID(str(category_id)), ZERO))
                share = (
                    quantize((total / category_spent) * Decimal("100"))
                    if category_spent > ZERO
                    else ZERO
                )
                finding_key = f"merchant-budget-pressure:{key}:{today.year}-{today.month:02d}"
                if share >= Decimal("20") and finding_key not in dismissed:
                    findings.append(
                        {
                            "key": finding_key,
                            "type": "merchant_budget_pressure",
                            "severity": "high",
                            "merchant": display,
                            "merchant_key": key,
                            "category_id": str(category_id),
                            "title": f"{display} is pressing on your {budget_row.category_name} budget",
                            "message": (
                                f"{budget_row.category_name} is over budget for {today.strftime('%B')}, "
                                f"and {display} accounts for {share}% of this month's spending there."
                            ),
                            "confidence": "medium",
                            "evidence": {
                                "allocated": str(budget_row.allocated),
                                "spent": str(budget_row.spent),
                                "merchant_total_window": str(total),
                                "share_of_category_percent": str(share),
                            },
                        }
                    )

        # A single purchase far above this merchant's own median.
        if len(items) >= 4:
            baseline = statistics.median(float(t.amount) for t in items)
            if baseline > 0:
                for txn in items:
                    if float(txn.amount) >= baseline * 2.5:
                        finding_key = f"merchant-unusual:{txn.id}"
                        if finding_key in dismissed:
                            continue
                        findings.append(
                            {
                                "key": finding_key,
                                "type": "unusual_purchase",
                                "severity": "low",
                                "merchant": display,
                                "merchant_key": key,
                                "title": f"An unusually large {display} purchase",
                                "message": (
                                    f"{format_money(txn.amount)} on {txn.txn_date.isoformat()} is well "
                                    f"above your usual {format_money(Decimal(str(round(baseline, 2))))} here."
                                ),
                                "confidence": "medium",
                                "evidence": {
                                    "transaction_id": str(txn.id),
                                    "amount": str(quantize(txn.amount)),
                                    "median_amount": str(quantize(Decimal(str(round(baseline, 2))))),
                                },
                            }
                        )
                        break

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda item: severity_order.get(str(item["severity"]), 3))
    return findings[:12]
