"""Timezone-aware date helpers used by bills, budgets and calculations."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = ZoneInfo("UTC")


def resolve_timezone(name: str | None, fallback: str = "UTC") -> ZoneInfo:
    for candidate in (name, fallback, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return UTC


def today_in(timezone_name: str | None, fallback: str = "UTC") -> date:
    return datetime.now(resolve_timezone(timezone_name, fallback)).date()


def utc_now() -> datetime:
    return datetime.now(UTC)


def now_in(timezone_name: str | None, fallback: str = "UTC") -> datetime:
    """The current instant, expressed in the user's timezone.

    The instant is the same everywhere; only the offset attached to it changes.
    It matters because callers render this value for a person: a timestamp
    stamped in UTC shows a user in the Americas a time that can sit on the
    previous or next calendar day from the one their Safe-to-Spend was computed
    for, which reads as a bug in the calculation rather than in its label.

    Returns an aware datetime, so nothing downstream has to guess an offset.
    """
    return datetime.now(resolve_timezone(timezone_name, fallback))


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def shift_months_preserving_day(value: date, months: int, preferred_day: int | None = None) -> date:
    day = preferred_day or value.day
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return clamp_day(year, month, day)


def next_frequency_date(
    current: date, frequency: str, *, custom_interval_days: int | None = None, preferred_day: int | None = None
) -> date:
    """Return the next due date for a recurring schedule."""
    match frequency:
        case "weekly":
            return current + timedelta(days=7)
        case "biweekly":
            return current + timedelta(days=14)
        case "monthly":
            return shift_months_preserving_day(current, 1, preferred_day)
        case "every_two_months":
            return shift_months_preserving_day(current, 2, preferred_day)
        case "quarterly":
            return shift_months_preserving_day(current, 3, preferred_day)
        case "semiannual":
            return shift_months_preserving_day(current, 6, preferred_day)
        case "annual":
            return shift_months_preserving_day(current, 12, preferred_day)
        case "custom":
            interval = custom_interval_days or 30
            return current + timedelta(days=interval)
        case _:
            raise ValueError(f"Unsupported frequency: {frequency}")


def iter_due_dates(
    anchor: date,
    frequency: str,
    until: date,
    *,
    custom_interval_days: int | None = None,
    preferred_day: int | None = None,
    max_iterations: int = 600,
) -> list[date]:
    """All due dates from ``anchor`` through ``until`` (inclusive).

    Deterministic and bounded; used for idempotent occurrence materialisation.
    """
    if until < anchor:
        return []
    dates: list[date] = []
    current = anchor
    for _ in range(max_iterations):
        if current > until:
            break
        dates.append(current)
        current = next_frequency_date(
            current, frequency, custom_interval_days=custom_interval_days, preferred_day=preferred_day
        )
    return dates


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def date_range_overlaps(start: date, end: date, other_start: date, other_end: date) -> bool:
    return start <= other_end and other_start <= end
