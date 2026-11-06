"""Deterministic transaction intelligence: categorisation, recurring detection, anomalies.

Everything here is rules and statistics over the user's own data. No model, no randomness,
and every output carries the evidence that produced it so the UI can show *why*.

Category suggestions are stored, not applied. Automation never writes a category directly,
which is what keeps ``transactions.category_source = 'user'`` meaningful.
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.normalize import normalize_merchant
from app.models import Category, CategorySuggestion, RecurringSeries, Transaction, User
from app.models.enums import (
    CategorySource,
    Frequency,
    RecurringStatus,
    SuggestionSource,
    SuggestionStatus,
    TransactionStatus,
    TransactionType,
)
from app.utils.dates import today_in, utc_now
from app.utils.money import ZERO, quantize

# --------------------------------------------------------------------- rules
# Ordered: the first match wins, so specific merchants precede generic words.
MERCHANT_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("whole foods", "trader joe", "safeway", "kroger", "aldi", "publix", "grocery"), "Groceries", "Merchant is a grocery store"),
    (("starbucks", "dunkin", "coffee"), "Restaurants", "Merchant is a coffee shop"),
    (("chipotle", "mcdonald", "taco bell", "burger", "pizza", "subway", "kfc", "wendy"), "Fast food", "Merchant is a fast-food chain"),
    (("netflix", "spotify", "hulu", "disney", "hbo", "max subscription", "prime video", "youtube premium", "apple.com/bill", "icloud"), "Entertainment", "Merchant is a streaming or digital subscription"),
    (("shell", "chevron", "exxon", "mobil", "bp ", "citgo", "speedway", "fuel", "gas station"), "Fuel", "Merchant sells fuel"),
    (("uber", "lyft", "metro", "transit", "parking"), "Transportation", "Merchant is a transport service"),
    (("amazon", "target", "walmart", "best buy", "etsy", "ebay"), "Shopping", "Merchant is a general retailer"),
    (("cvs", "walgreens", "pharmacy", "clinic", "dental", "hospital"), "Medical", "Merchant is a pharmacy or clinic"),
    (("verizon", "at&t", "t-mobile", "mint mobile"), "Phone", "Merchant is a mobile carrier"),
    (("comcast", "xfinity", "spectrum", "centurylink", "internet"), "Internet", "Merchant provides internet service"),
    (("electric", "power", "energy", "utility"), "Electricity", "Merchant is an electric utility"),
    (("water district", "water bill"), "Water", "Merchant is a water utility"),
    (("rent", "apartment", "property management", "mortgage"), "Housing", "Payment is housing"),
    (("insurance", "geico", "allstate", "state farm"), "Insurance", "Payment is insurance"),
    (("gym", "fitness", "salon", "barber", "spa"), "Personal care", "Merchant is personal care or fitness"),
]

# Provider category taxonomy (Plaid ``personal_finance_category.primary``) -> category name.
PROVIDER_CATEGORY_MAP: dict[str, str] = {
    "FOOD_AND_DRINK": "Groceries",
    "GENERAL_MERCHANDISE": "Shopping",
    "ENTERTAINMENT": "Entertainment",
    "TRANSPORTATION": "Transportation",
    "TRAVEL": "Transportation",
    "RENT_AND_UTILITIES": "Housing",
    "BILLS_AND_UTILITIES": "Electricity",
    "MEDICAL": "Medical",
    "PERSONAL_CARE": "Personal care",
    "HOME_IMPROVEMENT": "Housing",
}

# A rule hit is strong but not certain; a user's own history is stronger evidence.
RULE_CONFIDENCE = Decimal("0.72")
PROVIDER_CONFIDENCE = Decimal("0.55")
HISTORY_MIN_OCCURRENCES = 3
HISTORY_BASE_CONFIDENCE = Decimal("0.60")

_CATEGORISABLE_TYPES = {
    TransactionType.PURCHASE.value,
    TransactionType.BILL_PAYMENT.value,
    TransactionType.REFUND.value,
}


@dataclass(frozen=True)
class Candidate:
    category_id: uuid.UUID
    confidence: Decimal
    source: SuggestionSource
    reason: str


def _categories_by_name(db: Session, user_id: uuid.UUID) -> dict[str, Category]:
    return {
        c.name: c
        for c in db.scalars(
            select(Category).where(
                Category.user_id == user_id, Category.is_archived.is_(False)
            )
        )
    }


def _rule_match(text: str) -> tuple[str, str] | None:
    lowered = f" {text} "
    for needles, category_name, reason in MERCHANT_RULES:
        if any(f" {needle}" in lowered for needle in needles):
            return category_name, reason
    return None


def _history_choice(
    db: Session, user_id: uuid.UUID, txn: Transaction, merchant_key: str
) -> tuple[uuid.UUID, int] | None:
    if not merchant_key:
        return None
    rows = list(
        db.execute(
            select(Transaction.category_id, Transaction.merchant, Transaction.description)
            .where(
                Transaction.user_id == user_id,
                Transaction.id != txn.id,
                Transaction.category_id.is_not(None),
                Transaction.tx_type.in_(list(_CATEGORISABLE_TYPES)),
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date >= txn.txn_date - timedelta(days=365),
            )
        )
    )
    tally: dict[uuid.UUID, int] = defaultdict(int)
    for category_id, merchant, description in rows:
        key = normalize_merchant(merchant or description)
        if key and key == merchant_key:
            tally[category_id] += 1
    if not tally:
        return None
    best_id, count = max(tally.items(), key=lambda item: (item[1], str(item[0])))
    if count < HISTORY_MIN_OCCURRENCES:
        return None
    return best_id, count


def choose_category(
    db: Session, user: User, txn: Transaction, *, provider_category: str | None = None
) -> Candidate | None:
    """Pick the best category proposal for a transaction, or None."""
    if txn.category_id is not None:
        return None
    if txn.tx_type not in _CATEGORISABLE_TYPES:
        return None

    by_name = _categories_by_name(db, user.id)
    if not by_name:
        return None
    merchant_key = normalize_merchant(txn.merchant or txn.description)

    # 1. The user's own history for this merchant beats any generic rule.
    history = _history_choice(db, user.id, txn, merchant_key)
    if history is not None:
        category_id, count = history
        confidence = min(
            Decimal("0.95"),
            HISTORY_BASE_CONFIDENCE + Decimal("0.05") * Decimal(min(count, 7)),
        )
        return Candidate(
            category_id=category_id,
            confidence=quantize(confidence),
            source=SuggestionSource.HISTORY,
            reason=f"You filed {count} earlier transactions from this merchant here",
        )

    # 2. Deterministic merchant rules.
    rule = _rule_match(merchant_key) or _rule_match((txn.merchant or txn.description).lower())
    if rule is not None:
        category_name, reason = rule
        category = by_name.get(category_name)
        if category is not None:
            return Candidate(
                category_id=category.id,
                confidence=RULE_CONFIDENCE,
                source=SuggestionSource.RULE,
                reason=reason,
            )

    # 3. The institution's own category, mapped onto the user's categories.
    if provider_category:
        mapped = PROVIDER_CATEGORY_MAP.get(provider_category.upper())
        category = by_name.get(mapped) if mapped else None
        if category is not None:
            return Candidate(
                category_id=category.id,
                confidence=PROVIDER_CONFIDENCE,
                source=SuggestionSource.PROVIDER,
                reason=f"Your bank filed this as {provider_category}",
            )
    return None


def suggest_category(
    db: Session, user: User, txn: Transaction, *, provider_category: str | None = None
) -> CategorySuggestion | None:
    candidate = choose_category(db, user, txn, provider_category=provider_category)
    if candidate is None:
        return None
    existing = db.scalar(
        select(CategorySuggestion).where(
            CategorySuggestion.user_id == user.id,
            CategorySuggestion.transaction_id == txn.id,
            CategorySuggestion.category_id == candidate.category_id,
        )
    )
    if existing is not None:
        if existing.status == SuggestionStatus.REJECTED.value:
            return None  # The user said no; do not nag.
        return existing
    suggestion = CategorySuggestion(
        user_id=user.id,
        transaction_id=txn.id,
        category_id=candidate.category_id,
        confidence=candidate.confidence,
        source=candidate.source.value,
        status=SuggestionStatus.SUGGESTED.value,
        reason=candidate.reason,
    )
    db.add(suggestion)
    db.flush()
    return suggestion


def list_suggestions(
    db: Session, user_id: uuid.UUID, *, status: str = SuggestionStatus.SUGGESTED.value, limit: int = 50
) -> list[CategorySuggestion]:
    return list(
        db.scalars(
            select(CategorySuggestion)
            .where(
                CategorySuggestion.user_id == user_id,
                CategorySuggestion.status == status,
            )
            .order_by(CategorySuggestion.created_at.desc())
            .limit(limit)
        )
    )


def _get_suggestion(
    db: Session, user_id: uuid.UUID, suggestion_id: uuid.UUID
) -> CategorySuggestion:
    from app.services.errors import NotFoundError

    suggestion = db.scalar(
        select(CategorySuggestion).where(
            CategorySuggestion.id == suggestion_id,
            CategorySuggestion.user_id == user_id,
        )
    )
    if suggestion is None:
        raise NotFoundError("Category suggestion not found.")
    return suggestion


def accept_suggestion(
    db: Session, user: User, suggestion_id: uuid.UUID
) -> CategorySuggestion:
    suggestion = _get_suggestion(db, user.id, suggestion_id)
    if suggestion.status != SuggestionStatus.SUGGESTED.value:
        return suggestion
    txn = db.get(Transaction, suggestion.transaction_id)
    if txn is not None and txn.user_id == user.id:
        txn.category_id = suggestion.category_id
        # Automation must never be mistaken for a human decision later.
        txn.category_source = CategorySource.USER.value
        db.flush()
    suggestion.status = SuggestionStatus.ACCEPTED.value
    suggestion.resolved_at = utc_now()
    # Any competing proposal for the same transaction is now moot.
    for other in db.scalars(
        select(CategorySuggestion).where(
            CategorySuggestion.transaction_id == suggestion.transaction_id,
            CategorySuggestion.id != suggestion.id,
            CategorySuggestion.status == SuggestionStatus.SUGGESTED.value,
        )
    ):
        other.status = SuggestionStatus.REJECTED.value
        other.resolved_at = utc_now()
    db.flush()
    return suggestion


def reject_suggestion(
    db: Session, user: User, suggestion_id: uuid.UUID
) -> CategorySuggestion:
    suggestion = _get_suggestion(db, user.id, suggestion_id)
    suggestion.status = SuggestionStatus.REJECTED.value
    suggestion.resolved_at = utc_now()
    db.flush()
    return suggestion


# ---------------------------------------------------------------- recurring
RECURRING_LOOKBACK_DAYS = 180
RECURRING_MIN_OCCURRENCES = 3
INTERVAL_TOLERANCE_DAYS = 4
AMOUNT_TOLERANCE_RATIO = 0.15
SUBSCRIPTION_MAX_MONTHLY = Decimal("60.00")

_FREQUENCY_BANDS: list[tuple[int, int, Frequency]] = [
    (5, 9, Frequency.WEEKLY),
    (12, 16, Frequency.BIWEEKLY),
    (26, 32, Frequency.MONTHLY),
    (55, 65, Frequency.EVERY_TWO_MONTHS),
    (85, 95, Frequency.QUARTERLY),
    (170, 190, Frequency.SEMIANNUAL),
    (350, 380, Frequency.ANNUAL),
]


def _frequency_for(median_gap: float) -> tuple[Frequency, int]:
    for low, high, frequency in _FREQUENCY_BANDS:
        if low <= median_gap <= high:
            return frequency, int(round(median_gap))
    return Frequency.CUSTOM, int(round(median_gap))


def _confidence(occurrences: int, interval_cv: float, amount_cv: float) -> Decimal:
    score = Decimal("0.45")
    score += min(Decimal("0.20"), Decimal(str(occurrences)) * Decimal("0.03"))
    score += Decimal("0.20") * (Decimal("1") - min(Decimal("1"), Decimal(str(interval_cv))))
    score += Decimal("0.15") * (Decimal("1") - min(Decimal("1"), Decimal(str(amount_cv))))
    return quantize(min(Decimal("0.97"), max(Decimal("0.0"), score)))


def detect_recurring_series(db: Session, user: User) -> list[RecurringSeries]:
    """Find charges that repeat on a stable cadence. Deterministic and explainable."""
    today = today_in(user.timezone)
    window_start = today - timedelta(days=RECURRING_LOOKBACK_DAYS)
    rows = list(
        db.execute(
            select(Transaction)
            .where(
                Transaction.user_id == user.id,
                Transaction.tx_type == TransactionType.PURCHASE.value,
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date >= window_start,
                Transaction.txn_date <= today,
            )
            .order_by(Transaction.txn_date)
        ).scalars()
    )

    groups: dict[str, list[Transaction]] = {}
    for txn in rows:
        key = normalize_merchant(txn.merchant or txn.description)
        if key:
            groups.setdefault(key, []).append(txn)

    by_name = _categories_by_name(db, user.id)
    found: list[RecurringSeries] = []

    for key, items in groups.items():
        if len(items) < RECURRING_MIN_OCCURRENCES:
            continue
        dates = [t.txn_date for t in items]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
        if len(gaps) < RECURRING_MIN_OCCURRENCES - 1:
            continue
        median_gap = statistics.median(gaps)
        if median_gap <= 0:
            continue
        deviations = [abs(gap - median_gap) for gap in gaps]
        if max(deviations) > INTERVAL_TOLERANCE_DAYS:
            continue
        interval_cv = statistics.pstdev(gaps) / median_gap if median_gap else 1.0

        amounts = [quantize(t.amount) for t in items]
        mean_amount = statistics.fmean([float(a) for a in amounts])
        if mean_amount <= 0:
            continue
        amount_cv = statistics.pstdev([float(a) for a in amounts]) / mean_amount
        if amount_cv > AMOUNT_TOLERANCE_RATIO:
            continue

        frequency, interval_days = _frequency_for(median_gap)
        confidence = _confidence(len(items), interval_cv, amount_cv)

        sample = items[0]
        merchant = sample.merchant or sample.description
        # Category by majority among the occurrences (they usually share one).
        category_tally: dict[uuid.UUID, int] = {}
        for txn in items:
            if txn.category_id:
                category_tally[txn.category_id] = category_tally.get(txn.category_id, 0) + 1
        category_id = (
            max(category_tally.items(), key=lambda kv: kv[1])[0] if category_tally else None
        )
        category_name = None
        for candidate in by_name.values():
            if candidate.id == category_id:
                category_name = candidate.name
                break

        is_subscription = (
            frequency in {Frequency.MONTHLY, Frequency.WEEKLY}
            and quantize(Decimal(str(mean_amount))) <= SUBSCRIPTION_MAX_MONTHLY
            and (category_name == "Entertainment" or confidence >= Decimal("0.75"))
        )

        series = db.scalar(
            select(RecurringSeries).where(
                RecurringSeries.user_id == user.id, RecurringSeries.merchant_key == key[:160]
            )
        )
        if series is not None and series.status == RecurringStatus.DISMISSED.value:
            continue  # A dismissal is a decision: do not resurrect it.
        if series is None:
            series = RecurringSeries(
                user_id=user.id,
                merchant_key=key[:160],
                display_name=merchant[:160],
                merchant=sample.merchant[:160] if sample.merchant else None,
                average_amount=quantize(Decimal(str(mean_amount))),
                last_amount=amounts[-1],
                frequency=frequency.value,
                interval_days=interval_days,
                occurrences=len(items),
                first_seen=dates[0],
                last_seen=dates[-1],
                confidence=confidence,
                is_subscription=is_subscription,
            )
            db.add(series)
        else:
            series.display_name = merchant[:160]
            series.merchant = sample.merchant[:160] if sample.merchant else None
            series.average_amount = quantize(Decimal(str(mean_amount)))
            series.last_amount = amounts[-1]
            series.frequency = frequency.value
            series.interval_days = interval_days
            series.occurrences = len(items)
            series.first_seen = dates[0]
            series.last_seen = dates[-1]
            series.confidence = confidence
            series.is_subscription = is_subscription
        series.category_id = category_id
        series.next_expected_date = dates[-1] + timedelta(days=interval_days)
        series.detail = {
            "median_interval_days": median_gap,
            "interval_cv": round(interval_cv, 3),
            "amount_cv": round(amount_cv, 3),
            "sample_transaction_ids": [str(t.id) for t in items[-5:]],
            "heuristic": (
                "is_subscription is inferred from a monthly-or-weekly cadence at a small "
                "stable amount; confirm or dismiss it."
            ),
        }
        db.flush()
        found.append(series)

    found.sort(key=lambda s: (-float(s.confidence), s.display_name))
    return found


def list_recurring(
    db: Session, user_id: uuid.UUID, *, include_dismissed: bool = False
) -> list[RecurringSeries]:
    query = select(RecurringSeries).where(RecurringSeries.user_id == user_id)
    if not include_dismissed:
        query = query.where(RecurringSeries.status != RecurringStatus.DISMISSED.value)
    return list(db.scalars(query.order_by(RecurringSeries.confidence.desc())))


def set_recurring_status(
    db: Session, user: User, series_id: uuid.UUID, status: RecurringStatus
) -> RecurringSeries:
    from app.services.errors import NotFoundError

    series = db.scalar(
        select(RecurringSeries).where(
            RecurringSeries.id == series_id, RecurringSeries.user_id == user.id
        )
    )
    if series is None:
        raise NotFoundError("Recurring series not found.")
    series.status = status.value
    db.flush()
    return series


# ---------------------------------------------------------------- anomalies
def unusual_transactions(
    db: Session, user: User, *, days: int = 45, multiplier: Decimal = Decimal("2.5")
) -> list[dict[str, object]]:
    """Transactions far above what this merchant normally costs for this user."""
    today = today_in(user.timezone)
    start = today - timedelta(days=max(days, 30) * 4)
    rows = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.tx_type == TransactionType.PURCHASE.value,
                Transaction.status == TransactionStatus.POSTED.value,
                Transaction.txn_date >= start,
            )
        )
    )
    groups: dict[str, list[Transaction]] = {}
    for txn in rows:
        key = normalize_merchant(txn.merchant or txn.description)
        if key:
            groups.setdefault(key, []).append(txn)

    out: list[dict[str, object]] = []
    for key, items in groups.items():
        if len(items) < 4:
            continue  # Too little history to call anything unusual.
        history = [t for t in items if t.txn_date < today - timedelta(days=days)]
        recent = [t for t in items if t.txn_date >= today - timedelta(days=days)]
        if len(history) < 3 or not recent:
            continue
        baseline = statistics.median(float(t.amount) for t in history)
        if baseline <= 0:
            continue
        for txn in recent:
            if float(txn.amount) >= baseline * float(multiplier):
                out.append(
                    {
                        "transaction_id": str(txn.id),
                        "description": txn.description,
                        "merchant": txn.merchant,
                        "amount": str(quantize(txn.amount)),
                        "txn_date": txn.txn_date.isoformat(),
                        "typical_amount": str(quantize(Decimal(str(baseline)))),
                        "times_typical": round(float(txn.amount) / baseline, 2),
                        "reason": (
                            f"Usually about {quantize(Decimal(str(baseline)))} at this "
                            f"merchant; this one was {quantize(txn.amount)}."
                        ),
                    }
                )
    out.sort(key=lambda r: str(r["txn_date"]), reverse=True)
    return out[:20]
