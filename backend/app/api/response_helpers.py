"""Cookie handling and shared API helpers."""

from __future__ import annotations

from fastapi import Response

from app.config import settings
from app.security.tokens import create_access_token, new_csrf_token
from app.services.errors import NotFoundError
from app.utils.money import quantize


def set_session_cookies(response: Response, user_id, token_version: int = 0) -> tuple[str, str]:
    token = create_access_token(user_id, token_version=token_version)
    csrf = new_csrf_token()
    max_age = settings.access_token_ttl_minutes * 60
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return token, csrf


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def to_money(value) -> "Decimal":  # type: ignore[name-defined]
    return quantize(value)


def require_found(value, message: str):
    if value is None:
        raise NotFoundError(message)
    return value
