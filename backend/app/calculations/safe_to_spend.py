"""Deterministic Safe-to-Spend engine.

Pure functions and immutable dataclasses only: no database, no clock, no network.
Every number a user sees comes from here or from the budgeting engine.

Definition
----------
Safe-to-Spend is money that can be spent *right now* without breaking the plan::

    eligible balances
      - pending debits not yet reflected in those balances
      - unpaid bill occurrences inside the planning horizon
      - the user's minimum cash buffer
      - explicitly reserved savings / commitments
      = raw safe-to-spend   (clamped at zero for the recommendation)

Expected future income is never included before it arrives. Credit limits and
credit card balances are never treated as cash.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.utils.dates import utc_now
from app.utils.money import ZERO, clamp_zero, format_money, quantize


@dataclass(frozen=True)
class AccountSnapshot:
    id: uuid.UUID
    name: str
    account_type: str
    balance: Decimal  # posted balance (opening + posted transactions + adjustments)
    include_in_safe_to_spend: bool
    is_liability: bool = False
    is_archived: bool = False


@dataclass(frozen=True)
class PendingItem:
    id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal
    tx_type: str
    # For transfers, the destination account. A transfer between two eligible
    # cash accounts does not change spendable cash; a transfer out of eligible
    # cash (for example, to savings) does.
    counter_account_id: uuid.UUID | None = None
    linked_to_bill: bool = False


@dataclass(frozen=True)
class BillReserveItem:
    occurrence_id: uuid.UUID
    bill_id: uuid.UUID
    bill_name: str
    due_date: date
    amount: Decimal
    is_overdue: bool
    is_essential: bool
    category_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ReserveItem:
    id: uuid.UUID
    name: str
    amount: Decimal
    is_savings: bool = False


@dataclass(frozen=True)
class LoanReserveItem:
    """One loan instalment falling due inside the horizon."""

    loan_id: uuid.UUID
    loan_name: str
    due_date: date
    amount: Decimal
    is_overdue: bool = False
    is_estimate: bool = False
    remaining_balance: Decimal = ZERO


@dataclass(frozen=True)
class SavingsReserveItem:
    """Money protected by a savings goal, or a contribution due before the horizon."""

    goal_id: uuid.UUID
    name: str
    amount: Decimal
    mode: str = "virtual"
    is_planned_contribution: bool = False
    due_date: date | None = None


@dataclass(frozen=True)
class CreditCardObligation:
    """A user-entered minimum payment. Never inferred from the balance."""

    account_id: uuid.UUID
    name: str
    minimum_payment: Decimal
    due_date: date | None = None


@dataclass(frozen=True)
class SafeToSpendInputs:
    today: date
    horizon_end: date
    accounts: list[AccountSnapshot]
    pending: list[PendingItem] = field(default_factory=list)
    bills: list[BillReserveItem] = field(default_factory=list)
    reserves: list[ReserveItem] = field(default_factory=list)
    loans: list[LoanReserveItem] = field(default_factory=list)
    savings: list[SavingsReserveItem] = field(default_factory=list)
    credit_cards: list[CreditCardObligation] = field(default_factory=list)
    minimum_buffer: Decimal = ZERO
    include_pending_debits: bool = True
    payday: date | None = None
    currency: str = "USD"
    last_transaction_date: date | None = None
    as_of: datetime | None = None


@dataclass(frozen=True)
class ExplanationLine:
    key: str
    label: str
    amount: Decimal
    kind: str  # "credit" | "debit" | "result"
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "amount": str(quantize(self.amount)),
            "kind": self.kind,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SafeToSpendResult:
    currency: str
    as_of: datetime
    today: date
    horizon_end: date
    payday: date | None
    eligible_balance: Decimal
    pending_debits: Decimal
    bill_reserves: Decimal
    minimum_buffer: Decimal
    explicit_reserves: Decimal
    raw_amount: Decimal
    safe_to_spend: Decimal
    projected_shortfall: Decimal
    is_negative: bool
    accounts: list[dict[str, object]]
    bills: list[dict[str, object]]
    reserves: list[dict[str, object]]
    pending_items: list[dict[str, object]]
    warnings: list[str]
    explanation: list[ExplanationLine]
    stale_information: bool
    loan_reserves: Decimal = ZERO
    savings_reserves: Decimal = ZERO
    credit_card_reserves: Decimal = ZERO
    obligations_total: Decimal = ZERO
    loans: list[dict[str, object]] = field(default_factory=list)
    savings: list[dict[str, object]] = field(default_factory=list)
    credit_cards: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "currency": self.currency,
            "as_of": self.as_of.isoformat(),
            "today": self.today.isoformat(),
            "horizon_end": self.horizon_end.isoformat(),
            "payday": self.payday.isoformat() if self.payday else None,
            "eligible_balance": str(self.eligible_balance),
            "pending_debits": str(self.pending_debits),
            "bill_reserves": str(self.bill_reserves),
            "minimum_buffer": str(self.minimum_buffer),
            "explicit_reserves": str(self.explicit_reserves),
            "raw_amount": str(self.raw_amount),
            "safe_to_spend": str(self.safe_to_spend),
            "projected_shortfall": str(self.projected_shortfall),
            "is_negative": self.is_negative,
            "accounts": self.accounts,
            "bills": self.bills,
            "reserves": self.reserves,
            "pending_items": self.pending_items,
            "warnings": self.warnings,
            "explanation": [line.as_dict() for line in self.explanation],
            "stale_information": self.stale_information,
            "loan_reserves": str(self.loan_reserves),
            "savings_reserves": str(self.savings_reserves),
            "credit_card_reserves": str(self.credit_card_reserves),
            "obligations_total": str(self.obligations_total),
            "loans": self.loans,
            "savings": self.savings,
            "credit_cards": self.credit_cards,
        }


STALE_AFTER_DAYS = 30


def calculate_safe_to_spend(inputs: SafeToSpendInputs) -> SafeToSpendResult:
    """Compute Safe-to-Spend with an auditable explanation."""
    warnings: list[str] = []
    lines: list[ExplanationLine] = []

    eligible = [
        account
        for account in inputs.accounts
        if account.include_in_safe_to_spend
        and not account.is_archived
        and not account.is_liability
    ]
    excluded_liabilities = [
        a for a in inputs.accounts if a.include_in_safe_to_spend and a.is_liability
    ]

    if not eligible:
        warnings.append(
            "No spending accounts contribute to Safe-to-Spend yet. "
            "Select at least one active cash account in Settings."
        )
    if excluded_liabilities:
        warnings.append(
            "Credit card balances never count as available cash, even if marked as contributing."
        )

    account_rows: list[dict[str, object]] = []
    eligible_balance = ZERO
    for account in sorted(eligible, key=lambda a: a.name.lower()):
        eligible_balance += account.balance
        account_rows.append(
            {
                "id": str(account.id),
                "name": account.name,
                "account_type": account.account_type,
                "balance": str(quantize(account.balance)),
                "contributes": True,
            }
        )
    eligible_balance = quantize(eligible_balance)

    # Pending outflows are not yet in the posted balance. Count them until they
    # post, including payments already linked to a bill: the bill reserve only
    # covers the occurrence's remaining amount, not cash that has not left yet.
    pending_items = list(inputs.pending)
    eligible_ids = {a.id for a in eligible}
    pending_debits = quantize(
        sum(
            (
                p.amount
                for p in pending_items
                if p.account_id in eligible_ids
                and (p.counter_account_id is None or p.counter_account_id not in eligible_ids)
            ),
            ZERO,
        )
    )
    if not inputs.include_pending_debits:
        pending_debits = ZERO
    elif pending_items and pending_debits > ZERO:
        warnings.append(
            "Pending transactions are included as deductions until they post."
        )

    bill_rows: list[dict[str, object]] = []
    bill_total = ZERO
    for bill in sorted(inputs.bills, key=lambda b: (b.due_date, b.bill_name.lower())):
        bill_total += bill.amount
        bill_rows.append(
            {
                "occurrence_id": str(bill.occurrence_id),
                "bill_id": str(bill.bill_id),
                "name": bill.bill_name,
                "due_date": bill.due_date.isoformat(),
                "amount": str(quantize(bill.amount)),
                "is_overdue": bill.is_overdue,
                "is_essential": bill.is_essential,
                "category_id": str(bill.category_id) if bill.category_id else None,
            }
        )
    bill_total = quantize(bill_total)

    reserve_rows: list[dict[str, object]] = []
    reserve_total = ZERO
    for reserve in inputs.reserves:
        reserve_total += reserve.amount
        reserve_rows.append(
            {
                "id": str(reserve.id),
                "name": reserve.name,
                "amount": str(quantize(reserve.amount)),
                "is_savings": reserve.is_savings,
            }
        )
    reserve_total = quantize(reserve_total)

    # Loan instalments are their own commitment: a repayment is not a purchase and
    # must not be lumped in with bills, or a loan that is also recorded as a bill
    # would be reserved twice.
    loan_rows: list[dict[str, object]] = []
    loan_total = ZERO
    estimated_loans: list[str] = []
    for loan in sorted(inputs.loans, key=lambda item: (item.due_date, item.loan_name.lower())):
        loan_total += loan.amount
        if loan.is_estimate:
            estimated_loans.append(loan.loan_name)
        loan_rows.append(
            {
                "loan_id": str(loan.loan_id),
                "name": loan.loan_name,
                "due_date": loan.due_date.isoformat(),
                "amount": str(quantize(loan.amount)),
                "is_overdue": loan.is_overdue,
                "is_estimate": loan.is_estimate,
                "remaining_balance": str(quantize(loan.remaining_balance)),
            }
        )
    loan_total = quantize(loan_total)

    savings_rows: list[dict[str, object]] = []
    savings_total = ZERO
    for item in inputs.savings:
        if item.amount <= ZERO:
            continue
        savings_total += item.amount
        savings_rows.append(
            {
                "goal_id": str(item.goal_id),
                "name": item.name,
                "amount": str(quantize(item.amount)),
                "mode": item.mode,
                "is_planned_contribution": item.is_planned_contribution,
                "due_date": item.due_date.isoformat() if item.due_date else None,
            }
        )
    savings_total = quantize(savings_total)

    credit_rows: list[dict[str, object]] = []
    credit_total = ZERO
    for card in inputs.credit_cards:
        if card.minimum_payment <= ZERO:
            continue
        credit_total += card.minimum_payment
        credit_rows.append(
            {
                "account_id": str(card.account_id),
                "name": card.name,
                "minimum_payment": str(quantize(card.minimum_payment)),
                "due_date": card.due_date.isoformat() if card.due_date else None,
            }
        )
    credit_total = quantize(credit_total)

    buffer_total = quantize(max(inputs.minimum_buffer, ZERO))

    raw = (
        eligible_balance
        - pending_debits
        - bill_total
        - loan_total
        - credit_total
        - reserve_total
        - savings_total
        - buffer_total
    )
    raw = quantize(raw)
    safe_to_spend = clamp_zero(raw)
    shortfall = clamp_zero(-raw)

    lines.append(
        ExplanationLine(
            key="eligible_balance",
            label="Available in spending accounts",
            amount=eligible_balance,
            kind="credit",
            detail=", ".join(a["name"] for a in account_rows) or None,
        )
    )
    if pending_debits > ZERO:
        lines.append(
            ExplanationLine(
                key="pending_debits",
                label="Pending debits not yet posted",
                amount=pending_debits,
                kind="debit",
            )
        )
    if bill_total > ZERO:
        lines.append(
            ExplanationLine(
                key="bill_reserves",
                label="Bills due before your next payday",
                amount=bill_total,
                kind="debit",
                detail=f"{len(bill_rows)} unpaid bill occurrence(s)",
            )
        )
    if buffer_total > ZERO:
        lines.append(
            ExplanationLine(
                key="minimum_buffer",
                label="Minimum cash buffer you want to keep",
                amount=buffer_total,
                kind="debit",
            )
        )
    if loan_total > ZERO:
        lines.append(
            ExplanationLine(
                key="loan_reserves",
                label="Loan and advance repayments due",
                amount=loan_total,
                kind="debit",
                detail=f"{len(loan_rows)} instalment(s)",
            )
        )
    if credit_total > ZERO:
        lines.append(
            ExplanationLine(
                key="credit_card_reserves",
                label="Credit card minimum payments you set",
                amount=credit_total,
                kind="debit",
            )
        )
    if reserve_total > ZERO:
        lines.append(
            ExplanationLine(
                key="explicit_reserves",
                label="Reserved savings and commitments",
                amount=reserve_total,
                kind="debit",
            )
        )
    if savings_total > ZERO:
        lines.append(
            ExplanationLine(
                key="savings_reserves",
                label="Money set aside in savings goals",
                amount=savings_total,
                kind="debit",
                detail=f"{len(savings_rows)} goal(s) and contribution(s)",
            )
        )
    lines.append(
        ExplanationLine(
            key="safe_to_spend",
            label="Safe to spend now",
            amount=safe_to_spend,
            kind="result",
        )
    )

    if shortfall > ZERO:
        warnings.append(
            f"Your reserved commitments exceed available cash by {format_money(shortfall)}. "
            "Safe-to-Spend is clamped to zero until income arrives or bills are reduced."
        )
    overdue = [b for b in inputs.bills if b.is_overdue]
    if overdue:
        warnings.append(
            f"{len(overdue)} bill occurrence(s) are overdue and still reserved: "
            + ", ".join(f"{b.bill_name} ({b.due_date.isoformat()})" for b in overdue[:3])
        )
    if estimated_loans:
        warnings.append(
            "Some loan balances are estimates because repayment terms or principal/interest "
            "splits are incomplete: " + ", ".join(estimated_loans[:3]) + "."
        )
    if inputs.payday is None:
        warnings.append(
            "No upcoming payday is set, so a fixed planning horizon was used."
        )
    elif inputs.payday <= inputs.today:
        warnings.append("Your recorded payday is not in the future; using a fixed horizon.")

    stale = (
        inputs.last_transaction_date is None
        or (inputs.today - inputs.last_transaction_date).days > STALE_AFTER_DAYS
    )
    if stale and inputs.accounts:
        warnings.append(
            "Your transaction history looks stale (nothing in the last 30 days). "
            "Balances may not reflect reality."
        )

    return SafeToSpendResult(
        currency=inputs.currency,
        as_of=inputs.as_of or utc_now(),
        today=inputs.today,
        horizon_end=inputs.horizon_end,
        payday=inputs.payday,
        eligible_balance=eligible_balance,
        pending_debits=pending_debits,
        bill_reserves=bill_total,
        minimum_buffer=buffer_total,
        explicit_reserves=reserve_total,
        loan_reserves=loan_total,
        savings_reserves=savings_total,
        credit_card_reserves=credit_total,
        obligations_total=quantize(bill_total + loan_total + credit_total),
        loans=loan_rows,
        savings=savings_rows,
        credit_cards=credit_rows,
        raw_amount=raw,
        safe_to_spend=safe_to_spend,
        projected_shortfall=shortfall,
        is_negative=raw < ZERO,
        accounts=account_rows,
        bills=bill_rows,
        reserves=reserve_rows,
        pending_items=[
            {
                "id": str(p.id),
                "account_id": str(p.account_id),
                "amount": str(quantize(p.amount)),
                "tx_type": p.tx_type,
            }
            for p in pending_items
            if p.account_id in eligible_ids
        ],
        warnings=warnings,
        explanation=lines,
        stale_information=stale,
    )


@dataclass(frozen=True)
class CategoryAvailabilityInputs:
    category_id: uuid.UUID
    category_name: str
    budgeted: Decimal
    spent: Decimal
    carryover_in: Decimal = ZERO
    upcoming_commitments: Decimal = ZERO


@dataclass(frozen=True)
class CategoryAvailability:
    category_id: uuid.UUID
    category_name: str
    budgeted: Decimal
    spent: Decimal
    carryover_in: Decimal
    remaining: Decimal
    percent_used: Decimal
    upcoming_commitments: Decimal
    max_safe_purchase: Decimal
    overall_safe_to_spend: Decimal
    limited_by: str  # "category" | "cash" | "none"

    def as_dict(self) -> dict[str, object]:
        return {
            "category_id": str(self.category_id),
            "category_name": self.category_name,
            "budgeted": str(quantize(self.budgeted)),
            "spent": str(quantize(self.spent)),
            "carryover_in": str(quantize(self.carryover_in)),
            "remaining": str(quantize(self.remaining)),
            "percent_used": str(quantize(self.percent_used)),
            "upcoming_commitments": str(quantize(self.upcoming_commitments)),
            "max_safe_purchase": str(quantize(self.max_safe_purchase)),
            "overall_safe_to_spend": str(quantize(self.overall_safe_to_spend)),
            "limited_by": self.limited_by,
        }


def calculate_category_availability(
    inputs: CategoryAvailabilityInputs, overall_safe_to_spend: Decimal
) -> CategoryAvailability:
    """Category spending recommendation = min(cash available now, category remaining).

    The overall cash constraint always wins: a healthy clothing budget cannot be
    spent if the money is already reserved for rent.
    """
    effective_budget = inputs.budgeted + inputs.carryover_in
    remaining = quantize(max(effective_budget - inputs.spent, ZERO))
    percent_used = (
        quantize((inputs.spent / effective_budget) * Decimal("100"))
        if effective_budget > ZERO
        else Decimal("0.00")
    )
    cash = clamp_zero(overall_safe_to_spend)
    if remaining <= ZERO:
        max_purchase = ZERO
        limited_by = "category"
    elif cash <= ZERO:
        max_purchase = ZERO
        limited_by = "cash"
    elif remaining < cash:
        max_purchase = remaining
        limited_by = "category"
    else:
        max_purchase = cash
        limited_by = "cash"
    return CategoryAvailability(
        category_id=inputs.category_id,
        category_name=inputs.category_name,
        budgeted=quantize(inputs.budgeted),
        spent=quantize(inputs.spent),
        carryover_in=quantize(inputs.carryover_in),
        remaining=remaining,
        percent_used=percent_used,
        upcoming_commitments=quantize(inputs.upcoming_commitments),
        max_safe_purchase=quantize(max_purchase),
        overall_safe_to_spend=quantize(overall_safe_to_spend),
        limited_by=limited_by,
    )


def evaluate_purchase(
    *, amount: Decimal, category_available: CategoryAvailability, safe_to_spend: Decimal
) -> dict[str, object]:
    """Deterministic what-if for a planned purchase (Shopping Check)."""
    remaining = category_available.remaining
    after_category = quantize(remaining - amount)
    after_cash = quantize(safe_to_spend - amount)
    allowed = amount <= remaining and amount <= safe_to_spend
    if amount <= remaining and amount <= safe_to_spend:
        message = (
            f"This {format_money(amount)} purchase fits your "
            f"{category_available.category_name} budget and leaves "
            f"{format_money(after_category)} in that category."
        )
    elif amount > remaining and amount <= safe_to_spend:
        message = (
            f"This purchase exceeds your {category_available.category_name} budget by "
            f"{format_money(amount - remaining)}."
        )
    elif amount <= remaining and amount > safe_to_spend:
        message = (
            "Your category budget allows this, but available cash does not. "
            f"You are short {format_money(amount - safe_to_spend)} of safe-to-spend."
        )
    else:
        message = "This purchase exceeds both your category budget and available cash."
    return {
        "amount": str(quantize(amount)),
        "allowed": allowed,
        "category_remaining": str(remaining),
        "category_remaining_after": str(after_category),
        "safe_to_spend": str(quantize(safe_to_spend)),
        "safe_to_spend_after": str(after_cash),
        "category_over_budget": amount > remaining,
        "cash_shortfall": str(clamp_zero(amount - safe_to_spend)),
        "message": message,
    }
