"""Synthetic engine-to-consumer acceptance; no providers, runtime or private data."""
from __future__ import annotations

import copy
import runpy
from pathlib import Path

import pytest

import personal_investment_decision_action_center as ac
import asymmetric_dislocation_research as asymmetric
import daily_opportunity_decision_queue as queue
from stocklookup_core.decision import current_opportunity_prioritization as priority
from stocklookup_core.decision import integrated_investment_decision_product as iid

SESSION = "2026-08-28"
HELPERS = runpy.run_path(str(Path(__file__).with_name("test_integrated_investment_decision_product.py")))
WATCHLIST_HELPERS = runpy.run_path(str(Path(__file__).with_name("test_watchlist_tactical_entry_classifier.py")))
WATCHLIST_HELPERS["_build"].__globals__["SESSION"] = SESSION
WATCHLIST = WATCHLIST_HELPERS["_build"]()[-1]["records"]

# Input scenarios use the existing classifiers; no new phase/action policy lives here.
SCENARIOS = [
    ("downtrend", "DWN", {"market_structure_state": "DOWNTREND", "ma20_slope_state": "FALLING"}, "AVOID"),
    ("stabilization", "EAS", {"market_structure_state": "DOWNTREND", "ma20_slope_state": "FLAT"}, "AVOID"),
    ("base", "BAS", {"market_structure_state": "SIDEWAYS", "base_status": "IN_BASE", "range_state": "RANGE_STABLE"}, "EARLY_WATCH"),
    ("early_reversal", "REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL", "choch_state": "BULLISH_CHOCH_DETECTED_BY_RULE"}, "EARLY_WATCH"),
    ("uptrend", "UPT", {}, "WAIT_FOR_CONFIRMATION"),
    ("breakout_attempt", "BRK", {"breakout_state_v3": "TESTING_PIVOT", "trigger_state": "APPROACHING"}, "WAIT_FOR_CONFIRMATION"),
    ("breakout_confirmed", "BRK", {"breakout_state_v3": "BREAKOUT", "trigger_state": "TRIGGERED"}, "INITIATE_ON_BREAKOUT"),
    ("failed_breakout", "DST", {"breakout_state_v3": "FAILED_BREAKOUT"}, "WAIT_FOR_CONFIRMATION"),
    ("weak_market", "BRK", {"breakout_state_v3": "BREAKOUT", "trigger_state": "TRIGGERED"}, "WAIT_FOR_CONFIRMATION"),
    ("absent_fundamentals", "REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL"}, "EARLY_WATCH"),
    ("stale_fundamentals", "REV", {"market_structure_state": "EARLY_BULLISH_REVERSAL"}, "EARLY_WATCH"),
    ("insufficient_technical", "THN", {"eligible": False, "market_structure_state": "INSUFFICIENT_HISTORY"}, "WAIT_FOR_CONFIRMATION"),
]


def scenario_inputs():
    records, sources, priority_records = {}, {}, {}
    for index, (name, watch_ticker, changes, _) in enumerate(SCENARIOS):
        ticker = f"S{index:02d}"
        watch = WATCHLIST[watch_ticker]
        tactical = HELPERS["_sample_tactical_record"](breakout_state_v3="NO_VALID_PIVOT", trigger_state="NOT_TRIGGERED", bos_state="NO_BOS")
        tactical.update(base_status="NONE", range_state="NONE", as_of_session=SESSION,
                        trigger_close_comparison_operator=">", invalidation_close_comparison_operator="<",
                        price_basis_qualification={"price_basis_verified": True, "research_label": "SYNTHETIC_COMPATIBLE_BASIS", "price_unit": "SYNTHETIC_PRICE_UNIT", "historical_pit_eligible": False})
        tactical.update(changes)
        financial = None if name == "absent_fundamentals" else HELPERS["_sample_financial_record"](as_of_period="2024-Q1" if name == "stale_fundamentals" else "2026-Q2")
        lane_tier = priority._lane_tier("TREND_MOMENTUM", watch, "SCENARIO_READY", {})
        opportunity_row = {
            "priority_tier": lane_tier, "eligible_strategies": ["TREND_MOMENTUM"],
            "lane_priority": {"TREND_MOMENTUM": lane_tier}, "tactical_state": watch["entry_state"],
            "entry_action": watch["entry_action"], "scenario_status": "SCENARIO_READY",
            "event_context_status": "UNAVAILABLE", "fundamental_context_status": "UNAVAILABLE" if financial is None else "SYNTHETIC_RESEARCH",
            "data_quality_status": watch["data_quality"]["confidence"],
            "priority_reasons": [f"TREND_MOMENTUM={lane_tier}"], "blocking_reasons": [],
            "invalidation_or_context_warnings": watch["data_quality"].get("warnings", []),
            "content_identity": f"synthetic:priority:{ticker}", "source_input_identities": {"tactical": "synthetic:watchlist"},
        }
        priority_records[ticker] = opportunity_row
        sources[ticker] = (name, watch, tactical, financial)
    queued = queue.build(opportunity={"records": priority_records, "coverage": {"current_official_universe": 12}, "research_session": SESSION, "artifact_identity": "synthetic:priority"}, triage={"records": {}, "artifact_identity": "synthetic:triage"})
    for ticker, (name, watch, tactical, financial) in sources.items():
        market = {"session": SESSION, "artifact_identity": "synthetic:market", "market": {"session": SESSION, "official_universe_count": 100, "exact_session_observed_count": 100, "missing_current_session_count": 0, "current_breadth_state": "BEARISH"}} if name == "weak_market" else None
        records[ticker] = iid.build_ticker_integrated_decision(
            ticker=ticker, as_of_session=SESSION, tactical_record=tactical, financial_record=financial,
            valuation_record=None, relative_volume_record=None, market_sector_record=market,
            priority_queue_record=queued["records"][ticker], legacy_opportunity_record=watch,
            structural_condition_source_identity="synthetic:structure",
            technical_coverage_disposition_record=HELPERS["_current_disposition"](),
        )
    integrated = {"contract_version": iid.CONTRACT_VERSION, "session": SESSION, "records": records}
    integrated.update(iid.content_identity(integrated))
    coverage = {"session": SESSION, "records": {ticker: {"disposition": "SAME_SESSION_TECHNICAL_COVERED"} for ticker in records}}
    return integrated, coverage, queued


def build(integrated, coverage, *, enabled=True, excluded=frozenset()):
    return ac.build_artifact(session=SESSION, requested_at="synthetic", integrated_decision_artifact=integrated,
        coverage_disposition_artifact=coverage, owner_focus={"owner_focus_tickers": (), "broader_watchlist": tuple(integrated["records"])},
        asymmetric_dislocation_artifact=asymmetric.build_artifact(session=SESSION, integrated_product=integrated),
        include_conditional_research=enabled, excluded_tickers=excluded)


def strip_details(artifact):
    artifact = copy.deepcopy(artifact)
    artifact.pop("conditional_research_presentation", None)
    for row in artifact["portfolio"]["holdings"] + artifact["watchlist"]["entries"] + [r for rows in artifact["discovery"]["lanes"].values() for r in rows]:
        row["evidence"].pop("conditional_research", None)
        for role in ("trigger", "invalidation"):
            row["evidence"][role].pop(role + "_level", None)
            row["evidence"][role].pop("distance_to_" + role + "_pct", None)
    for key in ("artifact_identity", "artifact_sha256"):
        artifact.pop(key, None)
    return artifact


def test_twelve_engine_scenarios_preserve_decisions_and_make_evidence_visible():
    integrated, coverage, queued = scenario_inputs()
    original = copy.deepcopy(integrated)
    baseline, candidate = build(integrated, coverage, enabled=False), build(integrated, coverage)
    assert baseline["artifact_identity"] == "personal_investment_decision_action_center/v1:ad9e9f15b1e26f1ddff4d2783c74fdd55ce7bf67184d06c06bfc6e7e8f3ca97d"
    text = ac.markdown(candidate)
    before = ac.markdown(baseline)
    assert strip_details(candidate) == strip_details(baseline)
    assert integrated == original
    assert candidate["decision_surface_index"] == baseline["decision_surface_index"]
    assert candidate["conditional_research_presentation"]["displayed_ticker_count"] == 12
    for index, (name, _, _, expected_posture) in enumerate(SCENARIOS):
        ticker = f"S{index:02d}"
        source = integrated["records"][ticker]
        assert source["research_action_posture"] == expected_posture, name
        evidence = next(row["evidence"] for row in candidate["watchlist"]["entries"] if row["ticker"] == ticker)
        detail = evidence["conditional_research"]
        assert detail["opportunity_priority"] == source["opportunity_priority"]
        assert source["opportunity_priority"]["research_priority_tier"] == queued["records"][ticker]["research_priority_tier"]
        assert detail["priority_posture_reconciliation"] == source["priority_posture_reconciliation"]
        for role in ("trigger", "invalidation"):
            assert detail[role]["condition"]["source_condition_identity"] == source[role]["condition"]["condition_identity"]
            assert detail[role]["trigger_state"] == source[role]["trigger_state"] if role == "trigger" else detail[role]["invalidation_method"] == source[role]["invalidation_method"]
            assert detail[role]["numeric_display_status"] == ("WITHHELD_UNQUALIFIED_BOUNDARY" if name == "insufficient_technical" else "AVAILABLE")
            assert evidence[role][role + "_level"] == (None if name == "insufficient_technical" else source[role][role + "_level"])
        assert source["why_now"] not in before
        assert source["why_now"] in text
        assert source["decision_identity"] in text
        assert source["trigger"]["condition"]["condition_identity"] in text
    assert "SELLING_PRESSURE_EASING" == WATCHLIST["EAS"]["entry_state"]
    assert "EARLY_REVERSAL_CANDIDATE" == WATCHLIST["REV"]["entry_state"]
    assert "future condition=MACHINE_EVALUABLE" in text
    assert "FIRST_LATER_COMPLETED_SESSION" in text
    assert "BEARISH_BREADTH_NARROWS_FRESH_ENTRY" in text
    assert candidate == build(integrated, coverage)
    assert candidate["artifact_identity"] != baseline["artifact_identity"]


@pytest.mark.parametrize("missing", ["price_basis", "stale_price", "missing_coverage"])
def test_unqualified_numeric_boundaries_do_not_hide_descriptive_setup(missing):
    integrated, coverage, _ = scenario_inputs()
    record = integrated["records"]["S03"]
    if missing == "price_basis":
        for role in ("trigger", "invalidation"):
            record[role]["price_basis"] = {"price_basis_verified": False, "limitations": ["PRICE_BASIS_MISSING_OR_MIXED"]}
        record["decision_identity"] = iid.decision_identity(record)
        integrated.update(iid.content_identity(integrated))
    elif missing == "stale_price":
        coverage["records"]["S03"]["disposition"] = "RAW_SAME_SESSION_PRESENT_TECHNICAL_MATERIALIZATION_MISSING"
    else:
        coverage = None
    candidate = build(integrated, coverage)
    detail = candidate["watchlist"]["entries"][3]["evidence"]["conditional_research"]
    for role in ("trigger", "invalidation"):
        assert detail[role][role + "_level"] is None
        assert detail[role]["condition"]["reference_level"] is None
        assert detail[role]["condition"]["source_condition_identity"] == record[role]["condition"]["condition_identity"]
    assert "EARLY_WATCH" in ac.markdown(candidate)
    assert "WITHHELD_UNQUALIFIED_BOUNDARY" in ac.markdown(candidate)
    assert "PRICE_BASIS_MISSING_OR_MIXED" in ac.markdown(candidate) if missing == "price_basis" else True


def test_missing_session_evidence_cannot_become_a_setup_or_event():
    integrated, coverage, _ = scenario_inputs()
    record = iid.build_ticker_integrated_decision(ticker="NONE", as_of_session=SESSION, tactical_record=None,
        financial_record=None, valuation_record=None, relative_volume_record=None, market_sector_record=None)
    integrated["records"] = {"NONE": record}
    integrated.update(iid.content_identity(integrated))
    candidate = build(integrated, None)
    text = ac.markdown(candidate)
    assert "INSUFFICIENT_CURRENT_RESEARCH" in text
    assert "INSUFFICIENT" == candidate["watchlist"]["entries"][0]["evidence"]["tactical_phase"]
    assert "NOT_MACHINE_EVALUABLE" in text
    assert not any(candidate["discovery"]["lanes"].values())


@pytest.mark.parametrize("corruption", ["session", "record", "decision", "coverage"])
def test_opt_in_rejects_identity_or_temporal_mismatch(corruption):
    integrated, coverage, _ = scenario_inputs()
    if corruption == "session":
        integrated["session"] = "2026-08-27"
    elif corruption == "record":
        integrated["records"]["S03"]["why_now"] = "tampered"
    elif corruption == "decision":
        integrated["records"]["S03"]["decision_identity"] = "tampered"
        integrated.update(iid.content_identity(integrated))
    else:
        coverage["session"] = "2026-08-27"
    with pytest.raises(ac.ActionCenterError):
        ac.build_artifact(session=SESSION, requested_at="synthetic", integrated_decision_artifact=integrated,
            coverage_disposition_artifact=coverage, include_conditional_research=True)


def test_exclusions_and_optional_portfolio_do_not_gain_actions():
    integrated, coverage, _ = scenario_inputs()
    candidate = build(integrated, coverage, excluded=frozenset({"S03"}))
    assert candidate["portfolio"]["status"] == "PRIVATE_PORTFOLIO_NOT_SUPPLIED"
    assert candidate["capital_rotation"]["pairs"] == []
    assert candidate["conditional_research_presentation"]["displayed_ticker_count"] == 11
    assert all(row["ticker"] != "S03" for row in candidate["watchlist"]["entries"])


def test_contradictory_level_is_withheld_without_reinterpreting_trigger_state():
    integrated, coverage, _ = scenario_inputs()
    record = integrated["records"]["S05"]
    record["trigger"]["trigger_level"] = 9999
    record["decision_identity"] = iid.decision_identity(record)
    integrated.update(iid.content_identity(integrated))
    candidate = build(integrated, coverage)
    detail = candidate["watchlist"]["entries"][5]["evidence"]["conditional_research"]
    assert detail["trigger"]["trigger_level"] is None
    assert detail["trigger"]["numeric_display_reason_codes"] == ["CONDITION_AND_BOUNDARY_LEVEL_CONFLICT"]
    assert detail["trigger"]["trigger_state"] == "APPROACHING"
    assert "9999" not in ac.markdown(candidate)


def test_legacy_missing_conditions_are_explicit_and_never_gain_boundaries():
    integrated, coverage, _ = scenario_inputs()
    record = integrated["records"]["S03"]
    for role in ("trigger", "invalidation"):
        record[role].pop("condition")
    record["decision_identity"] = iid.decision_identity(record)
    integrated.update(iid.content_identity(integrated))
    candidate = build(integrated, coverage)
    detail = candidate["watchlist"]["entries"][3]["evidence"]["conditional_research"]
    assert detail["trigger"]["trigger_level"] is None
    assert "CONDITION_NOT_MACHINE_EVALUABLE" in detail["trigger"]["numeric_display_reason_codes"]


def test_existing_retained_resolver_exposes_opt_in_without_a_new_entrypoint(monkeypatch, tmp_path):
    integrated, coverage, _ = scenario_inputs()
    monkeypatch.setattr(ac._pad, "load_integrated_decision_artifact", lambda *_: integrated)
    monkeypatch.setattr(ac, "_load_json", lambda path: coverage if "coverage" in path.name else None)
    monkeypatch.setattr(ac, "_previous_session", lambda *_: None)
    monkeypatch.setattr(ac._pad, "load_governed_sector_snapshot", lambda *_: None)
    monkeypatch.setattr(ac._pad, "resolve_sector_by_ticker", lambda **_: ({}, {}, None))
    monkeypatch.setattr(ac._private_portfolio_context, "portfolio_status", lambda **_: {"status": "NOT_PROVIDED"})
    monkeypatch.setattr(ac._owner_focus, "load_owner_research_focus", lambda: {"owner_focus_tickers": (), "broader_watchlist": tuple(integrated["records"])})
    preview = ac.evaluate_from_retained_artifacts(repo_root=tmp_path, session=SESSION, requested_at="synthetic", include_conditional_research=True)
    assert "PENDING_DEFINED_CONFIRMATION" in ac.markdown(preview)
    assert preview["conditional_research_presentation"]["displayed_ticker_count"] == 12
    assert not list(tmp_path.iterdir())  # Evaluation is read-only; writing stays explicit.


def test_conditional_detail_on_confirmed_holdings_preserves_portfolio_actions():
    integrated, coverage, _ = scenario_inputs()
    args = dict(session=SESSION, requested_at="synthetic", integrated_decision_artifact=integrated,
        coverage_disposition_artifact=coverage, owner_focus={"owner_focus_tickers": (), "broader_watchlist": ()},
        portfolio_aware_decision_artifact={"session": SESSION, "records": {"S03": {
            "position_state": "HELD", "portfolio_action_research": "HOLD_EXISTING_NO_ACTION",
            "security_research_action_posture": "EARLY_WATCH"}}})
    baseline = ac.build_artifact(**args)
    candidate = ac.build_artifact(**args, include_conditional_research=True)
    assert candidate["portfolio"]["holdings"][0]["action"] == baseline["portfolio"]["holdings"][0]["action"]
    assert "conditional_research" in candidate["portfolio"]["holdings"][0]["evidence"]
    assert candidate["capital_rotation"] == baseline["capital_rotation"]
