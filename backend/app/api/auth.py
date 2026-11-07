"""Authentication, onboarding, profile and account-lifecycle endpoints."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.response_helpers import clear_session_cookies, set_session_cookies
from app.config import settings
from app.database.base import get_db
from app.models import User
from app.schemas.auth import (
    ProfileUpdate,
    DataExportOut,
    DeleteAccountRequest,
    IncomeSourceCreate,
    IncomeSourceOut,
    IncomeSourceUpdate,
    LoginRequest,
    NotificationPreferenceOut,
    NotificationPreferencesUpdate,
    OnboardingRequest,
    PreferenceOut,
    PreferencesUpdate,
    ProfileOut,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.common import Message
from app.security.deps import get_current_user, token_from_request
from app.security.passwords import validate_password_strength
from app.services.errors import (
    AuthenticationError,
    DomainError,
    ForbiddenError,
    RateLimitError,
    ValidationError,
)
from app.services.server_setup import registration_allowed
from app.services.sessions import revoke_token
from app.services.users import (
    update_profile,
    add_income_source,
    authenticate,
    delete_income_source,
    delete_user_account,
    complete_onboarding,
    export_user_data,
    get_notification_preferences,
    get_preferences,
    list_income_sources,
    profile_payload,
    register_user,
    update_income_source,
    update_notification_preferences,
    update_preferences,
)

router = APIRouter(tags=["auth"])

# Simple per-process brute-force guard. Documented as best-effort in SECURITY.md.
_attempts: dict[str, deque[float]] = defaultdict(deque)
WINDOW_SECONDS = 60
MAX_ATTEMPTS = 8


def _rate_limit(key: str) -> None:
    now = time.time()
    bucket = _attempts[key]
    while bucket and now - bucket[0] > WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= MAX_ATTEMPTS:
        raise RateLimitError("Too many sign-in attempts. Try again in a minute.")
    bucket.append(now)


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(
    payload: RegisterRequest, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    # A self-hosted server decides who may create an account. The first-run
    # wizard is the only way in until its owner opens registration.
    if not registration_allowed(db):
        raise ForbiddenError(
            "Registration is closed on this server. Ask its administrator for an account."
        )
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    user = register_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        timezone=payload.timezone,
        currency=payload.currency,
    )
    token, csrf = set_session_cookies(response, user.id)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_ttl_minutes * 60,
        csrf_token=csrf,
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    client = request.client.host if request.client else "unknown"
    _rate_limit(f"{client}:{payload.email.lower()}")
    user = authenticate(db, payload.email, payload.password)
    token, csrf = set_session_cookies(response, user.id)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_ttl_minutes * 60,
        csrf_token=csrf,
    )


@router.post("/auth/logout", response_model=Message)
def logout(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> Message:
    # Clearing cookies is not enough for a stateless token: record the token's
    # jti so a copied token stops working immediately, from any client.
    token = token_from_request(request)
    if token:
        revoke_token(db, token)
    clear_session_cookies(response)
    return Message(message="Signed out.")


@router.get("/auth/me", response_model=ProfileOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProfileOut:
    return ProfileOut(**profile_payload(db, user))


@router.patch("/auth/profile", response_model=ProfileOut)
def patch_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    update_profile(db, user, display_name=payload.display_name, timezone=payload.timezone)
    return ProfileOut(**profile_payload(db, user))


@router.post("/auth/onboarding", response_model=ProfileOut)
def onboarding(
    payload: OnboardingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    complete_onboarding(db, user, payload)
    return ProfileOut(**profile_payload(db, user))


@router.patch("/auth/preferences", response_model=PreferenceOut)
def patch_preferences(
    payload: PreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PreferenceOut:
    prefs = update_preferences(db, user.id, payload)
    return PreferenceOut.model_validate(prefs)


@router.patch("/auth/notification-preferences", response_model=NotificationPreferenceOut)
def patch_notification_preferences(
    payload: NotificationPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferenceOut:
    prefs = update_notification_preferences(db, user.id, payload)
    return NotificationPreferenceOut.model_validate(prefs)


@router.get("/income-sources", response_model=list[IncomeSourceOut])
def get_income_sources(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[IncomeSourceOut]:
    return [IncomeSourceOut.model_validate(s) for s in list_income_sources(db, user.id)]


@router.post("/income-sources", response_model=IncomeSourceOut, status_code=201)
def post_income_source(
    payload: IncomeSourceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IncomeSourceOut:
    return IncomeSourceOut.model_validate(add_income_source(db, user.id, payload))


@router.patch("/income-sources/{source_id}", response_model=IncomeSourceOut)
def patch_income_source(
    source_id: uuid.UUID,
    payload: IncomeSourceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IncomeSourceOut:
    return IncomeSourceOut.model_validate(update_income_source(db, user.id, source_id, payload))


@router.delete("/income-sources/{source_id}", status_code=204)
def remove_income_source(
    source_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    delete_income_source(db, user.id, source_id)
    return Response(status_code=204)


@router.get("/account/export")
def export_data(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return export_user_data(db, user)


@router.post("/account/delete", response_model=Message)
def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Message:
    delete_user_account(db, user, payload.password, payload.confirm)
    clear_session_cookies(response)
    return Message(message="Your account and all associated financial data were deleted.")
