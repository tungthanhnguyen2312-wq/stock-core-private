"""S1-S20 and source corruption, entirely synthetic and offline."""
import ast
import copy
import json
from pathlib import Path

import pytest
import current_evidence_bound_scenario as scenario
import portfolio_opportunity_cost_research as opportunity
import integrated_investment_decision_product as owner
import market_structure_breakout_product_projection as structural
import current_research_decision_packet as packet
import current_research_decision_packet_product as product
from current_opportunity_prioritization import content_identity as opportunity_identity
from current_market_flow_positioning import content_identity as flow_identity
from _integrated_decision_fixture import disposition_artifact, disposition_record
from test_research_posture_v2_policy import tactical, FIRED, BEAR, FAILED, REVERSAL
from test_integrated_investment_decision_product import _sample_financial_record
from test_portfolio_opportunity_cost_research import _state

SESSION = "2026-08-28"


def source(changes=None, *, currency="CURRENT_SESSION", financial=False, participation=None, market=None, tickers=("AAA",)):
    rows = {}
    for ticker in tickers:
        row = tactical(**(changes or {}))
        row.update(ticker=ticker, as_of_session=SESSION, trigger_close_comparison_operator=">",
                   invalidation_close_comparison_operator="<", trigger_horizon="PIVOT_BREAKOUT_MEASUREMENT",
                   invalidation_horizon="SWING_STRUCTURE_ANALYTICAL_CONTEXT",
                   price_basis_qualification={"price_basis_verified": False, "basis": "PROVIDER_SCOPED", "historical_pit_eligible": False})
        rows[ticker] = row
    artifact = {"contract_version": structural.CONTRACT_VERSION, "session": SESSION, "records": rows}
    artifact.update(structural.content_identity(artifact))
    coverage = disposition_artifact({t: disposition_record(t, session=SESSION, currency=currency) for t in tickers}, session=SESSION)
    kwargs = dict(session=SESSION, requested_at=SESSION + "T15:00:00+07:00", technical_structure_artifact=artifact,
                  technical_coverage_disposition_artifact=coverage)
    if financial:
        kwargs["financial_analysis_artifact"] = {"artifact_identity": "financial:synthetic", "records": {t: _sample_financial_record() for t in tickers}}
    if participation:
        kwargs["participation_artifact"] = {"artifact_identity": "participation:synthetic", "session": SESSION, "records": {t: participation for t in tickers}}
    if market:
        kwargs["market_sector_artifact"] = {"artifact_identity": "market:synthetic", "session": SESSION,
            "market": {"session": SESSION, "status": "AVAILABLE", "current_breadth_state": market["market_regime"],
                       "official_universe_count": 2, "exact_session_observed_count": 2, "missing_current_session_count": 0},
            "ticker_contexts": {t: market for t in tickers}}
    return owner.build_artifact(**kwargs)


def bind(artifact, tickers=("AAA",), **kwargs):
    return scenario.bind_integrated_scenarios(session=SESSION, integrated_decision=artifact, tickers=tickers, **kwargs)


def candidate(ticker="AAA", **kwargs):
    return {"ticker": ticker, "session": SESSION, "horizon": "STRUCTURAL", "portfolio_role": "CORE", **kwargs}


def compare(artifact, *, state=None, candidates=None, binding=None):
    return opportunity.build_integrated_comparison(session=SESSION, integrated_decision=artifact,
        candidates=candidates or [candidate()], owner_portfolio_state=state, integrated_scenario_binding=binding)


MATRIX = [
    ("S1", {"base_status": "IN_BASE", "ma20_slope_state": "FLAT"}, "BASE_UNCONFIRMED", "UNCONFIRMED", False),
    ("S2", REVERSAL, "EARLY_MONITOR_NO_TRIGGER", "UNCONFIRMED", False),
    ("S3", {}, "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY", "NON_ENTRY", False),
    ("S5", FIRED, "FRESH_ENTRY_TRIGGER", "ENTRY_ADMITTED", True),
    ("S6", FAILED, "FAILED_BREAKOUT_REBASE_REQUIRED", "REBASE_REQUIRED", False),
    ("S7", BEAR, "BEARISH_STRUCTURE_ADVERSE", "ADVERSE", False),
    ("distribution", {"market_structure_state": "EARLY_BEARISH_REVERSAL"}, "DISTRIBUTION_RISK_NO_FRESH_ENTRY", "DISTRIBUTION_UNCONFIRMED", False),
    ("extended", {**FIRED, "distance_to_pivot_pct": .12}, "EXTENDED_NO_CHASE", "EXTENDED", False),
    ("retest", {"pivot_retest_confirmed": True, "distance_to_invalidation_pct": .01, "trigger_type": "RETEST_BROKEN_PIVOT"}, "CONFIRMED_RETEST_ENTRY", "ENTRY_ADMITTED", True),
]


@pytest.mark.parametrize("name,changes,klass,status,bull", MATRIX, ids=[c[0] for c in MATRIX])
def test_scenario_admission_and_opportunity_matrix(name, changes, klass, status, bull):
    artifact = source(changes)
    original = copy.deepcopy(artifact)
    binding = bind(artifact)
    row = binding["records"]["AAA"]
    assert row["posture_condition_class"] == klass
    assert row["bull_case"]["case_status"] == ("CONDITIONAL" if bull else "NOT_ADMITTED")
    assert row["bull_case"]["reason_code"] == ("QUALIFIED_INTEGRATED_ENTRY_TRIGGER" if bull else "NO_QUALIFIED_ENTRY_TRIGGER")
    built = compare(artifact, binding=binding)
    lens = built["comparison_units"][0]["lenses"]["tactical"]
    assert lens["confirmation"] == status
    assert lens["decision_identity"] == artifact["records"]["AAA"]["decision_identity"]
    assert not any(c["case"] == opportunity.ADD_CORE_REVIEW for c in built["research_cases"])
    if status in {"NON_ENTRY", "UNCONFIRMED"}:
        assert lens["non_entry_context"] == [klass]
        assert not any(e.startswith("TACTICAL_") for c in built["research_cases"] for e in c["supporting_evidence"])
    if bull:
        assert row["bull_case"]["trigger"] == artifact["records"]["AAA"]["trigger"]
        assert row["time_horizon"]["trigger"] == "PIVOT_BREAKOUT_MEASUREMENT"
    assert row["probability_status"] == "UNKNOWN_UNCALIBRATED"
    assert artifact == original


def test_s4_missing_owner_ticker_is_unresolved_never_hold_or_add():
    artifact = source()
    state = _state({}, sector_weights={})
    built = compare(artifact, state=state)
    assert built["comparison_units"][0]["holding_fact"] == "CURRENT_POSITION_UNRESOLVED"
    assert not any(c["case"] in {opportunity.HOLD_CORE_REVIEW, opportunity.ADD_CORE_REVIEW} for c in built["research_cases"])
    uncertain = _state({"AAA": "materials"}, sector_weights={"materials": .2})
    uncertain["positions"]["AAA"].pop("current_position_status")
    assert compare(artifact, state=uncertain)["comparison_units"][0]["holding_fact"] == "CURRENT_POSITION_UNRESOLVED"


@pytest.mark.parametrize("quantity", [None, True, -1, float("inf"), "unknown"])
def test_v2_unresolved_quantity_never_becomes_flat_or_held(quantity):
    state = _state({"AAA": "materials"}, sector_weights={"materials": .2})
    state["positions"]["AAA"]["current_quantity"] = quantity
    built = compare(source(FIRED), state=state)
    assert built["comparison_units"][0]["holding_fact"] == "CURRENT_POSITION_UNRESOLVED"
    assert not any(c["ticker"] == "AAA" for c in built["research_cases"])


def test_s8_missing_current_evidence_cannot_manufacture_bear():
    row = bind(source(BEAR, currency="NO_CURRENT_EVIDENCE"))["records"]["AAA"]
    assert row["posture_condition_class"] == "MISSING_CURRENT_EVIDENCE"
    assert row["bear_case"]["case_status"] == "INSUFFICIENT_EVIDENCE"
    assert row["bear_case"]["invalidation"] is None


def test_s9_absent_invalidation_is_not_invented_and_observed_adverse_is_distinct():
    quiet = bind(source({"invalidation_level": None}))["records"]["AAA"]
    assert quiet["bear_case"]["reason_code"] == "NO_QUALIFIED_INVALIDATION_OR_ADVERSE_EVIDENCE"
    adverse = bind(source({**BEAR, "invalidation_level": None}))["records"]["AAA"]
    assert adverse["bear_case"]["reason_code"] == "BEARISH_STRUCTURE_ADVERSE"
    assert adverse["bear_case"]["observed_adverse"] and adverse["bear_case"]["invalidation"] is None


def test_s10_no_comparable_alternative_no_superiority_or_invented_cash_yield():
    artifact = source(tickers=("AAA", "BBB"))
    built = compare(artifact, candidates=[candidate("AAA"), candidate("BBB")], state=_state({"AAA": "materials"}, sector_weights={"materials": .2}))
    alternative = next(c for c in built["research_cases"] if c["ticker"] == "BBB")
    assert alternative["case"] == opportunity.INSUFFICIENT_COMPARABLE_EVIDENCE
    assert built["pairwise"][0]["comparability"]["winner"] is None
    assert built["pairwise"][0]["comparability"]["superiority"] is None
    assert built["research_cases"][-1]["expected_return"] is None


def test_s11_s12_flow_missing_and_wrong_session_remain_unavailable():
    artifact = source(FIRED)
    missing = bind(artifact)["records"]["AAA"]
    flow = {"contract_version": "current_market_flow_positioning/v1", "session": "2026-08-27", "records": {"AAA": {"coverage": {"available_dimensions": 1}}}}
    flow.update(flow_identity(flow))
    mismatch = bind(artifact, optional_context={"flow": flow})["records"]["AAA"]
    assert missing["optional_context"]["flow"]["reason_code"] == "CONTEXT_NOT_SUPPLIED"
    assert mismatch["optional_context"]["flow"]["reason_code"] == "CONTEXT_SESSION_MISMATCH"
    assert mismatch["optional_context"]["flow"]["status"] == "UNAVAILABLE"
    assert mismatch["bull_case"] == missing["bull_case"]
    assert mismatch["research_action_posture"] == missing["research_action_posture"]


def test_same_session_flow_is_facts_only_and_cannot_admit_bull():
    artifact = source()
    flow = {"contract_version": "current_market_flow_positioning/v1", "session": SESSION,
            "records": {"AAA": {"session": SESSION, "coverage": {"available_dimensions": 1},
                                "foreign_flow": {"status": "AVAILABLE", "net_value": 3},
                                "price_flow_relationships": ["BUY_SUPPORT"]}}}
    flow.update(flow_identity(flow))
    row = bind(artifact, optional_context={"flow": flow})["records"]["AAA"]
    assert row["optional_context"]["flow"]["use"] == "NON_VOTING_CONTEXT_ONLY"
    assert row["optional_context"]["flow"]["status"] == "AVAILABLE_DESCRIPTIVE"
    assert row["bull_case"]["case_status"] == "NOT_ADMITTED"
    binding = bind(artifact, optional_context={"flow": flow})
    compare(artifact, binding=binding)
    binding["records"]["AAA"]["optional_context"]["flow"]["payload"]["foreign_flow"]["net_value"] = 99
    binding.update(scenario.binding_content_identity(binding))
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="SCENARIO_CONTEXT_RECORD_CONFLICT"):
        compare(artifact, binding=binding)


def resign(artifact):
    for row in artifact["records"].values():
        row["decision_identity"] = owner.decision_identity(row)
    artifact.update(owner.content_identity(artifact))
    return artifact


def test_s13_mixed_price_basis_is_visible_no_authority_promotion():
    artifact = source(FIRED)
    artifact["records"]["AAA"]["invalidation"]["price_basis"] = {"basis": "OTHER_PROVIDER", "price_basis_verified": False}
    row = bind(resign(artifact))["records"]["AAA"]
    assert row["price_basis"]["trigger"] != row["price_basis"]["invalidation"]
    assert "PRICE_BASIS_UNVERIFIED_OR_MIXED" in row["limitations"]


@pytest.mark.parametrize("target,reason", [("artifact", "INTEGRATED_POLICY_EPOCH_MISMATCH"), ("record", "INTEGRATED_RECORD_POLICY_EPOCH_MISMATCH")])
def test_s14_cross_policy_rejected(target, reason):
    artifact = source()
    (artifact if target == "artifact" else artifact["records"]["AAA"])["research_action_policy_version"] = "v1"
    artifact.update(owner.content_identity(artifact))
    with pytest.raises(scenario.IntegratedScenarioBindingError, match=reason):
        bind(artifact)


def test_s15_cross_integrated_identity_and_rehashed_binding_substitution_rejected():
    artifact, other = source(FIRED), source()
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="SCENARIO_INTEGRATED_IDENTITY_MISMATCH"):
        compare(other, binding=bind(artifact))
    binding = bind(artifact)
    binding["records"]["AAA"]["research_action_posture"] = "AVOID"
    binding.update(scenario.binding_content_identity(binding))
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="SCENARIO_BINDING_RECORD_CONFLICT"):
        compare(artifact, binding=binding)


@pytest.mark.parametrize("tickers,reason", [(("AAA", "AAA"), "DUPLICATE_TICKER"), (("MISSING",), "REQUESTED_TICKER_MISSING")])
def test_s16_s17_duplicate_and_missing_tickers_rejected(tickers, reason):
    with pytest.raises(scenario.IntegratedScenarioBindingError, match=reason):
        bind(source(), tickers)


def test_s18_contradicted_axis_never_recomputes_posture():
    artifact = source({**FIRED, **BEAR})
    row = bind(artifact)["records"]["AAA"]
    assert row["research_action_posture"] == "AVOID"
    assert row["bull_case"]["case_status"] == "NOT_ADMITTED"
    assert row["evidence_axis_coherence"] == artifact["records"]["AAA"]["evidence_axis_coherence"]


def test_s19_released_bearish_breadth_narrows_fresh_entry():
    # Real owner build with qualified same-session market input, rather than a
    # consumer changing the security posture after the fact.
    artifact = source(FIRED, market={"status": "AVAILABLE", "market_regime": "BEARISH"})
    row = bind(artifact)["records"]["AAA"]
    assert row["posture_condition_class"] == "BEARISH_BREADTH_NARROWS_FRESH_ENTRY"
    assert row["bull_case"]["case_status"] == "NOT_ADMITTED"


def test_s20_original_scenario_build_and_daily_entrypoint_unchanged():
    originals = {name: {"artifact_identity": name + ":synthetic", "session": SESSION, "records": {"AAA": {}}}
                 for name in ("descriptive", "tactical", "peer_relative", "fundamental", "valuation")}
    originals["triage"] = {"artifact_identity": "triage:synthetic"}
    old = scenario.build(**originals)
    assert old["contract_version"] == "current_evidence_bound_scenario/v1"
    assert old == scenario.build(**originals)
    path = Path(__file__).resolve().parents[1] / "daily_session_level2_package.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert any(isinstance(n, ast.ImportFrom) and n.module == "current_evidence_bound_scenario" and any(a.name == "build" for a in n.names) for n in ast.walk(tree))
    assert "bind_integrated_scenarios" not in path.read_text(encoding="utf-8")


def test_positive_add_requires_all_existing_constraints_and_integrated_entry():
    artifact = source(FIRED, financial=True)
    raw = candidate(structural={"source_identity": artifact["artifact_identity"], "session": SESSION,
                               "fundamental_state": artifact["records"]["AAA"]["fundamental_state"], "thesis_status": "INTACT", "thesis_source": "owner:synthetic"})
    state = _state({"AAA": "materials"}, sector_weights={"materials": .2})
    built = compare(artifact, state=state, candidates=[raw])
    assert any(c["case"] == opportunity.ADD_CORE_REVIEW for c in built["research_cases"])
    state["effective_policy"] = {"max_single_position_weight": .1}
    constrained = compare(artifact, state=state, candidates=[raw])
    assert not any(c["case"] == opportunity.ADD_CORE_REVIEW for c in constrained["research_cases"])
    assert any(r["reason"] == "OWNER_SINGLE_POSITION_LIMIT_REACHED" for r in constrained["narrowed_by_owner_constraints_or_evidence"])


@pytest.mark.parametrize("level", [None, 0, -1, True])
def test_unqualified_level_cannot_admit_bull_even_entry_class(level):
    artifact = source({**FIRED, "trigger_level": level})
    assert bind(artifact)["records"]["AAA"]["bull_case"]["reason_code"] == "NO_QUALIFIED_ENTRY_TRIGGER"
    assert compare(artifact)["comparison_units"][0]["lenses"]["tactical"]["confirmation"] == "NOT_USABLE"


def test_retest_without_corresponding_trigger_condition_not_admitted():
    artifact = source({"pivot_retest_confirmed": True, "distance_to_invalidation_pct": .01})
    assert artifact["records"]["AAA"]["posture_condition_class"] == "CONFIRMED_RETEST_ENTRY"
    assert bind(artifact)["records"]["AAA"]["bull_case"]["reason_code"] == "NO_QUALIFIED_ENTRY_TRIGGER"


def test_whole_source_identity_class_eligibility_and_prose_fail_closed():
    artifact = source(FIRED)
    corrupt = copy.deepcopy(artifact)
    corrupt["records"]["AAA"]["why_now"] = "substituted"
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="INTEGRATED_CONTENT_IDENTITY_MISMATCH"):
        bind(corrupt)
    conflict = copy.deepcopy(artifact)
    conflict["records"]["AAA"]["posture_condition_class"] = "BASE_UNCONFIRMED"
    conflict.update(owner.content_identity(conflict))
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="INTEGRATED_CLASS_POSTURE_CONFLICT"):
        bind(conflict)
    prose = copy.deepcopy(artifact)
    prose["records"]["AAA"]["trigger"]["condition"] = {"status": "READY", "narrative_reason": "buy above 40"}
    assert bind(resign(prose))["records"]["AAA"]["bull_case"]["case_status"] == "NOT_ADMITTED"
    substituted = copy.deepcopy(artifact)
    substituted["records"]["AAA"]["evidence_axes"]["TACTICAL_STRUCTURE"]["lineage"]["source_artifact_identity"] = "another:source"
    assert bind(resign(substituted))["records"]["AAA"]["bull_case"]["reason_code"] == "NO_QUALIFIED_ENTRY_TRIGGER"


@pytest.mark.parametrize("change,reason", [
    ("session", "INTEGRATED_SESSION_MISMATCH"), ("contract", "INTEGRATED_CONTRACT_MISMATCH"),
    ("decision", "INTEGRATED_DECISION_IDENTITY_MISMATCH"), ("eligibility", "INTEGRATED_TACTICAL_ELIGIBILITY_CONFLICT"),
    ("currency", "INTEGRATED_EVIDENCE_CURRENCY_INVALID"),
])
def test_adversarial_source_reasons(change, reason):
    artifact = source(FIRED)
    row = artifact["records"]["AAA"]
    if change == "session":
        artifact["session"] = "2026-08-27"
    elif change == "contract":
        artifact["contract_version"] = "other/v1"
    elif change == "decision":
        row["decision_identity"] = "substituted"
    elif change == "eligibility":
        row["evidence_axes"]["TACTICAL_STRUCTURE"]["fitness"] = "INSUFFICIENT_EVIDENCE"
    elif change == "currency":
        row["evidence_currency"] = "invalid"
        row["decision_identity"] = owner.decision_identity(row)
    artifact.update(owner.content_identity(artifact))
    with pytest.raises(scenario.IntegratedScenarioBindingError, match=reason):
        bind(artifact)


def test_dated_currency_preserved_and_corrupted_sibling_not_ignored():
    artifact = source(FIRED, currency="LAST_TRADE_AS_OF:2026-08-27", tickers=("AAA", "BBB"))
    assert bind(artifact)["records"]["AAA"]["base_case"]["current_state"]["evidence_currency"] == "LAST_TRADE_AS_OF:2026-08-27"
    artifact["records"]["BBB"]["decision_identity"] = "corrupt"
    artifact.update(owner.content_identity(artifact))
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="INTEGRATED_DECISION_IDENTITY_MISMATCH"):
        bind(artifact)


def test_private_portfolio_absent_from_iid_and_nonentry_held_never_add():
    artifact = source(financial=True)
    state = _state({"AAA": "materials"}, sector_weights={"materials": .2})
    raw = candidate(structural={"source_identity": artifact["artifact_identity"], "session": SESSION,
                               "thesis_status": "INTACT", "thesis_source": "owner:synthetic"})
    built = compare(artifact, candidates=[raw], state=state)
    assert any(c["case"] == opportunity.HOLD_CORE_REVIEW for c in built["research_cases"])
    assert not any(c["case"] == opportunity.ADD_CORE_REVIEW for c in built["research_cases"])
    assert artifact["records"]["AAA"]["portfolio_context"]["status"] == "NOT_PROVIDED"
    assert "current_quantity" not in json.dumps(artifact)


def test_one_source_to_binding_comparison_packet_product_and_replay():
    artifact = source(FIRED, tickers=("AAA", "BBB"))
    frozen = copy.deepcopy(artifact)
    binding = bind(artifact, ("AAA", "BBB"))
    comparison = compare(artifact, candidates=[candidate("AAA"), candidate("BBB")], binding=binding)
    upstream = {"contract_version": "current_opportunity_prioritization/v1", "research_session": SESSION,
                "records": {t: {} for t in artifact["records"]}}
    upstream.update(opportunity_identity(upstream))
    built = packet.build_artifact(opportunity=upstream, integrated_decision=artifact, integrated_scenario_binding=binding)
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="INTEGRATED_ARTIFACT_MISSING"):
        packet.build_artifact(opportunity=upstream, integrated_scenario_binding=binding)
    with pytest.raises(scenario.IntegratedScenarioBindingError, match="SCENARIO_INTEGRATED_IDENTITY_MISMATCH"):
        packet.build_artifact(opportunity=upstream, integrated_decision=source(tickers=("AAA", "BBB")), integrated_scenario_binding=binding)
    packet.replay(built)
    panel = product.project_shadow_panel(built)
    assert panel is not None
    for ticker in artifact["records"]:
        bound = built["records"][ticker]["integrated_scenario_binding"]
        assert bound == binding["records"][ticker]
        assert product.project_ticker(built["records"][ticker], built)["integrated_scenario_binding"] == bound
        assert bound["decision_identity"] == artifact["records"][ticker]["decision_identity"]
        assert bound["research_action_policy_version"] == "v2" and bound["session"] == SESSION
    assert comparison["source_identities"]["integrated_investment_decision_product"] == built["source_artifact_identities"]["integrated_decision"] == artifact["artifact_identity"]
    assert artifact == frozen
    legacy = packet.build_artifact(opportunity=upstream, integrated_decision=artifact)
    assert "integrated_scenario_binding_header" not in legacy
    packet.replay(legacy)
    malicious = copy.deepcopy(built)
    malicious["records"]["AAA"]["integrated_scenario_binding"]["decision_identity"] = "other"
    malicious.update(packet.content_identity(malicious))
    with pytest.raises(packet.CurrentResearchDecisionPacketError, match="PACKET_SCENARIO_BINDING_INVALID"):
        packet.replay(malicious)
    for obj in (binding, comparison, built):
        assert obj.get("is_actionable", False) is False
    assert comparison["winner"] is comparison["order"] is comparison["position_size"] is None
    assert set(opportunity.V2_CLASSIFICATION) == set(owner.POSTURE_CLASS_COMPATIBILITY)
