"""The Teller harness must refuse before it touches a live provider.

``scripts/verify_teller_live.py`` creates a real enrolment and revokes it, so every
preflight gate is a safety property rather than a convenience: a missing credential,
a non-sandbox environment, or an unreachable provider must stop the run *before* any
user row, enrolment or evidence file exists. These tests drive ``run()`` with a stub
adapter and assert the exit code, the message and — most importantly — the absence of
side effects.

No network is used: the stub adapter either answers or raises ``ProviderError``.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models import User
from app.providers.base import ProviderError
from app.services import provider_config

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_harness():
    """Load the script by path: ``backend/scripts`` is a scripts directory, not a package."""
    path = BACKEND_ROOT / "scripts" / "verify_teller_live.py"
    spec = importlib.util.spec_from_file_location("teller_harness_under_test", path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _load_harness()


class _Adapter:
    """Only the surface the preflight touches, so an unexpected call is obvious."""

    base_url = "https://api.teller.io"

    def __init__(
        self,
        *,
        environment: str = "sandbox",
        configured: bool = True,
        failure: ProviderError | None = None,
    ) -> None:
        self.environment = environment
        self._configured = configured
        self.failure = failure
        self.institution_calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def list_institutions(self, query: str | None = None):
        self.institution_calls += 1
        if self.failure is not None:
            raise self.failure
        return []


def _state(*, configured: bool = True, missing: tuple[str, ...] = ()):
    return provider_config.ProviderState(
        name="teller",
        label="Teller",
        enabled=True,
        priority=10,
        environment="sandbox",
        public={"application_id": "app_test"} if configured else {},
        secret={},
        source="database",
        configured=configured,
        missing=missing,
    )


def _args(**overrides):
    base = {
        "access_token": "token-sandbox-test",
        "enrollment_id": None,
        "teller_user_id": None,
        "poll": 0,
        "keep_user": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.fixture
def stub(monkeypatch):
    """Wire the harness to a stub adapter and a fixed provider state."""
    holders: dict[str, object] = {}

    def install(state, adapter):
        holders["adapter"] = adapter
        resolve = lambda db, name: state  # noqa: E731 - a stub with no behaviour
        monkeypatch.setattr(harness, "provider_config", SimpleNamespace(resolve=resolve))
        monkeypatch.setattr(harness, "adapter_for", lambda db, name: adapter)

    return SimpleNamespace(install=install, adapter=lambda: holders["adapter"])


def _user_count(db) -> int:
    return int(db.scalar(select(func.count()).select_from(User)) or 0)


def _evidence_files() -> set[Path]:
    if not harness.EVIDENCE_DIR.exists():
        return set()
    return set(harness.EVIDENCE_DIR.iterdir())


def test_missing_configuration_exits_2_without_contacting_teller(db, stub, capsys):
    """No application id means no run: exit 2, name what is missing, make no call."""
    adapter = _Adapter(configured=False)
    stub.install(_state(configured=False, missing=("application_id",)), adapter)
    users_before, evidence_before = _user_count(db), _evidence_files()

    assert harness.run(_args()) == 2

    err = capsys.readouterr().err
    assert "not configured" in err
    assert "application_id" in err
    assert "No live call was made" in err
    assert adapter.institution_calls == 0
    assert _user_count(db) == users_before
    assert _evidence_files() == evidence_before


def test_unconfigured_adapter_blocks_even_when_state_claims_configuration(db, stub, capsys):
    """The adapter's own ``is_configured`` is a second gate, not a redundant one."""
    adapter = _Adapter(configured=False)
    stub.install(_state(configured=True), adapter)
    users_before = _user_count(db)

    assert harness.run(_args()) == 2

    assert "not configured" in capsys.readouterr().err
    assert adapter.institution_calls == 0
    assert _user_count(db) == users_before


def test_non_sandbox_environment_exits_3_before_any_network_call(db, stub, capsys):
    """This run creates and revokes a real enrolment, so production is refused outright."""
    adapter = _Adapter(environment="development")
    stub.install(_state(configured=True), adapter)
    users_before, evidence_before = _user_count(db), _evidence_files()

    assert harness.run(_args()) == 3

    err = capsys.readouterr().err
    assert "TELLER_ENVIRONMENT=development" in err
    assert "sandbox-only" in err
    # The environment gate comes before the reachability probe.
    assert adapter.institution_calls == 0
    assert _user_count(db) == users_before
    assert _evidence_files() == evidence_before


def test_unreachable_provider_exits_2_and_creates_nothing(db, stub, capsys):
    """A network fault is reported as a network fault, and leaves no trace."""
    adapter = _Adapter(
        failure=ProviderError("Could not reach Teller.", code="network_error", retryable=True)
    )
    stub.install(_state(configured=True), adapter)
    users_before, evidence_before = _user_count(db), _evidence_files()

    assert harness.run(_args()) == 2

    err = capsys.readouterr().err
    assert "unreachable from this host" in err
    assert "network_error" in err
    assert "api.teller.io" in err
    # The probe was made exactly once: no retry loop, no second attempt.
    assert adapter.institution_calls == 1
    assert _user_count(db) == users_before
    assert _evidence_files() == evidence_before


def test_unreachable_provider_message_does_not_claim_an_adapter_fault(db, stub, capsys):
    """The distinction matters: a timeout says nothing about whether the adapter works."""
    adapter = _Adapter(
        failure=ProviderError("timed out", code="network_error", retryable=True)
    )
    stub.install(_state(configured=True), adapter)

    harness.run(_args())

    err = capsys.readouterr().err
    assert "not a verdict on" in err
    assert "Nothing was created" in err
