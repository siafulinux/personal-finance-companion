"""Loans and advances: CRUD, repayments and repayment matching."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import User
from app.models.enums import MatchStatus
from app.schemas.loans import (
    LoanCreate,
    LoanOut,
    LoanPaymentCreate,
    LoanPaymentOut,
    LoanPaymentSuggestions,
    LoanPaymentUpdate,
    LoanSummary,
    LoanUpdate,
)
from app.security.deps import get_current_user
from app.services import loans as loan_service
from app.services.loan_matching import link_transaction, suggestions_for_loan

router = APIRouter(prefix="/loans", tags=["loans"])


@router.get("", response_model=LoanSummary)
def get_loans(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> LoanSummary:
    return LoanSummary(**loan_service.summary(db, user.id))


@router.post("", response_model=LoanOut, status_code=201)
def post_loan(
    payload: LoanCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanOut:
    loan = loan_service.create_loan(db, user, payload)
    return LoanOut(**loan_service.loan_payload(loan))


@router.get("/{loan_id}", response_model=LoanOut)
def get_loan(
    loan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanOut:
    loan = loan_service.get_loan(db, user.id, loan_id)
    return LoanOut(**loan_service.loan_payload(loan))


@router.patch("/{loan_id}", response_model=LoanOut)
def patch_loan(
    loan_id: uuid.UUID,
    payload: LoanUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanOut:
    loan = loan_service.update_loan(db, user, loan_id, payload)
    return LoanOut(**loan_service.loan_payload(loan))


@router.delete("/{loan_id}", status_code=204)
def remove_loan(
    loan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    loan_service.delete_loan(db, user.id, loan_id)
    return Response(status_code=204)


@router.get("/{loan_id}/payments", response_model=list[LoanPaymentOut])
def get_payments(
    loan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LoanPaymentOut]:
    return [LoanPaymentOut(**row) for row in loan_service.list_payments(db, user.id, loan_id)]


@router.post("/{loan_id}/payments", response_model=LoanPaymentOut, status_code=201)
def post_payment(
    loan_id: uuid.UUID,
    payload: LoanPaymentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPaymentOut:
    payment = loan_service.add_payment(db, user, loan_id, payload)
    rows = loan_service.list_payments(db, user.id, loan_id)
    row = next(item for item in rows if item["id"] == payment.id)
    return LoanPaymentOut(**row)


@router.patch("/{loan_id}/payments/{payment_id}", response_model=LoanPaymentOut)
def patch_payment(
    loan_id: uuid.UUID,
    payment_id: uuid.UUID,
    payload: LoanPaymentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPaymentOut:
    payment = loan_service.update_payment(db, user, loan_id, payment_id, payload)
    rows = loan_service.list_payments(db, user.id, loan_id)
    row = next(item for item in rows if item["id"] == payment.id)
    return LoanPaymentOut(**row)


@router.post("/{loan_id}/payments/{payment_id}/confirm", response_model=LoanPaymentOut)
def confirm_payment(
    loan_id: uuid.UUID,
    payment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPaymentOut:
    payment = loan_service.set_payment_status(
        db, user, loan_id, payment_id, MatchStatus.CONFIRMED
    )
    rows = loan_service.list_payments(db, user.id, loan_id)
    row = next(item for item in rows if item["id"] == payment.id)
    return LoanPaymentOut(**row)


@router.post("/{loan_id}/payments/{payment_id}/reject", response_model=LoanPaymentOut)
def reject_payment(
    loan_id: uuid.UUID,
    payment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPaymentOut:
    payment = loan_service.set_payment_status(db, user, loan_id, payment_id, MatchStatus.REJECTED)
    rows = loan_service.list_payments(db, user.id, loan_id)
    row = next(item for item in rows if item["id"] == payment.id)
    return LoanPaymentOut(**row)


@router.delete("/{loan_id}/payments/{payment_id}", status_code=204)
def remove_payment(
    loan_id: uuid.UUID,
    payment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    loan_service.delete_payment(db, user, loan_id, payment_id)
    return Response(status_code=204)


@router.get("/{loan_id}/suggestions", response_model=LoanPaymentSuggestions)
def get_suggestions(
    loan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPaymentSuggestions:
    loan = loan_service.get_loan(db, user.id, loan_id)
    rows = suggestions_for_loan(db, user, loan_id)
    return LoanPaymentSuggestions(loan_id=loan_id, loan_name=loan.name, items=rows)


@router.post("/{loan_id}/suggestions/{transaction_id}", response_model=LoanPaymentOut)
def accept_suggestion(
    loan_id: uuid.UUID,
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPaymentOut:
    payment = link_transaction(db, user, loan_id, transaction_id, confirm=True)
    rows = loan_service.list_payments(db, user.id, loan_id)
    row = next(item for item in rows if item["id"] == payment.id)
    return LoanPaymentOut(**row)
