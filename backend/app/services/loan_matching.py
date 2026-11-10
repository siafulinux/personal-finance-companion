"""Match bank transactions to loan repayments, with an explicit confidence score.

The score is a transparent weighted sum, not a model:

* amount closeness (0.50) - a repayment is normally the scheduled figure
* lender/loan name appearing in the description (0.25)
* date proximity to the next due date (0.25)

Automatic linking happens only when the best candidate clears the user's
``auto_match_threshold`` *and* there is no close runner-up. Everything else is a
suggestion the user confirms or rejects, mirroring bill matching so the two
surfaces behave the same way.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.normalize import normalize_merchant
from app.models import BillPaymentMatch, Loan, LoanPayment, Transaction, User, UserPreference
from app.models.enums import MatchStatus, TransactionStatus, TransactionType
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.loans import get_loan, loan_numbers
from app.utils.money import ZERO, quantize

SEARCH_BEFORE_DAYS = 14
SEARCH_AFTER_DAYS = 7
AMBIGUITY_MARGIN = Decimal("0.08")


def _amount_score(expected: Decimal, actual: Decimal) -> Decimal:
    if expected <= ZERO or actual <= ZERO:
        return ZERO
    difference = abs(expected - actual)
    ratio = difference / max(expected, actual)
    return quantize(max(ZERO, Decimal("1") - ratio))


def _name_score(loan: Loan, txn: Transaction) -> Decimal:
    haystack = normalize_merchant(
        " ".join(filter(None, [txn.merchant, txn.description]))
    )
    if not haystack:
        return ZERO
    needles = [
        normalize_merchant(value)
        for value in (loan.lender, loan.name)
        if value and normalize_merchant(value)
    ]
    for needle in needles:
        if needle and needle in haystack:
            return Decimal("1")
    # A single shared significant word is weaker evidence, not none.
    words = {w for needle in needles for w in needle.split() if len(w) >= 5}
    if any(word in haystack for word in words):
        return Decimal("0.6")
    return ZERO


def _date_score(due: date | None, txn_date: date) -> Decimal:
    if due is None:
        return Decimal("0.5")
    distance = abs((txn_date - due).days)
    if distance > SEARCH_BEFORE_DAYS:
        return ZERO
    return quantize(Decimal("1") - (Decimal(distance) / Decimal(SEARCH_BEFORE_DAYS)))


def _prefs(db: Session, user_id: uuid.UUID) -> UserPreference | None:
    return db.get(UserPreference, user_id)


def _candidates(db: Session, user: User, loan: Loan, around: date | None = None) -> list[Transaction]:
    anchor = around or loan.next_payment_date
    if anchor is None:
        window_start = date.min
        window_end = date.max
    else:
        window_start = anchor - timedelta(days=SEARCH_BEFORE_DAYS)
        window_end = anchor + timedelta(days=SEARCH_AFTER_DAYS)
    linked = select(LoanPayment.transaction_id).where(
        LoanPayment.user_id == user.id, LoanPayment.transaction_id.is_not(None)
    )
    query = select(Transaction).where(
        Transaction.user_id == user.id,
        Transaction.tx_type.in_(
            [TransactionType.PURCHASE.value, TransactionType.BILL_PAYMENT.value]
        ),
        Transaction.id.not_in(linked),
    )
    if anchor is not None:
        query = query.where(Transaction.txn_date >= window_start, Transaction.txn_date <= window_end)
    if loan.account_id is not None:
        query = query.where(Transaction.account_id == loan.account_id)
    return list(db.scalars(query.order_by(Transaction.txn_date.desc()).limit(200)))


def score_candidate(loan: Loan, txn: Transaction) -> Decimal:
    expected = quantize(loan.scheduled_payment) if loan.scheduled_payment else ZERO
    if expected <= ZERO:
        # Without a schedule the amount carries no information, so the remaining
        # evidence has to stand on its own.
        amount = Decimal("0.5")
    else:
        amount = _amount_score(expected, quantize(txn.amount))
    score = (
        Decimal("0.50") * amount
        + Decimal("0.25") * _name_score(loan, txn)
        + Decimal("0.25") * _date_score(loan.next_payment_date, txn.txn_date)
    )
    return quantize(min(score, Decimal("1")))


def score_loan_for_transaction(loan: Loan, txn: Transaction) -> Decimal:
    """Score a transaction against a loan whose next date may be stale.

    A repayment can arrive at any time; when the stored next date is far from the
    transaction the date component is neutralised rather than penalised, so the
    amount and lender still decide.
    """
    expected = quantize(loan.scheduled_payment) if loan.scheduled_payment else ZERO
    amount = (
        _amount_score(expected, quantize(txn.amount)) if expected > ZERO else Decimal("0.5")
    )
    name = _name_score(loan, txn)
    if loan.next_payment_date is None or abs((txn.txn_date - loan.next_payment_date).days) > SEARCH_BEFORE_DAYS:
        date_part = Decimal("0.5")
    else:
        date_part = _date_score(loan.next_payment_date, txn.txn_date)
    return quantize(
        min(Decimal("0.50") * amount + Decimal("0.25") * name + Decimal("0.25") * date_part, Decimal("1"))
    )


def suggestions_for_loan(db: Session, user: User, loan_id: uuid.UUID) -> list[dict[str, object]]:
    loan = get_loan(db, user.id, loan_id)
    prefs = _prefs(db, user.id)
    threshold = quantize(prefs.suggestion_threshold) if prefs else Decimal("0.55")
    rows: list[dict[str, object]] = []
    scored = [(txn, score_candidate(loan, txn)) for txn in _candidates(db, user, loan)]
    scored = [(txn, score) for txn, score in scored if score >= threshold]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    for index, (txn, score) in enumerate(scored):
        runner_up = scored[index + 1][1] if index + 1 < len(scored) else ZERO
        rows.append(
            {
                "transaction_id": txn.id,
                "description": txn.description,
                "merchant": txn.merchant,
                "amount": txn.amount,
                "txn_date": txn.txn_date,
                "account_id": txn.account_id,
                "confidence": score,
                "reason": (
                    f"Amount and date match the {loan.name} schedule"
                    if score >= Decimal("0.8")
                    else "Amount and date are close to the loan schedule"
                ),
                "is_ambiguous": (score - runner_up) < AMBIGUITY_MARGIN,
            }
        )
    return rows


def link_transaction(
    db: Session,
    user: User,
    loan_id: uuid.UUID,
    transaction_id: uuid.UUID,
    *,
    confirm: bool = True,
    reason: str = "Matched by the user",
    confidence: Decimal | None = None,
    is_automatic: bool = False,
) -> LoanPayment:
    loan = get_loan(db, user.id, loan_id)
    txn = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == user.id
        )
    )
    if txn is None:
        raise ValidationError("The selected transaction does not exist.")
    if txn.tx_type not in (TransactionType.PURCHASE.value, TransactionType.BILL_PAYMENT.value):
        raise ValidationError("Only a debit transaction can repay a loan.")
    existing = db.scalar(select(LoanPayment).where(LoanPayment.transaction_id == txn.id))
    if existing is not None:
        raise ConflictError("That transaction is already linked to a repayment.")

    payment = LoanPayment(
        user_id=user.id,
        loan_id=loan.id,
        transaction_id=txn.id,
        amount=quantize(txn.amount),
        principal_amount=None,
        paid_on=txn.txn_date,
        status=MatchStatus.CONFIRMED.value if confirm else MatchStatus.SUGGESTED.value,
        confidence=quantize(confidence) if confidence is not None else score_candidate(loan, txn),
        is_automatic=is_automatic,
        is_ambiguous=False,
        reason=reason,
        notes=None,
    )
    if confirm:
        from app.utils.dates import utc_now

        payment.confirmed_at = utc_now()
    db.add(payment)
    db.flush()
    if confirm:
        from app.services.loans import _settle_status

        _settle_status(db, loan)
    return payment


def auto_match_transaction(db: Session, user: User, txn: Transaction) -> LoanPayment | None:
    """Attach a transaction to a loan when the evidence is strong and unique.

    A transaction already matched to a bill is left alone: the bill owns it, and
    claiming it twice would make one payment settle two obligations.
    """
    if txn.tx_type not in (TransactionType.PURCHASE.value, TransactionType.BILL_PAYMENT.value):
        return None
    prefs = _prefs(db, user.id)
    if prefs is not None and not prefs.auto_bill_matching:
        return None
    if db.scalar(
        select(BillPaymentMatch.id).where(
            BillPaymentMatch.transaction_id == txn.id,
            BillPaymentMatch.status == MatchStatus.CONFIRMED.value,
        )
    ):
        return None
    if db.scalar(select(LoanPayment.id).where(LoanPayment.transaction_id == txn.id)):
        return None

    threshold = quantize(prefs.auto_match_threshold) if prefs else Decimal("0.85")
    scored: list[tuple[Loan, Decimal]] = []
    for loan in db.scalars(
        select(Loan).where(
            Loan.user_id == user.id, Loan.status.in_(["active", "defaulted"])
        )
    ):
        numbers = loan_numbers(loan)
        if numbers["current_balance"] <= ZERO:
            continue
        score = score_loan_for_transaction(loan, txn)
        if score >= threshold:
            scored.append((loan, score))
    if len(scored) != 1:
        # Two plausible loans is exactly the ambiguous case the user must decide.
        return None
    loan, score = scored[0]
    return link_transaction(
        db,
        user,
        loan.id,
        txn.id,
        confirm=True,
        reason="Matched automatically from amount and date",
        confidence=score,
        is_automatic=True,
    )


def remove_suggestion(db: Session, user: User, payment_id: uuid.UUID) -> None:
    payment = db.scalar(
        select(LoanPayment).where(LoanPayment.id == payment_id, LoanPayment.user_id == user.id)
    )
    if payment is None:
        raise NotFoundError("Repayment not found.")
    db.delete(payment)
    db.flush()
