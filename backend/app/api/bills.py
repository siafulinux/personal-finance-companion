"""Bill, occurrence and payment-matching endpoints."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.base import get_db
from app.models import Bill, BillOccurrence, User
from app.models.enums import OccurrenceStatus
from app.schemas.common import APIModel, Message, Money
from app.schemas.planning import (
    MerchantAliasCreate,
    MerchantAliasOut,
    BillCalendarOut,
    BillCreate,
    BillOut,
    BillUpdate,
    BillWithSummary,
    MarkPaidRequest,
    MatchOut,
    OccurrenceOut,
    RecordPaymentRequest,
)
from app.security.deps import get_current_user
from app.services import bills as bill_service
from app.services.aliases import create_alias, delete_alias, list_aliases
from app.services.bill_matching import (
    confirm_match,
    link_transaction,
    reject_match,
    suggestions,
)
from app.services.errors import ValidationError
from app.utils.dates import today_in
from app.utils.money import quantize

router = APIRouter(tags=["bills"])


class ConfirmMatchRequest(APIModel):
    amount: Money | None = None


class LinkMatchRequest(APIModel):
    occurrence_id: uuid.UUID
    transaction_id: uuid.UUID
    confirm: bool = True


@router.get("/merchant-aliases", response_model=list[MerchantAliasOut])
def get_aliases(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[MerchantAliasOut]:
    return [MerchantAliasOut.model_validate(a) for a in list_aliases(db, user.id)]


@router.post("/merchant-aliases", response_model=MerchantAliasOut, status_code=201)
def post_alias(
    payload: MerchantAliasCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MerchantAliasOut:
    return MerchantAliasOut.model_validate(create_alias(db, user.id, payload))


@router.delete("/merchant-aliases/{alias_id}", status_code=204)
def remove_alias(
    alias_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    delete_alias(db, user.id, alias_id)
    return Response(status_code=204)


@router.get("/bills/calendar", response_model=BillCalendarOut)
def get_calendar(
    year: int = Query(ge=2000, le=2200),
    month: int = Query(ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillCalendarOut:
    today = today_in(user.timezone)
    bill_service.materialize_all(db, user.id, user.timezone)
    start, end, occurrences = bill_service.month_calendar(db, user.id, year, month, today)
    total_expected = sum(
        (Decimal(o["expected_amount"]) for o in occurrences), Decimal("0.00")
    )
    total_remaining = sum(
        (
            Decimal(o["remaining_amount"])
            for o in occurrences
            if o["status"] not in (OccurrenceStatus.PAID.value, OccurrenceStatus.SKIPPED.value)
        ),
        Decimal("0.00"),
    )
    return BillCalendarOut(
        year=year,
        month=month,
        start_date=start,
        end_date=end,
        occurrences=[OccurrenceOut(**o) for o in occurrences],
        totals={
            "expected": str(quantize(total_expected)),
            "remaining": str(quantize(total_remaining)),
            "count": str(len(occurrences)),
        },
    )


@router.get("/bill-occurrences", response_model=list[OccurrenceOut])
def get_occurrences(
    status: str | None = Query(default=None, pattern="^(upcoming|partial|paid|skipped)$"),
    start_date: date | None = None,
    end_date: date | None = None,
    overdue_only: bool = False,
    limit: int = Query(default=100, ge=1, le=400),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OccurrenceOut]:
    today = today_in(user.timezone)
    bill_service.materialize_all(db, user.id, user.timezone)
    rows = bill_service.list_occurrences(
        db,
        user.id,
        today,
        status=status,
        start=start_date,
        end=end_date,
        overdue_only=overdue_only,
        limit=limit,
    )
    return [OccurrenceOut(**bill_service.occurrence_dict(o, today)) for o in rows]


@router.get("/match-suggestions")
def get_suggestions(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return {"items": suggestions(db, user)}


@router.post("/matches/{match_id}/confirm", response_model=MatchOut)
def confirm(
    match_id: uuid.UUID,
    payload: ConfirmMatchRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatchOut:
    match = confirm_match(db, user, match_id, amount=payload.amount if payload else None)
    return MatchOut.model_validate(match)


@router.post("/matches/{match_id}/reject", response_model=MatchOut)
def reject(
    match_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatchOut:
    return MatchOut.model_validate(reject_match(db, user, match_id))


@router.post("/matches/link", response_model=MatchOut)
def link(
    payload: LinkMatchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatchOut:
    match = link_transaction(
        db,
        user,
        payload.occurrence_id,
        payload.transaction_id,
        confirm=payload.confirm,
    )
    return MatchOut.model_validate(match)


@router.post("/bill-occurrences/{occurrence_id}/mark-paid", response_model=OccurrenceOut)
def mark_paid(
    occurrence_id: uuid.UUID,
    payload: MarkPaidRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = bill_service.mark_paid(
        db, user.id, occurrence_id, notes=payload.notes if payload else None
    )
    return OccurrenceOut(**bill_service.occurrence_dict(occurrence, today_in(user.timezone)))


@router.post("/bill-occurrences/{occurrence_id}/unpaid", response_model=OccurrenceOut)
def mark_unpaid(
    occurrence_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = bill_service.mark_unpaid(db, user.id, occurrence_id)
    return OccurrenceOut(**bill_service.occurrence_dict(occurrence, today_in(user.timezone)))


@router.post("/bill-occurrences/{occurrence_id}/skip", response_model=OccurrenceOut)
def skip(
    occurrence_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = bill_service.skip_occurrence(db, user.id, occurrence_id)
    return OccurrenceOut(**bill_service.occurrence_dict(occurrence, today_in(user.timezone)))


@router.post("/bill-occurrences/{occurrence_id}/record-payment", response_model=OccurrenceOut)
def record_payment(
    occurrence_id: uuid.UUID,
    payload: RecordPaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence, _txn = bill_service.record_payment(
        db,
        user.id,
        occurrence_id,
        amount=payload.amount,
        account_id=payload.account_id,
        paid_on=payload.paid_on,
        notes=payload.notes,
        timezone=user.timezone,
    )
    return OccurrenceOut(**bill_service.occurrence_dict(occurrence, today_in(user.timezone)))


@router.get("/bills")
def get_bills(
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    today = today_in(user.timezone)
    bill_service.materialize_all(db, user.id, user.timezone)
    query = (
        select(Bill)
        .options(selectinload(Bill.occurrences))
        .where(Bill.user_id == user.id)
        .order_by(Bill.name)
    )
    if not include_inactive:
        query = query.where(Bill.is_active.is_(True))
    rows = list(db.scalars(query))
    items = []
    for bill in rows:
        payload = BillOut.model_validate(bill).model_dump()
        payload.update(
            {k: v for k, v in bill_service.bill_summary(bill, today).items()}
        )
        payload["next_due_date"] = (
            date.fromisoformat(payload["next_due_date"]) if payload["next_due_date"] else None
        )
        items.append(BillWithSummary(**payload))
    return {"items": items}


@router.post("/bills", response_model=BillOut, status_code=201)
def post_bill(
    payload: BillCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillOut:
    return BillOut.model_validate(bill_service.create_bill(db, user.id, payload, user.timezone))


@router.get("/bills/{bill_id}", response_model=BillOut)
def get_bill(
    bill_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillOut:
    return BillOut.model_validate(bill_service.get_bill(db, user.id, bill_id))


@router.patch("/bills/{bill_id}", response_model=BillOut)
def patch_bill(
    bill_id: uuid.UUID,
    payload: BillUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillOut:
    return BillOut.model_validate(
        bill_service.update_bill(db, user.id, bill_id, payload, user.timezone)
    )


@router.delete("/bills/{bill_id}", status_code=204)
def remove_bill(
    bill_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    bill_service.delete_bill(db, user.id, bill_id)
    return Response(status_code=204)
