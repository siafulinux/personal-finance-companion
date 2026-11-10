"""Institution-first provider selection.

An ordinary user never chooses a provider. They type the name of their bank or app, pick
it from one list, and the server decides — once per connection — which aggregator can
actually serve it. This module is that decision.

The rules, in order:

1. Only providers the administrator enabled *and* configured take part.
2. Providers are tried by their configured priority: Teller first, Plaid second by
   default. The administrator can reorder them without touching code.
3. A provider may only be chosen for an institution whose directory entry says it can
   supply **both** transactions and balances. Being listed is not enough: Teller and
   Plaid both publish per-institution products precisely because coverage varies.
4. If no provider meets the requirement, the institution is reported as unavailable with
   the reason. It is never handed to a provider that would fail later.
5. If automatic selection is switched off, only the highest-priority usable provider is
   considered, so an administrator can pin one aggregator deliberately.

Results are cached briefly (``PROVIDER_INSTITUTION_CACHE_SECONDS``) because the
directory is large and changes slowly. The key a client receives encodes only the
institution, never the provider, so the user-facing layer has nothing provider-specific
to leak.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.providers.base import ProviderError, ProviderInstitution
from app.providers.registry import adapter_for
from app.services import provider_config
from app.services.errors import ValidationError

logger = logging.getLogger(__name__)

#: The simulated institution is always last: it exists for development and demos.
SANDBOX_PRIORITY = 900

_CACHE: dict[tuple[str, str], tuple[float, list[ProviderInstitution]]] = {}
#: A provider that just failed is remembered briefly. Without this, one unreachable host
#: makes every catalogue request wait for its connect timeout before degrading.
_FAILURES: dict[tuple[str, str], tuple[float, ProviderError]] = {}
_FAILURE_TTL_SECONDS = 60

_NOISE = re.compile(
    r"\b(n\.?a\.?|bank|banking|financial|federal|savings|checking|loan|loans|mortgage|"
    r"credit union|national association|association|trust|company|corp|corporation|inc|"
    r"llc|fsb|ssb|group|holdings|securities|services|usa|us)\b",
    re.IGNORECASE,
)


def _slug(name: str) -> str:
    """A provider-neutral identity for an institution name.

    Teller and Plaid identify the same bank differently (``chase`` vs ``ins_56``), so the
    catalogue is grouped by a normalised name. Dropping bank-ish noise makes "USAA
    Federal Savings Bank" and "USAA" the same entry.
    """
    cleaned = _NOISE.sub(" ", name.lower())
    return re.sub(r"[^a-z0-9]+", "", cleaned) or re.sub(r"[^a-z0-9]+", "", name.lower())


def institution_key(name: str) -> str:
    return "inst_" + hashlib.sha256(_slug(name).encode("utf-8")).hexdigest()[:12]


def clear_cache() -> None:
    _CACHE.clear()
    _FAILURES.clear()


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    name: str
    provider: str | None
    provider_institution_id: str | None
    available: bool
    reason: str | None = None
    simulated: bool = False
    account_types: tuple[str, ...] = ()
    alternatives: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        # Deliberately no provider name: the client shows institutions, not vendors.
        return {
            "key": self.key,
            "name": self.name,
            "available": self.available,
            "reason": self.reason,
            "simulated": self.simulated,
            "account_types": list(self.account_types),
        }


@dataclass
class Catalog:
    entries: list[CatalogEntry]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "institutions": [e.as_dict() for e in self.entries],
            "warnings": self.warnings,
        }


# ------------------------------------------------------------------ provider order
def _ordered_providers(db: Session) -> tuple[list[str], bool]:
    """Usable providers in priority order, plus whether auto-selection is on."""
    auto = provider_config.auto_select_enabled(db)
    states = provider_config.resolve_all(db)
    usable = [s for s in states if s.enabled and s.configured]
    names = [s.name for s in usable]
    if settings.sandbox_provider_enabled:
        names.append("sandbox")
    if not auto and usable:
        names = [usable[0].name]
    return names, auto


def _institutions_for(db: Session, provider: str, query: str | None) -> list[ProviderInstitution]:
    """Cached directory lookup. One entry per (provider, query)."""
    cache_key = (provider, (query or "").strip().lower())
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < settings.provider_institution_cache_seconds:
        return cached[1]
    failed = _FAILURES.get(cache_key)
    if failed and now - failed[0] < _FAILURE_TTL_SECONDS:
        raise failed[1]
    adapter = adapter_for(db, provider)
    try:
        rows = adapter.list_institutions(query or None)
    except ProviderError as exc:
        _FAILURES[cache_key] = (now, exc)
        raise
    _CACHE[cache_key] = (now, rows)
    _FAILURES.pop(cache_key, None)
    return rows


# ---------------------------------------------------------------------- catalogue
def catalog(db: Session, query: str | None = None, *, limit: int = 40) -> Catalog:
    """Institutions matching ``query``, each resolved to at most one provider."""
    providers, auto = _ordered_providers(db)
    groups: dict[str, list[tuple[str, ProviderInstitution]]] = {}
    warnings: list[str] = []

    for provider in providers:
        try:
            rows = _institutions_for(db, provider, query)
        except ProviderError as exc:
            # A provider being down must not empty the list for the others. The warning is
            # deliberately provider-neutral: an ordinary user has no business learning
            # which aggregator this server uses. The admin coverage endpoint names names.
            warnings.append(
                "Some institutions may be missing because a connection service could not "
                "be reached just now."
            )
            logger.info("catalog: %s unavailable (%s)", provider, exc.code)
            continue

        for row in rows:
            groups.setdefault(_slug(row.name), []).append((provider, row))

    entries: list[CatalogEntry] = []
    for candidates in groups.values():
        # Candidates arrive in priority order, because providers were walked in order.
        chosen: tuple[str, ProviderInstitution] | None = None
        capability_holder: tuple[str, ProviderInstitution] | None = None
        for provider, row in candidates:
            if row.supports(transactions=True, balances=True):
                chosen = (provider, row)
                break
            if capability_holder is None:
                capability_holder = (provider, row)

        if chosen is not None:
            provider, row = chosen
            entries.append(
                CatalogEntry(
                    key=institution_key(row.name),
                    name=row.name,
                    provider=provider,
                    provider_institution_id=row.institution_id,
                    available=True,
                    simulated=provider == "sandbox",
                    account_types=row.account_types,
                )
            )
            continue

        # Listed, but without the data this application needs. Say so plainly instead of
        # offering a connection that would fail after the user has typed a password.
        provider, row = capability_holder or candidates[0]
        missing: list[str] = []
        if not row.supports_transactions:
            missing.append("transaction history")
        if not row.supports_balances:
            missing.append("balances")
        reason = (
            f"This institution cannot currently share {' or '.join(missing)} with this "
            "server. You can still add it manually or import a statement."
        )
        if not auto:
            reason = (
                "The server administrator has pinned a single provider and it cannot "
                "serve this institution. " + reason
            )
        entries.append(
            CatalogEntry(
                key=institution_key(row.name),
                name=row.name,
                provider=provider,
                provider_institution_id=row.institution_id,
                available=False,
                reason=reason,
                simulated=provider == "sandbox",
                account_types=row.account_types,
            )
        )

    # Available institutions first, then alphabetically: the realistic choice is on top.
    entries.sort(key=lambda e: (not e.available, e.name.lower()))
    return Catalog(entries=entries[:limit], warnings=list(dict.fromkeys(warnings)))


def coverage(db: Session, names: list[str]) -> dict[str, Any]:
    """Per-provider support for specific institutions, for the administrator's report.

    This bypasses the "one provider per institution" reduction deliberately: the point
    is to show *why* the selection chose what it chose, including the providers that
    could not serve the institution.
    """
    providers, auto = _ordered_providers(db)
    report: list[dict[str, Any]] = []
    for name in names:
        needle = name.strip()
        if not needle:
            continue
        rows: list[dict[str, Any]] = []
        for provider in [*provider_config.PROVIDER_NAMES, "sandbox"]:
            if provider not in providers and provider != "sandbox":
                # Still worth reporting as "not available on this server".
                state = provider_config.resolve(db, provider) if provider in provider_config.PROVIDER_NAMES else None
                rows.append(
                    {
                        "provider": provider,
                        "label": provider_config.PROVIDER_LABELS.get(provider, provider.title()),
                        "available": False,
                        "reason": "disabled or not configured on this server"
                        if state is not None
                        else "not enabled",
                        "match": None,
                    }
                )
                continue
            if provider == "sandbox" and not settings.sandbox_provider_enabled:
                continue
            try:
                found = _institutions_for(db, provider, needle)
            except ProviderError as exc:
                rows.append(
                    {
                        "provider": provider,
                        "label": provider_config.PROVIDER_LABELS.get(provider, provider.title()),
                        "available": True,
                        "reason": f"directory unavailable ({exc.code})",
                        "match": None,
                    }
                )
                continue
            match = next((i for i in found if _slug(i.name) == _slug(needle)), None)
            if match is None:
                # Fall back to a name containing the query, so "USAA" finds
                # "USAA Federal Savings Bank".
                match = next((i for i in found if needle.lower() in i.name.lower()), None)
            rows.append(
                {
                    "provider": provider,
                    "label": provider_config.PROVIDER_LABELS.get(provider, provider.title()),
                    "available": True,
                    "reason": None if match else "not listed",
                    "match": (
                        {
                            "institution_id": match.institution_id,
                            "name": match.name,
                            "products": list(match.products),
                            "transactions": match.supports_transactions,
                            "balances": match.supports_balances,
                            "account_types": list(match.account_types),
                            "note": match.note,
                        }
                        if match
                        else None
                    ),
                }
            )
        report.append({"query": needle, "providers": rows})
    return {"auto_select": auto, "institutions": report}


# ----------------------------------------------------------------------- selection
@dataclass(frozen=True)
class Selection:
    entry: CatalogEntry
    provider: str
    institution: ProviderInstitution

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.entry.key,
            "name": self.entry.name,
            "available": self.entry.available,
            "reason": self.entry.reason,
        }


def select(db: Session, name: str, *, key: str | None = None) -> Selection:
    """Resolve an institution the client picked to the provider that must serve it.

    The client sends the name it displayed plus the key it was given. The catalogue is
    rebuilt (from cache) and re-reduced, so a directory change between browsing and
    connecting is handled explicitly rather than by trusting a stale choice.
    """
    result = catalog(db, name)
    wanted = key or institution_key(name)
    entry = next(
        (e for e in result.entries if e.key == wanted),
        None,
    )
    if entry is None:
        # The key is derived from the name, so this is only reachable when the directory
        # no longer lists the institution at all.
        raise ValidationError(
            f"{name} is not currently available from this server's financial data "
            "providers. You can still add the account manually or import a statement."
        )
    if not entry.available or entry.provider is None or entry.provider_institution_id is None:
        raise ValidationError(entry.reason or f"{entry.name} is not currently supported.")

    adapter = adapter_for(db, entry.provider)
    rows = _institutions_for(db, entry.provider, name)
    institution = next(
        (r for r in rows if r.institution_id == entry.provider_institution_id), None
    )
    if institution is None:
        raise ValidationError(f"{entry.name} is no longer listed by this server.")
    return Selection(entry=entry, provider=entry.provider, institution=institution)


def start_link(db: Session, user_id: str, name: str, *, key: str | None = None) -> dict[str, Any]:
    """Begin the provider's own authorisation flow for one institution.

    Returns the client-side parameters (a Teller Connect configuration or a Plaid link
    token) plus the provider-neutral institution details the UI shows. Nothing secret is
    included, and the provider's name is not returned: the client does not need it to
    finish the flow, because ``finish_link`` takes the institution again.
    """
    selection = select(db, name, key=key)
    adapter = adapter_for(db, selection.provider)
    if not adapter.is_configured():
        raise ValidationError(
            "Financial connections are not configured on this server yet. "
            "Ask the administrator to finish the provider setup."
        )
    params = adapter.create_link_token(
        str(user_id), institution_id=selection.institution.institution_id
    )
    return {
        "connection": selection.as_dict(),
        "provider": selection.provider,
        "flow": {
            key: value
            for key, value in params.items()
            # ``provider`` is an implementation detail; the rest is what the client uses.
            if key not in {"provider", "mode"}
        },
        "mode": params.get("mode"),
    }


def finish_link(
    db: Session,
    user,
    name: str,
    *,
    key: str | None = None,
    public_token: str,
    payload: dict[str, Any] | None = None,
):
    """Complete the flow and connect, on the provider the catalogue selected."""
    from app.services.sync import connect_institution

    selection = select(db, name, key=key)
    enriched = dict(payload or {})
    enriched.setdefault("institution_id", selection.institution.institution_id)
    enriched.setdefault("institution_name", selection.institution.name)
    # The nonce must belong to the signed-in user, not to whoever the client claims.
    enriched["expected_user_id"] = str(user.id)
    return connect_institution(
        db,
        user,
        selection.provider,
        public_token,
        payload=enriched,
    )


__all__ = [
    "Catalog",
    "CatalogEntry",
    "Selection",
    "catalog",
    "clear_cache",
    "coverage",
    "finish_link",
    "institution_key",
    "select",
    "start_link",
]
