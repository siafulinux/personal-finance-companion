"""Domain errors mapped to HTTP responses by the API layer."""

from __future__ import annotations


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DomainError):
    status_code = 422


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class AuthenticationError(DomainError):
    status_code = 401


class ForbiddenError(DomainError):
    status_code = 403
