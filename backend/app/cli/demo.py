"""Demo data: explicitly flagged, deterministic and removable."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Bill,
    BillOccurrence,
    Budget,
    Category,
    FinancialAccount,
    IncomeSource,
    PlannedReserve,
    Transaction,
    User,
)
from app.models.enums import AccountType, OccurrenceStatus, TransactionType
from app.services.bills import ensure_bill_occurrences, materialize_all
from app.services.budgets import budget_summary, get_budget
from app.services.categories import DEFAULT_CATEGORIES
from app.services.errors import ConflictError
from app.services.users import get_user_by_email, register_user
from app.utils.dates import add_months, month_bounds, today_in, utc_now

D = Decimal
DEMO_NOTES = "Demo data - delete with `pfc seed-demo --remove`."


def demo_exists(db: Session, email: str) -> bool:
    return get_user_by_email(db, email) is not None


def remove_demo(db: Session, email: str) -> int:
    from app.models import (
        BillPaymentMatch,
        ImportRecord,
        TransactionImport,
    )

    users = list(db.scalars(select(User).where(User.is_demo.is_(True))))
    if email:
        user = get_user_by_email(db, email)
        if user and user.is_demo:
            users.append(user)
    removed = 0
    for user in {u.id: u for u in users}.values():
        # Explicit order keeps foreign keys happy.
        db.query(ImportRecord).filter(
            ImportRecord.import_id.in_(
                select(TransactionImport.id).where(TransactionImport.user_id == user.id)
            )
        ).delete(synchronize_session=False)
        db.query(BillPaymentMatch).filter(BillPaymentMatch.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(BillOccurrence).filter(BillOccurrence.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(Bill).filter(Bill.user_id == user.id).delete(synchronize_session=False)
        db.query(Transaction).filter(Transaction.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(TransactionImport).filter(TransactionImport.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(PlannedReserve).filter(PlannedReserve.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(IncomeSource).filter(IncomeSource.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(FinancialAccount).filter(FinancialAccount.user_id == user.id).delete(
            synchronize_session=False
        )
        for budget in db.scalars(select(Budget).where(Budget.user_id == user.id)):
            db.delete(budget)
        db.query(Category).filter(Category.user_id == user.id).delete(synchronize_session=False)
        db.delete(user)
        removed += 1
    db.commit()
    return removed


def seed_demo(db: Session, *, email: str, password: str, timezone: str) -> User:
    existing = get_user_by_email(db, email)
    if existing is not None:
        if existing.is_demo:
            return existing
        raise ConflictError(
            "That email belongs to a non-demo account. Choose another DEMO_USER_EMAIL."
        )

    user = register_user(
        db,
        email=email,
        password=password,
        display_name="Demo User",
        timezone=timezone,
    )
    user.is_demo = True
    user.onboarding_completed_at = utc_now()
    db.flush()
    today = today_in(timezone)

    categories = {
        c.name: c
        for c in db.scalars(select(Category).where(Category.user_id == user.id))
    }

    checking = FinancialAccount(
        user_id=user.id,
        name="Everyday Checking",
        account_type=AccountType.CHECKING.value,
        opening_balance=D("1200.00"),
        opening_balance_date=today - timedelta(days=90),
        include_in_safe_to_spend=True,
        description=DEMO_NOTES,
        institution="Demo Bank",
    )
    savings = FinancialAccount(
        user_id=user.id,
        name="Savings",
        account_type=AccountType.SAVINGS.value,
        opening_balance=D("2500.00"),
        opening_balance_date=today - timedelta(days=90),
        include_in_safe_to_spend=False,
        description=DEMO_NOTES,
        institution="Demo Bank",
    )
    card = FinancialAccount(
        user_id=user.id,
        name="Everyday Credit Card",
        account_type=AccountType.CREDIT_CARD.value,
        opening_balance=D("0.00"),
        opening_balance_date=today - timedelta(days=90),
        include_in_safe_to_spend=False,
        credit_limit=D("2000.00"),
        description=DEMO_NOTES,
        institution="Demo Bank",
    )
    cash = FinancialAccount(
        user_id=user.id,
        name="Cash Wallet",
        account_type=AccountType.CASH.value,
        opening_balance=D("120.00"),
        opening_balance_date=today - timedelta(days=90),
        include_in_safe_to_spend=True,
        description=DEMO_NOTES,
    )
    db.add_all([checking, savings, card, cash])
    db.flush()

    db.add(
        IncomeSource(
            user_id=user.id,
            name="Paycheck",
            amount=D("2400.00"),
            frequency="biweekly",
            next_payday=today + timedelta(days=(4 - today.weekday()) % 14 or 7),
            account_id=checking.id,
        )
    )

    def add_txn(account, amount, tx_type, description, merchant, category, days_ago, status="posted"):
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                description=description,
                merchant=merchant,
                amount=D(amount),
                tx_type=tx_type,
                status=status,
                txn_date=today - timedelta(days=days_ago),
                category_id=categories[category].id if category else None,
                notes=DEMO_NOTES,
            )
        )

    add_txn(checking, "2400.00", "income", "Paycheck deposit", "Employer", "Savings", 12)
    add_txn(checking, "1450.00", "purchase", "Rent", "Maple Apartments", "Housing", 34)
    add_txn(checking, "1420.00", "purchase", "Rent", "Maple Apartments", "Housing", 4)
    add_txn(checking, "112.30", "purchase", "Electric bill", "City Power", "Electricity", 9)
    add_txn(checking, "85.00", "purchase", "Internet", "Comcast", "Internet", 6)
    add_txn(card, "63.20", "purchase", "Groceries", "Aldi", "Groceries", 2)
    add_txn(card, "18.75", "purchase", "Lunch", "Chipotle", "Fast food", 1)
    add_txn(card, "65.00", "purchase", "Running shoes", "Target", "Clothing", 5)
    add_txn(cash, "22.00", "purchase", "Coffee beans", "Local Roaster", "Groceries", 3)
    add_txn(checking, "54.10", "purchase", "Fuel", "Shell", "Fuel", 7)
    add_txn(checking, "15.99", "purchase", "Streaming", "Netflix", "Entertainment", 11)
    add_txn(checking, "40.00", "purchase", "Pending debit", "Neighborhood Market", "Groceries", 0, "pending")
    add_txn(checking, "9.50", "purchase", "Card refund", "Target", "Clothing", 2, "posted")
    db.flush()
    # Turn the last purchase into a refund for realism.
    refund = db.scalar(
        select(Transaction)
        .where(Transaction.user_id == user.id, Transaction.description == "Card refund")
        .limit(1)
    )
    if refund:
        refund.tx_type = TransactionType.REFUND.value
    db.flush()

    # Bills with a mix of statuses.
    bill_specs = [
        ("Rent", "Maple Apartments", "1450.00", "Housing", today + timedelta(days=26), "monthly", True),
        ("Electricity", "City Power", "112.30", "Electricity", today + timedelta(days=8), "monthly", True),
        ("Internet", "Comcast", "85.00", "Internet", today + timedelta(days=-2), "monthly", True),
        ("Phone", "T-Mobile", "70.00", "Phone", today + timedelta(days=5), "monthly", True),
        ("Car insurance", "Geico", "128.00", "Insurance", today + timedelta(days=12), "quarterly", True),
        ("Streaming", "Netflix", "15.99", "Entertainment", today + timedelta(days=16), "monthly", False),
    ]
    bills = []
    for name, merchant, amount, category_name, anchor, frequency, essential in bill_specs:
        bill = Bill(
            user_id=user.id,
            name=name,
            merchant=merchant,
            expected_amount=D(amount),
            due_day=anchor.day,
            anchor_date=anchor,
            frequency=frequency,
            account_id=checking.id,
            category_id=categories[category_name].id,
            is_essential=essential,
            reserve_in_safe_to_spend=True,
            is_active=True,
            notes=DEMO_NOTES,
        )
        db.add(bill)
        bills.append(bill)
    db.flush()
    for bill in bills:
        ensure_bill_occurrences(db, bill, today + timedelta(days=200))

    # Mark the internet bill paid with a matching transaction (demo only).
    internet = next(b for b in bills if b.name == "Internet")
    occurrence = db.scalar(
        select(BillOccurrence)
        .where(BillOccurrence.bill_id == internet.id, BillOccurrence.status == OccurrenceStatus.UPCOMING.value)
        .order_by(BillOccurrence.due_date)
        .limit(1)
    )
    if occurrence:
        occurrence.paid_amount = occurrence.expected_amount
        occurrence.status = OccurrenceStatus.PAID.value
        occurrence.confirmed_at = utc_now()

    # Budget for this month based on a $4,800 income cycle.
    year, month = today.year, today.month
    existing_budget = get_budget(db, user.id, year, month)
    if existing_budget is None:
        budget = Budget(
            user_id=user.id,
            year=year,
            month=month,
            name="Demo budget",
            planned_income=D("4800.00"),
            notes=DEMO_NOTES,
        )
        db.add(budget)
        db.flush()
        allocations = {
            "Housing": "1450.00",
            "Groceries": "450.00",
            "Electricity": "130.00",
            "Internet": "90.00",
            "Phone": "75.00",
            "Insurance": "130.00",
            "Clothing": "70.00",
            "Fuel": "140.00",
            "Fast food": "60.00",
            "Entertainment": "60.00",
            "Savings": "400.00",
            "Miscellaneous": "100.00",
        }
        from app.models import BudgetAllocation

        for name, amount in allocations.items():
            db.add(
                BudgetAllocation(
                    budget_id=budget.id,
                    category_id=categories[name].id,
                    amount=D(amount),
                    carryover_enabled=name in {"Clothing", "Groceries"},
                )
            )

    db.add(
        PlannedReserve(
            user_id=user.id,
            name="Emergency fund contribution",
            amount=D("100.00"),
            is_savings=True,
            category_id=categories["Savings"].id,
            start_date=today,
            notes=DEMO_NOTES,
        )
    )
    user.last_login_at = utc_now()
    db.commit()
    materialize_all(db, user.id, timezone)
    return user


def demo_summary(db: Session, user: User) -> dict[str, object]:
    today = today_in(user.timezone)
    budget = get_budget(db, user.id, today.year, today.month)
    from app.services.safe_to_spend import compute

    return {
        "email": user.email,
        "user_id": str(user.id),
        "safe_to_spend": str(compute(db, user).safe_to_spend),
        "budget": (budget_summary(db, user.id, budget, today)["total_allocated"] if budget else "0.00"),
        "note": DEMO_NOTES,
    }
