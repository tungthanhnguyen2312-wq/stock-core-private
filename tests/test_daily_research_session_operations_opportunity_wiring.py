import json
from pathlib import Path

import pytest

from daily_research_session_operations import build_operation, load_registry, materialize, resolve_inputs

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "operations-review"


def test_unregistered_optional_inputs_cannot_be_injected_into_a_prior_session():
    inputs, _ = resolve_inputs(ROOT, "2026-08-21", load_registry(ROOT))
    inputs = dict(inputs)
    inputs["official_universe"] = json.loads((OPS / "current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json").read_text(encoding="utf-8"))
    inputs["event_context"] = json.loads((OPS / "current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="SESSION_INPUT_NOT_REGISTERED"):
        build_operation(inputs, "2026-08-21", producer_head="producer", consumer_head="consumer")


def test_decision_queue_builds_from_registered_same_session_optional_inputs_and_is_deterministic():
    registry = load_registry(ROOT)
    inputs, _ = resolve_inputs(ROOT, "2026-08-24", registry)
    first = build_operation(inputs, "2026-08-24", producer_head="producer", consumer_head="consumer", registry=registry)
    second = build_operation(inputs, "2026-08-24", producer_head="producer", consumer_head="consumer", registry=registry)
    assert first["manifest"]["operation_identity"] == second["manifest"]["operation_identity"]
    assert first["decision_queue"] is not None and first["opportunity"] is not None
    assert first["opportunity"]["coverage"]["current_official_universe"] == 1507
    summary = first["decision_queue"]["entry_relevant_summary"]
    assert 0 < summary["PRIORITY_NOW_TOTAL"] <= 1507
    assert summary["PRIORITY_NOW_ENTRY_RELEVANT"] + summary["PRIORITY_NOW_NOT_ENTRY_RELEVANT"] == summary["PRIORITY_NOW_TOTAL"]
    assert first["manifest"]["outputs"]["daily_opportunity_decision_queue"] == first["decision_queue"]["artifact_identity"]
    assert first["manifest"]["outputs"]["opportunity_decision_prospective_context"] == first["opportunity_snapshot"]["snapshot_id"]
    assert first["opportunity_snapshot"]["cohort_count"] == 1507
    product_summary = first["product"]["research_priority_queue"]
    assert product_summary["full_priority_now_count"] == summary["PRIORITY_NOW_TOTAL"]
    cards = first["product"]["detailed_research_cards"]
    available = [ticker for ticker, card in cards.items() if card["research_priority"]["status"] == "AVAILABLE"]
    assert len(available) == len(cards)


def test_decision_queue_absent_when_optional_inputs_missing_matches_pre_change_behavior():
    inputs, _ = resolve_inputs(ROOT, "2026-08-21", load_registry(ROOT))
    operation = build_operation(inputs, "2026-08-21", producer_head="producer", consumer_head="consumer")
    assert operation["decision_queue"] is None and operation["opportunity"] is None
    assert "opportunity_prioritization" not in operation["manifest"]["outputs"]
    assert "research_priority_queue" not in operation["product"]
    assert operation["product"]["detailed_research_cards"]["ABB"]["research_priority"]["status"] == "NOT_IN_RESEARCH_PRIORITY_QUEUE"


def test_materialize_writes_decision_queue_artifacts_only_when_present(tmp_path):
    registry = load_registry(ROOT)
    inputs, _ = resolve_inputs(ROOT, "2026-08-24", registry)
    operation = build_operation(inputs, "2026-08-24", producer_head="producer", consumer_head="consumer", registry=registry)
    materialize(tmp_path, operation)
    assert (tmp_path / "daily_opportunity_decision_queue_artifact.json").exists()
    assert (tmp_path / "opportunity_prioritization_artifact.json").exists()
    assert (tmp_path / "opportunity_decision_prospective_context.json").exists()


def test_materialize_omits_decision_queue_artifacts_when_absent(tmp_path):
    inputs, _ = resolve_inputs(ROOT, "2026-08-21", load_registry(ROOT))
    operation = build_operation(inputs, "2026-08-21", producer_head="producer", consumer_head="consumer")
    materialize(tmp_path, operation)
    assert not (tmp_path / "daily_opportunity_decision_queue_artifact.json").exists()
    assert not (tmp_path / "opportunity_prioritization_artifact.json").exists()
    assert not (tmp_path / "opportunity_decision_prospective_context.json").exists()
