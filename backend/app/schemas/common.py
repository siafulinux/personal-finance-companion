"""Shared Pydantic configuration and validators."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

Money = Annotated[
    Decimal,
    Field(max_digits=18, decimal_places=2),
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str


def clean_optional_text(value: str | None, max_length: int = 2000) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"Text must be at most {max_length} characters.")
    return cleaned


class DateRangeParams(BaseModel):
    start: date | None = None
    end: date | None = None

    @field_validator("end")
    @classmethod
    def _check_order(cls, value: date | None, info):
        start = info.data.get("start")
        if value and start and value < start:
            raise ValueError("end must be on or after start")
        return value
