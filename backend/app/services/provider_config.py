"""Administrator-managed provider configuration.

The owner of a self-hosted installation configures financial providers exactly once. This
module is that configuration: which providers exist, whether they may be used, the order
the selection service tries them in, the environment they talk to, and their credentials.

Three rules shape the design.

**Credentials are ciphertext.** They are stored as AES-256-GCM ciphertext with a key that
comes from ``PROVIDER_ENCRYPTION_KEY`` (or is derived from ``SECRET_KEY``), never from the
database they protect. A database dump therefore does not hand out Plaid's secret.

**The environment still works.** ``PLAID_CLIENT_ID`` / ``PLAID_SECRET`` /
``TELLER_APPLICATION_ID`` configure a deployment without ever opening the admin screen,
which is what a ``.env``-driven Docker install wants. A value saved on the admin screen
wins, because that is the value the owner last chose deliberately; everything it does not
set falls through to the environment.

**Nothing secret is ever serialised.** :func:`describe` returns booleans, counts and
masked hints only. The UI can therefore show "secret configured" without the browser, the
Android client, an ordinary user or a log line ever seeing the value.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PROVIDER_NAMES, ProviderConfig, ServerSettings, User
from app.models.server import SETTINGS_ID
from app.security.secrets import DecryptionError, decrypt_text, encrypt_text, mask_token
from app.services.errors import ValidationError
from app.services.server_setup import is_admin
from app.utils.dates import utc_now

logger = logging.getLogger(__name__)

PROVIDER_LABELS: dict[str, str] = {"teller": "Teller", "plaid": "Plaid"}

#: Environments each provider knows. Both use the same vocabulary so one UI control and
#: one validation rule cover them; the adapter maps the word to its own host.
PROVIDER_ENVIRONMENTS: dict[str, tuple[str, ...]] = {
    "teller": ("sandbox", "development", "production"),
    "plaid": ("sandbox", "development", "production"),
}

#: Teller is primary: it is tried first for every institution it supports.
DEFAULT_PRIORITY: dict[str, int] = {"teller": 10, "plaid": 20}
DEFAULT_ENVIRONMENT: dict[str, str] = {"teller": "sandbox", "plaid": "sandbox"}


@dataclass(frozen=True)
class CredentialField:
    """One configurable field, described well enough to render a form from."""

    key: str
    label: str
    secret: bool
    required: bool
    help: str
    multiline: bool = False
    placeholder: str | None = None


CREDENTIAL_FIELDS: dict[str, tuple[CredentialField, ...]] = {
    "teller": (
        CredentialField(
            key="application_id",
            label="Teller application ID",
            secret=False,
            required=True,
            help=(
                "From https://teller.io → Applications. Teller Connect uses it to show "
                "your app's name in the bank approval sheet."
            ),
            placeholder="app_xxxxxxxxxxxx",
        ),
        CredentialField(
            key="certificate",
            label="Client certificate (PEM)",
            secret=True,
            required=False,
            help=(
                "Teller's API is mutually authenticated outside sandbox. Paste the "
                "certificate Teller issued for this application."
            ),
            multiline=True,
        ),
        CredentialField(
            key="private_key",
            label="Client private key (PEM)",
            secret=True,
            required=False,
            help="Paste the private key that matches the certificate above.",
            multiline=True,
        ),
    ),
    "plaid": (
        CredentialField(
            key="client_id",
            label="Plaid client ID",
            secret=False,
            required=True,
            help="From https://dashboard.plaid.com/team/keys.",
        ),
        CredentialField(
            key="secret",
            label="Plaid secret",
            secret=True,
            required=True,
            help=(
                "The secret for the selected environment. Sandbox secrets work without "
                "production approval."
            ),
        ),
    ),
}

#: Where each field falls back to when the database holds no value.
_ENV_FIELDS: dict[str, dict[str, str]] = {
    "teller": {
        "application_id": "teller_application_id",
        "certificate": "teller_certificate",
        "private_key": "teller_private_key",
    },
    "plaid": {
        "client_id": "plaid_client_id",
        "secret": "plaid_secret",
    },
}

_ENV_ENVIRONMENT: dict[str, str] = {
    "teller": "teller_environment",
    "plaid": "plaid_environment",
}

_ENV_ENABLED: dict[str, str] = {
    "teller": "teller_provider_enabled",
    "plaid": "plaid_provider_enabled",
}

#: A PEM is a few kilobytes; anything far larger is a mistake, not a certificate.
_MAX_SECRET_LENGTH = 20_000
_MAX_PUBLIC_LENGTH = 500


@dataclass(frozen=True)
class ProviderState:
    """The effective configuration of one provider, with secrets decrypted.

    Only server-side code ever holds one of these. ``public`` and ``secret`` are split so
    a caller that only needs to build a request cannot accidentally serialise the wrong
    half.
    """

    name: str
    label: str
    enabled: bool
    priority: int
    environment: str
    public: dict[str, str]
    secret: dict[str, str]
    #: "database", "environment" or "none" — where the effective values came from.
    source: str
    #: True when every required field is present and readable.
    configured: bool
    missing: tuple[str, ...] = ()
    #: Why the stored ciphertext could not be read, when that is the problem.
    problem: str | None = None

    def credential(self, key: str) -> str | None:
        value = self.public.get(key) or self.secret.get(key)
        return value or None


# ---------------------------------------------------------------------- plumbing
def _env_map(name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, attribute in _ENV_FIELDS.get(name, {}).items():
        raw = getattr(settings, attribute, None)
        if raw:
            values[key] = str(raw)
    return values


def _env_environment(name: str) -> str:
    raw = getattr(settings, _ENV_ENVIRONMENT.get(name, ""), None)
    default = DEFAULT_ENVIRONMENT.get(name, "sandbox")
    candidate = str(raw or default).lower()
    return candidate if candidate in PROVIDER_ENVIRONMENTS.get(name, ()) else default


def _env_enabled(name: str) -> bool:
    attribute = _ENV_ENABLED.get(name)
    return bool(getattr(settings, attribute, True)) if attribute else True


def _decrypt_payload(row: ProviderConfig | None) -> tuple[dict[str, str], str | None]:
    """Return the stored credential map and, if unreadable, why."""
    if row is None or not row.credentials_ciphertext:
        return {}, None
    try:
        raw = decrypt_text(row.credentials_ciphertext)
    except DecryptionError as exc:
        # A rotated key is an operational problem, not a crash: report it through the
        # status endpoint so the owner can re-enter the values.
        logger.warning("provider credentials unreadable provider=%s", row.name)
        return {}, str(exc)
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}, "Stored credentials are not valid JSON."
    if not isinstance(payload, dict):
        return {}, "Stored credentials have an unexpected shape."
    return {str(k): str(v) for k, v in payload.items() if v is not None}, None


def _get_row(db: Session, name: str) -> ProviderConfig | None:
    return db.get(ProviderConfig, name)


def ensure_defaults(db: Session) -> None:
    """Create the two rows on an installation that predates this feature.

    The migration seeds them too; this keeps a database restored from an older dump or a
    test fixture honest without requiring an out-of-band SQL step.
    """
    created = False
    for name in PROVIDER_NAMES:
        if _get_row(db, name) is None:
            db.add(
                ProviderConfig(
                    name=name,
                    enabled=_env_enabled(name),
                    priority=DEFAULT_PRIORITY.get(name, 100),
                    environment=_env_environment(name),
                )
            )
            created = True
    if created:
        db.flush()


def resolve(db: Session, name: str) -> ProviderState:
    """Effective configuration: database values over environment values."""
    row = _get_row(db, name)
    stored, problem = _decrypt_payload(row)
    env_values = _env_map(name)

    public: dict[str, str] = {}
    secret: dict[str, str] = {}
    missing: list[str] = []
    for spec in CREDENTIAL_FIELDS.get(name, ()):
        value = stored.get(spec.key) or env_values.get(spec.key)
        if value:
            (secret if spec.secret else public)[spec.key] = value
        elif spec.required:
            missing.append(spec.key)

    if row is not None:
        enabled = bool(row.enabled)
        priority = int(row.priority)
        environment = row.environment or DEFAULT_ENVIRONMENT.get(name, "sandbox")
    else:
        enabled = _env_enabled(name)
        priority = DEFAULT_PRIORITY.get(name, 100)
        environment = _env_environment(name)

    if stored:
        source = "database"
    elif env_values:
        source = "environment"
    else:
        source = "none"

    return ProviderState(
        name=name,
        label=PROVIDER_LABELS.get(name, name.title()),
        enabled=enabled,
        priority=priority,
        environment=environment,
        public=public,
        secret=secret,
        source=source,
        configured=not missing and problem is None,
        missing=tuple(missing),
        problem=problem,
    )


def resolve_all(db: Session) -> list[ProviderState]:
    ensure_defaults(db)
    return sorted((resolve(db, name) for name in PROVIDER_NAMES), key=lambda s: s.priority)


def usable(db: Session, name: str) -> bool:
    state = resolve(db, name)
    return state.enabled and state.configured


def credentials_for(db: Session, name: str) -> dict[str, str]:
    """The decrypted credential map an adapter is constructed with.

    Kept as one flat dict so adapters stay ignorant of the storage schema; each adapter
    reads only the keys it declares.
    """
    state = resolve(db, name)
    return {**state.public, **state.secret}


# ------------------------------------------------------------------------ reading
def describe(db: Session, name: str) -> dict[str, Any]:
    """A safe view of one provider for the admin screen. No secret leaves this call."""
    state = resolve(db, name)
    row = _get_row(db, name)
    values = {**state.public, **state.secret}
    return {
        "name": state.name,
        "label": state.label,
        "enabled": state.enabled,
        "priority": state.priority,
        "environment": state.environment,
        "environments": list(PROVIDER_ENVIRONMENTS.get(name, ())),
        "configured": state.configured,
        "usable": state.enabled and state.configured,
        "source": state.source,
        "missing": list(state.missing),
        "problem": state.problem,
        # Public (non-secret) values are shown as-is; secrets as a masked hint only.
        "fields": [
            {
                "key": spec.key,
                "label": spec.label,
                "secret": spec.secret,
                "required": spec.required,
                "multiline": spec.multiline,
                "placeholder": spec.placeholder,
                "help": spec.help,
                "present": bool(values.get(spec.key)),
                "value": None if spec.secret else values.get(spec.key),
                "hint": mask_token(values.get(spec.key)) if spec.secret and values.get(spec.key) else None,
            }
            for spec in CREDENTIAL_FIELDS.get(name, ())
        ],
        "last_test": (
            {
                "at": row.last_tested_at,
                "ok": row.last_test_ok,
                "message": row.last_test_message,
                "detail": row.last_test_detail or {},
            }
            if row is not None and row.last_tested_at is not None
            else None
        ),
    }


def overview(db: Session) -> dict[str, Any]:
    ensure_defaults(db)
    providers = [describe(db, name) for name in PROVIDER_NAMES]
    providers.sort(key=lambda p: p["priority"])
    primary = next((p["name"] for p in providers if p["usable"]), None)
    return {
        "providers": providers,
        "auto_select": auto_select_enabled(db),
        "primary": primary,
        "any_usable": primary is not None,
        "sandbox_available": bool(settings.sandbox_provider_enabled),
    }


# ------------------------------------------------------------------------ writing
def _clean(value: Any, spec: CredentialField) -> str:
    text = str(value or "").strip()
    limit = _MAX_SECRET_LENGTH if spec.secret else _MAX_PUBLIC_LENGTH
    if len(text) > limit:
        raise ValidationError(f"{spec.label} is too long.")
    return text


def update_provider(
    db: Session,
    actor: User,
    name: str,
    *,
    enabled: bool | None = None,
    priority: int | None = None,
    environment: str | None = None,
    credentials: dict[str, Any] | None = None,
) -> ProviderConfig:
    """Apply an administrator's change. Returns the row, without its ciphertext.

    Credential semantics: a key that is present and non-empty sets the value; a key that
    is present and empty clears it; an absent key is left alone. That lets a form submit
    only what changed, so saving the page never wipes a secret the owner did not retype.
    """
    if not is_admin(db, actor):
        from app.services.errors import ForbiddenError

        raise ForbiddenError("Only the server administrator can configure providers.")
    if name not in PROVIDER_NAMES:
        raise ValidationError(f"Unknown financial provider: {name}.")

    ensure_defaults(db)
    row = _get_row(db, name)
    assert row is not None  # ensured above

    changed: list[str] = []

    if environment is not None:
        candidate = environment.strip().lower()
        if candidate not in PROVIDER_ENVIRONMENTS[name]:
            raise ValidationError(
                f"{PROVIDER_LABELS[name]} does not have a {candidate!r} environment."
            )
        if row.environment != candidate:
            row.environment = candidate
            changed.append("environment")

    if priority is not None:
        if not 0 <= priority <= 1000:
            raise ValidationError("Provider priority must be between 0 and 1000.")
        if row.priority != priority:
            row.priority = int(priority)
            changed.append("priority")

    if enabled is not None and bool(row.enabled) != bool(enabled):
        row.enabled = bool(enabled)
        changed.append("enabled")

    if credentials:
        stored, problem = _decrypt_payload(row)
        if problem is not None:
            # The ciphertext cannot be read, so there is nothing to merge into. Start
            # clean instead of silently keeping a value nobody can decrypt.
            stored = {}
        specs = {spec.key: spec for spec in CREDENTIAL_FIELDS.get(name, ())}
        for key, raw in credentials.items():
            spec = specs.get(key)
            if spec is None:
                raise ValidationError(f"{PROVIDER_LABELS[name]} has no {key!r} credential.")
            text = _clean(raw, spec)
            if text:
                if stored.get(key) != text:
                    stored[key] = text
                    changed.append(key)
            elif key in stored:
                stored.pop(key)
                changed.append(key)
        if changed:
            row.credentials_ciphertext = encrypt_text(json.dumps(stored)) if stored else None
            # A new credential invalidates the last test: it proved the old one.
            if set(changed) & set(specs):
                row.last_test_ok = None
                row.last_test_message = None
                row.last_test_detail = None

    if changed:
        row.updated_at = utc_now()
    db.flush()
    # Never log values: only which fields moved.
    logger.info(
        "provider config updated provider=%s fields=%s admin=%s",
        name,
        ",".join(sorted(set(changed))) or "none",
        actor.id,
    )
    return row


def record_test(
    db: Session, name: str, *, ok: bool, message: str, detail: dict[str, Any] | None = None
) -> None:
    # A test can be run on an installation whose rows predate this feature, so the row
    # is created on demand rather than the result being silently dropped.
    ensure_defaults(db)
    row = _get_row(db, name)
    if row is None:
        return
    row.last_tested_at = utc_now()
    row.last_test_ok = ok
    row.last_test_message = message[:1000]
    row.last_test_detail = detail or None
    db.flush()


def clear_test_result(db: Session, name: str) -> None:
    row = _get_row(db, name)
    if row is None:
        return
    row.last_tested_at = None
    row.last_test_ok = None
    row.last_test_message = None
    row.last_test_detail = None
    db.flush()


# --------------------------------------------------------------------- auto-select
def auto_select_enabled(db: Session) -> bool:
    row = db.get(ServerSettings, SETTINGS_ID)
    if row is None:
        return bool(settings.provider_auto_select)
    return bool(row.provider_auto_select)


def set_auto_select(db: Session, actor: User, enabled: bool) -> bool:
    from app.services.errors import ForbiddenError

    if not is_admin(db, actor):
        raise ForbiddenError("Only the server administrator can change provider selection.")
    row = db.get(ServerSettings, SETTINGS_ID)
    if row is None:
        row = ServerSettings(id=SETTINGS_ID, server_name=settings.app_name)
        db.add(row)
    row.provider_auto_select = bool(enabled)
    db.flush()
    logger.info("provider auto-select set to %s by admin=%s", bool(enabled), actor.id)
    return bool(row.provider_auto_select)


__all__ = [
    "CREDENTIAL_FIELDS",
    "DEFAULT_PRIORITY",
    "PROVIDER_ENVIRONMENTS",
    "PROVIDER_LABELS",
    "CredentialField",
    "ProviderState",
    "auto_select_enabled",
    "clear_test_result",
    "credentials_for",
    "describe",
    "ensure_defaults",
    "overview",
    "record_test",
    "resolve",
    "resolve_all",
    "set_auto_select",
    "update_provider",
    "usable",
]
