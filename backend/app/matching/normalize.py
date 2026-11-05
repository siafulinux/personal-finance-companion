"""Merchant normalisation used by deterministic bill matching."""

from __future__ import annotations

import re
import unicodedata

# Payment-network noise that carries no merchant identity.
_NOISE_TOKENS = {
    "pos",
    "debit",
    "credit",
    "card",
    "purchase",
    "payment",
    "pmt",
    "ach",
    "web",
    "online",
    "autopay",
    "auto",
    "recur",
    "recurring",
    "pending",
    "txn",
    "transaction",
    "store",
    "pymt",
    "pay",
    "usd",
}

_LEGAL_SUFFIXES = {"inc", "llc", "ltd", "co", "corp", "corporation", "company", "plc"}

# Card/account digits and long reference numbers must not defeat matching.
_LONG_DIGITS = re.compile(r"\b\d{4,}\b")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_merchant(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = _NON_ALNUM.sub(" ", text)
    text = _LONG_DIGITS.sub(" ", text)
    tokens = [t for t in text.split() if t and t not in _NOISE_TOKENS and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


def merchant_tokens(value: str | None) -> set[str]:
    return set(normalize_merchant(value).split())


def merchant_similarity(left: str | None, right: str | None) -> float:
    """Deterministic 0..1 similarity between two merchant strings."""
    a_norm, b_norm = normalize_merchant(left), normalize_merchant(right)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    if a_norm in b_norm or b_norm in a_norm:
        return 0.92
    a_tokens, b_tokens = set(a_norm.split()), set(b_norm.split())
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = len(a_tokens & b_tokens)
    if overlap == 0:
        return 0.0
    jaccard = overlap / len(a_tokens | b_tokens)
    containment = overlap / min(len(a_tokens), len(b_tokens))
    return round(0.5 * jaccard + 0.5 * containment, 4)
