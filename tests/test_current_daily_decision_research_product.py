import json
from pathlib import Path

from current_daily_decision_research_product import build, content_identity, markdown
from export_ai_bundle import attach_current_daily_decision_research_product


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


def test_markdown_is_a_compact_human_review_product_not_recommendation_text():
    brief = markdown(build(**_inputs()))
    assert "## Market brief" in brief and "## Detailed research cards" in brief
    assert "Candidate means human research candidate only" in brief
    assert "Human review required; no sizing or execution instruction." in brief
    assert "most likely" not in brief.lower()


def test_opt_in_attach_passes_card_from_single_product_artifact():
    path = OPERATIONS / "current-daily-decision-research-product-v2-20260824/current_daily_decision_research_product_artifact.json"
    bundle = {"ABB": {}}
    attach_current_daily_decision_research_product(bundle, True, str(path))
    card = bundle["ABB"]["current_daily_decision_research"]
    assert card["source_artifact_identity"].startswith("current_daily_decision_research_product:")
    assert card["current_decision_state"]["entry_action"] == "EARLY_ENTRY"
