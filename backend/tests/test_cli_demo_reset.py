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
