"""JWT access tokens and CSRF tokens."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import settings
from app.utils.dates import utc_now

ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a token is missing, malformed or expired."""


def create_access_token(
    user_id: uuid.UUID, *, expires_minutes: int | None = None, token_version: int = 0
) -> str:
    ttl = expires_minutes or settings.access_token_ttl_minutes
    now = utc_now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "type": "access",
        "jti": secrets.token_urlsafe(8),
        # Bumped whenever every session must end (a password change). A token
        # carrying an older value is refused, even within the same second.
        "ver": token_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


@dataclass(frozen=True)
class TokenClaims:
    """Verified contents of an access token."""

    user_id: uuid.UUID
    jti: str
    expires_at: datetime
    version: int


def decode_token(token: str) -> TokenClaims:
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
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise TokenError("Token subject is invalid.") from exc
    jti = payload.get("jti")
    if not jti:
        raise TokenError("Token is missing an identifier.")
    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    # Tokens minted before the version claim existed carry no version; they belong
    # to the initial generation, which is the column's default.
    try:
        version = int(payload.get("ver", 0))
    except (TypeError, ValueError) as exc:
        raise TokenError("Token version is invalid.") from exc
    return TokenClaims(
        user_id=user_id, jti=str(jti), expires_at=expires_at, version=version
    )


def decode_access_token(token: str) -> uuid.UUID:
    return decode_token(token).user_id


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return secrets.compare_digest(a, b)
