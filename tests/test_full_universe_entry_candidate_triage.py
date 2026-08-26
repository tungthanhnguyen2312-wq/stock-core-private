import json
from pathlib import Path

import pytest

from full_universe_entry_candidate_triage import (
    ENTRY_RELEVANT_STATES,
    FullUniverseEntryCandidateTriageError,
    build,
    content_identity,
    replay,
)
from market_wide_current_descriptive_research import content_identity as descriptive_identity
from current_market_screening_opportunity_comparison_foundation import content_identity as screening_identity
from watchlist_tactical_entry_classifier import content_identity as tactical_identity

ROOT = Path(__file__).resolve().parents[1]
POSTCLOSE = ROOT / "operations-review/full-universe-entry-candidate-triage-postclose-20260824/full_universe_entry_candidate_triage_20260824.json"


def _stamp(payload, identity_fn):
    return {**payload, **identity_fn(payload)}


def _descriptive(session, records):
    payload = {"session": session, "records": records, "contract_version": "market_wide_current_descriptive_research/v1"}
    return _stamp(payload, descriptive_identity)


def _screening(session, records, descriptive_id):
    payload = {
        "session": session,
        "records": records,
        "input_lineage": {"current_descriptive_artifact_identity": descriptive_id},
        "contract_version": "current_market_screening_and_opportunity_comparison_foundation/v1",
    }
    return _stamp(payload, screening_identity)


def _tactical(session, records, descriptive_id, screening_id):
    payload = {
        "session": session,
        "records": records,
        "source_artifacts": {"descriptive": descriptive_id, "screening": screening_id},
        "contract_version": "watchlist_tactical_entry_classifier/v1",
    }
    return _stamp(payload, tactical_identity)


def _tech(close, ma20, mom, rvol, ret, vol):
    return {
        "status": "SHADOW_ONLY",
        "is_current_session": True,
        "values": {"close": close, "ma_20": ma20, "momentum_20d": mom, "relative_volume_provider_scoped": rvol, "return_1d": ret, "volatility_20d": vol},
    }


def _fixture():
    desc_records = {
        "AAA": {"technical_features": _tech(10.2, 10.0, 0.1, 1.4, 0.01, 0.01)},
        "BBB": {"technical_features": _tech(9.0, 10.0, -0.02, 0.8, -0.01, 0.04)},
        "CCC": {"technical_features": _tech(11.0, 10.0, 0.05, 1.5, 0.02, 0.02)},
    }
    descriptive = _descriptive("2026-08-25", desc_records)
    screen_records = {
        "AAA": {
            "market_relative_comparison": {"status": "AVAILABLE", "momentum_bucket": "UPPER_QUARTILE", "relative_volume_bucket": "UPPER_MIDDLE", "relative_volume_cohort_median": 1.0},
            "sector_relative_comparison": {"status": "AVAILABLE", "momentum_bucket": "UPPER_MIDDLE", "classification_label": "corporate"},
        },
        "BBB": {
            "market_relative_comparison": {"status": "AVAILABLE", "momentum_bucket": "LOWER_MIDDLE", "relative_volume_bucket": "LOWER_QUARTILE", "relative_volume_cohort_median": 1.0},
            "sector_relative_comparison": {"status": "AVAILABLE", "momentum_bucket": "LOWER_QUARTILE", "classification_label": "corporate"},
        },
        "CCC": {
            "market_relative_comparison": {"status": "AVAILABLE", "momentum_bucket": "UPPER_QUARTILE", "relative_volume_bucket": "UPPER_QUARTILE", "relative_volume_cohort_median": 1.0},
            "sector_relative_comparison": {"status": "AVAILABLE", "momentum_bucket": "UPPER_QUARTILE", "classification_label": "corporate"},
        },
    }
    screening = _screening("2026-08-25", screen_records, descriptive["artifact_identity"])
    tactical_records = {
        "AAA": {"entry_state": "BREAKOUT_READY", "entry_action": "BUY_ON_CONFIRMATION", "horizon": "NEXT_SESSION_WATCH", "ticker_structure_state": "NEAR_MA20_NEUTRAL", "evidence_for": ["up"], "evidence_against": [], "confirmation_trigger": "extend", "invalidation": "ma20", "data_quality": {"liquidity_status": "ELIGIBLE", "technical_eligible": True, "is_current_session": True}},
        "BBB": {"entry_state": "BASE_BUILDING", "entry_action": "ACCUMULATE_IN_BASE", "horizon": "MULTI_WEEK", "ticker_structure_state": "BASE", "evidence_for": [], "evidence_against": [], "confirmation_trigger": None, "invalidation": None, "data_quality": {"liquidity_status": "ELIGIBLE", "technical_eligible": True, "is_current_session": True}},
        "CCC": {"entry_state": "EARLY_REVERSAL_CANDIDATE", "entry_action": "EARLY_ENTRY", "horizon": "SHORT", "ticker_structure_state": "REVERSAL", "evidence_for": [], "evidence_against": [], "confirmation_trigger": None, "invalidation": None, "data_quality": {"liquidity_status": "UNAVAILABLE", "technical_eligible": True, "is_current_session": True}},
        "DDD": {"entry_state": "UPTREND_CONFIRMED", "entry_action": "WAIT", "data_quality": {"liquidity_status": "ELIGIBLE"}},
    }
    tactical = _tactical("2026-08-25", tactical_records, descriptive["artifact_identity"], screening["artifact_identity"])
    fundamental = {"records": {
        "AAA": {"authority_tier": "PROVIDER_RESEARCH", "entity_class": "corporate", "fundamental_trajectory_context": {"available_dimension_count": 1, "earnings_direction": None, "data_limitations": ["provider_scoped_research_only_not_official_qualified"]}},
    }}
    return descriptive, screening, tactical, fundamental


def test_high_priority_rule_and_entry_relevant_states_only():
    descriptive, screening, tactical, fundamental = _fixture()
    artifact = build(descriptive=descriptive, screening=screening, tactical=tactical, fundamental=fundamental, session="2026-08-25")
    replay(artifact)
    assert artifact["source_market_session"] == "2026-08-25"
    assert set(artifact["all_entry_relevant_records"]) == set(ENTRY_RELEVANT_STATES)
    tickers = {row["ticker"] for rows in artifact["all_entry_relevant_records"].values() for row in rows}
    assert tickers == {"AAA", "BBB", "CCC"}
    assert "DDD" not in tickers
    hp = [row["ticker"] for row in artifact["high_priority_review_eligible_records"]]
    assert hp == ["AAA"]
    bbb = artifact["all_entry_relevant_records"]["BASE_BUILDING"][0]
    assert bbb["ticker"] == "BBB"
    assert bbb["high_priority_review_eligible"] is False
    assert "SECTOR_LOWER_QUARTILE" in bbb["high_priority_exclusion_reasons"]
    ccc = artifact["all_entry_relevant_records"]["EARLY_REVERSAL_CANDIDATE"][0]
    assert "LIQUIDITY_NOT_ELIGIBLE" in ccc["high_priority_exclusion_reasons"]
    assert artifact["preopen_review_set"] == artifact["high_priority_review_eligible_records"]
    assert "AAA" in artifact["cohorts"]["BREAKOUT_CONFIRMATION_REVIEW"]
    assert "CCC" in artifact["cohorts"]["EARLY_REVERSAL_RETURN_VOLUME_CONFIRMING"]
    assert "BBB" in artifact["cohorts"]["TACTICAL_WEAK_RELATIVE_CONTEXT"]
    assert "CCC" in artifact["cohorts"]["TACTICAL_DATA_LIMITED"]
    assert "AAA" in artifact["cohorts"]["TACTICAL_WITH_FUNDAMENTAL_SUPPORT"]


def test_session_mismatch_fails_closed():
    descriptive, screening, tactical, fundamental = _fixture()
    tactical = {**tactical, "session": "2026-08-24", **tactical_identity({**tactical, "session": "2026-08-24"})}
    with pytest.raises(FullUniverseEntryCandidateTriageError, match="TRIAGE_SESSION_COHERENCE_MISMATCH"):
        build(descriptive=descriptive, screening=screening, tactical=tactical, fundamental=fundamental, session="2026-08-25")


def test_replay_governed_2026_08_24_postclose_identity():
    retained = json.loads(POSTCLOSE.read_text(encoding="utf-8"))
    assert retained["source_market_session"] == "2026-08-24"
    ops = ROOT / "operations-review"
    descriptive = json.loads((ops / "market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json").read_text(encoding="utf-8"))
    screening = json.loads((ops / "current-market-screening-opportunity-comparison-foundation-v1-20260824/current_market_screening_opportunity_comparison_foundation_artifact.json").read_text(encoding="utf-8"))
    tactical = json.loads((ops / "watchlist-tactical-entry-decision-v1-20260824/watchlist_tactical_entry_classifier_artifact.json").read_text(encoding="utf-8"))
    fundamental = json.loads((ops / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json").read_text(encoding="utf-8"))
    rebuilt = build(descriptive=descriptive, screening=screening, tactical=tactical, fundamental=fundamental, session="2026-08-24")
    replay(rebuilt)
    assert rebuilt["artifact_identity"] == retained["artifact_identity"]
    assert rebuilt["coverage"] == retained["coverage"]
    assert rebuilt["cohort_counts"] == retained["cohort_counts"]
    assert rebuilt["cohorts"] == retained["cohorts"]
