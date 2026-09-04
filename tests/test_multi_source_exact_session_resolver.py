import threading
import time

import pandas as pd
import pytest

from field_temporal_contract import stable_id
from multi_source_exact_session_resolver import (
    DEGRADED_RECOVERY_COMPLETED,
    DEGRADED_RECOVERY_NOT_TRIGGERED,
    POSITIVE_YIELD_EXPAND,
    PROVIDER_ERROR_DOMINATED_NOT_ZERO_YIELD,
    ZERO_OBSERVED_INCREMENTAL_YIELD_FOR_THIS_RUN,
    DailyRecoveryRuntimeBudgetExceeded,
    DnseProviderWideQualityDegraded,
    MultiSourceResolverError,
    _ProviderAwareMemoizingFetch,
    _ProviderSchedulePolicy,
    _DailyRecoveryRuntimeGuard,
    _kbs_result_warrants_vci_fallback,
    assert_dnse_quality_acceptable,
    resolve_exact_session_with_autorecovery,
    resolve_multi_source_exact_session_snapshot,
    select_residual_gap_sentinel,
    select_sentinel_cohort,
)
from vn_stock_pipeline import FetchOutcome
from vnstock_rate_governor import VnstockRateGovernor, get_active_governor

TARGET = "2026-09-03"
REQUESTED_AT = "2026-09-03T20:00:00+07:00"


def _dnse_obs(session, close, volume=1000):
    return {"session": session, "open": close, "high": close, "low": close, "close": close, "volume": volume,
            "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
            "price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"}


def make_dnse_snapshot(records_spec):
    """records_spec: {ticker: (disposition, [observation dicts] or None)}"""
    records = {}
    for ticker, (disposition, observations) in records_spec.items():
        status = "OBSERVED" if disposition == "EXACT_SESSION_RETAINED" else "FETCH_FAILED" if disposition in ("PROVIDER_REJECTED", "TRANSPORT_FAILED") else disposition
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


def make_df(dates_closes, unit_scale=1000):
    df = pd.DataFrame({
        "ticker": "T", "date": [d for d, _ in dates_closes],
        "open": [c for _, c in dates_closes], "high": [c for _, c in dates_closes],
        "low": [c for _, c in dates_closes], "close": [c for _, c in dates_closes],
        "volume": [999000 for _ in dates_closes], "source": "VCI",
    })
    df.attrs["unit_scale"] = unit_scale
    return df


def assert_self_consistent(projected):
    payload = {k: v for k, v in projected.items() if k not in {"snapshot_sha256", "snapshot_identity"}}
    assert projected["snapshot_sha256"] == stable_id(payload)
    assert projected["snapshot_identity"] == f"p3f9_exact_session_snapshot:{projected['snapshot_sha256']}"


# ---- basic single-ticker scenarios ----

def test_dnse_resolved_ticker_is_never_recovery_queried():
    dnse = make_dnse_snapshot({"AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 10.0)])})
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        raise AssertionError("should never be called for a DNSE-resolved ticker")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert calls == []
    assert projected["records"]["AAA"]["disposition"] == "EXACT_SESSION_RETAINED"
    assert projected["records"]["AAA"]["observations"][0]["provider"] == "DNSE"
    assert evidence["dnse_exact_session_count"] == 1
    assert evidence["recovery_attempts"] == {"VCI": 0, "KBS": 0}


def test_kbs_recovers_dnse_missing_ticker_without_touching_vci():
    dnse = make_dnse_snapshot({"BBB": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 20.0)])})
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return FetchOutcome("success", data=make_df([(TARGET, 20500.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L1"}])

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert calls == [("BBB", "KBS")]
    rec = projected["records"]["BBB"]
    assert rec["disposition"] == "EXACT_SESSION_RETAINED"
    assert rec["observations"][0]["provider"] == "KBS"
    assert rec["observations"][0]["close"] == 20.5  # native scale, matching DNSE's own convention
    assert rec["payload_hash"] == "L1"
    assert evidence["recovery_successes"] == {"VCI": 0, "KBS": 1}


def test_vci_recovers_when_kbs_fails_transport():
    """DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1: VCI fallback fires for a genuine KBS
    provider error (transport failure here), never for a clean KBS SESSION_MISSING -- see
    test_vci_does_not_run_after_clean_kbs_session_missing for the negative case."""
    dnse = make_dnse_snapshot({"CCC": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 30.0)])})

    def fetch(ticker, source, start, end):
        if source == "KBS":
            return FetchOutcome("failed", errors=["transient_network_error"], transient_failure=True)
        return FetchOutcome("success", data=make_df([(TARGET, 30300.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L2"}])

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    rec = projected["records"]["CCC"]
    assert rec["disposition"] == "EXACT_SESSION_RETAINED"
    assert rec["observations"][0]["provider"] == "VCI"
    assert evidence["recovery_attempts"] == {"VCI": 1, "KBS": 1}


def test_vci_does_not_run_after_clean_kbs_session_missing():
    """DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1: a clean KBS SESSION_MISSING must never
    automatically trigger VCI -- 0/55 measured incremental recovery (operations-review/
    same-session-gap-semantics-and-fallback-value-qualification-v1-20260904). The ticker stays
    honestly SESSION_MISSING, never fabricated as exact or zero-trade."""
    dnse = make_dnse_snapshot({"CCC": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 30.0)])})
    calls = []

    def fetch(ticker, source, start, end):
        calls.append(source)
        if source == "KBS":
            return FetchOutcome("empty")
        raise AssertionError("VCI must not be called after a clean KBS SESSION_MISSING")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert calls == ["KBS"]
    assert evidence["recovery_attempts"] == {"VCI": 0, "KBS": 1}
    assert projected["records"]["CCC"]["disposition"] == "SESSION_MISSING"
    vci_obs = next(o for o in evidence["records"]["CCC"]["observations"] if o["source"] == "VCI")
    assert vci_obs["status"] == "NOT_APPLICABLE"
    assert vci_obs["reason_code"] == "NOT_ATTEMPTED_CLEAN_SESSION_MISSING_FALLBACK_POLICY_ERROR_ONLY"


@pytest.mark.parametrize("dnse_disposition", ["SESSION_MISSING", "PROVIDER_REJECTED", "TRANSPORT_FAILED", "MALFORMED"])
def test_all_sources_missing_preserves_original_dnse_disposition(dnse_disposition):
    dnse = make_dnse_snapshot({"DDD": (dnse_disposition, [])})

    def fetch(ticker, source, start, end):
        return FetchOutcome("empty")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    rec = projected["records"]["DDD"]
    assert rec["disposition"] == dnse_disposition  # unchanged -- never silently overwritten
    assert rec["multi_source_recovery_result"] == "ALL_SOURCES_MISSING"
    assert evidence["resolution_counts"]["SESSION_MISSING_ALL_SOURCES"] == 1


def test_transport_failure_classified_transport_failed_not_source_rejected():
    dnse = make_dnse_snapshot({"EEE": ("SESSION_MISSING", [])})

    def fetch(ticker, source, start, end):
        return FetchOutcome("failed", errors=[f"{source}:read_timeout"], transient_failure=True)

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    vci_obs = next(o for o in evidence["records"]["EEE"]["observations"] if o["source"] == "VCI")
    assert vci_obs["status"] == "TRANSPORT_FAILED"


def test_permanent_failure_classified_source_rejected():
    dnse = make_dnse_snapshot({"FFF": ("SESSION_MISSING", [])})

    def fetch(ticker, source, start, end):
        return FetchOutcome("failed", errors=[f"{source}:request_error"], transient_failure=False)

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    vci_obs = next(o for o in evidence["records"]["FFF"]["observations"] if o["source"] == "VCI")
    assert vci_obs["status"] == "SOURCE_REJECTED"


def test_target_session_absent_from_history_is_session_missing_not_observed():
    dnse = make_dnse_snapshot({"GGG": ("SESSION_MISSING", [])})

    def fetch(ticker, source, start, end):
        return FetchOutcome("success", data=make_df([("2026-08-28", 10.0)]))  # no TARGET row

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    # KBS (primary) genuinely queried: target-session-absent classifies SESSION_MISSING, never
    # fabricated OBSERVED. A clean SESSION_MISSING is not a provider error, so VCI is never
    # attempted (DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1) -- it gets an explicit stub instead.
    kbs_obs = next(o for o in evidence["records"]["GGG"]["observations"] if o["source"] == "KBS")
    assert kbs_obs["status"] == "SESSION_MISSING"
    vci_obs = next(o for o in evidence["records"]["GGG"]["observations"] if o["source"] == "VCI")
    assert vci_obs["status"] == "NOT_APPLICABLE"
    assert projected["records"]["GGG"]["disposition"] == "SESSION_MISSING"


# ---- generic, no-ticker-specific-branch behavior across a larger synthetic universe ----

def test_generic_behavior_no_ticker_specific_branches():
    tickers = [f"T{i:03d}" for i in range(20)]
    spec = {}
    for i, t in enumerate(tickers):
        if i < 5:
            spec[t] = ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, float(i))])
        else:
            spec[t] = ("SESSION_MISSING", [_dnse_obs("2026-08-28", float(i))])
    dnse = make_dnse_snapshot(spec)
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        # Odd-indexed missing tickers recover cleanly on KBS. Even-indexed KBS calls fail with a
        # genuine transport error (not a clean miss), so VCI fallback fires and recovers them --
        # DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1: a clean KBS SESSION_MISSING must never
        # reach VCI, so "needs VCI" can only be modeled here via a real provider error. One
        # ticker fails cleanly on both and stays unresolved.
        idx = int(ticker[1:])
        if idx == 19:
            return FetchOutcome("empty")
        if idx % 2 == 1:
            if source == "KBS":
                return FetchOutcome("success", data=make_df([(TARGET, float(idx) * 1000)]))
            raise AssertionError(f"VCI must not be called for odd-indexed {ticker} (clean KBS exact)")
        if source == "KBS":
            return FetchOutcome("failed", errors=["transient_network_error"], transient_failure=True)
        return FetchOutcome("success", data=make_df([(TARGET, float(idx) * 1000)]))

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert {t for t, s in calls if s == "KBS"} == set(tickers[5:])  # every DNSE-missing ticker tried KBS
    # Only the even-indexed (genuine KBS transport failure) tickers ever reach VCI -- the
    # odd-indexed (clean KBS exact) and T019 (clean KBS miss) never do.
    expected_vci_calls = {t for t in tickers[5:] if int(t[1:]) % 2 == 0 and int(t[1:]) != 19}
    assert {t for t, s in calls if s == "VCI"} == expected_vci_calls
    resolved = [t for t in tickers if projected["records"][t]["disposition"] == "EXACT_SESSION_RETAINED"]
    assert "T019" not in resolved
    assert len(resolved) == 19  # 5 DNSE + 14 recovered (T005..T018 except the unresolvable one already excluded)
    assert projected["exact_session_observed_count"] == 19
    assert projected["disposition_counts"]["EXACT_SESSION_RETAINED"] == 19


# ---- resolved coverage / self-consistency / authority boundaries ----

def test_resolved_snapshot_passes_self_consistency_check():
    dnse = make_dnse_snapshot({
        "AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 10.0)]),
        "BBB": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 20.0)]),
    })

    def fetch(ticker, source, start, end):
        return FetchOutcome("success", data=make_df([(TARGET, 20500.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    _, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert_self_consistent(projected)
    assert projected["contract_version"] == "p3f9_exact_session_mva_snapshot/v2"


def test_authority_boundary_never_promoted():
    dnse = make_dnse_snapshot({"AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 10.0)])})
    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=lambda *a: FetchOutcome("empty"), request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert evidence["is_actionable_for_execution"] is False
    assert evidence["pit_backtest_eligible"] is False
    assert evidence["liquidity_sizing_authority"] == "BLOCKED"
    assert evidence["authority_boundary"]["RAW_AS_TRADED"] == "NOT_PROMOTED"
    assert evidence["authority_boundary"]["cross_provider_volume_synthesis"] == "NEVER_PERFORMED"
    assert projected["records"]["AAA"]["observations"][0]["price_basis"] == "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"


# ---- future/prior session non-substitution ----

def test_session_mismatch_between_dnse_snapshot_and_target_raises():
    dnse = make_dnse_snapshot({"AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs("2026-08-28", 10.0)])})
    # dnse's own resolved_completed_session is TARGET (2026-09-03) by construction; force a mismatch.
    dnse["resolved_completed_session"] = "2026-08-28"
    with pytest.raises(MultiSourceResolverError):
        resolve_multi_source_exact_session_snapshot(
            dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
            fetch_single_source=lambda *a: FetchOutcome("empty"), request_delay=0.0, sleep_fn=lambda s: None,
        )


# ---- bounded recovery candidate limit (test/diagnostic knob only) ----

def test_max_recovery_candidates_bounds_live_requests():
    spec = {f"M{i}": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 1.0)]) for i in range(10)}
    dnse = make_dnse_snapshot(spec)
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return FetchOutcome("empty")

    resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        max_recovery_candidates=3,
    )
    assert len({t for t, s in calls}) == 3


def test_dnse_exact_session_count_unaffected_by_bounded_recovery_cap():
    """Regression: dnse_exact_session_count must reflect DNSE's TRUE resolved count, never
    "candidates not selected for a (possibly capped) recovery attempt" -- a real bug this
    milestone's own bounded live validation caught (a 15-candidate cap on a real ~1665-missing
    day misreported dnse_exact_session_count as 1668 instead of the true 18)."""
    spec = {"AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 1.0)])}
    for i in range(20):
        spec[f"M{i:02d}"] = ("SESSION_MISSING", [_dnse_obs("2026-08-28", 1.0)])
    dnse = make_dnse_snapshot(spec)

    def fetch(ticker, source, start, end):
        return FetchOutcome("empty")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        max_recovery_candidates=3,  # far fewer than the 20 truly-missing tickers
    )
    assert evidence["dnse_exact_session_count"] == 1  # only AAA -- never candidate_count - 3
    assert evidence["dnse_missing_total_count"] == 20
    assert evidence["dnse_missing_excluded_by_recovery_bound_count"] == 17
    # Every excluded-by-bound ticker keeps its true original DNSE disposition, never silently
    # relabeled as though DNSE had resolved it or recovery had genuinely been attempted.
    excluded = [t for t in spec if t != "AAA"][3:]
    assert len(excluded) == 17
    for ticker in excluded:
        assert projected["records"][ticker]["disposition"] == "SESSION_MISSING"
        stub = next(o for o in evidence["records"][ticker]["observations"] if o["source"] == "VCI")
        assert stub["reason_code"] == "NOT_ATTEMPTED_BOUNDED_RECOVERY_LIMIT"


def test_production_default_has_no_recovery_bound_and_reports_are_consistent():
    """The no-cap (production) path must never exercise the excluded-by-bound label at all."""
    spec = {"AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 1.0)])}
    spec["BBB"] = ("SESSION_MISSING", [_dnse_obs("2026-08-28", 1.0)])
    dnse = make_dnse_snapshot(spec)

    def fetch(ticker, source, start, end):
        return FetchOutcome("empty")

    evidence, _ = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert evidence["dnse_missing_excluded_by_recovery_bound_count"] == 0
    assert evidence["dnse_exact_session_count"] == 1
    # BBB was genuinely attempted at KBS, uncapped; its clean SESSION_MISSING never reaches VCI
    # (DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1).
    assert evidence["recovery_attempts"]["KBS"] == 1
    assert evidence["recovery_attempts"]["VCI"] == 0


# ---- select_sentinel_cohort: deterministic, versioned, no random sampling ----

def test_sentinel_cohort_is_deterministic_across_repeated_calls():
    metadata = {
        "HPG": {"exchange": "HOSE", "market_cap": 100}, "VCB": {"exchange": "HOSE", "market_cap": 200},
        "SHS": {"exchange": "HNX", "market_cap": 50}, "ACB": {"exchange": "UPCOM", "market_cap": 30},
    }
    first = select_sentinel_cohort(candidate_metadata=metadata, dnse_exact_tickers=["HPG", "VCB"])
    second = select_sentinel_cohort(candidate_metadata=metadata, dnse_exact_tickers=["HPG", "VCB"])
    assert first == second
    assert first["cohort_version"] == "dnse_quality_sentinel_cohort/v1"


def test_sentinel_cohort_composition_reasons():
    metadata = {
        "HPG": {"exchange": "HOSE", "market_cap": 500}, "VCB": {"exchange": "HOSE", "market_cap": 900},
        "SHS": {"exchange": "HNX", "market_cap": 50}, "ACB": {"exchange": "UPCOM", "market_cap": 30},
        "ZZZ": {"exchange": "HOSE", "market_cap": None},  # missing market_cap never crashes ranking
    }
    cohort = select_sentinel_cohort(
        candidate_metadata=metadata, dnse_exact_tickers=["ZZZ"],
        watchlist=["HPG"], governed_liquid_sample_size=1, per_exchange_sample_size=1,
    )
    assert "HPG" in cohort["reasons"] and "OWNER_WATCHLIST_11" in cohort["reasons"]["HPG"]
    assert "VCB" in cohort["reasons"] and "GOVERNED_LIQUID_TOP" in cohort["reasons"]["VCB"]  # highest market_cap
    assert "CROSS_EXCHANGE_HNX" in cohort["reasons"]["SHS"]
    assert "CROSS_EXCHANGE_UPCOM" in cohort["reasons"]["ACB"]
    assert "DNSE_EXACT_SESSION_SAMPLE" in cohort["reasons"]["ZZZ"]
    assert cohort["tickers"] == sorted(cohort["tickers"])  # deduplicated, deterministic order


def test_sentinel_cohort_never_random_ties_break_on_ticker():
    metadata = {"BBB": {"exchange": "HOSE", "market_cap": 100}, "AAA": {"exchange": "HOSE", "market_cap": 100}}
    cohort = select_sentinel_cohort(
        candidate_metadata=metadata, dnse_exact_tickers=[],
        governed_liquid_sample_size=1, per_exchange_sample_size=0,
    )
    assert cohort["reasons"]["AAA"] == ["GOVERNED_LIQUID_TOP"]  # equal market_cap -> ticker A-Z tiebreak
    assert "BBB" not in cohort["reasons"]


# ---- Pass 5 DNSE quality sentinel: independent of Pass 2-4 gap-recovery scope ----

def test_sentinel_none_preserves_pre_sentinel_behavior_exactly():
    dnse = make_dnse_snapshot({"AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 10.0)])})
    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=lambda *a: (_ for _ in ()).throw(AssertionError("no fetch expected")),
        request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert evidence["dnse_quality_sentinel"] is None
    assert projected["records"]["AAA"]["multi_source_recovery_result"] == "DNSE_RESOLVED_NO_RECOVERY_NEEDED"


def test_sentinel_queries_vci_and_kbs_for_a_dnse_resolved_ticker_pass_2_4_would_skip():
    dnse_native_close = 79.2
    dnse = make_dnse_snapshot({"GMD": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, dnse_native_close, volume=20800)])})
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        # VCI and KBS agree with each other and materially conflict with DNSE's 79.2 close.
        return FetchOutcome("success", data=make_df([(TARGET, 77600.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": f"L-{source}"}])

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=["GMD"],
    )
    assert set(calls) == {("GMD", "VCI"), ("GMD", "KBS")}  # both queried despite DNSE already resolving it
    rec = projected["records"]["GMD"]
    assert rec["multi_source_recovery_result"] == "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE"
    assert rec["dnse_observation_overridden"] is True
    assert rec["observations"][0]["close"] == 77.6
    dnse_ob = next(o for o in evidence["records"]["GMD"]["observations"] if o["source"] == "DNSE")
    assert dnse_ob["normalized"]["close_vnd"] == dnse_native_close  # DNSE observation retained
    assert evidence["dnse_quality_sentinel"]["health"]["conflict_count"] == 1


def test_sentinel_leaves_agreeing_dnse_resolved_ticker_untouched():
    dnse = make_dnse_snapshot({"HPG": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 25.0, volume=1000000)])})

    def fetch(ticker, source, start, end):
        return FetchOutcome("success", data=make_df([(TARGET, 25000.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=["HPG"],
    )
    assert projected["records"]["HPG"]["multi_source_recovery_result"] == "DNSE_RESOLVED_NO_RECOVERY_NEEDED"
    assert evidence["dnse_quality_sentinel"]["health"]["corroborated_count"] == 1


def test_sentinel_reuses_pass_3_4_observations_for_a_dnse_missing_sentinel_member():
    """A sentinel member DNSE did NOT resolve is already in Pass 3/4's gap-recovery scope --
    Pass 5 must never issue a second, duplicate fetch for it."""
    dnse = make_dnse_snapshot({"BBB": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 20.0)])})
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return FetchOutcome("success", data=make_df([(TARGET, 20500.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L1"}])

    resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=["BBB"],
    )
    assert calls == [("BBB", "KBS")]  # exactly Pass 3's own single attempt -- no Pass 5 repeat


def _broad_conflict_dnse_and_fetch():
    """6 DNSE-exact tickers; VCI and KBS agree with each other, materially conflicting with
    every DNSE bar -- a real provider-wide degraded shape (this milestone's own real
    2026-09-03 sentinel validation found exactly this: 18/18 DNSE-exact tickers conflicted)."""
    dnse_native_close = 10.0
    spec = {f"C{i}": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, dnse_native_close)]) for i in range(6)}
    dnse = make_dnse_snapshot(spec)

    def fetch(ticker, source, start, end):
        return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    return dnse, fetch, list(spec)


def test_broad_dnse_conflict_never_raises_inside_the_resolver_itself():
    """resolve_multi_source_exact_session_snapshot's own job is to resolve and honestly report
    evidence -- it must always return real evidence/projected artifacts, even when the
    sentinel finds DNSE_BROAD_STALE_OR_INCOMPLETE_EOD, so a caller can persist them. The
    fail-closed policy decision belongs one layer up (assert_dnse_quality_acceptable)."""
    dnse, fetch, cohort = _broad_conflict_dnse_and_fetch()
    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=cohort,
    )
    health = evidence["dnse_quality_sentinel"]["health"]
    assert health["state"] == "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"
    assert health["conflict_count"] == 6
    assert projected["records"]["C0"]["multi_source_recovery_result"] == \
        "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE"


def test_assert_dnse_quality_acceptable_raises_on_broad_verdict():
    dnse, fetch, cohort = _broad_conflict_dnse_and_fetch()
    evidence, _ = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=cohort,
    )
    with pytest.raises(DnseProviderWideQualityDegraded) as excinfo:
        assert_dnse_quality_acceptable(evidence)
    assert excinfo.value.dnse_quality_sentinel["health"]["state"] == "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"


def test_assert_dnse_quality_acceptable_is_noop_when_healthy_or_no_sentinel():
    assert_dnse_quality_acceptable({"dnse_quality_sentinel": None})  # no sentinel_cohort was run
    assert_dnse_quality_acceptable({"dnse_quality_sentinel": {"health": {"state": "DNSE_EXACT_AND_CORROBORATED"}}})
    assert_dnse_quality_acceptable({"dnse_quality_sentinel": {"health": {"state": "DNSE_MATERIAL_CONFLICT"}}})


# ---- resolve_exact_session_with_autorecovery: P0 DEFECT 1 (automatic DEGRADED_PROVIDER_RECOVERY_MODE) ----

def test_autorecovery_healthy_day_is_a_single_pass_and_not_triggered():
    """A non-degraded sentinel verdict must behave exactly like a single
    resolve_multi_source_exact_session_snapshot call -- the cheap path, per
    WHEN_DNSE_HEALTHY_POLICY -- with no second resolver pass and no extra live fetch."""
    dnse = make_dnse_snapshot({"HPG": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 25.0, volume=1000000)])})
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return FetchOutcome("success", data=make_df([(TARGET, 25000.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    evidence, projected = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=["HPG"],
    )
    assert calls == [("HPG", "VCI"), ("HPG", "KBS")]  # exactly Pass 5's own single round, never repeated
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_NOT_TRIGGERED
    assert evidence["degraded_provider_recovery"]["expanded_ticker_count"] == 0
    assert projected["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_NOT_TRIGGERED
    assert projected["dnse_provider_health_state"] == "DNSE_EXACT_AND_CORROBORATED"
    assert_self_consistent(projected)


def test_autorecovery_empty_sentinel_cohort_is_not_triggered():
    """An empty sentinel_cohort still runs Pass 5 (0 members, 0 fetches) rather than skipping it
    entirely -- health resolves to DNSE_EXACT_BUT_UNCORROBORATED (assessed=0), never
    BROAD_STALE_OR_INCOMPLETE_EOD, so degraded-provider-recovery must not trigger."""
    dnse = make_dnse_snapshot({"AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 10.0)])})
    evidence, projected = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=lambda *a: (_ for _ in ()).throw(AssertionError("no fetch expected")),
        request_delay=0.0, sleep_fn=lambda s: None, sentinel_cohort=[],
    )
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_EXACT_BUT_UNCORROBORATED"
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_NOT_TRIGGERED
    assert projected["dnse_provider_health_state"] == "DNSE_EXACT_BUT_UNCORROBORATED"


def _real_20260903_shaped_degraded_scenario():
    """Mirrors this milestone's own retained real 2026-09-03 evidence exactly (see
    operations-review/multi-source-exact-session-market-evidence-and-daily-resilience-v1-20260903/
    sentinel-validation-20260903/sentinel_result_BROAD.json): 18 DNSE-exact tickers, a sentinel
    cohort whose DNSE_EXACT_SESSION_SAMPLE component happens to cover all 18 (DEFAULT_DNSE_EXACT_
    SAMPLE_SIZE=18 == the real count that day), VCI==KBS agreeing with each other and materially
    conflicting with DNSE for every one of them -> DNSE_BROAD_STALE_OR_INCOMPLETE_EOD with 18/18
    conflict, 0/18 corroborated -- byte-identical to the real retained verdict."""
    dnse_native_close = 10.0
    tickers = [f"D{i:02d}" for i in range(18)]
    spec = {t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, dnse_native_close)]) for t in tickers}
    dnse = make_dnse_snapshot(spec)

    def fetch(ticker, source, start, end):
        return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    return dnse, fetch, tickers


def test_autorecovery_real_20260903_shape_needs_zero_new_fetches_and_is_accepted():
    """The decisive real-evidence validation this milestone requires: when the sentinel cohort's
    DNSE_EXACT_SESSION_SAMPLE already covers 100% of DNSE's exact-session tickers (the real
    2026-09-03 case), DEGRADED_PROVIDER_RECOVERY_MODE's expansion has nothing left to query --
    every DNSE-exact ticker is already independently resolved from the sentinel pass alone, no
    live probe is spent reproducing numbers already retained, and the corrected policy distrusts
    DNSE's own bars in favor of the corroborated VCI/KBS value for every one of them."""
    dnse, fetch, tickers = _real_20260903_shaped_degraded_scenario()
    calls = []

    def counting_fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return fetch(ticker, source, start, end)

    evidence, projected = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=counting_fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=tickers,
    )
    assert evidence["dnse_quality_sentinel"]["health"]["state"] == "DNSE_BROAD_STALE_OR_INCOMPLETE_EOD"
    assert evidence["dnse_quality_sentinel"]["health"]["conflict_count"] == 18
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_COMPLETED
    assert evidence["degraded_provider_recovery"]["expanded_ticker_count"] == 0
    # Every (ticker, source) pair fetched exactly once across the WHOLE run, healthy-cohort pass
    # and expansion pass combined -- the expansion pass added zero new live queries.
    assert len(calls) == len(set(calls)) == 18 * 2
    # DNSE is no longer blindly trusted for any of the 18 -- every one now resolves via the
    # corroborated non-DNSE basis, matching the real retained per_ticker_resolution verdict.
    for ticker in tickers:
        assert projected["records"][ticker]["multi_source_recovery_result"] == \
            "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE"
        assert projected["records"][ticker]["disposition"] == "EXACT_SESSION_RETAINED"
    # Coverage is unaffected (still 18/18 EXACT_SESSION_RETAINED) -- only WHICH source each row
    # trusts changed, matching the real 772/1683 (45.87%) retained finding's own composition.
    assert projected["exact_session_observed_count"] == 18
    assert_self_consistent(projected)


def test_autorecovery_partial_sentinel_overlap_expands_only_uncovered_dnse_exact_tickers():
    """General case: the sentinel's small cohort does NOT already cover every DNSE-exact ticker
    (unlike the real 2026-09-03 coincidence). Only the tickers outside the original cohort may be
    newly queried; they are KBS-first, while the original sentinel alone remains dual-source."""
    dnse_native_close = 10.0
    all_exact = [f"E{i:02d}" for i in range(10)]
    spec = {t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, dnse_native_close)]) for t in all_exact}
    dnse = make_dnse_snapshot(spec)
    small_cohort = all_exact[:6]  # sentinel only ever covered 6/10 DNSE-exact tickers
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    evidence, projected = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=small_cohort,
    )
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_COMPLETED
    assert evidence["degraded_provider_recovery"]["expanded_ticker_count"] == 4  # E06..E09
    assert evidence["degraded_provider_recovery"]["expanded_recovery_attempts"] == {"VCI": 0, "KBS": 4}
    # Every newly-covered ticker is KBS-first. VCI is not a market-wide corroborator: the only
    # dual-source work is the retained, small health sentinel.
    newly_covered = [t for t in all_exact if t not in small_cohort]
    assert len(newly_covered) == 4
    for ticker in newly_covered:
        assert calls.count((ticker, "KBS")) == 1
        assert calls.count((ticker, "VCI")) == 0
        assert projected["records"][ticker]["observations"][0]["provider"] == "KBS"
    # No (ticker, source) pair anywhere in the run was ever fetched more than once. The six
    # sentinel names retain VCI+KBS; four recovered names add KBS only.
    assert len(calls) == len(set(calls))
    assert len(calls) == 6 * 2 + 4
    # Now every DNSE-exact ticker, not just the original small cohort, correctly distrusts DNSE.
    for ticker in small_cohort:
        assert projected["records"][ticker]["multi_source_recovery_result"] == \
            "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE"
    for ticker in newly_covered:
        assert projected["records"][ticker]["multi_source_recovery_result"] == \
            "DEGRADED_DNSE_QUARANTINED_SINGLE_SOURCE_KBS"
    assert_self_consistent(projected)


def test_autorecovery_uses_vci_only_when_marketwide_kbs_is_unusable():
    """VCI remains a per-ticker failover, not a second market-wide verification pass."""
    exact = [f"R{i:02d}" for i in range(8)]
    sentinel = exact[:6]
    dnse = make_dnse_snapshot({
        ticker: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 10.0)]) for ticker in exact
    })
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        if ticker == "R06" and source == "KBS":
            return FetchOutcome("empty")
        return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                            lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    evidence, projected = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda _seconds: None,
        sentinel_cohort=sentinel,
    )

    recovery = evidence["degraded_provider_recovery"]
    assert recovery["expanded_recovery_attempts"] == {"VCI": 1, "KBS": 2}
    assert recovery["expanded_primary_source"] == "KBS"
    assert recovery["expanded_fallback_source"] == "VCI"
    assert calls.count(("R06", "VCI")) == calls.count(("R06", "KBS")) == 1
    assert calls.count(("R07", "KBS")) == 1
    assert calls.count(("R07", "VCI")) == 0
    assert projected["records"]["R06"]["observations"][0]["provider"] == "VCI"
    assert projected["records"]["R07"]["observations"][0]["provider"] == "KBS"
    assert_self_consistent(projected)


def test_autorecovery_never_duplicates_a_source_ticker_fetch_when_gap_recovery_and_sentinel_overlap():
    """A gap-recovery KBS result and the small exact-name sentinel remain disjoint, and no
    ticker/source pair is requested more than once within the complete autorecovery run."""
    dnse_native_close = 10.0
    exact_tickers = [f"F{i:02d}" for i in range(6)]
    spec = {t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, dnse_native_close)]) for t in exact_tickers}
    spec["MISSING1"] = ("SESSION_MISSING", [_dnse_obs("2026-08-28", 1.0)])
    dnse = make_dnse_snapshot(spec)
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    evidence, projected = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=exact_tickers,
    )
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_COMPLETED
    # MISSING1 is DNSE-missing: its KBS success means no VCI attempt and no duplicated source pair.
    assert calls.count(("MISSING1", "KBS")) == 1
    assert calls.count(("MISSING1", "VCI")) == 0
    assert len(calls) == len(set(calls))  # no pair anywhere, from either pass or either call, twice


def test_autorecovery_pacing_delay_spent_once_per_genuine_fetch_not_per_call():
    """The memoizing fetcher owns provider pacing without any duplicate-request sleeps."""
    dnse_native_close = 10.0
    exact_tickers = [f"G{i:02d}" for i in range(6)]
    spec = {t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, dnse_native_close)]) for t in exact_tickers}
    dnse = make_dnse_snapshot(spec)
    sleeps = []

    def fetch(ticker, source, start, end):
        return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])

    evidence, _ = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=1.1, sleep_fn=sleeps.append,
        sentinel_cohort=exact_tickers,
    )
    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_COMPLETED
    # One launch interval occurs between consecutive calls from each source: VCI retains its
    # 1.1s sequential pace while qualified KBS uses its 0.25s policy.  No synthetic expansion
    # pass or duplicate cache request contributes a further wait.
    assert len(sleeps) == 2 * (len(exact_tickers) - 1)
    assert sum(wait > 1.0 for wait in sleeps) == len(exact_tickers) - 1
    assert sum(0.20 < wait < 0.30 for wait in sleeps) == len(exact_tickers) - 1


def test_provider_scheduler_caps_workers_deduplicates_and_returns_input_order():
    active = 0
    maximum_active = 0
    calls = []
    lock = threading.Lock()

    def fetch(ticker, source, start, end):
        nonlocal active, maximum_active
        del source, start, end
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            calls.append(ticker)
        time.sleep(0.02)
        with lock:
            active -= 1
        return FetchOutcome("empty", errors=[ticker], request_attempts=1)

    scheduler = _ProviderAwareMemoizingFetch(
        fetch,
        provider_policies={"KBS": _ProviderSchedulePolicy(2, 0.0, 1.0)},
        sleep_fn=lambda _seconds: None,
    )
    outcomes = scheduler.fetch_many([
        ("BBB", "KBS", "start", "end"),
        ("AAA", "KBS", "start", "end"),
        ("BBB", "KBS", "start", "end"),
        ("CCC", "KBS", "start", "end"),
    ])

    assert maximum_active == 2
    assert sorted(calls) == ["AAA", "BBB", "CCC"]
    assert [outcome.errors for outcome in outcomes] == [["BBB"], ["AAA"], ["BBB"], ["CCC"]]


def test_provider_scheduler_shares_retry_after_before_next_dispatch():
    clock = [0.0]
    waits = []
    call_times = []

    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    def fetch(ticker, source, start, end):
        del source, start, end
        call_times.append((ticker, clock[0]))
        return FetchOutcome(
            "empty", request_attempts=1,
            http_429_count=1 if ticker == "AAA" else 0,
            retry_after_seconds=5.0 if ticker == "AAA" else 0.0,
        )

    scheduler = _ProviderAwareMemoizingFetch(
        fetch,
        provider_policies={"KBS": _ProviderSchedulePolicy(1, 0.0, 1.0)},
        sleep_fn=sleep,
        clock=lambda: clock[0],
    )
    scheduler.fetch_many([
        ("AAA", "KBS", "start", "end"),
        ("BBB", "KBS", "start", "end"),
    ])

    assert waits == [5.0]
    assert call_times == [("AAA", 0.0), ("BBB", 5.0)]


def test_runtime_guard_aborts_from_small_timed_sample_with_provider_telemetry():
    """A slow first handful of sequential requests must stop Daily before a market-wide hour run."""
    clock = [0.0]
    guard = _DailyRecoveryRuntimeGuard(
        request_delay=1.1, runtime_budget_seconds=300.0, clock=lambda: clock[0],
    )
    guard.set_plan(stage="DNSE_GAP_RECOVERY_KBS_FIRST", remaining_by_source={"VCI": 0, "KBS": 100})
    with pytest.raises(DailyRecoveryRuntimeBudgetExceeded) as raised:
        for _ in range(5):
            guard.observe(
                ticker="AAA", source="KBS",
                outcome=FetchOutcome("failed", errors=["KBS:read_timeout"], transient_failure=True,
                                     request_attempts=2, retry_count=1, timeout_count=2),
                elapsed_seconds=45.0,
            )
            clock[0] += 46.1
    diagnostic = raised.value.diagnostic
    assert diagnostic["stage"] == "DNSE_GAP_RECOVERY_KBS_FIRST"
    assert diagnostic["request_count"] == 5
    assert diagnostic["providers"]["KBS"]["provider_attempts"] == 10
    assert diagnostic["providers"]["KBS"]["retries"] == 5
    assert diagnostic["providers"]["KBS"]["timeouts"] == 10
    assert diagnostic["concurrency"]["enabled"] is False
    assert diagnostic["projected_total_seconds"] > diagnostic["runtime_budget_seconds"]


# ---- P0 DEFECT B integration: DNSE quarantined from FINAL resolution once broadly degraded ----
# DAILY_GOVERNED_PREVIOUS_SESSION_AND_DEGRADED_SOURCE_FINAL_HARDENING_V1

def test_autorecovery_quarantines_dnse_across_all_four_degraded_mode_outcomes():
    """End-to-end proof that resolve_exact_session_with_autorecovery wires
    resolve_ticker_degraded_dnse in, covering the required regressions in one real run: 6
    DNSE-exact tickers, sentinel_cohort covers all 6 (>= DNSE_BROAD_MIN_ASSESSED_COUNT=5), each
    ticker exercises a DIFFERENT one of the four degraded-mode rules."""
    dnse_native = 10.0
    tickers = [f"Q{i}" for i in range(6)]
    spec = {t: ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, dnse_native)]) for t in tickers}
    dnse = make_dnse_snapshot(spec)

    def fetch(ticker, source, start, end):
        if ticker == "Q0":  # VCI+KBS agree with each other, conflict with DNSE
            return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                                 lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])
        if ticker == "Q1":  # VCI+KBS agree with each other AND with DNSE (passive agreement)
            return FetchOutcome("success", data=make_df([(TARGET, dnse_native * 1000)]),
                                 lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])
        if ticker == "Q2":  # VCI only
            if source == "VCI":
                return FetchOutcome("success", data=make_df([(TARGET, 8000.0)]),
                                     lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])
            return FetchOutcome("empty")
        if ticker == "Q3":  # KBS only
            if source == "KBS":
                return FetchOutcome("success", data=make_df([(TARGET, 9000.0)]),
                                     lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])
            return FetchOutcome("empty")
        if ticker == "Q4":  # VCI and KBS both present but conflict with EACH OTHER
            value = 8000.0 if source == "VCI" else 9500.0
            return FetchOutcome("success", data=make_df([(TARGET, value)]),
                                 lineage=[{"trading_session_date": TARGET, "source_record_hash": "L"}])
        # Q5: neither VCI nor KBS available
        return FetchOutcome("empty")

    evidence, projected = resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=tickers,
    )

    assert evidence["degraded_provider_recovery"]["mode"] == DEGRADED_RECOVERY_COMPLETED

    # Q0 and Q1: corroborated non-DNSE, counted as exact -- including the passive-agreement case.
    for ticker in ("Q0", "Q1"):
        rec = projected["records"][ticker]
        assert rec["disposition"] == "EXACT_SESSION_RETAINED"
        assert rec["multi_source_recovery_result"] == "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE"
        assert rec["observations"][0]["provider"] == "VCI"

    # Q2/Q3: single usable secondary wins, DNSE never the resolved provider.
    q2, q3 = projected["records"]["Q2"], projected["records"]["Q3"]
    assert q2["disposition"] == "EXACT_SESSION_RETAINED"
    assert q2["observations"][0]["provider"] == "VCI"
    assert q2["multi_source_recovery_result"] == "DEGRADED_DNSE_QUARANTINED_SINGLE_SOURCE_VCI"
    assert q3["disposition"] == "EXACT_SESSION_RETAINED"
    assert q3["observations"][0]["provider"] == "KBS"
    assert q3["multi_source_recovery_result"] == "DEGRADED_DNSE_QUARANTINED_SINGLE_SOURCE_KBS"

    # Q4: VCI/KBS conflict -- unresolved, downgraded off EXACT_SESSION_RETAINED, never DNSE either.
    q4 = projected["records"]["Q4"]
    assert q4["disposition"] == "SESSION_MISSING"
    assert q4["multi_source_recovery_result"] == "DEGRADED_DNSE_QUARANTINED_UNRESOLVED_SOURCE_CONFLICT"
    assert not any(row["session"] == TARGET for row in q4["observations"])

    # Q5: no secondary at all -- unresolved despite DNSE's own same-dated bar.
    q5 = projected["records"]["Q5"]
    assert q5["disposition"] == "SESSION_MISSING"
    assert not any(row["session"] == TARGET for row in q5["observations"])

    # Required regression 10: final coverage counts only the 4 justified resolutions, never all 6.
    assert projected["exact_session_observed_count"] == 4
    assert evidence["resolved_exact_session_count"] == 4

    # DNSE's own observation is retained as evidence for every ticker, including the two
    # downgraded ones -- never deleted, only excluded from winning.
    for ticker in tickers:
        dnse_ob = next(o for o in evidence["records"][ticker]["observations"] if o["source"] == "DNSE")
        assert dnse_ob["status"] == "EXACT_SESSION_OBSERVED"

    # Required regression 11: RAW_AS_TRADED/PIT authority boundary is untouched by this milestone.
    assert evidence["authority_boundary"]["RAW_AS_TRADED"] == "NOT_PROMOTED"
    assert evidence["authority_boundary"]["HISTORICAL_PIT"] == "BLOCKED"
    assert evidence["pit_backtest_eligible"] is False
    assert evidence["is_actionable_for_execution"] is False


# ---- DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1 (2026-09-04) ----------------------------
# recovery_eligibility_projection pre-filter, residual-gap sentinel gate, VCI-fallback-error-only.

def _eligibility_projection(*, ineligible: dict[str, str]) -> dict:
    """A minimal, already-``available`` projection shape -- see
    daily_recovery_eligibility_projection.project_recovery_eligibility's real return shape."""
    return {
        "available": True,
        "per_ticker": {
            ticker: {"recovery_eligible": False, "reason_code": reason}
            for ticker, reason in ineligible.items()
        },
        "source_evidence_identities": {"test_fixture": True},
    }


def test_non_current_recovery_exclusion_never_spends_a_request():
    """A DNSE gap already known ineligible (e.g. corroborated delisted) must get zero KBS/VCI
    requests, keep its true DNSE disposition, and carry an explicit ineligibility reason code."""
    dnse = make_dnse_snapshot({
        "AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 1.0)]),
        "DELISTED1": ("PROVIDER_REJECTED", []),
        "GENUINE_GAP": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 2.0)]),
    })
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        if ticker == "GENUINE_GAP":
            return FetchOutcome("success", data=make_df([(TARGET, 2000.0)]))
        raise AssertionError(f"recovery-ineligible ticker {ticker} must never be fetched")

    projection = _eligibility_projection(ineligible={"DELISTED1": "RECOVERY_INELIGIBLE_INACTIVE_OR_DELISTED"})
    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        recovery_eligibility_projection=projection,
    )
    assert {t for t, _ in calls} == {"GENUINE_GAP"}
    assert evidence["dnse_missing_excluded_by_recovery_ineligibility_count"] == 1
    assert evidence["dnse_missing_excluded_by_recovery_ineligibility_tickers"] == ["DELISTED1"]
    # True DNSE disposition preserved, never relabeled.
    assert projected["records"]["DELISTED1"]["disposition"] == "PROVIDER_REJECTED"
    for source in ("KBS", "VCI"):
        stub = next(o for o in evidence["records"]["DELISTED1"]["observations"] if o["source"] == source)
        assert stub["status"] == "NOT_APPLICABLE"
        assert stub["reason_code"] == "NOT_ATTEMPTED_RECOVERY_INELIGIBLE_INACTIVE_OR_DELISTED"
    assert projected["records"]["GENUINE_GAP"]["disposition"] == "EXACT_SESSION_RETAINED"


def test_recovery_eligibility_projection_none_is_byte_identical_to_no_filter():
    """The default (no projection given) must exercise every DNSE-missing ticker exactly as
    before this milestone -- full backward compatibility for every existing caller."""
    dnse = make_dnse_snapshot({"BBB": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 1.0)])})

    def fetch(ticker, source, start, end):
        return FetchOutcome("empty")

    evidence, _ = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert evidence["dnse_missing_excluded_by_recovery_ineligibility_count"] == 0
    assert evidence["recovery_eligibility_projection_summary"] is None
    assert evidence["recovery_attempts"]["KBS"] == 1


def _kbs_fallback_helper_cases():
    return [
        ("SESSION_MISSING", False), ("SOURCE_REJECTED", True),
        ("TRANSPORT_FAILED", True), ("MALFORMED", True), ("EXACT_SESSION_OBSERVED", False),
    ]


@pytest.mark.parametrize("status,expected", _kbs_fallback_helper_cases())
def test_kbs_result_warrants_vci_fallback_only_for_provider_errors(status, expected):
    assert _kbs_result_warrants_vci_fallback(status) is expected


# ---- select_residual_gap_sentinel: deterministic, versioned, stratified by recency ----------

def _sentinel_dnse_snapshot(latest_session_by_ticker: dict[str, str | None]) -> dict:
    records = {}
    for ticker, latest in latest_session_by_ticker.items():
        obs = [_dnse_obs(latest, 1.0)] if latest else []
        records[ticker] = {"disposition": "SESSION_MISSING", "observations": obs}
    return {"records": records}


def test_select_residual_gap_sentinel_is_deterministic():
    latest = {f"T{i:03d}": (None if i % 5 == 0 else f"2026-08-{20 + (i % 8):02d}") for i in range(40)}
    snapshot = _sentinel_dnse_snapshot(latest)
    metadata = {t: {"exchange": "HOSE" if i % 2 == 0 else "UPCOM"} for i, t in enumerate(latest)}
    first = select_residual_gap_sentinel(
        recovery_eligible_missing_tickers=list(latest), dnse_snapshot=snapshot,
        candidate_metadata=metadata, target_session=TARGET, size=12,
    )
    second = select_residual_gap_sentinel(
        recovery_eligible_missing_tickers=list(latest), dnse_snapshot=snapshot,
        candidate_metadata=metadata, target_session=TARGET, size=12,
    )
    assert first == second
    assert 0 < first["size"] <= 12
    assert sum(first["pool_sizes"].values()) == len(latest)


def test_select_residual_gap_sentinel_covers_no_observation_stratum():
    latest = {"A": None, "B": "2026-08-28", "C": "2026-08-27", "D": None, "E": "2026-08-21"}
    snapshot = _sentinel_dnse_snapshot(latest)
    metadata = {t: {"exchange": "HOSE"} for t in latest}
    cohort = select_residual_gap_sentinel(
        recovery_eligible_missing_tickers=list(latest), dnse_snapshot=snapshot,
        candidate_metadata=metadata, target_session=TARGET, size=8,
    )
    assert cohort["pool_sizes"]["no_observations"] == 2
    assert set(cohort["stratum_picks"]["no_observations"]) <= {"A", "D"}


# ---- residual-gap sentinel gate wired into resolve_multi_source_exact_session_snapshot ------

def _make_missing_universe(n: int) -> dict:
    spec = {}
    for i in range(n):
        spec[f"S{i:03d}"] = ("SESSION_MISSING", [_dnse_obs("2026-08-28", float(i))])
    return make_dnse_snapshot(spec)


def test_zero_yield_sentinel_stops_market_wide_kbs_fan_out():
    """A sentinel that recovers zero exact bars and hits zero provider errors (a clean 100%
    SESSION_MISSING sample) must stop KBS from ever being attempted on the rest -- no VCI either,
    and every un-attempted ticker keeps its honest SESSION_MISSING disposition."""
    dnse = _make_missing_universe(10)
    sentinel_tickers = ["S000", "S001", "S002"]
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        return FetchOutcome("empty")  # clean miss for every sentinel member, every source

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        residual_yield_sentinel_tickers=sentinel_tickers,
    )
    assert {t for t, s in calls} == set(sentinel_tickers)  # nobody outside the sentinel was ever called
    assert {s for _, s in calls} == {"KBS"}  # VCI never ran either (clean misses)
    sentinel_result = evidence["residual_gap_sentinel"]
    assert sentinel_result["decision"] == ZERO_OBSERVED_INCREMENTAL_YIELD_FOR_THIS_RUN
    assert sentinel_result["exact_count"] == 0
    assert sentinel_result["provider_error_count"] == 0
    for ticker in [f"S{i:03d}" for i in range(3, 10)]:
        assert projected["records"][ticker]["disposition"] == "SESSION_MISSING"
        for source in ("KBS", "VCI"):
            stub = next(o for o in evidence["records"][ticker]["observations"] if o["source"] == source)
            assert stub["reason_code"] == "NOT_ATTEMPTED_ZERO_YIELD_SENTINEL_GATE"
    assert evidence["recovery_attempts"] == {"KBS": 3, "VCI": 0}


def test_positive_yield_sentinel_permits_full_expansion():
    """One sentinel exact recovery must expand KBS to the rest of the eligible population."""
    dnse = _make_missing_universe(6)
    sentinel_tickers = ["S000", "S001"]
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        if ticker == "S000" and source == "KBS":
            return FetchOutcome("success", data=make_df([(TARGET, 1000.0)]))
        return FetchOutcome("empty")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        residual_yield_sentinel_tickers=sentinel_tickers,
    )
    assert evidence["residual_gap_sentinel"]["decision"] == POSITIVE_YIELD_EXPAND
    # every one of the 6 candidates got a genuine KBS attempt -- full expansion happened
    assert {t for t, s in calls if s == "KBS"} == {f"S{i:03d}" for i in range(6)}
    assert projected["records"]["S000"]["disposition"] == "EXACT_SESSION_RETAINED"


def test_provider_error_dominated_sentinel_is_not_misclassified_as_zero_yield():
    """A sentinel with zero exact hits but a genuine transport/provider error must NOT be
    treated as zero-yield evidence -- it still expands to the rest, and the erroring sentinel
    member correctly reaches VCI fallback."""
    dnse = _make_missing_universe(6)
    sentinel_tickers = ["S000", "S001"]
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        if ticker == "S000" and source == "KBS":
            return FetchOutcome("failed", errors=["transient_network_error"], transient_failure=True)
        if ticker == "S000" and source == "VCI":
            return FetchOutcome("success", data=make_df([(TARGET, 500.0)]))
        return FetchOutcome("empty")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        residual_yield_sentinel_tickers=sentinel_tickers,
    )
    sentinel_result = evidence["residual_gap_sentinel"]
    assert sentinel_result["decision"] == PROVIDER_ERROR_DOMINATED_NOT_ZERO_YIELD
    assert sentinel_result["exact_count"] == 0
    assert sentinel_result["provider_error_count"] == 1
    # Expansion still happened -- every candidate got a genuine KBS attempt.
    assert {t for t, s in calls if s == "KBS"} == {f"S{i:03d}" for i in range(6)}
    # S000's genuine KBS error correctly reached VCI and recovered there.
    assert projected["records"]["S000"]["disposition"] == "EXACT_SESSION_RETAINED"
    assert projected["records"]["S000"]["observations"][0]["provider"] == "VCI"


def test_sentinel_members_never_double_fetched_by_expansion_round():
    """A sentinel member must be fetched at most once per source across the whole run, even
    when the rest of the population expands -- no duplicate (ticker, source) network calls."""
    dnse = _make_missing_universe(6)
    sentinel_tickers = ["S000", "S001"]
    calls = []

    def fetch(ticker, source, start, end):
        calls.append((ticker, source))
        if ticker == "S000" and source == "KBS":
            return FetchOutcome("success", data=make_df([(TARGET, 1000.0)]))
        return FetchOutcome("empty")

    resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
        residual_yield_sentinel_tickers=sentinel_tickers,
    )
    assert len(calls) == len(set(calls))  # every (ticker, source) pair appears at most once


# ---- DAILY_GLOBAL_VNSTOCK_RATE_GOVERNOR_V1 (2026-09-04) ------------------------------------
# Retained-failure replay: reproduce today's request topology deterministically with a fake
# monotonic clock and confirm one shared budget governs every phase.

class _FakeGovernorClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _governed_fetch(outcome_for):
    """A fake fetch_single_source that consults whatever governor is currently active, exactly
    as the real vn_stock_pipeline._bounded_send_request_direct chokepoint does -- lets these
    resolver-level tests exercise the real cross-module integration seam (get_active_governor)
    without needing a real HTTP/vnstock layer underneath."""
    def fetch(ticker, source, start, end):
        active = get_active_governor()
        if active is not None:
            active.acquire(provider=source)
        return outcome_for(ticker, source)
    return fetch


def test_acceptance_b_dnse_health_sentinel_and_residual_gap_sentinel_share_one_budget():
    """The pre-existing DNSE quality/corroboration sentinel (Pass 5) and this milestone's own
    residual-gap incremental-yield sentinel (Pass 3 gate) must draw from the SAME shared
    governor, not each get a fresh quota -- this is precisely the 2026-09-04 live failure's
    root cause (independent per-mechanism pacing that combined to exceed vnai's single
    process-wide counter)."""
    # 5 DNSE-exact tickers (feed the Pass 5 DNSE-health sentinel via DNSE_EXACT_SESSION_SAMPLE)
    # + 6 DNSE-missing tickers (feed the residual-gap sentinel).
    spec = {}
    for i in range(5):
        spec[f"E{i:03d}"] = ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, float(i))])
    for i in range(6):
        spec[f"M{i:03d}"] = ("SESSION_MISSING", [_dnse_obs("2026-08-28", float(i))])
    dnse = make_dnse_snapshot(spec)

    clock = _FakeGovernorClock()
    governor = VnstockRateGovernor(limit=4, hard_ceiling=60, clock=clock, sleep_fn=lambda s: clock.advance(s))

    def outcome_for(ticker, source):
        return FetchOutcome("empty")  # clean miss everywhere -- isolates budget-sharing, not yield

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=_governed_fetch(outcome_for), request_delay=0.0, sleep_fn=lambda s: None,
        sentinel_cohort=[f"E{i:03d}" for i in range(5)],
        residual_yield_sentinel_tickers=[f"M{i:03d}" for i in range(6)],
        rate_governor=governor,
    )
    # Pass 3 gate: 6 residual-gap-sentinel KBS calls, all clean SESSION_MISSING -> zero yield,
    # never expands, never reaches VCI. Pass 5: 5 DNSE-exact tickers x 2 sources (VCI+KBS) = 10.
    # Total genuine requests = 6 + 10 = 16, ALL through the one governor.
    assert governor.attempts == 16
    assert governor.max_window_utilization <= governor.limit
    assert governor.waits > 0  # 16 requests against a limit of 4 must have imposed real pacing
    assert evidence["vnstock_rate_governor"]["attempts"] == 16
    assert evidence["residual_gap_sentinel"]["decision"] == ZERO_OBSERVED_INCREMENTAL_YIELD_FOR_THIS_RUN


def test_acceptance_g_runtime_forecast_stops_impossible_broad_expansion_before_it_starts():
    """When the shared governor's own steady-state pacing alone would blow the runtime budget,
    the existing DailyRecoveryRuntimeBudgetExceeded guard must fire BEFORE a long fan-out is
    launched -- not merely abort partway through hundreds of requests."""
    # A large recovery-eligible population (400 gaps) with a positive-yield sentinel decision
    # (so the code WOULD otherwise expand to all 400), a tiny runtime budget, and a governor
    # limit low enough that 400 requests could never fit in budget.
    spec = {"E000": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 1.0)])}
    for i in range(400):
        spec[f"M{i:03d}"] = ("SESSION_MISSING", [_dnse_obs("2026-08-28", float(i))])
    dnse = make_dnse_snapshot(spec)

    clock = _FakeGovernorClock()
    governor = VnstockRateGovernor(limit=10, hard_ceiling=60, clock=clock, sleep_fn=lambda s: clock.advance(s))
    runtime_guard = _DailyRecoveryRuntimeGuard(
        request_delay=0.0, runtime_budget_seconds=30.0, clock=clock, rate_governor=governor,
    )
    calls = []

    def outcome_for(ticker, source):
        calls.append((ticker, source))
        if ticker == "M000":
            return FetchOutcome("success", data=make_df([(TARGET, 1000.0)]))  # sentinel: positive yield
        return FetchOutcome("empty")

    with pytest.raises(DailyRecoveryRuntimeBudgetExceeded) as raised:
        resolve_multi_source_exact_session_snapshot(
            dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
            fetch_single_source=_governed_fetch(outcome_for), request_delay=0.0, sleep_fn=lambda s: None,
            residual_yield_sentinel_tickers=["M000", "M001", "M002", "M003"],
            recovery_runtime_guard=runtime_guard, rate_governor=governor,
        )
    # 400 remaining requests at this governor's pacing (60/10 = 6s/request) alone project to
    # 2400s, far over the 30s budget -- the guard must catch this before hundreds of requests.
    assert raised.value.diagnostic["projected_total_seconds"] > runtime_guard.runtime_budget_seconds
    assert len(calls) < 50  # aborted long before anything resembling a full 400-ticker fan-out


def test_acceptance_h_activity_aware_semantics_unchanged_under_the_new_governor():
    """Regression: every DAILY_ACTIVITY_AWARE_ADAPTIVE_GAP_RECOVERY_V1 behavior (ineligible
    exclusion, clean-KBS-miss never reaching VCI, zero-yield sentinel stopping fan-out,
    SESSION_MISSING never becoming ZERO_TRADE) must hold identically now that a real governor
    is active for the whole call."""
    dnse = make_dnse_snapshot({
        "AAA": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET, 1.0)]),
        "DELISTED1": ("PROVIDER_REJECTED", []),
        "GENUINE_GAP": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 2.0)]),
    })
    clock = _FakeGovernorClock()
    governor = VnstockRateGovernor(limit=5, hard_ceiling=60, clock=clock, sleep_fn=lambda s: clock.advance(s))

    def outcome_for(ticker, source):
        assert ticker != "DELISTED1"  # never spend a request on an ineligible ticker
        return FetchOutcome("empty")  # clean miss for GENUINE_GAP on every source

    projection = _eligibility_projection(ineligible={"DELISTED1": "RECOVERY_INELIGIBLE_INACTIVE_OR_DELISTED"})
    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=_governed_fetch(outcome_for), request_delay=0.0, sleep_fn=lambda s: None,
        recovery_eligibility_projection=projection, rate_governor=governor,
    )
    assert evidence["dnse_missing_excluded_by_recovery_ineligibility_count"] == 1
    assert projected["records"]["DELISTED1"]["disposition"] == "PROVIDER_REJECTED"  # never relabeled
    assert projected["records"]["GENUINE_GAP"]["disposition"] == "SESSION_MISSING"  # never ZERO_TRADE
    vci_obs = next(o for o in evidence["records"]["GENUINE_GAP"]["observations"] if o["source"] == "VCI")
    assert vci_obs["status"] == "NOT_APPLICABLE"  # clean KBS miss never reached VCI
    assert governor.attempts == 1  # exactly one genuine request: GENUINE_GAP x KBS
