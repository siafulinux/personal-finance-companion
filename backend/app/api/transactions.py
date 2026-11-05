"""Transaction endpoints with filtering, duplicate detection and bill matching."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import User
from app.schemas.finance import (
    DuplicateCandidate,
    TransactionCreate,
    TransactionCreateResponse,
    TransactionListParams,
    TransactionOut,
    TransactionUpdate,
)
from app.security.deps import get_current_user
from app.services.transactions import (
    create_transaction,
    delete_transaction,
    get_transaction,
    list_transactions,
    possible_duplicates,
    serialize_transaction,
    update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
def get_transactions(
    search: str | None = Query(default=None, max_length=120),
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    merchant: str | None = Query(default=None, max_length=120),
    tx_type: Literal["income", "purchase", "bill_payment", "refund", "transfer", "adjustment"]
    | None = None,
    status: Literal["pending", "posted"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    min_amount: str | None = None,
    max_amount: str | None = None,
    sort: str = Query(default="-txn_date", max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    params = TransactionListParams(
        search=search,
        account_id=account_id,
        category_id=category_id,
        merchant=merchant,
        tx_type=tx_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items, total, totals = list_transactions(db, user.id, params)
    return {
        "items": [serialize_transaction(t) for t in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "totals": totals,
    }


@router.post("", response_model=TransactionCreateResponse, status_code=201)
def post_transaction(
    payload: TransactionCreate,
    check_duplicates: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionCreateResponse:
    duplicates = (
        possible_duplicates(db, user, payload) if check_duplicates else []
    )
    txn, match_info = create_transaction(db, user, payload)
    refreshed = get_transaction(db, user.id, txn.id)
    return TransactionCreateResponse(
        transaction=TransactionOut(**serialize_transaction(refreshed)),
        match_info=match_info,
        possible_duplicates=[DuplicateCandidate(**d) for d in duplicates],
    )


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_one_transaction(
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    return TransactionOut(**serialize_transaction(get_transaction(db, user.id, transaction_id)))


@router.patch("/{transaction_id}", response_model=TransactionOut)
def patch_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    updated = update_transaction(db, user, transaction_id, payload)
    return TransactionOut(**serialize_transaction(get_transaction(db, user.id, updated.id)))


@router.delete("/{transaction_id}", status_code=204)
def remove_transaction(
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    delete_transaction(db, user, transaction_id)
    return Response(status_code=204)
