"""Phase 4 API surface: loans, savings, obligations, shopping locations, assistant."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.services.users import register_user
from app.utils.dates import today_in


def _new_loan_body(user, **overrides) -> dict:
    body = {
        "name": "Payday advance",
        "lender": "Cash App",
        "loan_type": "payday",
        "original_amount": "500.00",
        "opening_balance": "400.00",
        "scheduled_payment": "100.00",
        "payment_frequency": "biweekly",
        "next_payment_date": (today_in(user.timezone) + timedelta(days=4)).isoformat(),
    }
    body.update(overrides)
    return body


def test_loan_crud_and_payment_through_the_api(auth_client, user, account):
    created = auth_client.post("/api/v1/loans", json=_new_loan_body(user))
    assert created.status_code == 201, created.text
    loan = created.json()
    assert loan["current_balance"] == "400.00"
    assert loan["balance_is_estimate"] is False

    listed = auth_client.get("/api/v1/loans").json()
    assert listed["active_loans"] == 1
    assert listed["loans"][0]["name"] == "Payday advance"

    patched = auth_client.patch(
        f"/api/v1/loans/{loan['id']}", json={"scheduled_payment": "125.00"}
    )
    assert patched.status_code == 200
    assert patched.json()["scheduled_payment"] == "125.00"

    payment = auth_client.post(
        f"/api/v1/loans/{loan['id']}/payments", json={"amount": "100.00", "confirm": True}
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["status"] == "confirmed"

    detail = auth_client.get(f"/api/v1/loans/{loan['id']}").json()
    assert detail["current_balance"] == "300.00"
    assert detail["payment_count"] == 1

    assert auth_client.delete(f"/api/v1/loans/{loan['id']}").status_code == 204
    assert auth_client.get(f"/api/v1/loans/{loan['id']}").status_code == 404


def test_loan_validation_rejects_negative_amounts(auth_client, user):
    body = _new_loan_body(user, original_amount="-5.00")
    response = auth_client.post("/api/v1/loans", json=body)
    assert response.status_code == 422


def test_savings_goal_and_contribution(auth_client, user):
    created = auth_client.post(
        "/api/v1/savings",
        json={
            "name": "Emergency fund",
            "target_amount": "1000.00",
            "saved_amount": "100.00",
            "contribution_amount": "25.00",
            "contribution_frequency": "weekly",
        },
    )
    assert created.status_code == 201, created.text
    goal = created.json()
    assert goal["protected_amount"] == "100.00"
    assert goal["progress_percent"] == "10.00"

    contributed = auth_client.post(
        f"/api/v1/savings/{goal['id']}/contributions", json={"amount": "150.00"}
    )
    assert contributed.status_code == 201
    assert contributed.json()["saved_amount"] == "250.00"

    summary = auth_client.get("/api/v1/savings").json()
    assert summary["total_protected"] == "250.00"
    assert summary["active_goals"] == 1


def test_obligations_and_recommendations_are_served(auth_client, user, account):
    auth_client.post("/api/v1/loans", json=_new_loan_body(user))
    obligations = auth_client.get("/api/v1/obligations?days=30")
    assert obligations.status_code == 200
    payload = obligations.json()
    assert payload["totals"]["due_in_horizon"]
    assert "double_counting_guards" in payload
    assert any(item["kind"] == "loan" for item in payload["items"])

    recommendations = auth_client.get("/api/v1/recommendations")
    assert recommendations.status_code == 200
    assert "items" in recommendations.json()

    merchants = auth_client.get("/api/v1/insights/merchants")
    assert merchants.status_code == 200
    assert merchants.json()["merchants"] == []


def test_shopping_settings_and_locations_round_trip(auth_client, user, account):
    settings_row = auth_client.get("/api/v1/shopping/location-settings").json()
    assert settings_row["location_features_opted_in"] is False
    assert settings_row["supported"]["business_lookup"] in {"osm", "none"}

    enabled = auth_client.patch(
        "/api/v1/shopping/location-settings",
        json={"shopping_intelligence_enabled": True, "discovery_enabled": True},
    ).json()
    assert enabled["location_features_opted_in"] is True
    assert enabled["shopping_intelligence_enabled"] is True

    created = auth_client.post(
        "/api/v1/shopping/locations",
        json={"name": "Target", "latitude": "30.451500", "longitude": "-91.187100", "radius_m": 150},
    )
    assert created.status_code == 201, created.text
    assert created.json()["visit_count"] == 0

    detected = auth_client.post(
        "/api/v1/shopping/visits/detect",
        json={
            "latitude": "30.451500",
            "longitude": "-91.187100",
            "business_name": "Target",
        },
    )
    assert detected.status_code == 200
    body = detected.json()
    assert body["recorded"] is True
    assert body["visit"]["business_name"] == "Target"

    history = auth_client.get("/api/v1/shopping/visits").json()
    assert history["count"] == 1

    cleared = auth_client.delete("/api/v1/shopping/visits")
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 1


def test_assistant_uses_the_new_tools(auth_client, user, account):
    auth_client.post("/api/v1/loans", json=_new_loan_body(user))
    answer = auth_client.post(
        "/api/v1/assistant/ask",
        json={"question": "How much do I owe on my loans and what is due before payday?"},
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert "loans" in body["used_tools"]
    assert "obligations" in body["used_tools"]
    assert "loan" in body["answer"].lower() or "owe" in body["answer"].lower()


def test_other_users_cannot_reach_a_loan(auth_client, db, user, account):
    loan = auth_client.post("/api/v1/loans", json=_new_loan_body(user)).json()

    other = register_user(
        db,
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123",
        display_name="Other",
        timezone="UTC",
    )
    db.commit()

    with TestClient(app) as second:
        login = second.post(
            "/api/v1/auth/login",
            json={"email": other.email, "password": "TestPassword123"},
        )
        assert login.status_code == 200
        second.headers.update({"X-CSRF-Token": second.cookies.get("pfc_csrf")})

        assert second.get(f"/api/v1/loans/{loan['id']}").status_code == 404
        assert second.get("/api/v1/loans").json()["loans"] == []
        assert second.get("/api/v1/shopping/visits").json()["count"] == 0
        # The other user cannot repurpose the first user's loan id either.
        payment = second.post(
            f"/api/v1/loans/{loan['id']}/payments", json={"amount": "10.00", "confirm": True}
        )
        assert payment.status_code == 404
