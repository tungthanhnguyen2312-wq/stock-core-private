"""Same-session technical coverage dispositions over retained 2026-08-24 artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_wide_current_descriptive_research import (
    MarketWideCurrentDescriptiveResearchError,
    build_artifact,
)
from market_wide_current_technical_coverage_scaleout import recovery_candidates
from same_session_technical_coverage_disposition import (
    DISPOSITIONS,
    _classify_one,
    build,
    content_identity,
    official_research_universe,
)
from tests.test_market_wide_current_descriptive_research import (
    TARGET,
    _build_scenario,
    _observations,
    liquidity_artifact,
    p3f9b_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "operations-review"
PROTECTED_DESCRIPTIVE_ID = "market_wide_current_descriptive_research:ab08cf56fa4678b86296fc5c1f4cbaf108ec66b2e776d6d4070880bbc0b77ce1"
PROTECTED_TACTICAL_ID = "watchlist_tactical_entry_classifier:3fc4ed10d487a543887ddd66dc70cd8b5df4907654b302b25f604707e16f75f1"
PROTECTED_OFFICIAL_ID = "current_official_market_universe:d77e16f82893df419689b24356d066d6a6431bd3c27e09190e3c319e004abb55"
PROTECTED_SNAPSHOT_ID = "p3f9_exact_session_snapshot:8f1d762c5fb4d1cbdd9a26dc415b318aafefa630799c38fd74076ca166d8f25c"
PROTECTED_FREEZE_ID = "prospective_research_snapshot:d227f98bfc0f9d79ae20ae0d686d2eab8085ecb014da3bf48345de7db3c3daf1"


def _load(relative: str) -> dict:
    return json.loads((OPS / relative).read_text(encoding="utf-8"))


def _retained() -> dict:
    return build(
        descriptive=_load("market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json"),
        official_universe=_load("current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json"),
        p3f9b_snapshot=_load("p3f9b-market-wide-exact-session-scaleout-20260824/p3f9b_mva_exact_session_snapshot.json"),
        universe_status=_load("current-universe-status-and-session-coverage-resolution-v1-20260824/current_universe_status_and_session_coverage_resolution_artifact.json"),
        tactical=_load("watchlist-tactical-entry-decision-v1-20260824/watchlist_tactical_entry_classifier_artifact.json"),
        recovery=_load("market-wide-current-technical-coverage-scaleout-v1-20260824/market_wide_current_technical_coverage_recovery_artifact.json"),
    )


def test_retained_2026_08_24_candidate_universe_reconciles_with_zero_unexplained():
    artifact = _retained()
    counts = artifact["candidate_universe"]["disposition_counts"]
    assert artifact["candidate_universe"]["count"] == 1683
    assert sum(counts[name] for name in DISPOSITIONS) == 1683
    assert counts["SAME_SESSION_TECHNICAL_COVERED"] == 881
    assert counts["PROVIDER_REJECTED_OR_INVALID_SYMBOL"] == 173
    assert counts["OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE"] == 3
    assert counts["PROVIDER_SESSION_UNAVAILABLE"] == 626
    assert counts["RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING"] == 0
    assert counts["PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION"] == 0
    assert counts["MALFORMED_OR_CONFLICTED"] == 0
    assert counts["UNEXPLAINED"] == 0
    assert artifact["coverage_ceiling"]["unexplained"] == 0
    assert artifact["coverage_ceiling"]["history_recovery_applied_count"] == 132


def test_retained_2026_08_24_official_universe_reconciles():
    artifact = _retained()
    official = artifact["official_research_universe"]
    assert official["count"] == 1507
    assert official["same_session_technical_covered"] == 881
    assert official["missing_same_session_technical"] == 626
    assert official["disposition_counts"]["PROVIDER_REJECTED_OR_INVALID_SYMBOL"] == 0
    assert official["disposition_counts"]["OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE"] == 0
    assert official["disposition_counts"]["PROVIDER_SESSION_UNAVAILABLE"] == 626
    assert official["disposition_counts"]["SAME_SESSION_TECHNICAL_COVERED"] == 881
    assert sum(official["disposition_counts"].values()) == 1507


def test_stale_prior_session_features_are_unavailable_not_same_session_coverage():
    artifact = _retained()
    stale = [
        row for row in artifact["records"].values()
        if row["reason_code"] == "STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION"
    ]
    assert len(stale) == 43
    assert all(row["disposition"] == "PROVIDER_SESSION_UNAVAILABLE" for row in stale)
    assert all(row["is_current_session"] is False for row in stale)
    assert all(row["feature_as_of_session"] != "2026-08-24" for row in stale)
    assert all(row["has_exact_session_bar"] is False for row in stale)


def test_identity_drift_names_are_outside_official_universe():
    artifact = _retained()
    assert {artifact["records"][ticker]["disposition"] for ticker in ("BCG", "BCR", "VTS")} == {"OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE"}
    assert official_research_universe(_load("current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json")).isdisjoint({"BCG", "BCR", "VTS"})


def test_recovery_candidates_never_include_session_missing_names():
    descriptive = _load("market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json")
    snapshot = _load("p3f9b-market-wide-exact-session-scaleout-20260824/p3f9b_mva_exact_session_snapshot.json")
    # Reconstruct a pre-recovery baseline shape: recovery_candidates needs MISSING + EXACT_SESSION.
    baseline_records = {
        ticker: {
            "in_current_descriptive_scope": record["in_current_descriptive_scope"],
            "technical_features": {"status": "MISSING"} if snapshot["records"][ticker]["disposition"] == "EXACT_SESSION_RETAINED" else record["technical_features"],
        }
        for ticker, record in descriptive["records"].items()
    }
    from market_wide_current_technical_coverage_scaleout import content_identity as recovery_identity
    baseline = {"records": baseline_records}
    baseline.update(recovery_identity(baseline))
    selected = set(recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=snapshot))
    missing = {ticker for ticker, record in snapshot["records"].items() if record.get("disposition") == "SESSION_MISSING"}
    assert selected.isdisjoint(missing)


def test_exact_session_incomplete_history_without_recovery_fails_closed():
    ur, pf, liq, classifications = _build_scenario()
    pf_records = dict(pf["records"])
    pf_records["DEC1"] = {"disposition": "EXACT_SESSION_RETAINED", "observations": _observations(TARGET, 7, start_close=100.0, step=-1.0)}
    pf = p3f9b_snapshot(pf_records)
    liq = liquidity_artifact(liq["records"], snapshot_identity=pf["snapshot_identity"])
    with pytest.raises(MarketWideCurrentDescriptiveResearchError, match="RECOVERABLE_SAME_SESSION_TECHNICAL_HISTORY_GAP"):
        build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq, entity_classifications=classifications)


def test_stale_features_still_do_not_satisfy_same_session_eligibility_in_descriptive_build():
    ur, pf, liq, classifications = _build_scenario()
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq, entity_classifications=classifications)
    assert artifact["records"]["STALE1"]["technical_features"]["is_current_session"] is False
    assert artifact["market_breadth"]["same_session_technical_feature_available_count"] == 6
    assert artifact["records"]["STALE1"]["ticker"] not in {
        ticker for ticker, record in artifact["records"].items()
        if record["technical_features"].get("status") == "SHADOW_ONLY" and record["technical_features"].get("is_current_session") is True
    }


def test_disposition_identity_is_deterministic_and_governed_inputs_are_unchanged():
    first, second = _retained(), _retained()
    assert first["artifact_identity"] == second["artifact_identity"]
    assert content_identity(first)["artifact_sha256"] == first["artifact_sha256"]
    descriptive = _load("market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json")
    tactical = _load("watchlist-tactical-entry-decision-v1-20260824/watchlist_tactical_entry_classifier_artifact.json")
    official = _load("current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json")
    snapshot = _load("p3f9b-market-wide-exact-session-scaleout-20260824/p3f9b_mva_exact_session_snapshot.json")
    freeze = json.loads((OPS / "current-decision-prospective-learning-v1-20260824/current_decision_prospective_snapshot_20260821.json").read_text(encoding="utf-8"))
    assert descriptive["artifact_identity"] == PROTECTED_DESCRIPTIVE_ID
    assert tactical["artifact_identity"] == PROTECTED_TACTICAL_ID
    assert official["artifact_identity"] == PROTECTED_OFFICIAL_ID
    assert snapshot["snapshot_identity"] == PROTECTED_SNAPSHOT_ID
    assert freeze["snapshot_id"] == PROTECTED_FREEZE_ID
    committed = OPS / "same-session-technical-coverage-recovery-v1-20260824/same_session_technical_coverage_disposition_artifact.json"
    assert json.loads(committed.read_text(encoding="utf-8"))["artifact_identity"] == first["artifact_identity"]


# =====================================================================================
# 2026-09-21 SAME_SESSION_TECHNICAL_COVERAGE_DISPOSITION_20260921_CORRECTIVE_V1: real
# retained evidence for 2026-09-21 had 8 TRANSPORT_FAILED tickers (rate-limited/connection
# failure, retried once, still unsuccessful) that no existing rule covered, so they fell
# through to the UNEXPLAINED fail-closed sentinel. TRANSPORT_FAILED and MALFORMED are now
# classified explicitly; UNEXPLAINED itself is untouched and must still fail closed for any
# genuinely unmodeled disposition.
# =====================================================================================

_MINIMAL_DESCRIPTIVE_NOT_APPLICABLE = {
    "technical_features": {"status": "NOT_APPLICABLE", "is_current_session": False},
    "activity_and_session_state": "UNKNOWN",
}
_MINIMAL_OFFICIAL = {"qualification": "FIRST_PARTY_CURRENT_HOSE_STOCK_MASTER_ROW"}


def test_transport_failed_is_provider_session_unavailable_not_invalid_symbol():
    row = _classify_one(
        ticker="ZZT",
        descriptive=_MINIMAL_DESCRIPTIVE_NOT_APPLICABLE,
        snapshot={"disposition": "TRANSPORT_FAILED", "status": "FETCH_FAILED", "reason": "request_failed_ConnectTimeout"},
        status={},
        official=_MINIMAL_OFFICIAL,
        target_session="2026-09-21",
        official_tickers={"ZZT"},
    )
    assert row["disposition"] == "PROVIDER_SESSION_UNAVAILABLE"
    assert row["disposition"] != "PROVIDER_REJECTED_OR_INVALID_SYMBOL"
    assert row["reason_code"] == "PROVIDER_TRANSPORT_FAILURE_NO_QUALIFIED_OBSERVATION"


def test_malformed_response_is_malformed_or_conflicted_with_precise_reason():
    row = _classify_one(
        ticker="ZZM",
        descriptive=_MINIMAL_DESCRIPTIVE_NOT_APPLICABLE,
        snapshot={"disposition": "MALFORMED", "status": "MALFORMED_RESPONSE", "reason": "BODY_NOT_OBJECT"},
        status={},
        official=_MINIMAL_OFFICIAL,
        target_session="2026-09-21",
        official_tickers={"ZZM"},
    )
    assert row["disposition"] == "MALFORMED_OR_CONFLICTED"
    assert row["reason_code"] == "PROVIDER_RESPONSE_MALFORMED"


def test_exact_session_current_session_conflict_still_malformed_or_conflicted():
    row = _classify_one(
        ticker="ZZC",
        descriptive={
            "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True},
            "activity_and_session_state": "ACTIVE_LISTED",
        },
        snapshot={"disposition": "SESSION_MISSING", "status": "EXACT_SESSION_MISSING", "reason": "EXACT_SESSION_MISSING", "observations": []},
        status={},
        official=_MINIMAL_OFFICIAL,
        target_session="2026-09-21",
        official_tickers={"ZZC"},
    )
    assert row["disposition"] == "MALFORMED_OR_CONFLICTED"
    assert row["reason_code"] == "CONFLICTING_SAME_SESSION_AND_SOURCE_STATE"


def test_session_missing_classification_unchanged():
    row = _classify_one(
        ticker="ZZS",
        descriptive={"technical_features": {"status": "MISSING"}, "activity_and_session_state": "UNKNOWN"},
        snapshot={"disposition": "SESSION_MISSING", "status": "EXACT_SESSION_MISSING", "reason": "EXACT_SESSION_MISSING", "observations": []},
        status={"nearby_observation_count_in_retained_window": 0},
        official=_MINIMAL_OFFICIAL,
        target_session="2026-09-21",
        official_tickers={"ZZS"},
    )
    assert row["disposition"] == "PROVIDER_SESSION_UNAVAILABLE"
    assert row["reason_code"] == "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"


def test_provider_rejected_classification_unchanged():
    row = _classify_one(
        ticker="ZZR",
        descriptive={"technical_features": {}, "activity_and_session_state": "UNKNOWN"},
        snapshot={"disposition": "PROVIDER_REJECTED", "status": "FETCH_FAILED", "reason": "invalid_symbol"},
        status={},
        official=_MINIMAL_OFFICIAL,
        target_session="2026-09-21",
        official_tickers={"ZZR"},
    )
    assert row["disposition"] == "PROVIDER_REJECTED_OR_INVALID_SYMBOL"


def test_outside_official_universe_classification_unchanged():
    row = _classify_one(
        ticker="ZZO",
        descriptive={"technical_features": {}, "activity_and_session_state": "UNKNOWN"},
        snapshot={"disposition": "SESSION_MISSING", "status": "EXACT_SESSION_MISSING", "reason": "EXACT_SESSION_MISSING", "observations": []},
        status={},
        official=None,
        target_session="2026-09-21",
        official_tickers=set(),
    )
    assert row["disposition"] == "OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE"


def test_unknown_future_disposition_still_falls_to_unexplained():
    row = _classify_one(
        ticker="ZZU",
        descriptive=_MINIMAL_DESCRIPTIVE_NOT_APPLICABLE,
        snapshot={"disposition": "SOME_BRAND_NEW_DISPOSITION_NOT_YET_MODELED", "status": "UNKNOWN"},
        status={},
        official=_MINIMAL_OFFICIAL,
        target_session="2026-09-21",
        official_tickers={"ZZU"},
    )
    assert row["disposition"] == "UNEXPLAINED"
    assert row["reason_code"] == "NO_MUTUALLY_EXCLUSIVE_RULE_MATCHED"


def test_build_still_fails_closed_for_a_genuinely_unmodeled_disposition():
    # Fully synthetic, single-ticker scenario (independent of any real retained fixture) whose
    # snapshot disposition matches no rule at all -- build() must still refuse, not silently drop
    # the fail-closed sentinel just because two new dispositions are now explicitly modeled.
    session = "2026-09-21"
    descriptive = {
        "session": session,
        "records": {
            "ZZFAIL": {
                "technical_features": {"status": "NOT_APPLICABLE", "is_current_session": False},
                "activity_and_session_state": "UNKNOWN",
            },
        },
    }
    official_universe = {
        "records": {
            "ZZFAIL": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY"},
        },
    }
    snapshot = {
        "resolved_completed_session": session,
        "records": {
            "ZZFAIL": {"disposition": "SOME_BRAND_NEW_DISPOSITION_NOT_YET_MODELED", "status": "UNKNOWN", "observations": []},
        },
    }
    universe_status = {
        "input_candidates": {"resolved_completed_session": session},
        "records": {"ZZFAIL": {}},
    }
    tactical = {"coverage": {"classified_count": 0}}
    recovery = {"recovered_history_overrides": {}}
    with pytest.raises(ValueError, match="UNEXPLAINED_COVERAGE_DISPOSITION:1"):
        build(
            descriptive=descriptive, official_universe=official_universe, p3f9b_snapshot=snapshot,
            universe_status=universe_status, tactical=tactical, recovery=recovery,
        )


def _retained_20260921() -> dict:
    return build(
        descriptive=_load("market-wide-current-descriptive-research-v1-20260921/market_wide_current_descriptive_research_artifact.json"),
        official_universe=_load("current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json"),
        p3f9b_snapshot=_load("p3f9b-market-wide-exact-session-scaleout-20260921/p3f9b_mva_exact_session_snapshot.json"),
        universe_status=_load("current-universe-status-and-session-coverage-resolution-v1-20260921/current_universe_status_and_session_coverage_resolution_artifact.json"),
        tactical=_load("watchlist-tactical-entry-decision-v1-20260921/watchlist_tactical_entry_classifier_artifact.json"),
        recovery=_load("market-wide-current-technical-coverage-scaleout-v1-20260921/market_wide_current_technical_coverage_recovery_artifact.json"),
    )


_REAL_20260921_TRANSPORT_FAILED_TICKERS = ("PSW", "PTE", "PTG", "PTH", "PTI", "PTL", "PTM", "PTS")


def test_real_2026_09_21_candidate_universe_reconciles_with_zero_unexplained():
    artifact = _retained_20260921()
    counts = artifact["candidate_universe"]["disposition_counts"]
    assert artifact["candidate_universe"]["count"] == 1683
    assert sum(counts[name] for name in DISPOSITIONS) == 1683
    assert counts["UNEXPLAINED"] == 0
    assert artifact["coverage_ceiling"]["unexplained"] == 0
    assert counts["SAME_SESSION_TECHNICAL_COVERED"] == 838
    assert counts["PROVIDER_SESSION_UNAVAILABLE"] == 664
    assert counts["PROVIDER_REJECTED_OR_INVALID_SYMBOL"] == 179
    assert counts["OUTSIDE_OFFICIAL_RESEARCH_UNIVERSE"] == 1
    assert counts["PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION"] == 1
    assert counts["MALFORMED_OR_CONFLICTED"] == 0


def test_real_2026_09_21_all_eight_transport_failed_tickers_classify_deterministically():
    artifact = _retained_20260921()
    for ticker in _REAL_20260921_TRANSPORT_FAILED_TICKERS:
        row = artifact["records"][ticker]
        assert row["snapshot_disposition"] == "TRANSPORT_FAILED"
        assert row["disposition"] == "PROVIDER_SESSION_UNAVAILABLE"
        assert row["reason_code"] == "PROVIDER_TRANSPORT_FAILURE_NO_QUALIFIED_OBSERVATION"
    reasons = artifact["candidate_universe"]["reason_counts"]
    assert reasons["PROVIDER_TRANSPORT_FAILURE_NO_QUALIFIED_OBSERVATION"] == len(_REAL_20260921_TRANSPORT_FAILED_TICKERS)


def test_real_2026_09_21_tactical_classified_count_coherent():
    artifact = _retained_20260921()
    tactical = _load("watchlist-tactical-entry-decision-v1-20260921/watchlist_tactical_entry_classifier_artifact.json")
    covered = artifact["candidate_universe"]["disposition_counts"]["SAME_SESSION_TECHNICAL_COVERED"]
    assert tactical["coverage"]["classified_count"] == covered


def test_real_2026_09_21_disposition_identity_is_deterministic():
    first, second = _retained_20260921(), _retained_20260921()
    assert first["artifact_identity"] == second["artifact_identity"]
    assert content_identity(first)["artifact_sha256"] == first["artifact_sha256"]
    assert first["session"] == "2026-09-21"
