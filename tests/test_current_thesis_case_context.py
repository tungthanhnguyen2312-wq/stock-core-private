"""Targeted tests for current_thesis_case_context.py (CANONICAL_EVIDENCE_BOUND_THESIS_CASES_
DECISION_INPUT_V1).

Root cause under test: the canonical current chain has always passed ``thesis_cases=None`` into
``current_valuation_opportunity_integration.build_artifacts`` -- this module is the first
deterministic, evidence-bound builder for that input, sourced only from already-upstream
``financial_analysis_product_context``/corporate event context, never from presentation scenario
artifacts and never from security_decision_context/Workspace/Screener/portfolio output.
"""
from __future__ import annotations

import inspect

import current_thesis_case_context as tcc
import current_valuation_opportunity_integration as cvoi


SESSION = "2026-09-11"


def _fa_context(records):
    return {"contract_version": "financial_analysis_product_integration/v1", "artifact_identity": "fa_v2:1", "records": records}


def _fa_record(**overrides):
    record = {
        "status": "AVAILABLE", "as_of_financial_period": "2026-Q2-TTM", "lineage_ref": "lineage:1",
        "profitability_state": None, "margin_state": None, "balance_sheet_state": None,
        "cash_conversion_state": None, "growth_state": None,
        # Prose fields that must never be read as structured evidence by this module.
        "positive_evidence": ["AAA: profitable retained net income"],
        "negative_evidence": ["AAA: compatible net margin compressing"],
        "conflicting_evidence": ["AAA: growth conflicts with margin compression"],
    }
    record.update(overrides)
    return record


def _events(records):
    return {"artifact_identity": "evt:1", "records": records}


def _event_record(events):
    return {"research_session": "2026-09-10", "events": events}


# ---------------------------------------------------------------------------
# Contract: evidence mapping by case class
# ---------------------------------------------------------------------------

def test_supporting_and_counter_evidence_map_from_fa_v2_categorical_states_only():
    fa = _fa_context({"AAA": _fa_record(
        profitability_state="PROFITABLE", margin_state="MARGIN_EXPANDING",
        balance_sheet_state="DETERIORATING", cash_conversion_state="WEAK", growth_state="CONTRACTING",
    )})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=None,
    )
    record = artifact["records"]["AAA"]
    supporting_dims = {item["source_dimension"] for item in record["supporting_evidence"]}
    counter_dims = {item["source_dimension"] for item in record["counter_thesis_evidence_detail"]}
    assert supporting_dims == {"PROFITABILITY", "MARGIN"}
    assert counter_dims == {"BALANCE_SHEET", "CASH_CONVERSION", "GROWTH"}
    assert "SUPPORT" in record["case_classes_present"]
    assert "COUNTER" in record["case_classes_present"]
    # The consumer-facing tag list excludes dimensions security_decision_context's own FA V2
    # annotation already tags from this same record (BALANCE_SHEET, CASH_CONVERSION here) --
    # only the non-duplicate GROWTH dimension surfaces as a key_counter_thesis tag.
    assert record["counter_thesis_evidence"] == ["FA_V2_GROWTH_CONTRACTING"]
    # Never read the engine's own prose evidence lists as structured thesis evidence.
    for item in record["supporting_evidence"] + record["counter_thesis_evidence_detail"]:
        assert "AAA:" not in str(item["value"])
        assert item["value"] in {"profitability_state", "margin_state", "balance_sheet_state", "cash_conversion_state", "growth_state"}


def test_fundamental_invalidation_is_a_distinct_boundary_not_folded_into_counter_thesis():
    fa = _fa_context({"AAA": _fa_record(profitability_state="PROFITABLE")})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=None,
    )
    record = artifact["records"]["AAA"]
    invalidation = record["fundamental_invalidation"]
    assert invalidation["status"] == "READY"
    assert invalidation["thesis_dimension"] == "PROFITABILITY"
    assert invalidation["watch_state"] == "LOSS_MAKING"
    assert invalidation["as_of"] == "2026-Q2-TTM"
    # The boundary is its own object, never appended into either counter-thesis list.
    assert invalidation not in record["counter_thesis_evidence_detail"]
    assert invalidation not in record["counter_thesis_evidence"]
    assert "INVALIDATION" in record["case_classes_present"]


def test_no_positive_fa_v2_state_means_no_fabricated_invalidation():
    fa = _fa_context({"AAA": _fa_record(profitability_state="LOSS_MAKING")})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=None,
    )
    record = artifact["records"]["AAA"]
    assert record["fundamental_invalidation"]["status"] == "UNAVAILABLE"
    assert record["fundamental_invalidation"]["reason"] == "NO_POSITIVE_FA_V2_STATE_TO_INVALIDATE"
    assert "INVALIDATION" not in record["case_classes_present"]
    # LOSS_MAKING is itself observed negative evidence -- retained in the full detail list, but
    # not re-emitted as a key_counter_thesis tag since security_decision_context's own FA V2
    # annotation already tags PROFITABLE/LOSS_MAKING from this same record.
    assert any(item["source_dimension"] == "PROFITABILITY" for item in record["counter_thesis_evidence_detail"])
    assert record["counter_thesis_evidence"] == []


def test_risk_evidence_maps_from_genuinely_adverse_event_status_only():
    events = _events({
        "AAA": _event_record([{"event_type": "AGM", "event_status": "CANCELLED", "known_at": "2026-09-09",
                                "evidence_tier": "OFFICIAL_QUALIFIED", "source_record_identity": "src:1"}]),
        "BBB": _event_record([{"event_type": "CASH_DIVIDEND", "event_status": "CONFIRMED_UPCOMING",
                                "known_at": "2026-09-01", "evidence_tier": "OFFICIAL_QUALIFIED", "warnings": []}]),
    })
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA", "BBB"},
        financial_analysis_product_context=None, events=events,
    )
    aaa, bbb = artifact["records"]["AAA"], artifact["records"]["BBB"]
    assert len(aaa["risk_evidence"]) == 1
    assert aaa["risk_evidence"][0]["value"] == "CANCELLED"
    assert "RISK" in aaa["case_classes_present"]
    # A qualified, non-adverse event is not risk evidence.
    assert bbb["risk_evidence"] == []
    assert "RISK" not in bbb["case_classes_present"]


def test_routine_boilerplate_warning_is_never_treated_as_risk_evidence():
    """Regression for a self-caught overclassification bug: real retained
    current_official_event_context/v1 evidence stamps a fixed authority-boundary disclaimer into
    EVERY event's ``warnings`` (e.g. "No event impact, probability, score, target, or
    recommendation is derived."). A prior version of this module treated any non-empty
    ``warnings`` as adverse RISK evidence, fabricating RISK on ~65% of the real 2026-09-11
    universe from pure boilerplate. Only a genuinely adverse event_status/event_state counts."""
    events = _events({
        "AAA": _event_record([{
            "event_type": "CASH_DIVIDEND", "event_state": "PAST", "qualification": "EX_DATE_OFFICIAL_QUALIFIED",
            "warnings": ["No event impact, probability, score, target, or recommendation is derived."],
        }]),
    })
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=None, events=events,
    )
    record = artifact["records"]["AAA"]
    assert record["risk_evidence"] == []
    assert "RISK" not in record["case_classes_present"]


def test_counter_thesis_tags_never_duplicate_what_the_fa_v2_decision_annotation_already_tags():
    """security_decision_context._financial_analysis_annotation already turns a negative
    profitability_state/margin_state/balance_sheet_state/cash_conversion_state reading on this
    exact same financial_analysis_product_context record into FA_V2_LOSS_MAKING/FA_V2_MARGIN_
    COMPRESSING/FA_V2_BALANCE_SHEET_DETERIORATING/FA_V2_CASH_CONVERSION_WEAK tags via the separate
    ``financial_analysis`` argument opportunity_context.build_ticker_opportunity already accepts.
    This module's own consumer-facing counter_thesis_evidence tag list must never re-emit those
    four dimensions -- only genuinely additive evidence (here: growth_state)."""
    fa = _fa_context({"AAA": _fa_record(
        profitability_state="LOSS_MAKING", margin_state="MARGIN_COMPRESSING",
        balance_sheet_state="DETERIORATING", cash_conversion_state="WEAK",
    )})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=None,
    )
    record = artifact["records"]["AAA"]
    assert record["counter_thesis_evidence"] == []
    assert len(record["counter_thesis_evidence_detail"]) == 4
    assert "COUNTER" in record["case_classes_present"]


def test_catalysts_are_never_fabricated_here_corporate_event_context_already_owns_them():
    fa = _fa_context({"AAA": _fa_record(profitability_state="PROFITABLE")})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=None,
    )
    record = artifact["records"]["AAA"]
    assert record["catalysts"] == []
    assert record["retained_event_context"] == []
    assert record["catalyst_axis_reason"]
    assert "CATALYST" not in record["case_classes_present"]


def test_technical_invalidation_is_explicitly_absent_tactical_confirmation_boundaries_already_own_it():
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=None, events=None,
    )
    assert artifact["records"]["AAA"]["technical_invalidation"]["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Zero fabrication / zero silent drop / determinism
# ---------------------------------------------------------------------------

def test_missing_evidence_produces_no_fabricated_case_ticker_still_retained():
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA", "ZZZ"},
        financial_analysis_product_context=_fa_context({"AAA": _fa_record(profitability_state="PROFITABLE")}),
        events=None,
    )
    assert set(artifact["records"]) == {"AAA", "ZZZ"}
    zzz = artifact["records"]["ZZZ"]
    assert zzz["case_classes_present"] == []
    assert zzz["supporting_evidence"] == []
    assert zzz["counter_thesis_evidence"] == []
    assert zzz["counter_thesis_evidence_detail"] == []
    assert zzz["risk_evidence"] == []
    assert zzz["fundamental_invalidation"]["status"] == "UNAVAILABLE"
    assert artifact["coverage"]["zero_silent_ticker_drops"] is True
    assert artifact["coverage"]["tickers_with_zero_eligible_cases"] == 1


def test_no_ticker_widening_or_narrowing_beyond_the_supplied_daily_denominator():
    fa = _fa_context({"AAA": _fa_record(profitability_state="PROFITABLE"),
                       "NOT_IN_DAILY": _fa_record(profitability_state="PROFITABLE")})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=None,
    )
    assert set(artifact["records"]) == {"AAA"}


def test_deterministic_identity_same_inputs_same_identity():
    fa = _fa_context({"AAA": _fa_record(profitability_state="PROFITABLE", margin_state="MARGIN_COMPRESSING")})
    events = _events({"AAA": _event_record([{"event_type": "AGM", "event_status": "CANCELLED", "known_at": "2026-09-09"}])})
    first = tcc.build_artifact(as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00",
                               daily_tickers={"AAA"}, financial_analysis_product_context=fa, events=events)
    second = tcc.build_artifact(as_of_session=SESSION, requested_at="2026-09-11T19:30:00+07:00",  # different wall clock
                                daily_tickers={"AAA"}, financial_analysis_product_context=fa, events=events)
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["artifact_sha256"] == second["artifact_sha256"]


def test_identity_excludes_wall_clock_and_has_no_machine_path_or_pid():
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=None, events=None,
    )
    assert "requested_at" not in artifact["artifact_identity"]
    assert "\\" not in artifact["artifact_identity"] and "/" not in artifact["artifact_identity"].split(":", 1)[1]


def test_empty_daily_denominator_raises_rather_than_fabricating_a_record():
    import pytest
    with pytest.raises(tcc.ThesisCaseContextError):
        tcc.build_artifact(as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00",
                           daily_tickers=set(), financial_analysis_product_context=None, events=None)


# ---------------------------------------------------------------------------
# No decision-authority fields anywhere
# ---------------------------------------------------------------------------

def test_no_probability_target_price_expected_return_action_or_sizing_fields():
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=_fa_context({"AAA": _fa_record(profitability_state="PROFITABLE")}),
        events=None,
    )
    blocked = artifact["blocked_outputs"]
    assert blocked["probability_of_success"] == "FORECAST_PROHIBITED"
    assert blocked["target_price"] == "NOT_EMITTED"
    assert blocked["expected_return"] == "NOT_EMITTED"
    assert blocked["action"] == "NOT_EMITTED"
    assert blocked["position_size"] == "NOT_EMITTED"
    assert blocked["universal_thesis_score"] == "SCORING_PROHIBITED"
    record = artifact["records"]["AAA"]
    for key in ("probability", "target_price", "expected_return", "action", "position_size", "score", "rank"):
        assert key not in record


def test_presentation_only_sourced_cases_is_always_zero():
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=_fa_context({"AAA": _fa_record(profitability_state="PROFITABLE")}),
        events=None,
    )
    assert artifact["coverage"]["presentation_only_sourced_cases"] == 0


# ---------------------------------------------------------------------------
# Temporal / lineage semantics
# ---------------------------------------------------------------------------

def test_evidence_preserves_its_own_periodic_as_of_not_the_daily_session():
    fa = _fa_context({"AAA": _fa_record(profitability_state="PROFITABLE", as_of_financial_period="2026-Q1-TTM")})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=None,
    )
    record = artifact["records"]["AAA"]
    assert record["as_of_session"] == SESSION  # the Daily session, at the record level
    assert record["fundamental_invalidation"]["as_of"] == "2026-Q1-TTM"  # the evidence's own period
    assert record["fundamental_invalidation"]["as_of"] != SESSION
    for item in record["supporting_evidence"]:
        assert item["as_of"] == "2026-Q1-TTM"


def test_upstream_lineage_identities_are_retained():
    fa = _fa_context({"AAA": _fa_record(profitability_state="PROFITABLE", lineage_ref="lineage:xyz")})
    events = _events({"AAA": _event_record([])})
    artifact = tcc.build_artifact(
        as_of_session=SESSION, requested_at="2026-09-11T18:00:00+07:00", daily_tickers={"AAA"},
        financial_analysis_product_context=fa, events=events,
    )
    assert artifact["source_artifacts"]["financial_analysis_product_context"] == "fa_v2:1"
    assert artifact["source_artifacts"]["corporate_event_context"] == "evt:1"
    record = artifact["records"]["AAA"]
    assert record["lineage"]["financial_analysis_source_identity"] == "lineage:xyz"
    assert record["lineage"]["corporate_event_source_session"] == "2026-09-10"


# ---------------------------------------------------------------------------
# DAG / circularity safeguards
# ---------------------------------------------------------------------------

def test_module_imports_nothing_downstream_of_the_security_decision():
    forbidden = (
        "security_decision_context", "investment_decision_workspace_projection", "opportunity_context",
        "screener_master_projection", "current_research_scenario_context", "current_evidence_bound_scenario",
        "shadow_security_recommendation", "portfolio_aware_decision",
    )
    for name in forbidden:
        assert not hasattr(tcc, name), f"current_thesis_case_context.py must not import {name}"


def test_build_artifact_signature_has_no_decision_or_workspace_parameters():
    params = set(inspect.signature(tcc.build_artifact).parameters)
    assert params == {"as_of_session", "requested_at", "daily_tickers", "financial_analysis_product_context", "events"}


def test_final_decision_consumes_thesis_cases_without_recursion():
    """Smoke-test the actual downstream wiring: a thesis_cases artifact from this module can be
    fed straight into current_valuation_opportunity_integration.build_artifacts (which in turn
    calls opportunity_context/security_decision_context) with no import cycle and no recursion,
    and its fundamental_invalidation genuinely reaches the decision record."""
    session = SESSION
    watchlist = {"session": session, "artifact_identity": "watch:1",
                 "records": {"AAA": {"entry_state": "BASE_BUILDING", "entry_action": "ACCUMULATE"}}}
    valuation = {"valuation_session": session, "artifact_identity": "val:1", "records": {"AAA": {}}}
    fa = _fa_context({"AAA": _fa_record(profitability_state="PROFITABLE")})
    thesis = tcc.build_artifact(as_of_session=session, requested_at="2026-09-11T18:00:00+07:00",
                                daily_tickers={"AAA"}, financial_analysis_product_context=fa, events=None)
    result = cvoi.build_artifacts(
        as_of_session=session, watchlist=watchlist, valuation=valuation, thesis_cases=thesis,
        requested_at="2026-09-11T18:00:00+07:00",
    )
    decision_record = result["security_decision_context"]["records"]["AAA"]
    assert decision_record["fundamental_invalidation"]["status"] == "READY"
    assert decision_record["fundamental_invalidation"]["thesis_dimension"] == "PROFITABILITY"
