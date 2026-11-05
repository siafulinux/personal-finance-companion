"""Deterministic, explainable bill <-> transaction matching.

The engine is a pure function: no database access, no randomness, no AI. Given a
candidate transaction, outstanding bill occurrences and the user's tolerances it
returns ranked candidates with a confidence score and a human-readable reason.

Signals and weights (sum = 1.00):
    merchant similarity  0.45
    amount similarity    0.30
    date proximity       0.15
    account agreement    0.10

Hard rules
----------
* A candidate needs a merchant signal and an amount inside the acceptance band;
  amount alone never matches an unrelated merchant.
* Exact merchant alias matches unlock the highest merchant score.
* Two close candidates are ambiguous and are never auto-confirmed.
* A partial payment may be suggested but scores too low to auto-confirm.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.matching.normalize import merchant_similarity, normalize_merchant
from app.utils.money import ZERO, quantize

WEIGHT_MERCHANT = Decimal("0.45")
WEIGHT_AMOUNT = Decimal("0.30")
WEIGHT_DATE = Decimal("0.15")
WEIGHT_ACCOUNT = Decimal("0.10")

AMBIGUITY_MARGIN = Decimal("0.10")
PARTIAL_PAYMENT_MIN_RATIO = Decimal("0.20")


@dataclass(frozen=True)
class OccurrenceCandidate:
    occurrence_id: uuid.UUID
    bill_id: uuid.UUID
    bill_name: str
    merchant: str | None
    expected_amount: Decimal
    paid_amount: Decimal
    due_date: date
    account_id: uuid.UUID | None
    aliases: tuple[str, ...] = ()

    @property
    def remaining(self) -> Decimal:
        remaining = self.expected_amount - self.paid_amount
        return quantize(remaining if remaining > ZERO else ZERO)


@dataclass(frozen=True)
class TransactionCandidate:
    transaction_id: uuid.UUID
    merchant: str | None
    description: str
    amount: Decimal
    txn_date: date
    account_id: uuid.UUID


@dataclass(frozen=True)
class MatchConfig:
    window_before_days: int = 3
    window_after_days: int = 7
    tolerance_amount: Decimal = Decimal("2.00")
    tolerance_percent: Decimal = Decimal("1.00")
    auto_threshold: Decimal = Decimal("0.85")
    suggestion_threshold: Decimal = Decimal("0.55")
    auto_matching_enabled: bool = True


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: OccurrenceCandidate
    score: Decimal
    amount_score: Decimal
    merchant_score: Decimal
    date_score: Decimal
    account_score: Decimal
    is_partial: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "occurrence_id": str(self.candidate.occurrence_id),
            "bill_id": str(self.candidate.bill_id),
            "bill_name": self.candidate.bill_name,
            "due_date": self.candidate.due_date.isoformat(),
            "remaining": str(self.candidate.remaining),
            "confidence": f"{self.score:.3f}",
            "signals": {
                "merchant": f"{self.merchant_score:.3f}",
                "amount": f"{self.amount_score:.3f}",
                "date": f"{self.date_score:.3f}",
                "account": f"{self.account_score:.3f}",
            },
            "is_partial": self.is_partial,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MatchDecision:
    outcome: str  # "auto" | "suggest" | "none"
    method: str  # "automatic" | "suggested" | "none"
    scored: list[ScoredCandidate] = field(default_factory=list)
    ambiguous: bool = False
    reason: str = ""

    @property
    def best(self) -> ScoredCandidate | None:
        return self.scored[0] if self.scored else None


def _merchant_score(tx: TransactionCandidate, occ: OccurrenceCandidate) -> tuple[Decimal, str]:
    tx_merchant = tx.merchant or tx.description
    if not occ.merchant:
        # Bills without a merchant rely on amount + date + account only.
        return Decimal("0.60"), "Bill has no merchant; matched on amount and timing"

    tx_norm = normalize_merchant(tx_merchant)
    # Aliases supplied for this bill map alternative descriptors to it.
    alias_hit = bool(tx_norm) and any(
        normalize_merchant(alias) == tx_norm for alias in occ.aliases
    )
    if alias_hit:
        return Decimal("1.00"), f"Alias match for {occ.merchant}"

    similarity = merchant_similarity(tx_merchant, occ.merchant)
    name_similarity = merchant_similarity(tx_merchant, occ.bill_name)
    best = max(similarity, name_similarity)
    if best >= 0.99:
        return Decimal("1.00"), f"Merchant matches {occ.merchant}"
    if best > 0:
        return Decimal(f"{best:.3f}"), f"Merchant similar to {occ.merchant}"
    return ZERO, "Merchant does not match"


def _amount_score(
    tx: TransactionCandidate, occ: OccurrenceCandidate, config: MatchConfig
) -> tuple[Decimal | None, bool, str]:
    remaining = occ.remaining
    if remaining <= ZERO:
        return None, False, "Bill occurrence is already fully paid"
    tolerance = max(
        config.tolerance_amount,
        quantize(remaining * config.tolerance_percent / Decimal("100")),
    )
    diff = abs(tx.amount - remaining)
    if diff <= tolerance:
        ratio = Decimal("1") - (diff / tolerance) * Decimal("0.3") if tolerance > ZERO else Decimal("1")
        return quantize(ratio), False, f"Amount within tolerance (+/- {tolerance})"
    if (
        tx.amount < remaining
        and tx.amount >= remaining * PARTIAL_PAYMENT_MIN_RATIO
        and tx.amount <= remaining
    ):
        return Decimal("0.45"), True, "Possible partial payment"
    return None, False, "Amount outside the accepted range"


def _date_score(tx: TransactionCandidate, occ: OccurrenceCandidate, config: MatchConfig) -> Decimal:
    days = (tx.txn_date - occ.due_date).days
    if days < -config.window_before_days or days > config.window_after_days:
        return ZERO
    span = max(config.window_before_days + config.window_after_days, 1)
    return quantize(Decimal("1") - (Decimal(abs(days)) / Decimal(span)) * Decimal("0.5"))


def _account_score(tx: TransactionCandidate, occ: OccurrenceCandidate) -> Decimal:
    if occ.account_id is None:
        return Decimal("0.70")
    return Decimal("1.00") if occ.account_id == tx.account_id else ZERO


def score_candidate(
    tx: TransactionCandidate, occ: OccurrenceCandidate, config: MatchConfig
) -> ScoredCandidate | None:
    merchant_score, merchant_reason = _merchant_score(tx, occ)
    if merchant_score <= ZERO:
        return None
    amount_score, is_partial, amount_reason = _amount_score(tx, occ, config)
    if amount_score is None:
        return None
    date_score = _date_score(tx, occ, config)
    if date_score <= ZERO:
        return None
    account_score = _account_score(tx, occ)

    score = quantize(
        merchant_score * WEIGHT_MERCHANT
        + amount_score * WEIGHT_AMOUNT
        + date_score * WEIGHT_DATE
        + account_score * WEIGHT_ACCOUNT
    )
    reason = "; ".join(filter(None, [merchant_reason, amount_reason]))
    return ScoredCandidate(
        candidate=occ,
        score=score,
        amount_score=amount_score,
        merchant_score=merchant_score,
        date_score=date_score,
        account_score=account_score,
        is_partial=is_partial,
        reason=reason,
    )


def rank_matches(
    tx: TransactionCandidate,
    occurrences: list[OccurrenceCandidate],
    config: MatchConfig,
) -> list[ScoredCandidate]:
    scored = [s for o in occurrences if (s := score_candidate(tx, o, config)) is not None]
    scored.sort(key=lambda s: (-s.score, s.candidate.due_date, str(s.candidate.occurrence_id)))
    return scored


def decide(
    tx: TransactionCandidate,
    occurrences: list[OccurrenceCandidate],
    config: MatchConfig,
) -> MatchDecision:
    ranked = rank_matches(tx, occurrences, config)
    if not ranked:
        return MatchDecision(outcome="none", method="none", reason="No bill candidate found")

    top = ranked[0]
    ambiguous = len(ranked) > 1 and (top.score - ranked[1].score) < AMBIGUITY_MARGIN

    if ambiguous:
        contenders = [r for r in ranked if (top.score - r.score) < AMBIGUITY_MARGIN]
        return MatchDecision(
            outcome="suggest",
            method="suggested",
            scored=contenders,
            ambiguous=True,
            reason=(
                f"{len(contenders)} bills could match this transaction "
                f"(confidence {top.score:.2f} vs {ranked[1].score:.2f}); confirmation required"
            ),
        )

    if top.score < config.suggestion_threshold:
        return MatchDecision(
            outcome="none",
            method="none",
            scored=[top],
            reason=f"Best candidate confidence {top.score:.2f} is below the suggestion threshold",
        )

    if config.auto_matching_enabled and top.score >= config.auto_threshold and not top.is_partial:
        return MatchDecision(
            outcome="auto",
            method="automatic",
            scored=[top],
            reason=f"High-confidence unique match ({top.score:.2f}); {top.reason}",
        )

    return MatchDecision(
        outcome="suggest",
        method="suggested",
        scored=[top],
        reason=f"Confidence {top.score:.2f} requires confirmation; {top.reason}",
    )
