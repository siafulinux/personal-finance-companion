"""Scenarios H and I, refunds, corrections, authentication and isolation."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import (
    BillOccurrence,
    BillPaymentMatch,
    Category,
    FinancialAccount,
    Transaction,
)
from app.models.enums import AccountType
from app.schemas.finance import TransactionCreate, TransactionUpdate
from app.schemas.planning import BudgetAllocationInput, BudgetCreate
from app.services.accounts import account_payload, create_account, list_accounts
from app.services.balances import balances_for_accounts, period_totals, spending_by_category
from app.services.bill_matching import match_transaction
from app.services.bills import create_bill
from app.schemas.planning import BillCreate
from app.services.transactions import create_transaction, update_transaction
from app.services.users import register_user
from app.utils.dates import month_bounds

D = Decimal


def second_account(db, user, name="Savings", opening="500.00", account_type=AccountType.SAVINGS):
    row = FinancialAccount(
        user_id=user.id,
        name=name,
        account_type=account_type.value,
        opening_balance=D(opening),
        opening_balance_date=date.today() - timedelta(days=60),
        include_in_safe_to_spend=account_type != AccountType.CREDIT_CARD,
    )
    db.add(row)
    db.commit()
    return row


def test_scenario_h_internal_transfer_does_not_change_income_or_spending(db, user, account, today):
    savings = second_account(db, user)
    txn, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            transfer_account_id=savings.id,
            description="Move to savings",
            amount=D("200.00"),
            tx_type="transfer",
            txn_date=today,
        ),
    )
    db.commit()
    balances = balances_for_accounts(db, user.id)
    assert balances[account.id].posted_balance == D("700.00")
    assert balances[savings.id].posted_balance == D("700.00")

    start, end = month_bounds(today.year, today.month)
    totals = period_totals(db, user.id, start, end)
    assert totals["income"] == D("0.00")
    assert totals["spending"] == D("0.00")
    assert totals["transfers"] == D("200.00")
    assert spending_by_category(db, user.id, start, end) == {}
    assert txn.transfer_account_id == savings.id


def test_transfer_requires_two_accounts(db, user, account, today):
    with pytest.raises(Exception):
        create_transaction(
            db,
            user,
            TransactionCreate(
                account_id=account.id,
                transfer_account_id=account.id,
                description="Bad transfer",
                amount=D("10.00"),
                tx_type="transfer",
                txn_date=today,
            ),
        )


def test_scenario_i_credit_card_purchase_counted_once(db, user, account, today):
    card = second_account(
        db,
        user,
        name="Visa",
        opening="0.00",
        account_type=AccountType.CREDIT_CARD,
    )
    assert card.include_in_safe_to_spend is False

    purchase, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=card.id,
            description="Dinner",
            merchant="Restaurant",
            amount=D("80.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    start, end = month_bounds(today.year, today.month)
    assert period_totals(db, user.id, start, end)["spending"] == D("80.00")
    balances = balances_for_accounts(db, user.id)
    assert balances[card.id].posted_balance == D("-80.00")

    payment, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            transfer_account_id=card.id,
            description="Visa payment",
            amount=D("80.00"),
            tx_type="transfer",
            txn_date=today,
        ),
    )
    db.commit()
    balances = balances_for_accounts(db, user.id)
    assert balances[card.id].posted_balance == D("0.00")
    assert balances[account.id].posted_balance == D("820.00")
    totals = period_totals(db, user.id, start, end)
    assert totals["spending"] == D("80.00")  # payment is not a second expense
    assert totals["income"] == D("0.00")


def test_credit_card_never_contributes_to_safe_to_spend(db, user, account, today):
    card = second_account(db, user, name="Amex", opening="0.00", account_type=AccountType.CREDIT_CARD)
    create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=card.id,
            description="Purchase",
            amount=D("100.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    from app.services.safe_to_spend import compute

    result = compute(db, user)
    assert result.eligible_balance == D("900.00")
    assert all(row["name"] != "Amex" for row in result.accounts)


def test_refund_reduces_spending(db, user, account, today):
    from app.services.categories import seed_default_categories

    seed_default_categories(db, user.id)
    db.commit()
    from app.models import Category

    clothing = db.query(Category).filter_by(user_id=user.id, name="Clothing").one()
    create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Jacket",
            amount=D("50.00"),
            tx_type="purchase",
            txn_date=today,
            category_id=clothing.id,
        ),
    )
    create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Jacket refund",
            amount=D("20.00"),
            tx_type="refund",
            txn_date=today,
            category_id=clothing.id,
        ),
    )
    db.commit()
    start, end = month_bounds(today.year, today.month)
    assert period_totals(db, user.id, start, end)["spending"] == D("30.00")
    assert spending_by_category(db, user.id, start, end)[clothing.id] == D("30.00")


def test_transaction_correction_updates_balances_and_categories(db, user, account, today):
    from app.models import Category

    from app.services.categories import seed_default_categories

    seed_default_categories(db, user.id)
    db.commit()
    category = db.query(Category).filter_by(user_id=user.id, name="Groceries").one()
    txn, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Groceries",
            amount=D("50.00"),
            tx_type="purchase",
            txn_date=today,
            category_id=category.id,
        ),
    )
    db.commit()
    update_transaction(db, user, txn.id, TransactionUpdate(amount=D("30.00")))
    db.commit()
    balances = balances_for_accounts(db, user.id)
    assert balances[account.id].posted_balance == D("870.00")
    start, end = month_bounds(today.year, today.month)
    assert spending_by_category(db, user.id, start, end)[category.id] == D("30.00")


def test_correcting_a_matched_transaction_reverts_the_bill(db, user, prefs, account, today):
    bill = create_bill(
        db,
        user.id,
        BillCreate(
            name="Internet",
            merchant="Comcast",
            expected_amount=D("95.00"),
            anchor_date=today + timedelta(days=2),
            frequency="monthly",
            account_id=account.id,
        ),
        user.timezone,
    )
    db.commit()
    txn, info = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Comcast",
            merchant="Comcast",
            amount=D("95.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    assert info["outcome"] == "auto"
    # A bill can hold more than one occurrence and `Bill.occurrences` has no
    # order, so `occurrences[0]` is whichever row the database hands back first:
    # on one run that was the matched occurrence, on the next it was the one after
    # it, and the assertion below failed a commit whose code had not changed. Ask
    # for the occurrence the payment actually matched instead.
    match = db.get(BillPaymentMatch, uuid.UUID(info["match_id"]))
    assert match is not None
    occurrence = db.get(BillOccurrence, match.occurrence_id)
    assert occurrence is not None
    db.refresh(occurrence)
    assert occurrence.paid_amount == D("95.00")

    update_transaction(db, user, txn.id, TransactionUpdate(amount=D("120.00")))
    db.commit()
    db.refresh(occurrence)
    assert occurrence.paid_amount == D("0.00")
    assert occurrence.status == "upcoming"


def test_manual_duplicate_detection(db, user, account, today):
    from app.services.transactions import possible_duplicates

    first, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Coffee",
            merchant="Cafe",
            amount=D("5.50"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    duplicates = possible_duplicates(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Coffee",
            merchant="Cafe",
            amount=D("5.50"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    assert len(duplicates) == 1
    assert duplicates[0]["transaction_id"] == str(first.id)


def test_authentication_required(client):
    response = client.get("/api/v1/accounts")
    assert response.status_code == 401
    assert client.get("/api/v1/dashboard").status_code == 401
    assert client.get("/api/v1/safe-to-spend").status_code == 401


def test_csrf_required_for_cookie_auth(client, user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "TestPassword123"},
    )
    assert login.status_code == 200
    # Cookie present, no CSRF header -> rejected.
    response = client.post(
        "/api/v1/accounts",
        json={
            "name": "Hacked",
            "account_type": "checking",
            "opening_balance": "10.00",
            "opening_balance_date": "2026-01-01",
        },
    )
    assert response.status_code == 403


def test_bearer_token_does_not_require_csrf(client, user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "TestPassword123"},
    )
    token = login.json()["access_token"]
    response = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Bearer account",
            "account_type": "cash",
            "opening_balance": "25.00",
            "opening_balance_date": "2026-01-01",
        },
    )
    assert response.status_code == 201, response.text


def test_login_failure_is_generic(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


def test_user_cannot_access_another_users_account(client, db, user):
    other = register_user(
        db,
        email="other@example.com",
        password="OtherPassword123",
        display_name="Other",
        timezone="UTC",
    )
    db.commit()
    account = FinancialAccount(
        user_id=other.id,
        name="Other checking",
        account_type="checking",
        opening_balance=D("100.00"),
        opening_balance_date=date.today(),
    )
    db.add(account)
    db.commit()

    login = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "TestPassword123"}
    )
    assert login.status_code == 200
    response = client.get(f"/api/v1/accounts/{account.id}")
    assert response.status_code == 404


def test_register_weak_password_is_a_validation_error(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "abcdefgh1",
            "display_name": "Weak Password",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 422
    assert "at least" in response.json()["detail"].lower()


def test_financial_resources_are_isolated_between_users(client, db, user, account, today):
    from app.services.bills import create_bill
    from app.services.budgets import create_budget

    other = register_user(
        db,
        email="isolation-other@example.com",
        password="OtherPassword123",
        display_name="Other",
        timezone="UTC",
    )
    other_account = FinancialAccount(
        user_id=other.id,
        name="Other checking",
        account_type="checking",
        opening_balance=D("500.00"),
        opening_balance_date=today,
    )
    db.add(other_account)
    db.flush()
    other_category = db.query(Category).filter_by(user_id=other.id, name="Housing").one()
    other_txn, _ = create_transaction(
        db,
        other,
        TransactionCreate(
            account_id=other_account.id,
            description="Other rent",
            amount=D("100.00"),
            tx_type="purchase",
            txn_date=today,
            category_id=other_category.id,
        ),
    )
    other_bill = create_bill(
        db,
        other.id,
        BillCreate(
            name="Other bill",
            expected_amount=D("50.00"),
            anchor_date=today + timedelta(days=2),
            frequency="monthly",
            account_id=other_account.id,
            category_id=other_category.id,
        ),
        other.timezone,
    )
    other_budget = create_budget(
        db,
        other.id,
        BudgetCreate(
            year=today.year,
            month=today.month,
            allocations=[
                BudgetAllocationInput(category_id=other_category.id, amount=D("50.00"))
            ],
        ),
    )
    db.commit()

    token = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "TestPassword123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    checks = [
        ("get", f"/api/v1/accounts/{other_account.id}", None, 404),
        ("patch", f"/api/v1/accounts/{other_account.id}", {"name": "Stolen"}, 404),
        ("delete", f"/api/v1/accounts/{other_account.id}", None, 404),
        ("get", f"/api/v1/transactions/{other_txn.id}", None, 404),
        ("patch", f"/api/v1/transactions/{other_txn.id}", {"amount": "1.00"}, 404),
        ("delete", f"/api/v1/transactions/{other_txn.id}", None, 404),
        ("get", f"/api/v1/bills/{other_bill.id}", None, 404),
        ("patch", f"/api/v1/bills/{other_bill.id}", {"name": "Stolen bill"}, 404),
        ("delete", f"/api/v1/bills/{other_bill.id}", None, 404),
        ("get", f"/api/v1/categories/{other_category.id}", None, 404),
        ("patch", f"/api/v1/categories/{other_category.id}", {"name": "Stolen"}, 404),
        ("delete", f"/api/v1/categories/{other_category.id}", None, 404),
        ("get", f"/api/v1/budgets/{today.year}/{today.month}", None, 404),
        ("patch", f"/api/v1/budgets/{other_budget.id}", {"name": "Stolen"}, 404),
    ]
    for method, path, body, expected in checks:
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == expected, (method, path, response.status_code, response.text)

    # Foreign keys are never accepted from another user's account or category.
    response = client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "account_id": str(other_account.id),
            "description": "Injected transaction",
            "amount": "10.00",
            "tx_type": "purchase",
            "txn_date": today.isoformat(),
        },
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/bills",
        headers=headers,
        json={
            "name": "Injected bill",
            "expected_amount": "10.00",
            "anchor_date": today.isoformat(),
            "frequency": "monthly",
            "account_id": str(account.id),
            "category_id": str(other_category.id),
        },
    )
    assert response.status_code == 422


def test_production_configuration_rejects_development_secrets():
    from app.config import Settings

    with pytest.raises(RuntimeError):
        Settings(
            environment="production",
            secret_key="change-me-dev-only-secret-key-please-generate-your-own",
            cookie_secure=False,
            cors_origins="*",
        ).validate_runtime()


def test_archived_account_keeps_its_derived_balance(db, user, account, today):
    from app.services.accounts import archive_account, list_accounts

    create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Last purchase",
            amount=D("25.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    archive_account(db, user.id, account.id)
    db.commit()
    rows = list_accounts(db, user.id, include_archived=True)
    archived = next(row for row, _summary in rows if row.id == account.id)
    summary = next(summary for row, summary in rows if row.id == account.id)
    assert archived.is_archived is True
    assert summary.posted_balance == D("875.00")


def test_validation_error_shape(client, user):
    login = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "TestPassword123"}
    )
    token = login.json()["access_token"]
    response = client.post(
        "/api/v1/transactions",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": ""},
    )
    assert response.status_code == 422
    assert "errors" in response.json()


def test_account_balance_adjustment_audited(db, user, account, today):
    from app.services.accounts import adjust_balance, list_adjustments

    adjustment = adjust_balance(
        db,
        user.id,
        account.id,
        target_balance=D("950.00"),
        reason="Matched bank statement",
    )
    db.commit()
    balances = balances_for_accounts(db, user.id)
    assert balances[account.id].posted_balance == D("950.00")
    rows = list_adjustments(db, user.id, account.id)
    assert len(rows) == 1
    assert rows[0].previous_balance == D("900.00")
    assert rows[0].new_balance == D("950.00")


def test_future_posted_income_is_rejected(db, user, account, today):
    from app.services.errors import ValidationError

    with pytest.raises(ValidationError, match="cannot be dated in the future"):
        create_transaction(
            db,
            user,
            TransactionCreate(
                account_id=account.id,
                description="Paycheck that has not arrived",
                amount=D("2500.00"),
                tx_type="income",
                status="posted",
                txn_date=today + timedelta(days=1),
            ),
        )


def test_editing_a_posted_transaction_into_the_future_is_rejected(db, user, account, today):
    from app.services.errors import ValidationError

    txn, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Today's paycheck",
            amount=D("2500.00"),
            tx_type="income",
            status="posted",
            txn_date=today,
        ),
    )
    db.commit()
    with pytest.raises(ValidationError, match="cannot be dated in the future"):
        update_transaction(
            db,
            user,
            txn.id,
            TransactionUpdate(txn_date=today + timedelta(days=3)),
        )
