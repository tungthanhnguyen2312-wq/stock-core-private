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
    # The latest session is read from the governed ledger, never inferred from the wall clock.
    assert resolve_latest_registered_completed_session(_registry()) == "2026-08-26"


def test_completed_session_gate_refuses_incomplete_session():
    registry = copy.deepcopy(_registry())
    registry["completed_sessions"]["2026-08-21"]["status"] = "INTRADAY"
    with pytest.raises(DailyProducerError, match="SESSION_COMPLETION_NOT_PROVED"):
        completed_session_gate(registry, "2026-08-21", now=datetime(2026, 8, 24, 16, 0, tzinfo=VN_TZ))


# --- Same-day completed-session gate: session > local date is always refused; a session
# equal to the local date is refused or accepted purely by the explicit governed
# completed_sessions ledger, never by wall-clock/"market should be closed" inference. ---

def test_gate_A_future_session_refused_even_with_complete_looking_evidence():
    """A session strictly after local date must refuse regardless of ledger content --
    proves the date check is not merely skipped once evidence exists."""
    registry = copy.deepcopy(_registry())
    registry["completed_sessions"]["2026-08-26"] = {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}
    with pytest.raises(DailyProducerError, match="TARGET_NOT_STRICTLY_BEFORE_LOCAL_DATE"):
        completed_session_gate(registry, "2026-08-26", now=datetime(2026, 8, 25, 16, 0, tzinfo=VN_TZ))


def test_gate_B_same_day_without_completed_evidence_refused():
    """Same local date with no ledger entry, or an entry not yet proved complete, must
    still refuse -- same-day is never granted merely by matching the wall clock."""
    registry = copy.deepcopy(_registry())
    registry["completed_sessions"].pop("2026-08-26", None)
    registry["sessions"].pop("2026-08-26", None)
    now = datetime(2026, 8, 26, 16, 0, tzinfo=VN_TZ)
    with pytest.raises(DailyProducerError, match="SESSION_NOT_GOVERNED_COMPLETED"):
        completed_session_gate(registry, "2026-08-26", now=now)

    registry["completed_sessions"]["2026-08-26"] = {"status": "INTRADAY", "trading_day_valid": True}
    with pytest.raises(DailyProducerError, match="SESSION_COMPLETION_NOT_PROVED"):
        completed_session_gate(registry, "2026-08-26", now=now)

    registry["completed_sessions"]["2026-08-26"] = {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": False}
    with pytest.raises(DailyProducerError, match="TRADING_DAY_NOT_VALIDATED"):
        completed_session_gate(registry, "2026-08-26", now=now)


def test_gate_C_same_day_with_explicit_completed_evidence_accepted():
    """The one behavior this fix adds: a same-local-date session with a governed
    COMPLETED_RETAINED_EVIDENCE + trading_day_valid=True record must PASS, not refuse."""
    registry = copy.deepcopy(_registry())
    registry["completed_sessions"]["2026-08-25"] = {
        "status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True,
        "completion_evidence": {"basis": "EXACT_SESSION_UPSTREAM_ARTIFACT_REGISTRY"},
    }
    gate = completed_session_gate(registry, "2026-08-25", now=datetime(2026, 8, 25, 18, 30, tzinfo=VN_TZ))
    assert gate["status"] == "PASS"
    assert gate["target_session"] == "2026-08-25"
    assert gate["completion_status"] == "COMPLETED_RETAINED_EVIDENCE"


def test_gate_D_prior_day_completed_session_behavior_unchanged():
    """A strictly-prior-day session with governed evidence must still PASS exactly as
    before this fix (session > local_date is False either way for a prior day)."""
    gate = completed_session_gate(_registry(), "2026-08-21", now=datetime(2026, 8, 25, 9, 0, tzinfo=VN_TZ))
    assert gate["status"] == "PASS"
    assert resolve_latest_registered_completed_session(_registry()) == "2026-08-26"


def test_gate_E_same_day_gate_pass_does_not_bypass_exact_session_input_coherence():
    """Passing the date/evidence gate for a same-day session must not by itself make an
    incoherent or missing exact-session input set acceptable -- resolve_inputs/
    validate_coherence remain independent, composed fail-closed checks (mirrors
    test_malformed_retained_artifact_and_source_session_mismatch_fail_closed, but pinned
    to a same-day gate PASS to prove the two checks were not accidentally merged)."""
    registry = copy.deepcopy(_registry())
    registry["completed_sessions"]["2026-08-25"] = {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True}
    registry["sessions"].pop("2026-08-26", None)
    gate = completed_session_gate(registry, "2026-08-25", now=datetime(2026, 8, 25, 18, 30, tzinfo=VN_TZ))
    assert gate["status"] == "PASS"

    with pytest.raises(ValueError, match="SESSION_NOT_REGISTERED_EXPLICIT_INPUT_MANIFEST_REQUIRED"):
        resolve_inputs(ROOT, "2026-08-26", registry)

    inputs, _ = resolve_inputs(ROOT, "2026-08-21", _registry())
    inputs["tactical"]["session"] = "2026-08-20"
    with pytest.raises(ValueError, match="SESSION_COHERENCE_MISMATCH"):
        validate_coherence(inputs, "2026-08-21")


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
