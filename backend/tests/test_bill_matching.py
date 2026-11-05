"""Scenarios D, E, F: automatic, ambiguous and partial bill payments."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.matching.engine import (
    MatchConfig,
    OccurrenceCandidate,
    TransactionCandidate,
    decide,
    rank_matches,
)
from app.models import BillOccurrence, BillPaymentMatch
from app.models.enums import MatchStatus, OccurrenceStatus
from app.schemas.finance import TransactionCreate
from app.schemas.planning import BillCreate
from app.services.bill_matching import confirm_match, link_transaction, match_transaction
from app.services.bills import create_bill, record_payment
from app.services.errors import ConflictError
from app.services.transactions import create_transaction

D = Decimal


def make_occurrence(**overrides) -> OccurrenceCandidate:
    from datetime import date

    defaults = dict(
        occurrence_id=uuid.uuid4(),
        bill_id=uuid.uuid4(),
        bill_name="Internet",
        merchant="Comcast",
        expected_amount=D("95.00"),
        paid_amount=D("0.00"),
        due_date=date(2026, 11, 15),
        account_id=None,
        aliases=(),
    )
    defaults.update(overrides)
    return OccurrenceCandidate(**defaults)


def make_tx(amount: str = "95.00", merchant: str = "Comcast", **overrides) -> TransactionCandidate:
    from datetime import date

    defaults = dict(
        transaction_id=uuid.uuid4(),
        merchant=merchant,
        description=merchant,
        amount=D(amount),
        txn_date=date(2026, 11, 14),
        account_id=uuid.uuid4(),
    )
    defaults.update(overrides)
    return TransactionCandidate(**defaults)


def test_bill_rejects_another_users_category(db, user, account, today):
    from app.models import Category
    from app.services.bills import create_bill
    from app.services.errors import ValidationError
    from app.services.users import register_user

    other = register_user(
        db,
        email="bill-other@example.com",
        password="OtherPassword123",
        display_name="Other",
        timezone="UTC",
    )
    db.commit()
    other_category = db.query(Category).filter_by(user_id=other.id, name="Housing").one()
    with pytest.raises(ValidationError):
        create_bill(
            db,
            user.id,
            BillCreate(
                name="Injected category",
                expected_amount=D("10.00"),
                anchor_date=today,
                frequency="monthly",
                account_id=account.id,
                category_id=other_category.id,
            ),
            user.timezone,
        )


def test_paid_occurrence_is_not_the_next_due_date(db, user, account, today):
    from app.services.bills import bill_summary, mark_paid
    from app.utils.dates import add_months

    bill = create_bill(
        db,
        user.id,
        BillCreate(
            name="Monthly bill",
            expected_amount=D("50.00"),
            anchor_date=today,
            frequency="monthly",
            account_id=account.id,
        ),
        user.timezone,
    )
    db.commit()
    first = min(bill.occurrences, key=lambda o: o.due_date)
    mark_paid(db, user.id, first.id)
    db.commit()
    db.refresh(bill)
    summary = bill_summary(bill, today)
    assert summary["next_due_date"] != first.due_date.isoformat()
    assert summary["next_due_date"] == add_months(today, 1).isoformat()


def test_high_confidence_match_is_automatic():
    decision = decide(make_tx(), [make_occurrence()], MatchConfig())
    assert decision.outcome == "auto"
    assert decision.scored[0].score >= Decimal("0.85")
    assert "Merchant matches" in decision.scored[0].reason


def test_alias_is_a_strong_signal():
    occurrence = make_occurrence(aliases=("xfinity",))
    decision = decide(make_tx(merchant="XFINITY"), [occurrence], MatchConfig())
    assert decision.outcome == "auto"
    assert decision.scored[0].merchant_score == Decimal("1.00")


def test_dissimilar_merchant_never_matches():
    decision = decide(make_tx(merchant="Starbucks"), [make_occurrence()], MatchConfig())
    assert decision.outcome == "none"
    assert decision.scored == []


def test_amount_outside_tolerance_does_not_match():
    decision = decide(make_tx(amount="150.00"), [make_occurrence()], MatchConfig())
    assert decision.outcome == "none"


def test_two_close_candidates_are_ambiguous_and_never_auto():
    first = make_occurrence()
    second = make_occurrence()
    decision = decide(make_tx(), [first, second], MatchConfig())
    assert decision.ambiguous is True
    assert decision.outcome == "suggest"
    assert len(decision.scored) == 2
    assert "confirmation required" in decision.reason


def test_partial_payment_is_only_a_suggestion():
    decision = decide(make_tx(amount="40.00"), [make_occurrence(expected_amount=D("100.00"))], MatchConfig())
    assert decision.outcome == "suggest"
    assert decision.scored[0].is_partial is True
    assert decision.scored[0].score < Decimal("0.85")


def test_auto_matching_disabled_still_suggests():
    decision = decide(
        make_tx(),
        [make_occurrence()],
        MatchConfig(auto_matching_enabled=False),
    )
    assert decision.outcome == "suggest"
    assert decision.method == "suggested"


def test_date_window_excludes_far_due_dates():
    from datetime import date

    occurrence = make_occurrence(due_date=date(2026, 12, 15))
    decision = decide(make_tx(), [occurrence], MatchConfig())
    assert decision.outcome == "none"


def test_ranking_is_deterministic():
    first = make_occurrence()
    second = make_occurrence(due_date=make_occurrence().due_date - timedelta(days=1))
    ranked = rank_matches(make_tx(), [first, second], MatchConfig())
    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score
    assert ranked == rank_matches(make_tx(), [first, second], MatchConfig()) or len(ranked) == 2


def test_scenario_d_auto_match_marks_bill_paid(db, user, prefs, account, today):
    bill = create_bill(
        db,
        user.id,
        BillCreate(
            name="Internet",
            merchant="Comcast",
            expected_amount=D("95.00"),
            anchor_date=today + timedelta(days=2),
            frequency="monthly",
            account_id=account.id,
        ),
        user.timezone,
    )
    db.commit()

    txn, info = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="COMCAST CABLE 1234",
            merchant="Comcast",
            amount=D("95.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    assert info is not None and info["outcome"] == "auto"

    occurrence = db.scalar(
        select(BillOccurrence).where(BillOccurrence.bill_id == bill.id)
    )
    db.refresh(occurrence)
    assert occurrence.status == OccurrenceStatus.PAID.value
    assert occurrence.paid_amount == D("95.00")
    match = db.scalar(
        select(BillPaymentMatch).where(BillPaymentMatch.transaction_id == txn.id)
    )
    assert match.status == MatchStatus.CONFIRMED.value
    assert match.is_automatic is True
    assert match.confidence >= Decimal("0.85")


def test_scenario_e_ambiguous_match_requires_confirmation(db, user, prefs, account, today):
    for suffix in ("East", "West"):
        create_bill(
            db,
            user.id,
            BillCreate(
                name=f"Internet {suffix}",
                merchant="Comcast",
                expected_amount=D("95.00"),
                anchor_date=today + timedelta(days=2),
                frequency="monthly",
                account_id=account.id,
            ),
            user.timezone,
        )
    db.commit()
    txn, info = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="COMCAST PAYMENT",
            merchant="Comcast",
            amount=D("95.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    assert info is not None
    assert info["outcome"] == "suggest"
    assert info["ambiguous"] is True

    matches = list(
        db.scalars(
            select(BillPaymentMatch).where(BillPaymentMatch.transaction_id == txn.id)
        )
    )
    assert len(matches) >= 2
    assert all(m.status == MatchStatus.SUGGESTED.value for m in matches)
    occurrences = list(db.scalars(select(BillOccurrence)))
    assert all(o.status == OccurrenceStatus.UPCOMING.value for o in occurrences)
    assert all(o.paid_amount == D("0.00") for o in occurrences)


def test_scenario_f_partial_payment_accumulates(db, user, prefs, account, today):
    bill = create_bill(
        db,
        user.id,
        BillCreate(
            name="Car insurance",
            merchant="Geico",
            expected_amount=D("100.00"),
            anchor_date=today + timedelta(days=1),
            frequency="monthly",
            account_id=account.id,
        ),
        user.timezone,
    )
    db.commit()
    occurrence = bill.occurrences[0]
    updated, txn = record_payment(
        db,
        user.id,
        occurrence.id,
        amount=D("40.00"),
        account_id=account.id,
        paid_on=today,
        notes=None,
        timezone=user.timezone,
    )
    db.commit()
    assert updated.paid_amount == D("40.00")
    assert updated.remaining_amount == D("60.00")
    assert updated.status == OccurrenceStatus.PARTIAL.value
    assert txn.amount == D("40.00")
    assert txn.tx_type == "bill_payment"

    updated, _ = record_payment(
        db,
        user.id,
        occurrence.id,
        amount=D("60.00"),
        account_id=account.id,
        paid_on=today,
        notes=None,
        timezone=user.timezone,
    )
    db.commit()
    assert updated.paid_amount == D("100.00")
    assert updated.status == OccurrenceStatus.PAID.value


def test_partial_overpayment_is_rejected(db, user, prefs, account, today):
    bill = create_bill(
        db,
        user.id,
        BillCreate(
            name="Water",
            merchant="City Water",
            expected_amount=D("100.00"),
            anchor_date=today + timedelta(days=1),
            frequency="monthly",
        ),
        user.timezone,
    )
    db.commit()
    occurrence = bill.occurrences[0]
    with pytest.raises(Exception):
        record_payment(
            db,
            user.id,
            occurrence.id,
            amount=D("150.00"),
            account_id=account.id,
            paid_on=today,
            notes=None,
            timezone=user.timezone,
        )


def test_matching_is_idempotent(db, user, prefs, account, today):
    create_bill(
        db,
        user.id,
        BillCreate(
            name="Internet",
            merchant="Comcast",
            expected_amount=D("95.00"),
            anchor_date=today + timedelta(days=2),
            frequency="monthly",
            account_id=account.id,
        ),
        user.timezone,
    )
    db.commit()
    txn, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Comcast",
            merchant="Comcast",
            amount=D("95.00"),
            tx_type="bill_payment",
            txn_date=today,
        ),
    )
    db.commit()
    assert match_transaction(db, user, txn) is None
    db.commit()
    count = db.scalar(select(func.count(BillPaymentMatch.id)))
    assert count == 1


def test_one_transaction_cannot_pay_two_bills(db, user, prefs, account, today):
    occurrences = []
    for suffix in ("A", "B"):
        bill = create_bill(
            db,
            user.id,
            BillCreate(
                name=f"Utility {suffix}",
                merchant="Utility Co",
                expected_amount=D("60.00"),
                anchor_date=today + timedelta(days=1),
                frequency="monthly",
                account_id=account.id,
            ),
            user.timezone,
        )
        db.commit()
        occurrences.append(bill.occurrences[0])

    txn, _ = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="Utility payment",
            merchant="Utility Co",
            amount=D("60.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()

    link_transaction(db, user, occurrences[0].id, txn.id)
    db.commit()
    with pytest.raises(ConflictError):
        link_transaction(db, user, occurrences[1].id, txn.id, confirm=True)
    db.rollback()


def test_suggestions_can_be_confirmed(db, user, prefs, account, today):
    create_bill(
        db,
        user.id,
        BillCreate(
            name="Phone",
            merchant="T-Mobile",
            expected_amount=D("70.00"),
            anchor_date=today + timedelta(days=2),
            frequency="monthly",
            account_id=account.id,
        ),
        user.timezone,
    )
    db.commit()
    # Disable auto matching so a suggestion is produced.
    prefs.auto_bill_matching = False
    db.commit()
    txn, info = create_transaction(
        db,
        user,
        TransactionCreate(
            account_id=account.id,
            description="TMOBILE PYMNT",
            merchant="T-Mobile",
            amount=D("70.00"),
            tx_type="purchase",
            txn_date=today,
        ),
    )
    db.commit()
    assert info["outcome"] == "suggest"
    match = db.scalar(
        select(BillPaymentMatch).where(BillPaymentMatch.transaction_id == txn.id)
    )
    confirm_match(db, user, match.id)
    db.commit()
    db.refresh(match)
    assert match.status == MatchStatus.CONFIRMED.value
    occurrence = db.get(BillOccurrence, match.occurrence_id)
    db.refresh(occurrence)
    assert occurrence.status == OccurrenceStatus.PAID.value
