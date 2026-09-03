import pandas as pd
import pytest

from field_temporal_contract import stable_id
from multi_source_exact_session_resolver import (
    DnseProviderWideQualityDegraded,
    MultiSourceResolverError,
    assert_dnse_quality_acceptable,
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
