import copy
import hashlib
import json
from datetime import date, timedelta

import pytest

from prospective_decision_outcome_measurement import (
    FIELD_NOT_RETAINED,
    PENDING,
    ProspectiveOutcomeError,
    build_outcome_artifact,
    evaluate_case,
    prospective_outcome_context,
)


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _case(*, t0=None):
    body = {"ticker": "AAA", "known_at": "2026-01-01T16:00:00+07:00", "as_of": "2026-01-01",
            "outcome_measurement_t0": t0 if t0 is not None else _t0()}
    identity = "prospective_research_case:" + _hash(body)
    body["case_id"] = identity
    body["case_content_identity"] = identity
    return {"record_type": "IMMUTABLE_T0_CASE", "case": body, "ai_draft": {"fixture": False}}


def _t0():
    return {
        "completed_session": "2026-01-01", "close": {"close": 100.0, "price_basis_identity": "basis:adjusted-research", "source_identity": "t0-price"},
        "research_stance": "WAIT_FOR_CONFIRMATION", "entry_state": "BASE_BUILDING", "entry_action": "ACCUMULATE_IN_BASE", "setup_tags": ["RANGE_COMPRESSION"],
        "fundamental_state": "PROFITABLE", "valuation_state": "ATTRACTIVE_RELATIVE_RESEARCH",
        "confirmation_boundary": {"role": "confirmation", "boundary_identity": "confirm-1", "kind": "technical", "condition": {"field": "close", "operator": ">=", "value": 102}},
        "invalidation_boundary": {"role": "invalidation", "boundary_identity": "invalidate-1", "kind": "technical", "condition": {"field": "close", "operator": "<=", "value": 99}},
        "benchmark": {"identity": "benchmark:INDEX", "t0_close": {"close": 200.0, "price_basis_identity": "index-basis", "source_identity": "index-t0"}},
    }


def _sessions(count=60):
    origin = date(2026, 1, 1)
    rows = []
    for number in range(1, count + 1):
        session = (origin + timedelta(days=number)).isoformat()
        rows.append({"session": session, "session_identity": "session:" + session,
                     "completed_session_gate": {"completion_gate_status": "READY", "resolved_session": session},
                     "prices": {"AAA": {"close": 100.0 + number, "price_basis_identity": "basis:adjusted-research", "source_identity": "price:" + session}},
                     "benchmarks": {"benchmark:INDEX": {"close": 200.0 + number, "price_basis_identity": "index-basis", "source_identity": "index:" + session}}})
    return rows


def test_completed_session_horizons_returns_close_path_benchmark_and_determinism():
    first = build_outcome_artifact([_case()], _sessions())
    second = build_outcome_artifact([_case()], _sessions())
    assert first == second
    row = first["outcomes"][0]
    assert row["horizons"]["T5"]["future_session"] == "2026-01-06"
    assert row["horizons"]["T5"]["return"] == pytest.approx(.05)
    assert row["horizons"]["T20"]["return"] == pytest.approx(.20)
    assert row["horizons"]["T60"]["return"] == pytest.approx(.60)
    assert row["close_path"]["T5"]["MAX_FAVORABLE_CLOSE_RETURN"] == pytest.approx(.05)
    assert row["close_path"]["T5"]["MAX_ADVERSE_CLOSE_RETURN"] == pytest.approx(.01)
    assert row["close_path"]["T5"]["mfe"] == "UNAVAILABLE_HIGH_LOW_BASIS"
    assert row["benchmark_relative"]["T5"]["return"] == pytest.approx(.025)
    assert row["confirmation"]["status"] == "CONFIRMED"
    assert row["event_ordering"] == "CONFIRMED_ONLY"
    assert first["t0_immutability_verified"] is True


def test_calendar_days_do_not_count_and_missing_future_sessions_are_pending():
    sessions = _sessions(4)
    skipped = copy.deepcopy(sessions[0])
    skipped["session"] = "2026-01-03"  # Calendar date present but not a completed session.
    skipped["completed_session_gate"]["completion_gate_status"] = "TOO_EARLY"
    row = evaluate_case(_case(), sessions + [skipped])
    assert row["horizons"]["T5"]["status"] == PENDING
    assert row["horizons"]["T20"]["status"] == PENDING
    assert row["horizons"]["T60"]["status"] == PENDING


def test_incompatible_basis_is_localized_and_absent_t0_fields_are_not_backfilled():
    sessions = _sessions(20)
    sessions[4]["prices"]["AAA"]["price_basis_identity"] = "basis:other"
    t0 = _t0()
    t0.pop("entry_action")
    row = evaluate_case(_case(t0=t0), sessions)
    assert row["horizons"]["T5"]["status"] == "PRICE_BASIS_INCOMPATIBLE"
    assert row["horizons"]["T20"]["status"] == "MATURE"
    assert row["entry_action_at_t0"] == FIELD_NOT_RETAINED


def test_boundary_absence_event_order_and_fundamental_pending_are_explicit():
    t0 = _t0()
    t0["confirmation_boundary"] = {"role": "confirmation", "boundary_identity": "c", "kind": "technical", "condition": {"field": "close", "operator": ">=", "value": 105}}
    t0["invalidation_boundary"] = {"role": "invalidation", "boundary_identity": "i", "kind": "technical", "condition": {"field": "close", "operator": "<=", "value": 102}}
    row = evaluate_case(_case(t0=t0), _sessions(6))
    assert row["event_ordering"] == "INVALIDATED_BEFORE_CONFIRMED"
    t0.pop("confirmation_boundary")
    t0["invalidation_boundary"] = {"role": "invalidation", "boundary_identity": "f", "kind": "fundamental", "condition": {"field": "earnings", "operator": "<=", "value": 0}}
    row = evaluate_case(_case(t0=t0), _sessions(6))
    assert row["confirmation"]["status"] == "BOUNDARY_NOT_RETAINED_AT_T0"
    assert row["invalidation"]["status"] == "PENDING_NEXT_COMPATIBLE_FINANCIAL_OBSERVATION"


def test_non_case_cannot_be_retroactively_measured_and_product_context_is_compact():
    with pytest.raises(ProspectiveOutcomeError, match="GENUINE_IMMUTABLE_T0_CASE_REQUIRED"):
        evaluate_case({"record_type": "T0_CANDIDATE", "case": {}}, _sessions())
    artifact = build_outcome_artifact([_case()], _sessions(5))
    context = prospective_outcome_context(artifact, artifact["outcomes"][0]["case_id"])
    assert context["contract_version"] == "prospective_outcome_context/v1"
    assert "T20" in context["pending_horizons"]
    group = artifact["cohort_observation_summary"]["groups"][0]
    assert group["OBSERVED_POSITIVE_RATE"]["N"] == 1
    assert "PROBABILITY_OF_SUCCESS" not in group
