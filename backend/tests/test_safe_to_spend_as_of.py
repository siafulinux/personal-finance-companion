"""Safe-to-Spend's ``as_of`` is stamped in the user's zone, not the host's.

Safe-to-Spend is computed for the user's *calendar day* -- ``today`` already comes
from ``today_in(user.timezone)`` -- so the timestamp attached to the result has to
agree with it. A server in UTC stamping ``as_of`` in UTC gives a user in New York a
result dated today but "as of" yesterday evening, and a user in Tokyo one dated
tomorrow, which reads as the calculation being wrong rather than its label.

The pure engine has no user, so it cannot resolve a zone on its own: it takes one
on the inputs and uses it for the fallback. These tests pin both halves separately,
because either one alone would leave the other free to drift back to the host clock.
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.calculations.safe_to_spend import SafeToSpendInputs, calculate_safe_to_spend
from app.services.safe_to_spend import build_inputs
from app.utils.dates import today_in


def minimum_inputs(*, timezone: str) -> SafeToSpendInputs:
    today = today_in(timezone)
    return SafeToSpendInputs(
        today=today,
        horizon_end=today + datetime.timedelta(days=7),
        accounts=[],
        minimum_buffer=Decimal("0.00"),
        last_transaction_date=today,
        timezone=timezone,
    )


def test_build_inputs_stamps_as_of_in_the_users_zone(db, user):
    """The service hands the engine an instant labelled with the user's offset."""
    inputs = build_inputs(db, user)

    assert user.timezone == "America/New_York"
    assert inputs.timezone == user.timezone
    # The instant is the same one a UTC stamp would carry; the offset is what differs.
    assert inputs.as_of is not None
    assert inputs.as_of.utcoffset() == datetime.datetime.now(
        ZoneInfo(user.timezone)
    ).utcoffset()
    assert inputs.as_of.utcoffset() != datetime.timedelta(0)
    # "as of" must name the same day the calculation used, so a client cannot show
    # a result dated tomorrow (or yesterday) beside the day it was computed for.
    assert inputs.as_of.astimezone(ZoneInfo(user.timezone)).date() == inputs.today


def test_engine_fallback_follows_the_named_zone_not_the_host_clock():
    """Without a caller-supplied as_of, the engine uses the zone it was given.

    The host is whatever the CI container is (UTC), so a fallback reading the host
    clock would produce a +00:00 timestamp here and fail.
    """
    result = calculate_safe_to_spend(minimum_inputs(timezone="Asia/Tokyo"))

    assert result.as_of.utcoffset() == datetime.timedelta(hours=9)
    assert result.as_of.astimezone(ZoneInfo("Asia/Tokyo")).date() == result.today


def test_a_caller_supplied_as_of_is_kept_as_it_is(db, user):
    """An explicit instant is not re-stamped: a caller may book a different moment."""
    explicit = datetime.datetime(2026, 3, 1, 12, 0, tzinfo=ZoneInfo("America/New_York"))

    inputs = dataclasses.replace(build_inputs(db, user), as_of=explicit)

    assert calculate_safe_to_spend(inputs).as_of == explicit
