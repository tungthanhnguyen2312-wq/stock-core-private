import copy
from pathlib import Path

import pytest

from daily_research_session_operations import build_operation, load_registry, materialize, resolve_inputs, validate_coherence


ROOT = Path(__file__).resolve().parents[1]


def _resolved():
    return resolve_inputs(ROOT, "2026-08-21", load_registry(ROOT))[0]


def test_explicit_registry_selects_recovered_956_artifact_and_not_stale_763_path():
    inputs = _resolved(); coherence = validate_coherence(inputs, "2026-08-21")
    assert inputs["descriptive"]["artifact_identity"].endswith("8660d4ece155e91895557a0f7b70a6a501ab5ebcee8978818199084a88a6c9b6")
    assert coherence["technical_coverage_semantics"]["same_session_technical_feature_available_count"] == 956
    stale = copy.deepcopy(inputs); stale["descriptive"]["market_breadth"]["same_session_technical_feature_available_count"] = 763
    with pytest.raises(ValueError, match="TECHNICAL_COVERAGE_TACTICAL_CLASSIFIED_MISMATCH"):
        validate_coherence(stale, "2026-08-21")


def test_operation_is_deterministic_and_preserves_current_contracts(tmp_path: Path):
    first = build_operation(_resolved(), "2026-08-21", producer_head="producer", consumer_head="consumer")
    second = build_operation(_resolved(), "2026-08-21", producer_head="producer", consumer_head="consumer")
    assert first["manifest"]["operation_identity"] == second["manifest"]["operation_identity"]
    assert first["product"]["market_brief"]["coverage"]["same_session_technical_feature_available_count"] == 956
    assert first["product"]["watchlist"]["cards_available"] == 11
    assert first["product"]["detailed_research_cards"]["ABB"]["scenario"]["probability_status"] == "UNKNOWN_UNCALIBRATED"
    assert first["snapshot"]["future_outcomes"] == "PENDING_FUTURE_OBSERVATION"
    assert first["corporate_snapshot"]["cohort_count"] == 1683
    assert first["strategy"]["coverage"]["universe_count"] == 1683
    assert first["manifest"]["input_artifacts"]["corporate_intelligence"]["artifact_identity"].startswith("market_wide_current_corporate_intelligence:")
    materialize(tmp_path, first); materialize(tmp_path, second)
    assert (tmp_path / "run_manifest.json").exists()
    assert (tmp_path / "corporate_intelligence_prospective_context.json").exists()
    assert (tmp_path / "strategy_classification_artifact.json").exists()


def test_mismatched_tactical_lineage_fails_closed():
    inputs = _resolved(); broken = copy.deepcopy(inputs)
    broken["tactical"]["source_artifacts"]["descriptive"] = "stale"
    with pytest.raises(ValueError, match="TACTICAL_UPSTREAM_LINEAGE_MISMATCH"):
        validate_coherence(broken, "2026-08-21")
