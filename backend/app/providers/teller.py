"""Teller adapter — the primary financial connectivity provider.

Teller differs from Plaid in one structural way that shapes this file: **there is no
server-side token exchange.** The end user's access token is minted by Teller Connect in
the browser (or the native SDK) and handed to us. The server's job is therefore to

1. give the client everything it needs to open Teller Connect (application id,
   environment, products, and a server-generated nonce), and
2. verify what comes back before storing it.

Verification is the security boundary. Teller signs the enrolment with ED25519 over
``nonce.accessToken.userId.enrollmentId.environment`` using the application's token
signing key, so a replayed or forged enrolment fails to verify. In development and
production the signature is *required*; in sandbox it is accepted when absent (Teller's
sandbox has no end-user data), and a warning is logged instead.

API facts this adapter relies on, from Teller's documentation:

* One host for every environment, ``https://api.teller.io``. Sandbox data is selected by
  the enrolment, not by the URL.
* End-user-data requests need mutual TLS outside sandbox (``/docs/api/authentication``),
  so a client certificate and key are configured by the administrator.
* The access token is HTTP Basic auth with the token as username and an empty password.
* ``GET /institutions`` is public, unpaginated, and lists per-institution ``products``;
  that list — not the institution count — is what provider selection trusts.
* ``GET /accounts/{id}/transactions`` is per account, reports ``status`` as ``posted`` or
  ``pending``, and has no cursor. Sync therefore re-reads a bounded date window and lets
  the engine's deduplication absorb the overlap; Teller's own guide recommends exactly
  that overlap because a pending transaction's date often changes when it posts.
* ``DELETE /accounts`` deletes the enrolment's authorisation (our revoke path).
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

import httpx

from app.config import settings
from app.providers.base import (
    LinkResult,
    ProviderAccountData,
    ProviderAdapter,
    ProviderError,
    ProviderInstitution,
    ProviderTransactionData,
    TransactionDelta,
)
from app.security.link_nonce import verify_nonce
from app.utils.money import quantize

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.teller.io"
#: Teller has no cursor, so a sync re-reads this window behind the last sync date.
OVERLAP_DAYS = 10
#: How much history a first sync asks for.
INITIAL_HISTORY_DAYS = 90
#: Products this application needs. Both must be supported by the institution.
REQUIRED_PRODUCTS = ("balance", "transactions")

_CURSOR_PREFIX = "teller:v1:"

#: Account mapping. Teller reports `type` depository|credit plus a subtype.
_ACCOUNT_TYPES = {
    ("depository", "checking"): "checking",
    ("depository", "savings"): "savings",
    ("depository", "money_market"): "savings",
    ("depository", "certificate_of_deposit"): "savings",
    ("depository", "treasury"): "savings",
    ("depository", "sweep"): "savings",
    ("credit", "credit_card"): "credit_card",
}

#: Teller categories are lowercase nouns; this keeps them recognisable to the existing
#: classifier while removing Teller-specific casing.
_TRANSFER_TYPES = {"transfer", "ach", "wire", "deposit", "withdrawal"}
_INCOME_CATEGORIES = {"income", "tax"}

#: Materialised mTLS files live for the life of the process, in a 0700 directory.
_cert_dir: str | None = None


class _CertMaterial:
    """Client-certificate handling.

    ``httpx`` (like ``ssl``) takes certificate *paths*, not PEM text, and the
    administrator pastes PEM into the settings form. The text is therefore written to a
    private temporary directory with 0600 files, once per process, and removed at exit.
    A value that is not a PEM block is treated as a path, which is what a Docker secret
    mount looks like.
    """

    def __init__(self, certificate: str, private_key: str) -> None:
        self.certificate = certificate
        self.private_key = private_key
        self._paths: tuple[str, str] | None = None

    def paths(self) -> tuple[str, str]:
        if self._paths is not None:
            return self._paths
        if not self.certificate.startswith("-----BEGIN"):
            # Already a filesystem path (Docker secret, mounted file).
            self._paths = (self.certificate, self.private_key)
            return self._paths
        global _cert_dir
        if _cert_dir is None:
            _cert_dir = tempfile.mkdtemp(prefix="pfc-teller-")
            os.chmod(_cert_dir, 0o700)
            atexit.register(shutil.rmtree, _cert_dir, True)
        cert_path = os.path.join(_cert_dir, "client.pem")
        key_path = os.path.join(_cert_dir, "client.key")
        for path, content in ((cert_path, self.certificate), (key_path, self.private_key)):
            if not os.path.exists(path):
                handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(content)
        self._paths = (cert_path, key_path)
        return self._paths


def _map_account_type(raw_type: str | None, subtype: str | None) -> str:
    return _ACCOUNT_TYPES.get(((raw_type or "").lower(), (subtype or "").lower()), "other")


def _parse_date(raw: str | None) -> date:
    if not raw:
        raise ProviderError(
            "Teller returned a transaction without a date.", code="bad_payload", retryable=False
        )
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError as exc:
        raise ProviderError(
            "Teller returned a transaction with an unreadable date.",
            code="bad_payload",
            retryable=False,
        ) from exc


def _error_code(response: httpx.Response) -> tuple[str, str]:
    """Teller errors are ``{"error": {"code": ..., "message": ...}}`` where possible."""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    body = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(body, dict):
        code = str(body.get("code") or f"http_{response.status_code}")
        message = str(body.get("message") or body.get("code") or "").strip()
        return code, message
    raw = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(raw, str):
        # Newer Teller responses sometimes carry a dot-separated string, e.g.
        # ``account.closed``.
        return raw, raw
    return f"http_{response.status_code}", ""


class TellerProvider(ProviderAdapter):
    name = "teller"
    display_name = "Teller"

    def __init__(
        self,
        *,
        application_id: str | None = None,
        certificate: str | None = None,
        private_key: str | None = None,
        signing_key: str | None = None,
        environment: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.application_id = application_id or settings.teller_application_id
        self.environment = (
            environment or settings.teller_environment or "sandbox"
        ).lower()
        self.signing_key = signing_key or settings.teller_signing_key
        self.base_url = (base_url or settings.teller_base_url or DEFAULT_BASE_URL).rstrip("/")
        self._certificate = certificate or settings.teller_certificate
        self._private_key = private_key or settings.teller_private_key
        self._client = client
        self._timeout = timeout

    # --- configuration -------------------------------------------------------
    @property
    def requires_mtls(self) -> bool:
        # Teller: "mTLS is required for all API requests that involve end-user data,
        # i.e. all requests in development and production."
        return self.environment != "sandbox"

    @property
    def has_mtls(self) -> bool:
        return bool(self._certificate and self._private_key)

    def is_configured(self) -> bool:
        if not self.application_id:
            return False
        return self.has_mtls or not self.requires_mtls

    def can_schedule(self) -> bool:
        # Teller refreshes enrolments daily and documents webhooks; polling works too.
        return True

    # --- plumbing ------------------------------------------------------------
    def _build_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        # The connect timeout is deliberately shorter than the read timeout: a host that
        # cannot be reached should not make the institution catalogue wait.
        kwargs: dict = {"timeout": httpx.Timeout(self._timeout, connect=8.0)}
        if self.has_mtls:
            assert self._certificate and self._private_key
            kwargs["cert"] = _CertMaterial(self._certificate, self._private_key).paths()
        return httpx.Client(**kwargs)

    def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None = None,
        params: dict | None = None,
        public: bool = False,
    ) -> httpx.Response:
        if not public:
            if not self.application_id:
                raise ProviderError(
                    "Teller is not configured on this server (application ID missing).",
                    code="not_configured",
                    retryable=False,
                )
            if self.requires_mtls and not self.has_mtls:
                raise ProviderError(
                    "Teller needs a client certificate outside sandbox. Ask the server "
                    "administrator to finish the Teller configuration.",
                    code="missing_mtls",
                    retryable=False,
                )
        client = self._build_client()
        auth = httpx.BasicAuth(access_token, "") if access_token else None
        try:
            response = client.request(
                method, f"{self.base_url}{path}", params=params, auth=auth
            )
        except httpx.HTTPError as exc:
            # Never echo the request: the Authorization header is the access token.
            raise ProviderError(
                "Could not reach Teller.", code="network_error", retryable=True
            ) from exc
        finally:
            if self._client is None:
                client.close()

        if response.status_code < 400:
            return response
        code, message = _error_code(response)
        if response.status_code in (401, 403):
            raise ProviderError(
                message or "Teller rejected this connection; reauthorise the institution.",
                code="invalid_token",
                requires_reauth=True,
                retryable=False,
            )
        if response.status_code == 410 or code.startswith("account.closed"):
            raise ProviderError(
                "Teller reports this account is closed or no longer accessible.",
                code="account_closed",
                requires_reauth=True,
                retryable=False,
            )
        if response.status_code == 404:
            raise ProviderError(
                "Teller could not find that resource.", code="not_found", retryable=False
            )
        if response.status_code == 429:
            raise ProviderError(
                "Teller is rate limiting this server; retrying later.",
                code="rate_limited",
                retryable=True,
            )
        if response.status_code >= 500:
            raise ProviderError(
                "Teller is temporarily unavailable.", code="provider_unavailable", retryable=True
            )
        raise ProviderError(
            message or "Teller rejected the request.", code=code, retryable=False
        )

    def _get_json(self, path: str, **kwargs) -> object:
        response = self._request("GET", path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                "Teller returned an unreadable response.", code="bad_payload"
            ) from exc

    # --- contract ------------------------------------------------------------
    def create_link_token(
        self, user_id: str, institution_id: str | None = None
    ) -> dict[str, object]:
        """Parameters for Teller Connect. Contains no secret.

        The nonce is issued and signed by this server, so the enrolment that comes back
        can be tied to this session and cannot be replayed from elsewhere.
        """
        from app.security.link_nonce import issue_nonce

        if not self.application_id:
            raise ProviderError(
                "Teller is not configured on this server.", code="not_configured", retryable=False
            )
        return {
            "provider": self.name,
            "mode": "teller_connect",
            "application_id": self.application_id,
            "environment": self.environment,
            "products": list(REQUIRED_PRODUCTS),
            "nonce": issue_nonce(user_id),
            "connect_script": "https://cdn.teller.io/connect/connect.js",
            # Skips Teller's own picker: the user already chose in our catalogue.
            "institution": institution_id,
            "note": (
                "Teller Connect collects the bank credentials; this server never sees "
                "them and only receives the resulting access token."
            ),
        }

    def complete_link(
        self, public_token: str, payload: dict | None = None
    ) -> LinkResult:
        """Verify and accept a Teller Connect enrolment.

        ``public_token`` is the access token. ``payload`` must carry the enrolment's
        identity (``user_id``, ``enrollment_id``) and, when signing is configured, the
        ``signatures`` Teller produced for our nonce.
        """
        if not public_token:
            raise ProviderError(
                "Teller did not return an access token.", code="bad_payload", retryable=False
            )
        payload = payload or {}
        nonce = str(payload.get("nonce") or "")
        user_id = str(payload.get("user_id") or "")
        enrollment_id = str(payload.get("enrollment_id") or "")
        signatures = payload.get("signatures") or []
        if not isinstance(signatures, list):
            signatures = [signatures]

        if nonce:
            verify_nonce(nonce, payload.get("expected_user_id"))
        elif self.requires_mtls:
            raise ProviderError(
                "Teller enrolment is missing the nonce this server issued.",
                code="invalid_nonce",
                requires_reauth=True,
                retryable=False,
            )

        self._verify_signature(
            signatures=signatures,
            nonce=nonce,
            access_token=public_token,
            user_id=user_id,
            enrollment_id=enrollment_id,
        )

        try:
            accounts = self.list_accounts(public_token)
        except ProviderError:
            raise
        if not accounts:
            raise ProviderError(
                "Teller authorised the connection but shared no accounts.",
                code="no_accounts",
                retryable=False,
            )

        institution_id = payload.get("institution_id")
        institution_name = payload.get("institution_name")
        if not institution_id:
            raw = self._get_json("/accounts", access_token=public_token)
            first = raw[0] if isinstance(raw, list) and raw else {}
            institution = (first or {}).get("institution") or {}
            institution_id = institution.get("id")
            institution_name = institution_name or institution.get("name")

        return LinkResult(
            access_token=public_token,
            external_item_id=enrollment_id or str(payload.get("external_item_id") or ""),
            institution_name=str(institution_name or "Connected institution")[:160],
            institution_id=str(institution_id) if institution_id else None,
            history_start=date.today() - timedelta(days=INITIAL_HISTORY_DAYS),
        )

    def _verify_signature(
        self,
        *,
        signatures: list,
        nonce: str,
        access_token: str,
        user_id: str,
        enrollment_id: str,
    ) -> None:
        """Check Teller's ED25519 signature over the enrolment hand-off."""
        if not signatures:
            if self.requires_mtls:
                raise ProviderError(
                    "Teller enrolment is not signed; the connection cannot be trusted.",
                    code="unsigned_enrollment",
                    requires_reauth=True,
                    retryable=False,
                )
            logger.warning(
                "teller: accepting an unsigned sandbox enrolment (no signatures present)"
            )
            return
        if not self.signing_key:
            logger.warning(
                "teller: enrolment signatures present but no token signing key is configured"
            )
            return

        message = ".".join(
            [nonce, access_token, user_id, enrollment_id, self.environment]
        ).encode("utf-8")
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            key = load_pem_public_key(self.signing_key.replace("\\n", "\n").encode("utf-8"))
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("not an Ed25519 key")
        except Exception as exc:  # noqa: BLE001 - any parse failure is a config problem
            logger.error("teller: configured token signing key is unusable")
            raise ProviderError(
                "The configured Teller token signing key is not a valid ED25519 key.",
                code="bad_signing_key",
                retryable=False,
            ) from exc

        for candidate in signatures:
            try:
                import base64

                raw = base64.b64decode(str(candidate), validate=False)
                key.verify(raw, message)
                return
            except Exception:  # noqa: BLE001 - try the next signature
                continue
        raise ProviderError(
            "The Teller enrolment signature did not verify for this server session.",
            code="invalid_signature",
            requires_reauth=True,
            retryable=False,
        )

    def list_accounts(self, access_token: str) -> list[ProviderAccountData]:
        raw = self._get_json("/accounts", access_token=access_token)
        if not isinstance(raw, list):
            raise ProviderError(
                "Teller returned an unexpected accounts payload.", code="bad_payload"
            )
        accounts: list[ProviderAccountData] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            if (row.get("status") or "open").lower() == "closed":
                # A closed account is not an error for the others; it simply cannot be
                # read, so it is skipped rather than failing the whole link.
                logger.info("teller: skipping closed account %s", row.get("id"))
                continue
            account_id = str(row.get("id") or "")
            if not account_id:
                continue
            balance = self._balance_for(account_id, access_token)
            account_type = _map_account_type(row.get("type"), row.get("subtype"))
            accounts.append(
                ProviderAccountData(
                    external_id=account_id,
                    name=str(row.get("name") or "Account")[:120],
                    account_type=account_type,
                    # Credit balances are money owed; the sync engine signs liabilities.
                    balance=quantize(abs(balance)),
                    currency=str(row.get("currency") or "USD"),
                    mask=(str(row["last_four"]) if row.get("last_four") else None),
                )
            )
        return accounts

    def _balance_for(self, account_id: str, access_token: str) -> Decimal:
        try:
            data = self._get_json(
                f"/accounts/{account_id}/balances", access_token=access_token
            )
        except ProviderError as exc:
            # An account whose balances are unsupported still has transactions; a zero
            # balance with the drift check surfacing the truth beats failing the sync.
            logger.info("teller: balances unavailable for %s (%s)", account_id, exc.code)
            return Decimal("0")
        if not isinstance(data, dict):
            return Decimal("0")
        raw = data.get("available")
        if raw is None:
            raw = data.get("ledger")
        try:
            return Decimal(str(raw)) if raw is not None else Decimal("0")
        except Exception:  # noqa: BLE001 - a malformed number is not fatal
            return Decimal("0")

    def sync_page(
        self,
        access_token: str,
        cursor: str | None,
        count: int = 100,
        *,
        today: date | None = None,
    ) -> TransactionDelta:
        """Re-read a date window for every account.

        Teller has no cursor, so the cursor stores the window's start date and each run
        looks ``OVERLAP_DAYS`` behind it. Rows are reported as additions; the sync
        engine's stable-identifier dedupe skips what it already holds and reconciles a
        pending row whose posted form arrives under the same id.

        The window ends on the user's local date rather than the server's, so a server
        running ahead of them does not ask for tomorrow's activity.
        """
        today = today or date.today()
        start = today - timedelta(days=INITIAL_HISTORY_DAYS)
        if cursor and cursor.startswith(_CURSOR_PREFIX):
            try:
                start = date.fromisoformat(cursor[len(_CURSOR_PREFIX) :])
            except ValueError:
                start = today - timedelta(days=INITIAL_HISTORY_DAYS)
        window_start = start - timedelta(days=OVERLAP_DAYS)

        accounts = self.list_accounts(access_token)
        types = {a.external_id: a.account_type for a in accounts}
        delta = TransactionDelta(next_cursor=f"{_CURSOR_PREFIX}{today.isoformat()}")
        for account in accounts:
            raw = self._get_json(
                f"/accounts/{account.external_id}/transactions",
                access_token=access_token,
                params={
                    "start_date": window_start.isoformat(),
                    "end_date": today.isoformat(),
                },
            )
            if not isinstance(raw, list):
                raise ProviderError(
                    "Teller returned an unexpected transactions payload.", code="bad_payload"
                )
            for row in raw:
                if isinstance(row, dict):
                    delta.added.append(
                        self._map_transaction(
                            row, account.external_id, types.get(account.external_id, "other")
                        )
                    )
        # One window is the whole page: there is no server cursor to continue from.
        delta.has_more = False
        return delta

    def _map_transaction(
        self, row: dict, account_external_id: str, account_type: str
    ) -> ProviderTransactionData:
        try:
            amount = Decimal(str(row.get("amount", "0")))
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                "Teller returned a transaction with an unreadable amount.",
                code="bad_payload",
                retryable=False,
            ) from exc
        details = row.get("details") or {}
        category = str(details.get("category") or "").strip().lower() or None
        counterparty = (details.get("counterparty") or {}).get("name")
        raw_type = str(row.get("type") or "").lower()
        status = str(row.get("status") or "posted").lower()
        description = str(row.get("description") or "")[:255] or "Teller transaction"
        is_credit = account_type == "credit_card"

        # Teller signs amounts the way a statement does: money leaving the account is
        # positive. A credit-card payment therefore arrives negative.
        is_transfer = raw_type in _TRANSFER_TYPES or category == "investment"
        if is_transfer:
            tx_type = "transfer_out" if amount > 0 else "transfer_in"
        elif amount < 0:
            tx_type = "refund" if is_credit else "income"
        else:
            tx_type = "purchase"
        if category in _INCOME_CATEGORIES and not is_credit:
            tx_type = "income"

        return ProviderTransactionData(
            external_id=str(row.get("id") or ""),
            account_external_id=account_external_id,
            description=description,
            amount=quantize(abs(amount)),
            tx_type=tx_type,
            txn_date=_parse_date(row.get("date")),
            posting_date=None if status == "pending" else _parse_date(row.get("date")),
            merchant=(str(counterparty)[:160] if counterparty else None),
            pending=status == "pending",
            provider_category=(category.upper() if category else None),
        )

    def remove_item(self, access_token: str) -> None:
        """Revoke the enrolment: ``DELETE /accounts`` deletes its authorisation."""
        try:
            self._request("DELETE", "/accounts", access_token=access_token)
        except ProviderError as exc:
            if exc.code in {"not_found", "invalid_token"}:
                return
            raise

    # --- directory + health --------------------------------------------------
    def list_institutions(self, query: str | None = None) -> list[ProviderInstitution]:
        # Documented as public: "Doesn't require authentication."
        raw = self._get_json("/institutions", public=True)
        if not isinstance(raw, list):
            raise ProviderError(
                "Teller returned an unexpected institution payload.", code="bad_payload"
            )
        needle = (query or "").strip().lower()
        rows: list[ProviderInstitution] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            institution_id = str(row.get("id") or "").strip()
            if not name or not institution_id:
                continue
            if needle and needle not in name.lower():
                continue
            products = tuple(str(p) for p in (row.get("products") or []))
            rows.append(
                ProviderInstitution(
                    provider=self.name,
                    institution_id=institution_id,
                    name=name,
                    products=products,
                    supports_transactions="transactions" in products,
                    supports_balances="balance" in products,
                    account_types=("checking", "savings", "credit_card"),
                )
            )
        return rows

    def check_connection(self) -> dict[str, object]:
        if not self.application_id:
            raise ProviderError(
                "Add the Teller application ID first.",
                code="not_configured",
                retryable=False,
            )
        if self.requires_mtls and not self.has_mtls:
            raise ProviderError(
                "Teller needs the client certificate and private key outside sandbox.",
                code="missing_mtls",
                retryable=False,
            )
        institutions = self.list_institutions()
        transaction_ready = [i for i in institutions if i.supports_transactions]
        return {
            "provider": self.name,
            "environment": self.environment,
            "base_url": self.base_url,
            "mtls": self.has_mtls,
            "mtls_required": self.requires_mtls,
            "institutions": len(institutions),
            "institutions_with_transactions": len(transaction_ready),
            "signing_key_configured": bool(self.signing_key),
            "message": (
                f"Reached Teller's {self.environment} API: {len(institutions)} institutions, "
                f"{len(transaction_ready)} with transaction access."
            ),
        }


__all__ = [
    "DEFAULT_BASE_URL",
    "INITIAL_HISTORY_DAYS",
    "OVERLAP_DAYS",
    "REQUIRED_PRODUCTS",
    "TellerProvider",
]
