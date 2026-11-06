"""Encryption for provider credentials and other secrets at rest.

Provider access tokens are the most dangerous thing this application stores: with one, an
attacker reads a user's entire bank history. They are therefore encrypted with AES-256-GCM
before they ever reach the database, and the key is derived with HKDF so the application
secret can be rotated by supplying a dedicated ``PROVIDER_ENCRYPTION_KEY``.

The ciphertext format is ``v1:<base64(nonce || ciphertext)>``. The version prefix exists so
a future key or algorithm change can be migrated row by row instead of all at once.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

_VERSION = "v1:"
_NONCE_BYTES = 12
_KEY_INFO = b"pfc-provider-token-encryption"
_SALT = b"personal-finance-companion"


class DecryptionError(RuntimeError):
    """Raised when stored ciphertext cannot be read with the current key."""


def _master_key() -> bytes:
    material = settings.provider_encryption_key or settings.secret_key
    if not material:
        raise DecryptionError("No encryption material is configured.")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        info=_KEY_INFO,
    ).derive(material.encode("utf-8"))


def encrypt_text(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_master_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _VERSION + base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(blob: str) -> str:
    if not blob.startswith(_VERSION):
        raise DecryptionError("Unsupported ciphertext version.")
    try:
        raw = base64.b64decode(blob[len(_VERSION) :], validate=True)
    except Exception as exc:  # noqa: BLE001 - any decode failure is the same problem
        raise DecryptionError("Stored ciphertext is not valid base64.") from exc
    if len(raw) <= _NONCE_BYTES:
        raise DecryptionError("Stored ciphertext is truncated.")
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    try:
        return AESGCM(_master_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - InvalidTag and friends
        raise DecryptionError(
            "Stored ciphertext cannot be decrypted with the configured key."
        ) from exc


def mask_token(token: str | None) -> str:
    """A short, non-reversible hint that is safe to log or show in a UI."""
    if not token:
        return "(none)"
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}…{token[-4:]}"
