"""FastAPI authentication dependencies (Bearer for apps, HttpOnly cookie for web)."""

from __future__ import annotations

import uuid

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database.base import get_db
from app.models import User
from app.security.tokens import TokenError, decode_token
from app.services.errors import AuthenticationError
from app.services.sessions import is_revoked
from app.services.users import get_user


def _token_from_request(request: Request) -> tuple[str | None, str]:
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip(), "bearer"
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        return cookie, "cookie"
    return None, "none"


def token_from_request(request: Request) -> str | None:
    """The raw access token from the Authorization header or session cookie."""
    return _token_from_request(request)[0]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token, source = _token_from_request(request)
    if not token:
        raise AuthenticationError("Authentication required.")
    try:
        claims = decode_token(token)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc
    if is_revoked(db, claims.jti):
        raise AuthenticationError("This session has been signed out. Please sign in again.")
    user_id: uuid.UUID = claims.user_id
    user = get_user(db, user_id)
    if user is None:
        raise AuthenticationError("This account is no longer available.")
    request.state.auth_source = source
    request.state.user_id = str(user.id)
    return user


CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
