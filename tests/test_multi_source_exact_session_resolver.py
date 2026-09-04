import pandas as pd
import pytest

from field_temporal_contract import stable_id
from multi_source_exact_session_resolver import (
    DEGRADED_RECOVERY_COMPLETED,
    DEGRADED_RECOVERY_NOT_TRIGGERED,
    DnseProviderWideQualityDegraded,
    MultiSourceResolverError,
    assert_dnse_quality_acceptable,
    resolve_exact_session_with_autorecovery,
    resolve_multi_source_exact_session_snapshot,
    select_sentinel_cohort,
)
from vn_stock_pipeline import FetchOutcome

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


def test_vci_recovers_dnse_missing_ticker_without_touching_kbs():
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
    assert calls == [("BBB", "VCI")]
    rec = projected["records"]["BBB"]
    assert rec["disposition"] == "EXACT_SESSION_RETAINED"
    assert rec["observations"][0]["provider"] == "VCI"
    assert rec["observations"][0]["close"] == 20.5  # native scale, matching DNSE's own convention
    assert rec["payload_hash"] == "L1"
    assert evidence["recovery_successes"] == {"VCI": 1, "KBS": 0}


def test_kbs_recovers_when_vci_empty():
    dnse = make_dnse_snapshot({"CCC": ("SESSION_MISSING", [_dnse_obs("2026-08-28", 30.0)])})

    def fetch(ticker, source, start, end):
        if source == "VCI":
            return FetchOutcome("empty")
        return FetchOutcome("success", data=make_df([(TARGET, 30300.0)]),
                             lineage=[{"trading_session_date": TARGET, "source_record_hash": "L2"}])

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    rec = projected["records"]["CCC"]
    assert rec["disposition"] == "EXACT_SESSION_RETAINED"
    assert rec["observations"][0]["provider"] == "KBS"
    assert evidence["recovery_attempts"] == {"VCI": 1, "KBS": 1}


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
    vci_obs = next(o for o in evidence["records"]["GGG"]["observations"] if o["source"] == "VCI")
    assert vci_obs["status"] == "SESSION_MISSING"
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
        # Odd-indexed missing tickers recover on VCI, even-indexed need KBS, one stays unresolved.
        idx = int(ticker[1:])
        if idx == 19:
            return FetchOutcome("empty")
        if source == "VCI" and idx % 2 == 1:
            return FetchOutcome("success", data=make_df([(TARGET, float(idx) * 1000)]))
        if source == "KBS" and idx % 2 == 0:
            return FetchOutcome("success", data=make_df([(TARGET, float(idx) * 1000)]))
        return FetchOutcome("empty")

    evidence, projected = resolve_multi_source_exact_session_snapshot(
        dnse_snapshot=dnse, target_session=TARGET, requested_at=REQUESTED_AT,
        fetch_single_source=fetch, request_delay=0.0, sleep_fn=lambda s: None,
    )
    assert {t for t, s in calls if s == "VCI"} == set(tickers[5:])  # every DNSE-missing ticker tried VCI
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
    assert evidence["recovery_attempts"]["VCI"] == 1  # BBB was genuinely attempted, uncapped


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
    assert calls == [("BBB", "VCI")]  # exactly Pass 3's own single attempt -- no Pass 5 repeat


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
    newly queried; sentinel-covered ones must never be re-fetched."""
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
    assert evidence["degraded_provider_recovery"]["expanded_recovery_attempts"] == {"VCI": 4, "KBS": 4}
    # Every one of the 4 newly-covered tickers was queried exactly once per source -- never twice.
    newly_covered = [t for t in all_exact if t not in small_cohort]
    assert len(newly_covered) == 4
    for ticker in newly_covered:
        assert calls.count((ticker, "VCI")) == 1
        assert calls.count((ticker, "KBS")) == 1
    # No (ticker, source) pair anywhere in the run was ever fetched more than once, including the
    # original 6-ticker cohort's own pairs (served from cache on the expansion's second pass).
    assert len(calls) == len(set(calls))
    assert len(calls) == 10 * 2
    # Now every DNSE-exact ticker, not just the original small cohort, correctly distrusts DNSE.
    for ticker in all_exact:
        assert projected["records"][ticker]["multi_source_recovery_result"] == \
            "CORROBORATED_NON_DNSE_CURRENT_RESEARCH_SENTINEL_OVERRIDE"
    assert_self_consistent(projected)


def test_autorecovery_never_duplicates_a_source_ticker_fetch_when_gap_recovery_and_sentinel_overlap():
    """A DNSE-missing ticker already queried by Pass 3/4 gap recovery must never be re-queried by
    the degraded-expansion pass either, even though both resolver calls inside the wrapper run
    Pass 3/4 again internally over the identical DNSE-missing set. Sentinel cohort covers all 6
    DNSE-exact tickers (>= DNSE_BROAD_MIN_ASSESSED_COUNT) so 100% conflict is classified BROAD and
    the expansion pass genuinely runs a second resolver call."""
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
    # MISSING1 is DNSE-missing -- Pass 3/4 in BOTH resolver calls target it, but the shared
    # memoizing cache must still collapse that to exactly one real VCI attempt (KBS never reached
    # since VCI already succeeded).
    assert calls.count(("MISSING1", "VCI")) == 1
    assert calls.count(("MISSING1", "KBS")) == 0
    assert len(calls) == len(set(calls))  # no pair anywhere, from either pass or either call, twice


def test_autorecovery_pacing_delay_spent_once_per_genuine_fetch_not_per_call():
    """The shared memoizing cache must own pacing too, not just correctness: a cached (ticker,
    source) pair must never sleep again on the expansion's second resolver call, or a fully-
    degraded real-sized universe would burn its ENTIRE original Pass 3/4 pacing budget a second
    time for zero new network activity. Sentinel cohort already covers every DNSE-exact ticker,
    so the expansion pass's Pass 5 is 100% cache hits -- contributing zero additional sleeps."""
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
    # Exactly one real sleep per genuine (ticker, source) fetch: 6 tickers x 2 sources = 12 total
    # across the whole run, never doubled by the second resolver call re-processing the first
    # pass's own already-cached pairs.
    assert len(sleeps) == 6 * 2
    assert all(s == 1.1 for s in sleeps)


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
