"""Phase 4: loans, savings goals and the Safe-to-Spend arithmetic around them."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import FinancialAccount, Loan, LoanPayment, NotificationPreference, Transaction
from app.models.enums import AccountType, MatchStatus
from app.schemas.loans import LoanCreate, LoanPaymentCreate, LoanUpdate
from app.schemas.savings import SavingsContributionCreate, SavingsGoalCreate
from app.services import loans as loan_service
from app.services import savings as savings_service
from app.services.loan_matching import auto_match_transaction, suggestions_for_loan
from app.services.obligations import unified_obligations
from app.services.safe_to_spend import compute
from app.services.users import register_user
from app.utils.dates import today_in
from tests.conftest import make_transaction


def _loan(db, user, **overrides) -> Loan:
    payload = LoanCreate(
        name=overrides.pop("name", "Payday advance"),
        lender=overrides.pop("lender", "Cash App"),
        loan_type=overrides.pop("loan_type", "payday"),
        original_amount=overrides.pop("original_amount", Decimal("500.00")),
        opening_balance=overrides.pop("opening_balance", Decimal("400.00")),
        scheduled_payment=overrides.pop("scheduled_payment", Decimal("100.00")),
        next_payment_date=overrides.pop("next_payment_date", today_in(user.timezone) + timedelta(days=3)),
        payment_frequency=overrides.pop("payment_frequency", "biweekly"),
        **overrides,
    )
    return loan_service.create_loan(db, user, payload)


def _savings_account(db, user, *, spendable: bool, balance: str) -> FinancialAccount:
    row = FinancialAccount(
        user_id=user.id,
        name=f"Savings {uuid.uuid4().hex[:4]}",
        account_type=AccountType.SAVINGS.value,
        opening_balance=Decimal(balance),
        opening_balance_date=date.today() - timedelta(days=30),
        include_in_safe_to_spend=spendable,
    )
    db.add(row)
    db.commit()
    return row


# ------------------------------------------------------------------------ loans
def test_loan_balance_derives_from_confirmed_payments(db, user):
    loan = _loan(db, user)
    db.commit()

    loan_service.add_payment(
        db, user, loan.id, LoanPaymentCreate(amount=Decimal("100.00"), confirm=True)
    )
    db.commit()
    db.refresh(loan)

    payload = loan_service.loan_payload(loan)
    assert payload["current_balance"] == Decimal("300.00")
    assert payload["principal_repaid"] == Decimal("100.00")
    # The payment had no principal/interest split, so the balance is an estimate.
    assert payload["balance_is_estimate"] is True
    assert payload["progress_percent"] == Decimal("25.00")


def test_partial_payment_and_interest_split(db, user):
    loan = _loan(db, user, name="BNPL", loan_type="buy_now_pay_later")
    db.commit()

    loan_service.add_payment(
        db,
        user,
        loan.id,
        LoanPaymentCreate(
            amount=Decimal("60.00"),
            principal_amount=Decimal("50.00"),
            interest_amount=Decimal("7.50"),
            fee_amount=Decimal("2.50"),
            confirm=True,
        ),
    )
    db.commit()
    db.refresh(loan)

    payload = loan_service.loan_payload(loan)
    assert payload["current_balance"] == Decimal("350.00")
    assert payload["interest_paid"] == Decimal("7.50")
    assert payload["fees_paid"] == Decimal("2.50")
    # Every component was supplied, so nothing here is a guess.
    assert payload["balance_is_estimate"] is False
    assert payload["total_repaid"] == Decimal("60.00")


def test_suggested_payment_does_not_move_the_balance(db, user, account):
    loan = _loan(db, user)
    txn = make_transaction(
        db, user, account,
        amount="100.00", description="CASH APP LOAN PMT", merchant="Cash App",
    )
    loan_service.add_payment(
        db,
        user,
        loan.id,
        LoanPaymentCreate(amount=Decimal("100.00"), transaction_id=txn.id, confirm=False),
    )
    db.commit()
    db.refresh(loan)
    assert loan_service.loan_payload(loan)["current_balance"] == Decimal("400.00")


def test_two_loans_per_user_are_independent(db, user, account):
    first = _loan(db, user, name="Payday", opening_balance=Decimal("300.00"))
    second = _loan(db, user, name="Car repair", loan_type="personal", opening_balance=Decimal("900.00"))
    db.commit()
    loan_service.add_payment(
        db, user, first.id, LoanPaymentCreate(amount=Decimal("100.00"), confirm=True)
    )
    db.commit()

    summary = loan_service.summary(db, user.id)
    balances = {row["name"]: row["current_balance"] for row in summary["loans"]}
    assert balances == {"Payday": Decimal("200.00"), "Car repair": Decimal("900.00")}
    assert summary["total_outstanding"] == Decimal("1100.00")
    assert second.id != first.id


def test_paying_off_a_loan_marks_it_paid(db, user):
    loan = _loan(db, user, opening_balance=Decimal("100.00"), scheduled_payment=Decimal("100.00"))
    db.commit()
    loan_service.add_payment(
        db, user, loan.id, LoanPaymentCreate(amount=Decimal("100.00"), confirm=True)
    )
    db.commit()
    db.refresh(loan)
    assert loan.status == "paid_off"
    assert loan_service.summary(db, user.id)["active_loans"] == 0


def test_estimate_flags_when_terms_are_missing(db, user):
    loan = _loan(
        db,
        user,
        name="Informal loan",
        scheduled_payment=None,
        next_payment_date=None,
        payment_frequency=None,
    )
    db.commit()
    payload = loan_service.loan_payload(loan)
    assert payload["estimated_payoff_date"] is None
    assert payload["payoff_is_estimate"] is False
    assert payload["remaining_installments"] is None


def test_payoff_projection_uses_remaining_count(db, user):
    due = today_in(user.timezone) + timedelta(days=5)
    loan = _loan(db, user, name="Installment", remaining_payments=3, next_payment_date=due)
    db.commit()
    payload = loan_service.loan_payload(loan)
    assert payload["remaining_installments"] == 3
    assert payload["payoff_is_estimate"] is True
    assert payload["estimated_payoff_date"] > due


def test_transaction_auto_matches_a_single_plausible_loan(db, user, account):
    loan = _loan(db, user, scheduled_payment=Decimal("120.00"))
    db.commit()
    txn = make_transaction(
        db, user, account, amount="120.00", description="CASH APP PAYMENT", merchant="Cash App",
        txn_date=today_in(user.timezone) + timedelta(days=2),
    )
    payment = auto_match_transaction(db, user, txn)
    assert payment is not None
    assert payment.loan_id == loan.id
    assert payment.is_automatic is True
    db.commit()
    db.refresh(loan)
    assert loan_service.loan_payload(loan)["current_balance"] == Decimal("280.00")


def test_ambiguous_loans_are_not_auto_matched(db, user, account):
    _loan(db, user, name="Advance A", scheduled_payment=Decimal("120.00"))
    _loan(db, user, name="Advance B", scheduled_payment=Decimal("120.00"), lender="Cash App")
    db.commit()
    txn = make_transaction(
        db, user, account, amount="120.00", description="CASH APP PAYMENT", merchant="Cash App",
        txn_date=today_in(user.timezone) + timedelta(days=2),
    )
    assert auto_match_transaction(db, user, txn) is None


def test_suggestion_is_offered_but_not_applied_for_a_weak_match(db, user, account):
    loan = _loan(db, user, scheduled_payment=Decimal("100.00"))
    db.commit()
    make_transaction(
        db, user, account, amount="96.00", description="CASH APP PMT", merchant="Cash App",
        txn_date=today_in(user.timezone) + timedelta(days=1),
    )
    db.commit()
    rows = suggestions_for_loan(db, user, loan.id)
    assert rows, "a close amount and date should at least be suggested"
    db.refresh(loan)
    assert loan_service.loan_payload(loan)["current_balance"] == Decimal("400.00")


# ---------------------------------------------------------------------- savings
def test_virtual_savings_reduce_safe_to_spend_once(db, user, account, prefs):
    before = compute(db, user).safe_to_spend
    goal = savings_service.create_goal(
        db,
        user,
        SavingsGoalCreate(
            name="Emergency fund", target_amount=Decimal("1000.00"), saved_amount=Decimal("200.00")
        ),
    )
    db.commit()
    after = compute(db, user).safe_to_spend
    assert before - after == Decimal("200.00")

    payload = savings_service.goal_payload(
        db, goal, today=today_in(user.timezone), balances={account.id: None}
    )
    assert payload["protected_amount"] == Decimal("200.00")
    assert payload["progress_percent"] == Decimal("20.00")


def test_account_backed_savings_in_an_excluded_account_are_not_deducted_twice(db, user, prefs):
    savings = _savings_account(db, user, spendable=False, balance="500.00")
    before = compute(db, user).safe_to_spend
    savings_service.create_goal(
        db,
        user,
        SavingsGoalCreate(
            name="Holiday",
            target_amount=Decimal("800.00"),
            saved_amount=Decimal("500.00"),
            mode="account",
            account_id=savings.id,
        ),
    )
    db.commit()
    after = compute(db, user).safe_to_spend
    # The savings balance was never spendable, so protecting it changes nothing.
    assert after == before


def test_account_backed_savings_in_a_spendable_account_are_protected(db, user, prefs):
    savings = _savings_account(db, user, spendable=True, balance="500.00")
    before = compute(db, user).safe_to_spend
    savings_service.create_goal(
        db,
        user,
        SavingsGoalCreate(
            name="Holiday",
            target_amount=Decimal("800.00"),
            saved_amount=Decimal("300.00"),
            mode="account",
            account_id=savings.id,
        ),
    )
    db.commit()
    after = compute(db, user).safe_to_spend
    assert before - after == Decimal("300.00")


def test_planned_contribution_is_reserved_before_it_happens(db, user, account, prefs):
    savings_service.create_goal(
        db,
        user,
        SavingsGoalCreate(
            name="Christmas",
            target_amount=Decimal("600.00"),
            contribution_amount=Decimal("50.00"),
            contribution_frequency="weekly",
        ),
    )
    db.commit()
    safe = compute(db, user)
    assert safe.savings_reserves >= Decimal("50.00")
    assert any(item["is_planned_contribution"] for item in safe.savings)
    # Nothing was actually moved.
    assert db.scalar(select(Transaction).where(Transaction.user_id == user.id)) is None


def test_contribution_raises_saved_amount_and_completes_goal(db, user):
    goal = savings_service.create_goal(
        db,
        user,
        SavingsGoalCreate(name="Car", target_amount=Decimal("100.00"), saved_amount=Decimal("80.00")),
    )
    db.commit()
    savings_service.add_contribution(
        db, user, goal.id, SavingsContributionCreate(amount=Decimal("20.00"))
    )
    db.commit()
    db.refresh(goal)
    assert goal.saved_amount == Decimal("100.00")
    assert goal.status == "completed"


# ------------------------------------------------------------------ obligations
def test_obligations_merge_bills_and_loan_instalments(db, user, account):
    _loan(db, user, name="Payday", scheduled_payment=Decimal("100.00"))
    db.commit()
    result = unified_obligations(db, user, days=30)
    kinds = {item["kind"] for item in result["items"]}
    assert "loan" in kinds
    assert Decimal(result["totals"]["due_in_horizon"]) >= Decimal("100.00")


def test_loan_instalment_already_paid_is_not_listed_again(db, user, account):
    due = today_in(user.timezone) + timedelta(days=2)
    loan = _loan(db, user, name="Advance", scheduled_payment=Decimal("100.00"), next_payment_date=due)
    db.commit()
    loan_service.add_payment(
        db,
        user,
        loan.id,
        LoanPaymentCreate(amount=Decimal("100.00"), paid_on=due, confirm=True),
    )
    db.commit()
    result = unified_obligations(db, user, days=30)
    assert all(item["kind"] != "loan" for item in result["items"])


def test_credit_card_minimum_is_reserved_when_set(db, user, account, prefs):
    card = FinancialAccount(
        user_id=user.id,
        name="Visa",
        account_type=AccountType.CREDIT_CARD.value,
        opening_balance=Decimal("-400.00"),
        opening_balance_date=date.today() - timedelta(days=30),
        include_in_safe_to_spend=False,
        credit_limit=Decimal("2000.00"),
        minimum_payment=Decimal("35.00"),
    )
    db.add(card)
    db.commit()
    safe = compute(db, user)
    assert safe.credit_card_reserves == Decimal("35.00")
    # A credit limit is never cash.
    assert safe.eligible_balance == Decimal("900.00")


def test_engine_reports_estimated_loans_in_the_breakdown(db, user, account):
    loan = _loan(db, user, name="Payday", scheduled_payment=Decimal("100.00"))
    db.commit()
    # A repayment with no principal/interest split makes the derived balance an
    # estimate, and the engine has to say so rather than presenting it as fact.
    loan_service.add_payment(
        db, user, loan.id, LoanPaymentCreate(amount=Decimal("50.00"), confirm=True)
    )
    db.commit()
    safe = compute(db, user)
    # 50 of the 100 instalment has already been paid, so only the remainder is
    # still reserved; the paid half is not counted twice.
    assert safe.loan_reserves == Decimal("50.00")
    assert any("estimate" in warning for warning in safe.warnings)
    keys = {line.key for line in safe.explanation}
    assert {"loan_reserves", "safe_to_spend"} <= keys


def test_transfer_between_own_accounts_is_not_an_obligation(db, user, account):
    other = FinancialAccount(
        user_id=user.id,
        name="Second checking",
        account_type=AccountType.CHECKING.value,
        opening_balance=Decimal("100.00"),
        opening_balance_date=date.today() - timedelta(days=30),
        include_in_safe_to_spend=True,
    )
    db.add(other)
    db.commit()
    make_transaction(
        db, user, account, amount="50.00", tx_type="transfer",
        description="Move to savings", transfer_account_id=other.id,
    )
    result = unified_obligations(db, user, days=30)
    assert result["items"] == []


# -------------------------------------------------------------------- isolation
def test_loans_and_savings_are_isolated_between_users(db, user):
    other = register_user(
        db,
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123",
        display_name="Other",
        timezone="UTC",
    )
    db.commit()
    loan = _loan(db, user)
    savings_service.create_goal(
        db, user, SavingsGoalCreate(name="Mine", target_amount=Decimal("100.00"))
    )
    db.commit()

    assert loan_service.summary(db, other.id)["total_outstanding"] == Decimal("0.00")
    assert savings_service.summary(db, other)["active_goals"] == 0
    with pytest.raises(Exception):
        loan_service.get_loan(db, other.id, loan.id)
