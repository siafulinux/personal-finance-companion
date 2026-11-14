"""Savings goals, and the careful arithmetic that stops money being counted twice.

A goal protects money in exactly one of two ways:

* ``virtual`` - the balance stays where it is and the goal's saved amount is
  subtracted from Safe-to-Spend. If the underlying account is excluded from
  spending, nothing is subtracted, because that money was never spendable.
* ``account`` - the money already sits in its own account. If that account is
  excluded from spending, nothing is subtracted. If the owner deliberately keeps
  it spendable, the goal protects its saved amount there.

The invariant the whole module exists to keep: **a dollar of savings is deducted
at most once**, however the user happens to have arranged their accounts.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import FinancialAccount, SavingsContribution, SavingsGoal, User
from app.models.enums import Frequency, SavingsMode, SavingsStatus
from app.schemas.savings import SavingsContributionCreate, SavingsGoalCreate, SavingsGoalUpdate
from app.services.balances import balances_for_accounts
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import next_frequency_date, resolve_timezone, today_in
from app.utils.money import ZERO, quantize

MAX_SCHEDULE_ITERATIONS = 600


def list_goals(db: Session, user_id: uuid.UUID, *, include_archived: bool = False) -> list[SavingsGoal]:
    query = select(SavingsGoal).where(SavingsGoal.user_id == user_id)
    if not include_archived:
        query = query.where(SavingsGoal.status != SavingsStatus.ARCHIVED.value)
    return list(
        db.scalars(query.order_by(SavingsGoal.sort_order, SavingsGoal.created_at))
    )


def get_goal(db: Session, user_id: uuid.UUID, goal_id: uuid.UUID) -> SavingsGoal:
    goal = db.scalar(
        select(SavingsGoal).where(SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id)
    )
    if goal is None:
        raise NotFoundError("Savings goal not found.")
    return goal


def _account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID | None) -> FinancialAccount | None:
    if account_id is None:
        return None
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.id == account_id, FinancialAccount.user_id == user_id
        )
    )
    if account is None:
        raise ValidationError("The selected account does not exist.")
    return account


def next_contribution_date(
    goal: SavingsGoal, today: date, *, timezone: str | None = None
) -> date | None:
    if goal.contribution_amount is None or goal.contribution_frequency is None:
        return None
    last = max((c.contributed_on for c in goal.contributions), default=None)
    # `created_at` is a UTC timestamp, so its date can already be the user's tomorrow:
    # a goal created at 20:00 in the Americas is 01:00 UTC. Counting the schedule from
    # that date put the first contribution a day late for them, every cycle after it.
    cursor = last or goal.created_at.astimezone(resolve_timezone(timezone)).date()
    if cursor > today:
        return cursor
    for _ in range(MAX_SCHEDULE_ITERATIONS):
        try:
            cursor = next_frequency_date(cursor, goal.contribution_frequency)
        except ValueError:
            return None
        if cursor > today:
            return cursor
    return None


def _periods_until(today: date, target: date, frequency: str | None) -> int | None:
    if frequency is None or target <= today:
        return None
    cursor = today
    count = 0
    for _ in range(MAX_SCHEDULE_ITERATIONS):
        try:
            cursor = next_frequency_date(cursor, frequency)
        except ValueError:
            return None
        count += 1
        if cursor >= target:
            return count
    return None


def goal_payload(
    db: Session,
    goal: SavingsGoal,
    *,
    today: date,
    balances: dict,
    timezone: str | None = None,
) -> dict[str, object]:
    account = db.get(FinancialAccount, goal.account_id) if goal.account_id else None
    account_balance = None
    spendable = None
    if account is not None:
        summary = balances.get(account.id)
        account_balance = (
            summary.posted_balance if summary is not None else quantize(account.opening_balance)
        )
        spendable = bool(account.include_in_safe_to_spend) and not account.is_archived

    saved = quantize(goal.saved_amount)
    protected = protected_amount(goal, spendable, account_balance)
    target = quantize(goal.target_amount)
    remaining = quantize(max(target - saved, ZERO))
    progress = (
        min(quantize((saved / target) * Decimal("100")), Decimal("100.00")) if target > ZERO else ZERO
    )
    next_date = next_contribution_date(goal, today, timezone=timezone)

    required = None
    if goal.target_date is not None:
        periods = _periods_until(today, goal.target_date, goal.contribution_frequency)
        if periods:
            required = quantize(remaining / periods)

    projected = None
    if goal.contribution_amount and goal.contribution_frequency and remaining > ZERO:
        periods = int(
            (remaining / quantize(goal.contribution_amount)).to_integral_value(
                rounding="ROUND_CEILING"
            )
        )
        cursor = next_date or today
        for _ in range(min(periods, MAX_SCHEDULE_ITERATIONS)):
            try:
                cursor = next_frequency_date(cursor, goal.contribution_frequency)
            except ValueError:
                cursor = None
                break
        projected = cursor

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "target_date": goal.target_date,
        "mode": goal.mode,
        "saved_amount": goal.saved_amount,
        "account_id": goal.account_id,
        "account_name": account.name if account else None,
        "account_balance": account_balance,
        "account_is_spendable": spendable,
        "category_id": goal.category_id,
        "contribution_amount": goal.contribution_amount,
        "contribution_frequency": goal.contribution_frequency,
        "status": goal.status,
        "color": goal.color,
        "notes": goal.notes,
        "created_at": goal.created_at,
        "progress_percent": progress,
        "remaining_to_target": remaining,
        "protected_amount": protected,
        "protects_money": protected > ZERO,
        "next_contribution_date": next_date,
        "required_per_period": required,
        "projected_completion": projected,
    }


def protected_amount(
    goal: SavingsGoal, account_is_spendable: bool | None, account_balance: Decimal | None
) -> Decimal:
    """How much of Safe-to-Spend this goal takes away. Never more than once."""
    if goal.status != SavingsStatus.ACTIVE.value:
        return ZERO
    saved = quantize(goal.saved_amount)
    if goal.mode == SavingsMode.VIRTUAL.value:
        # The money sits in a spend account. If that account does not contribute
        # to Safe-to-Spend the balance is already excluded, so there is nothing
        # left to protect here.
        if account_is_spendable is False:
            return ZERO
        return saved
    # Account-backed: only protect anything when the account is spend-eligible.
    if account_is_spendable is not True or account_balance is None:
        return ZERO
    return min(saved, max(account_balance, ZERO))


def create_goal(db: Session, user: User, payload: SavingsGoalCreate) -> SavingsGoal:
    _account(db, user.id, payload.account_id)
    goal = SavingsGoal(
        user_id=user.id,
        name=payload.name.strip(),
        target_amount=quantize(payload.target_amount),
        target_date=payload.target_date,
        mode=payload.mode.value,
        saved_amount=quantize(payload.saved_amount),
        account_id=payload.account_id,
        category_id=payload.category_id,
        contribution_amount=quantize(payload.contribution_amount)
        if payload.contribution_amount is not None
        else None,
        contribution_frequency=payload.contribution_frequency.value
        if payload.contribution_frequency
        else None,
        status=SavingsStatus.COMPLETED.value if payload.mark_complete else SavingsStatus.ACTIVE.value,
        color=payload.color,
        notes=payload.notes,
    )
    db.add(goal)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A savings goal with that name already exists.") from exc
    return goal


def update_goal(
    db: Session, user: User, goal_id: uuid.UUID, payload: SavingsGoalUpdate
) -> SavingsGoal:
    goal = get_goal(db, user.id, goal_id)
    data = payload.model_dump(exclude_unset=True)
    if "account_id" in data:
        _account(db, user.id, data["account_id"])
    for field, value in data.items():
        if isinstance(value, Decimal):
            value = quantize(value)
        if hasattr(value, "value"):
            value = value.value
        setattr(goal, field, value)
    if goal.mode == SavingsMode.ACCOUNT.value and goal.account_id is None:
        raise ValidationError("Account-backed goals need the savings account they live in.")
    db.flush()
    return goal


def delete_goal(db: Session, user_id: uuid.UUID, goal_id: uuid.UUID) -> None:
    goal = get_goal(db, user_id, goal_id)
    db.delete(goal)
    db.flush()


def list_contributions(
    db: Session, user_id: uuid.UUID, goal_id: uuid.UUID
) -> list[SavingsContribution]:
    get_goal(db, user_id, goal_id)
    return list(
        db.scalars(
            select(SavingsContribution)
            .where(
                SavingsContribution.user_id == user_id,
                SavingsContribution.goal_id == goal_id,
            )
            .order_by(SavingsContribution.contributed_on.desc())
        )
    )


def add_contribution(
    db: Session, user: User, goal_id: uuid.UUID, payload: SavingsContributionCreate
) -> SavingsContribution:
    """Record money set aside. This never moves money between accounts."""
    goal = get_goal(db, user.id, goal_id)
    contribution = SavingsContribution(
        user_id=user.id,
        goal_id=goal.id,
        amount=quantize(payload.amount),
        contributed_on=payload.contributed_on or today_in(user.timezone),
        note=payload.note,
        is_transfer_recorded=False,
    )
    db.add(contribution)
    goal.saved_amount = quantize(goal.saved_amount + quantize(payload.amount))
    _settle_goal(goal)
    db.flush()
    return contribution


def delete_contribution(
    db: Session, user: User, goal_id: uuid.UUID, contribution_id: uuid.UUID
) -> None:
    goal = get_goal(db, user.id, goal_id)
    contribution = db.scalar(
        select(SavingsContribution).where(
            SavingsContribution.id == contribution_id,
            SavingsContribution.goal_id == goal.id,
            SavingsContribution.user_id == user.id,
        )
    )
    if contribution is None:
        raise NotFoundError("Contribution not found.")
    goal.saved_amount = quantize(max(goal.saved_amount - quantize(contribution.amount), ZERO))
    db.delete(contribution)
    _settle_goal(goal)
    db.flush()


def _settle_goal(goal: SavingsGoal) -> None:
    if goal.status == SavingsStatus.COMPLETED.value and goal.saved_amount < goal.target_amount:
        goal.status = SavingsStatus.ACTIVE.value
        goal.completed_at = None
    elif (
        goal.status == SavingsStatus.ACTIVE.value
        and goal.saved_amount >= goal.target_amount
        and goal.target_amount > ZERO
    ):
        from app.utils.dates import utc_now

        goal.status = SavingsStatus.COMPLETED.value
        goal.completed_at = utc_now()


def summary(db: Session, user: User, *, today: date | None = None) -> dict[str, object]:
    today = today or today_in(user.timezone)
    balances = balances_for_accounts(db, user.id)
    goals = list_goals(db, user.id)
    rows = [
        goal_payload(db, goal, today=today, balances=balances, timezone=user.timezone)
        for goal in goals
    ]
    active = [row for row in rows if row["status"] == SavingsStatus.ACTIVE.value]
    monthly = ZERO
    for goal in goals:
        if goal.contribution_amount and goal.contribution_frequency == Frequency.MONTHLY.value:
            monthly += quantize(goal.contribution_amount)
        elif goal.contribution_amount and goal.contribution_frequency == Frequency.WEEKLY.value:
            monthly += quantize(goal.contribution_amount) * Decimal("4.3333")
        elif goal.contribution_amount and goal.contribution_frequency == Frequency.BIWEEKLY.value:
            monthly += quantize(goal.contribution_amount) * Decimal("2.1667")
    return {
        "total_target": quantize(sum((row["target_amount"] for row in active), ZERO)),
        "total_saved": quantize(sum((row["saved_amount"] for row in active), ZERO)),
        "total_protected": quantize(sum((row["protected_amount"] for row in active), ZERO)),
        "active_goals": len(active),
        "completed_goals": len([row for row in rows if row["status"] == SavingsStatus.COMPLETED.value]),
        "monthly_commitment": quantize(monthly),
        "goals": rows,
    }


def planned_contributions(
    db: Session, user: User, *, today: date, horizon_end: date
) -> list[dict[str, object]]:
    """Contributions the plan expects before the horizon ends.

    These are earmarks, not transfers: nothing is moved, and no provider capability
    is assumed.
    """
    balances = balances_for_accounts(db, user.id)
    out: list[dict[str, object]] = []
    for goal in list_goals(db, user.id):
        if goal.status != SavingsStatus.ACTIVE.value:
            continue
        if goal.contribution_amount is None or goal.contribution_frequency is None:
            continue
        due = next_contribution_date(goal, today, timezone=user.timezone)
        while due is not None and due <= horizon_end:
            payload = goal_payload(
                db, goal, today=today, balances=balances, timezone=user.timezone
            )
            out.append(
                {
                    "goal_id": goal.id,
                    "goal_name": goal.name,
                    "due_date": due,
                    "amount": quantize(goal.contribution_amount),
                    "remaining_to_target": payload["remaining_to_target"],
                }
            )
            try:
                nxt = next_frequency_date(due, goal.contribution_frequency)
            except ValueError:
                break
            if nxt == due or (nxt - due) > timedelta(days=400):
                break
            due = nxt
    return out
