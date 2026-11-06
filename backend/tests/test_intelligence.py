"""Phase 2 intelligence: category suggestions, recurring detection, insights, assistant."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ai.assistant import answer_question, assistant_status
from app.config import settings
from app.models import Category, CategorySuggestion, RecurringSeries, Transaction, User
from app.models.enums import CategorySource, RecurringStatus, TransactionType
from app.schemas.planning import BudgetAllocationInput, BudgetCreate
from app.services.budgets import create_budget
from app.services.categories import seed_default_categories
from app.services.intelligence import (
    accept_suggestion,
    detect_recurring_series,
    reject_suggestion,
    set_recurring_status,
    suggest_category,
)
from app.services.personal import merchant_profile, spending_insights
from app.services.shopping import shopping_check
from app.utils.dates import add_months, month_bounds

D = Decimal


@pytest.fixture(autouse=True)
def categories(db, user):
    seed_default_categories(db, user.id)
    db.commit()
    return db.query(Category).filter(Category.user_id == user.id).all()


def _cat(db, user, name: str) -> Category:
    return db.query(Category).filter_by(user_id=user.id, name=name).one()


def _txn(
    db,
    user,
    account,
    *,
    description="Purchase",
    merchant=None,
    amount="10.00",
    tx_type="purchase",
    txn_date=None,
    category_id=None,
    status="posted",
) -> Transaction:
    txn = Transaction(
        user_id=user.id,
        account_id=account.id,
        description=description,
        merchant=merchant,
        amount=D(amount),
        tx_type=tx_type,
        status=status,
        txn_date=txn_date or date.today(),
        category_id=category_id,
    )
    db.add(txn)
    db.commit()
    return txn


# ------------------------------------------------------------------ suggestions
def test_rule_suggestion_is_proposed_not_applied(db, user, account):
    txn = _txn(db, user, account, description="STARBUCKS STORE 08431", merchant="Starbucks")
    assert txn.category_id is None

    suggestion = suggest_category(db, user, txn)
    db.refresh(txn)

    assert suggestion is not None
    assert suggestion.source == "rule"
    assert suggestion.confidence == D("0.72")
    assert "coffee shop" in (suggestion.reason or "")
    category = db.get(Category, suggestion.category_id)
    assert category.name == "Restaurants"
    # Automation must not decide for the user.
    assert txn.category_id is None


def test_accepting_suggestion_marks_it_as_a_user_decision(db, user, account):
    txn = _txn(db, user, account, description="NETFLIX.COM", merchant="Netflix")
    suggestion = suggest_category(db, user, txn)
    assert suggestion is not None

    accept_suggestion(db, user, suggestion.id)
    db.refresh(txn)
    db.refresh(suggestion)

    assert suggestion.status == "accepted"
    assert suggestion.resolved_at is not None
    assert txn.category_id == suggestion.category_id
    assert txn.category_source == CategorySource.USER.value


def test_rejected_suggestion_is_not_offered_again(db, user, account):
    txn = _txn(db, user, account, description="SHELL OIL", merchant="Shell")
    suggestion = suggest_category(db, user, txn)
    assert suggestion is not None
    reject_suggestion(db, user, suggestion.id)

    again = suggest_category(db, user, txn)
    assert again is None


def test_confirmed_category_is_never_overwritten(db, user, account):
    category = _cat(db, user, "Shopping")
    txn = _txn(
        db,
        user,
        account,
        description="WHOLE FOODS MKT",
        merchant="Whole Foods Market",
        category_id=category.id,
    )
    txn.category_source = CategorySource.USER.value
    db.commit()

    assert suggest_category(db, user, txn) is None


def test_user_history_outranks_the_generic_rule(db, user, account):
    shopping = _cat(db, user, "Shopping")
    today = date.today()
    for offset in (60, 40, 20):
        _txn(
            db,
            user,
            account,
            description="WHOLE FOODS MKT #10251",
            merchant="Whole Foods Market",
            amount="80.00",
            txn_date=today - timedelta(days=offset),
            category_id=shopping.id,
        )
    fresh = _txn(db, user, account, description="WHOLE FOODS MKT #10251", merchant="Whole Foods Market")

    suggestion = suggest_category(db, user, fresh)
    assert suggestion is not None
    assert suggestion.source == "history"
    assert suggestion.category_id == shopping.id
    assert "3 earlier transactions" in (suggestion.reason or "")


def test_income_needs_no_category_suggestion(db, user, account):
    txn = _txn(db, user, account, description="ACME PAYROLL", tx_type="income", amount="2000.00")
    assert suggest_category(db, user, txn) is None


# -------------------------------------------------------------------- recurring
def test_recurring_detection_finds_a_monthly_subscription(db, user, account, categories):
    entertainment = _cat(db, user, "Entertainment")
    today = date.today()
    for offset in (3, 2, 1):
        when = add_months(today, -offset).replace(day=12)
        _txn(
            db,
            user,
            account,
            description="NETFLIX.COM",
            merchant="Netflix",
            amount="15.49",
            txn_date=when,
            category_id=entertainment.id,
        )

    series = detect_recurring_series(db, user)
    assert len(series) == 1
    found = series[0]
    assert found.display_name == "Netflix"
    assert found.frequency == "monthly"
    assert found.occurrences == 3
    assert found.is_subscription is True
    assert found.confidence >= D("0.7")
    assert found.category_id == entertainment.id
    assert found.next_expected_date is not None
    assert found.detail["sample_transaction_ids"]


def test_recurring_detection_needs_three_occurrences(db, user, account):
    today = date.today()
    for offset in (2, 1):
        _txn(
            db,
            user,
            account,
            description="GYM MEMBERSHIP",
            merchant="Gym",
            amount="40.00",
            txn_date=add_months(today, -offset).replace(day=5),
        )
    assert detect_recurring_series(db, user) == []


def test_irregular_spending_is_not_a_series(db, user, account):
    today = date.today()
    for days in (120, 60, 12):
        _txn(
            db,
            user,
            account,
            description="TARGET",
            merchant="Target",
            amount="120.00",
            txn_date=today - timedelta(days=days),
        )
    # Gaps of 60 and 48 days are not a stable cadence.
    assert detect_recurring_series(db, user) == []


def test_dismissed_series_stays_dismissed(db, user, account):
    today = date.today()
    for offset in (3, 2, 1):
        _txn(
            db,
            user,
            account,
            description="SPOTIFY USA",
            merchant="Spotify",
            amount="10.99",
            txn_date=add_months(today, -offset).replace(day=21),
        )
    series = detect_recurring_series(db, user)[0]
    set_recurring_status(db, user, series.id, RecurringStatus.DISMISSED)

    assert detect_recurring_series(db, user) == []
    db.refresh(series)
    assert series.status == "dismissed"


# --------------------------------------------------------------------- personal
def test_merchant_profile_refuses_to_judge_thin_history(db, user, account):
    _txn(db, user, account, description="TARGET", merchant="Target", amount="90.00")
    profile = merchant_profile(db, user, "Target")
    assert profile["has_enough_history"] is False
    assert profile["monthly_average"] is None
    assert profile["transaction_count"] == 1


def test_category_over_budget_insight_carries_evidence(db, user, account, today):
    groceries = _cat(db, user, "Groceries")
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[BudgetAllocationInput(category_id=groceries.id, amount=D("100.00"))],
        ),
    )
    db.commit()
    _txn(
        db,
        user,
        account,
        description="WHOLE FOODS",
        merchant="Whole Foods Market",
        amount="130.00",
        txn_date=today,
        category_id=groceries.id,
    )

    payload = spending_insights(db, user)
    assert payload["enabled"] is True
    over = [i for i in payload["insights"] if i["type"] == "category_over_budget"]
    assert over, payload["insights"]
    insight = over[0]
    assert insight["severity"] == "high"
    assert insight["evidence"]["allocated"] == "100.00"
    assert insight["evidence"]["spent"] == "130.00"
    assert insight["evidence"]["remaining"] == "-30.00"


def test_insights_can_be_disabled_by_the_user(db, user, account):
    prefs = db.get(__import__("app.models", fromlist=["UserPreference"]).UserPreference, user.id)
    prefs.personalized_insights_enabled = False
    db.commit()

    payload = spending_insights(db, user)
    assert payload["enabled"] is False
    assert payload["insights"] == []


def test_shopping_check_includes_merchant_history(db, user, account, today):
    groceries = _cat(db, user, "Groceries")
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[BudgetAllocationInput(category_id=groceries.id, amount=D("400.00"))],
        ),
    )
    db.commit()
    # Five purchases over three months clears the minimum-history guard.
    for offset, day_offset in ((3, 0), (3, 8), (2, 0), (2, 8), (1, 0)):
        _txn(
            db,
            user,
            account,
            description="WHOLE FOODS",
            merchant="Whole Foods Market",
            amount="70.00",
            txn_date=add_months(today, -offset) + timedelta(days=day_offset),
            category_id=groceries.id,
        )

    result = shopping_check(
        db, user, store_name="Whole Foods Market", category_id=groceries.id
    )
    advice = result["merchant_advice"]
    assert advice["has_enough_history"] is True
    assert advice["suggested_limit"] is not None
    assert "Whole Foods" in result["message"]


def test_shopping_check_is_honest_about_unknown_merchants(db, user, account):
    groceries = _cat(db, user, "Groceries")
    result = shopping_check(db, user, store_name="Brand New Shop", category_id=groceries.id)
    advice = result["merchant_advice"]
    assert advice["has_enough_history"] is False
    assert advice["suggested_limit"] is None


# -------------------------------------------------------------------- assistant
def test_assistant_answers_from_the_engine_without_a_model(db, user, account):
    result = answer_question(db, user, "How much can I safely spend?")
    assert result["mode"] == "deterministic"
    assert result["can_modify_data"] is False
    assert "Safe-to-Spend" in result["answer"]
    assert "safe_to_spend" in result["used_tools"]


def test_assistant_compares_a_named_amount(db, user, account, today):
    groceries = _cat(db, user, "Groceries")
    from app.models import UserPreference

    prefs = db.get(UserPreference, user.id)
    prefs.minimum_balance_buffer = D("0")
    prefs.safe_to_spend_horizon_days = 30
    db.commit()

    result = answer_question(db, user, "Can I afford $150 on Groceries?")
    assert "Groceries" in result["answer"]
    assert "150" in result["answer"]
    assert "category_availability" in result["used_tools"]


def test_assistant_is_read_only_and_has_no_mutation_tool(db, user):
    result = answer_question(db, user, "Pay my rent bill now")
    assert result["can_modify_data"] is False
    assert "move money or change your data" in result["disclaimer"]


def test_model_is_not_used_without_consent(db, user, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_api_key", "test-key")

    status = assistant_status(db, user)
    assert status["model_configured"] is True
    assert status["consent_required"] is True
    assert status["mode"] == "deterministic"

    result = answer_question(db, user, "How much can I spend?")
    assert result["mode"] == "deterministic"
    assert "not enabled" in result["note"]
