"""CSV import request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.models.enums import ImportRowStatus, ImportStatus
from app.schemas.common import APIModel, ORMModel

ALLOWED_MAPPING_KEYS = {
    "date",
    "description",
    "amount",
    "debit",
    "credit",
    "merchant",
    "type",
    "category",
    "external_id",
    "status",
}


class ImportMappingRequest(APIModel):
    mapping: dict[str, str | None] | None = None

    @field_validator("mapping")
    @classmethod
    def _keys(cls, value):
        if value is None:
            return None
        unknown = set(value) - ALLOWED_MAPPING_KEYS
        if unknown:
            raise ValueError(f"Unknown mapping fields: {sorted(unknown)}")
        return value


class ImportOut(ORMModel):
    id: uuid.UUID
    account_id: uuid.UUID
    filename: str
    file_size: int
    status: ImportStatus
    row_count: int
    imported_count: int
    duplicate_count: int
    rejected_count: int
    created_at: datetime
    committed_at: datetime | None


class ImportRecordOut(ORMModel):
    id: uuid.UUID
    row_number: int
    status: ImportRowStatus
    reason: str | None
    transaction_id: uuid.UUID | None
    raw_data: dict
