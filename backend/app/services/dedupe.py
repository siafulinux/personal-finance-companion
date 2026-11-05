"""Deterministic fingerprints for duplicate-free imports."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import date
from decimal import Decimal

from app.utils.money import quantize

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    text = _NON_ALNUM.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def transaction_fingerprint(
    *,
    account_id: uuid.UUID,
    txn_date: date,
    amount: Decimal,
    description: str | None,
    merchant: str | None,
    tx_type: str,
    external_id: str | None = None,
) -> str:
    """Stable 40-char key. External ids win when the source provides them."""
    if external_id:
        raw = f"ext|{account_id}|{external_id.strip()}"
    else:
        raw = "|".join(
            [
                str(account_id),
                txn_date.isoformat(),
                f"{quantize(amount):.2f}",
                normalize_text(description),
                normalize_text(merchant),
                tx_type,
            ]
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def file_fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
