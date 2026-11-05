"""Scenario A plus the accounting rules behind Safe-to-Spend."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.calculations.safe_to_spend import (
    AccountSnapshot,
    BillReserveItem,
    PendingItem,
    ReserveItem,
    SafeToSpendInputs,
    calculate_safe_to_spend,
)
from app.models import PlannedReserve
from app.schemas.planning import BillCreate
from app.services.bills import mark_paid
from app.services.safe_to_spend import build_inputs, compute
from app.services.bills import create_bill as create_bill_service
from tests.conftest import make_transaction

D = Decimal


def build_inputs_scenario_a(today: date, **overrides) -> SafeToSpendInputs:
    account_id = uuid.uuid4()
    bill_id = uuid.uuid4()
    defaults = dict(
        today=today,
        horizon_end=today + timedelta(days=14),
        accounts=[
            AccountSnapshot(
                id=account_id,
                name="Checking",
                account_type="checking",
                balance=D("900.00"),
                include_in_safe_to_spend=True,
            )
        ],
        pending=[
            PendingItem(
                id=uuid.uuid4(),
                account_id=account_id,
                amount=D("40.00"),
                tx_type="purchase",
            )
        ],
        bills=[
            BillReserveItem(
                occurrence_id=uuid.uuid4(),
                bill_id=bill_id,
                bill_name="Rent",
                due_date=today + timedelta(days=3),
                amount=D("300.00"),
                is_overdue=False,
                is_essential=True,
            )
        ],
        reserves=[
            ReserveItem(id=uuid.uuid4(), name="Emergency savings", amount=D("50.00"), is_savings=True)
        ],
        minimum_buffer=D("200.00"),
        last_transaction_date=today,
    )
    defaults.update(overrides)
    return SafeToSpendInputs(**defaults)


def test_scenario_a_exact_safe_to_spend(today):
    result = calculate_safe_to_spend(build_inputs_scenario_a(today))
    assert result.eligible_balance == D("900.00")
    assert result.pending_debits == D("40.00")
    assert result.bill_reserves == D("300.00")
    assert result.minimum_buffer == D("200.00")
    assert result.explicit_reserves == D("50.00")
    assert result.raw_amount == D("310.00")
    assert result.safe_to_spend == D("310.00")
    assert result.projected_shortfall == D("0.00")
    assert result.is_negative is False


def test_explanation_matches_formula(today):
    result = calculate_safe_to_spend(build_inputs_scenario_a(today))
    keys = [line.key for line in result.explanation]
    assert keys == [
        "eligible_balance",
        "pending_debits",
        "bill_reserves",
        "minimum_buffer",
        "explicit_reserves",
        "safe_to_spend",
    ]
    total = (
        result.eligible_balance
        - result.pending_debits
        - result.bill_reserves
        - result.minimum_buffer
        - result.explicit_reserves
    )
    assert total == result.raw_amount


def test_negative_result_is_clamped_but_shortfall_reported(today):
    inputs = build_inputs_scenario_a(
        today,
        bills=[
            BillReserveItem(
                occurrence_id=uuid.uuid4(),
                bill_id=uuid.uuid4(),
                bill_name="Rent",
                due_date=today + timedelta(days=2),
                amount=D("1000.00"),
                is_overdue=False,
                is_essential=True,
            )
        ],
    )
    result = calculate_safe_to_spend(inputs)
    assert result.safe_to_spend == D("0.00")
    assert result.projected_shortfall == D("390.00")
    assert result.is_negative is True
    assert any("exceed available cash" in w for w in result.warnings)


def test_pending_bill_payment_is_deducted_until_it_posts(today):
    # A confirmed bill match lowers the occurrence's remaining reserve, but the
    # pending payment has not reduced the posted balance yet. It must still be
    # deducted, otherwise Safe-to-Spend overstates available cash.
    from dataclasses import replace

    base = build_inputs_scenario_a(today)
    pending = list(base.pending)
    pending[0] = replace(base.pending[0], linked_to_bill=True)
    result = calculate_safe_to_spend(replace(base, pending=pending))
    assert result.pending_debits == D("40.00")
    assert result.safe_to_spend == D("310.00")


def test_pending_transfer_to_savings_reduces_spendable_cash(today):
    from dataclasses import replace

    base = build_inputs_scenario_a(today)
    checking = base.accounts[0].id
    savings = uuid.uuid4()
    result = calculate_safe_to_spend(
        replace(
            base,
            accounts=[
                *base.accounts,
                AccountSnapshot(
                    id=savings,
                    name="Savings",
                    account_type="savings",
                    balance=D("500.00"),
                    include_in_safe_to_spend=False,
                ),
            ],
            pending=[
                PendingItem(
                    id=uuid.uuid4(),
                    account_id=checking,
                    amount=D("100.00"),
                    tx_type="transfer",
                    counter_account_id=savings,
                )
            ],
        )
    )
    assert result.eligible_balance == D("900.00")
    assert result.pending_debits == D("100.00")
    assert result.safe_to_spend == D("250.00")


def test_pending_transfer_between_eligible_accounts_is_net_zero(today):
    from dataclasses import replace

    base = build_inputs_scenario_a(today)
    checking = base.accounts[0].id
    wallet = uuid.uuid4()
    result = calculate_safe_to_spend(
        replace(
            base,
            accounts=[
                *base.accounts,
                AccountSnapshot(
                    id=wallet,
                    name="Wallet",
                    account_type="cash",
                    balance=D("100.00"),
                    include_in_safe_to_spend=True,
                ),
            ],
            pending=[
                PendingItem(
                    id=uuid.uuid4(),
                    account_id=checking,
                    amount=D("100.00"),
                    tx_type="transfer",
                    counter_account_id=wallet,
                )
            ],
        )
    )
    assert result.eligible_balance == D("1000.00")
    assert result.pending_debits == D("0.00")
    assert result.safe_to_spend == D("450.00")


def test_credit_card_never_counts_as_cash(today):
    card = AccountSnapshot(
        id=uuid.uuid4(),
        name="Visa",
        account_type="credit_card",
        balance=D("5000.00"),
        include_in_safe_to_spend=True,
        is_liability=True,
    )
    result = calculate_safe_to_spend(
        build_inputs_scenario_a(today, accounts=[*build_inputs_scenario_a(today).accounts, card])
    )
    assert result.eligible_balance == D("900.00")
    assert any("Credit card" in warning for warning in result.warnings)


def test_archived_accounts_and_reserves_excluded(today):
    archived = AccountSnapshot(
        id=uuid.uuid4(),
        name="Old savings",
        account_type="savings",
        balance=D("1000.00"),
        include_in_safe_to_spend=True,
        is_archived=True,
    )
    result = calculate_safe_to_spend(
        build_inputs_scenario_a(today, accounts=[*build_inputs_scenario_a(today).accounts, archived])
    )
    assert result.eligible_balance == D("900.00")


def test_overdue_bill_warning(today):
    result = calculate_safe_to_spend(
        build_inputs_scenario_a(
            today,
            bills=[
                BillReserveItem(
                    occurrence_id=uuid.uuid4(),
                    bill_id=uuid.uuid4(),
                    bill_name="Electricity",
                    due_date=today - timedelta(days=5),
                    amount=D("80.00"),
                    is_overdue=True,
                    is_essential=True,
                )
            ],
        )
    )
    assert any("overdue" in warning.lower() for warning in result.warnings)


def test_stale_information_warning(today):
    result = calculate_safe_to_spend(
        build_inputs_scenario_a(today, last_transaction_date=today - timedelta(days=60))
    )
    assert result.stale_information is True
    assert any("stale" in w.lower() for w in result.warnings)


def test_no_eligible_accounts_warns(today):
    result = calculate_safe_to_spend(build_inputs_scenario_a(today, accounts=[]))
    assert result.safe_to_spend == D("0.00")
    assert any("No spending accounts" in w for w in result.warnings)


def test_integration_scenario_a(db, user, prefs, account, today):
    prefs.minimum_balance_buffer = D("200.00")
    prefs.safe_to_spend_horizon_days = 30
    db.commit()

    make_transaction(
        db,
        user,
        account,
        amount="40.00",
        description="Pending grocery",
        merchant="Aldi",
        status="pending",
        txn_date=today,
    )
    db.add(
        PlannedReserve(
            user_id=user.id,
            name="Emergency savings",
            amount=D("50.00"),
            is_savings=True,
            start_date=today - timedelta(days=1),
        )
    )
    db.commit()

    create_bill_service(
        db,
        user.id,
        BillCreate(
            name="Rent",
            expected_amount=D("300.00"),
            anchor_date=today + timedelta(days=3),
            frequency="monthly",
        ),
        user.timezone,
    )
    db.commit()

    inputs = build_inputs(db, user)
    result = compute(db, user)
    assert result.eligible_balance == D("900.00")
    assert result.pending_debits == D("40.00")
    assert result.bill_reserves == D("300.00")
    assert result.safe_to_spend == D("310.00")
    assert inputs.horizon_end >= today


def test_paid_bill_no_longer_reserved(db, user, prefs, account, today):
    prefs.safe_to_spend_horizon_days = 30
    db.commit()
    bill = create_bill_service(
        db,
        user.id,
        BillCreate(
            name="Rent",
            expected_amount=D("300.00"),
            anchor_date=today + timedelta(days=2),
            frequency="monthly",
        ),
        user.timezone,
    )
    db.commit()
    occurrence = bill.occurrences[0]
    assert compute(db, user).bill_reserves == D("300.00")
    mark_paid(db, user.id, occurrence.id)
    db.commit()
    result = compute(db, user)
    assert result.bill_reserves == D("0.00")
    assert result.safe_to_spend == D("900.00")


def test_bill_already_covered_by_payment_is_not_reserved(db, user, prefs, account, today):
    prefs.safe_to_spend_horizon_days = 30
    db.commit()
    bill = create_bill_service(
        db,
        user.id,
        BillCreate(
            name="Internet",
            merchant="Comcast",
            expected_amount=D("95.00"),
            anchor_date=today + timedelta(days=1),
            frequency="monthly",
            account_id=account.id,
        ),
        user.timezone,
    )
    db.commit()
    from app.schemas.finance import TransactionCreate
    from app.services.transactions import create_transaction

    txn, info = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Comcast internet",
            merchant="Comcast",
            amount=D("95.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    assert info is not None and info["outcome"] == "auto"
    result = compute(db, user)
    assert result.bill_reserves == D("0.00")
    assert result.safe_to_spend == D("805.00")


def test_horizon_uses_next_payday(db, user, prefs, account, today):
    from app.models import IncomeSource

    db.add(
        IncomeSource(
            user_id=user.id,
            name="Salary",
            amount=D("2000.00"),
            frequency="biweekly",
            next_payday=today + timedelta(days=5),
        )
    )
    db.commit()
    inputs = build_inputs(db, user)
    assert inputs.payday == today + timedelta(days=5)
    assert inputs.horizon_end == today + timedelta(days=5)


def test_stale_payday_is_projected_forward(db, user, prefs, account, today):
    from app.models import IncomeSource

    db.add(
        IncomeSource(
            user_id=user.id,
            name="Salary",
            amount=D("2000.00"),
            frequency="biweekly",
            next_payday=today - timedelta(days=3),
        )
    )
    db.commit()
    inputs = build_inputs(db, user)
    assert inputs.payday == today + timedelta(days=11)
    assert inputs.horizon_end == inputs.payday


def test_payday_today_uses_the_following_payday(db, user, prefs, account, today):
    from app.models import IncomeSource

    db.add(
        IncomeSource(
            user_id=user.id,
            name="Salary",
            amount=D("2000.00"),
            frequency="monthly",
            next_payday=today,
        )
    )
    db.commit()
    inputs = build_inputs(db, user)
    assert inputs.payday is not None
    assert inputs.payday > today
    assert inputs.horizon_end == inputs.payday


def test_far_payday_is_capped(db, user, prefs, account, today):
    from app.models import IncomeSource
    from app.config import settings

    db.add(
        IncomeSource(
            user_id=user.id,
            name="Salary",
            amount=D("2000.00"),
            frequency="monthly",
            next_payday=today + timedelta(days=200),
        )
    )
    db.commit()
    inputs = build_inputs(db, user)
    assert inputs.horizon_end == today + timedelta(days=settings.max_safe_to_spend_horizon_days)


def test_expected_paycheck_is_not_counted_as_available_cash(db, user, prefs, account, today):
    """A stored future paycheck changes the horizon, never the money on hand."""
    from app.models import IncomeSource

    prefs.minimum_balance_buffer = D("100.00")
    prefs.safe_to_spend_horizon_days = 30
    db.add(
        IncomeSource(
            user_id=user.id,
            name="Salary",
            amount=D("5000.00"),
            frequency="biweekly",
            next_payday=today + timedelta(days=5),
        )
    )
    db.commit()
    result = compute(db, user)
    assert result.eligible_balance == D("900.00")
    assert result.safe_to_spend == D("800.00")
    assert result.safe_to_spend < D("5000.00")
