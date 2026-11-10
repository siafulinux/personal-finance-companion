"""Short-lived, server-signed nonces for provider linking.

Teller Connect includes a server-generated nonce in the enrolment it signs, which is what
makes a captured enrolment useless in another session. The nonce therefore has to be
issued by *this* server, tied to the user starting the flow, and expiring quickly.

It is signed with ``SECRET_KEY`` rather than stored, so no table, cleanup job or
cross-request state is needed: the nonce is self-describing and verifiable, and a restart
does not invalidate an approval that is still in progress.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from app.config import settings
from app.utils.dates import utc_now

#: Long enough for a bank login with MFA, short enough to be worthless if leaked.
NONCE_TTL_MINUTES = 30
_DOMAIN = b"pfc-link-nonce-v1"


class NonceError(RuntimeError):
    """The nonce is missing, malformed, expired or belongs to another session."""


def _sign(payload: str) -> str:
    digest = hmac.new(
        settings.secret_key.encode("utf-8"), _DOMAIN + payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_nonce(user_id: str, *, ttl_minutes: int = NONCE_TTL_MINUTES) -> str:
    """A signed nonce bound to one user and a deadline."""
    expires = int((utc_now() + timedelta(minutes=ttl_minutes)).timestamp())
    payload = f"{user_id}.{expires}.{secrets.token_urlsafe(12)}"
    return f"{payload}.{_sign(payload)}"


def verify_nonce(nonce: str, expected_user_id: str | None = None) -> None:
    """Raise :class:`NonceError` unless the nonce is ours, fresh and for this user."""
    parts = (nonce or "").split(".")
    if len(parts) != 4:
        raise NonceError("The linking nonce has an unexpected shape.")
    user_id, expires_raw, _, signature = parts
    payload = ".".join(parts[:3])
    if not hmac.compare_digest(signature, _sign(payload)):
        raise NonceError("The linking nonce did not come from this server.")
    try:
        expires = int(expires_raw)
    except ValueError as exc:
        raise NonceError("The linking nonce has an unreadable expiry.") from exc
    if utc_now().timestamp() > expires:
        raise NonceError("The linking nonce has expired. Start the connection again.")
    if expected_user_id and str(expected_user_id) != user_id:
        raise NonceError("The linking nonce belongs to another session.")


def nonce_user(nonce: str) -> str | None:
    parts = (nonce or "").split(".")
    return parts[0] if len(parts) == 4 else None


__all__ = ["NONCE_TTL_MINUTES", "NonceError", "issue_nonce", "nonce_user", "verify_nonce"]
