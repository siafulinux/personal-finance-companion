"""Scenario J: Shopping Check uses real engine values, including bill warnings."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.models import Category, PlannedReserve
from app.schemas.planning import BudgetAllocationInput, BudgetCreate, BillCreate
from app.services.bills import create_bill
from app.services.budgets import create_budget
from app.services.shopping import shopping_check

D = Decimal


def setup_scenario_a(db, user, prefs, account, today):
    prefs.minimum_balance_buffer = D("200.00")
    prefs.safe_to_spend_horizon_days = 30
    db.commit()
    clothing = db.query(Category).filter_by(user_id=user.id, name="Clothing").one()
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[BudgetAllocationInput(category_id=clothing.id, amount=D("70.00"))],
        ),
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
    create_bill(
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

    from tests.conftest import make_transaction

    make_transaction(
        db,
        user,
        account,
        amount="40.00",
        description="Pending debit",
        status="pending",
        txn_date=today,
    )
    return clothing


def test_scenario_j_shopping_check_is_allowed_with_5_left(db, user, prefs, account, today):
    clothing = setup_scenario_a(db, user, prefs, account, today)
    result = shopping_check(
        db,
        user,
        store_name="Target",
        category_id=clothing.id,
        expected_amount=D("65.00"),
    )
    assert result["safe_to_spend"]["safe_to_spend"] == "310.00"
    assert result["category"]["remaining"] == "70.00"
    assert result["purchase"]["allowed"] is True
    assert result["purchase"]["category_remaining_after"] == "5.00"
    assert result["bills_covered"] is True
    assert "leaves $5.00" in result["message"]
    assert "bills are covered" in result["message"]
    assert result["store_name"] == "Target"


def test_shopping_check_blocks_over_budget_purchase(db, user, prefs, account, today):
    clothing = setup_scenario_a(db, user, prefs, account, today)
    result = shopping_check(
        db,
        user,
        store_name="Target",
        category_id=clothing.id,
        expected_amount=D("80.00"),
    )
    assert result["purchase"]["allowed"] is False
    assert result["purchase"]["category_over_budget"] is True
    assert any("not recommended" in w for w in result["warnings"])


def test_shopping_check_respects_cash_limit(db, user, prefs, account, today):
    prefs.minimum_balance_buffer = D("850.00")
    prefs.safe_to_spend_horizon_days = 10
    clothing = db.query(Category).filter_by(user_id=user.id, name="Clothing").one()
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[BudgetAllocationInput(category_id=clothing.id, amount=D("70.00"))],
        ),
    )
    db.commit()
    result = shopping_check(
        db, user, store_name="Target", category_id=clothing.id, expected_amount=D("60.00")
    )
    assert result["safe_to_spend"]["safe_to_spend"] == "50.00"
    assert result["category"]["max_safe_purchase"] == "50.00"
    assert result["purchase"]["allowed"] is False


def test_shopping_check_without_amount_lists_context(db, user, prefs, account, today):
    clothing = setup_scenario_a(db, user, prefs, account, today)
    result = shopping_check(db, user, store_name="Target", category_id=clothing.id)
    assert result["purchase"] is None
    assert "310.00" in result["message"]
    assert result["next_payday"] is None
    assert result["upcoming_bills"]


def test_shopping_api_uses_backend_engine(auth_client, db, user, prefs, account, today):
    clothing = setup_scenario_a(db, user, prefs, account, today)
    response = auth_client.post(
        "/api/v1/shopping/check",
        json={
            "store_name": "Target",
            "category_id": str(clothing.id),
            "expected_amount": "65.00",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["purchase"]["allowed"] is True
    assert body["safe_to_spend"]["safe_to_spend"] == "310.00"
    assert body["category"]["remaining"] == "70.00"

    context = auth_client.get("/api/v1/shopping/context")
    assert context.status_code == 200
    assert context.json()["safe_to_spend"] == "310.00"
