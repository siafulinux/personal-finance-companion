"""Changing a password: the current one is required, and other sessions end."""

from __future__ import annotations

from app.services.users import register_user

OLD = "TestPassword123"
NEW = "BrandNewPassword456"


def _login(client, email: str, password: str = OLD) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _change(client, token: str, current: str, new: str):
    return client.post(
        "/api/v1/auth/password",
        json={"current_password": current, "new_password": new},
        headers={"Authorization": f"Bearer {token}"},
    )


def _me(client, token: str):
    return client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_changing_the_password_requires_the_current_one(client, user):
    token = _login(client, user.email)

    response = _change(client, token, current="NotMyPassword1", new=NEW)

    assert response.status_code == 401, response.text
    assert "current password" in response.json()["detail"].lower()
    # A rejected attempt must leave the account exactly as it was.
    _login(client, user.email, OLD)


def test_the_new_password_replaces_the_old_one(client, user):
    token = _login(client, user.email)

    assert _change(client, token, OLD, NEW).status_code == 200

    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": OLD}
        ).status_code
        == 401
    )
    _login(client, user.email, NEW)


def test_the_device_that_changed_the_password_stays_signed_in(client, user):
    """A security action must not throw the user out of the app they are in."""
    token = _login(client, user.email)

    response = _change(client, token, OLD, NEW)

    assert response.status_code == 200, response.text
    replacement = response.json()["access_token"]
    assert _me(client, replacement).status_code == 200


def test_other_sessions_stop_working(client, user):
    """Both tokens are minted in the same second; a version bump separates them."""
    first = _login(client, user.email)
    second = _login(client, user.email)

    response = _change(client, first, OLD, NEW)
    assert response.status_code == 200, response.text

    # The device that made the change had its own token revoked outright.
    assert _me(client, first).status_code == 401

    # The other device was not touched directly; it is refused because it belongs
    # to the previous generation of the account.
    rejected = _me(client, second)
    assert rejected.status_code == 401, rejected.text
    assert "password changed" in rejected.json()["detail"].lower()

    assert _me(client, response.json()["access_token"]).status_code == 200


def test_a_weak_password_is_rejected_and_nothing_changes(client, user):
    token = _login(client, user.email)

    # Long enough for the schema, but no digit: the policy, not the field length,
    # is what must reject it.
    response = _change(client, token, current=OLD, new="onlyletters")

    assert response.status_code == 422, response.text
    assert "number" in response.json()["detail"].lower()
    # Still the old password, still the old session.
    assert _me(client, token).status_code == 200
    _login(client, user.email, OLD)


def test_reusing_the_current_password_is_rejected(client, user):
    token = _login(client, user.email)

    response = _change(client, token, current=OLD, new=OLD)

    assert response.status_code == 422, response.text
    assert "different" in response.json()["detail"].lower()
    _login(client, user.email, OLD)


def test_changing_a_password_requires_authentication(client):
    response = client.post(
        "/api/v1/auth/password", json={"current_password": OLD, "new_password": NEW}
    )
    assert response.status_code == 401


def test_another_account_is_unaffected(client, user, db):
    # Created directly, so the result does not depend on whether this server has
    # registration open.
    other = register_user(
        db,
        email=f"other-{user.id.hex[:8]}@example.com",
        password=OLD,
        display_name="Other User",
        timezone="America/New_York",
    )
    db.commit()
    other_token = _login(client, other.email)

    token = _login(client, user.email)
    assert _change(client, token, OLD, NEW).status_code == 200

    # The other account's session is untouched by someone else's password change.
    assert _me(client, other_token).status_code == 200
