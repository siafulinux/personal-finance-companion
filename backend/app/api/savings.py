"""Savings goals, contributions and protected allocations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import User
from app.schemas.savings import (
    SavingsContributionCreate,
    SavingsContributionOut,
    SavingsGoalCreate,
    SavingsGoalOut,
    SavingsGoalUpdate,
    SavingsSummary,
)
from app.security.deps import get_current_user
from app.services import savings as savings_service
from app.services.balances import balances_for_accounts
from app.utils.dates import today_in

router = APIRouter(prefix="/savings", tags=["savings"])


def _payload(db: Session, user: User, goal_id: uuid.UUID) -> SavingsGoalOut:
    goal = savings_service.get_goal(db, user.id, goal_id)
    balances = balances_for_accounts(db, user.id)
    row = savings_service.goal_payload(
        db,
        goal,
        today=today_in(user.timezone),
        balances=balances,
        timezone=user.timezone,
    )
    return SavingsGoalOut(**row)


@router.get("", response_model=SavingsSummary)
def get_goals(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SavingsSummary:
    return SavingsSummary(**savings_service.summary(db, user))


@router.post("", response_model=SavingsGoalOut, status_code=201)
def post_goal(
    payload: SavingsGoalCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavingsGoalOut:
    goal = savings_service.create_goal(db, user, payload)
    return _payload(db, user, goal.id)


@router.get("/{goal_id}", response_model=SavingsGoalOut)
def get_goal(
    goal_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavingsGoalOut:
    return _payload(db, user, goal_id)


@router.patch("/{goal_id}", response_model=SavingsGoalOut)
def patch_goal(
    goal_id: uuid.UUID,
    payload: SavingsGoalUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavingsGoalOut:
    savings_service.update_goal(db, user, goal_id, payload)
    return _payload(db, user, goal_id)


@router.delete("/{goal_id}", status_code=204)
def remove_goal(
    goal_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    savings_service.delete_goal(db, user.id, goal_id)
    return Response(status_code=204)


@router.get("/{goal_id}/contributions", response_model=list[SavingsContributionOut])
def get_contributions(
    goal_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavingsContributionOut]:
    return [
        SavingsContributionOut.model_validate(row)
        for row in savings_service.list_contributions(db, user.id, goal_id)
    ]


@router.post(
    "/{goal_id}/contributions", response_model=SavingsGoalOut, status_code=201
)
def post_contribution(
    goal_id: uuid.UUID,
    payload: SavingsContributionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavingsGoalOut:
    savings_service.add_contribution(db, user, goal_id, payload)
    return _payload(db, user, goal_id)


@router.delete("/{goal_id}/contributions/{contribution_id}", status_code=204)
def remove_contribution(
    goal_id: uuid.UUID,
    contribution_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    savings_service.delete_contribution(db, user, goal_id, contribution_id)
    return Response(status_code=204)
