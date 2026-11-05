"""Category management including the default Phase 1 category set."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BudgetAllocation, Category, Transaction
from app.schemas.finance import CategoryCreate, CategoryUpdate
from app.services.errors import ConflictError, NotFoundError, ValidationError

DEFAULT_CATEGORIES: list[tuple[str, str, str]] = [
    ("Housing", "#6366f1", "home"),
    ("Electricity", "#f59e0b", "zap"),
    ("Water", "#0ea5e9", "droplet"),
    ("Internet", "#8b5cf6", "wifi"),
    ("Phone", "#14b8a6", "smartphone"),
    ("Insurance", "#64748b", "shield"),
    ("Groceries", "#22c55e", "shopping-basket"),
    ("Restaurants", "#f97316", "utensils"),
    ("Fast food", "#fb923c", "burger"),
    ("Clothing", "#ec4899", "shirt"),
    ("Shopping", "#a855f7", "bag"),
    ("Transportation", "#3b82f6", "bus"),
    ("Fuel", "#ef4444", "fuel"),
    ("Medical", "#10b981", "heart-pulse"),
    ("Entertainment", "#eab308", "ticket"),
    ("Personal care", "#06b6d4", "sparkles"),
    ("Savings", "#059669", "piggy-bank"),
    ("Debt payments", "#dc2626", "credit-card"),
    ("Miscellaneous", "#94a3b8", "shapes"),
]


def list_categories(
    db: Session, user_id: uuid.UUID, *, include_archived: bool = False
) -> list[Category]:
    query = select(Category).where(Category.user_id == user_id)
    if not include_archived:
        query = query.where(Category.is_archived.is_(False))
    return list(db.scalars(query.order_by(Category.sort_order, Category.name)))


def get_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    if category is None:
        raise NotFoundError("Category not found.")
    return category


def seed_default_categories(db: Session, user_id: uuid.UUID) -> list[Category]:
    existing = set(
        db.scalars(select(Category.name).where(Category.user_id == user_id)).all()
    )
    created: list[Category] = []
    for index, (name, color, icon) in enumerate(DEFAULT_CATEGORIES):
        if name in existing:
            continue
        category = Category(
            user_id=user_id,
            name=name,
            kind="expense",
            color=color,
            icon=icon,
            is_system=True,
            sort_order=index,
        )
        db.add(category)
        created.append(category)
    db.flush()
    return created


def create_category(db: Session, user_id: uuid.UUID, payload: CategoryCreate) -> Category:
    category = Category(
        user_id=user_id,
        name=payload.name.strip(),
        kind=payload.kind.value,
        color=payload.color,
        icon=payload.icon,
        sort_order=payload.sort_order,
    )
    db.add(category)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A category with that name already exists.") from exc
    return category


def update_category(
    db: Session, user_id: uuid.UUID, category_id: uuid.UUID, payload: CategoryUpdate
) -> Category:
    category = get_category(db, user_id, category_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        data["name"] = data["name"].strip()
    if data.get("is_archived") is True:
        data["is_archived"] = True
    for field, value in data.items():
        setattr(category, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Another category already uses that name.") from exc
    return category


def archive_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    category = get_category(db, user_id, category_id)
    category.is_archived = True
    db.flush()
    return category


def delete_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
    category = get_category(db, user_id, category_id)
    tx_count = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id, Transaction.category_id == category_id
        )
    )
    alloc_count = db.scalar(
        select(func.count(BudgetAllocation.id)).where(BudgetAllocation.category_id == category_id)
    )
    if tx_count or alloc_count:
        raise ConflictError(
            "This category is in use by transactions or budgets. Archive it instead of deleting."
        )
    db.delete(category)
    db.flush()


def ensure_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    category = get_category(db, user_id, category_id)
    if category.is_archived:
        raise ValidationError("That category is archived. Choose an active category.")
    return category
