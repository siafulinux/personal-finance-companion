"""JWT access tokens and CSRF tokens."""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any

import jwt

from app.config import settings
from app.utils.dates import utc_now

ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a token is missing, malformed or expired."""


def create_access_token(user_id: uuid.UUID, *, expires_minutes: int | None = None) -> str:
    ttl = expires_minutes or settings.access_token_ttl_minutes
    now = utc_now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "type": "access",
        "jti": secrets.token_urlsafe(8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Session expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid session token.") from exc
    if payload.get("type") != "access":
        raise TokenError("Invalid token type.")
    subject = payload.get("sub")
    if not subject:
        raise TokenError("Token is missing a subject.")
    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise TokenError("Token subject is invalid.") from exc


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return secrets.compare_digest(a, b)
