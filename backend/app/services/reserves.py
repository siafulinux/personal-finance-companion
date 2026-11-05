"""Explicit money reservations (savings contributions, planned expenses)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FinancialAccount, PlannedReserve
from app.schemas.planning import ReserveCreate, ReserveUpdate
from app.services.errors import NotFoundError, ValidationError
from app.utils.money import quantize


def list_reserves(db: Session, user_id: uuid.UUID, *, active_only: bool = False) -> list[PlannedReserve]:
    query = select(PlannedReserve).where(PlannedReserve.user_id == user_id)
    if active_only:
        query = query.where(PlannedReserve.is_active.is_(True))
    return list(db.scalars(query.order_by(PlannedReserve.created_at.desc())))


def get_reserve(db: Session, user_id: uuid.UUID, reserve_id: uuid.UUID) -> PlannedReserve:
    reserve = db.scalar(
        select(PlannedReserve).where(
            PlannedReserve.id == reserve_id, PlannedReserve.user_id == user_id
        )
    )
    if reserve is None:
        raise NotFoundError("Reserve not found.")
    return reserve


def create_reserve(
    db: Session, user_id: uuid.UUID, payload: ReserveCreate
) -> PlannedReserve:
    if payload.account_id:
        account = db.scalar(
            select(FinancialAccount).where(
                FinancialAccount.id == payload.account_id,
                FinancialAccount.user_id == user_id,
            )
        )
        if account is None:
            raise ValidationError("The selected account does not exist.")
    reserve = PlannedReserve(
        user_id=user_id,
        name=payload.name.strip(),
        amount=quantize(payload.amount),
        is_savings=payload.is_savings,
        category_id=payload.category_id,
        account_id=payload.account_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        notes=payload.notes,
    )
    db.add(reserve)
    db.flush()
    return reserve


def update_reserve(
    db: Session, user_id: uuid.UUID, reserve_id: uuid.UUID, payload: ReserveUpdate
) -> PlannedReserve:
    reserve = get_reserve(db, user_id, reserve_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "amount" and value is not None:
            value = quantize(value)
        setattr(reserve, field, value)
    if reserve.end_date and reserve.end_date < reserve.start_date:
        raise ValidationError("End date must be on or after the start date.")
    db.flush()
    return reserve


def delete_reserve(db: Session, user_id: uuid.UUID, reserve_id: uuid.UUID) -> None:
    reserve = get_reserve(db, user_id, reserve_id)
    db.delete(reserve)
    db.flush()
