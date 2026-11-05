"""Category endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import User
from app.schemas.finance import CategoryCreate, CategoryOut, CategoryUpdate
from app.security.deps import get_current_user
from app.services.categories import (
    archive_category,
    create_category,
    delete_category,
    get_category,
    list_categories,
    update_category,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def get_categories(
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CategoryOut]:
    return [
        CategoryOut.model_validate(c)
        for c in list_categories(db, user.id, include_archived=include_archived)
    ]


@router.post("", response_model=CategoryOut, status_code=201)
def post_category(
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    return CategoryOut.model_validate(create_category(db, user.id, payload))


@router.get("/{category_id}", response_model=CategoryOut)
def get_one_category(
    category_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    return CategoryOut.model_validate(get_category(db, user.id, category_id))


@router.patch("/{category_id}", response_model=CategoryOut)
def patch_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    return CategoryOut.model_validate(update_category(db, user.id, category_id, payload))


@router.post("/{category_id}/archive", response_model=CategoryOut)
def archive(
    category_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryOut:
    return CategoryOut.model_validate(archive_category(db, user.id, category_id))


@router.delete("/{category_id}", status_code=204)
def remove_category(
    category_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    delete_category(db, user.id, category_id)
    return Response(status_code=204)
