"""Regression coverage for the retained current official-market projection."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from current_official_market_universe import build_artifact, replay


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "operations-review"
PATHS = {
    "hnx": OPS / "hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260824/hnx_enumerable_universe_artifact.json",
    "hose": OPS / "hose-public-xhr-and-periodic-series-recon-v1-20260824-reconciled/hose_public_xhr_artifact.json",
    "status": OPS / "current-universe-status-and-session-coverage-resolution-v1-20260823/current_universe_status_and_session_coverage_resolution_artifact.json",
    "descriptive": OPS / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json",
    "screening": OPS / "current-market-screening-opportunity-comparison-foundation-v1-20260823/current_market_screening_opportunity_comparison_foundation_artifact.json",
    "tactical": OPS / "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
    "strategy": OPS / "polymorphic-current-strategy-classification-v1-20260824/polymorphic_current_strategy_classification_artifact.json",
    "scenario": OPS / "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
}


@lru_cache(maxsize=1)
def _build():
    return build_artifact(**{name: json.loads(path.read_text(encoding="utf-8")) for name, path in PATHS.items()})


def test_exact_current_master_reconciliation_and_consumer_filters():
    artifact = _build()
    reconciliation = artifact["reconciliation"]
    assert reconciliation["stocklookup_universe_count"] == 1683
    assert reconciliation["official_hnx_upcom_match"] + reconciliation["official_hose_match"] == reconciliation["official_total_match"]
    assert reconciliation["official_total_match"] + reconciliation["stocklookup_only_unresolved"] == 1683
    assert len(artifact["records"]) == 1683 + reconciliation["official_only_not_in_stocklookup"]
    assert artifact["consumer_compatibility"]["breadth"]["after"]["denominator"] == reconciliation["official_total_match"]
    assert artifact["consumer_compatibility"]["screening"]["after"]["data_ready"] == artifact["consumer_compatibility"]["screening"]["before"]["data_ready"]
    assert artifact["fitness_for_use"]["HISTORICAL_PIT_UNIVERSE"] == "BLOCKED_NOT_CONSTRUCTED"
    replay(artifact)


def test_projection_is_deterministic_and_detects_tampering():
    first = _build()
    assert first["artifact_identity"] == _build()["artifact_identity"]
    tampered = dict(first)
    tampered["reconciliation"] = {**first["reconciliation"], "official_total_match": 0}
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        replay(tampered)
