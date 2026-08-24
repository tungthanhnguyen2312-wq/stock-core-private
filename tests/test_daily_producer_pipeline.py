import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from ai_research_session_delivery import build_delivery
from daily_producer_pipeline import (
    DailyProducerError,
    _verify_delivery,
    _write_immutable,
    build_acquisition_plan,
    completed_session_gate,
    resolve_latest_registered_completed_session,
)
from daily_research_session_operations import load_registry, resolve_inputs, validate_coherence
from vn_time import VN_TZ


ROOT = Path(__file__).resolve().parents[1]


def _registry():
    return load_registry(ROOT)


def test_completed_session_gate_uses_governed_ledger_not_clock_inference():
    gate = completed_session_gate(_registry(), "2026-08-21", now=datetime(2026, 8, 24, 9, 0, tzinfo=VN_TZ))
    assert gate["status"] == "PASS"
    assert gate["completion_status"] == "COMPLETED_RETAINED_EVIDENCE"
    assert resolve_latest_registered_completed_session(_registry()) == "2026-08-21"


def test_completed_session_gate_refuses_incomplete_or_current_session():
    registry = copy.deepcopy(_registry())
    registry["completed_sessions"]["2026-08-24"] = {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}
    with pytest.raises(DailyProducerError, match="TARGET_NOT_STRICTLY_BEFORE_LOCAL_DATE"):
        completed_session_gate(registry, "2026-08-24", now=datetime(2026, 8, 24, 16, 0, tzinfo=VN_TZ))
    registry["completed_sessions"]["2026-08-21"]["status"] = "INTRADAY"
    with pytest.raises(DailyProducerError, match="SESSION_COMPLETION_NOT_PROVED"):
        completed_session_gate(registry, "2026-08-21", now=datetime(2026, 8, 24, 16, 0, tzinfo=VN_TZ))


def test_acquisition_plan_preserves_exact_identities_and_localized_optional_states():
    inputs, entries = resolve_inputs(ROOT, "2026-08-21", _registry())
    plan = build_acquisition_plan(inputs, entries, "2026-08-21")
    rows = {row["input_class"]: row for row in plan["items"]}
    assert rows["descriptive"]["execution_disposition"] == "REUSE_CURRENT_VALID_RETAINED"
    assert rows["descriptive"]["artifact_identity"] == entries["descriptive"]["artifact_identity"]
    assert rows["valuation"]["execution_disposition"] == "BLOCKED"
    assert rows["macro"]["execution_disposition"] == "OPTIONAL_UNAVAILABLE"
    assert rows["market_flow_positioning"]["required_for_core_operation"] is False


def test_malformed_retained_artifact_and_source_session_mismatch_fail_closed():
    malformed = copy.deepcopy(_registry())
    malformed["sessions"]["2026-08-21"]["descriptive"]["path"] = "AGENTS.md"
    with pytest.raises(json.JSONDecodeError):
        resolve_inputs(ROOT, "2026-08-21", malformed)
    inputs, _ = resolve_inputs(ROOT, "2026-08-21", _registry())
    inputs["tactical"]["session"] = "2026-08-20"
    with pytest.raises(ValueError, match="SESSION_COHERENCE_MISMATCH"):
        validate_coherence(inputs, "2026-08-21")


def test_parity_mismatch_fails_closed(tmp_path: Path):
    operation = {
        "product": {"artifact_identity": "product:1", "authority_boundary": {"is_actionable": False}, "market_brief": {}, "macro_context": {}, "research_cohorts": {}, "high_priority_full_universe_review_set": {}, "watchlist": {}, "aggregate_validation": {"entry_relevant_90_count": 0}, "detailed_research_cards": {}, "risk_data_gap_panel": {}, "what_to_verify_next": [], "source_artifact_identities": {}},
        "manifest": {"market_session": "2026-08-21", "operation_identity": "operation:1", "producer_head": "p", "consumer_head": "c", "input_artifacts": {"descriptive": {"artifact_identity": "d:1"}}, "outputs": {}, "warnings": [], "session_coherence": {}, "coverage_summary": {}},
        "peer": {"records": {}}, "scenario": {"records": {}}, "strategy": {"records": {}}, "portfolio_risk": None,
    }
    delivery = build_delivery(operation, {"descriptive": {"records": {}}})
    for name, value in (("ai_research_session_bundle.json", delivery["primary"]), ("ai_research_full_universe.ndjson", delivery["full_universe"]), ("ai_research_bundle_manifest.json", delivery["manifest"]), ("current_decision_cockpit_projection.json", delivery["projection"])):
        (tmp_path / name).write_bytes(value)
    projection = json.loads((tmp_path / "current_decision_cockpit_projection.json").read_text(encoding="utf-8"))
    projection["source"]["product_identity"] = "wrong:identity"
    (tmp_path / "current_decision_cockpit_projection.json").write_text(json.dumps(projection), encoding="utf-8")
    with pytest.raises(DailyProducerError, match="AI_DASHBOARD_PARITY_PRODUCT_MISMATCH"):
        _verify_delivery(operation, tmp_path)


def test_immutable_resume_rejects_conflicting_partial_stage(tmp_path: Path):
    path = tmp_path / "artifact.json"
    _write_immutable(path, b"one\n")
    _write_immutable(path, b"one\n")
    with pytest.raises(DailyProducerError, match="IMMUTABLE_DAILY_PRODUCER_CONTENT_CONFLICT"):
        _write_immutable(path, b"two\n")
