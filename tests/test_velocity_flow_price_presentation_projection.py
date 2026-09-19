"""Focused tests for velocity_flow_price_presentation_projection.py.

Covers the synthetic-fixture invariants (fail-closed, no fabrication, cohort membership
independent of data availability) plus a real-artifact acceptance pass against the actual
retained 2026-09-18 multi_session_signal_velocity/v1.2 and flow_price_divergence_shadow/v1
artifacts, so this presentation layer is proven against genuine evidence, not only fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import velocity_flow_price_presentation_projection as bridge

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-18"
VELOCITY_PATH = ROOT / "operations-review" / "multi-session-signal-velocity-v1.2" / SESSION / "multi_session_signal_velocity_artifact.json"
FLOW_PRICE_PATH = ROOT / "operations-review" / "flow-price-divergence-shadow-v1" / SESSION / "flow_price_divergence_shadow_artifact.json"
OWNER_FOCUS_PATH = ROOT / "config" / "owner_research_focus.json"


def _velocity_artifact(records):
    return {"contract_version": bridge.SIGNAL_VELOCITY_CONTRACT_VERSION, "records": records, "artifact_identity": "multi_session_signal_velocity:test"}


def _velocity_record(ticker, session, *, overall="STABLE", quality="COMPLETE_RETAINED_EVIDENCE"):
    trajectory = {
        "valid_observation_count": 5, "retained_session_span": {"first": "2026-09-10", "last": session},
        "continuity_state": "CONTIGUOUS_RETAINED_OBSERVATIONS", "latest_transition": "IMPROVING",
        "persistence": "IMPROVEMENT_PERSISTENT", "acceleration_state": "NOT_EVALUABLE_CATEGORICAL_ONLY",
    }
    return {
        "ticker": ticker, "session": session, "overall_transition_state": overall,
        "evidence_quality": {"state": quality},
        "axes": {"structural_repair": {"trajectory": trajectory}},
        "independent_supporting_axes": ["structural_repair"], "contradicting_axes": [],
    }


def _flow_price_artifact(records):
    return {"contract_version": bridge.FLOW_PRICE_CONTRACT_VERSION, "records": records, "artifact_identity": "flow_price_divergence_shadow:test"}


def _flow_price_record(ticker, *, relationship="FLOW_PRICE_MIXED", session=SESSION):
    return {
        "ticker": ticker, "reference_session": session,
        "flow": {"state": "NET_FOREIGN_BUY", "persistence": "MIXED_FLOW", "latest_qualified_flow_session": session, "freshness": {"status": "current"}},
        "price": {"state": "PRICE_MIXED", "velocity_state": "MIXED_TRANSITION", "participation_context": "PARTICIPATION_NEUTRAL", "market_support": "SUPPORTIVE", "sector_support": "MIXED"},
        "relationship": relationship,
        "evidence_quality": "COMPLETE_RETAINED_EVIDENCE",
        "session_alignment": {"state": "EXACT_SESSION_ALIGNED"},
        "limitations": ["QUALIFIED_FOREIGN_VALUE_ONLY"],
    }


# ---------------------------------------------------------------------------
# Cohort membership
# ---------------------------------------------------------------------------

def test_cohort_tickers_from_owner_focus_reads_broader_watchlist():
    owner_focus = {"broader_watchlist": ["hpg", "VNM"]}
    assert bridge.cohort_tickers_from_owner_focus(owner_focus) == frozenset({"HPG", "VNM"})


def test_cohort_tickers_from_owner_focus_missing_input_is_empty():
    assert bridge.cohort_tickers_from_owner_focus(None) == frozenset()


# ---------------------------------------------------------------------------
# Signal Velocity -- fail-closed / no fabrication
# ---------------------------------------------------------------------------

def test_signal_velocity_no_artifact_supplied_is_insufficient_evidence():
    view = bridge.signal_velocity_view(ticker="HPG", artifact=None, as_of_session=SESSION)
    assert view["overall_transition_state"] == "INSUFFICIENT_EVIDENCE"
    assert view["evidence_quality"] == "INSUFFICIENT_RETAINED_EVIDENCE"
    assert view["reason_code"] == "SIGNAL_VELOCITY_ARTIFACT_NOT_SUPPLIED_OR_UNSUPPORTED_CONTRACT"


def test_signal_velocity_wrong_contract_version_rejected():
    artifact = {"contract_version": "multi_session_signal_velocity/v1.1", "records": []}
    view = bridge.signal_velocity_view(ticker="HPG", artifact=artifact, as_of_session=SESSION)
    assert view["overall_transition_state"] == "INSUFFICIENT_EVIDENCE"


def test_signal_velocity_never_substitutes_an_older_session_record():
    artifact = _velocity_artifact([_velocity_record("HPG", "2026-09-17")])
    view = bridge.signal_velocity_view(ticker="HPG", artifact=artifact, as_of_session=SESSION)
    assert view["overall_transition_state"] == "INSUFFICIENT_EVIDENCE"
    assert view["reason_code"] == "NO_RETAINED_VELOCITY_RECORD_FOR_EXACT_SESSION"


def test_signal_velocity_passthrough_of_real_record_fields():
    artifact = _velocity_artifact([_velocity_record("HPG", SESSION, overall="PERSISTENT_IMPROVEMENT")])
    view = bridge.signal_velocity_view(ticker="HPG", artifact=artifact, as_of_session=SESSION)
    assert view["overall_transition_state"] == "PERSISTENT_IMPROVEMENT"
    assert view["valid_observation_count"] == 5
    assert view["retained_session_span"] == {"first": "2026-09-10", "last": SESSION}
    assert view["continuity_state"] == "CONTIGUOUS_RETAINED_OBSERVATIONS"
    assert view["acceleration_state"] == "NOT_EVALUABLE_CATEGORICAL_ONLY"
    assert view["independent_supporting_axes"] == ["structural_repair"]
    assert view["is_actionable"] is False


# ---------------------------------------------------------------------------
# Flow-Price -- cohort membership is independent of data availability
# ---------------------------------------------------------------------------

def test_flow_price_cohort_member_with_no_artifact_still_flagged_in_cohort():
    view = bridge.flow_price_view(ticker="HPG", artifact=None, cohort_tickers=frozenset({"HPG"}))
    assert view["cohort_membership"] == bridge.IN_COHORT
    assert view["relationship"] == "FLOW_UNAVAILABLE"


def test_flow_price_non_member_is_outside_cohort():
    view = bridge.flow_price_view(ticker="AAA", artifact=None, cohort_tickers=frozenset({"HPG"}))
    assert view["cohort_membership"] == bridge.OUTSIDE_COHORT
    assert view["relationship"] == "FLOW_UNAVAILABLE"


def test_flow_price_never_forces_a_relationship_not_present_in_the_input():
    artifact = _flow_price_artifact([_flow_price_record("HPG", relationship="FOREIGN_BUYING_PRICE_WEAKNESS")])
    view = bridge.flow_price_view(ticker="HPG", artifact=artifact, cohort_tickers=frozenset({"HPG"}))
    assert view["relationship"] == "FOREIGN_BUYING_PRICE_WEAKNESS"
    assert view["cohort_membership"] == bridge.IN_COHORT
    assert view["evidence_quality"] == "COMPLETE_RETAINED_EVIDENCE"


def test_flow_price_missing_ticker_record_is_unavailable_not_zero():
    artifact = _flow_price_artifact([_flow_price_record("HPG")])
    view = bridge.flow_price_view(ticker="VNM", artifact=artifact, cohort_tickers=frozenset({"HPG", "VNM"}))
    assert view["relationship"] == "FLOW_UNAVAILABLE"
    assert view["reason_code"] == "NO_RETAINED_FLOW_PRICE_RECORD_FOR_TICKER"
    assert view["cohort_membership"] == bridge.IN_COHORT


# ---------------------------------------------------------------------------
# Real-artifact acceptance: genuine 2026-09-18 retained evidence, not fixtures.
# ---------------------------------------------------------------------------

pytestmark_real = pytest.mark.skipif(
    not (VELOCITY_PATH.is_file() and FLOW_PRICE_PATH.is_file() and OWNER_FOCUS_PATH.is_file()),
    reason="real retained 2026-09-18 artifacts not present in this checkout",
)


@pytestmark_real
def test_real_persistent_improvement_ticker_projects_correctly():
    artifact = json.loads(VELOCITY_PATH.read_text(encoding="utf-8"))
    view = bridge.signal_velocity_view(ticker="HHP", artifact=artifact, as_of_session=SESSION)
    assert view["overall_transition_state"] == "PERSISTENT_IMPROVEMENT"
    assert view["evidence_quality"] is not None
    assert view["acceleration_state"] == "NOT_EVALUABLE_CATEGORICAL_ONLY"


@pytestmark_real
def test_real_deteriorating_ticker_projects_correctly():
    artifact = json.loads(VELOCITY_PATH.read_text(encoding="utf-8"))
    view = bridge.signal_velocity_view(ticker="AAA", artifact=artifact, as_of_session=SESSION)
    assert view["overall_transition_state"] == "DETERIORATING"


@pytestmark_real
def test_real_flow_price_cohort_member_is_honestly_unavailable_today():
    """CORRECTED (FLOW_PRICE_CANONICAL_SOURCE_BACKFILL_AND_PRESENTATION_CORRECTIVE_V1): this
    file (`operations-review/flow-price-divergence-shadow-v1/2026-09-18/`) is a genuine retained
    PRE-LIVE historical snapshot -- 0 evaluable relationships is correct FOR THIS SNAPSHOT, and it
    is deliberately preserved immutably rather than overwritten (PHASE 6). It is NOT the real
    current state: the live 11-ticker DNSE acquisition was subsequently run and independently
    reproduces (see test_canonical_current_product_projections.py's operation-linked regression
    test) a real 7 MIXED / 2 buying-weakness / 2 selling-weakness distribution. Presentation now
    resolves that live evidence dynamically (canonical_current_product_projections.
    materialize_current_flow_price_divergence_shadow), never this static file -- this test only
    proves the *projection layer* still degrades this one pre-live snapshot honestly if it were
    ever handed to it directly."""
    flow_artifact = json.loads(FLOW_PRICE_PATH.read_text(encoding="utf-8"))
    owner_focus = json.loads(OWNER_FOCUS_PATH.read_text(encoding="utf-8"))
    cohort = bridge.cohort_tickers_from_owner_focus(owner_focus)
    assert "HPG" in cohort
    view = bridge.flow_price_view(ticker="HPG", artifact=flow_artifact, cohort_tickers=cohort)
    assert view["cohort_membership"] == bridge.IN_COHORT
    assert view["relationship"] == "FLOW_UNAVAILABLE"


@pytestmark_real
def test_real_flow_price_non_cohort_ticker_is_outside_scope_not_missing():
    flow_artifact = json.loads(FLOW_PRICE_PATH.read_text(encoding="utf-8"))
    owner_focus = json.loads(OWNER_FOCUS_PATH.read_text(encoding="utf-8"))
    cohort = bridge.cohort_tickers_from_owner_focus(owner_focus)
    assert "AAA" not in cohort
    view = bridge.flow_price_view(ticker="AAA", artifact=flow_artifact, cohort_tickers=cohort)
    assert view["cohort_membership"] == bridge.OUTSIDE_COHORT


@pytestmark_real
def test_real_flow_relationship_distribution_has_no_evaluable_category_today():
    """This locks in that the specific PRE-LIVE historical snapshot at FLOW_PRICE_PATH stays
    exactly what it was when retained (0 evaluable) -- it must never be silently overwritten to
    look like a later live result. The real, currently evaluable 7/2/2 distribution lives in the
    dynamically-rebuilt operation-linked artifact, not in this file; see
    test_canonical_current_product_projections.py for that coverage."""
    flow_artifact = json.loads(FLOW_PRICE_PATH.read_text(encoding="utf-8"))
    relationships = {row.get("relationship") for row in flow_artifact.get("records", [])}
    assert relationships == {"FLOW_UNAVAILABLE"}
