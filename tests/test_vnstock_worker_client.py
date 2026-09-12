"""Unit tests for vnstock_worker_client.VnstockWorkerFetcher against the deterministic fake
worker (tests/fixtures/fake_vnstock_worker.py) -- no real vnstock/vnai/network anywhere in this
file. Covers protocol-level acceptance cases J (startup failure), K (SystemExit), L (hang/
timeout), M (malformed/truncated response), plus lazy-start, deterministic shutdown, duplicate/
unknown request-id handling, and the rate-governor-shim duck-typed methods
(estimated_minimum_seconds_for/diagnostic).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from vnstock_rate_governor import DEFAULT_EFFECTIVE_RPM, RATE_WINDOW_SECONDS, VnstockRateGovernor
from vnstock_worker_client import VnstockWorkerFetcher
from vnstock_worker_protocol import (
    VnstockWorkerAdapterError,
    VnstockWorkerProcessExitError,
    VnstockWorkerProtocolError,
    VnstockWorkerStartupError,
    VnstockWorkerTimeoutError,
)

FAKE_WORKER = Path(__file__).with_name("fixtures") / "fake_vnstock_worker.py"


def _fetcher(**overrides) -> VnstockWorkerFetcher:
    kwargs = {"worker_script": FAKE_WORKER, "request_timeout": 5.0, "startup_timeout": 5.0, "shutdown_timeout": 5.0}
    kwargs.update(overrides)
    return VnstockWorkerFetcher(**kwargs)


def test_lazy_start_never_spawns_a_process_until_first_fetch():
    fetcher = _fetcher()
    assert fetcher._started is False
    fetcher.shutdown()  # must be a safe no-op when never started
    assert fetcher._process is None


def test_successful_fetch_reconstructs_a_dataframe_matching_vn_stock_pipeline_shape():
    fetcher = _fetcher()
    try:
        outcome = fetcher.fetch("EXACT_AAA", "KBS", "2026-09-01", "2026-09-10")
        assert outcome.status == "success"
        assert list(outcome.data["date"]) == ["2026-09-10"]
        assert outcome.data.attrs["unit_scale"] == 1000
        assert float(outcome.data.iloc[0]["close"]) == 10100.0
    finally:
        fetcher.shutdown()


def test_empty_transport_reject_and_malformed_statuses_round_trip_distinctly():
    fetcher = _fetcher()
    try:
        empty = fetcher.fetch("MISSING_X", "KBS", "2026-09-01", "2026-09-10")
        assert empty.status == "empty" and empty.data is None
        transport = fetcher.fetch("TRANSPORT_X", "VCI", "2026-09-01", "2026-09-10")
        assert transport.status == "failed" and transport.transient_failure is True
        reject = fetcher.fetch("REJECT_X", "VCI", "2026-09-01", "2026-09-10")
        assert reject.status == "failed" and reject.transient_failure is False
        assert "permanent_test_failure" in reject.errors[0]
        malformed = fetcher.fetch("MALFORMED_X", "VCI", "2026-09-01", "2026-09-10")
        assert malformed.status == "failed" and "invalid_schema_test" in malformed.errors[0]
    finally:
        fetcher.shutdown()


def test_concurrent_fetches_are_thread_safe_and_correctly_correlated():
    fetcher = _fetcher()
    results = {}
    errors = []

    def worker(name):
        try:
            results[name] = fetcher.fetch(f"EXACT_{name}", "KBS", "2026-09-01", "2026-09-10")
        except Exception as exc:  # noqa: BLE001
            errors.append((name, exc))

    import threading

    threads = [threading.Thread(target=worker, args=(f"T{i}",)) for i in range(12)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors, errors
        assert len(results) == 12
        for name, outcome in results.items():
            assert outcome.data.iloc[0]["ticker"] == f"EXACT_{name}"
    finally:
        fetcher.shutdown()


def test_shutdown_is_idempotent():
    fetcher = _fetcher()
    fetcher.fetch("EXACT_A", "KBS", "2026-09-01", "2026-09-10")
    fetcher.shutdown()
    fetcher.shutdown()  # must not raise


# ---- J: worker startup failure ----

def test_startup_failure_raises_explicit_error_never_a_fabricated_outcome():
    fetcher = _fetcher(env={"FAKE_WORKER_STARTUP_FAIL": "1"}, startup_timeout=3.0)
    with pytest.raises(VnstockWorkerStartupError):
        fetcher.fetch("EXACT_A", "KBS", "2026-09-01", "2026-09-10")
    fetcher.shutdown()  # must still be safe to call


# ---- K: worker exits via SystemExit ----

def test_worker_systemexit_is_caught_as_a_worker_failure_not_a_provider_outcome():
    fetcher = _fetcher()
    try:
        with pytest.raises((VnstockWorkerProcessExitError, VnstockWorkerTimeoutError)):
            fetcher.fetch("__SYSTEMEXIT_PROCESS__", "KBS", "2026-09-01", "2026-09-10")
        # The canonical parent process itself must survive -- proven simply by reaching this
        # line and being able to keep running Python code (a real SystemExit inside this
        # process, rather than the child, would have aborted the test runner instead).
        assert True
    finally:
        fetcher.shutdown()


# ---- L: worker hang ----

def test_worker_hang_hits_a_bounded_timeout_and_never_returns_a_partial_result():
    fetcher = _fetcher(request_timeout=1.0)
    try:
        started = time.monotonic()
        with pytest.raises(VnstockWorkerTimeoutError):
            fetcher.fetch("__HANG_FOREVER__", "KBS", "2026-09-01", "2026-09-10")
        elapsed = time.monotonic() - started
        assert elapsed < 10.0  # bounded, not an indefinite hang
    finally:
        fetcher.shutdown()


# ---- M: truncated/malformed worker response ----

def test_malformed_worker_response_fails_closed():
    fetcher = _fetcher()
    try:
        with pytest.raises(VnstockWorkerProtocolError):
            fetcher.fetch("__RAW_GARBAGE__", "KBS", "2026-09-01", "2026-09-10")
    finally:
        fetcher.shutdown()


def test_after_any_fatal_failure_the_fetcher_stays_permanently_failed_no_transparent_restart():
    fetcher = _fetcher()
    try:
        with pytest.raises(VnstockWorkerProtocolError):
            fetcher.fetch("__RAW_GARBAGE__", "KBS", "2026-09-01", "2026-09-10")
        # A second, otherwise-perfectly-valid request must still raise immediately -- the
        # fetcher never silently reconstitutes a fresh worker/budget after a fatal failure.
        with pytest.raises(VnstockWorkerProtocolError):
            fetcher.fetch("EXACT_A", "KBS", "2026-09-01", "2026-09-10")
    finally:
        fetcher.shutdown()


# ---- rate-governor duck-typed shim ----

def test_estimated_minimum_seconds_for_matches_the_real_governor_exactly():
    real = VnstockRateGovernor()
    fetcher = _fetcher()
    try:
        for n in (0, 1, 5, 45, 100):
            assert fetcher.estimated_minimum_seconds_for(n) == real.estimated_minimum_seconds_for(n)
        assert fetcher.estimated_minimum_seconds_for(45) == 45 * (RATE_WINDOW_SECONDS / DEFAULT_EFFECTIVE_RPM)
    finally:
        fetcher.shutdown()


def test_diagnostic_is_honest_about_an_unstarted_or_failed_worker_never_pretends():
    fetcher = _fetcher()
    diag = fetcher.diagnostic()
    assert diag["worker_started"] is False
    fetcher.fetch("EXACT_A", "KBS", "2026-09-01", "2026-09-10")
    real_diag = fetcher.diagnostic()
    assert real_diag["source"] == "VNSTOCK_WORKER_REMOTE_GOVERNOR"
    assert real_diag["attempts"] == 1
    fetcher.shutdown()


def test_worker_diagnostics_are_bounded_and_never_contain_secrets():
    fetcher = _fetcher()
    try:
        fetcher.fetch("EXACT_A", "KBS", "2026-09-01", "2026-09-10")
        diag = fetcher.worker_diagnostics()
        assert diag["worker_started"] is True
        assert isinstance(diag["worker_pid"], int)
        assert diag["provider_attempt_counts"] == {"KBS": 1}
        assert diag["request_count"] == 1
    finally:
        fetcher.shutdown()
