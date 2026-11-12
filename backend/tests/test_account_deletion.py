"""Deleting a user's account must remove every row once, quietly.

Budgets and budget allocations used to be deleted twice: the ORM was asked to delete
them, but ``budget_allocations.category_id`` and ``budgets.user_id`` are ON DELETE
CASCADE, so deleting the user's categories and the user row had already removed them.
The second DELETE matched no rows and SQLAlchemy warned ("expected to delete N row(s);
0 were matched"). That is the symptom this test pins down: a stray warning here means
the deletion path and the database disagree about who removes what.
"""

from __future__ import annotations

import uuid
import warnings
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.database.base import SessionLocal
from app.models import (
    Budget,
    BudgetAllocation,
    Category,
    InsightDismissal,
    Loan,
    LoanPayment,
    SavingsContribution,
    SavingsGoal,
    ShoppingVisit,
    TrackedLocation,
    Transaction,
    User,
)
from app.schemas.planning import BudgetAllocationInput, BudgetCreate
from app.services.budgets import create_budget
from app.services.users import delete_user_account, register_user

PASSWORD = "TestPassword123"


# Every Phase 4 table a user owns. The models declare ``ON DELETE CASCADE`` from
# ``users.id`` and ``User`` has no relationship to any of them, so ``DELETE FROM
# users`` is the only thing that removes these rows: if the schema and the models
# ever disagree, they survive and this tuple catches it.
PHASE_4_OWNED = (
    Loan,
    LoanPayment,
    SavingsGoal,
    SavingsContribution,
    TrackedLocation,
    ShoppingVisit,
    InsightDismissal,
)


def _phase_4_rows(db, user) -> None:
    """One row in every Phase 4 table, including children of children."""
    loan = Loan(
        user_id=user.id,
        name=f"Car loan {user.id.hex[:6]}",
        lender="Example Lender",
        original_amount=Decimal("12000.00"),
        opening_balance=Decimal("8400.00"),
        balance_as_of=date.today(),
    )
    goal = SavingsGoal(
        user_id=user.id,
        name=f"Emergency fund {user.id.hex[:6]}",
        target_amount=Decimal("5000.00"),
        saved_amount=Decimal("1250.00"),
    )
    place = TrackedLocation(
        user_id=user.id,
        name=f"Target {user.id.hex[:6]}",
        merchant="Target",
        merchant_key="target",
    )
    db.add_all([loan, goal, place])
    # Ids come from the parent rows above, so the children need them flushed first.
    db.flush()
    db.add_all(
        [
            LoanPayment(
                user_id=user.id,
                loan_id=loan.id,
                amount=Decimal("310.00"),
                paid_on=date.today(),
            ),
            SavingsContribution(
                user_id=user.id,
                goal_id=goal.id,
                amount=Decimal("100.00"),
                contributed_on=date.today(),
            ),
            ShoppingVisit(
                user_id=user.id,
                tracked_location_id=place.id,
                business_name="Target",
                merchant_key="target",
                visited_at=datetime.now(UTC),
                visit_day=date.today(),
            ),
            InsightDismissal(user_id=user.id, key=f"merchant:target:{user.id.hex[:6]}"),
        ]
    )
    db.commit()


def _budget_for(db, user) -> Budget:
    categories = list(db.scalars(select(Category).where(Category.user_id == user.id)).all())
    assert categories, "registration should have created default categories"
    return create_budget(
        db,
        user.id,
        BudgetCreate(
            year=date.today().year,
            month=date.today().month,
            allocations=[
                BudgetAllocationInput(category_id=row.id, amount=Decimal("25.00"))
                for row in categories[:2]
            ],
        ),
    )


def test_deleting_an_account_does_not_delete_budgets_twice(db, user):
    budget = _budget_for(db, user)
    budget_id = budget.id
    allocation_ids = [
        row.id
        for row in db.scalars(
            select(BudgetAllocation).where(BudgetAllocation.budget_id == budget_id)
        )
    ]
    assert len(allocation_ids) == 2
    db.commit()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        delete_user_account(db, user, PASSWORD, "DELETE")
        db.commit()

    double_deletes = [
        str(item.message) for item in caught if "expected to delete" in str(item.message)
    ]
    assert not double_deletes, (
        "the deletion path asked SQLAlchemy to delete rows the database had already "
        f"cascade-deleted: {double_deletes}"
    )

    assert db.get(Budget, budget_id) is None
    assert db.scalars(
        select(BudgetAllocation).where(BudgetAllocation.id.in_(allocation_ids))
    ).all() == []
    assert db.get(User, user.id) is None


def test_deleting_an_account_leaves_other_accounts_untouched(db, user):
    other = register_user(
        db,
        email=f"bystander-{uuid.uuid4().hex[:8]}@example.com",
        password=PASSWORD,
        display_name="Bystander",
        timezone="America/New_York",
    )
    db.flush()

    doomed = _budget_for(db, user)
    survivor = _budget_for(db, other)
    db.commit()
    survivor_id = survivor.id

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        delete_user_account(db, user, PASSWORD, "DELETE")
        db.commit()

    assert [str(i.message) for i in caught if "expected to delete" in str(i.message)] == []

    assert db.get(Budget, doomed.id) is None
    remaining = db.get(Budget, survivor_id)
    assert remaining is not None and remaining.user_id == other.id
    assert (
        db.scalars(
            select(BudgetAllocation).where(BudgetAllocation.budget_id == survivor_id)
        ).all()
        != []
    )


def test_deleting_an_account_still_removes_financial_history(db, user):
    """The fix is about warnings, not about deleting less: everything must still go."""
    from datetime import timedelta

    from app.models import FinancialAccount
    from app.models.enums import AccountType, TransactionType
    from app.utils.money import quantize

    account = FinancialAccount(
        user_id=user.id,
        name="Everyday Checking",
        account_type=AccountType.CHECKING.value,
        opening_balance=Decimal("100.00"),
        opening_balance_date=date.today() - timedelta(days=30),
    )
    db.add(account)
    db.flush()
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            description="Coffee",
            amount=quantize(Decimal("4.50")),
            tx_type=TransactionType.PURCHASE.value,
            txn_date=date.today(),
        )
    )
    _budget_for(db, user)
    db.commit()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        delete_user_account(db, user, PASSWORD, "DELETE")
        db.commit()

    assert [str(i.message) for i in caught if "expected to delete" in str(i.message)] == []
    assert db.scalars(select(Transaction).where(Transaction.user_id == user.id)).all() == []
    assert (
        db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user.id)).all()
        == []
    )
    assert db.scalars(select(Budget).where(Budget.user_id == user.id)).all() == []


def _owned_count(session, model, user_id) -> int:
    return session.scalar(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    )


def test_deleting_a_user_takes_their_phase_4_rows_with_them(db, user):
    other = register_user(
        db,
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password=PASSWORD,
        display_name="Other User",
        timezone="America/New_York",
    )
    db.commit()

    _phase_4_rows(db, user)
    _phase_4_rows(db, other)

    victim_id, survivor_id = user.id, other.id
    for model in PHASE_4_OWNED:
        assert _owned_count(db, model, victim_id) == 1, f"{model.__name__} was not set up"

    delete_user_account(db, user, PASSWORD, "DELETE")
    db.commit()

    # Read back through a fresh session: the claim being proven is that the
    # database removed these rows, not that this session stopped mentioning them.
    with SessionLocal() as fresh:
        assert fresh.get(User, victim_id) is None
        assert fresh.get(User, survivor_id) is not None
        for model in PHASE_4_OWNED:
            assert (
                _owned_count(fresh, model, victim_id) == 0
            ), f"{model.__name__} outlived its owner"
            # The cascade is scoped to the deleted user: another account's loan,
            # goal, visit and tracked place must be exactly where they were.
            assert (
                _owned_count(fresh, model, survivor_id) == 1
            ), f"{model.__name__} deleted another user's row"
