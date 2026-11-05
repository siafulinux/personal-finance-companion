"""Session lifecycle: sign-out revokes the token, other sessions survive."""

from __future__ import annotations

from app.security.tokens import create_access_token


def _login(client, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "TestPassword123"}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_logout_revokes_the_presented_token(client, user):
    token = _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200, logout.text

    rejected = client.get("/api/v1/auth/me", headers=headers)
    assert rejected.status_code == 401
    assert "signed out" in rejected.json()["detail"].lower()


def test_logout_does_not_revoke_another_device(client, user):
    first = _login(client, user.email)
    second = _login(client, user.email)

    client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {first}"})

    assert client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {first}"}
    ).status_code == 401
    assert client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {second}"}
    ).status_code == 200


def test_logout_without_a_token_is_harmless(client):
    assert client.post("/api/v1/auth/logout").status_code == 200


def test_revoking_twice_is_idempotent(client, user):
    token = _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200


def test_repeated_failed_logins_are_throttled_with_429(client, user):
    """Throttling must be distinguishable from a wrong password (401)."""
    statuses = [
        client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "DefinitelyWrong123"},
        ).status_code
        for _ in range(9)
    ]
    assert statuses[:8] == [401] * 8
    assert statuses[8] == 429


def test_token_for_unknown_user_is_rejected(client):
    import uuid

    token = create_access_token(uuid.uuid4())
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
