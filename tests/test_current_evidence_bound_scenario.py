import json
from pathlib import Path

from current_evidence_bound_scenario import build, content_identity
from export_ai_bundle import attach_current_evidence_bound_scenario


ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "operations-review"


def _inputs():
    paths = {
        "descriptive": "market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json",
        "tactical": "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
        "peer_relative": "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json",
        "fundamental": "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json",
        "valuation": "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json",
        "triage": "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json",
        "catalyst": "catalyst-event-research-context-v1-20260820/catalyst_event_research_context_artifact.json",
        "screening": "current-market-screening-opportunity-comparison-foundation-v1-20260823/current_market_screening_opportunity_comparison_foundation_artifact.json",
    }
    return {name: json.loads((OPERATIONS / path).read_text(encoding="utf-8")) for name, path in paths.items()}


def test_current_scenarios_are_deterministic_conditional_and_full_universe():
    artifact = build(**_inputs())
    assert content_identity(artifact)["artifact_sha256"] == artifact["artifact_sha256"]
    assert artifact["coverage"]["universe_count"] == 1683
    assert all(record["probability_status"] == "UNKNOWN_UNCALIBRATED" for record in artifact["records"].values())
    assert all(record["is_actionable"] is False for record in artifact["records"].values())
    assert all(set(("bear_case", "base_case", "bull_case")) <= set(record) for record in artifact["records"].values())


def test_validation_cohorts_and_existing_tactical_boundaries_are_preserved():
    artifact = build(**_inputs())
    validation = artifact["validation"]
    assert len(validation["watchlist"]) == 11
    assert len(validation["preopen_47"]) == 47
    assert len(validation["entry_relevant_90"]) == 90
    assert set(validation["representative_scenarios"]) == {"EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING", "BREAKOUT_READY", "UPTREND_CONFIRMED", "DISTRIBUTION_RISK", "DOWNTREND"}
    assert artifact["records"]["HPG"]["confirmation_trigger"] == _inputs()["tactical"]["records"]["HPG"]["confirmation_trigger"]


def test_opt_in_bundle_attach_keeps_current_scenario_verbatim():
    path = OPERATIONS / "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json"
    bundle = {"HPG": {}}
    attach_current_evidence_bound_scenario(bundle, True, str(path))
    record = bundle["HPG"]["current_evidence_bound_scenario"]
    assert record["source_artifact_identity"].startswith("current_evidence_bound_scenario:")
    assert record["bull_case"]["probability_status"] == "UNKNOWN_UNCALIBRATED"
