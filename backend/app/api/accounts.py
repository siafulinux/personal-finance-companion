"""Financial account endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import User
from app.schemas.finance import (
    AccountAdjustmentCreate,
    AccountAdjustmentOut,
    AccountCreate,
    AccountOut,
    AccountSummary,
    AccountUpdate,
)
from app.security.deps import get_current_user
from app.services.accounts import (
    account_payload,
    adjust_balance,
    archive_account,
    create_account,
    delete_account,
    get_account,
    list_accounts,
    list_adjustments,
    totals,
    update_account,
)
from app.services.balances import account_balance

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountSummary)
def get_accounts(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountSummary:
    rows = list_accounts(db, user.id, include_archived=include_archived)
    account_totals = totals(db, user.id)
    return AccountSummary(
        total_cash=account_totals["total_cash"],
        total_debt=account_totals["total_debt"],
        net_worth=account_totals["net_worth"],
        accounts=[AccountOut(**account_payload(a, s)) for a, s in rows],
    )


@router.post("", response_model=AccountOut, status_code=201)
def post_account(
    payload: AccountCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOut:
    account = create_account(db, user.id, payload)
    summary = account_balance(db, user.id, account.id)
    return AccountOut(**account_payload(account, summary))


@router.get("/{account_id}", response_model=AccountOut)
def get_one_account(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOut:
    account = get_account(db, user.id, account_id)
    return AccountOut(**account_payload(account, account_balance(db, user.id, account.id)))


@router.patch("/{account_id}", response_model=AccountOut)
def patch_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOut:
    account = update_account(db, user.id, account_id, payload)
    return AccountOut(**account_payload(account, account_balance(db, user.id, account.id)))


@router.post("/{account_id}/archive", response_model=AccountOut)
def archive(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOut:
    account = archive_account(db, user.id, account_id)
    return AccountOut(**account_payload(account, account_balance(db, user.id, account.id)))


@router.delete("/{account_id}", status_code=204)
def remove_account(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    delete_account(db, user.id, account_id)
    return Response(status_code=204)


@router.get("/{account_id}/adjustments", response_model=list[AccountAdjustmentOut])
def get_adjustments(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AccountAdjustmentOut]:
    return [AccountAdjustmentOut.model_validate(a) for a in list_adjustments(db, user.id, account_id)]


@router.post("/{account_id}/adjustments", response_model=AccountAdjustmentOut, status_code=201)
def post_adjustment(
    account_id: uuid.UUID,
    payload: AccountAdjustmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountAdjustmentOut:
    adjustment = adjust_balance(
        db,
        user.id,
        account_id,
        target_balance=payload.target_balance,
        reason=payload.reason,
    )
    return AccountAdjustmentOut.model_validate(adjustment)
