"""One forward-looking list of everything the user owes.

Bills, loan instalments, BNPL/cash-advance repayments and credit-card minimums are
merged into a single ordered view. The rules that keep it honest:

* A bill occurrence and the loan instalment it repays cannot both appear: loan
  instalments already settled by a recorded repayment are dropped.
* Credit-card *repayments* are transfers, not spending, and are never shown as
  obligations in their own right. Only a minimum payment the owner typed in is.
* Income is reported separately. It is never netted against obligations to make
  the total look smaller.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FinancialAccount, IncomeSource, User
from app.models.enums import AccountType
from app.services.bills import horizon_candidates, next_payday_date
from app.services.loans import upcoming_payments
from app.services.safe_to_spend import account_is_stale, last_transaction_date
from app.utils.dates import today_in
from app.utils.money import ZERO, quantize


def _bill_items(db: Session, user: User, today: date, horizon_end: date) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for occurrence in horizon_candidates(db, user.id, today, horizon_end):
        bill = occurrence.bill
        if bill is None or not bill.is_active:
            continue
        remaining = occurrence.remaining_amount
        if remaining <= ZERO:
            continue
        items.append(
            {
                "kind": "bill",
                "id": str(occurrence.id),
                "source_id": str(bill.id),
                "name": bill.name,
                "detail": "Recurring bill" if bill.frequency != "custom" else "Scheduled payment",
                "due_date": occurrence.due_date.isoformat(),
                "amount": str(quantize(remaining)),
                "status": "overdue" if occurrence.due_date < today else "upcoming",
                "is_overdue": occurrence.due_date < today,
                "is_estimate": False,
                "is_essential": bill.is_essential,
                "category_id": str(bill.category_id) if bill.category_id else None,
                "account_id": str(bill.account_id) if bill.account_id else None,
                "reserved_in_safe_to_spend": bill.reserve_in_safe_to_spend,
            }
        )
    return items


def _loan_items(db: Session, user: User, today: date, horizon_end: date) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for row in upcoming_payments(db, user, today=today, horizon_end=horizon_end):
        items.append(
            {
                "kind": "loan",
                "id": f"loan-{row['loan_id']}-{row['due_date'].isoformat()}",
                "source_id": str(row["loan_id"]),
                "name": row["loan_name"],
                "detail": row["lender"] or "Loan or advance repayment",
                "due_date": row["due_date"].isoformat(),
                "amount": str(quantize(row["amount"])),
                "status": "overdue" if row["is_overdue"] else "upcoming",
                "is_overdue": bool(row["is_overdue"]),
                "is_estimate": bool(row["is_estimate"]),
                "is_essential": True,
                "category_id": str(row["category_id"]) if row["category_id"] else None,
                "account_id": str(row["account_id"]) if row["account_id"] else None,
                "reserved_in_safe_to_spend": True,
                "remaining_balance": str(quantize(row["remaining_balance"])),
            }
        )
    return items


def _credit_card_items(db: Session, user: User) -> list[dict[str, object]]:
    cards = db.scalars(
        select(FinancialAccount).where(
            FinancialAccount.user_id == user.id,
            FinancialAccount.is_archived.is_(False),
            FinancialAccount.account_type == AccountType.CREDIT_CARD.value,
            FinancialAccount.minimum_payment.is_not(None),
        )
    )
    items: list[dict[str, object]] = []
    for card in cards:
        minimum = quantize(card.minimum_payment or ZERO)
        if minimum <= ZERO:
            continue
        items.append(
            {
                "kind": "credit_card",
                "id": f"card-{card.id}",
                "source_id": str(card.id),
                "name": f"{card.name} minimum payment",
                "detail": "Credit card payment (a transfer, not a purchase)",
                "due_date": None,
                "amount": str(minimum),
                "status": "upcoming",
                "is_overdue": False,
                "is_estimate": False,
                "is_essential": True,
                "category_id": None,
                "account_id": str(card.id),
                "reserved_in_safe_to_spend": True,
            }
        )
    return items


def unified_obligations(db: Session, user: User, *, days: int = 45) -> dict[str, object]:
    today = today_in(user.timezone)
    horizon_end = today + timedelta(days=max(1, min(days, 180)))
    items = _bill_items(db, user, today, horizon_end)
    items += _loan_items(db, user, today, horizon_end)
    items += _credit_card_items(db, user)
    items.sort(
        key=lambda item: (
            item["due_date"] is None,
            item["due_date"] or "",
            str(item["name"]).lower(),
        )
    )

    total = quantize(sum((Decimal(str(item["amount"])) for item in items), ZERO))
    overdue = quantize(
        sum((Decimal(str(item["amount"])) for item in items if item["is_overdue"]), ZERO)
    )
    due_soon = quantize(
        sum(
            (
                Decimal(str(item["amount"]))
                for item in items
                if item["due_date"] is not None
                and today <= date.fromisoformat(str(item["due_date"])) <= today + timedelta(days=7)
            ),
            ZERO,
        )
    )
    payday = next_payday_date(db, user.id, today)
    before_payday = quantize(
        sum(
            (
                Decimal(str(item["amount"]))
                for item in items
                if item["due_date"] is not None
                and (
                    (payday is None and item["due_date"] <= (today + timedelta(days=14)).isoformat())
                    or (
                        payday is not None
                        and item["due_date"] <= payday.isoformat()
                    )
                )
            ),
            ZERO,
        )
    )

    income = list(
        db.scalars(
            select(IncomeSource).where(
                IncomeSource.user_id == user.id, IncomeSource.is_active.is_(True)
            )
        )
    )
    latest = last_transaction_date(db, user.id)
    stale = account_is_stale(db, user, today)

    return {
        "today": today.isoformat(),
        "horizon_end": horizon_end.isoformat(),
        "next_payday": payday.isoformat() if payday else None,
        "items": items,
        "counts": {
            "total": len(items),
            "overdue": len([item for item in items if item["is_overdue"]]),
            "estimated": len([item for item in items if item["is_estimate"]]),
        },
        "totals": {
            "due_in_horizon": str(total),
            "overdue": str(overdue),
            "due_within_7_days": str(due_soon),
            "due_before_payday": str(before_payday),
        },
        "income": {
            "next_payday": payday.isoformat() if payday else None,
            "sources": [
                {
                    "name": source.name,
                    "amount": str(quantize(source.amount)),
                    "frequency": source.frequency,
                    "next_payday": source.next_payday.isoformat() if source.next_payday else None,
                }
                for source in income
            ],
            "note": "Income is shown separately and is never netted off the amount owed.",
        },
        "data_freshness": {
            "last_transaction_date": latest.isoformat() if latest else None,
            "stale": stale,
            "warning": (
                "No transactions in the last 45 days. Obligations may be out of date."
                if stale
                else None
            ),
        },
        "double_counting_guards": [
            "Transfers between your own accounts are never income or spending.",
            "Credit card repayments settle a liability; they are not counted as purchases.",
            "A loan instalment already covered by a recorded repayment is not listed again.",
        ],
    }
