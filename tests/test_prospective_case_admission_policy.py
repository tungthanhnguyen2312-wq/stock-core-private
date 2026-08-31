import tempfile
from pathlib import Path

import pytest

from durable_prospective_research_case_store import DurableProspectiveResearchCaseStore
from prospective_case_admission_policy import AdmissionPolicyError, apply_admission_policy, material_decision_state_signature, retain_admitted_cases
from prospective_decision_outcome_measurement import build_outcome_artifact, load_genuine_case_envelopes


def _card(ticker, stance, *, entry="BASE_BUILDING"):
    return {"ticker": ticker, "research_stance": stance, "research_stance_readiness": "RESEARCH_CONDITIONAL", "entry_state": entry, "entry_action": "WAIT", "setup_tags": ["RANGE_COMPRESSION"],
            "confirmation": {"status": "READY", "boundary_type": "PRICE_RECLAIM", "source_rule": "R1", "source_metric": "close", "comparison_operator": ">=", "value": 10.0},
            "invalidation": {"technical": {"status": "READY", "boundary_type": "BREAKDOWN", "source_rule": "R1", "source_metric": "close", "comparison_operator": "<=", "value": 8.0}, "fundamental": {"status": "UNAVAILABLE"}},
            "valuation": {"readiness": "UNAVAILABLE", "relative_research_state": "UNAVAILABLE", "supporting_methods": [], "share_basis": "UNAVAILABLE"},
            "fundamental": {"readiness": "UNAVAILABLE", "state": "UNAVAILABLE", "trajectory": "UNAVAILABLE", "research_fitness": "UNAVAILABLE"},
            "liquidity": {"readiness": "LIQUIDITY_RESEARCH_PROXY", "descriptive_research_state": "CURRENT", "exact_execution_capacity_status": "EXECUTION_CAPACITY_EXACT_BLOCKED"},
            "market_sector": {"freshness_status": "CURRENT"}, "catalyst": {"freshness_status": "STALE_BUT_RESEARCH_USABLE"}, "lineage": {"per_axis_freshness": {"tactical": "CURRENT", "fundamental": "UNAVAILABLE"}}}


def _workspace(session="2026-09-01"):
    return {"contract_version": "investment_decision_workspace_projection/v1", "as_of_session": session, "artifact_identity": "workspace:test", "cards": {"AAA": _card("AAA", "INITIATE_RESEARCH_CANDIDATE"), "BBB": _card("BBB", "WAIT_FOR_CONFIRMATION"), "CCC": _card("CCC", "INSUFFICIENT_EVIDENCE")}}


def _prices():
    return {ticker: {"close": 10.0, "price_basis_identity": "basis:current-research", "source_identity": "price:2026-09-01"} for ticker in ("AAA", "BBB", "CCC")}


def test_policy_admits_all_eligible_roles_and_excludes_insufficient_without_liquidity_or_valuation_gates():
    artifact = apply_admission_policy(_workspace(), latest_qualified_completed_session="2026-09-01", price_evidence=_prices(), admitted_at="2026-09-01T19:00:00+07:00")
    assert artifact["coverage"]["decision_denominator"] == 3
    assert artifact["coverage"]["admission_status"] == {"ADMITTED": 2, "INSUFFICIENT_EVIDENCE_NOT_ADMITTED": 1}
    roles = {item["ticker"]: item.get("case_role") for item in artifact["decisions"]}
    assert roles == {"AAA": "ACTIVE_RESEARCH_THESIS", "BBB": "WATCH_FOR_CONFIRMATION", "CCC": None}
    assert artifact["decisions"][0]["case"]["outcome_measurement_t0"]["liquidity_research_state"]["exact_execution_capacity_status"] == "EXECUTION_CAPACITY_EXACT_BLOCKED"


def test_stale_projection_is_refused_and_signature_ignores_lineage_formatting():
    with pytest.raises(AdmissionPolicyError, match="DECISION_SESSION_NOT_LATEST_COMPLETED"):
        apply_admission_policy(_workspace("2026-08-28"), latest_qualified_completed_session="2026-09-01", price_evidence=_prices(), admitted_at="2026-09-01T19:00:00+07:00")
    first = _card("AAA", "INITIATE_RESEARCH_CANDIDATE")
    second = _card("AAA", "INITIATE_RESEARCH_CANDIDATE"); second["lineage"]["formatting_only"] = "changed"
    assert material_decision_state_signature(first, "ACTIVE_RESEARCH_THESIS") == material_decision_state_signature(second, "ACTIVE_RESEARCH_THESIS")


def test_durable_retention_is_idempotent_allows_material_transition_and_initial_outcomes_are_pending():
    with tempfile.TemporaryDirectory() as directory:
        store = DurableProspectiveResearchCaseStore(Path(directory) / "store")
        first = apply_admission_policy(_workspace(), latest_qualified_completed_session="2026-09-01", price_evidence=_prices(), admitted_at="2026-09-01T19:00:00+07:00", store=store)
        retained = retain_admitted_cases(first, store)
        assert len(retained["retained"]) == 2 and not retained["errors"]
        second = apply_admission_policy(_workspace(), latest_qualified_completed_session="2026-09-01", price_evidence=_prices(), admitted_at="2026-09-01T19:00:00+07:00", store=store)
        assert second["coverage"]["admission_status"] == {"CASE_ALREADY_ACTIVE": 2, "INSUFFICIENT_EVIDENCE_NOT_ADMITTED": 1}
        changed = _workspace(); changed["cards"]["AAA"]["entry_state"] = "BREAKOUT_READY"
        transition = apply_admission_policy(changed, latest_qualified_completed_session="2026-09-01", price_evidence=_prices(), admitted_at="2026-09-01T19:00:00+07:00", store=store)
        assert transition["decisions"][0]["admission_status"] == "ADMITTED"
        artifact = build_outcome_artifact(load_genuine_case_envelopes(store.root), [{"session": "2026-09-01", "completed_session_gate": {"completion_gate_status": "READY", "resolved_session": "2026-09-01"}}], evaluation_as_of_session="2026-09-01")
        assert all(row["horizons"]["T5"]["status"] == "PENDING_NOT_ENOUGH_FUTURE_SESSIONS" for row in artifact["outcomes"])
        assert all(row["confirmation"]["session"] is None for row in artifact["outcomes"])


def test_malformed_price_is_localized_without_silent_record_drop():
    prices = _prices(); prices.pop("BBB")
    artifact = apply_admission_policy(_workspace(), latest_qualified_completed_session="2026-09-01", price_evidence=prices, admitted_at="2026-09-01T19:00:00+07:00")
    assert len(artifact["decisions"]) == 3
    result = {item["ticker"]: item["admission_status"] for item in artifact["decisions"]}
    assert result == {"AAA": "ADMITTED", "BBB": "MALFORMED_CASE", "CCC": "INSUFFICIENT_EVIDENCE_NOT_ADMITTED"}
