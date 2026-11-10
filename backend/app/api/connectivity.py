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
from app.security.link_nonce import NonceError
from app.services import provider_selection
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


class InstitutionChoice(APIModel):
    """The institution the user picked, as the catalogue showed it."""

    institution_name: str = Field(min_length=1, max_length=200)
    institution_key: str | None = Field(default=None, max_length=40)


class ConnectFinishRequest(InstitutionChoice):
    """What the provider's flow handed back.

    ``public_token`` is the approval credential: a Plaid public token, or the access
    token Teller Connect minted in the client. The remaining fields are the Teller
    enrolment's identity and signature, which the server verifies before storing
    anything.
    """

    public_token: str = Field(min_length=1, max_length=4000)
    consent: bool = True
    nonce: str | None = Field(default=None, max_length=400)
    user_id: str | None = Field(default=None, max_length=120)
    enrollment_id: str | None = Field(default=None, max_length=160)
    signatures: list[str] | None = Field(default=None, max_length=10)


@router.get("/catalog")
def get_catalog(
    query: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=40, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Institutions this server can connect, with no provider detail exposed.

    Each entry is already resolved to the provider that will serve it; an institution no
    provider can serve is returned as unavailable with the reason, so the UI can say so
    instead of offering a connection that would fail mid-flow.
    """
    result = provider_selection.catalog(db, query, limit=limit)
    body = result.as_dict()
    # Tell the user plainly when nothing can be connected at all, rather than showing an
    # empty search box with no explanation. This asks about the server's providers, not
    # about this search: a bank the directory does not carry must not read as "the
    # administrator has not finished setup".
    body["configured"] = provider_selection.configured(db)
    return body


@router.post("/connect/start")
def start_connection(
    payload: InstitutionChoice,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Begin the chosen provider's authorisation flow for one institution."""
    try:
        return provider_selection.start_link(
            db,
            str(user.id),
            payload.institution_name,
            key=payload.institution_key,
        )
    except DomainError:
        raise
    except ProviderError as exc:
        raise ValidationError(exc.message) from exc


@router.post("/connect/finish", status_code=201)
def finish_connection(
    payload: ConnectFinishRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Complete the flow, store the connection and run the first sync."""
    if not payload.consent:
        raise ValidationError(
            "Consent is required before data can be imported from a financial institution."
        )
    extra = {
        "nonce": payload.nonce,
        "user_id": payload.user_id,
        "enrollment_id": payload.enrollment_id,
        "signatures": payload.signatures,
    }
    try:
        link, accounts, run = provider_selection.finish_link(
            db,
            user,
            payload.institution_name,
            key=payload.institution_key,
            public_token=payload.public_token,
            payload={k: v for k, v in extra.items() if v is not None},
        )
    except NonceError as exc:
        raise ValidationError(str(exc)) from exc
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
