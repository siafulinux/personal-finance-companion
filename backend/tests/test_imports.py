"""Scenario G plus CSV mapping, validation and idempotency."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.imports.parse import parse_amount, parse_date
from app.models import BillOccurrence, BillPaymentMatch, Transaction
from app.schemas.planning import BillCreate
from app.services.bills import create_bill

D = Decimal

def csv_content(today) -> str:
    """CSV rows dated relative to the run date.

    The bill-match window is bounded by the run date, so fixed calendar dates would
    silently drift out of range as the suite ages (the Comcast row must land within
    the window of a bill due tomorrow).
    """
    return (
        "Date,Description,Amount,Merchant\n"
        f"{today.isoformat()},Comcast internet,-95.00,Comcast\n"
        f"{(today - timedelta(days=1)).isoformat()},Grocery run,-45.50,Aldi\n"
        f"{(today - timedelta(days=2)).isoformat()},Paycheck,1200.00,Employer\n"
    )


def upload(client, account_id, content: bytes, filename="transactions.csv"):
    return client.post(
        "/api/v1/imports",
        files={"file": (filename, content, "text/csv")},
        data={"account_id": str(account_id)},
    )


def test_scenario_g_duplicate_import_creates_no_duplicates(auth_client, db, user, prefs, account, today):
    bill = create_bill(
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

    first = upload(auth_client, account.id, csv_content(today).encode())
    assert first.status_code == 201, first.text
    payload = first.json()
    assert payload["preview"]["summary"]["ready"] == 3
    import_id = payload["import"]["id"]
    mapping = payload["preview"]["mapping"]

    commit = auth_client.post(
        f"/api/v1/imports/{import_id}/commit", json={"mapping": mapping}
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["imported"] == 3
    assert result["auto_matched"] == 1
    assert result["suggested_matches"] == 0
    assert result["matched_bills"] == result["auto_matched"] + result["suggested_matches"]
    assert db.scalar(select(func.count(Transaction.id))) == 3

    occurrence = bill.occurrences[0]
    db.refresh(occurrence)
    assert occurrence.status == "paid"
    assert occurrence.paid_amount == D("95.00")
    assert db.scalar(select(func.count(BillPaymentMatch.id))) == 1

    # Committing the same import twice is a no-op.
    again = auth_client.post(
        f"/api/v1/imports/{import_id}/commit", json={"mapping": mapping}
    )
    assert again.status_code == 200
    assert again.json()["already_committed"] is True
    assert db.scalar(select(func.count(Transaction.id))) == 3

    # Uploading and importing the identical file again is fully deduplicated.
    second = upload(auth_client, account.id, csv_content(today).encode())
    assert second.status_code == 201
    second_payload = second.json()
    assert second_payload["preview"]["summary"]["duplicates"] == 3
    assert second_payload["preview"]["summary"]["ready"] == 0
    second_commit = auth_client.post(
        f"/api/v1/imports/{second_payload['import']['id']}/commit",
        json={"mapping": second_payload["preview"]["mapping"]},
    )
    assert second_commit.status_code == 200
    assert second_commit.json()["imported"] == 0
    assert second_commit.json()["duplicates"] == 3
    assert db.scalar(select(func.count(Transaction.id))) == 3
    assert db.scalar(select(func.count(BillPaymentMatch.id))) == 1
    db.refresh(occurrence)
    assert occurrence.paid_amount == D("95.00")


def test_invalid_rows_are_rejected_with_reasons(auth_client, db, user, account):
    content = (
        "Date,Description,Amount\n"
        "not-a-date,Broken row,-10.00\n"
        "2026-11-01,Zero amount,0.00\n"
        "2026-11-02,Valid purchase,-12.34\n"
    )
    response = upload(auth_client, account.id, content.encode())
    assert response.status_code == 201
    preview = response.json()["preview"]
    summary = preview["summary"]
    assert summary["rejected"] == 2
    assert summary["ready"] == 1
    statuses = [row["status"] for row in preview["rows"]]
    assert statuses.count("error") == 2
    commit = auth_client.post(
        f"/api/v1/imports/{response.json()['import']['id']}/commit",
        json={"mapping": preview["mapping"]},
    )
    assert commit.json()["imported"] == 1
    assert commit.json()["rejected"] == 2


def test_mapping_correction(auth_client, db, user, account):
    content = (
        "When,What,How Much,Who\n"
        "11/05/2026,Corner store,-$12.50,Bodega\n"
    )
    response = upload(auth_client, account.id, content.encode())
    assert response.status_code == 201, response.text
    import_id = response.json()["import"]["id"]
    mapping = response.json()["suggested_mapping"]
    mapping.update(
        {
            "date": "When",
            "description": "What",
            "amount": "How Much",
            "merchant": "Who",
        }
    )
    updated = auth_client.post(
        f"/api/v1/imports/{import_id}/preview", json={"mapping": mapping}
    )
    assert updated.status_code == 200, updated.text
    row = updated.json()["rows"][0]
    assert row["date"] == "2026-11-05"
    assert row["amount"] == "12.50"
    assert row["status"] == "ok"


def test_debit_credit_columns(auth_client, db, user, account):
    content = (
        "Date,Description,Debit,Credit\n"
        "2026-11-01,Rent payment,1200.00,\n"
        "2026-11-02,Refund from store,,25.00\n"
    )
    response = upload(auth_client, account.id, content.encode())
    preview = response.json()["preview"]
    mapping = preview["mapping"]
    assert mapping["debit"] == "Debit"
    assert mapping["credit"] == "Credit"
    rows = preview["rows"]
    assert rows[0]["suggested_type"] == "purchase"
    assert rows[0]["amount"] == "1200.00"
    assert rows[1]["suggested_type"] == "income"
    assert rows[1]["amount"] == "25.00"


def test_parse_amount_formats():
    assert parse_amount("$1,234.56") == D("1234.56")
    assert parse_amount("(45.00)") == D("-45.00")
    assert parse_amount("1.234,56") == D("1234.56")
    assert parse_amount("12,50") == D("12.50")
    assert parse_amount("-7.25") == D("-7.25")


def test_parse_date_formats():
    assert parse_date("2026-11-02").isoformat() == "2026-11-02"
    assert parse_date("11/02/2026").isoformat() == "2026-11-02"
    assert parse_date("02-Nov-2026").isoformat() == "2026-11-02"
    assert parse_date("2026/11/02").isoformat() == "2026-11-02"


def test_large_uploaded_file_is_rejected(auth_client, account):
    content = b"Date,Description,Amount\n" + b"2026-11-01,Test,-1.00\n" * 6000
    response = upload(auth_client, account.id, content)
    assert response.status_code == 422


def test_import_history(auth_client, account):
    response = upload(
        auth_client,
        account.id,
        b"Date,Description,Amount\n2026-11-01,Coffee,-4.50\n",
    )
    assert response.status_code == 201
    history = auth_client.get("/api/v1/imports")
    assert history.status_code == 200
    assert len(history.json()) == 1
