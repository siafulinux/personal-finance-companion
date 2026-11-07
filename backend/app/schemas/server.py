"""Server configuration, first-run setup and pairing schemas."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import APIModel


def normalize_base_url(value: str | None) -> str | None:
    """Accept only absolute http(s) URLs; return them without a trailing slash.

    A self-hosted server is reached by whatever address its owner chose, so the
    scheme and host are deliberately not restricted beyond http/https — but a
    value that is not an absolute URL is rejected rather than stored and later
    used to build broken links.
    """
    if value is None:
        return None
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a full URL such as https://finance.example.com")
    return cleaned


class SetupRequest(APIModel):
    """The first-run wizard: names the server and creates its administrator."""

    server_name: str = Field(min_length=1, max_length=120)
    admin_email: EmailStr
    admin_name: str = Field(min_length=1, max_length=120)
    admin_password: str = Field(min_length=8, max_length=256)
    #: Whether other people may sign up later. Closed by default.
    registration_enabled: bool = False
    #: Optional public address, e.g. https://finance.example.com. Empty means
    #: "derive it from the request", which is right for a LAN install.
    public_base_url: str | None = Field(default=None, max_length=255)

    @field_validator("server_name", "admin_name")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required.")
        return cleaned

    @field_validator("public_base_url")
    @classmethod
    def _clean_url(cls, value: str | None) -> str | None:
        return normalize_base_url(value)


class ServerSettingsUpdate(APIModel):
    """Partial update of installation settings. Only the administrator may send it."""

    server_name: str | None = Field(default=None, min_length=1, max_length=120)
    registration_enabled: bool | None = None
    public_base_url: str | None = Field(default=None, max_length=255)

    @field_validator("server_name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Server name cannot be empty.")
        return cleaned

    @field_validator("public_base_url")
    @classmethod
    def _clean_url(cls, value: str | None) -> str | None:
        # An empty string is how a client clears a previously set public URL.
        return normalize_base_url(value)


class PairingCreate(APIModel):
    label: str | None = Field(default=None, max_length=120)


class PairingRequest(APIModel):
    token: str = Field(min_length=16, max_length=200)
