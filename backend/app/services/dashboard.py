"""Dashboard composition: one consistent snapshot from the calculation layer."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import BillPaymentMatch, Category, PlannedReserve, User
from app.models.enums import CategoryKind, MatchStatus
from app.services.accounts import list_accounts, totals
from app.services.balances import period_totals, spending_by_category
from app.services.bills import (
    horizon_candidates,
    next_payday_date,
    occurrence_dict,
)
from app.services.budgets import budget_summary, get_budget, top_spending_categories
from app.services.safe_to_spend import category_availability, compute
from app.services.transactions import recent_transactions, serialize_transaction
from app.utils.dates import month_bounds, today_in
from app.utils.money import ZERO, quantize


def _upcoming_occurrences(db: Session, user: User, today, horizon_end):
    rows = horizon_candidates(db, user.id, today, horizon_end)
    return [occurrence_dict(o, today) for o in rows]


def dashboard_snapshot(db: Session, user: User) -> dict[str, object]:
    today = today_in(user.timezone)
    safe = compute(db, user)
    accounts = [
        {
            "id": str(account.id),
            "name": account.name,
            "account_type": account.account_type,
            "balance": str(summary.posted_balance),
            "pending_balance": str(summary.pending_balance),
            "include_in_safe_to_spend": account.include_in_safe_to_spend,
            "is_archived": account.is_archived,
        }
        for account, summary in list_accounts(db, user.id)
    ]
    account_totals = totals(db, user.id)

    month_start, month_end = month_bounds(today.year, today.month)
    budget = get_budget(db, user.id, today.year, today.month)
    budget_data = budget_summary(db, user.id, budget, today) if budget else None

    next_fourteen = today + timedelta(days=14)
    # The panel is explicitly "next 14 days"; Safe-to-Spend uses the (possibly shorter)
    # payday horizon, so fetch the wider display window here.
    display_end = max(safe.horizon_end, next_fourteen)
    upcoming = _upcoming_occurrences(db, user, today, display_end)
    upcoming_soon = [
        o
        for o in upcoming
        if o["due_date"] <= next_fourteen.isoformat() or o["is_overdue"]
    ]

    pending_suggestions = db.scalar(
        select(func.count(BillPaymentMatch.id)).where(
            BillPaymentMatch.user_id == user.id,
            BillPaymentMatch.status == MatchStatus.SUGGESTED.value,
        )
    ) or 0

    month_totals = period_totals(db, user.id, month_start, month_end)
    categories = list(
        db.scalars(
            select(Category)
            .where(
                Category.user_id == user.id,
                Category.is_archived.is_(False),
                Category.kind == CategoryKind.EXPENSE.value,
            )
            .order_by(Category.sort_order, Category.name)
        )
    )

    warnings = list(safe.warnings)
    if budget_data and budget_data["total_remaining"] < ZERO:
        warnings.append(
            f"Your budget is overspent by {abs(budget_data['total_remaining'])} this month."
        )
    overdue = [o for o in upcoming if o["is_overdue"]]
    if overdue and not any("overdue" in w.lower() for w in warnings):
        warnings.append(f"{len(overdue)} overdue bill(s) need attention.")

    next_payday = next_payday_date(db, user.id, today)
    reserves_total = db.scalar(
        select(func.coalesce(func.sum(PlannedReserve.amount), 0)).where(
            PlannedReserve.user_id == user.id,
            PlannedReserve.is_active.is_(True),
            PlannedReserve.start_date <= today,
        )
    ) or ZERO

    shopping_categories = []
    for category in categories:
        availability = category_availability(db, user, category.id, overall=safe)
        shopping_categories.append(availability.as_dict())

    return {
        "as_of": safe.as_of.isoformat(),
        "today": today.isoformat(),
        "safe_to_spend": safe.as_dict(),
        "accounts": accounts,
        "account_totals": {
            "total_cash": str(account_totals["total_cash"]),
            "total_debt": str(account_totals["total_debt"]),
            "net_worth": str(account_totals["net_worth"]),
        },
        "budget": budget_data,
        "spending_by_category": top_spending_categories(db, user.id, month_start, month_end, 7),
        "upcoming_bills": upcoming_soon,
        "upcoming_bills_total": str(
            quantize(sum((Decimal(str(o["remaining_amount"])) for o in upcoming_soon), ZERO))
        ),
        "next_payday": next_payday.isoformat() if next_payday else None,
        "recent_transactions": [
            serialize_transaction(txn) for txn in recent_transactions(db, user.id, 7)
        ],
        "pending_match_suggestions": int(pending_suggestions),
        "month_totals": {
            "income": str(month_totals["income"]),
            "spending": str(month_totals["spending"]),
            "net": str(month_totals["net"]),
        },
        "reserved_total": str(quantize(Decimal(str(reserves_total)))),
        "warnings": warnings,
        "shopping_categories": shopping_categories,
        "currency": user.currency,
        "is_demo": user.is_demo,
    }
