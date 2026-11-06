"""Bundled sandbox institution.

This adapter is the credential-free development and acceptance path: it simulates one US
institution with checking, savings and credit-card accounts, roughly three months of
realistic activity, a pending card authorisation that later posts, recurring subscriptions
and a reversal.

It is deliberately deterministic. The same item id always produces the same transactions
with the same external ids, which is what lets duplicate-suppression and pending→posted
reconciliation be tested without network access or an account at any aggregator.

The `advance()` helper moves an item to its next "day" of activity. Tests use it to drive
pending→posted, new charges and reversals; the API never exposes it.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta
from decimal import Decimal

from app.providers.base import (
    LinkResult,
    ProviderAccountData,
    ProviderAdapter,
    ProviderError,
    ProviderTransactionData,
    TransactionDelta,
)
from app.utils.dates import add_months
from app.utils.money import quantize

CHECKING = "sbx-checking"
SAVINGS = "sbx-savings"
CREDIT = "sbx-credit"

# How many activity "days" each item has been advanced. Module state on purpose: the
# sandbox only exists for development and tests, and never holds real money.
_GENERATION: dict[str, int] = {}
_HISTORY_DAYS = 90

_SUBSCRIPTIONS = [
    # (merchant, description, day of month, amount, provider category)
    ("Netflix", "NETFLIX.COM 866-579-7172", 12, Decimal("15.49"), "ENTERTAINMENT"),
    ("Spotify", "SPOTIFY USA", 21, Decimal("10.99"), "ENTERTAINMENT"),
    ("iCloud", "APPLE.COM/BILL", 4, Decimal("2.99"), "ENTERTAINMENT"),
]


def reset_state() -> None:
    """Clear sandbox progress. Used by tests to keep cases independent."""
    _GENERATION.clear()


def advance(item_id: str) -> int:
    """Move a sandbox item to the next day of activity and return the new generation."""
    _GENERATION[item_id] = _GENERATION.get(item_id, 0) + 1
    return _GENERATION[item_id]


def generation_of(item_id: str) -> int:
    return _GENERATION.get(item_id, 0)


def _seed(item_id: str) -> int:
    return int(hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:8], 16)


def _ext(item_id: str, kind: str, index: int) -> str:
    return f"sbx-{_seed(item_id):08x}-{kind}-{index:03d}"


def _history(item_id: str, today: date) -> list[ProviderTransactionData]:
    """Deterministic ~90 day history, newest last."""
    rng = random.Random(_seed(item_id))
    start = today - timedelta(days=_HISTORY_DAYS)
    rows: list[ProviderTransactionData] = []
    counter = 0

    def add(
        *,
        day: date,
        account: str,
        description: str,
        amount: Decimal,
        tx_type: str,
        merchant: str | None,
        provider_category: str | None,
        pending: bool = False,
        kind: str = "t",
    ) -> None:
        nonlocal counter
        counter += 1
        rows.append(
            ProviderTransactionData(
                external_id=_ext(item_id, kind, counter),
                account_external_id=account,
                description=description,
                amount=quantize(amount),
                tx_type=tx_type,
                txn_date=day,
                posting_date=day,
                merchant=merchant,
                pending=pending,
                provider_category=provider_category,
            )
        )

    # A fortnightly paycheck into checking, anchored to the window start.
    payday = start
    while payday <= today - timedelta(days=3):
        add(
            day=payday,
            account=CHECKING,
            description="ACME PAYROLL DIRECT DEP",
            amount=Decimal("2340.00"),
            tx_type="income",
            merchant="Acme Payroll",
            provider_category="INCOME",
        )
        payday += timedelta(days=14)

    # Monthly subscriptions on the credit card: the recurring-detection fixtures.
    for month_offset in range(4):
        for merchant, description, day_of_month, amount, category in _SUBSCRIPTIONS:
            month_start = add_months(today.replace(day=1), -month_offset)
            try:
                when = month_start.replace(day=day_of_month)
            except ValueError:  # pragma: no cover - day_of_month is always valid
                continue
            if start <= when <= today:
                add(
                    day=when,
                    account=CREDIT,
                    description=description,
                    amount=amount,
                    tx_type="purchase",
                    merchant=merchant,
                    provider_category=category,
                )

    # Weekly groceries in varying amounts (drives personalisation fixtures).
    for week in range(_HISTORY_DAYS // 7):
        when = start + timedelta(days=7 * week + 2)
        if when > today:
            break
        add(
            day=when,
            account=CHECKING,
            description="WHOLE FOODS MKT #10251",
            amount=quantize(Decimal("96.40") + Decimal(rng.randint(-2800, 4200)) / 100),
            tx_type="purchase",
            merchant="Whole Foods Market",
            provider_category="FOOD_AND_DRINK",
        )

    # Monthly household purchases at one store, with one clear overspend month.
    for month_offset in range(3):
        when = add_months(today.replace(day=1), -month_offset).replace(day=16)
        if start <= when <= today:
            bump = Decimal("180.00") if month_offset == 0 else Decimal("0")
            add(
                day=when,
                account=CREDIT,
                description="TARGET 00021498",
                amount=quantize(Decimal("118.75") + bump),
                tx_type="purchase",
                merchant="Target",
                provider_category="GENERAL_MERCHANDISE",
            )

    # Frequent small coffee purchases: the "repeated small purchases" signal.
    for day_offset in range(0, _HISTORY_DAYS, 3):
        when = start + timedelta(days=day_offset)
        if when > today:
            break
        add(
            day=when,
            account=CHECKING,
            description="STARBUCKS STORE 08431",
            amount=quantize(Decimal("4.25") + Decimal(rng.randint(0, 275)) / 100),
            tx_type="purchase",
            merchant="Starbucks",
            provider_category="FOOD_AND_DRINK",
        )

    # A fuel fill each month.
    for month_offset in range(3):
        when = add_months(today.replace(day=1), -month_offset).replace(day=9)
        if start <= when <= today:
            add(
                day=when,
                account=CHECKING,
                description="SHELL OIL 5744192",
                amount=quantize(Decimal("52.10") + Decimal(rng.randint(0, 900)) / 100),
                tx_type="purchase",
                merchant="Shell",
                provider_category="TRANSPORTATION",
            )

    # A transfer to savings, monthly: must never count as spending. Both legs are
    # reported, as a real institution does, so the sync engine can pair them into a
    # single internal transfer instead of two unrelated cash movements.
    for month_offset in range(3):
        when = add_months(today.replace(day=1), -month_offset).replace(day=25)
        if start <= when <= today:
            add(
                day=when,
                account=CHECKING,
                description="TRANSFER TO SAVINGS",
                amount=Decimal("200.00"),
                tx_type="transfer_out",
                merchant=None,
                provider_category="TRANSFER_OUT",
                kind="out",
            )
            add(
                day=when,
                account=SAVINGS,
                description="TRANSFER FROM CHECKING",
                amount=Decimal("200.00"),
                tx_type="transfer_in",
                merchant=None,
                provider_category="TRANSFER_IN",
                kind="in",
            )

    rows.sort(key=lambda r: (r.txn_date, r.external_id))
    return rows


def _pending_transaction(item_id: str, today: date) -> ProviderTransactionData:
    return ProviderTransactionData(
        external_id=_ext(item_id, "pending", 1),
        account_external_id=CREDIT,
        description="AMAZON MKTPLACE PMTS",
        amount=Decimal("68.42"),
        tx_type="purchase",
        txn_date=today,
        posting_date=None,
        merchant="Amazon",
        pending=True,
        provider_category="GENERAL_MERCHANDISE",
    )


def _delta_for_generation(item_id: str, today: date, gen: int) -> dict[str, list]:
    """The change set a single advance produces."""
    if gen <= 0:
        return {"added": [], "modified": [], "removed": []}

    if gen == 1:
        # The pending authorisation posts, in place: same external id, now posted.
        posted = ProviderTransactionData(
            external_id=_ext(item_id, "pending", 1),
            account_external_id=CREDIT,
            description="AMAZON MKTPLACE PMTS",
            amount=Decimal("68.42"),
            tx_type="purchase",
            txn_date=today - timedelta(days=1),
            posting_date=today,
            merchant="Amazon",
            pending=False,
            provider_category="GENERAL_MERCHANDISE",
        )
        fresh = ProviderTransactionData(
            external_id=_ext(item_id, "new", 1),
            account_external_id=CHECKING,
            description="WHOLE FOODS MKT #10251",
            amount=Decimal("74.18"),
            tx_type="purchase",
            txn_date=today,
            posting_date=today,
            merchant="Whole Foods Market",
            provider_category="FOOD_AND_DRINK",
        )
        return {"added": [fresh], "modified": [posted], "removed": []}

    if gen == 2:
        # A new card charge plus a refund on a previous purchase.
        charge = ProviderTransactionData(
            external_id=_ext(item_id, "new", 2),
            account_external_id=CREDIT,
            description="VERIZON WIRELESS PAYMENTS",
            amount=Decimal("85.00"),
            tx_type="purchase",
            txn_date=today,
            posting_date=today,
            merchant="Verizon Wireless",
            provider_category="BILLS_AND_UTILITIES",
        )
        refund = ProviderTransactionData(
            external_id=_ext(item_id, "new", 3),
            account_external_id=CREDIT,
            description="TARGET RETURN",
            amount=Decimal("42.99"),
            tx_type="refund",
            txn_date=today,
            posting_date=today,
            merchant="Target",
            provider_category="GENERAL_MERCHANDISE",
        )
        return {"added": [charge, refund], "modified": [], "removed": []}

    # gen >= 3: the refund is reversed and disappears.
    return {"added": [], "modified": [], "removed": [_ext(item_id, "new", 3)]}


class SandboxProvider(ProviderAdapter):
    name = "sandbox"
    display_name = "Sandbox Credit Union (simulated)"

    def __init__(self, *, page_size: int = 40) -> None:
        self.page_size = page_size

    def is_configured(self) -> bool:
        return True

    def can_schedule(self) -> bool:
        return True

    def create_link_token(self, user_id: str) -> dict[str, object]:
        return {
            "provider": self.name,
            "link_token": f"sbx-link-{_seed(user_id):08x}",
            "expires_in": 3600,
            "mode": "direct",
            "note": (
                "The sandbox provider needs no credentials; approving the request connects "
                "the simulated institution immediately."
            ),
        }

    def complete_link(self, public_token: str) -> LinkResult:
        if not public_token or not public_token.startswith("sbx-link-"):
            raise ProviderError(
                "The sandbox link token is not valid for this flow.",
                code="invalid_public_token",
                retryable=False,
            )
        seed = public_token.replace("sbx-link-", "")
        return LinkResult(
            access_token=f"sbx-access-{seed}",
            external_item_id=f"sbx-item-{seed}",
            institution_name="Sandbox Credit Union",
            institution_id="ins_sandbox_credit_union",
            history_start=date.today() - timedelta(days=_HISTORY_DAYS),
        )

    def list_accounts(self, access_token: str) -> list[ProviderAccountData]:
        if not access_token or not access_token.startswith("sbx-access-"):
            raise ProviderError(
                "The sandbox access token is not valid.",
                code="invalid_token",
                requires_reauth=True,
                retryable=False,
            )
        return [
            ProviderAccountData(
                external_id=CHECKING,
                name="Sandbox Checking",
                account_type="checking",
                balance=Decimal("1842.63"),
                mask="0042",
                currency="USD",
            ),
            ProviderAccountData(
                external_id=SAVINGS,
                name="Sandbox Savings",
                account_type="savings",
                balance=Decimal("6120.00"),
                mask="7781",
                currency="USD",
            ),
            ProviderAccountData(
                external_id=CREDIT,
                name="Sandbox Credit Card",
                account_type="credit_card",
                balance=Decimal("486.19"),
                credit_limit=Decimal("5000.00"),
                mask="9123",
                currency="USD",
            ),
        ]

    def _events(self, item_id: str, today: date, upto_gen: int) -> list[tuple[str, object]]:
        """Every event the item has produced, in order, up to a generation.

        Append-only by construction, which is what makes an offset a valid cursor: a
        caller that consumed N events stays at N even after new generations arrive.
        """
        events: list[tuple[str, object]] = [
            ("added", row) for row in _history(item_id, today)
        ]
        events.append(("added", _pending_transaction(item_id, today)))
        for gen in range(1, upto_gen + 1):
            delta = _delta_for_generation(item_id, today, gen)
            events.extend(("added", row) for row in delta["added"])
            events.extend(("modified", row) for row in delta["modified"])
            events.extend(("removed", removed_id) for removed_id in delta["removed"])
        return events

    def sync_page(
        self, access_token: str, cursor: str | None, count: int = 100
    ) -> TransactionDelta:
        item_id = access_token.replace("sbx-access-", "sbx-item-")
        today = date.today()
        current = generation_of(item_id)

        # A missing cursor means "from the beginning", which is how a forced full
        # refresh replays history (and how duplicate suppression is exercised).
        offset = 0
        if cursor:
            try:
                generation_part, _, offset_part = cursor.partition(":")
                if not generation_part.startswith("g"):
                    raise ValueError
                int(generation_part[1:])
                offset = int(offset_part) if offset_part else 0
            except (ValueError, IndexError) as exc:
                raise ProviderError(
                    "The sandbox cursor is not recognised; reconnect the institution.",
                    code="invalid_cursor",
                    retryable=False,
                ) from exc

        events = self._events(item_id, today, current)
        offset = max(0, min(offset, len(events)))
        page_size = max(1, min(count, self.page_size))
        window = events[offset : offset + page_size]
        has_more = offset + page_size < len(events)

        # The offset is always explicit: a generation-only cursor would be read back as
        # offset 0 and replay the whole history on every sync. It records what was
        # actually consumed, never offset+page_size, or a short final page would leave a
        # gap that later events fall into.
        consumed = min(offset + page_size, len(events))
        delta = TransactionDelta(
            next_cursor=f"g{current}:{consumed}",
            has_more=has_more,
        )
        for kind, payload in window:
            if kind == "removed":
                delta.removed.append(str(payload))
            else:
                assert isinstance(payload, ProviderTransactionData)
                getattr(delta, kind).append(payload)
        return delta

    def remove_item(self, access_token: str) -> None:
        _GENERATION.pop(access_token.replace("sbx-access-", "sbx-item-"), None)
