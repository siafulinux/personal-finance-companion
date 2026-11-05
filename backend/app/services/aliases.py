"""Merchant aliases: explicit user knowledge that improves deterministic matching."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import MerchantAlias
from app.schemas.planning import MerchantAliasCreate
from app.services.errors import ConflictError, NotFoundError


def list_aliases(db: Session, user_id: uuid.UUID) -> list[MerchantAlias]:
    return list(
        db.scalars(
            select(MerchantAlias)
            .where(MerchantAlias.user_id == user_id)
            .order_by(MerchantAlias.canonical_merchant, MerchantAlias.alias)
        )
    )


def create_alias(
    db: Session, user_id: uuid.UUID, payload: MerchantAliasCreate
) -> MerchantAlias:
    alias = MerchantAlias(
        user_id=user_id,
        alias=payload.alias.strip(),
        canonical_merchant=payload.canonical_merchant.strip(),
        notes=payload.notes,
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("That alias already exists.") from exc
    return alias


def delete_alias(db: Session, user_id: uuid.UUID, alias_id: uuid.UUID) -> None:
    alias = db.scalar(
        select(MerchantAlias).where(
            MerchantAlias.id == alias_id, MerchantAlias.user_id == user_id
        )
    )
    if alias is None:
        raise NotFoundError("Merchant alias not found.")
    db.delete(alias)
    db.flush()
