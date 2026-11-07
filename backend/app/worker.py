"""Background worker for scheduled institution sync.

This runs the *existing* sync engine on a timer; it invents no financial logic.
It is deliberately a plain loop rather than a scheduler framework: one process,
one job, visible in ``docker compose logs worker``.

Set ``WORKER_SYNC_INTERVAL_SECONDS`` (default 300) to change the cadence. Each
pass reuses ``sync_due_links``, which already honours per-link backoff and the
minimum interval between attempts, so a fast loop cannot hammer a provider.

Shutdown: SIGTERM/SIGINT finish the current pass and exit, so a restart never
leaves a half-applied sync.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from types import FrameType

from app.config import settings
from app.database.base import SessionLocal
from app.logging_config import configure_logging
from app.services.sync import sync_due_links

logger = logging.getLogger("pfc.worker")

DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 30

#: Touched after every pass. The container health check reads its mtime, which is
#: how a process with no HTTP port can still report that it is alive and working.
HEARTBEAT_PATH = os.environ.get("WORKER_HEARTBEAT_PATH", "/tmp/pfc-worker-heartbeat")

_stopping = False


def _request_stop(signum: int, _frame: FrameType | None) -> None:
    global _stopping
    _stopping = True
    logger.info("worker. stopping after the current pass (signal %s)", signum)


def run_once() -> int:
    """One pass over every due link. Returns how many links were attempted."""
    with SessionLocal() as session:
        try:
            results = sync_due_links(session)
            session.commit()
        except Exception:  # noqa: BLE001 - a bad pass must not kill the worker
            session.rollback()
            logger.exception("worker.sync_pass_failed")
            return 0
    if results:
        logger.info(
            "worker.sync_pass links=%s added=%s modified=%s failed=%s",
            len(results),
            sum(int(r.get("added") or 0) for r in results),
            sum(int(r.get("modified") or 0) for r in results),
            sum(1 for r in results if r.get("status") == "failed"),
        )
    else:
        logger.debug("worker.sync_pass links=0")
    return len(results)


def _touch_heartbeat() -> None:
    try:
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as handle:
            handle.write(str(time.time()))
    except OSError:
        # A missing heartbeat only degrades the health check, never the sync.
        logger.debug("worker.heartbeat_unwritable path=%s", HEARTBEAT_PATH)


def _interval() -> int:
    raw = os.environ.get("WORKER_SYNC_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        logger.warning("worker.bad_interval value=%r, using default", raw)
        return DEFAULT_INTERVAL_SECONDS
    return max(value, MIN_INTERVAL_SECONDS)


def main() -> int:
    configure_logging()
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    interval = _interval()
    logger.info(
        "worker.start interval_seconds=%s environment=%s", interval, settings.environment
    )

    _touch_heartbeat()
    while not _stopping:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("worker.pass_error")
        _touch_heartbeat()
        # Sleep in short slices so a stop signal is honoured promptly.
        deadline = time.monotonic() + interval
        while not _stopping and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))

    logger.info("worker.stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
