"""Logging with redaction of financial data and secrets."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "token",
    "access_token",
    "authorization",
    "cookie",
    "secret",
    "secret_key",
    "amount",
    "balances",
    "opening_balance",
    "minimum_balance_buffer",
    "merchant",
    "description",
    "notes",
}
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


class RedactionFilter(logging.Filter):
    """Defence in depth: keeps account ids out of log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        record.msg = _UUID_RE.sub("<id>", message)
        record.args = ()
        return True


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Explicit helper for structured logging of request metadata."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        out[key] = "***" if key.lower() in _SENSITIVE_KEYS else value
    return out


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # Never let SQLAlchemy echo parameter values (financial amounts).
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
