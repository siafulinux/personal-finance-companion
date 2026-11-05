"""Password hashing (Argon2id) and password policy."""

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password_strength(password: str) -> None:
    """Raise ValueError with a user-safe message when policy is not met."""
    min_length = max(8, settings.password_min_length)
    if len(password) < min_length:
        raise ValueError(f"Password must be at least {min_length} characters long.")
    if len(password) > 256:
        raise ValueError("Password is too long (maximum 256 characters).")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")
    if password.lower() in {"password", "password1", "letmein123"}:
        raise ValueError("That password is too common. Choose a different one.")
