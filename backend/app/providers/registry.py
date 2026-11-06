"""Provider registry: the one place adapters are instantiated and discovered."""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.providers.base import ProviderAdapter, ProviderError
from app.providers.plaid import PlaidProvider
from app.providers.sandbox import SandboxProvider


@lru_cache
def _adapters() -> dict[str, ProviderAdapter]:
    adapters: dict[str, ProviderAdapter] = {}
    if settings.sandbox_provider_enabled:
        adapters["sandbox"] = SandboxProvider()
    # Registered even when unconfigured so the UI can explain what is missing instead of
    # pretending the provider does not exist.
    adapters["plaid"] = PlaidProvider()
    return adapters


def get_adapter(name: str) -> ProviderAdapter:
    adapter = _adapters().get(name)
    if adapter is None:
        raise ProviderError(
            f"Unknown financial provider: {name}.", code="unknown_provider", retryable=False
        )
    return adapter


def available_providers() -> list[dict[str, object]]:
    """Everything the client needs to render a provider picker, with no secrets."""
    rows: list[dict[str, object]] = []
    for name, adapter in _adapters().items():
        configured = adapter.is_configured()
        rows.append(
            {
                "name": name,
                "display_name": adapter.display_name,
                "configured": configured,
                "usable": configured,
                "requires_credentials": name != "sandbox",
                "simulated": name == "sandbox",
                "note": (
                    "Simulated institution. No bank credentials and no network access."
                    if name == "sandbox"
                    else (
                        "Ready to use."
                        if configured
                        else "Set PLAID_CLIENT_ID and PLAID_SECRET to enable this provider."
                    )
                ),
            }
        )
    return rows


def reset_registry_cache() -> None:
    """Tests change settings; the cached adapters must follow."""
    _adapters.cache_clear()
