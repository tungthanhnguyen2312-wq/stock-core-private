from __future__ import annotations

import pytest

from multi_session_thesis_recommendation_lifecycle import build_artifact


def context(*, priority="MONITOR", tactical="BASE_BUILDING", recommendation=None, invalidation=None, strategy="ELIGIBLE", scenario="SCENARIO_READY"):
    result = {"research_priority": {"research_priority_tier": priority, "entry_relevant": priority == "PRIORITY_NOW", "status": "AVAILABLE"},
              "current_decision_state": {"entry_state": tactical, "entry_action": "WAIT"},
              "strategy_fit": {"status": strategy, "eligible_strategy_ids": ["BASE_ACCUMULATION"], "scenario_relationship": {"scenario_disposition": scenario}},
              "scenario": {"status": "AVAILABLE", "probability_status": "UNKNOWN_UNCALIBRATED", "base_case": {"current_state": tactical, "case_status": "CONDITIONAL"}},
              "authority_limitations": ["NO_ACTION"]}
    if recommendation is not None: result["recommendation"] = {"recommendation_label": recommendation}
    if invalidation is not None: result["fundamental_invalidation"] = invalidation
    return result


def bundle(session, records):
    return {"session": session, "operation_identity": f"operation:{session}", "product_identity": f"product:{session}", "source_artifact_sha256": f"hash:{session}", "ticker_research_contexts": records}


def build(previous, current, chain=("2026-08-27", "2026-08-28")):
    return build_artifact(previous_bundle=previous, current_bundle=current, qualified_session_chain=list(chain))


def component(record, name):
    return next(item for item in record["component_transitions"] if item["dimension"] == name)


def test_valid_consecutive_and_weekend_governed_chain_do_not_use_calendar_minus_one():
    previous = bundle("2026-08-28", {"AAA": context()})
    current = bundle("2026-08-31", {"AAA": context()})
    artifact = build(previous, current, ("2026-08-28", "2026-08-31"))
    assert artifact["records"]["AAA"]["thesis_lifecycle_state"] == "UNCHANGED"
    assert artifact["previous_session"] == "2026-08-28"


def test_initial_observation_and_session_mismatch_fail_closed():
    current = bundle("2026-08-28", {"AAA": context()})
    initial = build(None, current)
    assert initial["records"]["AAA"]["thesis_lifecycle_state"] == "INITIAL_OBSERVATION"
    assert initial["previous_only_count"] == 0
    with pytest.raises(ValueError, match="PREVIOUS_SESSION_NOT_CONSECUTIVE"):
        build(bundle("2026-08-26", {"AAA": context()}), current)
    with pytest.raises(ValueError, match="CURRENT_SESSION_NOT_IN_GOVERNED_CHAIN"):
        build(None, bundle("2026-08-29", {"AAA": context()}))
    with pytest.raises(ValueError, match="CURRENT_SESSION_NOT_IN_GOVERNED_CHAIN"):
        build(None, bundle("2027-01-01", {"AAA": context()}))


def test_recommendation_change_is_preserved_not_replaced_with_action():
    prior = bundle("2026-08-27", {"AAA": context(recommendation="WAIT_FOR_CONFIRMATION")})
    now = bundle("2026-08-28", {"AAA": context(recommendation="HIGH_RISK_SPECULATION_ONLY")})
    prior["ticker_research_contexts"]["AAA"]["recommendation"]["source_note"] = "retained-prior"
    now["ticker_research_contexts"]["AAA"]["recommendation"]["source_note"] = "retained-current"
    record = build(prior, now)["records"]["AAA"]
    assert record["previous_recommendation"] == {"recommendation_label": "WAIT_FOR_CONFIRMATION", "source_note": "retained-prior"}
    assert record["current_recommendation"] == {"recommendation_label": "HIGH_RISK_SPECULATION_ONLY", "source_note": "retained-current"}
    assert record["thesis_lifecycle_state"] == "STATE_TRANSITION"
    assert "UPSTREAM_RECOMMENDATION_LABEL_CHANGED" in record["material_change_reasons"]
    assert "WEAKENING" not in str(record) and record["is_actionable"] is False


def test_unchanged_recommendation_and_full_upstream_component_are_preserved_verbatim():
    prior = bundle("2026-08-27", {"AAA": context(recommendation="AVOID_NEW_ENTRY")})
    now = bundle("2026-08-28", {"AAA": context(recommendation="AVOID_NEW_ENTRY")})
    prior["ticker_research_contexts"]["AAA"]["strategy_fit"]["retained_detail"] = {"unmodified": ["A"]}
    now["ticker_research_contexts"]["AAA"]["strategy_fit"]["retained_detail"] = {"unmodified": ["A"]}
    record = build(prior, now)["records"]["AAA"]
    assert component(record, "RECOMMENDATION")["transition"] == "UNCHANGED"
    assert record["previous_strategy_state"] == prior["ticker_research_contexts"]["AAA"]["strategy_fit"]
    assert record["current_strategy_state"] == now["ticker_research_contexts"]["AAA"]["strategy_fit"]
    assert record["thesis_lifecycle_state"] == "UNCHANGED"


def test_confirmation_and_invalidation_transitions_are_component_based():
    prior = bundle("2026-08-27", {"CONF": context(tactical="BASE_BUILDING"), "INV": context(invalidation={"current_trigger_state": "NOT_TRIGGERED", "status": "READY"})})
    now = bundle("2026-08-28", {"CONF": context(tactical="BREAKOUT_READY"), "INV": context(invalidation={"current_trigger_state": "TRIGGERED", "status": "READY"})})
    records = build(prior, now)["records"]
    assert records["CONF"]["thesis_lifecycle_state"] == "CONFIRMED"
    assert component(records["CONF"], "TACTICAL")["transition"] == "CONFIRMATION_GAINED"
    assert records["INV"]["thesis_lifecycle_state"] == "INVALIDATED"
    assert "UPSTREAM_FUNDAMENTAL_INVALIDATION_ACTIVATED" in records["INV"]["material_change_reasons"]


def test_unchanged_invalidation_is_not_reclassified_and_lifecycle_emits_no_new_authority():
    invalidation = {"current_trigger_state": "NOT_TRIGGERED", "status": "READY", "reason": "retained"}
    artifact = build(bundle("2026-08-27", {"AAA": context(invalidation=invalidation)}), bundle("2026-08-28", {"AAA": context(invalidation=invalidation)}))
    record = artifact["records"]["AAA"]
    assert component(record, "FUNDAMENTAL_INVALIDATION")["transition"] == "UNCHANGED"
    assert record["current_invalidation_state"] == invalidation
    assert artifact["authority_effect"] == "NONE" and artifact["is_actionable"] is False
    assert "NO_NEW_RECOMMENDATION_OR_ACTION" in artifact["interpretation_limits"]


def test_priority_gain_loss_missing_dimensions_and_determinism():
    prior = bundle("2026-08-27", {"GAIN": context(priority="MONITOR"), "LOSS": context(priority="PRIORITY_NOW"), "MISS": context()})
    now = bundle("2026-08-28", {"GAIN": context(priority="PRIORITY_NOW"), "LOSS": context(priority="MONITOR"), "MISS": context()})
    artifact = build(prior, now)
    assert "HIGH_PRIORITY_OPPORTUNITY_GAINED" in artifact["records"]["GAIN"]["material_change_reasons"]
    assert "HIGH_PRIORITY_OPPORTUNITY_LOST" in artifact["records"]["LOSS"]["material_change_reasons"]
    assert component(artifact["records"]["MISS"], "RECOMMENDATION")["transition"] == "MISSING"
    assert artifact["records"]["MISS"]["thesis_lifecycle_state"] == "UNCHANGED"
    assert artifact == build(prior, now)


def test_confirmation_lost_and_upstream_lineage_are_preserved():
    prior = bundle("2026-08-27", {"AAA": context(tactical="BREAKOUT_READY", recommendation="AVOID_NEW_ENTRY")})
    now = bundle("2026-08-28", {"AAA": context(tactical="BASE_BUILDING", recommendation="AVOID_NEW_ENTRY")})
    record = build(prior, now)["records"]["AAA"]
    assert component(record, "TACTICAL")["transition"] == "CONFIRMATION_LOST"
    assert record["previous_artifact_identity"]["operation_identity"] == "operation:2026-08-27"
    assert record["current_artifact_identity"]["source_artifact_sha256"] == "hash:2026-08-28"


def test_previous_only_coverage_is_explicit_without_synthetic_current_record():
    artifact = build(bundle("2026-08-27", {"OLD": context()}), bundle("2026-08-28", {"NEW": context()}))
    assert artifact["denominator"] == 1 and artifact["initial_only_count"] == 1 and artifact["previous_only_count"] == 1
    assert "OLD" not in artifact["records"]


def test_root_warnings_make_missing_dimensions_explicit():
    artifact = build(bundle("2026-08-27", {"AAA": context()}), bundle("2026-08-28", {"AAA": context()}))
    assert artifact["warnings"] == [
        "FUNDAMENTAL_INVALIDATION_MISSING_FOR_1_CURRENT_RECORDS",
        "RECOMMENDATION_MISSING_FOR_1_CURRENT_RECORDS",
    ]


def test_invalidation_cleared_is_a_material_change_symmetric_with_activated():
    prior = bundle("2026-08-27", {"AAA": context(invalidation={"current_trigger_state": "TRIGGERED", "status": "READY"})})
    now = bundle("2026-08-28", {"AAA": context(invalidation={"current_trigger_state": "NOT_TRIGGERED", "status": "READY"})})
    record = build(prior, now)["records"]["AAA"]
    assert component(record, "FUNDAMENTAL_INVALIDATION")["transition"] == "INVALIDATION_CLEARED"
    assert "UPSTREAM_FUNDAMENTAL_INVALIDATION_CLEARED" in record["material_change_reasons"]
    assert record["material_change"] is True


def test_invalidation_activation_does_not_force_a_recommendation_transition():
    prior = bundle("2026-08-27", {"AAA": context(recommendation="ACCUMULATE_RESEARCH_CANDIDATE", invalidation={"current_trigger_state": "NOT_TRIGGERED", "status": "READY"})})
    now = bundle("2026-08-28", {"AAA": context(recommendation="ACCUMULATE_RESEARCH_CANDIDATE", invalidation={"current_trigger_state": "TRIGGERED", "status": "READY"})})
    record = build(prior, now)["records"]["AAA"]
    assert component(record, "FUNDAMENTAL_INVALIDATION")["transition"] == "INVALIDATION_ACTIVATED"
    assert component(record, "RECOMMENDATION")["transition"] == "UNCHANGED"
    assert record["current_recommendation"]["recommendation_label"] == "ACCUMULATE_RESEARCH_CANDIDATE"
    assert "UPSTREAM_RECOMMENDATION_LABEL_CHANGED" not in record["material_change_reasons"]


def test_recommendation_transition_is_separate_from_thesis_lifecycle_state():
    # A recommendation-label change alone (no tactical confirmation gain, no invalidation
    # activation) is STATE_TRANSITION, never the tactical-only CONFIRMED state.
    prior = bundle("2026-08-27", {"AAA": context(recommendation="WAIT_FOR_CONFIRMATION")})
    now = bundle("2026-08-28", {"AAA": context(recommendation="INITIATE_RESEARCH_CANDIDATE")})
    record = build(prior, now)["records"]["AAA"]
    assert record["thesis_lifecycle_state"] == "STATE_TRANSITION"
    assert component(record, "RECOMMENDATION")["transition"] == "STATE_CHANGED"


def test_deterministic_identity_with_full_retained_recommendation_and_invalidation_context():
    rec = {
        "recommendation_label": "ACCUMULATE_RESEARCH_CANDIDATE", "recommendation_readiness": "RECOMMENDATION_READY",
        "as_of_session": "2026-08-28", "recommendation_reason_codes": ["X"], "warnings": ["W"],
        "authority_boundaries": {"trade_execution_authority": False}, "source_artifact_identity": "shadow_security_recommendation:deadbeef",
    }
    inv = {
        "status": "READY", "current_trigger_state": "NOT_TRIGGERED", "reason": "r", "rule_identity": "RULE/v1",
        "source_artifact_identity": "shadow_security_recommendation:deadbeef",
    }
    previous = bundle("2026-08-27", {"AAA": context(recommendation="WAIT_FOR_CONFIRMATION", invalidation={"current_trigger_state": "UNKNOWN", "status": "CONDITIONAL"})})
    current = bundle("2026-08-28", {"AAA": context(recommendation=None, invalidation=None)})
    current["ticker_research_contexts"]["AAA"]["recommendation"] = rec
    current["ticker_research_contexts"]["AAA"]["fundamental_invalidation"] = inv
    first = build_artifact(previous_bundle=previous, current_bundle=current, qualified_session_chain=["2026-08-27", "2026-08-28"])
    second = build_artifact(previous_bundle=previous, current_bundle=current, qualified_session_chain=["2026-08-27", "2026-08-28"])
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["records"]["AAA"]["current_recommendation"] == rec
    assert first["records"]["AAA"]["current_invalidation_state"] == inv
