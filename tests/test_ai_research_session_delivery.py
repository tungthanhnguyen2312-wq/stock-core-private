import hashlib
import json
from copy import deepcopy

import pytest

from ai_research_session_delivery import AI_CONTRACT, FULL_UNIVERSE_COMPANION_ROLE, PRIMARY_HUMAN_REVIEW_FILENAME, build_delivery
from stocklookup_core.decision.current_daily_decision_research_product import OWNER_FOCUS_TICKERS, WATCHLIST, ABSENT_OWNER_FOCUS_STATUS
from owner_research_focus import broader_watchlist, owner_focus_tickers


def _integrated_delivery_fixture(*, session="2026-08-21", identity="integrated_investment_decision_product/v1:integrated-1"):
    return {
        "contract_version": "integrated_investment_decision_product/v1",
        "session": session,
        "artifact_identity": identity,
        "coverage": {"universe_denominator": 1, "residual": 0},
        "records": {
            "AAA": {
                "ticker": "AAA",
                "as_of_session": session,
                "decision_identity": "decision:AAA:0001",
                "research_action_posture": "INITIATE_ON_BREAKOUT",
                "evidence_currency": "CURRENT_SESSION",
                "evidence_currency_gate": {"applied": False, "rule": "NO_CURRENT_EVIDENCE_NEVER_WAIT_FOR_CONFIRMATION"},
                "evidence_currency_lineage": {"disposition": "SAME_SESSION_TECHNICAL_COVERED", "feature_as_of_session": session},
                "position_context": {"position_state": "UNKNOWN_POSITION_NOT_SUPPLIED", "status": "NOT_SUPPLIED"},
                "opportunity_priority": {"status": "AVAILABLE", "research_priority_tier": "MONITOR", "authority": "INSPECTION_ORDER_ONLY_NOT_AN_ACTION_POSTURE"},
                "tactical_phase": "BREAKOUT_CONFIRMED",
                "trigger": {"trigger_type": "BREAKOUT", "trigger_level": 42.5, "trigger_state": "TRIGGERED", "distance_to_trigger_pct": 0.0},
                "invalidation": {"invalidation_level": 40.0, "invalidation_method": "CLOSE_BELOW_SUPPORT", "distance_to_invalidation_pct": 0.06},
                "evidence_axis_coherence": {"state": "COHERENT", "reason_codes": ["CONFIRMED"]},
                "evidence_axes": {"TACTICAL_STRUCTURE": {"state": "AVAILABLE"}},
                "financial_composite_context": {"financial_composite_state": "FUNDAMENTALS_IMPROVING"},
                "corporate_intelligence_context": {"state": "INFORMATIONAL_ONLY"},
                "material_uncertainties": ["EVIDENCE_LIMITED"],
                "counter_thesis": ["BREAKOUT_FAILURE"],
                "missing_evidence_decision_effect": "DOES_NOT_BLOCK_CURRENT_RESEARCH",
                "why_now": "Existing technical confirmation.",
                "participation": {"status": "AVAILABLE"},
                "valuation_context_summary": {"pe_multiple": 11.25, "status": "AVAILABLE"},
                "valuation_methods": {
                    "P/E": {"method_id": "P/E", "status": "RESEARCH_USABLE", "applicability": "APPLICABLE", "value": 11.25},
                    "P/B": {"method_id": "P/B", "status": "INPUT_BLOCKED", "applicability": "INPUT_BLOCKED", "blocker_reason_codes": ["ENTITY_CLASS_UNRESOLVED"], "value": None, "target_price": 99.0},
                },
                "valuation_method_reconciliation": {"P/E": {"comparison_status": "AVAILABLE"}},
                "source_identities": {"technical": "technical:1"},
            },
        },
    }


def _daily_brief_fixture(integrated, *, session="2026-08-21"):
    return {
        "contract_version": "daily_integrated_decision_brief/v1",
        "session": session,
        "artifact_identity": "daily_integrated_decision_brief/v1:brief-1",
        "coverage": {"watchlist_coverage": 1},
        "what_changed_today": {"availability": "AVAILABLE", "new_actionable_now": ["AAA"]},
        "source_artifact_identities": {"integrated_investment_decision_product": integrated["artifact_identity"]},
    }


def _operation():
    product = {"artifact_identity": "product:1", "authority_boundary": {"is_actionable": False, "probability": "UNKNOWN_UNCALIBRATED"}, "market_brief": {"coverage": {"technical": 0}}, "macro_context": {"status": "UNAVAILABLE"}, "research_cohorts": {"EARLY_REVERSAL": {"count": 1, "tickers": ["AAA"]}}, "high_priority_full_universe_review_set": {"count": 1, "tickers": ["AAA"]}, "watchlist": {"cards_available": 1, "tickers": ["AAA"]}, "aggregate_validation": {"entry_relevant_90_count": 1}, "detailed_research_cards": {"AAA": {"ticker": "AAA", "current_decision_state": {"entry_action": "WAIT", "is_actionable": False}, "market_flow_positioning": {"status": "UNAVAILABLE", "traded_value": 0.0}, "valuation_context": {"strict_valuation_status": "UNAVAILABLE"}}}, "risk_data_gap_panel": {"technical_unavailable": 0}, "what_to_verify_next": ["verify"] , "source_artifact_identities": {"descriptive": "descriptive:1"}}
    manifest = {"market_session": "2026-08-21", "operation_identity": "operation:1", "producer_head": "producer", "consumer_head": "consumer", "input_artifacts": {"descriptive": {"artifact_identity": "descriptive:1", "session": "2026-08-21"}}, "outputs": {"daily_product": "product:1"}, "warnings": ["warning"], "session_coherence": {"session": "2026-08-21"}, "coverage_summary": {}}
    return {"product": product, "manifest": manifest, "peer": {"records": {"AAA": {"status": "AVAILABLE"}}}, "scenario": {"records": {"AAA": {"probability_status": "UNKNOWN_UNCALIBRATED"}}}, "strategy": {"records": {"AAA": {"strategies": []}}}, "portfolio_risk": None}


def test_valuation_handoff_preserves_research_proxy_versus_authoritative_unavailable():
    from ai_research_session_delivery import _valuation_handoff
    row = {
        "price_input": {"status": "PRICE_READY", "session": "2026-08-26"},
        "share_basis_input": {"status": "PROVIDER_REPORTED_LAGGED"},
        "financial_input": {"authority": "PROVIDER_RESEARCH"},
        "metrics": {
            "market_cap": {"status": "RESEARCH_USABLE", "labels": ["CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE"], "blocked_reasons": [], "first_blocker": None},
            "P/E": {"status": "BLOCKED", "labels": [], "blocked_reasons": ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"], "first_blocker": "FINANCIAL_FACT_MISSING"},
        },
        "shadow_proxy_valuation": {
            "authority_tier": "SHADOW_RESEARCH_ONLY",
            "share_basis_type": "PROVIDER_ISSUED_SHARE_PROXY",
            "metrics": {"proxy_market_cap": {"status": "SHADOW_PROXY_READY", "labels": ["SHADOW", "NOT_COMMON_OUTSTANDING_SHARE_BASIS"]}},
        },
        "value_strategy": {"status": "BLOCKED"},
    }
    handoff = _valuation_handoff(row)
    assert handoff["metrics"]["market_cap"]["authority_note"] == "RESEARCH_PROXY_VALUATION_AVAILABLE_NOT_AUTHORITATIVE"
    assert handoff["metrics"]["P/E"]["authority_note"] == "AUTHORITATIVE_VALUATION_UNAVAILABLE"
    assert handoff["research_proxy_is_not_a_value_judgment"] is True
    assert handoff["is_actionable"] is False
    blob = json.dumps(handoff)
    assert '"BUY"' not in blob and '"SELL"' not in blob
    assert "target_price" not in blob
    operation = _operation()
    inputs = {
        "descriptive": {"records": {"AAA": {}}},
        "tactical": {"records": {"AAA": {"entry_state": "WAIT"}}},
        "fundamental": {"records": {"AAA": None}},
        "valuation": {"records": {"AAA": row}},
        "market_flow_positioning": {"records": {"AAA": {"traded_value": 0.0}}},
        "corporate_intelligence": {"records": {"AAA": {"status": "NO_RETAINED_INTELLIGENCE"}}},
    }
    universe = json.loads(build_delivery(operation, inputs)["full_universe"])
    assert universe["valuation_context"]["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert universe["valuation_context"]["metrics"]["P/E"]["first_blocker"] == "FINANCIAL_FACT_MISSING"


def test_delivery_is_deterministic_and_preserves_boundaries():
    operation = _operation()
    inputs = {"descriptive": {"records": {"AAA": {}}}, "tactical": {"records": {"AAA": {"entry_state": "WAIT"}}}, "fundamental": {"records": {"AAA": None}}, "valuation": {"records": {"AAA": {"status": "UNAVAILABLE"}}}, "market_flow_positioning": {"records": {"AAA": {"traded_value": 0.0}}}, "corporate_intelligence": {"records": {"AAA": {"status": "NO_RETAINED_INTELLIGENCE"}}}}
    one, two = build_delivery(operation, inputs), build_delivery(operation, inputs)
    assert one == two
    primary = json.loads(one["primary"])
    assert primary["schema_version"] == AI_CONTRACT
    assert primary["authority_boundary"]["is_actionable"] is False
    assert primary["ticker_research_contexts"]["AAA"]["market_flow_positioning"]["traded_value"] == 0.0
    assert json.loads(one["manifest"])["files"]["ai_research_full_universe.ndjson"]["record_count"] == 1
    assert len(one["full_universe"].splitlines()) == 1


def test_integrated_delivery_overlay_preserves_native_values_and_cockpit_card():
    operation = _operation()
    integrated = _integrated_delivery_fixture()
    brief = _daily_brief_fixture(integrated)
    inputs = {
        "descriptive": {"records": {"AAA": {}}}, "tactical": {"records": {"AAA": {}}},
        "fundamental": {"records": {}}, "valuation": {"records": {}},
        "market_flow_positioning": {"records": {}}, "corporate_intelligence": {"records": {}},
        "integrated_investment_decision_product": integrated,
        "daily_integrated_decision_brief": brief,
    }
    one, two = build_delivery(operation, inputs), build_delivery(operation, inputs)
    assert one == two
    primary = json.loads(one["primary"])
    row = primary["ticker_research_contexts"]["AAA"]["integrated_decision_v1"]
    assert row["research_action_posture"] == "INITIATE_ON_BREAKOUT"
    assert row["trigger"]["trigger_level"] == 42.5
    assert row["invalidation"]["invalidation_level"] == 40.0
    assert row["evidence_axis_coherence"]["state"] == "COHERENT"
    assert row["valuation_methods"]["P/E"]["value"] == 11.25
    assert row["valuation_methods"]["P/B"]["status"] == "INPUT_BLOCKED"
    assert "target_price" not in json.dumps(row["valuation_methods"])
    companion = json.loads(one["full_universe"])
    assert companion["integrated_decision_v1"]["trigger"]["distance_to_trigger_pct"] == 0.0
    projection = json.loads(one["projection"])
    overlay = primary["integrated_decision_overlay_v1"]
    assert overlay["daily_integrated_decision_brief_identity"] == brief["artifact_identity"]
    assert overlay["integrated_investment_decision_product_identity"] == integrated["artifact_identity"]
    assert overlay["session"] == integrated["session"] == brief["session"]
    assert json.loads(one["manifest"])["daily_integrated_decision_brief_identity"] == brief["artifact_identity"]
    card = projection["decision_card_v1"]["AAA"]
    assert card["verdict"] == "INITIATE_ON_BREAKOUT"
    assert card["entry_trigger"]["trigger_level"] == 42.5
    assert card["authority_boundary"]["research_support_not_execution_instruction"] is True
    assert card["authority_boundary"]["no_target_price"] is True


def test_integrated_delivery_rejects_cross_session_or_mismatched_brief_identity():
    operation = _operation()
    integrated = _integrated_delivery_fixture(session="2026-08-20")
    inputs = {"descriptive": {"records": {"AAA": {}}}, "integrated_investment_decision_product": integrated}
    with pytest.raises(ValueError, match="INTEGRATED_DELIVERY_SESSION_MISMATCH"):
        build_delivery(operation, inputs)
    integrated = _integrated_delivery_fixture()
    brief = _daily_brief_fixture(integrated)
    brief["source_artifact_identities"]["integrated_investment_decision_product"] = "integrated_investment_decision_product/v1:other"
    inputs["integrated_investment_decision_product"] = integrated
    inputs["daily_integrated_decision_brief"] = brief
    with pytest.raises(ValueError, match="DAILY_INTEGRATED_BRIEF_SOURCE_IDENTITY_MISMATCH"):
        build_delivery(operation, inputs)
    brief = _daily_brief_fixture(integrated, session="2026-08-20")
    inputs["daily_integrated_decision_brief"] = brief
    with pytest.raises(ValueError, match="DAILY_INTEGRATED_BRIEF_SESSION_MISMATCH"):
        build_delivery(operation, inputs)


# Exact shipped projection snapshot from 9d567d056e8c79494572e288e88dbf00af637ce6.
# Embedded so clean, shallow CI needs no historical Git object.
LEGACY_ACCOUNTING_PROJECTION_SOURCE = r'''
def _selected_fields(value: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {field: copy.deepcopy(value.get(field)) for field in fields if field in value}

def _valuation_methods_for_delivery(record: Mapping[str, Any]) -> dict[str, Any]:
    """Pass through qualified valuation values and blocked states without a calculation."""
    result: dict[str, Any] = {}
    for name, method in sorted((record.get("valuation_methods") or {}).items()):
        if not isinstance(method, Mapping):
            continue
        row = _selected_fields(method, (
            "method_id", "status", "applicability", "blocker_reason_codes",
            "period_basis", "value", "source_status", "p3f_method_status",
        )) or {}
        # Targets, fair values, and probabilities are deliberately not a delivery
        # field, even when an upstream blocked row represents them as null.
        result[str(name)] = row
    return result

def project_integrated_decision_for_ai_delivery(record: Any, *, integrated_identity: str | None = None) -> dict[str, Any] | None:
    """Project one Integrated Decision record for AI delivery.

    M1_LIVE_ACCEPTANCE_CORRECTIVE_V1: the decision-surface fields (ticker binding,
    ``evidence_currency`` and its gate/lineage, ``position_context``, priority) are
    copied verbatim from the canonical record, never recomputed here.  A field the
    record does not carry is delivered as ``None``; it is never inferred. ``is_actionable`` and
    the other boundary flags are fixed by this contract, not taken from the record, so the whole
    returned object (boundary flags included) is what AI handoff verification requires exactly.
    """
    if not isinstance(record, Mapping):
        return None
    trigger = _selected_fields(record.get("trigger"), (
        "trigger_type", "trigger_level", "trigger_state", "distance_to_trigger_pct",
        "condition", "watchlist_condition",
    ))
    invalidation = _selected_fields(record.get("invalidation"), (
        "invalidation_level", "invalidation_method", "distance_to_invalidation_pct",
        "condition", "watchlist_condition",
    ))
    return {
        "ticker": record.get("ticker"),
        "decision_identity": record.get("decision_identity"),
        "integrated_investment_decision_product_identity": integrated_identity,
        "as_of_session": record.get("as_of_session"),
        "research_action_posture": record.get("research_action_posture"),
        "posture_condition_class": record.get("posture_condition_class"),
        "research_action_policy_version": record.get("research_action_policy_version", "v1"),
        "evidence_currency": record.get("evidence_currency"),
        "evidence_currency_gate": copy.deepcopy(record.get("evidence_currency_gate")),
        "evidence_currency_lineage": copy.deepcopy(record.get("evidence_currency_lineage")),
        "position_context": copy.deepcopy(record.get("position_context")),
        "opportunity_priority": copy.deepcopy(record.get("opportunity_priority")),
        "tactical_phase": record.get("tactical_phase"),
        "trigger": trigger,
        "invalidation": invalidation,
        "evidence_axis_coherence": copy.deepcopy(record.get("evidence_axis_coherence")),
        "evidence_axes": copy.deepcopy(record.get("evidence_axes")),
        **({"financial_peer_context": copy.deepcopy(record["financial_peer_context"])} if "financial_peer_context" in record else {}),
        "financial_composite_context": copy.deepcopy(record.get("financial_composite_context")),
        "corporate_intelligence_context": copy.deepcopy(record.get("corporate_intelligence_context")),
        "material_uncertainties": copy.deepcopy(record.get("material_uncertainties")),
        "counter_thesis": copy.deepcopy(record.get("counter_thesis")),
        "missing_evidence_decision_effect": copy.deepcopy(record.get("missing_evidence_decision_effect")),
        "why_now": copy.deepcopy(record.get("why_now")),
        "participation": copy.deepcopy(record.get("participation")),
        "valuation_context_summary": copy.deepcopy(record.get("valuation_context_summary")),
        "valuation_methods": _valuation_methods_for_delivery(record),
        "valuation_method_reconciliation": copy.deepcopy(record.get("valuation_method_reconciliation")),
        "source_identities": copy.deepcopy(record.get("source_identities")),
        # CURRENT_RESEARCH_DECISION_CONVERGENCE_V1: the Producer's per-dimension explanation of
        # what is available, proxy, qualified, blocked or non-applicable and why -- passed
        # through so AI never reverse-engineers a disappeared metric.
        "current_research_decision_input": copy.deepcopy(record.get("current_research_decision_input")),
        "is_actionable": False,
        "research_support_not_execution_instruction": True,
        "no_target_price": True,
        "no_calibrated_probability": True,
        "no_position_size": True,
    }
'''
LEGACY_ACCOUNTING_PROJECTION_SHA256 = 'fb5f7fbd876a5216fd7d980a71eabe46e71ad72437400bf05a09f8438ee9b4f9'


@pytest.fixture(scope="module")
def legacy_accounting_delivery_projection():
    """Execute only the three shipped projection functions, without importing historical code."""
    import ast
    import copy
    from typing import Any, Mapping

    source = LEGACY_ACCOUNTING_PROJECTION_SOURCE
    assert hashlib.sha256(source.encode()).hexdigest() == LEGACY_ACCOUNTING_PROJECTION_SHA256
    names = {"_selected_fields", "_valuation_methods_for_delivery", "project_integrated_decision_for_ai_delivery"}
    functions = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in functions} == names
    namespace = {"copy": copy, "Any": Any, "Mapping": Mapping}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<shipped-delivery-projection>", "exec"), namespace)
    return namespace["project_integrated_decision_for_ai_delivery"]


def _accounting_delivery_inputs(session):
    operation = _operation()
    operation["manifest"]["market_session"] = session
    operation["manifest"]["session_coherence"]["session"] = session
    integrated = _integrated_delivery_fixture(session=session)
    record = integrated["records"]["AAA"]
    record["valuation_methods"]["P/E_REPORTED_PERIOD"] = {
        "method_id": "P/E_REPORTED_PERIOD", "status": "RESEARCH_USABLE", "applicability": "APPLICABLE",
        "value": 20.0, "period_basis": "2026-H1", "blocker_reason_codes": [],
        "earnings_definition": "REPORTED_TOTAL_NET_INCOME_NOT_PARENT_ATTRIBUTABLE",
        "denominator_metric": "net_income", "denominator_period_semantics": "SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED",
        "statement_scope": "consolidated", "share_basis": "CURRENT_SHARE_RESEARCH_PROXY",
        "limitations": ["CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE", "NO_ANNUALIZATION_OR_TTM"],
        "target_price": 999.0, "fair_value": 998.0, "probability": 0.9,
    }
    record["valuation_methods"]["P/B_CURRENT_RESEARCH"] = {
        "method_id": "P/B_CURRENT_RESEARCH", "status": "RESEARCH_USABLE", "applicability": "APPLICABLE",
        "value": 2.0, "period_basis": "POINT_IN_TIME_BALANCE_SHEET", "blocker_reason_codes": [],
        "equity_definition": "TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT",
        "statement_scope": "consolidated", "share_basis": "CURRENT_SHARE_RESEARCH_PROXY",
        "limitations": ["CURRENT_RESEARCH_ONLY", "NCI_NOT_DEDUCTED"],
    }
    brief = _daily_brief_fixture(integrated, session=session)
    return operation, integrated, brief, {
        "descriptive": {"records": {"AAA": {}}},
        "integrated_investment_decision_product": integrated, "daily_integrated_decision_brief": brief,
    }


@pytest.mark.parametrize("session", ["2026-10-12", "2026-10-13"])
def test_possible_sealed_deliveries_keep_all_shipped_bytes(session, monkeypatch, legacy_accounting_delivery_projection):
    import ai_research_session_delivery as delivery

    monkeypatch.setattr(delivery, "owner_focus_tickers", lambda: ("AAA",))
    operation, integrated, _brief, inputs = _accounting_delivery_inputs(session)
    # Neither a record date nor a delivery flag can choose the new source-session epoch.
    integrated["records"]["AAA"]["as_of_session"] = "2099-01-01"
    operation["manifest"]["accounting_qualifiers_enabled"] = True
    current = build_delivery(operation, inputs)
    with monkeypatch.context() as old:
        old.setattr(delivery, "project_integrated_decision_for_ai_delivery",
                    lambda record, *, integrated_identity=None, source_session=None:
                    legacy_accounting_delivery_projection(record, integrated_identity=integrated_identity))
        shipped = build_delivery(operation, inputs)
    assert current == shipped  # primary, full universe, cockpit, manifest and brief bytes


@pytest.mark.parametrize("source_session", [None, "", "not-a-date", "2026-02-30", "20261014", "2026-10-14T00:00:00Z"])
def test_absent_invalid_or_noncanonical_source_session_keeps_legacy_projection(source_session, legacy_accounting_delivery_projection):
    from ai_research_session_delivery import project_integrated_decision_for_ai_delivery

    _operation, integrated, _brief, _inputs = _accounting_delivery_inputs("2026-10-14")
    record = integrated["records"]["AAA"]
    expected = legacy_accounting_delivery_projection(record, integrated_identity=integrated["artifact_identity"])
    assert project_integrated_decision_for_ai_delivery(record, integrated_identity=integrated["artifact_identity"],
                                                      source_session=source_session) == expected


@pytest.mark.parametrize("session", ["2026-10-13", "2026-10-14", "2026-10-15"])
def test_actual_delivery_verifier_and_cockpit_preserve_prospective_accounting_labels(session, monkeypatch, tmp_path):
    import ai_research_session_delivery as delivery
    from pathlib import Path
    # This imports verifier functions, not the production launcher. An operator's
    # active-writer binding on the test host must not authorize/refuse a fixture.
    with monkeypatch.context() as isolated:
        isolated.setattr(Path, "home", lambda: tmp_path)
        from tools import run_owner_daily as workflow

    monkeypatch.setattr(delivery, "owner_focus_tickers", lambda: ("AAA",))
    operation, integrated, brief, inputs = _accounting_delivery_inputs(session)
    snapshot = deepcopy(inputs)
    result = build_delivery(operation, inputs)
    primary = json.loads(result["primary"])
    companion = json.loads(result["full_universe"])
    cockpit = json.loads(result["projection"])
    contexts = [primary["ticker_research_contexts"]["AAA"]["integrated_decision_v1"],
                primary["owner_focus_research_contexts"][0]["integrated_decision_v1"], companion["integrated_decision_v1"]]
    method_views = [context["valuation_methods"] for context in contexts]
    method_views.append(cockpit["decision_card_v1"]["AAA"]["valuation"]["methods"])
    for methods in method_views:
        pe, pb = methods["P/E_REPORTED_PERIOD"], methods["P/B_CURRENT_RESEARCH"]
        assert (pe["value"], pe["status"], pb["value"], pb["status"]) == (20.0, "RESEARCH_USABLE", 2.0, "RESEARCH_USABLE")
        if session >= "2026-10-14":
            assert pe["earnings_definition"] == integrated["records"]["AAA"]["valuation_methods"]["P/E_REPORTED_PERIOD"]["earnings_definition"]
            assert pe["denominator_metric"] == "net_income"
            assert pe["denominator_period_semantics"] == "SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED"
            assert pb["equity_definition"] == integrated["records"]["AAA"]["valuation_methods"]["P/B_CURRENT_RESEARCH"]["equity_definition"]
            assert "NCI_NOT_DEDUCTED" in pb["limitations"]
        else:
            assert "earnings_definition" not in pe and "equity_definition" not in pb
        assert "earnings_definition" not in methods["P/E"]  # absent source labels are not inferred
        assert not {"target_price", "fair_value", "probability"}.intersection(pe)
    assert all(context["research_action_posture"] == "INITIATE_ON_BREAKOUT" for context in contexts)
    assert cockpit["decision_card_v1"]["AAA"]["verdict"] == "INITIATE_ON_BREAKOUT"
    assert inputs == snapshot
    (tmp_path / delivery.PRIMARY_HUMAN_REVIEW_FILENAME).write_bytes(result["primary"])
    (tmp_path / delivery.FULL_UNIVERSE_LOOKUP_FILENAME).write_bytes(result["full_universe"])
    overlay = delivery.project_integrated_decision_delivery_overlay(session, integrated, brief)
    projections = overlay.pop("records")
    authority = {"operation_identity": operation["manifest"]["operation_identity"],
                 "product_identity": operation["product"]["artifact_identity"],
                 "overlay_header": overlay, "projections": projections,
                 "scoped": ["AAA"], "owner_focus": ["AAA"], "full_universe": ["AAA"]}
    assert workflow._verify_m1_ai_delivery(tmp_path, session, authority) == {
        "ticker_research_contexts": 1, "owner_focus_research_contexts": 1, "full_universe_rows": 1}
    if session >= "2026-10-14":
        primary["ticker_research_contexts"]["AAA"]["integrated_decision_v1"]["valuation_methods"]["P/E_REPORTED_PERIOD"]["earnings_definition"] = "PARENT_PROFIT"
        (tmp_path / delivery.PRIMARY_HUMAN_REVIEW_FILENAME).write_text(json.dumps(primary), encoding="utf-8")
        with pytest.raises(workflow.OwnerDailyError, match="M1_AI_DELIVERY_PROJECTION_MISMATCH"):
            workflow._verify_m1_ai_delivery(tmp_path, session, authority)


def test_integrated_delivery_without_brief_preserves_standalone_semantics():
    operation = _operation()
    integrated = _integrated_delivery_fixture()
    inputs = {
        "descriptive": {"records": {"AAA": {}}},
        "integrated_investment_decision_product": integrated,
    }
    delivery = build_delivery(operation, inputs)
    primary = json.loads(delivery["primary"])
    assert primary["integrated_decision_overlay_v1"]["daily_integrated_decision_brief_identity"] is None
    assert primary["integrated_decision_overlay_v1"]["integrated_investment_decision_product_identity"] == integrated["artifact_identity"]
    assert len(delivery["full_universe"].splitlines()) == 1


def test_conditions_survive_primary_companion_and_cockpit_without_reinterpretation():
    integrated = _integrated_delivery_fixture()
    record = integrated["records"]["AAA"]
    for role, operator in [("trigger", "<"), ("invalidation", ">")]:
        record[role]["condition"] = {
            "status": "MACHINE_EVALUABLE", "operator": operator,
            "reference_level": 100.0, "reason_codes": ["EXISTING_READY_FIXED_T0_CLOSE_BOUNDARY"],
            "source_strategy_identity": "verified:projection",
        }
        record[role]["watchlist_condition"] = {
            "status": "NOT_MACHINE_EVALUABLE", "reason_codes": ["FUTURE_STRATEGY_MEASUREMENT_REQUIRED"],
        }
    operation = _operation()
    inputs = {"descriptive": {"records": {"AAA": {}}}, "tactical": {"records": {"AAA": {}}},
              "fundamental": {"records": {}}, "valuation": {"records": {}},
              "integrated_investment_decision_product": integrated}
    delivery = build_delivery(operation, inputs)
    primary = json.loads(delivery["primary"])["ticker_research_contexts"]["AAA"]["integrated_decision_v1"]
    companion = json.loads(delivery["full_universe"])["integrated_decision_v1"]
    projection = json.loads(delivery["projection"])
    # All surfaces use the same standing projection, including the cockpit card.
    for view in [primary, companion]:
        for role in ["trigger", "invalidation"]:
            assert view[role]["condition"] == record[role]["condition"]
            assert view[role]["watchlist_condition"] == record[role]["watchlist_condition"]
        assert view["is_actionable"] is False
    card = projection["decision_card_v1"]["AAA"]
    assert card["entry_trigger"]["condition"] == record["trigger"]["condition"]
    assert card["invalidation"]["condition"] == record["invalidation"]["condition"]
    assert card["entry_trigger"]["watchlist_condition"] == record["trigger"]["watchlist_condition"]
    assert card["authority_boundary"]["is_actionable"] is False


def _card(ticker, action="WAIT"):
    return {
        "ticker": ticker,
        "status": "AVAILABLE",
        "current_decision_state": {
            "entry_action": action,
            "is_actionable": False,
            "entry_action_is_research_label_not_execution_instruction": True,
        },
        "market_flow_positioning": {"status": "UNAVAILABLE", "traded_value": 0.0},
        "valuation_context": {"strict_valuation_status": "UNAVAILABLE"},
    }


def _scoped_operation(missing_owner_focus=()):
    missing = set(missing_owner_focus)
    cards = {ticker: _card(ticker, "BUY_ON_CONFIRMATION") for ticker in OWNER_FOCUS_TICKERS if ticker not in missing}
    cards["QNS"] = _card("QNS", "ACCUMULATE_IN_BASE")
    cards["AAA"] = _card("AAA", "EARLY_ENTRY")
    product = {
        "artifact_identity": "product:1",
        "authority_boundary": {"is_actionable": False, "probability": "UNKNOWN_UNCALIBRATED", "recommendation": "NOT_EMITTED"},
        "market_brief": {"coverage": {"technical": 0}},
        "macro_context": {"status": "UNAVAILABLE"},
        "research_cohorts": {"EARLY_REVERSAL": {"count": 1, "tickers": ["AAA"], "ordering": "TICKER_ASCENDING_NOT_RANKING"}},
        "high_priority_full_universe_review_set": {"count": 1, "tickers": ["AAA"], "meaning": "Candidates for human research, not portfolio/watchlist inclusion."},
        "watchlist": {"cards_available": 11, "tickers": list(WATCHLIST), "role": "BROADER_WATCHLIST_NOT_PORTFOLIO_HOLDINGS", "is_portfolio_holdings": False},
        "owner_focus": {"tickers": list(OWNER_FOCUS_TICKERS), "cards_available": 10 - len(missing), "missing": list(missing), "role": "OWNER_FOCUS_REVIEW_SCOPE", "is_portfolio_holdings": False, "is_actionable": False},
        "aggregate_validation": {"entry_relevant_90_count": 1},
        "detailed_research_cards": cards,
        "risk_data_gap_panel": {"technical_unavailable": 0},
        "what_to_verify_next": ["verify"],
        "source_artifact_identities": {"descriptive": "descriptive:1"},
    }
    if missing:
        for ticker in missing:
            product["detailed_research_cards"][ticker] = {
                "ticker": ticker,
                "status": ABSENT_OWNER_FOCUS_STATUS,
                "current_decision_state": {"entry_action": None, "is_actionable": False, "entry_action_is_research_label_not_execution_instruction": True},
                "is_actionable": False,
            }
    manifest = {
        "market_session": "2026-08-26",
        "operation_identity": "operation:1",
        "producer_head": "producer",
        "consumer_head": "consumer",
        "input_artifacts": {"descriptive": {"artifact_identity": "descriptive:1", "session": "2026-08-26"}},
        "outputs": {"daily_product": "product:1"},
        "warnings": ["warning"],
        "session_coherence": {"session": "2026-08-26"},
        "coverage_summary": {},
    }
    return {"product": product, "manifest": manifest, "peer": {"records": {}}, "scenario": {"records": {}}, "strategy": {"records": {}}, "portfolio_risk": None}


def _scoped_inputs():
    universe = ["AAA", "AAM", "HPG", "PAN", "QNS", "SSI", "ZZZ"]
    return {
        "descriptive": {"records": {ticker: {} for ticker in universe}},
        "tactical": {"records": {ticker: {"entry_state": "WAIT", "entry_action": "WAIT"} for ticker in universe}},
        "fundamental": {"records": {}},
        "valuation": {"records": {}},
        "market_flow_positioning": {"records": {}},
        "corporate_intelligence": {"records": {}},
    }


def test_full_universe_ndjson_is_alphabetical_lookup_only_not_primary():
    delivery = build_delivery(_scoped_operation(), _scoped_inputs())
    rows = [json.loads(line) for line in delivery["full_universe"].splitlines() if line]
    assert [row["ticker"] for row in rows] == ["AAA", "AAM", "HPG", "PAN", "QNS", "SSI", "ZZZ"]
    assert all(row["companion_role"] == FULL_UNIVERSE_COMPANION_ROLE for row in rows)
    assert all(row["not_primary_human_review_input"] is True for row in rows)
    assert all(row["no_alphabetical_sampling"] is True for row in rows)
    manifest = json.loads(delivery["manifest"])
    ndjson = manifest["files"]["ai_research_full_universe.ndjson"]
    assert ndjson["role"] == FULL_UNIVERSE_COMPANION_ROLE
    assert ndjson["not_primary_human_review_input"] is True
    assert ndjson["ordering"] == "TICKER_ASCENDING_DETERMINISTIC_LOOKUP_NOT_SAMPLING"
    assert manifest["recommended_ai_inputs"]["arbitrary_ticker_lookup"] == "ai_research_full_universe.ndjson"
    assert hashlib.sha256(delivery["full_universe"]).hexdigest() == ndjson["sha256"]


def test_primary_human_review_artifact_is_session_bundle():
    delivery = build_delivery(_scoped_operation(), _scoped_inputs())
    primary = json.loads(delivery["primary"])
    manifest = json.loads(delivery["manifest"])
    brief = delivery["brief"].decode("utf-8")
    assert primary["artifact_role"] == "PRIMARY_NORMAL_HUMAN_REVIEW_INPUT"
    assert manifest["primary_bundle_filename"] == PRIMARY_HUMAN_REVIEW_FILENAME
    assert manifest["recommended_ai_inputs"]["normal_human_review"] == PRIMARY_HUMAN_REVIEW_FILENAME
    assert "UPLOAD THIS" in brief and PRIMARY_HUMAN_REVIEW_FILENAME in brief
    assert "DO NOT USE AS PRIMARY" in brief and "ai_research_full_universe.ndjson" in brief


def test_analysis_scope_lists_all_owner_focus_tickers_and_preserves_watchlist():
    primary = json.loads(build_delivery(_scoped_operation(), _scoped_inputs())["primary"])
    scope = primary["analysis_scope"]
    assert scope["owner_focus_tickers"] == list(owner_focus_tickers())
    assert scope["owner_focus_tickers"] == ["SSI", "HPG", "PAN", "EVF", "VNM", "FPT", "PVD", "NVL", "POW", "PNJ"]
    assert scope["mandatory_owner_focus_coverage_count"] == 10
    assert scope["broader_watchlist"] == list(broader_watchlist())
    assert "QNS" in scope["broader_watchlist"]
    assert "QNS" not in scope["owner_focus_tickers"]
    assert scope["is_portfolio_holdings"] is False
    assert scope["grants_investment_authority"] is False
    assert scope["review_order"] == "OWNER_FOCUS_REVIEW_REQUIRED_BEFORE_MARKET_DISCOVERY"
    assert scope["no_alphabetical_sampling"] is True
    assert scope["full_universe_companion_role"] == FULL_UNIVERSE_COMPANION_ROLE
    assert "AAA" in primary["ticker_research_contexts"]
    assert all(ticker in primary["ticker_research_contexts"] for ticker in OWNER_FOCUS_TICKERS)


def test_owner_focus_is_not_portfolio_holdings():
    primary = json.loads(build_delivery(_scoped_operation(), _scoped_inputs())["primary"])
    assert primary["authority_boundary"]["owner_focus_is_not_portfolio_holdings"] is True
    assert primary["research_cohorts"]["watchlist"]["is_portfolio_holdings"] is False
    assert primary["research_cohorts"]["owner_focus"]["is_portfolio_holdings"] is False
    assert primary["portfolio_risk"]["status"] == "NO_EXPLICIT_PORTFOLIO_SUPPLIED"


def test_primary_bundle_carries_owner_focus_cards_and_explicit_absence():
    present = json.loads(build_delivery(_scoped_operation(), _scoped_inputs())["primary"])
    assert [row["ticker"] for row in present["owner_focus_research_contexts"]] == list(OWNER_FOCUS_TICKERS)
    assert all(row["status"] == "AVAILABLE" for row in present["owner_focus_research_contexts"])
    assert present["analysis_scope"]["coverage"]["owner_focus_missing"] == []
    assert present["analysis_scope"]["coverage"]["owner_focus_context_count"] == 10
    absent = json.loads(build_delivery(_scoped_operation(missing_owner_focus=("HPG",)), _scoped_inputs())["primary"])
    missing = [row for row in absent["owner_focus_research_contexts"] if row["ticker"] == "HPG"]
    assert missing and missing[0]["status"] == ABSENT_OWNER_FOCUS_STATUS
    assert "HPG" in absent["analysis_scope"]["coverage"]["owner_focus_missing"]
    assert "HPG" in absent["ticker_research_contexts"]
    assert absent["ticker_research_contexts"]["HPG"]["status"] == ABSENT_OWNER_FOCUS_STATUS


def test_no_alphabetical_sampling_and_entry_action_are_tactical_labels_not_recommendations():
    delivery = build_delivery(_scoped_operation(), _scoped_inputs())
    primary = json.loads(delivery["primary"])
    brief = delivery["brief"].decode("utf-8")
    manifest = json.loads(delivery["manifest"])
    assert primary["no_alphabetical_sampling"] is True
    assert primary["analysis_scope"]["no_alphabetical_sampling"] is True
    assert primary["entry_action_is_research_label_not_execution_instruction"] is True
    assert primary["is_actionable"] is False
    assert primary["authority_boundary"]["entry_action_is_research_label_not_execution_instruction"] is True
    assert primary["authority_boundary"]["recommendation"] == "NOT_EMITTED"
    assert manifest["entry_action_is_research_label_not_execution_instruction"] is True
    assert "tactical research-state labels, not recommendations" in brief
    assert "No alphabetical sampling" in brief
    assert "BUY_ON_CONFIRMATION" in brief
    blob = json.dumps(primary)
    assert "target_price" not in blob
    assert primary["authority_boundary"].get("recommendation") != "BUY"


# ---------------------------------------------------------------- M1_LIVE_ACCEPTANCE_CORRECTIVE_V1
# The retained 2026-09-24 delivery projected research_action_posture but dropped evidence_currency
# and position_context from every Integrated Decision overlay (103 scoped + 1,683 full-universe
# rows), and never attached the overlay to the owner-focus contexts.

M1_IID_ID = "integrated_investment_decision_product/v1:m1"
_CURRENCIES = ("CURRENT_SESSION", "LAST_TRADE_AS_OF:2026-08-25", "NO_CURRENT_EVIDENCE")
_POSTURES = ("WAIT_FOR_CONFIRMATION", "AVOID", "INSUFFICIENT_CURRENT_RESEARCH")


def _m1_iid(tickers, *, session="2026-08-26"):
    records = {}
    for index, ticker in enumerate(sorted(tickers)):
        records[ticker] = {
            "ticker": ticker, "as_of_session": session, "decision_identity": f"decision:{ticker}:{index:04d}",
            "research_action_posture": _POSTURES[index % 3], "evidence_currency": _CURRENCIES[index % 3],
            "evidence_currency_gate": {"applied": index % 3 == 2, "rule": "NO_CURRENT_EVIDENCE_NEVER_WAIT_FOR_CONFIRMATION"},
            "evidence_currency_lineage": {"method": "same_session_technical_coverage_disposition/v1"},
            "position_context": {"position_state": "UNKNOWN_POSITION_NOT_SUPPLIED", "status": "NOT_SUPPLIED"},
            "opportunity_priority": {"status": "AVAILABLE", "research_priority_tier": "MONITOR"},
            "tactical_phase": "BASE", "trigger": None, "invalidation": None,
        }
    return {"contract_version": "integrated_investment_decision_product/v1", "session": session,
            "artifact_identity": M1_IID_ID, "coverage": {"universe_denominator": len(records)}, "records": records}


def _m1_delivery(*, missing_owner_focus=()):
    inputs = _scoped_inputs()
    universe = set(inputs["descriptive"]["records"])
    iid = _m1_iid(universe | set(OWNER_FOCUS_TICKERS))
    inputs["integrated_investment_decision_product"] = iid
    return iid, build_delivery(_scoped_operation(missing_owner_focus=missing_owner_focus), inputs)


def _assert_exact_projection(delivered, record):
    assert delivered["ticker"] == record["ticker"]
    assert delivered["research_action_posture"] == record["research_action_posture"]
    assert delivered["evidence_currency"] == record["evidence_currency"]
    assert delivered["position_context"] == record["position_context"]
    assert delivered["evidence_currency_gate"] == record["evidence_currency_gate"]
    assert delivered["evidence_currency_lineage"] == record["evidence_currency_lineage"]
    assert delivered["opportunity_priority"] == record["opportunity_priority"]
    assert delivered["decision_identity"] == record["decision_identity"]
    assert delivered["as_of_session"] == record["as_of_session"]
    assert delivered["integrated_investment_decision_product_identity"] == M1_IID_ID


def test_full_universe_companion_is_a_one_to_one_projection_of_the_integrated_decision():
    iid, delivery = _m1_delivery()
    rows = [json.loads(line) for line in delivery["full_universe"].splitlines() if line]
    assert [row["ticker"] for row in rows] == sorted(_scoped_inputs()["descriptive"]["records"])
    for row in rows:
        _assert_exact_projection(row["integrated_decision_v1"], iid["records"][row["ticker"]])
    assert sum(1 for row in rows if "evidence_currency" not in row["integrated_decision_v1"]) == 0
    assert sum(1 for row in rows if "position_context" not in row["integrated_decision_v1"]) == 0
    assert {(row["ticker"], row["integrated_decision_v1"]["research_action_posture"], row["integrated_decision_v1"]["evidence_currency"])
            for row in rows} == {(t, iid["records"][t]["research_action_posture"], iid["records"][t]["evidence_currency"])
                                 for t in _scoped_inputs()["descriptive"]["records"]}


def test_scoped_and_owner_focus_overlays_carry_the_exact_integrated_decision_row():
    iid, delivery = _m1_delivery(missing_owner_focus=("HPG",))
    primary = json.loads(delivery["primary"])
    for ticker, context in primary["ticker_research_contexts"].items():
        _assert_exact_projection(context["integrated_decision_v1"], iid["records"][ticker])
    owner_rows = primary["owner_focus_research_contexts"]
    assert [row["ticker"] for row in owner_rows] == list(OWNER_FOCUS_TICKERS)
    for row in owner_rows:
        _assert_exact_projection(row["integrated_decision_v1"], iid["records"][row["ticker"]])
    # An owner-focus name without a Product V2 card still gets its canonical posture; the card's own
    # explicit absence is preserved alongside it.
    hpg = next(row for row in owner_rows if row["ticker"] == "HPG")
    assert hpg["status"] == ABSENT_OWNER_FOCUS_STATUS
    assert hpg["integrated_decision_v1"]["research_action_posture"] == iid["records"]["HPG"]["research_action_posture"]


def test_integrated_projection_never_recomputes_or_fabricates_decision_fields():
    operation = _operation()
    for card in operation["product"]["detailed_research_cards"].values():
        card["research_stance"] = "ACCUMULATE"  # a contradicting legacy stance must play no role
    integrated = _integrated_delivery_fixture()
    record = integrated["records"]["AAA"]
    del record["position_context"], record["evidence_currency_lineage"]
    inputs = {"descriptive": {"records": {"AAA": {}}}, "tactical": {"records": {"AAA": {"entry_action": "BUY_ON_CONFIRMATION"}}},
              "integrated_investment_decision_product": integrated}
    delivery = build_delivery(operation, inputs)
    for row in (json.loads(delivery["primary"])["ticker_research_contexts"]["AAA"]["integrated_decision_v1"],
                json.loads(delivery["full_universe"])["integrated_decision_v1"]):
        assert row["research_action_posture"] == "INITIATE_ON_BREAKOUT"
        assert row["evidence_currency"] == "CURRENT_SESSION"
        # Unknown stays unknown: an absent source field is delivered as null, never inferred.
        assert row["position_context"] is None
        assert row["evidence_currency_lineage"] is None
    source = open(__import__("ai_research_session_delivery").__file__, encoding="utf-8").read()
    assert "research_stance" not in source


def test_delivery_and_cockpit_never_pair_a_peer_verdict_with_a_peer_valuation_gap():
    operation = _operation()
    operation["product"]["detailed_research_cards"]["AAA"].update({
        "valuation_context": {"strict_valuation_status": "UNAVAILABLE", "peer_valuation_status": "VALUATION_PEER_CONTEXT_UNAVAILABLE"},
        "peer_context": {"limitations": ["VALUATION_PEER_CONTEXT_UNAVAILABLE"], "expectations_context": {"counter_evidence": ["VALUATION_PEER_CONTEXT_UNAVAILABLE"]}},
        "thesis_counter_thesis": {"thesis": [], "questions_to_verify": [], "counter_thesis": [
            {"type": "DATA_GAP", "claim": "VALUATION_PEER_CONTEXT_UNAVAILABLE", "evidence_field": "peer_relative.data_gaps", "authority": "BLOCKED_OR_UNAVAILABLE"}]},
    })
    operation["product"]["risk_data_gap_panel"]["valuation_peer_context_unavailable"] = 1
    integrated = _integrated_delivery_fixture()
    integrated["records"]["AAA"]["valuation_context_summary"]["peer_relative_state"] = "CHEAP_VS_PEERS"
    inputs = {
        "descriptive": {"records": {"AAA": {}}}, "tactical": {"records": {"AAA": {}}},
        "fundamental": {"records": {}}, "valuation": {"records": {}},
        "market_flow_positioning": {"records": {}}, "corporate_intelligence": {"records": {}},
        "integrated_investment_decision_product": integrated,
        "daily_integrated_decision_brief": _daily_brief_fixture(integrated),
    }
    delivered = build_delivery(operation, inputs)
    primary, projection = json.loads(delivered["primary"]), json.loads(delivered["projection"])
    for card in (primary["ticker_research_contexts"]["AAA"], projection["ticker_cards"]["AAA"]):
        assert card["valuation_context"]["peer_valuation_status"] == "PEER_RELATIVE_RESEARCH_IN_INTEGRATED_DECISION"
        assert card["valuation_context"]["peer_valuation_reconciliation"]["integrated_peer_relative_state"] == "CHEAP_VS_PEERS"
        assert "VALUATION_PEER_CONTEXT_UNAVAILABLE" not in json.dumps({key: card[key] for key in ("peer_context", "thesis_counter_thesis")})
        assert card["valuation_context"]["strict_valuation_status"] == "UNAVAILABLE"
    assert projection["risk_data_gaps"]["valuation_peer_context_unavailable"] == 0
    assert projection["decision_card_v1"]["AAA"]["valuation"]["context"]["peer_relative_state"] == "CHEAP_VS_PEERS"
    # The Product V2 artifact itself is never rewritten by delivery.
    assert operation["product"]["detailed_research_cards"]["AAA"]["valuation_context"]["peer_valuation_status"] == "VALUATION_PEER_CONTEXT_UNAVAILABLE"
