"""Monthly budgeting: allocations, carryover, trends and the setup wizard."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Bill,
    BillOccurrence,
    Budget,
    BudgetAllocation,
    Category,
    Transaction,
    User,
)
from app.models.enums import CategoryKind, OccurrenceStatus, TransactionType
from app.schemas.planning import (
    BudgetAllocationInput,
    BudgetCreate,
    BudgetUpdate,
    BudgetWizardRequest,
    CategoryBudgetRow,
)
from app.services.balances import period_totals, spending_by_category
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import add_months, month_bounds, today_in
from app.utils.money import ZERO, quantize

MAX_CARRYOVER_DEPTH = 12


def get_budget(db: Session, user_id: uuid.UUID, year: int, month: int) -> Budget | None:
    return db.scalar(
        select(Budget)
        .options(selectinload(Budget.allocations))
        .where(Budget.user_id == user_id, Budget.year == year, Budget.month == month)
    )


def require_budget(db: Session, user_id: uuid.UUID, year: int, month: int) -> Budget:
    budget = get_budget(db, user_id, year, month)
    if budget is None:
        raise NotFoundError("No budget exists for that month yet.")
    return budget


def create_budget(db: Session, user_id: uuid.UUID, payload: BudgetCreate) -> Budget:
    existing = get_budget(db, user_id, payload.year, payload.month)
    if existing is not None:
        raise ConflictError("A budget already exists for that month. Edit it instead.")
    budget = Budget(
        user_id=user_id,
        year=payload.year,
        month=payload.month,
        name=payload.name,
        notes=payload.notes,
        planned_income=quantize(payload.planned_income) if payload.planned_income is not None else None,
    )
    db.add(budget)
    db.flush()
    _replace_allocations(db, user_id, budget, payload.allocations)
    return budget


def _validate_categories(db: Session, user_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, Category]:
    if not ids:
        return {}
    rows = list(
        db.scalars(
            select(Category).where(Category.user_id == user_id, Category.id.in_(ids))
        )
    )
    found = {row.id: row for row in rows}
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise ValidationError("Some categories do not exist.", details={"missing": missing})
    archived = [c.name for c in rows if c.is_archived]
    if archived:
        raise ValidationError(
            "Archived categories cannot receive new budget allocations.",
            details={"archived": archived},
        )
    return found


def _replace_allocations(db: Session, user_id: uuid.UUID, budget: Budget, allocations) -> None:
    ids = [a.category_id for a in allocations]
    _validate_categories(db, user_id, ids)
    existing = {a.category_id: a for a in list(budget.allocations)}
    incoming = set(ids)
    for category_id, allocation in existing.items():
        if category_id not in incoming:
            budget.allocations.remove(allocation)
            db.delete(allocation)
    for item in allocations:
        allocation = existing.get(item.category_id)
        if allocation is None:
            allocation = BudgetAllocation(
                category_id=item.category_id,
                amount=quantize(item.amount),
                carryover_enabled=item.carryover_enabled,
                notes=item.notes,
            )
            budget.allocations.append(allocation)
        else:
            allocation.amount = quantize(item.amount)
            allocation.carryover_enabled = item.carryover_enabled
            allocation.notes = item.notes
    db.flush()


def update_budget(
    db: Session, user_id: uuid.UUID, budget_id: uuid.UUID, payload: BudgetUpdate
) -> Budget:
    budget = db.scalar(
        select(Budget)
        .options(selectinload(Budget.allocations))
        .where(Budget.id == budget_id, Budget.user_id == user_id)
    )
    if budget is None:
        raise NotFoundError("Budget not found.")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        budget.name = data["name"]
    if "notes" in data:
        budget.notes = data["notes"]
    if "planned_income" in data:
        budget.planned_income = (
            quantize(data["planned_income"]) if data["planned_income"] is not None else None
        )
    if data.get("allocations") is not None:
        _replace_allocations(db, user_id, budget, payload.allocations or [])
    db.flush()
    return budget


def _carryover_in(
    db: Session, user_id: uuid.UUID, year: int, month: int, category_id: uuid.UUID, depth: int = 0
) -> Decimal:
    if depth >= MAX_CARRYOVER_DEPTH:
        return ZERO
    first, _ = month_bounds(year, month)
    previous = add_months(first, -1)
    prev_budget = get_budget(db, user_id, previous.year, previous.month)
    if prev_budget is None:
        return ZERO
    allocation = next(
        (a for a in prev_budget.allocations if a.category_id == category_id), None
    )
    if allocation is None or not allocation.carryover_enabled:
        return ZERO
    prev_first, prev_last = month_bounds(previous.year, previous.month)
    prev_spent = spending_by_category(db, user_id, prev_first, prev_last).get(category_id, ZERO)
    prev_carry = _carryover_in(db, user_id, previous.year, previous.month, category_id, depth + 1)
    leftover = allocation.amount + prev_carry - prev_spent
    return quantize(leftover if leftover > ZERO else ZERO)


def _upcoming_commitments(
    db: Session, user_id: uuid.UUID, category_id: uuid.UUID, start: date, end: date
) -> Decimal:
    rows = db.scalars(
        select(BillOccurrence)
        .join(Bill, Bill.id == BillOccurrence.bill_id)
        .where(
            BillOccurrence.user_id == user_id,
            Bill.is_active.is_(True),
            Bill.category_id == category_id,
            BillOccurrence.due_date >= start,
            BillOccurrence.due_date <= end,
            BillOccurrence.status.in_(
                [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
            ),
        )
    ).all()
    return quantize(sum((o.remaining_amount for o in rows), ZERO))


def _transaction_counts(db: Session, user_id: uuid.UUID, start: date, end: date) -> dict[uuid.UUID | None, int]:
    from sqlalchemy import func

    rows = db.execute(
        select(Transaction.category_id, func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.txn_date >= start,
            Transaction.txn_date <= end,
            Transaction.tx_type.in_(
                [
                    TransactionType.PURCHASE.value,
                    TransactionType.BILL_PAYMENT.value,
                    TransactionType.REFUND.value,
                ]
            ),
        )
        .group_by(Transaction.category_id)
    ).all()
    return {category_id: int(count) for category_id, count in rows}


def budget_summary(
    db: Session, user_id: uuid.UUID, budget: Budget, today: date | None = None
) -> dict[str, object]:
    start, end = month_bounds(budget.year, budget.month)
    spent_map = spending_by_category(db, user_id, start, end)
    prev_first, prev_last = month_bounds(*_previous_period(budget.year, budget.month))
    prev_spent_map = spending_by_category(db, user_id, prev_first, prev_last)
    counts = _transaction_counts(db, user_id, start, end)

    categories: dict[uuid.UUID, Category] = {
        c.id: c
        for c in db.scalars(
            select(Category).where(
                Category.user_id == user_id,
                Category.id.in_(
                    set(list(spent_map.keys()) + [a.category_id for a in budget.allocations]) - {None}
                ),
            )
        )
    }

    rows: list[dict[str, object]] = []
    seen: set[uuid.UUID] = set()
    allocations = {a.category_id: a for a in budget.allocations}
    all_ids = set(allocations) | {cid for cid, amount in spent_map.items() if cid and amount > ZERO}
    for category_id in all_ids:
        category = categories.get(category_id)
        if category is None:
            continue
        seen.add(category_id)
        allocation = allocations.get(category_id)
        allocated = quantize(allocation.amount) if allocation else ZERO
        carryover_enabled = bool(allocation and allocation.carryover_enabled)
        carry = (
            _carryover_in(db, user_id, budget.year, budget.month, category_id)
            if carryover_enabled
            else ZERO
        )
        spent = quantize(spent_map.get(category_id, ZERO))
        effective = allocated + carry
        remaining = quantize(effective - spent)
        percent = (
            quantize((spent / effective) * Decimal("100"))
            if effective > ZERO
            else (Decimal("100.00") if spent > ZERO else Decimal("0.00"))
        )
        previous = quantize(prev_spent_map.get(category_id, ZERO))
        trend = (
            quantize(((spent - previous) / previous) * Decimal("100"))
            if previous > ZERO
            else None
        )
        rows.append(
            {
                "category_id": category.id,
                "category_name": category.name,
                "category_color": category.color,
                "category_kind": category.kind,
                "allocated": allocated,
                "carryover_in": carry,
                "carryover_enabled": carryover_enabled,
                "spent": spent,
                "remaining": remaining,
                "percent_used": percent,
                "upcoming_commitments": _upcoming_commitments(
                    db, user_id, category_id, start, end
                ),
                "previous_month_spent": previous,
                "trend_percent": trend,
                "transaction_count": counts.get(category_id, 0),
            }
        )
    rows.sort(key=lambda r: (-float(r["allocated"]), str(r["category_name"]).lower()))

    total_allocated = quantize(sum((r["allocated"] for r in rows), ZERO))
    total_carry = quantize(sum((r["carryover_in"] for r in rows), ZERO))
    total_spent = quantize(sum((r["spent"] for r in rows), ZERO))
    effective_total = total_allocated + total_carry
    income = period_totals(db, user_id, start, end)["income"]
    planning_income = (
        quantize(budget.planned_income) if budget.planned_income is not None else income
    )
    percent_used = (
        quantize((total_spent / effective_total) * Decimal("100"))
        if effective_total > ZERO
        else ZERO
    )
    return {
        "id": budget.id,
        "year": budget.year,
        "month": budget.month,
        "name": budget.name,
        "notes": budget.notes,
        "total_allocated": total_allocated,
        "total_carryover": total_carry,
        "total_spent": total_spent,
        "total_remaining": quantize(effective_total - total_spent),
        "percent_used": percent_used,
        "income_this_month": income,
        "planned_income": quantize(budget.planned_income) if budget.planned_income is not None else None,
        "unallocated": quantize(planning_income - total_allocated),
        "rows": rows,
        "created_from_wizard": budget.created_from_wizard,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


def _previous_period(year: int, month: int) -> tuple[int, int]:
    first = date(year, month, 1)
    previous = add_months(first, -1)
    return previous.year, previous.month


def copy_budget(db: Session, user_id: uuid.UUID, payload) -> Budget:
    source = require_budget(db, user_id, payload.source_year, payload.source_month)
    existing = get_budget(db, user_id, payload.year, payload.month)
    if existing is not None:
        raise ConflictError("A budget already exists for the target month.")
    budget = Budget(
        user_id=user_id,
        year=payload.year,
        month=payload.month,
        name=source.name,
        notes=source.notes,
        planned_income=source.planned_income,
        created_from_wizard=source.created_from_wizard,
    )
    db.add(budget)
    db.flush()
    factor = (Decimal("100") + quantize(payload.adjust_percent)) / Decimal("100")
    _replace_allocations(
        db,
        user_id,
        budget,
        [
            BudgetAllocationInput(
                category_id=a.category_id,
                amount=quantize(a.amount * factor),
                carryover_enabled=a.carryover_enabled,
                notes=a.notes,
            )
            for a in source.allocations
        ],
    )
    return budget


def create_budget_from_wizard(
    db: Session, user_id: uuid.UUID, payload: BudgetWizardRequest
) -> Budget:
    existing = get_budget(db, user_id, payload.year, payload.month)
    if existing is not None:
        raise ConflictError("A budget already exists for that month. Edit it instead.")
    categories = {
        c.id: c
        for c in db.scalars(
            select(Category).where(Category.user_id == user_id, Category.is_archived.is_(False))
        )
    }
    by_name = {c.name.lower(): c for c in categories.values()}
    start, end = month_bounds(payload.year, payload.month)

    allocations: dict[uuid.UUID, Decimal] = {}
    if payload.include_existing_bills:
        bills = list(
            db.scalars(
                select(Bill).where(Bill.user_id == user_id, Bill.is_active.is_(True))
            )
        )
        for bill in bills:
            if not bill.category_id or bill.category_id not in categories:
                continue
            occurrences = db.scalars(
                select(BillOccurrence).where(
                    BillOccurrence.bill_id == bill.id,
                    BillOccurrence.due_date >= start,
                    BillOccurrence.due_date <= end,
                    BillOccurrence.status.in_(
                        [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
                    ),
                )
            ).all()
            commitment = quantize(sum((o.remaining_amount for o in occurrences), ZERO))
            allocations[bill.category_id] = allocations.get(bill.category_id, ZERO) + commitment

    income = quantize(payload.expected_income)
    savings = quantize(income * quantize(payload.savings_target_percent) / Decimal("100"))
    savings_category = by_name.get("savings")
    if savings > ZERO and savings_category:
        allocations[savings_category.id] = allocations.get(savings_category.id, ZERO) + savings

    committed = sum(allocations.values(), ZERO)
    remaining = quantize(income - committed)
    if remaining > ZERO and payload.priorities:
        valid = [p for p in payload.priorities if p.category_id in categories and p.weight > 0]
        total_weight = sum(p.weight for p in valid)
        if total_weight > 0:
            distributed = ZERO
            for index, priority in enumerate(valid):
                share = (
                    quantize(remaining * Decimal(priority.weight) / Decimal(total_weight))
                    if index < len(valid) - 1
                    else quantize(remaining - distributed)
                )
                distributed += share
                allocations[priority.category_id] = (
                    allocations.get(priority.category_id, ZERO) + share
                )

    budget = Budget(
        user_id=user_id,
        year=payload.year,
        month=payload.month,
        name="Household budget",
        notes=payload.notes,
        planned_income=income,
        created_from_wizard=True,
    )
    db.add(budget)
    db.flush()
    _replace_allocations(
        db,
        user_id,
        budget,
        [
            BudgetAllocationInput(
                category_id=category_id,
                amount=amount,
                carryover_enabled=False,
                notes="Created by setup wizard",
            )
            for category_id, amount in allocations.items()
            if amount > ZERO
        ],
    )
    return budget


def month_budget_lookup(
    db: Session, user_id: uuid.UUID, year: int, month: int, timezone: str
) -> tuple[Budget | None, dict[str, object] | None]:
    budget = get_budget(db, user_id, year, month)
    if budget is None:
        return None, None
    return budget, budget_summary(db, user_id, budget, today_in(timezone))


def ensure_budget_for_today(
    db: Session, user_id: uuid.UUID, timezone: str
) -> tuple[Budget, dict[str, object]]:
    today = today_in(timezone)
    budget = get_budget(db, user_id, today.year, today.month)
    if budget is None:
        budget = Budget(user_id=user_id, year=today.year, month=today.month)
        db.add(budget)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("A budget for this month was created concurrently.") from exc
    return budget, budget_summary(db, user_id, budget, today)


def top_spending_categories(
    db: Session, user_id: uuid.UUID, start: date, end: date, limit: int = 8
) -> list[dict[str, object]]:
    spent = spending_by_category(db, user_id, start, end)
    categories = {
        c.id: c
        for c in db.scalars(select(Category).where(Category.user_id == user_id))
    }
    rows = [
        {
            "category_id": str(category_id) if category_id else None,
            "name": categories[category_id].name if category_id and category_id in categories else "Uncategorized",
            "color": categories[category_id].color if category_id and category_id in categories else "#94a3b8",
            "amount": str(amount),
        }
        for category_id, amount in spent.items()
        if amount > ZERO
    ]
    rows.sort(key=lambda r: float(r["amount"]), reverse=True)
    return rows[:limit]


def budget_category_row(
    db: Session, user_id: uuid.UUID, year: int, month: int, category_id: uuid.UUID
) -> CategoryBudgetRow | None:
    budget = get_budget(db, user_id, year, month)
    start, end = month_bounds(year, month)
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    if category is None:
        return None
    allocation = None
    if budget:
        allocation = next(
            (a for a in budget.allocations if a.category_id == category_id), None
        )
    allocated = allocation.amount if allocation else ZERO
    carry = (
        _carryover_in(db, user_id, year, month, category_id)
        if allocation and allocation.carryover_enabled
        else ZERO
    )
    spent = spending_by_category(db, user_id, start, end).get(category_id, ZERO)
    effective = allocated + carry
    rows = _transaction_counts(db, user_id, start, end)
    prev_first, prev_last = month_bounds(*_previous_period(year, month))
    previous = spending_by_category(db, user_id, prev_first, prev_last).get(category_id, ZERO)
    return CategoryBudgetRow(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_kind=category.kind,
        allocated=quantize(allocated),
        carryover_in=quantize(carry),
        carryover_enabled=bool(allocation and allocation.carryover_enabled),
        spent=quantize(spent),
        remaining=quantize(effective - spent),
        percent_used=(
            quantize(spent / effective * Decimal("100")) if effective > ZERO else ZERO
        ),
        upcoming_commitments=_upcoming_commitments(db, user_id, category_id, start, end),
        previous_month_spent=quantize(previous),
        trend_percent=(
            quantize((spent - previous) / previous * Decimal("100")) if previous > ZERO else None
        ),
        transaction_count=rows.get(category_id, 0),
    )


def expense_categories(db: Session, user_id: uuid.UUID) -> list[Category]:
    return list(
        db.scalars(
            select(Category)
            .where(
                Category.user_id == user_id,
                Category.is_archived.is_(False),
                Category.kind.in_(
                    [CategoryKind.EXPENSE.value, CategoryKind.SAVINGS.value, CategoryKind.DEBT.value]
                ),
            )
            .order_by(Category.sort_order, Category.name)
        )
    )
