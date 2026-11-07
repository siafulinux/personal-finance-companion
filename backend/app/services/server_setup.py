"""Installation-level state: first-run setup, registration policy, pairing codes.

Everything here is about *this server*, not a user. The rules are deliberately
small and explicit because they decide who may create an account on a freshly
deployed instance:

1. A server with no users needs setup.
2. Until setup finishes, registration follows ``OPEN_REGISTRATION_UNTIL_SETUP``
   (true for local development, false for the Docker deployment, so a public
   install cannot be claimed by a stranger before its owner arrives).
3. After setup, registration follows the policy the owner chose in the wizard.
4. Only the account created by the wizard may change server settings.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PairingToken, ServerSettings, User
from app.models.server import SETTINGS_ID
from app.services.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.services.users import register_user
from app.utils.dates import utc_now
from app.version import API_VERSION, APP_VERSION, MIN_CLIENT_API_VERSION

#: A pairing code is meant to be read off a screen and typed within a minute or two.
PAIRING_TTL_MINUTES = 10


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ settings
def get_server_settings(db: Session) -> ServerSettings | None:
    return db.get(ServerSettings, SETTINGS_ID)


def _settings_row(db: Session) -> ServerSettings:
    row = get_server_settings(db)
    if row is None:
        row = ServerSettings(
            id=SETTINGS_ID,
            server_name=settings.app_name,
            registration_enabled=False,
        )
        db.add(row)
        db.flush()
    return row


def user_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User)) or 0)


def setup_required(db: Session) -> bool:
    """True only while the installation has no accounts at all."""
    return user_count(db) == 0


def registration_allowed(db: Session) -> bool:
    row = get_server_settings(db)
    if row is not None and row.setup_completed_at is not None:
        return bool(row.registration_enabled)
    return bool(settings.open_registration_until_setup)


def server_name(db: Session) -> str:
    row = get_server_settings(db)
    return (row.server_name if row else None) or settings.app_name


def is_admin(db: Session, user: User) -> bool:
    row = get_server_settings(db)
    return bool(row and row.admin_user_id and row.admin_user_id == user.id)


def complete_setup(db: Session, payload) -> User:
    """Create the administrator and close the wizard. Idempotency is by refusal."""
    if not setup_required(db):
        raise ConflictError(
            "This server has already been set up. Sign in with the administrator account."
        )
    user = register_user(
        db,
        email=str(payload.admin_email),
        password=payload.admin_password,
        display_name=payload.admin_name,
        timezone=settings.default_timezone,
    )
    row = _settings_row(db)
    row.server_name = payload.server_name
    row.registration_enabled = bool(payload.registration_enabled)
    row.admin_user_id = user.id
    row.setup_completed_at = utc_now()
    if payload.public_base_url:
        row.public_base_url = payload.public_base_url
    db.flush()
    return user


def update_server_settings(db: Session, user: User, payload) -> ServerSettings:
    if not is_admin(db, user):
        raise ForbiddenError("Only the server administrator can change these settings.")
    row = _settings_row(db)
    if payload.server_name is not None:
        row.server_name = payload.server_name
    if payload.registration_enabled is not None:
        row.registration_enabled = bool(payload.registration_enabled)
    # Sending an empty string clears an override and returns to request-derived URLs.
    if payload.public_base_url is not None:
        row.public_base_url = payload.public_base_url or None
    db.flush()
    return row


# ------------------------------------------------------------------- address
def public_base_url(db: Session, request) -> str:
    """The address clients should use for this server.

    An explicit owner-configured URL wins. Otherwise the request's own scheme and
    Host header are used, which is correct behind a TLS terminator only when the
    proxy forwards ``X-Forwarded-Proto`` (the bundled Caddy does, and uvicorn runs
    with ``--proxy-headers``). The internal Docker service name is never returned.
    """
    row = get_server_settings(db)
    if row and row.public_base_url:
        return row.public_base_url.rstrip("/")
    candidate = str(request.base_url).rstrip("/")
    # Guard against an internal hostname leaking out as a client address.
    host = urlsplit(candidate).hostname or ""
    if host in {"api", "web", "localhost", "127.0.0.1"} and settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    return candidate


def server_info(db: Session, request) -> dict:
    """The non-secret connection facts a client needs. Never includes credentials."""
    base = public_base_url(db, request)
    return {
        "app_name": settings.app_name,
        "server_name": server_name(db),
        "version": APP_VERSION,
        "api_version": API_VERSION,
        "min_client_api_version": MIN_CLIENT_API_VERSION,
        "api_base_url": f"{base}/api/v1",
        "web_url": base,
        "status": "ok",
        "registration_enabled": registration_allowed(db),
        "setup_required": setup_required(db),
    }


# ------------------------------------------------------------------- pairing
def _prune_pairings(db: Session, user_id) -> None:
    db.execute(
        delete(PairingToken).where(
            PairingToken.created_by == user_id,
            PairingToken.expires_at < utc_now() - timedelta(days=1),
        )
    )
    db.flush()


def create_pairing_code(db: Session, user: User, label: str | None) -> tuple[str, PairingToken]:
    """Issue a single-use code. The raw value is returned once and never stored."""
    if not is_admin(db, user):
        raise ForbiddenError("Only the server administrator can create pairing codes.")
    _prune_pairings(db, user.id)
    raw = secrets.token_urlsafe(24)
    row = PairingToken(
        token_hash=_digest(raw),
        label=(label or None),
        created_by=user.id,
        created_at=utc_now(),
        expires_at=utc_now() + timedelta(minutes=PAIRING_TTL_MINUTES),
    )
    db.add(row)
    db.flush()
    return raw, row


def consume_pairing_code(db: Session, token: str) -> None:
    """Burn a code. Expired, unknown and already-used codes are all rejected."""
    row = db.scalar(select(PairingToken).where(PairingToken.token_hash == _digest(token)))
    if row is None:
        raise NotFoundError("That pairing code is not valid on this server.")
    if row.used_at is not None:
        raise ConflictError("That pairing code has already been used. Generate a new one.")
    if row.expires_at <= utc_now():
        raise ValidationError("That pairing code has expired. Generate a new one.")
    row.used_at = utc_now()
    db.flush()
