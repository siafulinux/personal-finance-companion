"""Bills, recurring occurrence materialisation and manual payment recording."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Bill, BillOccurrence, BillPaymentMatch, FinancialAccount, Transaction
from app.models.enums import (
    Frequency,
    MatchStatus,
    OccurrenceStatus,
    TransactionSource,
    TransactionStatus,
    TransactionType,
)
from app.schemas.planning import BillCreate, BillUpdate
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import add_months, clamp_day, iter_due_dates, month_bounds, today_in, utc_now
from app.utils.money import ZERO, clamp_zero, money, quantize

MONTH_BASED_FREQUENCIES = {
    Frequency.MONTHLY.value,
    Frequency.EVERY_TWO_MONTHS.value,
    Frequency.QUARTERLY.value,
    Frequency.SEMIANNUAL.value,
    Frequency.ANNUAL.value,
}
MATERIALIZE_AHEAD_DAYS = 400


def get_bill(db: Session, user_id: uuid.UUID, bill_id: uuid.UUID) -> Bill:
    bill = db.scalar(select(Bill).where(Bill.id == bill_id, Bill.user_id == user_id))
    if bill is None:
        raise NotFoundError("Bill not found.")
    return bill


def _validate_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID | None) -> None:
    if account_id is None:
        return
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.id == account_id, FinancialAccount.user_id == user_id
        )
    )
    if account is None:
        raise ValidationError("The selected payment account does not exist.")
    if account.is_archived:
        raise ValidationError("The selected payment account is archived.")


def ensure_bill_occurrences(db: Session, bill: Bill, until: date | None = None) -> list[BillOccurrence]:
    """Idempotently materialise occurrences from the bill anchor through ``until``."""
    if not bill.is_active:
        return []
    until = until or (today_in(bill.user.timezone) + timedelta(days=MATERIALIZE_AHEAD_DAYS))  # type: ignore[union-attr]
    existing = {
        row
        for row in db.scalars(
            select(BillOccurrence.due_date).where(BillOccurrence.bill_id == bill.id)
        ).all()
    }
    preferred_day = bill.due_day if bill.frequency in MONTH_BASED_FREQUENCIES else None
    due_dates = iter_due_dates(
        bill.anchor_date,
        bill.frequency,
        until,
        custom_interval_days=bill.custom_interval_days,
        preferred_day=preferred_day,
    )
    created: list[BillOccurrence] = []
    for due in due_dates:
        if due in existing:
            continue
        occurrence = BillOccurrence(
            bill_id=bill.id,
            user_id=bill.user_id,
            due_date=due,
            expected_amount=bill.expected_amount,
            paid_amount=ZERO,
            status=OccurrenceStatus.UPCOMING.value,
        )
        db.add(occurrence)
        created.append(occurrence)
    if due_dates:
        bill.occurrences_generated_until = max(due_dates)
    try:
        db.flush()
    except IntegrityError:
        # Concurrent generation is harmless: the unique (bill, due_date) wins.
        db.rollback()
        raise ConflictError("Bill occurrences were generated concurrently. Retry.") from None
    return created


def materialize_all(db: Session, user_id: uuid.UUID, timezone: str, until: date | None = None) -> None:
    target = until or (today_in(timezone) + timedelta(days=MATERIALIZE_AHEAD_DAYS))
    bills = list(db.scalars(select(Bill).where(Bill.user_id == user_id, Bill.is_active.is_(True))))
    for bill in bills:
        ensure_bill_occurrences(db, bill, target)


def _validate_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID | None) -> None:
    if category_id is None:
        return
    from app.models import Category

    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    if category is None:
        raise ValidationError("The selected category does not exist.")
    if category.is_archived:
        raise ValidationError("The selected category is archived.")


def _normalise_anchor(payload: BillCreate) -> date:
    anchor = payload.anchor_date or payload.first_due_date
    if payload.frequency in MONTH_BASED_FREQUENCIES and payload.due_day:
        anchor = clamp_day(anchor.year, anchor.month, payload.due_day)
    return anchor


def create_bill(db: Session, user_id: uuid.UUID, payload: BillCreate, timezone: str) -> Bill:
    _validate_account(db, user_id, payload.account_id)
    _validate_category(db, user_id, payload.category_id)
    anchor = _normalise_anchor(payload)
    bill = Bill(
        user_id=user_id,
        name=payload.name.strip(),
        merchant=payload.merchant.strip() if payload.merchant else None,
        expected_amount=money(payload.expected_amount),
        minimum_amount=money(payload.minimum_amount) if payload.minimum_amount is not None else None,
        due_day=payload.due_day,
        anchor_date=anchor,
        frequency=payload.frequency.value,
        custom_interval_days=payload.custom_interval_days,
        account_id=payload.account_id,
        category_id=payload.category_id,
        notes=payload.notes,
        is_essential=payload.is_essential,
        reserve_in_safe_to_spend=payload.reserve_in_safe_to_spend,
        is_active=payload.is_active,
        auto_pay=payload.auto_pay,
    )
    db.add(bill)
    db.flush()
    ensure_bill_occurrences(db, bill, today_in(timezone) + timedelta(days=MATERIALIZE_AHEAD_DAYS))
    return bill


def update_bill(
    db: Session, user_id: uuid.UUID, bill_id: uuid.UUID, payload: BillUpdate, timezone: str
) -> Bill:
    bill = get_bill(db, user_id, bill_id)
    data = payload.model_dump(exclude_unset=True)
    if "account_id" in data:
        _validate_account(db, user_id, data["account_id"])
    if "category_id" in data:
        _validate_category(db, user_id, data["category_id"])
    schedule_changed = any(
        key in data and data[key] is not None
        for key in ("anchor_date", "frequency", "custom_interval_days", "due_day")
    )
    if "expected_amount" in data and data["expected_amount"] is not None:
        data["expected_amount"] = money(data["expected_amount"])
    for key, value in data.items():
        if hasattr(value, "value"):
            value = value.value
        if key == "name" and value:
            value = value.strip()
        setattr(bill, key, value)
    if schedule_changed:
        today = today_in(timezone)
        future = list(
            db.scalars(
                select(BillOccurrence).where(
                    BillOccurrence.bill_id == bill.id,
                    BillOccurrence.status.in_(
                        [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
                    ),
                    BillOccurrence.due_date >= today,
                )
            )
        )
        for occurrence in future:
            # Only unpaid, unmatched future occurrences can be regenerated safely.
            has_confirmed = db.scalar(
                select(BillPaymentMatch.id).where(
                    BillPaymentMatch.occurrence_id == occurrence.id,
                    BillPaymentMatch.status == MatchStatus.CONFIRMED.value,
                )
            )
            if occurrence.paid_amount == ZERO and not has_confirmed:
                db.delete(occurrence)
        db.flush()
        bill.occurrences_generated_until = None
    # Unpaid occurrences follow the current expected amount.
    for occurrence in db.scalars(
        select(BillOccurrence).where(
            BillOccurrence.bill_id == bill.id,
            BillOccurrence.status != OccurrenceStatus.PAID.value,
            BillOccurrence.paid_amount == ZERO,
        )
    ):
        occurrence.expected_amount = bill.expected_amount
    db.flush()
    if bill.is_active:
        ensure_bill_occurrences(
            db, bill, today_in(timezone) + timedelta(days=MATERIALIZE_AHEAD_DAYS)
        )
    return bill


def delete_bill(db: Session, user_id: uuid.UUID, bill_id: uuid.UUID) -> None:
    bill = get_bill(db, user_id, bill_id)
    confirmed = db.scalar(
        select(BillPaymentMatch.id)
        .join(BillOccurrence, BillOccurrence.id == BillPaymentMatch.occurrence_id)
        .where(
            BillOccurrence.bill_id == bill.id,
            BillPaymentMatch.status == MatchStatus.CONFIRMED.value,
        )
    )
    if confirmed:
        raise ConflictError(
            "This bill has confirmed payments. Deactivate it instead of deleting, "
            "so payment history stays auditable."
        )
    db.delete(bill)
    db.flush()


def get_occurrence(
    db: Session, user_id: uuid.UUID, occurrence_id: uuid.UUID, *, lock: bool = False
) -> BillOccurrence:
    stmt = (
        select(BillOccurrence)
        .options(selectinload(BillOccurrence.bill))
        .where(BillOccurrence.id == occurrence_id, BillOccurrence.user_id == user_id)
    )
    if lock:
        stmt = stmt.with_for_update()
    occurrence = db.scalar(stmt)
    if occurrence is None:
        raise NotFoundError("Bill occurrence not found.")
    return occurrence


def recompute_occurrence(db: Session, occurrence: BillOccurrence) -> BillOccurrence:
    """Derive paid amount and status from confirmed matches (never double counts)."""
    confirmed = db.execute(
        select(BillPaymentMatch.amount).where(
            BillPaymentMatch.occurrence_id == occurrence.id,
            BillPaymentMatch.status == MatchStatus.CONFIRMED.value,
        )
    ).scalars().all()
    paid = quantize(sum(confirmed, ZERO)) if confirmed else ZERO
    expected = quantize(occurrence.expected_amount)
    if paid > expected:
        paid = expected
    occurrence.paid_amount = paid
    if paid >= expected and expected > ZERO:
        occurrence.status = OccurrenceStatus.PAID.value
        occurrence.confirmed_at = occurrence.confirmed_at or utc_now()
    elif paid > ZERO:
        occurrence.status = OccurrenceStatus.PARTIAL.value
        occurrence.confirmed_at = None
    elif occurrence.status != OccurrenceStatus.SKIPPED.value:
        occurrence.status = OccurrenceStatus.UPCOMING.value
        occurrence.confirmed_at = None
    db.flush()
    return occurrence


def mark_paid(
    db: Session, user_id: uuid.UUID, occurrence_id: uuid.UUID, *, notes: str | None = None
) -> BillOccurrence:
    """Manual confirmation for bills already paid outside the tracked accounts."""
    occurrence = get_occurrence(db, user_id, occurrence_id)
    if occurrence.status == OccurrenceStatus.PAID.value:
        return occurrence
    occurrence.paid_amount = occurrence.expected_amount
    occurrence.status = OccurrenceStatus.PAID.value
    occurrence.confirmed_at = utc_now()
    if notes:
        occurrence.notes = notes
    db.flush()
    return occurrence


def mark_unpaid(db: Session, user_id: uuid.UUID, occurrence_id: uuid.UUID) -> BillOccurrence:
    occurrence = get_occurrence(db, user_id, occurrence_id)
    confirmed = list(
        db.scalars(
            select(BillPaymentMatch).where(
                BillPaymentMatch.occurrence_id == occurrence.id,
                BillPaymentMatch.status == MatchStatus.CONFIRMED.value,
            )
        )
    )
    for match in confirmed:
        match.status = MatchStatus.REJECTED.value
    occurrence.paid_amount = ZERO
    occurrence.status = OccurrenceStatus.UPCOMING.value
    occurrence.confirmed_at = None
    db.flush()
    recompute_occurrence(db, occurrence)
    return occurrence


def skip_occurrence(db: Session, user_id: uuid.UUID, occurrence_id: uuid.UUID) -> BillOccurrence:
    occurrence = get_occurrence(db, user_id, occurrence_id)
    if occurrence.status == OccurrenceStatus.PAID.value:
        raise ConflictError("A paid occurrence cannot be skipped.")
    occurrence.status = OccurrenceStatus.SKIPPED.value
    occurrence.confirmed_at = None
    db.flush()
    return occurrence


def record_payment(
    db: Session,
    user_id: uuid.UUID,
    occurrence_id: uuid.UUID,
    *,
    amount: Decimal | None,
    account_id: uuid.UUID,
    paid_on: date | None,
    notes: str | None,
    timezone: str,
) -> tuple[BillOccurrence, Transaction]:
    """Create a bill-payment transaction and confirm the link atomically."""
    occurrence = get_occurrence(db, user_id, occurrence_id, lock=True)
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.id == account_id, FinancialAccount.user_id == user_id
        )
    )
    if account is None:
        raise ValidationError("The selected payment account does not exist.")
    if account.is_archived:
        raise ValidationError("The selected payment account is archived.")
    remaining = occurrence.remaining_amount
    if remaining <= ZERO:
        raise ConflictError("This occurrence is already fully paid.")
    payment_amount = money(amount) if amount is not None else remaining
    if payment_amount <= ZERO:
        raise ValidationError("Payment amount must be greater than zero.")
    if payment_amount > remaining:
        raise ValidationError(
            f"Payment exceeds the remaining balance of {remaining} for this occurrence."
        )
    bill = occurrence.bill or get_bill(db, user_id, occurrence.bill_id)
    txn = Transaction(
        user_id=user_id,
        account_id=account.id,
        description=f"{bill.name} payment",
        merchant=bill.merchant or bill.name,
        amount=payment_amount,
        tx_type=TransactionType.BILL_PAYMENT.value,
        status=TransactionStatus.POSTED.value,
        txn_date=paid_on or today_in(timezone),
        category_id=bill.category_id,
        notes=notes,
        source=TransactionSource.MANUAL.value,
        tags=["bill-payment"],
    )
    db.add(txn)
    db.flush()
    match = BillPaymentMatch(
        user_id=user_id,
        occurrence_id=occurrence.id,
        transaction_id=txn.id,
        amount=payment_amount,
        confidence=Decimal("1.000"),
        status=MatchStatus.CONFIRMED.value,
        is_automatic=False,
        is_ambiguous=False,
        reason="Payment recorded manually",
        confirmed_at=utc_now(),
    )
    db.add(match)
    db.flush()
    recompute_occurrence(db, occurrence)
    return occurrence, txn


def occurrence_dict(occurrence: BillOccurrence, today: date) -> dict[str, object]:
    bill = occurrence.bill
    is_overdue = (
        occurrence.due_date < today
        and occurrence.status
        not in (OccurrenceStatus.PAID.value, OccurrenceStatus.SKIPPED.value)
    )
    return {
        "id": str(occurrence.id),
        "bill_id": str(occurrence.bill_id),
        "bill_name": bill.name if bill else None,
        "merchant": bill.merchant if bill else None,
        "category_id": str(bill.category_id) if bill and bill.category_id else None,
        "account_id": str(bill.account_id) if bill and bill.account_id else None,
        "due_date": occurrence.due_date.isoformat(),
        "expected_amount": str(quantize(occurrence.expected_amount)),
        "paid_amount": str(quantize(occurrence.paid_amount)),
        "remaining_amount": str(occurrence.remaining_amount),
        "status": occurrence.status,
        "is_overdue": is_overdue,
        "is_essential": bill.is_essential if bill else True,
        "is_partial": occurrence.status == OccurrenceStatus.PARTIAL.value,
        "confirmed_at": occurrence.confirmed_at.isoformat() if occurrence.confirmed_at else None,
        "notes": occurrence.notes,
    }


def list_occurrences(
    db: Session,
    user_id: uuid.UUID,
    today: date,
    *,
    status: str | None = None,
    start: date | None = None,
    end: date | None = None,
    overdue_only: bool = False,
    limit: int = 200,
) -> list[BillOccurrence]:
    query = (
        select(BillOccurrence)
        .options(selectinload(BillOccurrence.bill))
        .where(BillOccurrence.user_id == user_id)
    )
    if status:
        query = query.where(BillOccurrence.status == status)
    if start:
        query = query.where(BillOccurrence.due_date >= start)
    if end:
        query = query.where(BillOccurrence.due_date <= end)
    if overdue_only:
        query = query.where(
            BillOccurrence.due_date < today,
            BillOccurrence.status.in_(
                [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
            ),
        )
    query = query.order_by(BillOccurrence.due_date, BillOccurrence.created_at).limit(limit)
    return list(db.scalars(query))


def month_calendar(db: Session, user_id: uuid.UUID, year: int, month: int, today: date):
    start, end = month_bounds(year, month)
    occurrences = list_occurrences(db, user_id, today, start=start, end=end, limit=400)
    return start, end, [occurrence_dict(o, today) for o in occurrences]


def bill_summary(bill: Bill, today: date) -> dict[str, object]:
    future = [
        o
        for o in bill.occurrences
        if o.due_date >= today
        and o.status not in (OccurrenceStatus.PAID.value, OccurrenceStatus.SKIPPED.value)
    ]
    future.sort(key=lambda o: o.due_date)
    next_occurrence = future[0] if future else None
    return {
        "next_due_date": next_occurrence.due_date.isoformat() if next_occurrence else None,
        "next_remaining": str(next_occurrence.remaining_amount) if next_occurrence else "0.00",
        "is_overdue": any(
            o.due_date < today
            and o.status in (OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value)
            for o in bill.occurrences
        ),
    }


def monthly_bill_commitment(db: Session, user_id: uuid.UUID, year: int, month: int) -> Decimal:
    start, end = month_bounds(year, month)
    occurrences = list(
        db.scalars(
            select(BillOccurrence)
            .where(
                BillOccurrence.user_id == user_id,
                BillOccurrence.due_date >= start,
                BillOccurrence.due_date <= end,
                BillOccurrence.status.in_(
                    [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
                ),
            )
        )
    )
    return quantize(sum((o.remaining_amount for o in occurrences), ZERO))


def _advance_income_date(current: date, frequency: str) -> date:
    """Advance a recurring payday without drifting on month boundaries."""
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "biweekly":
        return current + timedelta(days=14)
    if frequency == "semimonthly":
        if current.day < 15:
            return current.replace(day=15)
        return add_months(current.replace(day=1), 1) + timedelta(days=14)
    if frequency == "monthly":
        return add_months(current, 1)
    return current + timedelta(days=30)


def next_payday_date(db: Session, user_id: uuid.UUID, today: date) -> date | None:
    """The next future payday, projected forward from a possibly stale anchor."""
    from app.models import IncomeSource

    sources = db.scalars(
        select(IncomeSource).where(
            IncomeSource.user_id == user_id,
            IncomeSource.is_active.is_(True),
            IncomeSource.next_payday.is_not(None),
        )
    ).all()
    dates: list[date] = []
    for source in sources:
        current = source.next_payday
        if current is None:
            continue
        if current > today:
            dates.append(current)
            continue
        if source.frequency == "irregular":
            # An irregular source cannot be projected reliably.
            continue
        for _ in range(240):
            current = _advance_income_date(current, source.frequency)
            if current > today:
                dates.append(current)
                break
    return min(dates) if dates else None


def horizon_candidates(
    db: Session, user_id: uuid.UUID, today: date, horizon_end: date
) -> list[BillOccurrence]:
    """Unpaid occurrences that must be reserved: all overdue plus those in the horizon."""
    return list(
        db.scalars(
            select(BillOccurrence)
            .options(selectinload(BillOccurrence.bill))
            .where(
                BillOccurrence.user_id == user_id,
                BillOccurrence.status.in_(
                    [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
                ),
                BillOccurrence.due_date <= horizon_end,
            )
            .order_by(BillOccurrence.due_date)
        )
    )


def add_months_safe(value: date, months: int) -> date:
    return add_months(value, months)
