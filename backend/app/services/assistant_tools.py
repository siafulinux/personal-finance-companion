"""Permission-checked, structured data tools for future AI features.

These are the only door an AI provider gets. Every function receives an
authenticated ``User`` from the caller and filters by ``user.id``; no raw SQL or
unrestricted database access is exposed. All arithmetic stays in the deterministic
engine - an AI layer may narrate these values but never compute them.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, Category, User
from app.services.accounts import list_accounts, totals
from app.services.balances import period_totals, spending_by_category
from app.services.bills import horizon_candidates, occurrence_dict
from app.services.budgets import budget_summary, get_budget, top_spending_categories
from app.services.forecast import cash_flow_forecast
from app.services.safe_to_spend import category_availability, compute
from app.utils.dates import month_bounds, today_in
from app.utils.money import ZERO, quantize


def get_account_summaries(db: Session, user: User) -> dict[str, Any]:
    accounts = [
        {
            "id": str(a.id),
            "name": a.name,
            "type": a.account_type,
            "balance": str(s.posted_balance),
            "contributes_to_safe_to_spend": a.include_in_safe_to_spend,
        }
        for a, s in list_accounts(db, user.id)
    ]
    return {"accounts": accounts, "totals": {k: str(v) for k, v in totals(db, user.id).items()}}


def get_spending_summary(db: Session, user: User, days: int = 30) -> dict[str, Any]:
    end = today_in(user.timezone)
    start = end - timedelta(days=days)
    totals_row = period_totals(db, user.id, start, end)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "income": str(totals_row["income"]),
        "spending": str(totals_row["spending"]),
        "net": str(totals_row["net"]),
        "by_category": top_spending_categories(db, user.id, start, end, 10),
        "note": "Internal transfers are excluded from income and spending.",
    }


def get_budget_overview(db: Session, user: User) -> dict[str, Any]:
    today = today_in(user.timezone)
    budget = get_budget(db, user.id, today.year, today.month)
    if budget is None:
        return {"current_month": f"{today.year}-{today.month:02d}", "budget": None}
    summary = budget_summary(db, user.id, budget, today)
    return {
        "current_month": f"{today.year}-{today.month:02d}",
        "budget": {
            "total_allocated": str(summary["total_allocated"]),
            "total_spent": str(summary["total_spent"]),
            "total_remaining": str(summary["total_remaining"]),
            "rows": [
                {
                    "category": row["category_name"],
                    "allocated": str(row["allocated"]),
                    "spent": str(row["spent"]),
                    "remaining": str(row["remaining"]),
                    "upcoming_commitments": str(row["upcoming_commitments"]),
                }
                for row in summary["rows"]
            ],
        },
    }


def _upcoming_bills(db: Session, user: User, days: int = 30) -> dict[str, Any]:
    today = today_in(user.timezone)
    end = today + timedelta(days=days)
    rows = [
        occurrence_dict(o, today)
        for o in horizon_candidates(db, user.id, today, end)
    ]
    return {
        "today": today.isoformat(),
        "horizon_end": end.isoformat(),
        "bills": rows,
        "total_due": str(quantize(sum((Decimal(r["remaining_amount"]) for r in rows), ZERO))),
    }


def get_recurring_payments(db: Session, user: User) -> dict[str, Any]:
    bills = list(
        db.scalars(
            select(Bill).where(Bill.user_id == user.id, Bill.is_active.is_(True))
        )
    )
    return {
        "recurring_payments": [
            {
                "name": b.name,
                "merchant": b.merchant,
                "amount": str(quantize(b.expected_amount)),
                "frequency": b.frequency,
                "next_anchor": b.anchor_date.isoformat(),
                "is_essential": b.is_essential,
                "reserved": b.reserve_in_safe_to_spend,
            }
            for b in bills
        ]
    }


def get_safe_to_spend_explanation(db: Session, user: User) -> dict[str, Any]:
    return compute(db, user).as_dict()


def get_cash_flow_forecast(db: Session, user: User, days: int = 60) -> dict[str, Any]:
    return cash_flow_forecast(db, user, days)


def get_category_trends(db: Session, user: User, months: int = 3) -> dict[str, Any]:
    today = today_in(user.timezone)
    categories = {
        c.id: c
        for c in db.scalars(
            select(Category).where(Category.user_id == user.id, Category.is_archived.is_(False))
        )
    }
    series: dict[str, list[dict[str, str]]] = {
        c.name: [] for c in categories.values()
    }
    cursor_year, cursor_month = today.year, today.month
    for _ in range(max(1, min(months, 12))):
        first, last = month_bounds(cursor_year, cursor_month)
        spent = spending_by_category(db, user.id, first, last)
        label = f"{cursor_year}-{cursor_month:02d}"
        for category_id, amount in spent.items():
            category = categories.get(category_id)
            if category:
                series.setdefault(category.name, []).append(
                    {"month": label, "spent": str(amount)}
                )
        prev = date(cursor_year, cursor_month, 1) - timedelta(days=1)
        cursor_year, cursor_month = prev.year, prev.month
    return {"months": months, "series": series}


def get_category_availability(db: Session, user: User, category_id) -> dict[str, Any]:
    return category_availability(db, user, category_id).as_dict()


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "accounts": {"description": "Account balances and totals", "fn": get_account_summaries},
    "spending": {"description": "Spending and income summary", "fn": get_spending_summary},
    "budget": {"description": "Current month budget", "fn": get_budget_overview},
    "upcoming_bills": {"description": "Bills due soon", "fn": _upcoming_bills},
    "recurring_payments": {"description": "Recurring bills", "fn": get_recurring_payments},
    "safe_to_spend": {"description": "Safe-to-Spend explanation", "fn": get_safe_to_spend_explanation},
    "forecast": {"description": "Cash-flow forecast", "fn": get_cash_flow_forecast},
    "category_trends": {"description": "Category spending trends", "fn": get_category_trends},
    "category_availability": {"description": "Category budget availability", "fn": get_category_availability},
}


def call_tool(db: Session, user: User, name: str, **kwargs) -> dict[str, Any]:
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        raise ValueError(f"Unknown tool: {name}")
    fn: Callable = tool["fn"]
    return fn(db, user, **kwargs)
