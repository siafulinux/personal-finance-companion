"""Exact decimal helpers. Money is never represented as float inside the backend."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value: object, field: str = "amount") -> Decimal:
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{field} is empty")
        try:
            dec = Decimal(cleaned)
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValueError(f"{field} is not a valid number") from exc
    elif isinstance(value, float):
        # Floats arrive only from legacy data; convert via repr to avoid binary noise.
        dec = Decimal(repr(value))
    else:
        raise ValueError(f"{field} must be a number")
    if not dec.is_finite():
        raise ValueError(f"{field} must be finite")
    return dec


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def money(value: object) -> Decimal:
    return quantize(to_decimal(value))


def clamp_zero(value: Decimal) -> Decimal:
    return value if value > ZERO else ZERO


def format_money(value: object) -> str:
    """Render an amount for human-readable explanations, e.g. "$180.00"."""
    return f"${quantize(to_decimal(value)):,.2f}"
