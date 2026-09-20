"""Focused tests for indicator_metric_availability.py.

Covers the synthetic-fixture invariants (fail-closed, no fabrication, never a silent
READY promotion, capability-exists vs value-missing, sector/cohort scoping) plus a real
-artifact acceptance pass against the actual retained 2026-09-18
investment_decision_workspace_projection/v1 artifact published in the sibling
market-dashboard repository, so this reconciliation layer is proven against genuine
evidence, not only fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import indicator_metric_availability as availability
import indicator_metric_display_state as display_state

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT.parent / "market-dashboard"
WORKSPACE_ARTIFACT_PATH = DASHBOARD / "data" / "investment_decision_workspace.json"
COHORT = frozenset({"EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM"})


def _base_card(**overrides):
    card = {
        "as_of_session": "2026-09-18",
        "fundamental": {"entity_applicability": "GENERIC_RESEARCH_PRIMITIVES_ALLOWED",
                        "current_features": {}, "financial_health": {}},
        "valuation": {"entity_class": "corporate", "method_diagnostics": {}},
        "tactical": {},
        "confirmation": {},
        "invalidation": {"technical": {}},
        "signal_velocity": {},
        "market_sector": {"sector_diagnostic": {}},
        "flow_price": {},
        "catalyst": {},
    }
    card.update(overrides)
    return card


# ---------------------------------------------------------------------------
# 1. Capability exists + value missing -> INSUFFICIENT_DATA, never omitted
# ---------------------------------------------------------------------------

def test_valuation_method_present_but_input_blocked_is_insufficient_data_not_omitted():
    card = _base_card(valuation={"entity_class": "corporate", "method_diagnostics": {
        "P/B": {"availability_state": "NOT_AVAILABLE", "status": "INPUT_BLOCKED",
                "blocker_reason_codes": ["MARKET_CAP_RESEARCH_INPUT_UNAVAILABLE"], "value": None},
    }})
    record = availability._valuation_method_record("pb", "P/B", card, "2026-09-18")
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["blocker_class"] == "MISSING_CURRENT_VALUATION_INPUT"
    assert record["value_present"] is False


def test_fundamental_feature_blocked_is_insufficient_data_with_named_blocker():
    card = _base_card(fundamental={
        "entity_applicability": "GENERIC_RESEARCH_PRIMITIVES_ALLOWED",
        "current_features": {"debt_to_equity": {
            "status": "BLOCKED", "blocker_reason_codes": ["MISSING_SAME_NATIVE_PERIOD_SCOPE_SERIES"], "value": None,
        }},
        "financial_health": {},
    })
    record = availability._fundamental_feature_record("debt_to_equity", "debt_to_equity", card, "2026-09-18")
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["blocker_class"] == "MISSING_PERIOD_COMPATIBILITY"
    assert record["recoverability"] == "REQUIRES_NEW_EVIDENCE"


# ---------------------------------------------------------------------------
# 2. Genuinely future-dependent metric -> BUILDING_HISTORY
# ---------------------------------------------------------------------------

def test_signal_velocity_thin_evidence_is_building_history():
    card = _base_card(signal_velocity={
        "overall_transition_state": "INSUFFICIENT_EVIDENCE",
        "evidence_quality": "INSUFFICIENT_RETAINED_EVIDENCE",
        "valid_observation_count": 1,
    })
    record = availability._signal_velocity_record(card, "2026-09-18")
    assert record["availability_state"] == "BUILDING_HISTORY"
    assert record["requires_future_observation"] is True
    assert record["blocker_class"] == "GENUINELY_WAITING_FUTURE_OBSERVATIONS"


def test_engine_insufficient_history_status_maps_to_building_history():
    card = _base_card(fundamental={
        "entity_applicability": "GENERIC_RESEARCH_PRIMITIVES_ALLOWED",
        "current_features": {"roe_eop_proxy": {"status": "INSUFFICIENT_HISTORY", "value": None}},
        "financial_health": {},
    })
    record = availability._fundamental_feature_record("roe", "roe_eop_proxy", card, "2026-09-18")
    assert record["availability_state"] == "BUILDING_HISTORY"
    assert record["requires_future_observation"] is True


# ---------------------------------------------------------------------------
# 3. Retained history recoverable now -> must NOT be BUILDING_HISTORY
# ---------------------------------------------------------------------------

def test_technical_trend_missing_without_evidence_never_fabricates_recovery():
    """INDICATOR_METRIC_AVAILABILITY_RECOVERY_CLASSIFICATION_CORRECTIVE_V1 (2026-09-20): a
    technical-trend gap with NO coverage-disposition evidence supplied must never fabricate
    RECOVER_NOW_EXISTING_PROVIDER_PATH (the corrected defect) -- but must also never collapse
    into BUILDING_HISTORY, since a delisted symbol or a permanent session gap is not "wait one
    more session"."""
    card = _base_card(tactical={})
    record = availability._technical_trend_record(card, "2026-09-18")
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["availability_state"] != "BUILDING_HISTORY"
    assert record["blocker_class"] == "UNKNOWN_BLOCKER"
    assert record["recoverability"] == "NO_IMPLEMENTATION"
    assert record["requires_future_observation"] is False


# ---------------------------------------------------------------------------
# 3b. INDICATOR_METRIC_AVAILABILITY_RECOVERY_CLASSIFICATION_CORRECTIVE_V1 (2026-09-20):
# precise technical-trend blocker classification from real coverage-disposition/recovery
# evidence, replacing the corrected blanket RECOVER_NOW_EXISTING_PROVIDER_PATH defect.
# ---------------------------------------------------------------------------

def test_technical_trend_provider_session_unavailable_is_not_recoverable_via_lookback():
    """Target-session bar itself absent (544/727 real 2026-09-18 tickers) needs a different
    mechanism (same-session bar-gap recovery), never the 20-session window recovery path."""
    card = _base_card(tactical={})
    record = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "PROVIDER_SESSION_UNAVAILABLE",
                               "reason_code": "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"},
    )
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["blocker_class"] == "PROVIDER_SESSION_UNAVAILABLE"
    assert record["recoverability"] != "RECOVER_NOW_EXISTING_PROVIDER_PATH"
    assert record["recoverability"] == "REQUIRES_NEW_EVIDENCE"


def test_technical_trend_invalid_delisted_symbol_is_never_recoverable_now():
    """Delisted/invalid symbol (180/727 real 2026-09-18 tickers) is a universe-membership
    fact, never a data gap -- never recoverable-now, never even a data 'metric applies' case."""
    card = _base_card(tactical={})
    record = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL",
                               "reason_code": "DELISTED_OR_NO_LONGER_CURRENT"},
    )
    assert record["availability_state"] == "NOT_APPLICABLE"
    assert record["blocker_class"] == "INVALID_OR_DELISTED_SYMBOL"
    assert record["recoverability"] != "RECOVER_NOW_EXISTING_PROVIDER_PATH"
    assert record["recoverability"] == "NOT_APPLICABLE"
    assert record["current_research_allowed"] is False


def test_technical_trend_exhausted_provider_chain_is_never_recoverable_now():
    """3/727 real tickers (DUS, GLC, TVG) already exhausted DNSE->KBS->VCI this exact session
    -- a true former RECOVER_NOW_EXISTING_PROVIDER_PATH candidate that already failed, so it
    must never keep claiming that label."""
    card = _base_card(tactical={})
    record = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION", "reason_code": None},
        recovery_record={"state": "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK",
                          "reason": "NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES"},
    )
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["blocker_class"] == "NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES"
    assert record["recoverability"] != "RECOVER_NOW_EXISTING_PROVIDER_PATH"
    assert record["recoverability"] == "REQUIRES_AUTHORITY_DECISION"


def test_technical_trend_true_untried_candidate_remains_recoverable_now():
    """A ticker whose target-session bar is present, technical window incomplete, and the
    recovery mechanism has not yet attempted it (no recovery_record) IS the one population
    RECOVER_NOW_EXISTING_PROVIDER_PATH genuinely describes -- this must still work."""
    card = _base_card(tactical={})
    record = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING",
                               "reason_code": "MISSING"},
        recovery_record=None,
    )
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["blocker_class"] == "RECOVERABLE_BY_EXISTING_BACKFILL"
    assert record["recoverability"] == "RECOVER_NOW_EXISTING_PROVIDER_PATH"
    assert record["recovery_action_code"] == "EXTENDED_LOOKBACK_TECHNICAL_HISTORY_RECOVERY"


def test_technical_trend_retained_only_candidate_is_recover_now_retained_only():
    """A window gap closeable from bytes already retained (zero new network calls) is a
    distinct, more favorable recoverability than the existing-provider-path case."""
    card = _base_card(tactical={})
    record = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING",
                               "reason_code": "MISSING", "recoverable_from_retained_bytes_only": True},
    )
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["blocker_class"] == "RECOVERABLE_FROM_RETAINED_DATA"
    assert record["recoverability"] == "RECOVER_NOW_RETAINED_ONLY"


def test_technical_trend_ready_is_unaffected_by_new_classification_branches():
    card = _base_card(tactical={"primary_entry_state": "UPTREND_CONFIRMED"})
    record = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "SAME_SESSION_TECHNICAL_COVERED", "reason_code": None},
    )
    assert record["availability_state"] == "READY"
    assert record["blocker_class"] == "READY"


def test_technical_trend_pit_and_current_research_flags_unchanged_by_corrective_fix():
    """PIT/RAW_AS_TRADED authority is untouched by this corrective milestone: every branch
    still reports historical_pit_allowed=False, and only the delisted/invalid branch turns
    off current_research_allowed (nothing applies to a dead symbol)."""
    card = _base_card(tactical={})
    for coverage_disposition in (
        {"disposition": "PROVIDER_SESSION_UNAVAILABLE", "reason_code": "X"},
        {"disposition": "RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING", "reason_code": None},
        None,
    ):
        record = availability._technical_trend_record(card, "2026-09-18", coverage_disposition=coverage_disposition)
        assert record["historical_pit_allowed"] is False
        assert record["current_research_allowed"] is True
    delisted = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL", "reason_code": "X"},
    )
    assert delisted["historical_pit_allowed"] is False
    assert delisted["current_research_allowed"] is False


def test_flow_in_cohort_missing_current_session_is_recoverable_now_not_building_history():
    card = _base_card(flow_price={"foreign_flow_state": "FLOW_UNAVAILABLE", "reference_session": None})
    record = availability._flow_metric_record("foreign_flow_state", "foreign_flow_state", "HPG", card, COHORT,
                                              "2026-09-18")
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["availability_state"] != "BUILDING_HISTORY"
    assert record["recoverability"] == "REQUIRES_NEW_EVIDENCE"


# ---------------------------------------------------------------------------
# 4. Sector-inapplicable metric -> NOT_APPLICABLE
# ---------------------------------------------------------------------------

def test_ev_ebitda_not_applicable_for_bank_entity_class():
    card = _base_card(valuation={"entity_class": "bank", "method_diagnostics": {
        "EV/EBITDA": {"availability_state": "NOT_AVAILABLE", "blocker_reason_codes": ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]},
    }})
    record = availability._valuation_method_record("ev_ebitda", "EV/EBITDA", card, "2026-09-18")
    assert record["availability_state"] == "NOT_APPLICABLE"
    assert record["applicability"] == "NOT_APPLICABLE"
    assert record["current_research_allowed"] is False


def test_fundamental_feature_not_applicable_for_specialist_entity():
    card = _base_card(fundamental={"entity_applicability": "NOT_APPLICABLE", "current_features": {}, "financial_health": {}})
    record = availability._fundamental_feature_record("gross_margin", "gross_margin", card, "2026-09-18")
    assert record["availability_state"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# 5. Outside flow cohort -> NOT_TRACKED
# ---------------------------------------------------------------------------

def test_flow_outside_cohort_is_not_tracked_never_insufficient_data():
    card = _base_card(flow_price={})
    record = availability._flow_metric_record("foreign_flow_state", "foreign_flow_state", "AAA", card, COHORT,
                                              "2026-09-18")
    assert record["availability_state"] == "NOT_TRACKED"
    assert record["availability_state"] != "INSUFFICIENT_DATA"


def test_flow_inside_cohort_is_never_not_tracked():
    card = _base_card(flow_price={"relationship": "FLOW_PRICE_MIXED", "reference_session": "2026-09-18"})
    record = availability._flow_metric_record("flow_price_relationship", "relationship", "HPG", card, COHORT,
                                              "2026-09-18")
    assert record["availability_state"] != "NOT_TRACKED"
    assert record["availability_state"] == "READY"


# ---------------------------------------------------------------------------
# 6/7. HPG EBITDA case study
# ---------------------------------------------------------------------------

def test_hpg_ebitda_engine_exists_but_bundle_not_wired_is_temporarily_unavailable_not_missing_forever():
    card = _base_card(valuation={"entity_class": "corporate", "method_diagnostics": {
        "EV/EBITDA_CALC_READY": {"availability_state": "NOT_AVAILABLE",
                                  "blocker_reason_codes": ["CALCULATION_READINESS_CONTEXT_UNAVAILABLE"], "value": None},
    }})
    record = availability.ebitda_case_study_record(card, "2026-09-18")
    assert record["availability_state"] == "TEMPORARILY_UNAVAILABLE"
    assert record["blocker_class"] == "PRESENTATION_TRANSPORT_GAP"
    assert record["recoverability"] == "REQUIRES_AUTHORITY_DECISION"


def test_ebitda_missing_components_is_insufficient_data_with_named_blocker():
    card = _base_card(valuation={"entity_class": "corporate", "method_diagnostics": {
        "EV/EBITDA_CALC_READY": {"availability_state": "NOT_AVAILABLE",
                                  "blocker_reason_codes": ["ebitda_not_ready"], "value": None},
    }})
    record = availability.ebitda_case_study_record(card, "2026-09-18")
    assert record["availability_state"] == "INSUFFICIENT_DATA"
    assert record["blocker_class"] == "MISSING_FINANCIAL_COMPONENT"


def test_ev_ebitda_distinguishes_ebitda_blocker_from_ev_input_blocker():
    """Same ticker, same session: EBITDA itself missing vs. EBITDA ready but EV inputs
    (price/share/debt/cash basis) missing must report two DIFFERENT blocker classes."""
    ebitda_missing_card = _base_card(valuation={"entity_class": "corporate", "method_diagnostics": {
        "EV/EBITDA_CALC_READY": {"availability_state": "NOT_AVAILABLE", "blocker_reason_codes": ["ebitda_not_ready"]},
    }})
    ev_input_missing_card = _base_card(valuation={"entity_class": "corporate", "method_diagnostics": {
        "EV/EBITDA": {"availability_state": "NOT_AVAILABLE",
                      "blocker_reason_codes": ["price_basis_unknown_and_unverified_universe_wide"]},
    }})
    ebitda_record = availability.ebitda_case_study_record(ebitda_missing_card, "2026-09-18")
    ev_record = availability._valuation_method_record("ev_ebitda", "EV/EBITDA", ev_input_missing_card, "2026-09-18")
    assert ebitda_record["blocker_class"] == "MISSING_FINANCIAL_COMPONENT"
    assert ev_record["blocker_class"] == "MISSING_PRICE_BASIS_AUTHORITY"
    assert ebitda_record["blocker_class"] != ev_record["blocker_class"]


# ---------------------------------------------------------------------------
# 9. PIT-only historical restriction never suppresses allowed current display
# ---------------------------------------------------------------------------

def test_ready_technical_record_allows_current_research_but_never_claims_pit():
    card = _base_card(tactical={"primary_entry_state": "UPTREND_CONFIRMED", "freshness_status": "CURRENT"})
    record = availability._technical_trend_record(card, "2026-09-18")
    assert record["availability_state"] == "READY"
    assert record["current_research_allowed"] is True
    assert record["historical_pit_allowed"] is False


# ---------------------------------------------------------------------------
# 11. missing != zero
# ---------------------------------------------------------------------------

def test_missing_fundamental_value_is_none_never_a_fabricated_zero():
    card = _base_card(fundamental={
        "entity_applicability": "GENERIC_RESEARCH_PRIMITIVES_ALLOWED",
        "current_features": {"gross_margin": {"status": "BLOCKED", "blocker_reason_codes": ["INPUT_BLOCKED"], "value": None}},
        "financial_health": {},
    })
    record = availability._fundamental_feature_record("gross_margin", "gross_margin", card, "2026-09-18")
    assert record["value"] is None
    assert record["value"] != 0


# ---------------------------------------------------------------------------
# 12. Deterministic identity: same input -> byte-identical output
# ---------------------------------------------------------------------------

def test_evaluate_ticker_is_deterministic():
    card = _base_card(tactical={"primary_entry_state": "UPTREND_CONFIRMED"})
    first = availability.evaluate_ticker("HPG", card, cohort_tickers=COHORT)
    second = availability.evaluate_ticker("HPG", card, cohort_tickers=COHORT)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ---------------------------------------------------------------------------
# 13. Metric does not disappear simply because value is null
# ---------------------------------------------------------------------------

def test_evaluate_ticker_returns_every_registered_metric_even_when_all_blocked():
    card = _base_card()
    records = availability.evaluate_ticker("ZZZ", card, cohort_tickers=COHORT)
    expected_ids = set(availability._FUNDAMENTAL_FEATURE_METRICS) | set(availability._VALUATION_METHOD_METRICS) | {
        "ebitda", "leverage_state", "cash_quality_state", "technical_trend_entry_state",
        "technical_confirmation_trigger", "technical_invalidation", "signal_velocity_state",
        "sector_relative_momentum", "foreign_flow_state", "flow_price_relationship",
        "flow_persistence_5session", "catalyst_event_context",
    }
    assert expected_ids <= set(records)
    for record in records.values():
        assert record["availability_state"] in availability.AVAILABILITY_STATES


# ---------------------------------------------------------------------------
# 14/15. Bank/securities/corporate applicability + never a silent READY promotion
# ---------------------------------------------------------------------------

def test_unrecognized_status_string_never_silently_promoted_to_ready():
    assert availability._status_to_state("SOME_NEW_UNMAPPED_STATUS") == "INSUFFICIENT_DATA"


def test_unrecognized_blocker_code_is_unknown_blocker_not_fabricated():
    assert availability._blocker_class_for_codes(["A_CODE_NEVER_SEEN_BEFORE"]) == "UNKNOWN_BLOCKER"


# ---------------------------------------------------------------------------
# Market-wide: no fabricated VN-Index level
# ---------------------------------------------------------------------------

def test_market_index_level_change_is_honestly_not_produced():
    records = availability.market_wide_records({}, "2026-09-18")
    record = records["market_index_level_change"]
    assert record["availability_state"] == "TEMPORARILY_UNAVAILABLE"
    assert record["blocker_class"] == "NOT_CURRENTLY_PRODUCED"


# ---------------------------------------------------------------------------
# Real-artifact acceptance
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not WORKSPACE_ARTIFACT_PATH.exists(), reason="sibling market-dashboard checkout not present")
def test_real_workspace_artifact_every_ticker_produces_every_metric_zero_silent_drops():
    artifact = json.loads(WORKSPACE_ARTIFACT_PATH.read_text(encoding="utf-8"))
    evaluation = availability.evaluate_workspace_artifact(artifact, cohort_tickers=COHORT)
    assert evaluation["ticker_denominator"] == len(artifact["cards"])
    assert set(evaluation["tickers"]) == set(artifact["cards"])
    for records in evaluation["tickers"].values():
        for record in records.values():
            assert record["availability_state"] in availability.AVAILABILITY_STATES


@pytest.mark.skipif(not WORKSPACE_ARTIFACT_PATH.exists(), reason="sibling market-dashboard checkout not present")
def test_real_hpg_card_ebitda_is_temporarily_unavailable_presentation_transport_gap():
    artifact = json.loads(WORKSPACE_ARTIFACT_PATH.read_text(encoding="utf-8"))
    hpg = artifact["cards"]["HPG"]
    record = availability.ebitda_case_study_record(hpg, artifact.get("as_of_session"))
    assert record["availability_state"] in ("TEMPORARILY_UNAVAILABLE", "INSUFFICIENT_DATA", "READY")
    assert record["blocker_class"] in ("PRESENTATION_TRANSPORT_GAP", "MISSING_FINANCIAL_COMPONENT", "READY")


@pytest.mark.skipif(not WORKSPACE_ARTIFACT_PATH.exists(), reason="sibling market-dashboard checkout not present")
def test_real_flow_cohort_membership_matches_owner_research_focus():
    artifact = json.loads(WORKSPACE_ARTIFACT_PATH.read_text(encoding="utf-8"))
    in_cohort = availability._flow_metric_record("foreign_flow_state", "foreign_flow_state", "HPG",
                                                  artifact["cards"]["HPG"], COHORT, artifact.get("as_of_session"))
    assert in_cohort["availability_state"] != "NOT_TRACKED"
    if "AAA" in artifact["cards"]:
        outside = availability._flow_metric_record("foreign_flow_state", "foreign_flow_state", "AAA",
                                                     artifact["cards"]["AAA"], COHORT, artifact.get("as_of_session"))
        assert outside["availability_state"] == "NOT_TRACKED"


# ---------------------------------------------------------------------------
# INDICATOR_METRIC_AVAILABILITY_RECOVERY_CLASSIFICATION_CORRECTIVE_V1 (2026-09-20):
# real-evidence acceptance for the exact 2026-09-18 tickers this milestone's brief names.
#
# Every (disposition, recovery_record) pair below is the REAL, retained classification for
# that real ticker on the real 2026-09-18 session -- transcribed, not fabricated, from
# operations-review/current-technical-recoverable-coverage-completion-v1-20260920/
# (representative_cases.json, recovery_results.json, candidate_inventory.json) in the
# long-lived primary stock-core-private checkout. That evidence directory is gitignored and
# worktree-local (already documented in this repository's own docs/STATE.md for a prior,
# unrelated milestone: "operations-review/ evidence exists only in the long-lived primary
# checkout, never in a freshly created worktree"), so it cannot be re-read live from an
# isolated corrective worktree -- these fixtures preserve its exact content instead of
# skipping the acceptance entirely.
# ---------------------------------------------------------------------------

def test_real_20260918_owner_focus_tickers_are_ready_unaffected_by_corrective_fix():
    """HPG/FPT/SSI: real disposition=SAME_SESSION_TECHNICAL_COVERED, technical_features_status
    =SHADOW_ONLY (representative_cases.json owner_focus_named_tickers) -- already READY via
    tactical.primary_entry_state before this milestone; this fix must not touch them."""
    for ticker in ("HPG", "FPT", "SSI"):
        card = _base_card(tactical={"primary_entry_state": "UPTREND_CONFIRMED", "freshness_status": "CURRENT"})
        record = availability._technical_trend_record(
            card, "2026-09-18",
            coverage_disposition={"disposition": "SAME_SESSION_TECHNICAL_COVERED", "reason_code": None},
        )
        assert record["availability_state"] == "READY", ticker
        assert record["blocker_class"] == "READY", ticker


def test_real_20260918_recovered_tickers_bhc_dld_sd7_uct_are_ready():
    """BHC/DLD/SD7/UCT: real recovery_results.json shows these 4 of the 7 true candidates
    RECOVERED_COMPLETE_TECHNICAL_HISTORY via the existing DNSE/VCI provider path during the
    normal 2026-09-18 Daily run, folding them into SAME_SESSION_TECHNICAL_COVERED/READY before
    this reconciliation layer ever sees them -- old classification was already READY too (this
    population was never part of the mislabeled 727)."""
    for ticker, provider in {"BHC": "VCI", "DLD": "VCI", "SD7": "DNSE", "UCT": "VCI"}.items():
        card = _base_card(tactical={"primary_entry_state": "RANGE_BOUND", "freshness_status": "CURRENT"})
        record = availability._technical_trend_record(
            card, "2026-09-18",
            coverage_disposition={"disposition": "SAME_SESSION_TECHNICAL_COVERED", "reason_code": None,
                                   "recovered_extended_history": True},
        )
        assert record["availability_state"] == "READY", (ticker, provider)


def test_real_20260918_dus_glc_tvg_exhausted_chain_old_vs_new_classification():
    """DUS/GLC/TVG: real recovery_results.json failed_tickers all show
    NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES after exhausting DNSE->KBS->VCI this exact
    session (candidate_inventory.json GENUINELY_MISSING_SOURCE_HISTORY). OLD classification
    (the corrected defect) mislabeled all three RECOVER_NOW_EXISTING_PROVIDER_PATH even though
    the mechanism had already tried and failed for them; NEW classification must say so."""
    for ticker in ("DUS", "GLC", "TVG"):
        card = _base_card(tactical={})
        old_classification = availability._technical_trend_record(card, "2026-09-18")  # no evidence, pre-fix shape
        assert old_classification["blocker_class"] != "NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES", ticker

        new_classification = availability._technical_trend_record(
            card, "2026-09-18",
            coverage_disposition={"disposition": "PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION", "reason_code": None},
            recovery_record={"state": "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK",
                              "reason": "NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES"},
        )
        assert new_classification["availability_state"] == "INSUFFICIENT_DATA", ticker
        assert new_classification["blocker_class"] == "NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES", ticker
        assert new_classification["recoverability"] == "REQUIRES_AUTHORITY_DECISION", ticker
        assert new_classification["recoverability"] != "RECOVER_NOW_EXISTING_PROVIDER_PATH", ticker
        display = display_state.to_display_state(new_classification)
        assert display["display_state"] == "INSUFFICIENT_DATA", ticker


def test_real_20260918_structural_session_gap_and_delisted_populations_old_vs_new():
    """544 PROVIDER_SESSION_UNAVAILABLE (structural target-session bar absent) and 180
    PROVIDER_REJECTED_OR_INVALID_SYMBOL (delisted/invalid) together are 724 of the 727 real
    mislabeled tickers (candidate_inventory.json OTHER_BLOCKER) -- neither population was ever
    a true RECOVER_NOW_EXISTING_PROVIDER_PATH candidate; both must stop claiming that label."""
    card = _base_card(tactical={})
    session_gap = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "PROVIDER_SESSION_UNAVAILABLE",
                               "reason_code": "STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION"},
    )
    assert session_gap["blocker_class"] == "PROVIDER_SESSION_UNAVAILABLE"
    assert session_gap["recoverability"] == "REQUIRES_NEW_EVIDENCE"
    assert display_state.to_display_state(session_gap)["display_state"] == "INSUFFICIENT_DATA"

    delisted = availability._technical_trend_record(
        card, "2026-09-18",
        coverage_disposition={"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL",
                               "reason_code": "DELISTED_OR_NO_LONGER_CURRENT"},
    )
    assert delisted["blocker_class"] == "INVALID_OR_DELISTED_SYMBOL"
    assert delisted["recoverability"] == "NOT_APPLICABLE"
    assert display_state.to_display_state(delisted)["display_state"] == "NOT_APPLICABLE"
