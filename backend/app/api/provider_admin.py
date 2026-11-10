"""Administrator-only provider configuration.

Every route here requires the account created by the first-run wizard. A normal user
never sees this surface, and — importantly — administering the server does not grant the
administrator access to anyone's connections: nothing in this module reads a
``provider_links`` row or a transaction.

Secrets only travel inward. A saved secret is never returned; the read endpoint reports
whether a field is present and a masked hint, which is enough for an owner to recognise
the value they pasted without exposing it to the browser, a log or a screenshot.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import PROVIDER_NAMES, User
from app.providers.base import ProviderError
from app.providers.registry import build_adapter
from app.schemas.common import APIModel
from app.security.deps import get_current_user
from app.services import provider_config, provider_selection
from app.services.errors import ForbiddenError, ValidationError
from app.services.server_setup import is_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/server/providers", tags=["provider administration"])


def require_admin(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    if not is_admin(db, user):
        raise ForbiddenError("Only the server administrator can configure providers.")
    return user


class ProviderUpdate(APIModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    environment: str | None = Field(default=None, max_length=20)
    #: Only the fields being changed need to be sent. An empty string clears a value.
    credentials: dict[str, str] | None = None


class SelectionUpdate(APIModel):
    auto_select: bool


@router.get("")
def read_providers(
    user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return provider_config.overview(db)


@router.patch("/selection")
def set_selection(
    payload: SelectionUpdate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    enabled = provider_config.set_auto_select(db, user, payload.auto_select)
    return {"auto_select": enabled}


@router.get("/coverage")
def coverage(
    names: str = Query(
        default="USAA,Cash App",
        max_length=400,
        description="Comma-separated institution names to check against every provider.",
    ),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requested = [part.strip() for part in names.split(",") if part.strip()][:10]
    return provider_selection.coverage(db, requested)


@router.patch("/{name}")
def update_provider(
    name: str,
    payload: ProviderUpdate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if name not in PROVIDER_NAMES:
        raise ValidationError(f"Unknown financial provider: {name}.")
    provider_config.update_provider(
        db,
        user,
        name,
        enabled=payload.enabled,
        priority=payload.priority,
        environment=payload.environment,
        credentials=payload.credentials,
    )
    # A credential or environment change can alter which provider serves what.
    provider_selection.clear_cache()
    return provider_config.describe(db, name)


@router.post("/{name}/test")
def test_provider(
    name: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Probe the provider with the currently saved configuration.

    A failure is reported, not raised: the administrator needs the reason (missing
    certificate, rejected secret, an outage) next to the form that fixes it.
    """
    if name not in PROVIDER_NAMES:
        raise ValidationError(f"Unknown financial provider: {name}.")
    state = provider_config.resolve(db, name)
    if not state.configured:
        missing = ", ".join(state.missing) or "credentials"
        message = f"{state.label} is not configured yet: {missing} missing."
        provider_config.record_test(
            db, name, ok=False, message=message, detail={"missing": list(state.missing)}
        )
        return {"ok": False, "message": message, "provider": provider_config.describe(db, name)}

    try:
        adapter = build_adapter(
            name, credentials=provider_config.credentials_for(db, name),
            environment=state.environment,
        )
        detail = adapter.check_connection()
    except ProviderError as exc:
        provider_config.record_test(db, name, ok=False, message=exc.message, detail={"code": exc.code})
        logger.info("provider test failed provider=%s code=%s", name, exc.code)
        return {
            "ok": False,
            "message": exc.message,
            "code": exc.code,
            "provider": provider_config.describe(db, name),
        }

    message = str(detail.get("message") or "Connection succeeded.")
    provider_config.record_test(db, name, ok=True, message=message, detail=detail)
    provider_selection.clear_cache()
    logger.info("provider test succeeded provider=%s", name)
    return {"ok": True, "message": message, "detail": detail, "provider": provider_config.describe(db, name)}


__all__ = ["router"]
