"""Budget endpoints including the setup wizard and category availability."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.calculations.safe_to_spend import CategoryAvailability
from app.database.base import get_db
from app.models import User
from app.schemas.planning import (
    BudgetCopyRequest,
    BudgetCreate,
    BudgetSummary,
    BudgetUpdate,
    BudgetWizardRequest,
    CategoryBudgetRow,
)
from app.security.deps import get_current_user
from app.services.budgets import (
    budget_category_row,
    budget_summary,
    copy_budget,
    create_budget,
    create_budget_from_wizard,
    ensure_budget_for_today,
    get_budget,
    require_budget,
    update_budget,
)
from app.services.safe_to_spend import category_availability, compute
from app.utils.dates import today_in

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _summary(db: Session, user: User, year: int, month: int) -> dict:
    budget = require_budget(db, user.id, year, month)
    return budget_summary(db, user.id, budget, today_in(user.timezone))


@router.get("/current", response_model=BudgetSummary)
def current_budget(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> BudgetSummary:
    _, summary = ensure_budget_for_today(db, user.id, user.timezone)
    return BudgetSummary(**summary)


@router.get("/{year}/{month}", response_model=BudgetSummary)
def get_month_budget(
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetSummary:
    return BudgetSummary(**_summary(db, user, year, month))


@router.post("", response_model=BudgetSummary, status_code=201)
def post_budget(
    payload: BudgetCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetSummary:
    budget = create_budget(db, user.id, payload)
    return BudgetSummary(**_summary(db, user, budget.year, budget.month))


@router.patch("/{budget_id}", response_model=BudgetSummary)
def patch_budget(
    budget_id: uuid.UUID,
    payload: BudgetUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetSummary:
    budget = update_budget(db, user.id, budget_id, payload)
    return BudgetSummary(**_summary(db, user, budget.year, budget.month))


@router.post("/copy", response_model=BudgetSummary, status_code=201)
def post_copy(
    payload: BudgetCopyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetSummary:
    budget = copy_budget(db, user.id, payload)
    return BudgetSummary(**_summary(db, user, budget.year, budget.month))


@router.post("/wizard", response_model=BudgetSummary, status_code=201)
def post_wizard(
    payload: BudgetWizardRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetSummary:
    budget = create_budget_from_wizard(db, user.id, payload)
    return BudgetSummary(**_summary(db, user, budget.year, budget.month))


@router.get("/{year}/{month}/categories/{category_id}", response_model=CategoryAvailability)
def get_category_availability(
    year: int,
    month: int,
    category_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryAvailability:
    safe = compute(db, user)
    return category_availability(db, user, category_id, overall=safe)
