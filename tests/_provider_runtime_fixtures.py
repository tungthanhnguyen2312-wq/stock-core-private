"""Shared hermetic fixtures for the isolated provider runtime (PROVIDER_RUNTIME_ISOLATION_V1).

No real vnstock/vnai anywhere: the "provider interpreter" is this test interpreter running the
deterministic fake worker (``tests/fixtures/fake_vnstock_worker.py``), and the launch policy is an
explicit test-only ``ALLOW`` object -- never the tracked owner policy, which stays
``SECURITY_REVIEW_BLOCKED``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import provider_runtime_state as runtime_contract
import vnstock_worker_client as worker_client

FAKE_WORKER = Path(__file__).with_name("fixtures") / "fake_vnstock_worker.py"

TEST_ALLOW_POLICY = runtime_contract.ProviderPolicy(
    provider_family=runtime_contract.PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
    policy=runtime_contract.POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME,
    reason="TEST_FIXTURE_EXPLICIT_ALLOW_FAKE_WORKER_ONLY",
    source="TEST_FIXTURE",
)


def fake_fetcher(**overrides: Any) -> worker_client.VnstockWorkerFetcher:
    kwargs: dict[str, Any] = {
        "python_executable": sys.executable,
        "policy": TEST_ALLOW_POLICY,
        "worker_script": FAKE_WORKER,
        "request_timeout": 10.0,
        "startup_timeout": 10.0,
        "shutdown_timeout": 5.0,
    }
    kwargs.update(overrides)
    return worker_client.VnstockWorkerFetcher(**kwargs)


class StubFetcher:
    """A started-looking fetcher for tests whose resolver is itself faked (never fetches)."""

    failure = None
    runtime_info = {"python_version": "test", "provider_distributions": {"vnstock": None, "vnai": None}}

    def __init__(self) -> None:
        self.shutdown_calls = 0

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("StubFetcher.fetch must not be called by a faked resolver")

    def outcome_stats(self) -> dict[str, int]:
        return runtime_contract.empty_outcome_stats()

    def diagnostic(self) -> dict[str, Any]:
        return {"source": "STUB"}

    def estimated_minimum_seconds_for(self, additional_requests: int) -> float:
        from vnstock_rate_governor import DEFAULT_EFFECTIVE_RPM, RATE_WINDOW_SECONDS

        return max(0, additional_requests) * (RATE_WINDOW_SECONDS / DEFAULT_EFFECTIVE_RPM)

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def available_handle(fetcher: Any | None = None) -> worker_client.ProviderRuntimeHandle:
    fetcher = fetcher if fetcher is not None else StubFetcher()
    state = runtime_contract.runtime_state_record(
        runtime_contract.AVAILABLE, runtime_contract.REASON_READY_HANDSHAKE, policy=TEST_ALLOW_POLICY,
        interpreter_configured=True, runtime_info=getattr(fetcher, "runtime_info", None) or {},
    )
    return worker_client.ProviderRuntimeHandle(state, fetcher, TEST_ALLOW_POLICY)


def unavailable_handle(state: str = runtime_contract.SECURITY_REVIEW_BLOCKED,
                       reason: str = runtime_contract.REASON_POLICY_SECURITY_REVIEW_BLOCKED) -> worker_client.ProviderRuntimeHandle:
    return worker_client.ProviderRuntimeHandle(
        runtime_contract.runtime_state_record(state, reason), None, TEST_ALLOW_POLICY,
    )


def healthy_sentinel_evidence(session: str, *, dnse_exact: int = 2) -> dict[str, Any]:
    """Minimal multi-source evidence carrying a corroborated DNSE quality sentinel."""
    return {
        "target_session": session,
        "dnse_exact_session_count": dnse_exact,
        "dnse_quality_sentinel": {
            "cohort_tickers": ["AAA"],
            "health": {"state": "DNSE_EXACT_AND_CORROBORATED", "dnse_assessed_count": 1,
                       "corroborated_count": 1, "conflict_count": 0, "uncorroborated_count": 0},
        },
        "degraded_provider_recovery": {"mode": "NOT_TRIGGERED"},
        "records": {},
    }
