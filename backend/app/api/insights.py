"""Safe-to-Spend, dashboard, forecast, shopping and AI-ready tool endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.ai.provider import ai_status
from app.calculations.safe_to_spend import CategoryAvailability
from app.database.base import get_db
from app.models import User
from app.schemas.common import APIModel, Money
from app.security.deps import get_current_user
from app.services.assistant_tools import TOOL_REGISTRY, call_tool
from app.services.dashboard import dashboard_snapshot
from app.services.forecast import cash_flow_forecast
from app.services.safe_to_spend import category_availability, compute
from app.services.shopping import shopping_check, shopping_defaults

router = APIRouter(tags=["insights"])


class ShoppingCheckRequest(APIModel):
    store_name: str = Field(default="Store", min_length=1, max_length=120)
    category_id: uuid.UUID
    expected_amount: Money | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=300)


@router.get("/safe-to-spend")
def get_safe_to_spend(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return compute(db, user).as_dict()


@router.get(
    "/safe-to-spend/category/{category_id}", response_model=CategoryAvailability
)
def get_category_safe_to_spend(
    category_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryAvailability:
    return category_availability(db, user, category_id)


@router.get("/dashboard")
def get_dashboard(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return dashboard_snapshot(db, user)


@router.get("/forecast")
def get_forecast(
    days: int = Query(default=60, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return cash_flow_forecast(db, user, days)


@router.get("/shopping/context")
def get_shopping_context(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return shopping_defaults(db, user)


@router.post("/shopping/check")
def post_shopping_check(
    payload: ShoppingCheckRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return shopping_check(
        db,
        user,
        store_name=payload.store_name,
        category_id=payload.category_id,
        expected_amount=payload.expected_amount,
        note=payload.note,
    )


@router.get("/ai/status")
def get_ai_status(user: User = Depends(get_current_user)) -> dict:
    return ai_status()


@router.get("/ai/tools")
def get_ai_tools(user: User = Depends(get_current_user)) -> dict:
    return {
        "tools": [
            {"name": name, "description": meta["description"]}
            for name, meta in TOOL_REGISTRY.items()
        ],
        "note": "AI providers receive only these permission-checked structured payloads.",
    }


@router.get("/ai/tools/{tool_name}")
def run_ai_tool(
    tool_name: str,
    category_id: uuid.UUID | None = None,
    days: int = Query(default=60, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if tool_name == "category_availability":
        if category_id is None:
            return {"error": "category_id is required for this tool"}
        return call_tool(db, user, tool_name, category_id=category_id)
    if tool_name == "forecast":
        return call_tool(db, user, tool_name, days=days)
    return call_tool(db, user, tool_name)
