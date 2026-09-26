"""Focused tests for investment_decision_workspace_projection.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from current_valuation_opportunity_integration import build_artifacts as build_opportunity_artifacts
from investment_decision_workspace_projection import (
    InvestmentDecisionWorkspaceError, RELATIVE_VALUATION_LABELS, content_identity,
)
import investment_decision_workspace_projection as _workspace_module
from _integrated_decision_fixture import integrated_decision as _integrated_decision, minimal_integrated_record

DECISION = "2026-08-28"


def build_artifacts(**kwargs):
    """CURRENT_DECISION_SURFACE_CONVERGENCE_V1: the Workspace now requires its action-decision
    authority. Pre-existing tests here exercise other card sections, so they receive a real,
    same-session, same-ticker-set Integrated Decision built by the production builder."""
    if "integrated_decision_artifact" not in kwargs:
        opportunity = kwargs.get("opportunity_artifact") or {}
        decision = kwargs.get("decision_artifact") or {}
        tickers = sorted(opportunity.get("records") or {})
        session = opportunity.get("as_of_session") or decision.get("as_of_session")
        kwargs["integrated_decision_artifact"] = _integrated_decision(session, tickers) if tickers and session else None
    return _workspace_module.build_artifacts(**kwargs)


def build_ticker_card(**kwargs):
    if "integrated_record" not in kwargs:
        kwargs["integrated_record"] = minimal_integrated_record(kwargs["ticker"], DECISION)
    return _workspace_module.build_ticker_card(**kwargs)


# ---------------------------------------------------------------------------
# Minimal fixture builders for the real upstream chain (opportunity_context +
# security_decision_context), trimmed from tests/test_current_valuation_opportunity_integration.py's
# proven-working versions -- this module's own tests build a real matched pair through the actual
# upstream module rather than hand-faking its output shape.
# ---------------------------------------------------------------------------

def _identity(kind: str) -> str:
    return f"{kind}:abc"


def _feature(status, value=None, state=None, periods=None):
    return {
        "feature_id": "x", "value": value, "categorical_state": state, "status": status,
        "method": "same_native_series_dimensionless_ratio/v1",
        "compatibility_class": "SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE",
        "input_periods": list(periods or []), "blocker_reason_codes": [],
    }


def feature_record(ticker, *, profit="PROFITABLE", ni=100.0, ttm_ni=400.0, ttm_rev=4000.0,
                    periods=("2025-Q4", "2026-Q1")):
    blocked = _feature("BLOCKED")
    features = {
        "net_income_ttm_sum": _feature("READY_RESEARCH_PROXY", ttm_ni, periods=periods) if ttm_ni is not None else blocked,
        "revenue_ttm_sum": _feature("READY_RESEARCH_PROXY", ttm_rev, periods=periods) if ttm_rev is not None else blocked,
        "profit_state": _feature("READY_RESEARCH_PROXY", ni, state=profit, periods=[periods[-1]]),
    }
    return {
        "ticker": ticker, "entity_type": "corporate", "entity_applicability": "GENERIC_RESEARCH_PRIMITIVES_ALLOWED",
        "fundamental_feature_context": {
            "availability": "PRODUCT_READY_RESEARCH_CONTEXT", "ready_feature_count": 3,
            "health_axes": {"PROFITABILITY_STATE": profit, "GROWTH_STATE": "INSUFFICIENT_DATA"},
            "current_features": features, "warnings_blockers": [],
        },
    }


def valuation_record(ticker, *, market_cap=8000.0, pe=10.0):
    share = {"authority": "provider_reported_lagged", "status": "PROVIDER_REPORTED_LAGGED",
              "value": 1000, "share_concept": "ISSUED_SHARES", "research_proxy_eligible": True,
              "authoritative_current_market_cap_eligible": False}

    def metric(status, value=None):
        return {"status": status, "value": value, "applicability": "APPLICABLE", "blocked_reasons": [], "share_identity": "ISSUED_SHARES"}

    return {
        "ticker": ticker, "entity_class": "corporate", "share_basis_input": share,
        "price_input": {"status": "PRICE_READY", "value": 8.0, "session": DECISION},
        "metrics": {
            "market_cap": metric("RESEARCH_USABLE", market_cap),
            "P/E": metric("RESEARCH_USABLE" if pe is not None else "BLOCKED", pe),
            "P/B": metric("BLOCKED"), "P/S": metric("BLOCKED"),
            "EV/Sales": metric("BLOCKED"), "EV/EBITDA": metric("BLOCKED"),
        },
    }


def behavior(ticker, *, entry="EARLY_REVERSAL_CANDIDATE", session=DECISION):
    return {
        "ticker": ticker, "as_of_session": session, "primary_entry_state": entry,
        "setup_tags": ["EARLY_REVERSAL_STRUCTURE"],
        "confirmation_boundary": {"status": "READY", "as_of": session, "boundary_type": "REVERSAL_CONFIRM"},
        "technical_invalidation_boundary": {"status": "READY", "as_of": session, "boundary_type": "BREAKDOWN"},
        "price_volume_behavior": {}, "trend_context": {}, "structure_context": {},
        "market_regime_context": {"current_breadth_state": "MARKET_BREADTH_MIXED"},
        "sector_context": {"leadership_state": None}, "relative_strength_context": {},
    }


def watchlist(ticker, *, entry="EARLY_REVERSAL_CANDIDATE", action="EARLY_ENTRY"):
    return {"ticker": ticker, "entry_state": entry, "entry_action": action}


def liquidity_record(ticker, *, session=DECISION):
    return {
        "ticker": ticker, "session": session, "disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE",
        "current_ohlc_v": 1000,
        "liquidity_research_contract": {
            "CURRENT_SESSION_LIQUIDITY_RESEARCH": {"state": "ELIGIBLE"},
            "EXECUTION_CAPACITY": {"state": "BLOCKED"}, "ADTV_RESEARCH": {"state": "BLOCKED"},
        },
    }


def _artifact(records, *, session=DECISION, kind="x"):
    return {"session": session, "as_of_session": session, "artifact_identity": _identity(kind), "records": records}


def _feature_store(rows):
    return {"artifact_identity": _identity("feature"), "contract_version": "market_wide_fundamental_feature_store/v1", "records": rows}


def real_pair(*, tickers=("AAA",), session=DECISION, behaviors=None, market_caps=None, pes=None, liquid=True, ttm=True):
    market_caps, pes = market_caps or {}, pes or {}
    behaviors = behaviors or {ticker: "EARLY_REVERSAL_CANDIDATE" for ticker in tickers}
    features = {ticker: feature_record(ticker, ttm_ni=(400.0 if ttm else None), ttm_rev=(4000.0 if ttm else None)) for ticker in tickers}
    valuations = {ticker: valuation_record(ticker, market_cap=market_caps.get(ticker, 8000.0), pe=pes.get(ticker, 10.0)) for ticker in tickers}
    behavior_records = {ticker: behavior(ticker, entry=behaviors[ticker], session=session) for ticker in tickers}
    watch = {ticker: watchlist(ticker, entry=behaviors[ticker]) for ticker in tickers}
    liquids = {ticker: liquidity_record(ticker, session=session) for ticker in tickers} if liquid else {}
    out = build_opportunity_artifacts(
        as_of_session=session, feature_store=_feature_store(features),
        tactical_behavior=_artifact(behavior_records, session=session, kind="tactical"),
        watchlist=_artifact(watch, session=session, kind="watch"),
        valuation={"valuation_session": session, "artifact_identity": _identity("val"), "records": valuations},
        liquidity=_artifact(liquids, session=session, kind="liq") if liquids else None,
        events={"research_session": session, "artifact_identity": _identity("evt"), "records": {}},
        thesis_cases={"as_of_session": session, "artifact_identity": _identity("thesis"), "records": {}},
        requested_at="2026-08-31T00:00:00+07:00",
    )
    return out["opportunity_context"], out["security_decision_context"]


def _leadership(tickers, group="INDUSTRIALS"):
    return {"artifact_identity": _identity("leadership"), "session": DECISION,
            "ticker_contexts": {t: {"sector_leadership_context": {"group_key": group}} for t in tickers}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ticker_denominator_not_silently_dropped():
    opportunity, decision = real_pair(tickers=("AAA", "BBB", "CCC"))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["coverage"]["ticker_denominator"] == 3
    assert out["coverage"]["zero_silent_ticker_drops"] is True
    assert set(out["cards"]) == {"AAA", "BBB", "CCC"}


def test_deterministic_workspace_identity_ignores_wall_clock():
    opportunity, decision = real_pair()
    first = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="2026-08-31T00:00:00+07:00")
    second = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="2099-01-01T00:00:00Z")
    assert first["artifact_sha256"] == second["artifact_sha256"]
    replay = content_identity(first)
    assert replay["artifact_sha256"] == first["artifact_sha256"]


def test_mismatched_lineage_pair_rejected():
    opportunity, _ = real_pair(tickers=("AAA",))
    _, decision = real_pair(tickers=("BBB",))
    with pytest.raises(InvestmentDecisionWorkspaceError):
        build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")


# ---------------------------------------------------------------------------
# WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1
# ---------------------------------------------------------------------------

def test_method_level_usable_value_survives_workspace_projection():
    tickers = ("AAA", "BBB", "CCC", "DDD", "EEE")
    opportunity, decision = real_pair(tickers=tickers, pes={t: 10.0 + i for i, t in enumerate(tickers)})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    diagnostics = out["cards"]["AAA"]["valuation"]["method_diagnostics"]["P/E"]
    assert diagnostics["status"] == "RESEARCH_USABLE"
    assert diagnostics["value"] == pytest.approx(10.0)
    assert diagnostics["availability_state"] == "AVAILABLE_QUALIFIED"


def test_peer_relative_blocker_does_not_erase_available_underlying_multiple():
    # Single ticker: well below MIN_COHORT_MEMBERS, so P/E has no qualified peer cohort --
    # the multiple itself must still survive as AVAILABLE_REFERENCE_ONLY, not disappear.
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": 12.0})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    diagnostics = out["cards"]["AAA"]["valuation"]["method_diagnostics"]["P/E"]
    assert diagnostics["status"] == "RESEARCH_USABLE"
    assert diagnostics["value"] == pytest.approx(12.0)
    assert diagnostics["availability_state"] == "AVAILABLE_REFERENCE_ONLY"
    summary = out["cards"]["AAA"]["valuation"]["valuation_summary"]
    assert summary["qualified_relative_method_count"] == 0
    assert summary["available_method_count"] >= 1


def test_truly_missing_method_stays_none_never_fabricated():
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": None})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    diagnostics = out["cards"]["AAA"]["valuation"]["method_diagnostics"]["P/E"]
    assert diagnostics["value"] is None
    assert diagnostics["availability_state"] == "NOT_AVAILABLE"


def test_blocked_or_proxy_method_cannot_become_qualified_merely_by_being_displayed():
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": 12.0})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    diagnostics = out["cards"]["AAA"]["valuation"]["method_diagnostics"]
    # P/B, P/S, EV/Sales, EV/EBITDA are all BLOCKED in this fixture -- displaying them
    # (they are present in method_diagnostics) never upgrades their availability_state.
    for method_id in ("P/B", "P/S", "EV/Sales", "EV/EBITDA"):
        assert diagnostics[method_id]["availability_state"] == "NOT_AVAILABLE"
        assert diagnostics[method_id]["value"] is None


def test_no_target_price_fair_value_or_dcf_created_by_diagnostic_passthrough():
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": 12.0})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    valuation = out["cards"]["AAA"]["valuation"]
    assert "target_price" not in valuation and "fair_value" not in valuation and "dcf" not in valuation
    for detail in valuation["method_diagnostics"].values():
        assert "target_price" not in detail and "fair_value" not in detail


def test_valuation_summary_never_calls_existing_multiples_intrinsic_fair_value():
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": 12.0})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    summary = out["cards"]["AAA"]["valuation"]["valuation_summary"]
    assert summary["not_intrinsic_fair_value"] is True
    assert "absolute valuation model" not in summary["display_note"].lower()


def test_raw_upstream_relative_state_preserved_separately_from_diagnostics():
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": 12.0})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    valuation = out["cards"]["AAA"]["valuation"]
    assert "raw_upstream_relative_research_state" in valuation
    assert "method_diagnostics" in valuation
    assert valuation["relative_research_state"] not in RELATIVE_VALUATION_LABELS


def test_diagnostic_passthrough_never_absent_when_upstream_lacks_new_field():
    # An older/rigged opportunity_record without "applicable_methods" must degrade to an
    # empty diagnostics map, never crash -- this module never requires requalification.
    card = build_ticker_card(
        ticker="ZZZ",
        opportunity_record={
            "usable_major_axes": [],
            "fundamental": {}, "tactical": {}, "market_sector": {}, "catalyst": {}, "liquidity": {},
            "valuation": {"peer_relative_context": {}, "absolute_research_context": {}},
            "data_authority": {},
        },
        decision_record={"deterministic_research_inference": {}, "warnings_counter_thesis": {}},
        sector="UNKNOWN", portfolio_research=None, prospective_record={"status": "NO_RETAINED_CURRENT_CASES"},
    )
    assert card["valuation"]["method_diagnostics"] == {}
    assert card["valuation"]["valuation_summary"] is None


def test_reference_trigger_display_never_implies_a_fired_confirmed_entry():
    # real_pair's fixture behavior records carry no reference_trigger_context -- the card
    # must degrade to a safe, explicitly-not-available reference, never fabricate a fired
    # trigger or entry authority.
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    trigger = out["cards"]["AAA"]["reference_trigger"]
    assert trigger["entry_authority"] is False
    assert trigger["trigger_condition_satisfied"] is False
    assert trigger["status"] == "NOT_AVAILABLE"
    # RETAINED_WORKSPACE_DIAGNOSTIC_REMATERIALIZATION_V1: reference_trigger lives exactly once
    # (top-level card["reference_trigger"]) -- never duplicated into card["tactical"] or
    # why.tactical_evidence, which the shipped Dashboard renderer never reads it from anyway
    # (it prefers card["reference_trigger"] first in its own fallback chain).
    assert "reference_trigger" not in out["cards"]["AAA"]["tactical"]
    assert "reference_trigger" not in out["cards"]["AAA"]["why"]["tactical_evidence"]


def test_fundamental_catalyst_liquidity_sector_diagnostics_additive_and_present():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    card = out["cards"]["AAA"]
    assert "financial_health" in card["fundamental"]
    assert "peer_relative" in card["fundamental"]
    assert "warnings_blockers" in card["fundamental"]
    assert "adverse_events" in card["catalyst"]
    assert "event_classifications" in card["catalyst"]
    assert "current_session_volume" in card["liquidity"]
    assert "authority_boundary" in card["liquidity"]
    assert "sector_diagnostic" in card["market_sector"]
    # Pre-existing fields are untouched by the additive diagnostics.
    assert card["fundamental"]["state"] == card["why"]["fundamental_evidence"]["state"]


def test_display_metrics_bridge_present_and_never_omits_a_registered_slot():
    """DASHBOARD_INVESTOR_FIRST_PRESENTATION_SIMPLIFICATION_V1: every card gets an additive
    display_metrics block from indicator_metric_display_state.py, covering every investor
    -facing metric slot regardless of whether the underlying value is available."""
    import indicator_metric_display_state as display

    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    card = out["cards"]["AAA"]
    assert "display_metrics" in card
    assert set(card["display_metrics"]) == set(display.INVESTOR_METRIC_ORDER)
    for metric_id, record in card["display_metrics"].items():
        assert record["display_state"] in display.DISPLAY_STATES
        # Compact per-ticker shape: label/family/tooltip are static, published once at
        # the artifact's top-level display_metric_catalog, never repeated per ticker.
        assert set(record) == {"display_state", "value"}
    assert "display_metric_catalog" in out
    assert set(out["display_metric_catalog"]) == set(display.INVESTOR_METRIC_ORDER)
    assert out["display_metric_catalog"]["ebitda"]["label"] == "EBITDA"
    # Pre-existing fields are untouched by this additive bridge.
    assert card["research_stance"] == decision["records"]["AAA"]["research_stance"]


def test_existing_research_stance_byte_identical_with_diagnostic_passthrough():
    tickers = ("AAA", "BBB", "CCC", "DDD", "EEE")
    opportunity, decision = real_pair(tickers=tickers, pes={t: 10.0 + i for i, t in enumerate(tickers)})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    card = out["cards"]["AAA"]
    assert card["research_stance"] == decision["records"]["AAA"]["research_stance"]
    assert card["entry_state"] == decision["records"]["AAA"]["entry_state"]
    assert card["valuation"]["relative_research_state"] == card["why"]["valuation_evidence"]["relative_research_state"]


# ---------------------------------------------------------------------------
# INDICATOR_METRIC_AVAILABILITY_RECOVERY_CLASSIFICATION_CORRECTIVE_V1 (2026-09-20) continuation:
# wiring same_session_technical_coverage_disposition/v1 + market_wide_current_technical_
# coverage_scaleout/v1 evidence into the real live caller chain (build_artifacts ->
# build_ticker_card -> indicator_metric_display_state.build_ticker_display_metrics ->
# indicator_metric_availability.evaluate_ticker).
# ---------------------------------------------------------------------------

import same_session_technical_coverage_disposition as _disposition_module
import market_wide_current_technical_coverage_scaleout as _scaleout_module
from investment_decision_workspace_projection import _coherent_technical_evidence


def _disposition_artifact(records: dict, *, session: str = DECISION) -> dict:
    payload = {"schema_version": "1.0.0", "contract_version": "same_session_technical_coverage_disposition/v1",
               "session": session, "records": records}
    return {**payload, **_disposition_module.content_identity(payload)}


def _recovery_artifact(records: dict, *, session: str = DECISION) -> dict:
    payload = {"schema_version": "1.0.0", "contract_version": "market_wide_current_technical_coverage_scaleout/v1",
               "target_session": session, "records": records}
    return {**payload, **_scaleout_module.content_identity(payload)}


_MINIMAL_OPPORTUNITY_RECORD = {
    "usable_major_axes": [], "fundamental": {}, "tactical": {}, "market_sector": {}, "catalyst": {}, "liquidity": {},
    "valuation": {"peer_relative_context": {}, "absolute_research_context": {}}, "data_authority": {},
}
_MINIMAL_DECISION_RECORD = {"deterministic_research_inference": {}, "warnings_counter_thesis": {}}


def _minimal_card(ticker, **kwargs):
    return build_ticker_card(
        ticker=ticker, opportunity_record=_MINIMAL_OPPORTUNITY_RECORD, decision_record=_MINIMAL_DECISION_RECORD,
        sector="UNKNOWN", portfolio_research=None, prospective_record={"status": "NO_RETAINED_CURRENT_CASES"},
        **kwargs,
    )


def test_coherent_technical_evidence_accepts_matching_session_and_identity():
    disposition = _disposition_artifact({"AAA": {"disposition": "PROVIDER_SESSION_UNAVAILABLE"}})
    recovery = _recovery_artifact({})
    disp_records, rec_records = _coherent_technical_evidence(
        as_of_session=DECISION, technical_coverage_disposition=disposition, technical_history_recovery=recovery,
    )
    assert disp_records == disposition["records"]
    assert rec_records == recovery["records"]


def test_coherent_technical_evidence_rejects_stale_session():
    stale = _disposition_artifact({"AAA": {"disposition": "PROVIDER_SESSION_UNAVAILABLE"}}, session="1999-01-01")
    disp_records, rec_records = _coherent_technical_evidence(
        as_of_session=DECISION, technical_coverage_disposition=stale, technical_history_recovery=None,
    )
    assert disp_records is None
    assert rec_records is None


def test_coherent_technical_evidence_rejects_tampered_content_identity():
    disposition = _disposition_artifact({"AAA": {"disposition": "PROVIDER_SESSION_UNAVAILABLE"}})
    tampered = dict(disposition, records={"AAA": {"disposition": "SAME_SESSION_TECHNICAL_COVERED"}})
    disp_records, _ = _coherent_technical_evidence(
        as_of_session=DECISION, technical_coverage_disposition=tampered, technical_history_recovery=None,
    )
    assert disp_records is None


def test_coherent_technical_evidence_rejects_wrong_contract_version():
    disposition = _disposition_artifact({"AAA": {"disposition": "PROVIDER_SESSION_UNAVAILABLE"}})
    wrong = dict(disposition, contract_version="something_else/v1")
    disp_records, _ = _coherent_technical_evidence(
        as_of_session=DECISION, technical_coverage_disposition=wrong, technical_history_recovery=None,
    )
    assert disp_records is None


def test_coherent_technical_evidence_drops_recovery_when_disposition_incoherent():
    """recovery is only ever consulted from inside a disposition-driven branch -- if disposition
    fails coherence, recovery must never be applied on its own, even if it is itself coherent."""
    stale_disposition = _disposition_artifact({"AAA": {"disposition": "PROVIDER_SESSION_UNAVAILABLE"}}, session="1999-01-01")
    coherent_recovery = _recovery_artifact({})
    disp_records, rec_records = _coherent_technical_evidence(
        as_of_session=DECISION, technical_coverage_disposition=stale_disposition, technical_history_recovery=coherent_recovery,
    )
    assert disp_records is None
    assert rec_records is None


def test_coherent_technical_evidence_handles_absent_evidence():
    disp_records, rec_records = _coherent_technical_evidence(
        as_of_session=DECISION, technical_coverage_disposition=None, technical_history_recovery=None,
    )
    assert disp_records is None
    assert rec_records is None


def test_build_ticker_card_without_technical_evidence_is_backward_compatible():
    """Old callers (no technical_coverage_disposition_records/technical_history_recovery_records
    kwargs at all) keep working exactly as before -- fails closed, never crashes."""
    card = _minimal_card("ZZZ")
    assert card["display_metrics"]["technical_trend_entry_state"]["display_state"] == "INSUFFICIENT_DATA"


def test_build_ticker_card_wires_provider_session_unavailable_evidence():
    card = _minimal_card(
        "ZZZ",
        technical_coverage_disposition_records={"ZZZ": {"disposition": "PROVIDER_SESSION_UNAVAILABLE", "reason_code": "X"}},
    )
    assert card["display_metrics"]["technical_trend_entry_state"]["display_state"] == "INSUFFICIENT_DATA"


def test_build_ticker_card_wires_invalid_delisted_symbol_to_not_applicable_display():
    """The one investor-visible effect of this milestone: a delisted/invalid symbol renders
    NOT_APPLICABLE through the real card-building path, not a misleading INSUFFICIENT_DATA."""
    card = _minimal_card(
        "ZZZ",
        technical_coverage_disposition_records={"ZZZ": {"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL",
                                                          "reason_code": "DELISTED_OR_NO_LONGER_CURRENT"}},
    )
    assert card["display_metrics"]["technical_trend_entry_state"]["display_state"] == "NOT_APPLICABLE"


def test_build_ticker_card_wires_exhausted_provider_chain_evidence():
    card = _minimal_card(
        "ZZZ",
        technical_coverage_disposition_records={"ZZZ": {"disposition": "PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION"}},
        technical_history_recovery_records={"ZZZ": {"state": "INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK",
                                                      "reason": "NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES"}},
    )
    assert card["display_metrics"]["technical_trend_entry_state"]["display_state"] == "INSUFFICIENT_DATA"


def test_build_ticker_card_ticker_mismatch_is_absent_evidence_not_a_crash():
    """Evidence keyed under a DIFFERENT ticker than the one being built must never leak in --
    a plain dict lookup miss, degrading to the same fail-closed default as no evidence at all."""
    card = _minimal_card(
        "ZZZ",
        technical_coverage_disposition_records={"SOME_OTHER_TICKER": {"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL"}},
    )
    assert card["display_metrics"]["technical_trend_entry_state"]["display_state"] == "INSUFFICIENT_DATA"


def test_build_artifacts_wires_coherent_evidence_through_the_full_live_path():
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": None})
    disposition = _disposition_artifact({"AAA": {"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL",
                                                  "reason_code": "DELISTED_OR_NO_LONGER_CURRENT"}})
    out = build_artifacts(
        opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t",
        technical_coverage_disposition=disposition,
    )
    card = out["cards"]["AAA"]
    assert card["display_metrics"]["technical_trend_entry_state"]["display_state"] == "NOT_APPLICABLE"
    assert out["source_artifacts"]["technical_coverage_disposition"] == disposition["artifact_identity"]
    assert out["source_artifacts"]["technical_history_recovery"] is None


def test_build_artifacts_rejects_stale_session_evidence_end_to_end():
    """The old blanket 727-style RECOVER_NOW_EXISTING_PROVIDER_PATH claim can never recur even
    via a stale evidence artifact reaching build_artifacts: a session mismatch drops the
    evidence entirely, so the card falls back to the existing fail-closed UNKNOWN_BLOCKER/
    INSUFFICIENT_DATA default, never a fabricated recovery claim."""
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": None})
    stale_disposition = _disposition_artifact(
        {"AAA": {"disposition": "PIPELINE_ELIGIBILITY_OR_FILTER_EXCLUSION"}}, session="1999-01-01",
    )
    out = build_artifacts(
        opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t",
        technical_coverage_disposition=stale_disposition,
    )
    card = out["cards"]["AAA"]
    assert card["display_metrics"]["technical_trend_entry_state"]["display_state"] == "INSUFFICIENT_DATA"
    assert out["source_artifacts"]["technical_coverage_disposition"] is None


def test_build_artifacts_without_technical_evidence_kwargs_is_unaffected():
    """Every existing caller of build_artifacts() that never supplies the two new keyword
    arguments must build byte-for-byte the same cards as before this milestone's continuation."""
    opportunity, decision = real_pair(tickers=("AAA", "BBB"))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["source_artifacts"]["technical_coverage_disposition"] is None
    assert out["source_artifacts"]["technical_history_recovery"] is None
    for ticker in ("AAA", "BBB"):
        assert "display_metrics" in out["cards"][ticker]


def test_empty_denominator_rejected():
    opportunity, decision = real_pair(tickers=("AAA",))
    empty_opportunity = {**opportunity, "records": {}}
    with pytest.raises(InvestmentDecisionWorkspaceError):
        build_artifacts(opportunity_artifact=empty_opportunity, decision_artifact=decision, requested_at="t")


def test_market_cap_only_cannot_create_valuation_stance_end_to_end():
    # AAA has zero usable relative multiples (P/E blocked here) but a real market-cap peer cohort
    # via BBB/CCC/DDD/EEE -- the whole pipeline (fixed upstream attach_peer_relative, then this
    # module's own defensive guard) must not label AAA attractive/expensive.
    opportunity, decision = real_pair(
        tickers=("AAA", "BBB", "CCC", "DDD", "EEE"),
        market_caps={"AAA": 1000.0, "BBB": 5000.0, "CCC": 5000.0, "DDD": 9000.0, "EEE": 20000.0},
        pes={"AAA": None, "BBB": None, "CCC": None, "DDD": None, "EEE": None},
        ttm=False,
    )
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    card = out["cards"]["AAA"]
    assert card["valuation"]["usable_relative_method_count"] == 0
    assert card["valuation"]["relative_research_state"] not in RELATIVE_VALUATION_LABELS


def test_defensive_guard_overrides_a_rigged_upstream_mislabel():
    # Unit-level defense-in-depth: even if some future/older opportunity_context artifact still
    # carries a market-cap-driven ATTRACTIVE_RELATIVE_RESEARCH label (e.g. materialized before the
    # source-level fix), this module must never display it as attractive/expensive.
    opportunity_record = {
        "ticker": "ZZZ", "usable_major_axes": ["fundamental", "valuation", "tactical"],
        "fundamental": {"state": "PROFITABLE", "trajectory": "INSUFFICIENT_DATA", "readiness": "READY_RESEARCH_PROXY", "research_fitness": "READY", "freshness": {}},
        "valuation": {
            "readiness": "READY_RESEARCH_PROXY", "share_basis": "CURRENT_SHARE_RESEARCH_PROXY", "entity_class": "corporate",
            "freshness": {"freshness_status": "CURRENT", "source_session": DECISION},
            "absolute_research_context": {"usable_relative_method_count": 0},
            "peer_relative_context": {
                "relative_research_state": "ATTRACTIVE_RELATIVE_RESEARCH",
                "methods": {"market_cap": {"status": "READY_RESEARCH_ONLY", "percentile": 0.1, "peer_count": 5}},
            },
        },
        "tactical": {"primary_entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION", "setup_tags": [], "freshness": {}},
        "market_sector": {"freshness": {}},
        "catalyst": {"freshness": {}},
        "liquidity": {"freshness": {}},
        "data_authority": {"per_axis_session": {}, "per_axis_freshness": {}, "proxy_or_qualified_state": {}, "blockers": []},
    }
    decision_record = {
        "as_of_session": DECISION, "research_stance": "INITIATE_RESEARCH_CANDIDATE", "research_stance_readiness": "RESEARCH_READY_CONDITIONAL",
        "entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION",
        "deterministic_research_inference": {"reasons": []}, "warnings_counter_thesis": {"warnings": []},
        "confirmation_boundary": {"status": "READY"}, "technical_invalidation": {"status": "READY"},
        "fundamental_invalidation": {"status": "UNAVAILABLE"}, "key_counter_thesis": [],
    }
    card = build_ticker_card(
        ticker="ZZZ", opportunity_record=opportunity_record, decision_record=decision_record,
        sector="UNKNOWN", portfolio_research=None, prospective_record={"status": "NO_RETAINED_CURRENT_CASES"},
    )
    assert card["valuation"]["relative_research_state"] not in RELATIVE_VALUATION_LABELS
    assert card["valuation"]["market_cap_semantic_guard_applied"] is True
    assert card["valuation"]["raw_upstream_relative_research_state"] == "ATTRACTIVE_RELATIVE_RESEARCH"
    # The security research stance itself is untouched by the valuation display guard.
    assert card["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"


def test_valuation_supporting_method_and_basis_exposed_when_real():
    opportunity, decision = real_pair(tickers=("AAA",), pes={"AAA": 10.0})
    # Give AAA four peers on the same P/E basis so it clears MIN_COHORT_MEMBERS.
    opp2, dec2 = real_pair(tickers=("AAA", "BBB", "CCC", "DDD", "EEE"), pes={t: 10.0 + i for i, t in enumerate(("AAA", "BBB", "CCC", "DDD", "EEE"))})
    out = build_artifacts(opportunity_artifact=opp2, decision_artifact=dec2, requested_at="t")
    card = out["cards"]["AAA"]
    if card["valuation"]["relative_research_state"] in RELATIVE_VALUATION_LABELS:
        assert card["valuation"]["supporting_methods"]
        method = card["valuation"]["supporting_methods"][0]
        assert method["method"] and method["basis"] is not None


def test_research_stance_preserved_verbatim_from_decision_context():
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": "DOWNTREND"})
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["cards"]["AAA"]["research_stance"] == decision["records"]["AAA"]["research_stance"] == "AVOID_NEW_ENTRY"


def test_why_section_carries_counterbalancing_context_from_decision_record():
    # AAA is DOWNTREND (AVOID_NEW_ENTRY) with a profitable fundamental -- the positive evidence
    # must reach the card's Why section as counterbalancing context, not be dropped by the join.
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": "DOWNTREND"})
    assert decision["records"]["AAA"]["counterbalancing_context"] == ["PROFITABLE_FUNDAMENTAL"]
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["why"]["counterbalancing_context"] == ["PROFITABLE_FUNDAMENTAL"]
    assert "PROFITABLE_FUNDAMENTAL" not in card["why"]["deterministic_reasons"]


def test_portfolio_fit_is_separate_from_and_never_mutates_security_stance():
    opportunity, decision = real_pair(tickers=("AAA",))
    portfolio_research = {
        "portfolio_id": "demo", "as_of_session": DECISION, "normalized_positions": [],
        "user_limit_breaches": [{"reason": "MAX_SECTOR_WEIGHT", "sector": "UNKNOWN"}],
        "sector_concentration": {"UNKNOWN": 0.5}, "tactical_concentration": {},
        "selected_joint_risk_horizon": "L60", "joint_risk_status": "READY",
        "pairwise_correlation_status": "AVAILABLE_SEPARATELY_FROM_JOINT_MATRIX",
    }
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, portfolio_research=portfolio_research, requested_at="t")
    card = out["cards"]["AAA"]
    assert card["portfolio"]["status"] == "EXCEEDS_USER_POLICY_LIMIT"
    assert card["research_stance"] == decision["records"]["AAA"]["research_stance"]
    assert card["authority_boundary"]["security_attractiveness_separate_from_portfolio_fit"] is True


def test_portfolio_not_evaluated_when_not_supplied():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["cards"]["AAA"]["portfolio"] == {
        "evaluated": False, "status": "NOT_EVALUATED", "reason": "NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED",
    }
    assert out["coverage"]["portfolio_evaluated_count"] == 0


def test_mixed_session_freshness_preserved_per_axis_not_coerced():
    opportunity, decision = real_pair(tickers=("AAA",))
    lineage = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]["lineage"]
    sessions = lineage["per_axis_source_session"]
    # tactical/liquidity are session-dated CURRENT; fundamental is period-based -- distinct axes,
    # never coerced into one fabricated same-session snapshot.
    assert sessions.get("tactical") == DECISION
    assert lineage["per_axis_freshness"].get("tactical") == "CURRENT"


def test_liquidity_proxy_and_exact_execution_capacity_are_separate_fields():
    opportunity, decision = real_pair(tickers=("AAA",))
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["liquidity"]["readiness"] == "LIQUIDITY_RESEARCH_PROXY"
    assert card["liquidity"]["exact_execution_capacity_status"] == "EXECUTION_CAPACITY_EXACT_BLOCKED"


def test_exact_liquidity_block_does_not_force_wait():
    opportunity, decision = real_pair(tickers=("AAA",), behaviors={"AAA": "EARLY_REVERSAL_CANDIDATE"})
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["liquidity"]["exact_execution_capacity_status"] == "EXECUTION_CAPACITY_EXACT_BLOCKED"
    assert card["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"
    assert card["research_stance"] != "WAIT_FOR_CONFIRMATION"


def test_confirmation_and_invalidation_retained():
    opportunity, decision = real_pair(tickers=("AAA",))
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["confirmation"]["status"] == "READY"
    assert card["invalidation"]["technical"]["status"] == "READY"
    assert "fundamental" in card["invalidation"]


def test_absent_deep_evidence_is_localized_and_does_not_block_the_card():
    opportunity, decision = real_pair(tickers=("AAA",))
    card = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")["cards"]["AAA"]
    assert card["lineage"]["deep_evidence_availability"] == "DEEP_EVIDENCE_ARTIFACT_NOT_MATERIALIZED_LOCALLY"
    assert card["research_stance"] is not None


def test_no_current_prospective_cases_does_not_block_workspace():
    # No prospective_lifecycle artifact supplied at all -> honest CASE_DATA_UNAVAILABLE, and the
    # ticker still gets a complete card (prospective cases are not a prerequisite).
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["cards"]["AAA"]["prospective_case"]["status"] == "CASE_DATA_UNAVAILABLE"
    assert out["coverage"]["ticker_denominator"] == 1
    assert out["cards"]["AAA"]["research_stance"] is not None

    # Artifact supplied but this ticker genuinely absent from it -> NO_RETAINED_CURRENT_CASES,
    # distinct from CASE_DATA_UNAVAILABLE.
    lifecycle = {"artifact_identity": "lifecycle:1", "records": {"OTHER": {"thesis_lifecycle_state": "UNCHANGED"}}}
    out2 = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, prospective_lifecycle=lifecycle, requested_at="t")
    assert out2["cards"]["AAA"]["prospective_case"]["status"] == "NO_RETAINED_CURRENT_CASES"


def test_forward_outcome_pending_when_lifecycle_is_initial_observation():
    opportunity, decision = real_pair(tickers=("AAA",))
    lifecycle = {
        "artifact_identity": "lifecycle:1",
        "records": {"AAA": {"thesis_lifecycle_state": "INITIAL_OBSERVATION", "previous_session": None, "current_session": DECISION,
                             "material_change": False, "material_change_reasons": [], "component_transitions": [],
                             "current_recommendation": {"recommendation_label": "INITIATE_RESEARCH_CANDIDATE"}, "current_tactical_state": {"entry_state": "BREAKOUT_READY"}}},
    }
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, prospective_lifecycle=lifecycle, requested_at="t")
    prospective = out["cards"]["AAA"]["prospective_case"]
    assert prospective["status"] == "PENDING_NOT_ENOUGH_FUTURE_SESSIONS"
    assert prospective["forward_outcome_status"] == "PENDING_NOT_ENOUGH_FUTURE_SESSIONS"
    for field in ("t_plus_5", "t_plus_20", "t_plus_60", "mfe", "mae", "benchmark_relative_result"):
        assert prospective[field] is None


def test_t0_is_never_fabricated_when_no_prior_session_exists():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    prospective = out["cards"]["AAA"]["prospective_case"]
    assert prospective["t0_session"] is None
    assert prospective["t0_stance"] is None


def test_sector_enrichment_from_leadership_when_available_else_unknown():
    opportunity, decision = real_pair(tickers=("AAA",))
    with_leadership = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision,
                                       leadership=_leadership(["AAA"], group="STEEL"), requested_at="t")
    without_leadership = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert with_leadership["cards"]["AAA"]["sector"] == "STEEL"
    assert without_leadership["cards"]["AAA"]["sector"] == "UNKNOWN"


def test_no_score_rank_probability_or_target_price_anywhere():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    assert out["blocked_outputs"]["universal_score"] == "SCORING_PROHIBITED"
    assert out["blocked_outputs"]["target_price"] == "NOT_EMITTED"
    card = out["cards"]["AAA"]
    assert "score" not in card and "rank" not in card and "probability" not in card and "target_price" not in card
    assert card["authority_boundary"]["no_score"] is True
    assert card["authority_boundary"]["no_probability"] is True


# ---------------------------------------------------------------------------
# SIGNAL_VELOCITY_AND_FLOW_PRICE_DECISION_PRESENTATION_V1
# ---------------------------------------------------------------------------

def _velocity_artifact(ticker, session, overall="STABLE"):
    return {
        "contract_version": "multi_session_signal_velocity/v1.2",
        "artifact_identity": "multi_session_signal_velocity:test",
        "records": [{
            "ticker": ticker, "session": session, "overall_transition_state": overall,
            "evidence_quality": {"state": "COMPLETE_RETAINED_EVIDENCE"},
            "axes": {"structural_repair": {"trajectory": {
                "valid_observation_count": 3, "retained_session_span": {"first": "2026-09-10", "last": session},
                "continuity_state": "CONTIGUOUS_RETAINED_OBSERVATIONS", "latest_transition": "IMPROVING",
                "persistence": "IMPROVEMENT_PERSISTENT", "acceleration_state": "NOT_EVALUABLE_CATEGORICAL_ONLY",
            }}},
            "independent_supporting_axes": ["structural_repair"], "contradicting_axes": [],
        }],
    }


def _flow_price_artifact(ticker, session, relationship="FLOW_PRICE_MIXED"):
    return {
        "contract_version": "flow_price_divergence_shadow/v1",
        "artifact_identity": "flow_price_divergence_shadow:test",
        "records": [{
            "ticker": ticker, "reference_session": session,
            "flow": {"state": "NET_FOREIGN_BUY", "persistence": "MIXED_FLOW", "latest_qualified_flow_session": session, "freshness": {"status": "current"}},
            "price": {"state": "PRICE_MIXED", "velocity_state": "MIXED_TRANSITION", "participation_context": "PARTICIPATION_NEUTRAL", "market_support": "SUPPORTIVE", "sector_support": "MIXED"},
            "relationship": relationship, "evidence_quality": "COMPLETE_RETAINED_EVIDENCE",
            "session_alignment": {"state": "EXACT_SESSION_ALIGNED"}, "limitations": ["QUALIFIED_FOREIGN_VALUE_ONLY"],
        }],
    }


def test_card_gains_signal_velocity_and_flow_price_when_artifacts_supplied():
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(
        opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t",
        signal_velocity_artifact=_velocity_artifact("AAA", DECISION, overall="PERSISTENT_IMPROVEMENT"),
        flow_price_artifact=_flow_price_artifact("AAA", DECISION, relationship="FOREIGN_BUYING_PRICE_WEAKNESS"),
        flow_research_cohort_tickers=frozenset({"AAA"}),
    )
    card = out["cards"]["AAA"]
    assert card["signal_velocity"]["overall_transition_state"] == "PERSISTENT_IMPROVEMENT"
    assert card["signal_velocity"]["acceleration_state"] == "NOT_EVALUABLE_CATEGORICAL_ONLY"
    assert card["flow_price"]["relationship"] == "FOREIGN_BUYING_PRICE_WEAKNESS"
    assert card["flow_price"]["cohort_membership"] == "IN_CURRENT_FLOW_RESEARCH_COHORT"
    assert out["source_artifacts"]["signal_velocity"] == "multi_session_signal_velocity:test"
    assert out["source_artifacts"]["flow_price_divergence_shadow"] == "flow_price_divergence_shadow:test"
    assert out["coverage"]["signal_velocity_distribution"] == {"PERSISTENT_IMPROVEMENT": 1}
    assert out["coverage"]["flow_price_research_cohort_tickers"] == ["AAA"]
    assert out["coverage"]["flow_price_relationship_distribution_within_cohort"] == {"FOREIGN_BUYING_PRICE_WEAKNESS": 1}


def test_card_degrades_explicitly_when_velocity_and_flow_price_absent():
    """Absence of the two new optional artifacts must never break the workspace, and must never
    silently omit the fields either -- every card still carries an explicit unavailable state."""
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t")
    card = out["cards"]["AAA"]
    assert card["signal_velocity"]["overall_transition_state"] == "INSUFFICIENT_EVIDENCE"
    assert card["flow_price"]["relationship"] == "FLOW_UNAVAILABLE"
    assert card["flow_price"]["cohort_membership"] == "OUTSIDE_CURRENT_FLOW_RESEARCH_COHORT"
    assert out["source_artifacts"]["signal_velocity"] is None
    assert out["source_artifacts"]["flow_price_divergence_shadow"] is None


def test_flow_price_cohort_coverage_denominator_is_cohort_not_full_universe():
    """1,672 tickers outside the flow cohort must never widen the relationship-distribution
    denominator used for any market-wide-sounding statistic."""
    tickers = ("AAA", "BBB", "CCC")
    opportunity, decision = real_pair(tickers=tickers)
    out = build_artifacts(
        opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t",
        flow_price_artifact=_flow_price_artifact("AAA", DECISION, relationship="FLOW_PRICE_MIXED"),
        flow_research_cohort_tickers=frozenset({"AAA"}),
    )
    assert out["coverage"]["flow_price_research_cohort_count"] == 1
    assert out["coverage"]["flow_price_relationship_distribution_within_cohort"] == {"FLOW_PRICE_MIXED": 1}
    # BBB/CCC are outside the cohort and must not appear in the cohort-denominated distribution
    # even though they also carry an (outside-cohort) flow_price field on their own cards.
    assert out["cards"]["BBB"]["flow_price"]["cohort_membership"] == "OUTSIDE_CURRENT_FLOW_RESEARCH_COHORT"
    assert out["cards"]["CCC"]["flow_price"]["cohort_membership"] == "OUTSIDE_CURRENT_FLOW_RESEARCH_COHORT"


def test_velocity_session_mismatch_falls_back_to_insufficient_evidence():
    """A velocity record from a different session must never be presented as current."""
    opportunity, decision = real_pair(tickers=("AAA",))
    out = build_artifacts(
        opportunity_artifact=opportunity, decision_artifact=decision, requested_at="t",
        signal_velocity_artifact=_velocity_artifact("AAA", "2026-08-01", overall="PERSISTENT_IMPROVEMENT"),
    )
    assert out["cards"]["AAA"]["signal_velocity"]["overall_transition_state"] == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# Real-evidence acceptance: the actual retained 2026-09-18 same_session_technical_coverage_
# disposition/v1 + market_wide_current_technical_coverage_scaleout/v1 artifacts, joined through
# the ACTUAL live path (indicator_metric_availability.evaluate_ticker /
# indicator_metric_display_state.build_ticker_display_metrics), not just build_ticker_card's
# minimal synthetic fixtures above. Guarded by skipif since these dated operations-review/
# artifacts are gitignored and only exist in a checkout where the 2026-09-18 Daily session (and
# its milestone-scoped disposition/recovery tool runs) actually happened -- e.g. the long-lived
# primary checkout, never a freshly created isolated milestone worktree.
# ---------------------------------------------------------------------------

import indicator_metric_availability as _availability  # noqa: E402
import indicator_metric_display_state as _display_state  # noqa: E402

_OPS = Path(__file__).resolve().parents[1] / "operations-review"
_REAL_WORKSPACE_PATH = (
    _OPS / "daily-research-session-operations-v1/2026-09-18"
    / "8a857ca4204136e42982dd2d1b953ebb857f3a6599837d7b0d20b3a820c3b95f"
    / "investment_decision_workspace_projection.json"
)
_REAL_DISPOSITION_PATH = (
    _OPS / "same-session-technical-coverage-recovery-v1-20260918" / "same_session_technical_coverage_disposition_artifact.json"
)
_REAL_RECOVERY_PATH = (
    _OPS / "market-wide-current-technical-coverage-scaleout-v1-20260918" / "market_wide_current_technical_coverage_recovery_artifact.json"
)


# Retained-evidence tier: the real retained 2026-09-18 technical evidence artifacts.
@pytest.mark.retained_evidence(
    *(path.relative_to(_OPS.parent).as_posix()
      for path in (_REAL_WORKSPACE_PATH, _REAL_DISPOSITION_PATH, _REAL_RECOVERY_PATH))
)
def test_real_20260918_live_path_reconciles_to_the_exact_evidence_verified_counts():
    """Phase 6/7/8 real end-to-end proof: the LIVE display-metrics caller (not a helper called
    in isolation) reconciles the real, retained 2026-09-18 universe (1,683 tickers) to exactly
    956 READY / 544 PROVIDER_SESSION_UNAVAILABLE / 180 INVALID_OR_DELISTED_SYMBOL / 3
    NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES / 0 genuinely-recoverable-now / 0 UNKNOWN_BLOCKER
    -- see operations-review/indicator-metric-availability-recovery-classification-corrective-
    v1-20260920/live_path_before_after.json for the full run this test also reproduces."""
    ws = json.loads(_REAL_WORKSPACE_PATH.read_text(encoding="utf-8"))
    disposition = json.loads(_REAL_DISPOSITION_PATH.read_text(encoding="utf-8"))
    recovery = json.loads(_REAL_RECOVERY_PATH.read_text(encoding="utf-8"))

    disp_records, rec_records = _coherent_technical_evidence(
        as_of_session=ws.get("as_of_session"),
        technical_coverage_disposition=disposition,
        technical_history_recovery=recovery,
    )
    assert disp_records is not None and len(disp_records) == 1683
    assert rec_records is not None and len(rec_records) == 7

    from collections import Counter
    blocker_counts: Counter = Counter()
    display_counts: Counter = Counter()
    cohort = frozenset({"EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM"})
    for ticker, card in ws["cards"].items():
        disp_row = disp_records.get(ticker)
        rec_row = rec_records.get(ticker)
        record = _availability.evaluate_ticker(
            ticker, card, cohort_tickers=cohort,
            technical_coverage_disposition=disp_row, technical_history_recovery_record=rec_row,
        )["technical_trend_entry_state"]
        blocker_counts[record["blocker_class"]] += 1
        display_metrics = _display_state.build_ticker_display_metrics(
            ticker, card, cohort_tickers=cohort,
            technical_coverage_disposition_record=disp_row, technical_history_recovery_record=rec_row,
        )
        display_counts[display_metrics["technical_trend_entry_state"]["display_state"]] += 1

    assert blocker_counts["READY"] == 956
    assert blocker_counts["PROVIDER_SESSION_UNAVAILABLE"] == 544
    assert blocker_counts["INVALID_OR_DELISTED_SYMBOL"] == 180
    assert blocker_counts["NO_FEATURE_SAFE_COMPATIBLE_PROVIDER_SERIES"] == 3
    assert blocker_counts.get("RECOVERABLE_BY_EXISTING_BACKFILL", 0) == 0
    assert blocker_counts.get("UNKNOWN_BLOCKER", 0) == 0
    assert sum(blocker_counts.values()) == 1683

    assert display_counts["AVAILABLE"] == 956
    assert display_counts["INSUFFICIENT_DATA"] == 547
    assert display_counts["NOT_APPLICABLE"] == 180
    assert set(display_counts) <= set(_display_state.DISPLAY_STATES)
