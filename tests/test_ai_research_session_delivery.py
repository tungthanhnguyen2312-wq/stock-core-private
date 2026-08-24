import json

from ai_research_session_delivery import AI_CONTRACT, build_delivery


def _operation():
    product = {"artifact_identity": "product:1", "authority_boundary": {"is_actionable": False, "probability": "UNKNOWN_UNCALIBRATED"}, "market_brief": {"coverage": {"technical": 0}}, "macro_context": {"status": "UNAVAILABLE"}, "research_cohorts": {"EARLY_REVERSAL": {"count": 1, "tickers": ["AAA"]}}, "high_priority_full_universe_review_set": {"count": 1, "tickers": ["AAA"]}, "watchlist": {"cards_available": 1, "tickers": ["AAA"]}, "aggregate_validation": {"entry_relevant_90_count": 1}, "detailed_research_cards": {"AAA": {"ticker": "AAA", "current_decision_state": {"entry_action": "WAIT", "is_actionable": False}, "market_flow_positioning": {"status": "UNAVAILABLE", "traded_value": 0.0}, "valuation_context": {"strict_valuation_status": "UNAVAILABLE"}}}, "risk_data_gap_panel": {"technical_unavailable": 0}, "what_to_verify_next": ["verify"] , "source_artifact_identities": {"descriptive": "descriptive:1"}}
    manifest = {"market_session": "2026-08-21", "operation_identity": "operation:1", "producer_head": "producer", "consumer_head": "consumer", "input_artifacts": {"descriptive": {"artifact_identity": "descriptive:1", "session": "2026-08-21"}}, "outputs": {"daily_product": "product:1"}, "warnings": ["warning"], "session_coherence": {"session": "2026-08-21"}, "coverage_summary": {}}
    return {"product": product, "manifest": manifest, "peer": {"records": {"AAA": {"status": "AVAILABLE"}}}, "scenario": {"records": {"AAA": {"probability_status": "UNKNOWN_UNCALIBRATED"}}}, "strategy": {"records": {"AAA": {"strategies": []}}}, "portfolio_risk": None}


def test_delivery_is_deterministic_and_preserves_boundaries():
    operation = _operation()
    inputs = {"descriptive": {"records": {"AAA": {}}}, "tactical": {"records": {"AAA": {"entry_state": "WAIT"}}}, "fundamental": {"records": {"AAA": None}}, "valuation": {"records": {"AAA": {"status": "UNAVAILABLE"}}}, "market_flow_positioning": {"records": {"AAA": {"traded_value": 0.0}}}, "corporate_intelligence": {"records": {"AAA": {"status": "NO_RETAINED_INTELLIGENCE"}}}}
    one, two = build_delivery(operation, inputs), build_delivery(operation, inputs)
    assert one == two
    primary = json.loads(one["primary"])
    assert primary["schema_version"] == AI_CONTRACT
    assert primary["authority_boundary"]["is_actionable"] is False
    assert primary["ticker_research_contexts"]["AAA"]["market_flow_positioning"]["traded_value"] == 0.0
    assert json.loads(one["manifest"])["files"]["ai_research_full_universe.ndjson"]["record_count"] == 1
    assert len(one["full_universe"].splitlines()) == 1
