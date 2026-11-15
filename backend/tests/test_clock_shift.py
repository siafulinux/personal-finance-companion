"""Fail closed when the suite claims to run on a shifted clock but does not.

`Backend on a shifted clock` runs this whole suite under libfaketime, with `TODAY`
naming the instant it should pretend it is. Every date-dependent test in that job
is only meaningful if the preload actually took effect: a library that failed to
install, an `LD_PRELOAD` path that resolves to nothing, or a wrapper that falls
back to the real clock all leave the tests running on today's date, where most of
them pass for the wrong reason. The job would report green while proving nothing,
which is the one outcome it must never produce.

The workflow checks this for a single `date` call before pytest starts. These
tests check the process the fixtures actually run in, and the subprocesses they
shell out to -- `conftest.migrated_database` runs `alembic upgrade head` as a
child process, so a shift that covers this interpreter but not its children would
still migrate on the real clock.

The third test needs no shifted clock: it proves the canary rejects an unshifted
one, so this file cannot pass by being vacuous.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time

import pytest

TODAY = os.environ.get("TODAY", "").strip()

# libfaketime holds the offset rather than freezing the clock, so a run legitimately
# advances from the instant it was given. Five minutes is far more than a suite takes
# and still rejects "roughly today", which is what a broken preload produces.
TOLERANCE = datetime.timedelta(minutes=5)

shifted = pytest.mark.skipif(
    not TODAY,
    reason="TODAY is unset: this run is not under a shifted clock, so there is nothing to check.",
)


def expected_instant() -> datetime.datetime:
    """The local instant ``TODAY`` asks libfaketime for.

    libfaketime reads the value as local time, so comparing a naive `datetime.now()`
    against it is timezone-independent: the runner being UTC or otherwise does not
    change what "the clock is shifted" means here.
    """
    try:
        return datetime.datetime.strptime(TODAY, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pytest.fail(
            f"TODAY={TODAY!r} is not a 'YYYY-MM-DD HH:MM:SS' instant, so the clock this "
            "job claims to test cannot be verified.",
            pytrace=False,
        )
        raise AssertionError("unreachable")  # keeps type checkers honest


def mismatch(expected: datetime.datetime, observed: datetime.datetime) -> str | None:
    """Describe how ``observed`` fails to be the shifted clock, or None if it is."""
    if observed.date() != expected.date():
        return f"the date is {observed.date()}, not {expected.date()}"
    drift = abs(observed - expected)
    if drift > TOLERANCE:
        return f"the clock is {drift.total_seconds():.0f}s away from {expected}"
    return None


def test_the_canary_rejects_the_real_clock() -> None:
    expected = datetime.datetime(2028, 2, 29, 12, 0, 0)
    # Exactly what a broken preload looks like: today's date, not the leap day.
    assert mismatch(expected, datetime.datetime(2026, 11, 14, 9, 30)) is not None
    # A clock inside the tolerance is accepted, or the canary would fail on drift.
    assert mismatch(expected, expected + TOLERANCE / 2) is None


@shifted
def test_the_test_process_runs_on_the_shifted_clock() -> None:
    expected = expected_instant()

    observed = datetime.datetime.now()
    problem = mismatch(expected, observed)
    assert problem is None, (
        f"libfaketime did not take effect in this process: {problem}. "
        f"TODAY={TODAY!r}. Every date-dependent test in this run is therefore reading "
        "the real clock, so this job proves nothing."
    )

    # The two other readings the fixtures and services use, so a preload that
    # intercepts only some of them is caught here rather than by a future bug.
    assert datetime.date.today() == expected.date(), (
        f"date.today() is {datetime.date.today()} but the shifted clock is "
        f"{expected.date()}: the C library's clock is not intercepted."
    )
    epoch_drift = abs(time.time() - expected.timestamp())
    assert epoch_drift <= TOLERANCE.total_seconds(), (
        f"time.time() is {epoch_drift:.0f}s away from {expected}: the epoch clock is "
        "not intercepted even though the datetime module is."
    )


@shifted
def test_subprocesses_run_on_the_shifted_clock_too() -> None:
    expected = expected_instant()
    code = "import datetime; print(datetime.datetime.now().isoformat(timespec='seconds'))"

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    observed = datetime.datetime.fromisoformat(result.stdout.strip())

    problem = mismatch(expected, observed)
    assert problem is None, (
        f"a child process sees {problem}, so the preload covers this interpreter only. "
        "The fixtures migrate through `alembic` as a subprocess, which would then build "
        "its schema on the real clock while the tests believe it is shifted."
    )
