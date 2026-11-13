"""A manually opened account dates from the user's calendar, not the server's.

The provider side of this skew is covered in ``test_connectivity``: ``complete_link``
counts its history window from the user's day. Manual accounts had no such path --
the API required the client to send a date, and a client that left it out got a
validation error rather than the user's today -- so this pins the other half.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.services.users import register_user
from app.utils.dates import today_in

PASSWORD = "TestPassword123"


def _open_account(client, owner, **fields):
    """Create an account over the API as ``owner``, with no date unless given."""
    login = client.post(
        "/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    body = {
        "name": f"Wallet {uuid.uuid4().hex[:6]}",
        "account_type": "cash",
        "opening_balance": "25.00",
        **fields,
    }
    return client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


def test_manual_account_opens_on_the_users_calendar(db, client):
    """Two users 25 hours apart cannot be given the same opening date.

    Kiritimati is UTC+14 and Midway UTC-11, so their local dates never agree. A
    date taken from the server's clock would be identical for both -- and for one
    of them it is tomorrow, where the opening balance is invisible to every
    "up to today" read. Each user's own date is the only answer that holds.
    """
    owners = {}
    for zone in ("Pacific/Kiritimati", "Pacific/Midway"):
        owners[zone] = register_user(
            db,
            email=f"open-{zone.split('/')[1].lower()}-{uuid.uuid4().hex[:6]}@example.com",
            password=PASSWORD,
            display_name="TZ Owner",
            timezone=zone,
        )
    db.commit()

    opened = {}
    for zone, owner in owners.items():
        response = _open_account(client, owner)
        assert response.status_code == 201, response.text
        opened[zone] = response.json()["opening_balance_date"]
        assert opened[zone] == today_in(zone).isoformat()

    assert opened["Pacific/Kiritimati"] != opened["Pacific/Midway"]
    assert opened["Pacific/Kiritimati"] > opened["Pacific/Midway"]


def test_manual_account_keeps_an_explicit_opening_date(db, client, user):
    """Back-dating is allowed: the fallback only fills in a date the client omitted."""
    response = _open_account(client, user, opening_balance_date="2026-01-01")

    assert response.status_code == 201, response.text
    assert date.fromisoformat(response.json()["opening_balance_date"]) == date(2026, 1, 1)
