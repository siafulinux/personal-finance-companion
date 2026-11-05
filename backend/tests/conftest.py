"""Pytest fixtures: an isolated PostgreSQL test database and API client."""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

TEST_DB = "finance_test"
DB_USER = os.environ.get("POSTGRES_USER", "finance")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "finance_dev_password")
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = os.environ.get("DB_PORT", "55432")

ADMIN_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/postgres"
TEST_URL = (
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{TEST_DB}"
)
os.environ["DATABASE_URL"] = TEST_URL
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use-only"
os.environ["ENVIRONMENT"] = "test"
os.environ["COOKIE_SECURE"] = "false"

BACKEND_ROOT = Path(__file__).resolve().parents[1]

from app.database.base import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    FinancialAccount,
    Transaction,
    User,
    UserPreference,
)
from app.models.enums import AccountType, TransactionStatus, TransactionType  # noqa: E402
from app.services.users import register_user  # noqa: E402
from app.utils.dates import today_in  # noqa: E402


def _ensure_database() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    _ensure_database()
    env = {**os.environ, "DATABASE_URL": TEST_URL}
    result = subprocess.run(
        [str(BACKEND_ROOT / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic failed:\n{result.stdout}\n{result.stderr}")
    yield


@pytest.fixture(scope="session")
def tables() -> list[str]:
    return [t.name for t in Base.metadata.sorted_tables]


@pytest.fixture(autouse=True)
def clean_database(migrated_database, tables):
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(f'"{name}"' for name in tables)
                + " RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user(db) -> User:
    account = register_user(
        db,
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123",
        display_name="Test User",
        timezone="America/New_York",
    )
    db.commit()
    return account


@pytest.fixture
def prefs(db, user) -> UserPreference:
    preferences = db.get(UserPreference, user.id)
    preferences.minimum_balance_buffer = Decimal("0.00")
    preferences.safe_to_spend_horizon_days = 30
    db.commit()
    return preferences


@pytest.fixture
def today(user) -> date:
    return today_in(user.timezone)


@pytest.fixture
def account(db, user) -> FinancialAccount:
    row = FinancialAccount(
        user_id=user.id,
        name="Everyday Checking",
        account_type=AccountType.CHECKING.value,
        opening_balance=Decimal("900.00"),
        opening_balance_date=date.today() - timedelta(days=60),
        include_in_safe_to_spend=True,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def auth_client(client, user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "TestPassword123",
        },
    )
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("pfc_csrf")
    client.headers.update({"X-CSRF-Token": csrf})
    return client


def make_transaction(
    db,
    user,
    account,
    *,
    amount: str,
    tx_type: str = "purchase",
    description: str = "Test transaction",
    merchant: str | None = None,
    txn_date: date | None = None,
    status: str = "posted",
    category_id=None,
    transfer_account_id=None,
) -> Transaction:
    txn = Transaction(
        user_id=user.id,
        account_id=account.id,
        transfer_account_id=transfer_account_id,
        description=description,
        merchant=merchant,
        amount=Decimal(amount),
        tx_type=tx_type,
        status=status,
        txn_date=txn_date or today_in(user.timezone),
        category_id=category_id,
    )
    db.add(txn)
    db.commit()
    return txn
