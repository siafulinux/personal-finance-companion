"""Server discovery, first-run setup, installation settings and device pairing.

``/server/info`` is intentionally public and read-only: it is how a client that
knows only a URL learns what it is talking to. It carries no account data, no
secret and no database detail, so it is safe on an unauthenticated LAN.

The rest requires authentication; changing settings or minting pairing codes
additionally requires the administrator created by the wizard.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.response_helpers import set_session_cookies
from app.config import settings
from app.database.base import get_db
from app.models import User
from app.schemas.server import (
    PairingCreate,
    PairingRequest,
    ServerSettingsUpdate,
    SetupRequest,
)
from app.security.deps import get_current_user
from app.services.errors import RateLimitError
from app.services.server_setup import (
    PAIRING_TTL_MINUTES,
    complete_setup,
    consume_pairing_code,
    create_pairing_code,
    get_server_settings,
    is_admin,
    registration_allowed,
    server_info,
    setup_required,
    update_server_settings,
)
from app.version import API_VERSION, APP_VERSION

router = APIRouter(prefix="/server", tags=["server"])

# These two endpoints are reachable without a session, so they get their own
# small per-address budget. It is per process, exactly like the login guard.
_WINDOW_SECONDS = 60
_MAX_ATTEMPTS = 10
_attempts: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(key: str) -> None:
    now = time.time()
    bucket = _attempts[key]
    while bucket and now - bucket[0] > _WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _MAX_ATTEMPTS:
        raise RateLimitError("Too many attempts. Wait a minute and try again.")
    bucket.append(now)


def _client(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/info")
def get_info(request: Request, db: Session = Depends(get_db)) -> dict:
    """Public connection facts for this installation."""
    return server_info(db, request)


@router.post("/setup", status_code=201)
def run_setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    _rate_limit(f"setup:{_client(request)}")
    user = complete_setup(db, payload)
    # Sign the new administrator in, so the wizard ends inside the app rather
    # than bouncing them to a login form they have just filled in.
    token, csrf = set_session_cookies(response, user.id)
    return {
        "server": server_info(db, request),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
        },
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
        "csrf_token": csrf,
    }


@router.get("/settings")
def read_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = get_server_settings(db)
    return {
        "server": server_info(db, request),
        "settings": {
            "server_name": server_info(db, request)["server_name"],
            "registration_enabled": registration_allowed(db),
            "public_base_url": row.public_base_url if row else None,
            "setup_required": setup_required(db),
            "is_admin": is_admin(db, user),
        },
        "versions": {"app": APP_VERSION, "api": API_VERSION},
    }


@router.patch("/settings")
def write_settings(
    payload: ServerSettingsUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = update_server_settings(db, user, payload)
    return {
        "server": server_info(db, request),
        "settings": {
            "server_name": row.server_name,
            "registration_enabled": bool(row.registration_enabled),
            "public_base_url": row.public_base_url,
            "is_admin": True,
        },
    }


@router.post("/pairing", status_code=201)
def create_pairing(
    payload: PairingCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mint a short-lived, single-use code that carries this server's address.

    The code contains no credential: redeeming it only reveals the same public
    facts as ``/server/info``. Signing in still needs the user's own password.
    """
    raw, row = create_pairing_code(db, user, payload.label)
    info = server_info(db, request)
    return {
        "token": raw,
        "expires_at": row.expires_at,
        "ttl_minutes": PAIRING_TTL_MINUTES,
        "pairing_url": f"{info['web_url']}/pair?token={raw}",
        "connection": info,
    }


@router.post("/pair")
def redeem_pairing(
    payload: PairingRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    _rate_limit(f"pair:{_client(request)}")
    consume_pairing_code(db, payload.token)
    return {"paired": True, "connection": server_info(db, request)}
