"""Bill-to-transaction matching orchestration (deterministic; no AI)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.matching.engine import (
    MatchConfig,
    OccurrenceCandidate,
    TransactionCandidate,
    decide,
)
from app.models import (
    Bill,
    BillOccurrence,
    BillPaymentMatch,
    MerchantAlias,
    Transaction,
    User,
    UserPreference,
)
from app.models.enums import MatchStatus, OccurrenceStatus, TransactionType
from app.services.bills import ensure_bill_occurrences, recompute_occurrence
from app.services.errors import ConflictError, NotFoundError
from app.utils.dates import today_in, utc_now
from app.utils.money import ZERO, quantize

MATCHABLE_TYPES = {TransactionType.PURCHASE.value, TransactionType.BILL_PAYMENT.value}


def get_match_config(db: Session, user_id: uuid.UUID) -> MatchConfig:
    prefs = db.get(UserPreference, user_id)
    if prefs is None:
        return MatchConfig()
    return MatchConfig(
        window_before_days=prefs.match_window_before_days,
        window_after_days=prefs.match_window_after_days,
        tolerance_amount=prefs.match_tolerance_amount,
        tolerance_percent=prefs.match_tolerance_percent,
        auto_threshold=prefs.auto_match_threshold,
        suggestion_threshold=prefs.suggestion_threshold,
        auto_matching_enabled=prefs.auto_bill_matching,
    )


def _alias_map(db: Session, user_id: uuid.UUID) -> dict[str, tuple[str, ...]]:
    rows = list(
        db.scalars(select(MerchantAlias).where(MerchantAlias.user_id == user_id))
    )
    mapping: dict[str, list[str]] = {}
    for row in rows:
        mapping.setdefault(row.canonical_merchant.lower(), []).append(row.alias)
    return {key: tuple(values) for key, values in mapping.items()}


def _candidates(
    db: Session,
    user: User,
    txn: Transaction,
    config: MatchConfig,
) -> list[OccurrenceCandidate]:
    window_start = txn.txn_date - timedelta(days=config.window_after_days)
    window_end = txn.txn_date + timedelta(days=config.window_before_days)
    bills = list(
        db.scalars(
            select(Bill)
            .where(Bill.user_id == user.id, Bill.is_active.is_(True))
            .options(selectinload(Bill.occurrences))
        )
    )
    for bill in bills:
        ensure_bill_occurrences(db, bill, window_end)
    db.expire_all()

    occurrences = list(
        db.scalars(
            select(BillOccurrence)
            .join(Bill, Bill.id == BillOccurrence.bill_id)
            .where(
                BillOccurrence.user_id == user.id,
                Bill.is_active.is_(True),
                BillOccurrence.status.in_(
                    [OccurrenceStatus.UPCOMING.value, OccurrenceStatus.PARTIAL.value]
                ),
                BillOccurrence.due_date >= window_start,
                BillOccurrence.due_date <= window_end,
            )
            .options(selectinload(BillOccurrence.bill))
        )
    )
    aliases = _alias_map(db, user.id)
    candidates: list[OccurrenceCandidate] = []
    for occurrence in occurrences:
        if occurrence.remaining_amount <= ZERO:
            continue
        bill = occurrence.bill
        if bill is None:
            continue
        canonical = (bill.merchant or bill.name).lower()
        candidates.append(
            OccurrenceCandidate(
                occurrence_id=occurrence.id,
                bill_id=bill.id,
                bill_name=bill.name,
                merchant=bill.merchant,
                expected_amount=occurrence.expected_amount,
                paid_amount=occurrence.paid_amount,
                due_date=occurrence.due_date,
                account_id=bill.account_id,
                aliases=aliases.get(canonical, ()),
            )
        )
    return candidates


def _existing_confirmed(db: Session, txn_id: uuid.UUID) -> BillPaymentMatch | None:
    return db.scalar(
        select(BillPaymentMatch).where(
            BillPaymentMatch.transaction_id == txn_id,
            BillPaymentMatch.status == MatchStatus.CONFIRMED.value,
        )
    )


def match_transaction(db: Session, user: User, txn: Transaction) -> dict[str, object] | None:
    """Inspect outstanding bills for a new/changed transaction. Idempotent."""
    if txn.tx_type not in MATCHABLE_TYPES:
        return None
    if _existing_confirmed(db, txn.id) is not None:
        return None
    if txn.amount <= ZERO:
        return None

    config = get_match_config(db, user.id)
    occurrences = _candidates(db, user, txn, config)
    if not occurrences:
        return None

    candidate_tx = TransactionCandidate(
        transaction_id=txn.id,
        merchant=txn.merchant or txn.description,
        description=txn.description,
        amount=txn.amount,
        txn_date=txn.txn_date,
        account_id=txn.account_id,
    )
    decision = decide(candidate_tx, occurrences, config)

    if decision.outcome == "none":
        return {"outcome": "none", "reason": decision.reason, "candidates": []}

    created: list[dict[str, object]] = []
    for scored in decision.scored:
        existing = db.scalar(
            select(BillPaymentMatch).where(
                BillPaymentMatch.transaction_id == txn.id,
                BillPaymentMatch.occurrence_id == scored.candidate.occurrence_id,
            )
        )
        if existing is not None:
            if existing.status == MatchStatus.CONFIRMED.value:
                continue
            existing.confidence = scored.score
            existing.is_ambiguous = decision.ambiguous
            existing.reason = decision.reason
            match = existing
        else:
            match = BillPaymentMatch(
                user_id=user.id,
                occurrence_id=scored.candidate.occurrence_id,
                transaction_id=txn.id,
                amount=min(txn.amount, scored.candidate.remaining),
                confidence=scored.score,
                status=MatchStatus.SUGGESTED.value,
                is_automatic=False,
                is_ambiguous=decision.ambiguous,
                reason=decision.reason,
            )
            db.add(match)
        db.flush()
        created.append(
            {
                "match_id": str(match.id),
                "occurrence_id": str(scored.candidate.occurrence_id),
                "bill_name": scored.candidate.bill_name,
                "due_date": scored.candidate.due_date.isoformat(),
                "confidence": f"{scored.score:.3f}",
                "is_ambiguous": decision.ambiguous,
                "signals": {
                    "merchant": f"{scored.merchant_score:.3f}",
                    "amount": f"{scored.amount_score:.3f}",
                    "date": f"{scored.date_score:.3f}",
                    "account": f"{scored.account_score:.3f}",
                },
            }
        )

    if decision.outcome == "auto" and created:
        match = db.get(BillPaymentMatch, uuid.UUID(str(created[0]["match_id"])))
        assert match is not None
        _confirm(db, user, match, automatic=True)
        return {
            "outcome": "auto",
            "matched": True,
            "match_id": str(match.id),
            "bill_name": created[0]["bill_name"],
            "confidence": created[0]["confidence"],
            "reason": decision.reason,
            "suggestions": [],
        }

    return {
        "outcome": "suggest",
        "matched": False,
        "ambiguous": decision.ambiguous,
        "reason": decision.reason,
        "suggestions": created,
    }


def _confirm(
    db: Session, user: User, match: BillPaymentMatch, *, automatic: bool
) -> BillPaymentMatch:
    occurrence = db.get(BillOccurrence, match.occurrence_id)
    txn = db.get(Transaction, match.transaction_id)
    if occurrence is None or txn is None:
        raise NotFoundError("The bill occurrence or transaction no longer exists.")

    other = _existing_confirmed(db, txn.id)
    if other is not None and other.id != match.id:
        raise ConflictError("This transaction is already linked to another bill payment.")
    if occurrence.remaining_amount <= ZERO:
        raise ConflictError("This bill occurrence is already fully paid.")

    amount = quantize(min(txn.amount, occurrence.remaining_amount))
    match.amount = amount
    match.status = MatchStatus.CONFIRMED.value
    match.confirmed_at = utc_now()
    match.is_automatic = automatic
    match.is_ambiguous = False
    match.reason = ("Automatically matched: " if automatic else "Confirmed: ") + (match.reason or "")
    db.query(BillPaymentMatch).filter(
        BillPaymentMatch.transaction_id == txn.id,
        BillPaymentMatch.id != match.id,
        BillPaymentMatch.status == MatchStatus.SUGGESTED.value,
    ).update({BillPaymentMatch.status: MatchStatus.REJECTED.value}, synchronize_session=False)
    db.flush()
    recompute_occurrence(db, occurrence)
    return match


def confirm_match(
    db: Session, user: User, match_id: uuid.UUID, *, amount: Decimal | None = None
) -> BillPaymentMatch:
    match = db.scalar(
        select(BillPaymentMatch).where(
            BillPaymentMatch.id == match_id, BillPaymentMatch.user_id == user.id
        )
    )
    if match is None:
        raise NotFoundError("Match suggestion not found.")
    if match.status == MatchStatus.CONFIRMED.value:
        return match
    if match.status == MatchStatus.REJECTED.value:
        raise ConflictError("This suggestion was rejected. Re-run matching to reconsider it.")
    if amount is not None:
        match.amount = quantize(amount)
    return _confirm(db, user, match, automatic=False)


def reject_match(db: Session, user: User, match_id: uuid.UUID) -> BillPaymentMatch:
    match = db.scalar(
        select(BillPaymentMatch).where(
            BillPaymentMatch.id == match_id, BillPaymentMatch.user_id == user.id
        )
    )
    if match is None:
        raise NotFoundError("Match not found.")
    was_confirmed = match.status == MatchStatus.CONFIRMED.value
    match.status = MatchStatus.REJECTED.value
    match.confirmed_at = None
    db.flush()
    if was_confirmed:
        occurrence = db.get(BillOccurrence, match.occurrence_id)
        if occurrence is not None:
            recompute_occurrence(db, occurrence)
    return match


def link_transaction(
    db: Session,
    user: User,
    occurrence_id: uuid.UUID,
    transaction_id: uuid.UUID,
    *,
    confidence: Decimal = Decimal("1.000"),
    confirm: bool = True,
) -> BillPaymentMatch:
    occurrence = db.scalar(
        select(BillOccurrence).where(
            BillOccurrence.id == occurrence_id, BillOccurrence.user_id == user.id
        )
    )
    txn = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == user.id
        )
    )
    if occurrence is None or txn is None:
        raise NotFoundError("Bill occurrence or transaction not found.")
    if txn.tx_type not in MATCHABLE_TYPES:
        raise ConflictError("Only purchases and bill payments can pay a bill.")
    if txn.amount <= ZERO:
        raise ConflictError("The transaction has no positive amount to apply.")
    if occurrence.remaining_amount <= ZERO:
        raise ConflictError("This occurrence is already fully paid.")

    existing = db.scalar(
        select(BillPaymentMatch).where(
            BillPaymentMatch.transaction_id == txn.id,
            BillPaymentMatch.occurrence_id == occurrence.id,
        )
    )
    if existing is None:
        existing = BillPaymentMatch(
            user_id=user.id,
            occurrence_id=occurrence.id,
            transaction_id=txn.id,
            amount=quantize(min(txn.amount, occurrence.remaining_amount)),
            confidence=confidence,
            status=MatchStatus.SUGGESTED.value,
            is_automatic=False,
            is_ambiguous=False,
            reason="Linked manually",
        )
        db.add(existing)
        db.flush()
    if confirm:
        return _confirm(db, user, existing, automatic=False)
    return existing


def match_summaries(db: Session, user: User) -> dict[str, object]:
    rows = list(
        db.scalars(
            select(BillPaymentMatch)
            .options(
                selectinload(BillPaymentMatch.occurrence).selectinload(BillOccurrence.bill),
                selectinload(BillPaymentMatch.transaction),
            )
            .where(
                BillPaymentMatch.user_id == user.id,
                BillPaymentMatch.status == MatchStatus.SUGGESTED.value,
            )
            .order_by(BillPaymentMatch.created_at.desc())
        )
    )
    grouped: dict[uuid.UUID, list[BillPaymentMatch]] = {}
    for row in rows:
        grouped.setdefault(row.transaction_id, []).append(row)
    return {"count": len(rows), "transactions": len(grouped)}


def suggestions(db: Session, user: User) -> list[dict[str, object]]:
    rows = list(
        db.scalars(
            select(BillPaymentMatch)
            .options(
                selectinload(BillPaymentMatch.occurrence).selectinload(BillOccurrence.bill),
                selectinload(BillPaymentMatch.transaction),
            )
            .where(
                BillPaymentMatch.user_id == user.id,
                BillPaymentMatch.status == MatchStatus.SUGGESTED.value,
            )
            .order_by(BillPaymentMatch.created_at.desc())
        )
    )
    grouped: dict[uuid.UUID, list[BillPaymentMatch]] = {}
    for row in rows:
        grouped.setdefault(row.transaction_id, []).append(row)
    output: list[dict[str, object]] = []
    for txn_id, matches in grouped.items():
        txn = matches[0].transaction
        if txn is None:
            continue
        output.append(
            {
                "transaction_id": str(txn.id),
                "transaction_description": txn.description,
                "transaction_merchant": txn.merchant,
                "transaction_amount": str(quantize(txn.amount)),
                "transaction_date": txn.txn_date.isoformat(),
                "account_id": str(txn.account_id),
                "candidates": [
                    {
                        "match_id": str(m.id),
                        "occurrence_id": str(m.occurrence_id),
                        "bill_name": m.occurrence.bill.name if m.occurrence.bill else None,
                        "due_date": m.occurrence.due_date.isoformat(),
                        "remaining": str(m.occurrence.remaining_amount),
                        "amount": str(quantize(m.amount)),
                        "confidence": f"{m.confidence:.3f}",
                        "is_ambiguous": m.is_ambiguous,
                        "reason": m.reason,
                    }
                    for m in matches
                ],
            }
        )
    return output


def stale_suggestions(db: Session, user: User, today: date) -> int:
    rows = db.scalars(
        select(BillPaymentMatch)
        .join(Transaction, Transaction.id == BillPaymentMatch.transaction_id)
        .where(
            BillPaymentMatch.user_id == user.id,
            BillPaymentMatch.status == MatchStatus.SUGGESTED.value,
            Transaction.txn_date < today - timedelta(days=45),
        )
    ).all()
    return len(list(rows))


def current_day(user: User) -> date:
    return today_in(user.timezone)
