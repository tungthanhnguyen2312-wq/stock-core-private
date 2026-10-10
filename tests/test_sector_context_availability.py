import pytest

import stocklookup_core.decision.integrated_investment_decision_product as product
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


def decision(sector):
    market = {"market": {"current_breadth_state": "MIXED_BREADTH"}, "ticker_contexts": {}}
    if sector is not None:
        market["ticker_contexts"]["TEST"] = {"sector_leadership_context": sector,
            "coverage_limitations": ["SECTOR_CONTEXT_DATA_LIMITED"] if sector.get("status") == "DATA_LIMITED" else []}
    return product.build_ticker_integrated_decision(ticker="TEST", as_of_session="2026-09-30",
        tactical_record=None, financial_record=None, valuation_record=None,
        relative_volume_record=None, market_sector_record=market,
        producer_artifact_identities={"market_sector": "sector:qualified"})


@pytest.mark.parametrize("sector,status,reason", [
    (None, "UNAVAILABLE", "SECTOR_LEADERSHIP_CONTEXT_NOT_PROVIDED"),
    ({"status": "UNAVAILABLE", "reason": "NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT"}, "UNAVAILABLE", "NO_CURRENT_EXACT_SESSION_TECHNICAL_CONTEXT"),
    ({"status": "DATA_LIMITED", "group_key": "entity|securities"}, "DATA_LIMITED", "SECTOR_CONTEXT_DATA_LIMITED"),
    ({"status": "UNAVAILABLE", "leadership_state": "LEADING"}, "UNAVAILABLE", "SECTOR_LEADERSHIP_UNAVAILABLE"),
    ({"status": "STALE_BUT_RESEARCH_USABLE", "leadership_state": "LEADING"}, "STALE_BUT_RESEARCH_USABLE", "SECTOR_LEADERSHIP_STALE_BUT_RESEARCH_USABLE"),
    ({"status": "BLOCKED", "leadership_state": "LEADING", "reason": "FUTURE_SESSION_PROHIBITED"}, "BLOCKED", "FUTURE_SESSION_PROHIBITED"),
])
def test_absence_or_upstream_gate_never_becomes_neutral_or_leading(sector, status, reason):
    record = decision(sector)
    summary = record["market_sector_context"]
    axis = record["evidence_axes"]["MARKET_SECTOR"]
    assert summary["sector_leadership"] == "UNKNOWN"
    assert summary["sector_leadership_status"] == status
    assert reason in summary["sector_leadership_reason_codes"]
    assert axis["state"] == summary["market_regime"] == "MIXED_BREADTH"
    assert axis["fitness"] == "PARTIAL"
    assert reason in axis["blocker_reason_codes"]
    assert axis["lineage"]["source_artifact_identity"] == "sector:qualified"
    assert record["research_action_posture"] == decision({"status": "AVAILABLE", "leadership_state": "MIXED"})["research_action_posture"]
    delivered = project_integrated_decision_for_ai_delivery(record)
    assert delivered["evidence_axes"]["MARKET_SECTOR"] == axis
    assert delivered["is_actionable"] is False


@pytest.mark.parametrize("state", ["LEADING", "MIXED", "WEAKENING"])
def test_qualified_leadership_keeps_its_group_basis_and_coverage(state):
    record = decision({"status": "AVAILABLE", "leadership_state": state,
        "group_key": "PROVIDER_DESCRIPTIVE_CLASSIFICATION|retained|industry", "group_coverage_ratio": 0.56})
    summary = record["market_sector_context"]
    axis = record["evidence_axes"]["MARKET_SECTOR"]
    assert summary["sector_leadership"] == state
    assert axis["fitness"] == "AVAILABLE"
    assert axis["context"]["sector_group_key"] == summary["sector_group_key"]
    assert axis["context"]["sector_group_coverage_ratio"] == 0.56
    assert axis["blocker_reason_codes"] == []
