import hashlib
import json

from ai_research_session_delivery import AI_CONTRACT, FULL_UNIVERSE_COMPANION_ROLE, PRIMARY_HUMAN_REVIEW_FILENAME, build_delivery
from current_daily_decision_research_product import OWNER_FOCUS_TICKERS, WATCHLIST, ABSENT_OWNER_FOCUS_STATUS
from owner_research_focus import broader_watchlist, owner_focus_tickers


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


def _card(ticker, action="WAIT"):
    return {
        "ticker": ticker,
        "status": "AVAILABLE",
        "current_decision_state": {
            "entry_action": action,
            "is_actionable": False,
            "entry_action_is_research_label_not_execution_instruction": True,
        },
        "market_flow_positioning": {"status": "UNAVAILABLE", "traded_value": 0.0},
        "valuation_context": {"strict_valuation_status": "UNAVAILABLE"},
    }


def _scoped_operation(missing_owner_focus=()):
    missing = set(missing_owner_focus)
    cards = {ticker: _card(ticker, "BUY_ON_CONFIRMATION") for ticker in OWNER_FOCUS_TICKERS if ticker not in missing}
    cards["QNS"] = _card("QNS", "ACCUMULATE_IN_BASE")
    cards["AAA"] = _card("AAA", "EARLY_ENTRY")
    product = {
        "artifact_identity": "product:1",
        "authority_boundary": {"is_actionable": False, "probability": "UNKNOWN_UNCALIBRATED", "recommendation": "NOT_EMITTED"},
        "market_brief": {"coverage": {"technical": 0}},
        "macro_context": {"status": "UNAVAILABLE"},
        "research_cohorts": {"EARLY_REVERSAL": {"count": 1, "tickers": ["AAA"], "ordering": "TICKER_ASCENDING_NOT_RANKING"}},
        "high_priority_full_universe_review_set": {"count": 1, "tickers": ["AAA"], "meaning": "Candidates for human research, not portfolio/watchlist inclusion."},
        "watchlist": {"cards_available": 11, "tickers": list(WATCHLIST), "role": "BROADER_WATCHLIST_NOT_PORTFOLIO_HOLDINGS", "is_portfolio_holdings": False},
        "owner_focus": {"tickers": list(OWNER_FOCUS_TICKERS), "cards_available": 10 - len(missing), "missing": list(missing), "role": "OWNER_FOCUS_REVIEW_SCOPE", "is_portfolio_holdings": False, "is_actionable": False},
        "aggregate_validation": {"entry_relevant_90_count": 1},
        "detailed_research_cards": cards,
        "risk_data_gap_panel": {"technical_unavailable": 0},
        "what_to_verify_next": ["verify"],
        "source_artifact_identities": {"descriptive": "descriptive:1"},
    }
    if missing:
        for ticker in missing:
            product["detailed_research_cards"][ticker] = {
                "ticker": ticker,
                "status": ABSENT_OWNER_FOCUS_STATUS,
                "current_decision_state": {"entry_action": None, "is_actionable": False, "entry_action_is_research_label_not_execution_instruction": True},
                "is_actionable": False,
            }
    manifest = {
        "market_session": "2026-08-26",
        "operation_identity": "operation:1",
        "producer_head": "producer",
        "consumer_head": "consumer",
        "input_artifacts": {"descriptive": {"artifact_identity": "descriptive:1", "session": "2026-08-26"}},
        "outputs": {"daily_product": "product:1"},
        "warnings": ["warning"],
        "session_coherence": {"session": "2026-08-26"},
        "coverage_summary": {},
    }
    return {"product": product, "manifest": manifest, "peer": {"records": {}}, "scenario": {"records": {}}, "strategy": {"records": {}}, "portfolio_risk": None}


def _scoped_inputs():
    universe = ["AAA", "AAM", "HPG", "PAN", "QNS", "SSI", "ZZZ"]
    return {
        "descriptive": {"records": {ticker: {} for ticker in universe}},
        "tactical": {"records": {ticker: {"entry_state": "WAIT", "entry_action": "WAIT"} for ticker in universe}},
        "fundamental": {"records": {}},
        "valuation": {"records": {}},
        "market_flow_positioning": {"records": {}},
        "corporate_intelligence": {"records": {}},
    }


def test_full_universe_ndjson_is_alphabetical_lookup_only_not_primary():
    delivery = build_delivery(_scoped_operation(), _scoped_inputs())
    rows = [json.loads(line) for line in delivery["full_universe"].splitlines() if line]
    assert [row["ticker"] for row in rows] == ["AAA", "AAM", "HPG", "PAN", "QNS", "SSI", "ZZZ"]
    assert all(row["companion_role"] == FULL_UNIVERSE_COMPANION_ROLE for row in rows)
    assert all(row["not_primary_human_review_input"] is True for row in rows)
    assert all(row["no_alphabetical_sampling"] is True for row in rows)
    manifest = json.loads(delivery["manifest"])
    ndjson = manifest["files"]["ai_research_full_universe.ndjson"]
    assert ndjson["role"] == FULL_UNIVERSE_COMPANION_ROLE
    assert ndjson["not_primary_human_review_input"] is True
    assert ndjson["ordering"] == "TICKER_ASCENDING_DETERMINISTIC_LOOKUP_NOT_SAMPLING"
    assert manifest["recommended_ai_inputs"]["arbitrary_ticker_lookup"] == "ai_research_full_universe.ndjson"
    assert hashlib.sha256(delivery["full_universe"]).hexdigest() == ndjson["sha256"]


def test_primary_human_review_artifact_is_session_bundle():
    delivery = build_delivery(_scoped_operation(), _scoped_inputs())
    primary = json.loads(delivery["primary"])
    manifest = json.loads(delivery["manifest"])
    brief = delivery["brief"].decode("utf-8")
    assert primary["artifact_role"] == "PRIMARY_NORMAL_HUMAN_REVIEW_INPUT"
    assert manifest["primary_bundle_filename"] == PRIMARY_HUMAN_REVIEW_FILENAME
    assert manifest["recommended_ai_inputs"]["normal_human_review"] == PRIMARY_HUMAN_REVIEW_FILENAME
    assert "UPLOAD THIS" in brief and PRIMARY_HUMAN_REVIEW_FILENAME in brief
    assert "DO NOT USE AS PRIMARY" in brief and "ai_research_full_universe.ndjson" in brief


def test_analysis_scope_lists_all_owner_focus_tickers_and_preserves_watchlist():
    primary = json.loads(build_delivery(_scoped_operation(), _scoped_inputs())["primary"])
    scope = primary["analysis_scope"]
    assert scope["owner_focus_tickers"] == list(owner_focus_tickers())
    assert scope["owner_focus_tickers"] == ["SSI", "HPG", "PAN", "EVF", "VNM", "FPT", "PVD", "NVL", "POW", "PNJ"]
    assert scope["mandatory_owner_focus_coverage_count"] == 10
    assert scope["broader_watchlist"] == list(broader_watchlist())
    assert "QNS" in scope["broader_watchlist"]
    assert "QNS" not in scope["owner_focus_tickers"]
    assert scope["is_portfolio_holdings"] is False
    assert scope["grants_investment_authority"] is False
    assert scope["review_order"] == "OWNER_FOCUS_REVIEW_REQUIRED_BEFORE_MARKET_DISCOVERY"
    assert scope["no_alphabetical_sampling"] is True
    assert scope["full_universe_companion_role"] == FULL_UNIVERSE_COMPANION_ROLE
    assert "AAA" in primary["ticker_research_contexts"]
    assert all(ticker in primary["ticker_research_contexts"] for ticker in OWNER_FOCUS_TICKERS)


def test_owner_focus_is_not_portfolio_holdings():
    primary = json.loads(build_delivery(_scoped_operation(), _scoped_inputs())["primary"])
    assert primary["authority_boundary"]["owner_focus_is_not_portfolio_holdings"] is True
    assert primary["research_cohorts"]["watchlist"]["is_portfolio_holdings"] is False
    assert primary["research_cohorts"]["owner_focus"]["is_portfolio_holdings"] is False
    assert primary["portfolio_risk"]["status"] == "NO_EXPLICIT_PORTFOLIO_SUPPLIED"


def test_primary_bundle_carries_owner_focus_cards_and_explicit_absence():
    present = json.loads(build_delivery(_scoped_operation(), _scoped_inputs())["primary"])
    assert [row["ticker"] for row in present["owner_focus_research_contexts"]] == list(OWNER_FOCUS_TICKERS)
    assert all(row["status"] == "AVAILABLE" for row in present["owner_focus_research_contexts"])
    assert present["analysis_scope"]["coverage"]["owner_focus_missing"] == []
    assert present["analysis_scope"]["coverage"]["owner_focus_context_count"] == 10
    absent = json.loads(build_delivery(_scoped_operation(missing_owner_focus=("HPG",)), _scoped_inputs())["primary"])
    missing = [row for row in absent["owner_focus_research_contexts"] if row["ticker"] == "HPG"]
    assert missing and missing[0]["status"] == ABSENT_OWNER_FOCUS_STATUS
    assert "HPG" in absent["analysis_scope"]["coverage"]["owner_focus_missing"]
    assert "HPG" in absent["ticker_research_contexts"]
    assert absent["ticker_research_contexts"]["HPG"]["status"] == ABSENT_OWNER_FOCUS_STATUS


def test_no_alphabetical_sampling_and_entry_action_are_tactical_labels_not_recommendations():
    delivery = build_delivery(_scoped_operation(), _scoped_inputs())
    primary = json.loads(delivery["primary"])
    brief = delivery["brief"].decode("utf-8")
    manifest = json.loads(delivery["manifest"])
    assert primary["no_alphabetical_sampling"] is True
    assert primary["analysis_scope"]["no_alphabetical_sampling"] is True
    assert primary["entry_action_is_research_label_not_execution_instruction"] is True
    assert primary["is_actionable"] is False
    assert primary["authority_boundary"]["entry_action_is_research_label_not_execution_instruction"] is True
    assert primary["authority_boundary"]["recommendation"] == "NOT_EMITTED"
    assert manifest["entry_action_is_research_label_not_execution_instruction"] is True
    assert "tactical research-state labels, not recommendations" in brief
    assert "No alphabetical sampling" in brief
    assert "BUY_ON_CONFIRMATION" in brief
    blob = json.dumps(primary)
    assert "target_price" not in blob
    assert primary["authority_boundary"].get("recommendation") != "BUY"
