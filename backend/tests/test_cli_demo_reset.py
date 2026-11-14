"""`pfc seed-demo --remove` must delete a demo account exactly once, quietly.

The demo reset has its own deletion path — ``app/cli/demo.remove_demo`` iterates
users and issues raw ``DELETE``s — so the account-deletion regression test does
not cover it. A stray ``DELETE`` that matches no rows is how a double delete
announces itself ("expected to delete N row(s); 0 were matched"), and
``pyproject.toml`` turns ``sqlalchemy.exc.SAWarning`` into an error, so the
warning filter is what fails these tests rather than the assertions below. The
counts stay here because they say what "removed" is supposed to mean: a reset
that quietly deletes nothing would otherwise look like a pass.
"""

from __future__ import annotations

from sqlalchemy import func, select
from typer.testing import CliRunner

from app.cli.main import app as cli
from app.config import settings
from app.models import (
    Bill,
    BillOccurrence,
    BillPaymentMatch,
    Budget,
    Category,
    FinancialAccount,
    ImportRecord,
    IncomeSource,
    PlannedReserve,
    Transaction,
    TransactionImport,
    User,
)
from app.services.users import get_user_by_email, register_user

runner = CliRunner()
PASSWORD = "TestPassword123"

# Rows the seed is known to create; each must exist before the reset, or the
# deletes below would be matching empty tables and proving nothing.
SEEDED = (
    FinancialAccount,
    Transaction,
    Bill,
    BillOccurrence,
    Budget,
    Category,
    IncomeSource,
    PlannedReserve,
)

# Everything the reset is responsible for, whether or not the seed populated it.
OWNED = SEEDED + (TransactionImport, BillPaymentMatch)


def _seed() -> None:
    result = runner.invoke(cli, ["seed-demo"])
    assert result.exit_code == 0, result.output
    assert "Demo data ready" in result.output


def _count(db, model, user_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    )


def _imports_for(db, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(ImportRecord)
        .where(
            ImportRecord.import_id.in_(
                select(TransactionImport.id).where(TransactionImport.user_id == user_id)
            )
        )
    )


def test_removing_the_demo_account_deletes_every_owned_row(db):
    _seed()
    db.expire_all()

    demo = get_user_by_email(db, settings.demo_user_email)
    assert demo is not None and demo.is_demo
    demo_id = demo.id

    for model in SEEDED:
        assert _count(db, model, demo_id) > 0, f"{model.__name__} was not seeded"

    result = runner.invoke(cli, ["seed-demo", "--remove", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Removed 1 demo account(s)." in result.output

    db.expire_all()
    assert get_user_by_email(db, settings.demo_user_email) is None
    assert db.get(User, demo_id) is None
    for model in OWNED:
        assert _count(db, model, demo_id) == 0, f"{model.__name__} rows survived the reset"
    assert _imports_for(db, demo_id) == 0


def test_the_reset_leaves_a_real_account_alone(db, user):
    _seed()
    real_id = user.id
    real_categories = _count(db, Category, real_id)
    assert real_categories > 0

    result = runner.invoke(cli, ["seed-demo", "--remove", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Removed 1 demo account(s)." in result.output

    db.expire_all()
    assert db.get(User, real_id) is not None
    assert _count(db, Category, real_id) == real_categories
    assert get_user_by_email(db, settings.demo_user_email) is None


def test_a_second_reset_finds_nothing_to_remove(db):
    _seed()
    assert runner.invoke(cli, ["seed-demo", "--remove", "--yes"]).exit_code == 0

    # Repeating the reset must be a no-op: the rows are already gone, so the same
    # deletes run again over empty tables. A warning here would mean the reset
    # cannot tell "already removed" from "removed twice".
    result = runner.invoke(cli, ["seed-demo", "--remove", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Removed 0 demo account(s)." in result.output


def test_reseeding_after_a_reset_starts_from_scratch(db):
    _seed()
    assert runner.invoke(cli, ["seed-demo", "--remove", "--yes"]).exit_code == 0

    _seed()
    db.expire_all()
    demo = get_user_by_email(db, settings.demo_user_email)
    assert demo is not None and demo.is_demo
    # The seed creates exactly four accounts (checking, savings, card, cash), so a
    # reseed that appended to leftovers would show more than four here.
    assert _count(db, FinancialAccount, demo.id) == 4


def test_removing_the_demo_account_clears_phase_4_rows_too(db, user):
    """The reset owns every table a demo account can own, not just the seeded ones.

    The seed creates the Phase 1/2 rows above. Phase 4 rows — a loan, a savings
    goal, a tracked place and the visit recorded there — are never seeded, but a
    demo account can acquire them the moment somebody clicks around the app, and
    they hang off ``users.id`` with ``ON DELETE CASCADE``. So the same reset has to
    clear them, and clear them once: the ``User`` row is deleted last, which means
    anything the database already removed must not be asked for again, or the
    ``SAWarning`` filter fails this test instead of the assertions.
    """
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from app.models import (
        InsightDismissal,
        Loan,
        LoanPayment,
        SavingsContribution,
        SavingsGoal,
        ShoppingVisit,
        TrackedLocation,
    )

    phase_4 = (
        Loan,
        LoanPayment,
        SavingsGoal,
        SavingsContribution,
        TrackedLocation,
        ShoppingVisit,
        InsightDismissal,
    )

    _seed()
    db.expire_all()
    demo = get_user_by_email(db, settings.demo_user_email)
    assert demo is not None and demo.is_demo
    demo_id = demo.id

    loan = Loan(
        user_id=demo.id,
        name="Demo payday loan",
        lender="QuickCash",
        original_amount=Decimal("300.00"),
        opening_balance=Decimal("220.00"),
        balance_as_of=date.today(),
    )
    goal = SavingsGoal(
        user_id=demo.id,
        name="Demo holiday fund",
        target_amount=Decimal("1200.00"),
        saved_amount=Decimal("150.00"),
    )
    place = TrackedLocation(
        user_id=demo.id,
        name="Demo corner shop",
        merchant="Corner Shop",
        merchant_key="corner-shop",
    )
    db.add_all([loan, goal, place])
    db.flush()
    db.add_all(
        [
            LoanPayment(
                user_id=demo.id,
                loan_id=loan.id,
                amount=Decimal("80.00"),
                paid_on=date.today(),
            ),
            SavingsContribution(
                user_id=demo.id,
                goal_id=goal.id,
                amount=Decimal("50.00"),
                contributed_on=date.today(),
            ),
            ShoppingVisit(
                user_id=demo.id,
                tracked_location_id=place.id,
                business_name="Corner Shop",
                merchant_key="corner-shop",
                visited_at=datetime.now(UTC),
                visit_day=date.today(),
            ),
            InsightDismissal(user_id=demo.id, key="merchant:corner-shop"),
        ]
    )
    # A second account's Phase 4 row: the reset must be scoped to demo users, so
    # this one is the control that says the cascade above was not just a wipe.
    db.add(
        Loan(
            user_id=user.id,
            name="Real loan",
            lender="Real Lender",
            original_amount=Decimal("900.00"),
            opening_balance=Decimal("800.00"),
            balance_as_of=date.today(),
        )
    )
    db.commit()

    # Prove the fixture: a reset that ran before any of this existed would prove
    # nothing about the cascade.
    for model in phase_4:
        assert _count(db, model, demo_id) > 0, f"{model.__name__} was not set up"

    result = runner.invoke(cli, ["seed-demo", "--remove", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Removed 1 demo account(s)." in result.output

    db.expire_all()
    assert db.get(User, demo_id) is None
    for model in phase_4:
        assert (
            _count(db, model, demo_id) == 0
        ), f"{model.__name__} outlived the demo account it belonged to"
    # The control: the same table that was just emptied for the demo account still
    # holds another user's row, so the deletes were scoped rather than sweeping.
    assert _count(db, Loan, user.id) == 1, "the demo reset deleted a real account's loan"
