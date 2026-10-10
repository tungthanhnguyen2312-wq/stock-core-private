import copy

import pytest

import stocklookup_core.decision.current_research_decision_input as dimension
import stocklookup_core.decision.integrated_investment_decision_product as product
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery


def decision(*, state="INFORMATIONAL_ONLY", fitness="AVAILABLE", session="2026-09-30"):
    return product.build_ticker_integrated_decision(
        ticker="TEST", as_of_session="2026-09-30", tactical_record=None, financial_record=None,
        valuation_record=None, relative_volume_record=None, market_sector_record=None,
        corporate_intelligence_record={"research_session": session, "state": state, "fitness": fitness,
                                       "blockers": ["SOURCE_BLOCKER"], "event_identities": ["event:retained"],
                                       "material_event_count": 1})


def test_no_qualified_event_is_absence_without_negative_evidence_or_global_block():
    record = decision(state="NO_QUALIFIED_CORPORATE_EVENT", fitness="NO_QUALIFIED_CORPORATE_EVENT")
    cell = record["current_research_decision_input"]["dimensions"]["CORPORATE"]
    assert cell["state"] == dimension.BLOCKED and cell["authority"] == dimension.NO_AUTHORITY
    assert "CORPORATE" not in record["current_research_decision_input"]["synthesis"]["exact_or_qualified_dimensions"]
    assert cell["reason_codes"] == ["NO_QUALIFIED_CORPORATE_EVENT", "SOURCE_BLOCKER"]
    assert record["counter_thesis"] == decision()["counter_thesis"]
    assert record["research_action_posture"] == decision()["research_action_posture"]


def test_unresolved_classification_retains_descriptive_evidence_without_qualification():
    record = decision(state="UNRESOLVED_EVIDENCE")
    cell = record["current_research_decision_input"]["dimensions"]["CORPORATE"]
    assert cell["state"] == dimension.PARTIAL and cell["authority"] == dimension.CURRENT_DESCRIPTIVE_ONLY
    assert "SOURCE_BLOCKER" in cell["reason_codes"]
    assert "CORPORATE_EVENT_CLASSIFICATION_UNRESOLVED" in cell["reason_codes"]
    assert record["corporate_intelligence_context"]["event_identities"] == ["event:retained"]


@pytest.mark.parametrize("session,temporal", [(None, "SOURCE_SESSION_ABSENT_OR_INVALID"),
                                             ("invalid", "SOURCE_SESSION_ABSENT_OR_INVALID"),
                                             ("2026-10-01", "FUTURE_INFORMATION_PROHIBITED")])
def test_missing_invalid_or_future_evidence_cannot_claim_current_qualification(session, temporal):
    record = decision(session=session)
    cell = record["current_research_decision_input"]["dimensions"]["CORPORATE"]
    assert cell["state"] == dimension.BLOCKED
    assert cell["authority"] == dimension.NO_AUTHORITY
    assert cell["temporal_status"] == temporal
    assert temporal in cell["reason_codes"]


@pytest.mark.parametrize("state", ["INFORMATIONAL_ONLY", "CATALYST_PRESENT", "RISK_PRESENT", "MIXED_EVIDENCE"])
def test_real_current_classified_evidence_retains_existing_research_qualification(state):
    cell = decision(state=state)["current_research_decision_input"]["dimensions"]["CORPORATE"]
    assert cell["state"] == dimension.AVAILABLE and cell["authority"] == dimension.RESEARCH_QUALIFIED
    assert cell["temporal_status"] == "CURRENT_EVIDENCE_SESSION"


def test_stale_information_is_partial_without_relabelling_or_changing_decision_identity():
    record = decision(session="2026-09-05")
    cell = record["current_research_decision_input"]["dimensions"]["CORPORATE"]
    assert cell["state"] == dimension.PARTIAL and cell["authority"] == dimension.RESEARCH_QUALIFIED
    assert cell["temporal_status"] == "STALE_EVIDENCE_SESSION"
    stripped = copy.deepcopy(record)
    stripped.pop("current_research_decision_input")
    assert product.decision_identity(stripped) == record["decision_identity"]
    view = project_integrated_decision_for_ai_delivery(record)
    assert view["current_research_decision_input"]["dimensions"]["CORPORATE"] == cell
    assert view["is_actionable"] is False


def test_unavailable_source_fitness_does_not_gain_qualification_from_a_state_name():
    cell = decision(fitness="UNAVAILABLE")["current_research_decision_input"]["dimensions"]["CORPORATE"]
    assert cell["state"] == dimension.BLOCKED
    assert "CORPORATE_SOURCE_FITNESS_UNAVAILABLE" in cell["reason_codes"]
