"""Golden BEFORE/AFTER semantic-equivalence suite for
VNSTOCK_EXACT_SESSION_WORKER_ISOLATION_AND_SENTINEL_EQUIVALENCE_V1.

BEFORE = a directly-injected synthetic ``fetch_single_source`` (today's contract: the resolver
never knows or cares whether that callable makes an in-process call or something else).
AFTER   = ``vnstock_worker_client.VnstockWorkerFetcher`` pointed at the deterministic fake worker
(``tests/fixtures/fake_vnstock_worker.py`` -- no real vnstock/vnai/network anywhere in this file).

For fixed synthetic evidence and a frozen clock, every acceptance case below asserts the parent's
own analytical semantics (selected winner/source, conflicts, recovery/quarantine state, coverage,
reason codes, eligibility, provider-outcome classification) are IDENTICAL whether the leaf fetch
happens in-process or through the worker -- proving the worker really is transport-only and the
parent kept 100% of source-ordering/fallback/quarantine/conflict-resolution policy.

New worker-only diagnostics (``vnstock_rate_governor``, ``recovery_throughput``, and the
resulting ``evidence_sha256``/``snapshot_sha256`` identity hashes, which embed those diagnostics)
are deliberately excluded from the BEFORE/AFTER equality assertions -- they are legitimate new
operational diagnostics, not canonical analytical identity (milestone brief, acceptance criterion
14). Everything else must match exactly.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from multi_source_exact_session_resolver import (
    DEGRADED_RECOVERY_COMPLETED,
    DEGRADED_RECOVERY_NOT_TRIGGERED,
    DailyRecoveryRuntimeBudgetExceeded,
    _DailyRecoveryRuntimeGuard,
    _kbs_result_warrants_vci_fallback,
    resolve_exact_session_with_autorecovery,
)
from vn_stock_pipeline import FetchOutcome
from vnstock_rate_governor import VnstockRateGovernor, get_active_governor, set_active_governor
from vnstock_worker_client import VnstockWorkerFetcher

TARGET = "2026-09-10"
REQUESTED_AT = "2026-09-10T20:00:00+07:00"
FAKE_WORKER = Path(__file__).with_name("fixtures") / "fake_vnstock_worker.py"

_DIAGNOSTIC_ONLY_KEYS = {
    "vnstock_rate_governor", "recovery_throughput", "evidence_sha256", "evidence_identity",
    "snapshot_sha256", "snapshot_identity",
}


def _strip_diagnostics(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in _DIAGNOSTIC_ONLY_KEYS}


def _dnse_obs_agreeing_with_secondary(session):
    """DNSE's own OHLC set to byte-match tests/fixtures/fake_vnstock_worker.py's canned EXACT_
    row (native open=10.0/high=10.2/low=9.9/close=10.1) -- a genuine, full agreement, not merely
    a matching close with divergent open/high/low (price agreement compares all four fields)."""
    return {
        "session": session, "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 123456,
        "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
        "price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
    }


def _dnse_obs(session, close, volume=1000):
    return {
        "session": session, "open": close, "high": close, "low": close, "close": close,
        "volume": volume, "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
        "price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
    }


def make_dnse_snapshot(records_spec):
    records = {}
    for ticker, (disposition, observations) in records_spec.items():
        status = (
            "OBSERVED" if disposition == "EXACT_SESSION_RETAINED"
            else "FETCH_FAILED" if disposition in ("PROVIDER_REJECTED", "TRANSPORT_FAILED") else disposition
        )
        records[ticker] = {
            "status": status, "reason": None if disposition == "EXACT_SESSION_RETAINED" else disposition,
            "disposition": disposition, "observations": observations or [],
            "payload_hash": f"hash-{ticker}" if observations else None,
            "request": {"symbol": ticker}, "provider_endpoint": "/price/ohlc" if observations else None,
        }
    return {
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "resolved_completed_session": TARGET, "retained_snapshot_session": TARGET,
        "requested_at": REQUESTED_AT, "target_session": TARGET,
        "candidate_count": len(records), "attempted_candidate_count": len(records),
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0,
        "source": {"provider": "DNSE", "endpoint": "/price/ohlc"},
        "authority_boundary": {"RAW_AS_TRADED": "NOT_PROMOTED", "HISTORICAL_PIT": "BLOCKED", "runtime_database_mutated": False},
        "records": records,
        "snapshot_identity": "p3f9_exact_session_snapshot:testhash",
    }


def _df(ticker, source):
    # Byte-identical to tests/fixtures/fake_vnstock_worker.py::_canned_outcome's EXACT_ row.
    df = pd.DataFrame({
        "ticker": [ticker], "date": [TARGET], "open": [10000], "high": [10200],
        "low": [9900], "close": [10100], "volume": [123456], "source": source,
    })
    df.attrs["unit_scale"] = 1000
    return df


def _direct_fetch_matching_fake_worker(ticker: str, source: str, start: str, end: str) -> FetchOutcome:
    """Mirrors tests/fixtures/fake_vnstock_worker.py::_canned_outcome exactly, so BEFORE (direct,
    in-process) and AFTER (worker-routed) are fed byte-identical synthetic evidence."""
    if ticker.startswith("EXACT_"):
        # lineage=[] matches the fake worker's own canned outcome exactly (it never fabricates
        # lineage records) -- BEFORE and AFTER must be fed byte-identical synthetic evidence.
        return FetchOutcome("success", data=_df(ticker, source), lineage=[])
    if ticker.startswith("MISSING_"):
        return FetchOutcome("empty")
    if ticker.startswith("TRANSPORT_"):
        return FetchOutcome("failed", transient_failure=True, errors=[f"{source}:transport_test_failure"])
    if ticker.startswith("REJECT_"):
        return FetchOutcome("failed", transient_failure=False, errors=[f"{source}:permanent_test_failure"])
    if ticker.startswith("MALFORMED_"):
        return FetchOutcome("failed", transient_failure=False, errors=[f"{source}:invalid_schema_test"])
    return FetchOutcome("empty")


def _run_before(dnse_snapshot, sentinel_cohort, **kwargs):
    # Same explicit-rate_governor hygiene as _run_after below: an explicit (non-None)
    # rate_governor makes the resolver's own wrapper skip restoring the module-global active
    # governor afterward, which would otherwise leak this test-local governor into later,
    # unrelated tests/files in the same pytest session.
    previous_active_governor = get_active_governor()
    try:
        return resolve_exact_session_with_autorecovery(
            dnse_snapshot=dnse_snapshot, target_session=TARGET, requested_at=REQUESTED_AT,
            sentinel_cohort=sentinel_cohort, fetch_single_source=_direct_fetch_matching_fake_worker,
            request_delay=0.0, sleep_fn=lambda s: None, rate_governor=VnstockRateGovernor(),
            **kwargs,
        )
    finally:
        set_active_governor(previous_active_governor)


def _run_after(dnse_snapshot, sentinel_cohort, **kwargs):
    # Passing an explicit rate_governor makes the resolver's own wrapper treat it as
    # caller-owned and skip restoring the module-global active governor afterward (see
    # daily_session_level2_package.ensure_exact_session_snapshot's identical hygiene comment) --
    # tests must restore it themselves so one test's worker never leaks into another test file's
    # unrelated vn_stock_pipeline/vnstock_rate_governor assertions.
    worker = VnstockWorkerFetcher(worker_script=FAKE_WORKER, request_timeout=10.0, startup_timeout=10.0)
    previous_active_governor = get_active_governor()
    try:
        return resolve_exact_session_with_autorecovery(
            dnse_snapshot=dnse_snapshot, target_session=TARGET, requested_at=REQUESTED_AT,
            sentinel_cohort=sentinel_cohort, fetch_single_source=worker.fetch,
            request_delay=0.0, sleep_fn=lambda s: None, rate_governor=worker,
            **kwargs,
        )
    finally:
        worker.shutdown()
        set_active_governor(previous_active_governor)


def _assert_equivalent(before, after):
    before_evidence, before_projected = before
    after_evidence, after_projected = after
    assert _strip_diagnostics(before_evidence) == _strip_diagnostics(after_evidence)
    assert _strip_diagnostics(before_projected) == _strip_diagnostics(after_projected)


# ---- A: DNSE complete + good quality ----

def test_A_dnse_complete_good_quality_sentinel_runs_agreement_does_not_alter_result():
    dnse = make_dnse_snapshot({"EXACT_AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs_agreeing_with_secondary(TARGET)])})
    before = _run_before(dnse, sentinel_cohort=["EXACT_AAA"])
    after = _run_after(dnse, sentinel_cohort=["EXACT_AAA"])
    _assert_equivalent(before, after)
    evidence, projected = before
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_EXACT_AND_CORROBORATED"
    assert projected["records"]["EXACT_AAA"]["observations"][0]["provider"] == "DNSE"


# ---- B: DNSE complete + deliberately wrong same-session value ----

def test_B_dnse_wrong_value_conflict_detected_and_replacement_identical():
    # DNSE says 10.0; both secondaries independently agree on 10.1 (fake worker's fixed canned
    # value for EXACT_* tickers) -- a material, isolated (single-ticker, assessed<5) conflict.
    dnse = make_dnse_snapshot({"EXACT_BBB": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 10.0)])})
    before = _run_before(dnse, sentinel_cohort=["EXACT_BBB"])
    after = _run_after(dnse, sentinel_cohort=["EXACT_BBB"])
    _assert_equivalent(before, after)
    evidence, _ = before
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_MATERIAL_CONFLICT"
    assert evidence["dnse_quality_sentinel"]["health"]["conflict_count"] == 1


# ---- C: DNSE missing eligible names -- KBS-first recovery unchanged ----

def test_C_dnse_missing_kbs_first_recovery_unchanged():
    dnse = make_dnse_snapshot({"EXACT_CCC": ("SESSION_MISSING", None)})
    before = _run_before(dnse, sentinel_cohort=[])
    after = _run_after(dnse, sentinel_cohort=[])
    _assert_equivalent(before, after)
    _, projected = before
    assert projected["records"]["EXACT_CCC"]["observations"][0]["provider"] == "KBS"
    assert projected["records"]["EXACT_CCC"]["disposition"] == "EXACT_SESSION_RETAINED"


# ---- D: KBS clean SESSION_MISSING -- ordinary gap path still skips VCI ----

def test_D_kbs_clean_session_missing_ordinary_gap_skips_vci():
    dnse = make_dnse_snapshot({"MISSING_DDD": ("SESSION_MISSING", None)})
    before = _run_before(dnse, sentinel_cohort=[])
    after = _run_after(dnse, sentinel_cohort=[])
    _assert_equivalent(before, after)
    _, projected = before
    assert projected["records"]["MISSING_DDD"]["disposition"] == "SESSION_MISSING"
    assert not _kbs_result_warrants_vci_fallback("SESSION_MISSING")


# ---- E: KBS transport/rejection/malformed -- VCI fallback remains exactly as current contract ----

@pytest.mark.parametrize("prefix", ["TRANSPORT_", "REJECT_", "MALFORMED_"])
def test_E_kbs_error_triggers_vci_fallback_unchanged(prefix):
    ticker = f"{prefix}EEE"
    dnse = make_dnse_snapshot({ticker: ("SESSION_MISSING", None)})
    before = _run_before(dnse, sentinel_cohort=[])
    after = _run_after(dnse, sentinel_cohort=[])
    _assert_equivalent(before, after)
    _, projected = before
    # VCI is also configured to return the same canned outcome (still an error/empty for this
    # ticker's prefix), so the ticker stays honestly SESSION_MISSING either way -- what matters
    # here is that BOTH KBS and VCI were actually attempted (the fallback fired), identically.
    assert projected["records"][ticker]["disposition"] == "SESSION_MISSING"


# ---- F: broad DNSE degradation -- quarantine behavior unchanged ----

def _broad_degraded_scenario():
    tickers = [f"EXACT_D{i:02d}" for i in range(18)]
    spec = {t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 999.0)]) for t in tickers}
    return make_dnse_snapshot(spec), tickers


def test_F_broad_dnse_degradation_quarantine_unchanged():
    dnse, tickers = _broad_degraded_scenario()
    before = _run_before(dnse, sentinel_cohort=tickers)
    after = _run_after(dnse, sentinel_cohort=tickers)
    _assert_equivalent(before, after)
    evidence, projected = before
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_COMPLETED
    for ticker in tickers:
        resolution = evidence["records"][ticker]["resolution"]
        assert resolution.get("resolved_under_quarantine") is True
        assert resolution["resolved_source"] != "DNSE"


# ---- G: degraded expansion + clean KBS missing (see module docstring: current code is
# symmetric -- KBS-first/VCI-on-error-only in BOTH ordinary and degraded-expansion paths; the
# equivalence requirement is that the WORKER PATH preserves whatever the direct-import path does,
# not that an asymmetry exists) ----

def test_G_degraded_expansion_clean_kbs_missing_behavior_matches_direct_path_exactly():
    tickers = [f"EXACT_D{i:02d}" for i in range(17)] + ["MISSING_EXPAND"]
    spec = {t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 999.0)]) for t in tickers}
    dnse = make_dnse_snapshot(spec)
    before = _run_before(dnse, sentinel_cohort=tickers)
    after = _run_after(dnse, sentinel_cohort=tickers)
    _assert_equivalent(before, after)


# ---- H: secondary disagreement -- normal and quarantined resolution semantics unchanged ----

def test_H_secondary_disagreement_normal_path():
    # VCI/KBS both return the fake worker's fixed EXACT_ value (agree with each other) but
    # disagree with DNSE -- exercised already by test_B; here we exercise a ticker with NO DNSE
    # observation at all so resolve_ticker's plain (non-degraded) corroborated-non-DNSE-free path
    # is exercised identically.
    dnse = make_dnse_snapshot({"EXACT_HHH": ("SESSION_MISSING", None)})
    before = _run_before(dnse, sentinel_cohort=[])
    after = _run_after(dnse, sentinel_cohort=[])
    _assert_equivalent(before, after)


# ---- I: secondary unavailable -- never treated as corroboration or degradation proof ----

def test_I_secondary_unavailable_not_corroboration_or_degradation_proof():
    dnse = make_dnse_snapshot({"TRANSPORT_III": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 5.0)])})
    before = _run_before(dnse, sentinel_cohort=["TRANSPORT_III"])
    after = _run_after(dnse, sentinel_cohort=["TRANSPORT_III"])
    _assert_equivalent(before, after)
    evidence, _ = before
    # A provider-error-dominated sentinel sample must not read as broad degradation nor as quiet
    # corroboration -- assessed excludes error-only members (see classify_dnse_provider_health).
    assert evidence["dnse_quality_sentinel"]["health"]["state"] != "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"


# ---- N: rate-budget exhaustion -- existing budget semantics remain (worker-shim governor
# produces the identical forecast/abort decision as a real VnstockRateGovernor) ----

def test_N_runtime_budget_forecast_identical_for_real_governor_and_worker_shim():
    """A tiny 5-second budget against 1000 remaining KBS requests must abort identically
    (existing DailyRecoveryRuntimeBudgetExceeded semantics, unchanged) whether the guard's
    pacing-floor forecast comes from a real VnstockRateGovernor or the worker-shim's duck-typed
    estimated_minimum_seconds_for -- proving N: the worker split changes nothing about the
    existing budget/abort contract."""
    real_governor = VnstockRateGovernor()
    worker = VnstockWorkerFetcher(worker_script=FAKE_WORKER)
    clock = [0.0]
    try:
        real_guard = _DailyRecoveryRuntimeGuard(
            request_delay=1.1, runtime_budget_seconds=5.0, clock=lambda: clock[0], rate_governor=real_governor,
        )
        worker_guard = _DailyRecoveryRuntimeGuard(
            request_delay=1.1, runtime_budget_seconds=5.0, clock=lambda: clock[0], rate_governor=worker,
        )
        with pytest.raises(DailyRecoveryRuntimeBudgetExceeded) as real_exc:
            real_guard.set_plan(stage="TEST", remaining_by_source={"KBS": 1000, "VCI": 0})
        with pytest.raises(DailyRecoveryRuntimeBudgetExceeded) as worker_exc:
            worker_guard.set_plan(stage="TEST", remaining_by_source={"KBS": 1000, "VCI": 0})
        assert (
            real_exc.value.diagnostic["projected_total_seconds"]
            == worker_exc.value.diagnostic["projected_total_seconds"]
        )
        assert real_exc.value.diagnostic["runtime_budget_seconds"] == worker_exc.value.diagnostic["runtime_budget_seconds"]
    finally:
        worker.shutdown()


# ---- O: worker import containment -- see tests/test_vnstock_worker_import_containment.py for
# the isolated-subprocess regression this milestone requires; a resolver-level in-process check
# would be contaminated by other test files in the same pytest session that legitimately import
# vn_stock_pipeline/vnstock directly, so it belongs in its own file (see that file's docstring).
