"""Provider registry: the one place adapters are instantiated and discovered.

Two construction paths exist on purpose:

* :func:`get_adapter` builds an adapter from environment settings only. It is what the
  tests and any caller without a database session use, and it keeps the original
  behaviour of this module.
* :func:`adapter_for` builds one from the administrator's saved configuration (which
  itself falls back to the environment). Everything the API and the sync engine do goes
  through this, so rotating a credential on the admin screen takes effect on the next
  request without a restart.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from app.config import settings
from app.providers.base import ProviderAdapter, ProviderError
from app.providers.plaid import PlaidProvider
from app.providers.sandbox import SandboxProvider
from app.providers.teller import TellerProvider


@lru_cache
def _adapters() -> dict[str, ProviderAdapter]:
    adapters: dict[str, ProviderAdapter] = {}
    if settings.sandbox_provider_enabled:
        adapters["sandbox"] = SandboxProvider()
    # Registered even when unconfigured so the UI can explain what is missing instead of
    # pretending the provider does not exist. Order matters: it is the default priority.
    adapters["teller"] = TellerProvider()
    adapters["plaid"] = PlaidProvider()
    return adapters


def build_adapter(
    name: str, *, credentials: dict[str, str] | None = None, environment: str | None = None
) -> ProviderAdapter:
    """Construct one adapter. Unknown names are a caller error, not a credential error."""
    values = credentials or {}
    if name == "sandbox":
        if not settings.sandbox_provider_enabled:
            raise ProviderError(
                "The simulated institution is disabled on this server.",
                code="disabled",
                retryable=False,
            )
        return SandboxProvider()
    if name == "teller":
        return TellerProvider(
            application_id=values.get("application_id"),
            certificate=values.get("certificate"),
            private_key=values.get("private_key"),
            signing_key=values.get("signing_key"),
            environment=environment,
        )
    if name == "plaid":
        return PlaidProvider(
            client_id=values.get("client_id"),
            secret=values.get("secret"),
            environment=environment,
        )
    raise ProviderError(
        f"Unknown financial provider: {name}.", code="unknown_provider", retryable=False
    )


def adapter_for(db: Session, name: str) -> ProviderAdapter:
    """An adapter configured from the database (falling back to the environment)."""
    from app.services.provider_config import credentials_for, resolve

    state = resolve(db, name)
    return build_adapter(
        name, credentials=credentials_for(db, name), environment=state.environment
    )


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
                        else "A server administrator must configure this provider."
                    )
                ),
            }
        )
    return rows


def reset_registry_cache() -> None:
    """Tests change settings; the cached adapters must follow."""
    _adapters.cache_clear()


__all__ = [
    "adapter_for",
    "available_providers",
    "build_adapter",
    "get_adapter",
    "reset_registry_cache",
]
