"""Budget allocations, spending totals, carryover, wizard and category limits."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.calculations.safe_to_spend import (
    CategoryAvailabilityInputs,
    calculate_category_availability,
    evaluate_purchase,
)
from app.models import Category, Transaction
from app.models.enums import TransactionType
from app.schemas.planning import (
    BudgetAllocationInput,
    BudgetCreate,
    BudgetWizardRequest,
    WizardPriority,
)
from app.services.budgets import (
    budget_summary,
    create_budget,
    create_budget_from_wizard,
    get_budget,
)
from app.services.safe_to_spend import category_availability, compute
from app.utils.dates import add_months, month_bounds

D = Decimal


def category(db, user, name: str) -> Category:
    row = db.query(Category).filter_by(user_id=user.id, name=name).one()
    return row


def test_budget_tracks_spending_and_remaining(db, user, account, today):
    clothing = category(db, user, "Clothing")
    groceries = category(db, user, "Groceries")
    start, _ = month_bounds(today.year, today.month)
    mid_month = date(today.year, today.month, min(15, today.day))
    budget = create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[
                BudgetAllocationInput(category_id=clothing.id, amount=D("100.00")),
                BudgetAllocationInput(category_id=groceries.id, amount=D("400.00")),
            ],
        ),
    )
    db.commit()
    for amount, category_id in (("65.00", clothing.id), ("120.00", groceries.id)):
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                description="Spend",
                amount=D(amount),
                tx_type=TransactionType.PURCHASE.value,
                status="posted",
                txn_date=mid_month,
                category_id=category_id,
            )
        )
    db.commit()

    summary = budget_summary(db, user.id, budget, today)
    rows = {row["category_name"]: row for row in summary["rows"]}
    assert rows["Clothing"]["spent"] == D("65.00")
    assert rows["Clothing"]["remaining"] == D("35.00")
    assert rows["Clothing"]["percent_used"] == D("65.00")
    assert summary["total_allocated"] == D("500.00")
    assert summary["total_spent"] == D("185.00")
    assert summary["total_remaining"] == D("315.00")


def test_refund_reduces_category_spending(db, user, account, today):
    clothing = category(db, user, "Clothing")
    start, _ = month_bounds(today.year, today.month)
    budget = create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[BudgetAllocationInput(category_id=clothing.id, amount=D("100.00"))],
        ),
    )
    db.commit()
    txn_date = date(today.year, today.month, min(5, today.day))
    db.add_all(
        [
            Transaction(
                user_id=user.id,
                account_id=account.id,
                description="Shirt",
                amount=D("80.00"),
                tx_type="purchase",
                status="posted",
                txn_date=txn_date,
                category_id=clothing.id,
            ),
            Transaction(
                user_id=user.id,
                account_id=account.id,
                description="Shirt refund",
                amount=D("30.00"),
                tx_type="refund",
                status="posted",
                txn_date=txn_date,
                category_id=clothing.id,
            ),
        ]
    )
    db.commit()
    summary = budget_summary(db, user.id, budget, today)
    rows = {row["category_name"]: row for row in summary["rows"]}
    assert rows["Clothing"]["spent"] == D("50.00")
    assert rows["Clothing"]["remaining"] == D("50.00")


def test_carryover_enabled_moves_leftover_forward(db, user, account, today):
    clothing = category(db, user, "Clothing")
    first, last = month_bounds(today.year, today.month)
    prev = add_months(first, -1)
    prev_budget = create_budget(
        db,
        user.id,
        BudgetCreate(
            year=prev.year,
            month=prev.month,
            allocations=[
                BudgetAllocationInput(
                    category_id=clothing.id, amount=D("100.00"), carryover_enabled=True
                )
            ],
        ),
    )
    db.commit()
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            description="Shoes",
            amount=D("60.00"),
            tx_type="purchase",
            status="posted",
            txn_date=date(prev.year, prev.month, 10),
            category_id=clothing.id,
        )
    )
    db.commit()
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[
                BudgetAllocationInput(
                    category_id=clothing.id, amount=D("100.00"), carryover_enabled=True
                )
            ],
        ),
    )
    db.commit()
    budget = get_budget(db, user.id, today.year, today.month)
    summary = budget_summary(db, user.id, budget, today)
    row = next(r for r in summary["rows"] if r["category_name"] == "Clothing")
    assert row["carryover_in"] == D("40.00")
    assert row["remaining"] == D("140.00")


def test_carryover_requires_previous_flag(db, user, today):
    clothing = category(db, user, "Clothing")
    first, _ = month_bounds(today.year, today.month)
    prev = add_months(first, -1)
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=prev.year,
            month=prev.month,
            allocations=[BudgetAllocationInput(category_id=clothing.id, amount=D("100.00"))],
        ),
    )
    db.commit()
    create_budget(
        db,
        user.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[
                BudgetAllocationInput(
                    category_id=clothing.id, amount=D("100.00"), carryover_enabled=True
                )
            ],
        ),
    )
    db.commit()
    budget = get_budget(db, user.id, today.year, today.month)
    summary = budget_summary(db, user.id, budget, today)
    row = next(r for r in summary["rows"] if r["category_name"] == "Clothing")
    assert row["carryover_in"] == D("0.00")


def test_wizard_respects_bills_savings_and_priorities(db, user, account, today):
    from app.schemas.planning import BillCreate
    from app.services.bills import create_bill

    housing = category(db, user, "Housing")
    clothing = category(db, user, "Clothing")
    savings = category(db, user, "Savings")
    start, _ = month_bounds(today.year, today.month)
    create_bill(
        db,
        user.id,
        BillCreate(
            name="Rent",
            merchant="Landlord",
            expected_amount=D("1000.00"),
            anchor_date=date(today.year, today.month, min(20, 20)),
            frequency="monthly",
            category_id=housing.id,
        ),
        user.timezone,
    )
    db.commit()

    budget = create_budget_from_wizard(
        db,
        user.id,
        BudgetWizardRequest(
            year=today.year,
            month=today.month,
            expected_income=D("3000.00"),
            savings_target_percent=D("10"),
            priorities=[WizardPriority(category_id=clothing.id, weight=1)],
        ),
    )
    db.commit()
    summary = budget_summary(db, user.id, budget, today)
    rows = {r["category_name"]: r for r in summary["rows"]}
    assert rows["Housing"]["allocated"] == D("1000.00")
    assert rows["Savings"]["allocated"] == D("300.00")
    assert rows["Clothing"]["allocated"] == D("1700.00")
    assert summary["total_allocated"] == D("3000.00")
    assert summary["unallocated"] == D("0.00")


def test_scenario_b_category_allows_purchase_within_budget(today):
    availability = calculate_category_availability(
        CategoryAvailabilityInputs(
            category_id=__import__("uuid").uuid4(),
            category_name="Clothing",
            budgeted=D("70.00"),
            spent=D("0.00"),
        ),
        overall_safe_to_spend=D("310.00"),
    )
    assert availability.max_safe_purchase == D("70.00")
    purchase = evaluate_purchase(
        amount=D("65.00"), category_available=availability, safe_to_spend=D("310.00")
    )
    assert purchase["allowed"] is True
    assert purchase["category_remaining_after"] == "5.00"
    assert "leaves $5.00" in purchase["message"]


def test_scenario_b_over_budget_warns(today):
    availability = calculate_category_availability(
        CategoryAvailabilityInputs(
            category_id=__import__("uuid").uuid4(),
            category_name="Clothing",
            budgeted=D("70.00"),
            spent=D("0.00"),
        ),
        overall_safe_to_spend=D("310.00"),
    )
    purchase = evaluate_purchase(
        amount=D("80.00"), category_available=availability, safe_to_spend=D("310.00")
    )
    assert purchase["allowed"] is False
    assert purchase["category_over_budget"] is True
    assert purchase["category_remaining_after"] == "-10.00"


def test_scenario_c_cash_constraint_wins(today):
    availability = calculate_category_availability(
        CategoryAvailabilityInputs(
            category_id=__import__("uuid").uuid4(),
            category_name="Clothing",
            budgeted=D("70.00"),
            spent=D("0.00"),
        ),
        overall_safe_to_spend=D("50.00"),
    )
    assert availability.max_safe_purchase == D("50.00")
    assert availability.limited_by == "cash"
    purchase = evaluate_purchase(
        amount=D("70.00"), category_available=availability, safe_to_spend=D("50.00")
    )
    assert purchase["allowed"] is False
    assert purchase["cash_shortfall"] == "20.00"


def test_budget_api_serializes_month_summary(auth_client, user, today):
    created = auth_client.post(
        "/api/v1/budgets",
        json={"year": today.year, "month": today.month, "allocations": []},
    )
    assert created.status_code == 201, created.text

    response = auth_client.get(f"/api/v1/budgets/{today.year}/{today.month}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["year"] == today.year
    assert payload["month"] == today.month
    assert payload["start_date"].endswith("-01")
    assert payload["rows"] == []


def test_category_availability_service_uses_real_budget(db, user, account, today):
    clothing = category(db, user, "Clothing")
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
        Transaction(
            user_id=user.id,
            account_id=account.id,
            description="Scarf",
            amount=D("20.00"),
            tx_type="purchase",
            status="posted",
            txn_date=date(today.year, today.month, min(3, today.day)),
            category_id=clothing.id,
        )
    )
    db.commit()
    availability = category_availability(db, user, clothing.id)
    assert availability.budgeted == D("70.00")
    assert availability.spent == D("20.00")
    assert availability.remaining == D("50.00")
    assert availability.max_safe_purchase == D("50.00")
    assert compute(db, user).safe_to_spend == D("880.00")
