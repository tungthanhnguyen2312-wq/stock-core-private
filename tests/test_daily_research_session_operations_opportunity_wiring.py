import json
from pathlib import Path

from daily_research_session_operations import build_operation, load_registry, materialize, resolve_inputs

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "operations-review"


def _resolved_with_opportunity_inputs():
    inputs, _ = resolve_inputs(ROOT, "2026-08-21", load_registry(ROOT))
    inputs = dict(inputs)
    # Test-only combination: official_universe/event_context are "current as of build"
    # (2026-08-24), not session-locked, per their own contracts. Layering them onto the
    # retained 2026-08-21 session inputs here proves the wiring mechanics against real
    # 1,507-scale data without ever materializing to operations-review/ or the session
    # registry -- so it never becomes a claim about a governed 2026-08-21 output (see
    # prospective_research_learning's "no backdated knowledge" boundary).
    inputs["official_universe"] = json.loads((OPS / "current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json").read_text(encoding="utf-8"))
    inputs["event_context"] = json.loads((OPS / "current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json").read_text(encoding="utf-8"))
    return inputs


def test_decision_queue_builds_when_optional_inputs_present_and_is_deterministic():
    # NOTE on the PRIORITY_NOW count seen here: this session's *registered* corporate_intelligence
    # input (coverage.current_event_coverage == 1) predates the 2026-08-24 official-event-context
    # merge, so EVENT_DRIVEN eligibility for this specific registered 2026-08-21 session is smaller
    # than the 190/124-count standalone snapshot produced by tools/run_current_opportunity_prioritization.py
    # (which rebuilds corporate_intelligence fresh with the event context). That is correct, not a
    # bug: this wiring must use the session's own registered corporate_intelligence, never silently
    # rebuild it with evidence the frozen session's registry entry does not carry (see the
    # "no backdated knowledge" boundary in prospective_research_learning.py / this module's own
    # official_universe/event_context comment above). This test therefore checks structure and
    # determinism, not the specific accepted 190 figure (covered separately, against the real
    # standalone snapshot, in test_daily_opportunity_decision_queue.py).
    inputs = _resolved_with_opportunity_inputs()
    first = build_operation(inputs, "2026-08-21", producer_head="producer", consumer_head="consumer")
    second = build_operation(inputs, "2026-08-21", producer_head="producer", consumer_head="consumer")
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
    assert len(available) == len(cards)  # every existing detailed card is within the 1,507 official universe


def test_decision_queue_absent_when_optional_inputs_missing_matches_pre_change_behavior():
    inputs, _ = resolve_inputs(ROOT, "2026-08-21", load_registry(ROOT))
    operation = build_operation(inputs, "2026-08-21", producer_head="producer", consumer_head="consumer")
    assert operation["decision_queue"] is None and operation["opportunity"] is None
    assert "opportunity_prioritization" not in operation["manifest"]["outputs"]
    assert "research_priority_queue" not in operation["product"]
    assert operation["product"]["detailed_research_cards"]["ABB"]["research_priority"]["status"] == "NOT_IN_RESEARCH_PRIORITY_QUEUE"


def test_materialize_writes_decision_queue_artifacts_only_when_present(tmp_path):
    inputs = _resolved_with_opportunity_inputs()
    operation = build_operation(inputs, "2026-08-21", producer_head="producer", consumer_head="consumer")
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
