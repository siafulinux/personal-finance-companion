"""Unified forward-looking obligations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import User
from app.security.deps import get_current_user
from app.services.obligations import unified_obligations

router = APIRouter(tags=["obligations"])


@router.get("/obligations")
def get_obligations(
    days: int = Query(default=45, ge=1, le=180),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return unified_obligations(db, user, days=days)
