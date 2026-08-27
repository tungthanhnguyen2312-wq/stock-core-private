import json

from ai_research_session_delivery import AI_CONTRACT, build_delivery


def _operation():
    product = {"artifact_identity": "product:1", "authority_boundary": {"is_actionable": False, "probability": "UNKNOWN_UNCALIBRATED"}, "market_brief": {"coverage": {"technical": 0}}, "macro_context": {"status": "UNAVAILABLE"}, "research_cohorts": {"EARLY_REVERSAL": {"count": 1, "tickers": ["AAA"]}}, "high_priority_full_universe_review_set": {"count": 1, "tickers": ["AAA"]}, "watchlist": {"cards_available": 1, "tickers": ["AAA"]}, "aggregate_validation": {"entry_relevant_90_count": 1}, "detailed_research_cards": {"AAA": {"ticker": "AAA", "current_decision_state": {"entry_action": "WAIT", "is_actionable": False}, "market_flow_positioning": {"status": "UNAVAILABLE", "traded_value": 0.0}, "valuation_context": {"strict_valuation_status": "UNAVAILABLE"}}}, "risk_data_gap_panel": {"technical_unavailable": 0}, "what_to_verify_next": ["verify"] , "source_artifact_identities": {"descriptive": "descriptive:1"}}
    manifest = {"market_session": "2026-08-21", "operation_identity": "operation:1", "producer_head": "producer", "consumer_head": "consumer", "input_artifacts": {"descriptive": {"artifact_identity": "descriptive:1", "session": "2026-08-21"}}, "outputs": {"daily_product": "product:1"}, "warnings": ["warning"], "session_coherence": {"session": "2026-08-21"}, "coverage_summary": {}}
    return {"product": product, "manifest": manifest, "peer": {"records": {"AAA": {"status": "AVAILABLE"}}}, "scenario": {"records": {"AAA": {"probability_status": "UNKNOWN_UNCALIBRATED"}}}, "strategy": {"records": {"AAA": {"strategies": []}}}, "portfolio_risk": None}


def test_valuation_handoff_preserves_research_proxy_versus_authoritative_unavailable():
    from ai_research_session_delivery import _valuation_handoff
    row = {
        "price_input": {"status": "PRICE_READY", "session": "2026-08-26"},
        "share_basis_input": {"status": "PROVIDER_REPORTED_LAGGED"},
        "financial_input": {"authority": "PROVIDER_RESEARCH"},
        "metrics": {
            "market_cap": {"status": "RESEARCH_USABLE", "labels": ["CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE"], "blocked_reasons": [], "first_blocker": None},
            "P/E": {"status": "BLOCKED", "labels": [], "blocked_reasons": ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"], "first_blocker": "FINANCIAL_FACT_MISSING"},
        },
        "shadow_proxy_valuation": {
            "authority_tier": "SHADOW_RESEARCH_ONLY",
            "share_basis_type": "PROVIDER_ISSUED_SHARE_PROXY",
            "metrics": {"proxy_market_cap": {"status": "SHADOW_PROXY_READY", "labels": ["SHADOW", "NOT_COMMON_OUTSTANDING_SHARE_BASIS"]}},
        },
        "value_strategy": {"status": "BLOCKED"},
    }
    handoff = _valuation_handoff(row)
    assert handoff["metrics"]["market_cap"]["authority_note"] == "RESEARCH_PROXY_VALUATION_AVAILABLE_NOT_AUTHORITATIVE"
    assert handoff["metrics"]["P/E"]["authority_note"] == "AUTHORITATIVE_VALUATION_UNAVAILABLE"
    assert handoff["research_proxy_is_not_a_value_judgment"] is True
    assert handoff["is_actionable"] is False
    blob = json.dumps(handoff)
    assert '"BUY"' not in blob and '"SELL"' not in blob
    assert "target_price" not in blob
    operation = _operation()
    inputs = {
        "descriptive": {"records": {"AAA": {}}},
        "tactical": {"records": {"AAA": {"entry_state": "WAIT"}}},
        "fundamental": {"records": {"AAA": None}},
        "valuation": {"records": {"AAA": row}},
        "market_flow_positioning": {"records": {"AAA": {"traded_value": 0.0}}},
        "corporate_intelligence": {"records": {"AAA": {"status": "NO_RETAINED_INTELLIGENCE"}}},
    }
    universe = json.loads(build_delivery(operation, inputs)["full_universe"])
    assert universe["valuation_context"]["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert universe["valuation_context"]["metrics"]["P/E"]["first_blocker"] == "FINANCIAL_FACT_MISSING"


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
