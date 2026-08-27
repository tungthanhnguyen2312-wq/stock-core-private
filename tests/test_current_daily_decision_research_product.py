import json
from pathlib import Path

from current_daily_decision_research_product import (
    ABSENT_OWNER_FOCUS_STATUS,
    OWNER_FOCUS_TICKERS,
    WATCHLIST,
    build,
    content_identity,
    markdown,
)
from export_ai_bundle import attach_current_daily_decision_research_product
from polymorphic_current_strategy_classification import build as build_strategy


ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "operations-review"


def _inputs():
    paths = {
        "descriptive": "market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json",
        "tactical": "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
        "peer_relative": "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json",
        "fundamental": "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json",
        "valuation": "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json",
        "scenario": "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
        "triage": "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json",
        "corporate_intelligence": "market-wide-current-corporate-intelligence-v1-20260824/market_wide_current_corporate_intelligence_artifact.json",
    }
    return {name: json.loads((OPERATIONS / path).read_text(encoding="utf-8")) for name, path in paths.items()}


def test_product_is_deterministic_and_reuses_existing_cohorts():
    product = build(**_inputs())
    assert content_identity(product)["artifact_sha256"] == product["artifact_sha256"]
    assert product["market_brief"]["source_market_session"] == "2026-08-21"
    assert product["research_cohorts"]["EARLY_REVERSAL"]["count"] == 30
    assert product["research_cohorts"]["BREAKOUT_CONFIRMATION"]["count"] == 40
    assert product["high_priority_full_universe_review_set"]["count"] == 47
    assert product["aggregate_validation"]["entry_relevant_90_count"] == 90


def test_cards_preserve_tactical_peer_scenario_and_human_review_boundaries():
    product = build(**_inputs()); card = product["detailed_research_cards"]["ABB"]
    assert card["current_decision_state"]["entry_state"] == "EARLY_REVERSAL_CANDIDATE"
    assert card["current_decision_state"]["entry_action"] == "EARLY_ENTRY"
    assert card["scenario"]["probability_status"] == "UNKNOWN_UNCALIBRATED"
    assert card["current_decision_state"]["requires_human_review"] is True
    assert card["current_decision_state"]["position_sizing_status"] == "NOT_EVALUATED"
    assert all(claim["type"] in {"FACT", "INFERENCE", "DATA_GAP", "QUESTION_TO_VERIFY"} for group in card["thesis_counter_thesis"].values() for claim in group)
    assert card["corporate_intelligence_context"]["status"] == "NO_RETAINED_INTELLIGENCE"
    assert product["detailed_research_cards"]["HPG"]["corporate_intelligence_context"]["confirmed"][0]["status"] == "EXECUTED"
    assert "No retained corporate intelligence" not in product["detailed_research_cards"]["HPG"]["corporate_intelligence_context"]["what_to_verify"][0]


def test_markdown_is_a_compact_human_review_product_not_recommendation_text():
    brief = markdown(build(**_inputs()))
    assert "## Market brief" in brief and "## Detailed research cards" in brief
    assert "Candidate means human research candidate only" in brief
    assert "Human review required; no sizing or execution instruction." in brief
    assert "most likely" not in brief.lower()


def test_product_shows_deterministic_strategy_fit_without_turning_it_into_action():
    inputs = _inputs()
    strategy = build_strategy(descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=inputs["peer_relative"], fundamental=inputs["fundamental"], valuation=inputs["valuation"], scenario=inputs["scenario"], corporate_intelligence=inputs["corporate_intelligence"])
    product = build(**inputs, strategy_classification=strategy)
    hpg = product["detailed_research_cards"]["HPG"]["strategy_fit"]
    assert hpg["is_actionable"] is False and hpg["source_artifact_identity"] == strategy["artifact_identity"]
    assert next(item for item in hpg["strategies"] if item["strategy_id"] == "EVENT_DRIVEN")["status"] == "ELIGIBLE"


def test_owner_focus_is_distinct_from_broader_watchlist_and_not_holdings():
    product = build(**_inputs())
    assert list(WATCHLIST) == ["EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM"]
    assert list(OWNER_FOCUS_TICKERS) == ["SSI", "HPG", "PAN", "EVF", "VNM", "FPT", "PVD", "NVL", "POW", "PNJ"]
    assert product["watchlist"]["tickers"] == list(WATCHLIST)
    assert "QNS" in product["watchlist"]["tickers"]
    assert "QNS" not in product["owner_focus"]["tickers"]
    assert product["watchlist"]["is_portfolio_holdings"] is False
    assert product["owner_focus"]["is_portfolio_holdings"] is False
    assert product["owner_focus"]["is_actionable"] is False
    assert product["authority_boundary"]["entry_action_is_research_label_not_execution_instruction"] is True
    assert product["authority_boundary"]["owner_focus_is_not_portfolio_holdings"] is True
    for ticker in OWNER_FOCUS_TICKERS:
        assert ticker in product["detailed_research_cards"]
        card = product["detailed_research_cards"][ticker]
        assert card["current_decision_state"]["entry_action_is_research_label_not_execution_instruction"] is True
        assert card["is_actionable"] is False


def test_absent_owner_focus_ticker_is_explicit_never_silently_dropped():
    inputs = _inputs()
    inputs["tactical"]["records"].pop("HPG", None)
    product = build(**inputs)
    card = product["detailed_research_cards"]["HPG"]
    assert card["status"] == ABSENT_OWNER_FOCUS_STATUS
    assert "HPG" in product["owner_focus"]["missing"]
    assert product["owner_focus"]["tickers"][1] == "HPG"
    assert "QNS" in product["watchlist"]["tickers"]


def test_opt_in_attach_passes_card_from_single_product_artifact():
    path = OPERATIONS / "current-daily-decision-research-product-v2-20260824/current_daily_decision_research_product_artifact.json"
    bundle = {"ABB": {}}
    attach_current_daily_decision_research_product(bundle, True, str(path))
    card = bundle["ABB"]["current_daily_decision_research"]
    assert card["source_artifact_identity"].startswith("current_daily_decision_research_product:")
    assert card["current_decision_state"]["entry_action"] == "EARLY_ENTRY"
