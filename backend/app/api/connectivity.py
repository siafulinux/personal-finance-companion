"""Institution linking, synchronisation and connection management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import SyncRun, User
from app.models.enums import SyncTrigger
from app.providers.base import ProviderError
from app.providers.registry import available_providers, get_adapter
from app.schemas.common import APIModel
from app.security.deps import get_current_user
from app.services.errors import DomainError, ValidationError
from app.services.sync import (
    connect_institution,
    disconnect_link,
    get_link,
    list_links,
    serialize_link,
    serialize_run,
    sync_link,
)

router = APIRouter(prefix="/connectivity", tags=["connectivity"])


class LinkTokenRequest(APIModel):
    provider: str = Field(min_length=1, max_length=40)


class ExchangeRequest(APIModel):
    provider: str = Field(min_length=1, max_length=40)
    # The user's approval from the provider's own flow. Never a bank password.
    public_token: str = Field(min_length=1, max_length=2000)
    consent: bool = True


@router.get("/providers")
def get_providers(user: User = Depends(get_current_user)) -> dict:
    return {"providers": available_providers()}


@router.post("/link-token")
def create_link_token(
    payload: LinkTokenRequest,
    user: User = Depends(get_current_user),
) -> dict:
    adapter = get_adapter(payload.provider)
    if not adapter.is_configured():
        raise ValidationError(
            f"{adapter.display_name} is not configured on this server. "
            "Use the sandbox institution to try the full flow."
        )
    return adapter.create_link_token(str(user.id))


@router.post("/exchange", status_code=201)
def exchange(
    payload: ExchangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not payload.consent:
        raise ValidationError(
            "Consent is required before data can be imported from a financial institution."
        )
    try:
        link, accounts, run = connect_institution(
            db, user, payload.provider, payload.public_token
        )
    except DomainError:
        raise
    except ProviderError as exc:
        raise ValidationError(exc.message) from exc
    return {
        "link": serialize_link(db, link),
        "accounts": [
            {
                "id": str(a.id),
                "name": a.name,
                "account_type": a.account_type,
                "external_account_id": a.external_account_id,
            }
            for a in accounts
        ],
        "sync": serialize_run(run),
    }


@router.get("/links")
def get_links(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return {"links": [serialize_link(db, link) for link in list_links(db, user.id)]}


@router.post("/links/{link_id}/sync")
def run_sync(
    link_id: uuid.UUID,
    full_refresh: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    link = get_link(db, user.id, link_id)
    run = sync_link(
        db, user, link, trigger=SyncTrigger.MANUAL, full_refresh=full_refresh
    )
    if run.status == "failed":
        # The run itself is persisted, so the client always sees what happened.
        return {
            "sync": serialize_run(run),
            "link": serialize_link(db, link),
            "error": run.error_message,
        }
    return {"sync": serialize_run(run), "link": serialize_link(db, link)}


@router.delete("/links/{link_id}")
def unlink(
    link_id: uuid.UUID,
    delete_data: bool = Query(
        default=False,
        description="Also delete the transactions and accounts this institution created.",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    link = get_link(db, user.id, link_id)
    result = disconnect_link(db, user, link, delete_data=delete_data)
    return result


@router.get("/sync-runs")
def get_sync_runs(
    link_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = select(SyncRun).where(SyncRun.user_id == user.id)
    if link_id is not None:
        query = query.where(SyncRun.link_id == link_id)
    runs = list(db.scalars(query.order_by(SyncRun.started_at.desc()).limit(limit)))
    return {"runs": [serialize_run(run) for run in runs]}
