"""Loans and advances: balances derived from confirmed repayments.

Nothing here guesses a loan term. A payoff date is produced only from figures the
user supplied (a remaining count, a scheduled payment and its frequency), and the
response says whether the balance and the payoff date are estimates.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, FinancialAccount, Loan, LoanPayment, User
from app.models.enums import (
    BalanceSource,
    LoanStatus,
    MatchStatus,
    TransactionStatus,
    TransactionType,
)
from app.schemas.loans import LoanCreate, LoanPaymentCreate, LoanPaymentUpdate, LoanUpdate
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import next_frequency_date, today_in
from app.utils.money import ZERO, quantize

# A payoff projection beyond this many periods is meaningless for a consumer loan.
MAX_PROJECTION_PERIODS = 600


def get_loan(db: Session, user_id: uuid.UUID, loan_id: uuid.UUID) -> Loan:
    loan = db.scalar(select(Loan).where(Loan.id == loan_id, Loan.user_id == user_id))
    if loan is None:
        raise NotFoundError("Loan not found.")
    return loan


def list_loans(db: Session, user_id: uuid.UUID) -> list[Loan]:
    return list(
        db.scalars(
            select(Loan)
            .where(Loan.user_id == user_id)
            .order_by(Loan.status, Loan.sort_order, Loan.created_at)
        )
    )


def _confirmed_payments(loan: Loan) -> list[LoanPayment]:
    return [p for p in loan.payments if p.status == MatchStatus.CONFIRMED.value]


def _check_owner(db: Session, user_id: uuid.UUID, account_id: uuid.UUID | None, category_id: uuid.UUID | None) -> None:
    if account_id is not None:
        exists = db.scalar(
            select(FinancialAccount.id).where(
                FinancialAccount.id == account_id, FinancialAccount.user_id == user_id
            )
        )
        if exists is None:
            raise ValidationError("The selected account does not exist.")
    if category_id is not None:
        exists = db.scalar(
            select(Category.id).where(Category.id == category_id, Category.user_id == user_id)
        )
        if exists is None:
            raise ValidationError("The selected category does not exist.")


def _advance(value: date, frequency: str | None) -> date | None:
    if not frequency:
        return None
    try:
        return next_frequency_date(value, frequency)
    except ValueError:
        return None


def payoff_projection(
    loan: Loan, balance: Decimal
) -> tuple[date | None, bool, int | None]:
    """Return ``(payoff_date, is_estimate, remaining_installments)``.

    Three sources, best first:

    1. A remaining count the user knows. Still an estimate for the *date* because
       payment dates drift, but the strongest signal available.
    2. Scheduled payment + frequency, until the balance is retired.
    3. No schedule at all: no date, and we say so rather than inventing one.
    """
    if balance <= ZERO or loan.status == LoanStatus.PAID_OFF.value:
        return (None if balance > ZERO else None), False, 0 if balance <= ZERO else loan.remaining_payments

    scheduled = quantize(loan.scheduled_payment) if loan.scheduled_payment else None
    anchor = loan.next_payment_date

    if loan.remaining_payments is not None and anchor is not None:
        if loan.remaining_payments <= 0:
            return anchor, True, 0
        cursor = anchor
        for _ in range(min(loan.remaining_payments - 1, MAX_PROJECTION_PERIODS)):
            nxt = _advance(cursor, loan.payment_frequency)
            if nxt is None:
                break
            cursor = nxt
        return cursor, True, loan.remaining_payments

    if scheduled and scheduled > ZERO and anchor is not None and loan.payment_frequency:
        remaining = balance
        cursor = anchor
        periods = 0
        for _ in range(MAX_PROJECTION_PERIODS):
            remaining -= scheduled
            periods += 1
            if remaining <= ZERO:
                return cursor, True, periods
            nxt = _advance(cursor, loan.payment_frequency)
            if nxt is None:
                return None, True, None
            cursor = nxt
        return None, True, None

    if scheduled and scheduled > ZERO:
        periods = int((balance / scheduled).to_integral_value(rounding="ROUND_CEILING"))
        return None, True, periods

    return None, False, None


def loan_numbers(loan: Loan) -> dict[str, object]:
    """Every derived figure for one loan, computed once and reused by the API and engine."""
    confirmed = _confirmed_payments(loan)
    principal = quantize(sum((quantize(p.effective_principal) for p in confirmed), ZERO))
    interest = quantize(sum((quantize(p.interest_amount or ZERO) for p in confirmed), ZERO))
    fees = quantize(sum((quantize(p.fee_amount or ZERO) for p in confirmed), ZERO))
    total = quantize(sum((quantize(p.amount) for p in confirmed), ZERO))

    opening = quantize(loan.opening_balance)
    balance = quantize(max(opening - principal, ZERO))

    # An unsplit payment still reduces the loan, but by an assumed amount: the
    # whole payment is treated as principal. That is common and useful, and it is
    # also why the derived balance is labelled an estimate in that case.
    unsplit = any(p.principal_amount is None for p in confirmed)
    balance_is_estimate = unsplit or loan.balance_source == BalanceSource.DERIVED.value

    outstanding_at_start = opening if opening > ZERO else quantize(loan.original_amount)
    repaid_share = (
        quantize((principal / outstanding_at_start) * Decimal("100"))
        if outstanding_at_start > ZERO
        else Decimal("100.00")
    )
    payoff_date, payoff_estimate, installments = payoff_projection(loan, balance)
    last_paid = max((p.paid_on for p in confirmed), default=None)

    return {
        "current_balance": balance,
        "principal_repaid": principal,
        "interest_paid": interest,
        "fees_paid": fees,
        "total_repaid": total,
        "balance_is_estimate": balance_is_estimate,
        "progress_percent": min(repaid_share, Decimal("100.00")),
        "payment_count": len(confirmed),
        "last_payment_date": last_paid,
        "estimated_payoff_date": payoff_date,
        "payoff_is_estimate": payoff_estimate,
        "remaining_installments": installments,
    }


def loan_payload(loan: Loan) -> dict[str, object]:
    numbers = loan_numbers(loan)
    return {
        "id": loan.id,
        "name": loan.name,
        "lender": loan.lender,
        "loan_type": loan.loan_type,
        "original_amount": loan.original_amount,
        "opening_balance": loan.opening_balance,
        "balance_as_of": loan.balance_as_of,
        "balance_source": loan.balance_source,
        "apr": loan.apr,
        "interest_charged": loan.interest_charged,
        "fees_charged": loan.fees_charged,
        "next_payment_date": loan.next_payment_date,
        "scheduled_payment": loan.scheduled_payment,
        "payment_frequency": loan.payment_frequency,
        "remaining_payments": loan.remaining_payments,
        "account_id": loan.account_id,
        "category_id": loan.category_id,
        "status": loan.status,
        "notes": loan.notes,
        "created_at": loan.created_at,
        **numbers,
    }


def create_loan(db: Session, user: User, payload: LoanCreate) -> Loan:
    _check_owner(db, user.id, payload.account_id, payload.category_id)
    loan = Loan(
        user_id=user.id,
        name=payload.name.strip(),
        lender=payload.lender,
        loan_type=payload.loan_type.value,
        original_amount=quantize(payload.original_amount),
        opening_balance=quantize(payload.opening_balance),
        balance_as_of=payload.balance_as_of or today_in(user.timezone),
        balance_source=BalanceSource.USER.value,
        apr=payload.apr,
        interest_charged=quantize(payload.interest_charged) if payload.interest_charged is not None else None,
        fees_charged=quantize(payload.fees_charged) if payload.fees_charged is not None else None,
        next_payment_date=payload.next_payment_date,
        scheduled_payment=quantize(payload.scheduled_payment) if payload.scheduled_payment is not None else None,
        payment_frequency=payload.payment_frequency.value if payload.payment_frequency else None,
        remaining_payments=payload.remaining_payments,
        account_id=payload.account_id,
        category_id=payload.category_id,
        status=payload.status.value,
        notes=payload.notes,
    )
    db.add(loan)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A loan with that name already exists.") from exc
    return loan


def update_loan(db: Session, user: User, loan_id: uuid.UUID, payload: LoanUpdate) -> Loan:
    loan = get_loan(db, user.id, loan_id)
    data = payload.model_dump(exclude_unset=True)
    _check_owner(db, user.id, data.get("account_id"), data.get("category_id"))
    for field, value in data.items():
        if isinstance(value, Decimal):
            value = quantize(value)
        if hasattr(value, "value"):
            value = value.value
        setattr(loan, field, value)
    if loan.scheduled_payment is not None and loan.scheduled_payment <= ZERO:
        raise ValidationError("A scheduled payment must be greater than zero.")
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Another loan already uses that name.") from exc
    return loan


def delete_loan(db: Session, user_id: uuid.UUID, loan_id: uuid.UUID) -> None:
    loan = get_loan(db, user_id, loan_id)
    db.delete(loan)
    db.flush()


def list_payments(db: Session, user_id: uuid.UUID, loan_id: uuid.UUID) -> list[dict[str, object]]:
    from app.models import Transaction

    get_loan(db, user_id, loan_id)
    rows = list(
        db.scalars(
            select(LoanPayment)
            .where(LoanPayment.user_id == user_id, LoanPayment.loan_id == loan_id)
            .order_by(LoanPayment.paid_on.desc(), LoanPayment.created_at.desc())
        )
    )
    out: list[dict[str, object]] = []
    for payment in rows:
        txn = db.get(Transaction, payment.transaction_id) if payment.transaction_id else None
        out.append(
            {
                "id": payment.id,
                "loan_id": payment.loan_id,
                "transaction_id": payment.transaction_id,
                "amount": payment.amount,
                "principal_amount": payment.principal_amount,
                "interest_amount": payment.interest_amount,
                "fee_amount": payment.fee_amount,
                "paid_on": payment.paid_on,
                "status": payment.status,
                "confidence": payment.confidence,
                "is_automatic": payment.is_automatic,
                "is_ambiguous": payment.is_ambiguous,
                "reason": payment.reason,
                "notes": payment.notes,
                "created_at": payment.created_at,
                "transaction_description": txn.description if txn else None,
                "transaction_merchant": txn.merchant if txn else None,
            }
        )
    return out


def _validate_split(payload: LoanPaymentCreate | LoanPaymentUpdate) -> None:
    parts = [
        value
        for value in (
            getattr(payload, "principal_amount", None),
            getattr(payload, "interest_amount", None),
            getattr(payload, "fee_amount", None),
        )
        if value is not None
    ]
    amount = getattr(payload, "amount", None)
    if parts and amount is not None and sum(parts) > amount:
        raise ValidationError("Principal, interest and fees cannot exceed the payment amount.")


def add_payment(
    db: Session, user: User, loan_id: uuid.UUID, payload: LoanPaymentCreate
) -> LoanPayment:
    loan = get_loan(db, user.id, loan_id)
    _validate_split(payload)
    txn = None
    if payload.transaction_id is not None:
        from app.models import Transaction

        txn = db.scalar(
            select(Transaction).where(
                Transaction.id == payload.transaction_id, Transaction.user_id == user.id
            )
        )
        if txn is None:
            raise ValidationError("The selected transaction does not exist.")
        if txn.tx_type not in (
            TransactionType.PURCHASE.value,
            TransactionType.BILL_PAYMENT.value,
        ):
            raise ValidationError("Only a debit transaction can repay a loan.")
        already = db.scalar(
            select(LoanPayment.id).where(LoanPayment.transaction_id == txn.id)
        )
        if already is not None:
            raise ConflictError("That transaction is already linked to a repayment.")
    payment = LoanPayment(
        user_id=user.id,
        loan_id=loan.id,
        transaction_id=payload.transaction_id,
        amount=quantize(payload.amount),
        principal_amount=quantize(payload.principal_amount) if payload.principal_amount is not None else None,
        interest_amount=quantize(payload.interest_amount) if payload.interest_amount is not None else None,
        fee_amount=quantize(payload.fee_amount) if payload.fee_amount is not None else None,
        paid_on=payload.paid_on or (txn.txn_date if txn else today_in(user.timezone)),
        status=MatchStatus.CONFIRMED.value if payload.confirm else MatchStatus.SUGGESTED.value,
        confidence=Decimal("1.000") if payload.confirm else Decimal("0.500"),
        is_automatic=False,
        reason="Recorded by hand" if payload.confirm else "Suggested by hand",
        confirmed_at=None,
        notes=payload.notes,
    )
    if payload.confirm:
        from app.utils.dates import utc_now

        payment.confirmed_at = utc_now()
    db.add(payment)
    db.flush()
    _settle_status(db, loan)
    return payment


def update_payment(
    db: Session,
    user: User,
    loan_id: uuid.UUID,
    payment_id: uuid.UUID,
    payload: LoanPaymentUpdate,
) -> LoanPayment:
    loan = get_loan(db, user.id, loan_id)
    payment = db.scalar(
        select(LoanPayment).where(
            LoanPayment.id == payment_id,
            LoanPayment.loan_id == loan.id,
            LoanPayment.user_id == user.id,
        )
    )
    if payment is None:
        raise NotFoundError("Repayment not found.")
    _validate_split(payload)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if isinstance(value, Decimal):
            value = quantize(value)
        setattr(payment, field, value)
    parts = [payment.principal_amount, payment.interest_amount, payment.fee_amount]
    if any(part is not None for part in parts) and sum(
        quantize(part or ZERO) for part in parts
    ) > payment.amount:
        raise ValidationError("Principal, interest and fees cannot exceed the payment amount.")
    db.flush()
    _settle_status(db, loan)
    return payment


def set_payment_status(
    db: Session, user: User, loan_id: uuid.UUID, payment_id: uuid.UUID, status: MatchStatus
) -> LoanPayment:
    loan = get_loan(db, user.id, loan_id)
    payment = db.scalar(
        select(LoanPayment).where(
            LoanPayment.id == payment_id,
            LoanPayment.loan_id == loan.id,
            LoanPayment.user_id == user.id,
        )
    )
    if payment is None:
        raise NotFoundError("Repayment not found.")
    payment.status = status.value
    if status == MatchStatus.CONFIRMED:
        from app.utils.dates import utc_now

        payment.confirmed_at = utc_now()
    db.flush()
    _settle_status(db, loan)
    return payment


def delete_payment(db: Session, user: User, loan_id: uuid.UUID, payment_id: uuid.UUID) -> None:
    loan = get_loan(db, user.id, loan_id)
    payment = db.scalar(
        select(LoanPayment).where(
            LoanPayment.id == payment_id,
            LoanPayment.loan_id == loan.id,
            LoanPayment.user_id == user.id,
        )
    )
    if payment is None:
        raise NotFoundError("Repayment not found.")
    db.delete(payment)
    db.flush()
    _settle_status(db, loan)


def _settle_status(db: Session, loan: Loan) -> None:
    """Mark a fully repaid loan paid off, and reopen one that was over-credited.

    Only a confirmed repayment can settle a loan: a suggestion the user has not
    agreed to must not change the balance or the status.
    """
    db.refresh(loan)
    if not _confirmed_payments(loan):
        db.flush()
        return
    balance = loan_numbers(loan)["current_balance"]
    if loan.status == LoanStatus.ACTIVE.value and balance == ZERO:
        loan.status = LoanStatus.PAID_OFF.value
    elif loan.status == LoanStatus.PAID_OFF.value and balance > ZERO:
        loan.status = LoanStatus.ACTIVE.value
    db.flush()


def summary(db: Session, user_id: uuid.UUID) -> dict[str, object]:
    loans = [loan_payload(loan) for loan in list_loans(db, user_id)]
    active = [row for row in loans if row["status"] == LoanStatus.ACTIVE.value]
    upcoming = [row for row in active if row["next_payment_date"] is not None]
    next_date = min((row["next_payment_date"] for row in upcoming), default=None)
    next_total = quantize(
        sum(
            (
                quantize(row["scheduled_payment"] or ZERO)
                for row in upcoming
                if row["next_payment_date"] == next_date
            ),
            ZERO,
        )
    )
    return {
        "total_outstanding": quantize(sum((row["current_balance"] for row in active), ZERO)),
        "total_original": quantize(sum((row["original_amount"] for row in loans), ZERO)),
        "active_loans": len(active),
        "next_payment_date": next_date,
        "next_payment_total": next_total,
        "loans": loans,
    }


# ---------------------------------------------------------------- obligations
def upcoming_payments(
    db: Session, user: User, *, today: date, horizon_end: date
) -> list[dict[str, object]]:
    """Repayments falling due inside the planning horizon.

    A repayment already covered by a recorded transaction is skipped: that cash is
    either in the posted balance or counted as a pending debit, and reserving it
    again would count the same money twice.
    """
    out: list[dict[str, object]] = []
    for loan in list_loans(db, user.id):
        if loan.status != LoanStatus.ACTIVE.value:
            continue
        if loan.next_payment_date is None or loan.scheduled_payment is None:
            continue
        numbers = loan_numbers(loan)
        balance = numbers["current_balance"]
        if balance <= ZERO:
            continue
        due = loan.next_payment_date
        if due > horizon_end:
            continue
        # Repayments recorded around this due date have already left the account,
        # so only the unpaid remainder is still an obligation. Summing (rather
        # than treating any single payment as settling the cycle) is what makes a
        # partial payment reserve the rest instead of cancelling it.
        paid_towards_due = quantize(
            sum(
                (
                    quantize(payment.amount)
                    for payment in loan.payments
                    if payment.status == MatchStatus.CONFIRMED.value
                    and abs((payment.paid_on - due).days) <= 10
                ),
                ZERO,
            )
        )
        amount = min(quantize(loan.scheduled_payment) - paid_towards_due, balance)
        if amount <= ZERO:
            continue
        out.append(
            {
                "loan_id": loan.id,
                "loan_name": loan.name,
                "lender": loan.lender,
                "due_date": due,
                "amount": amount,
                "is_overdue": due < today,
                "is_estimate": bool(numbers["balance_is_estimate"])
                or loan.payment_frequency is None,
                "remaining_balance": balance,
                "covered_by_transaction": False,
                "category_id": loan.category_id,
                "account_id": loan.account_id,
            }
        )
    return out
