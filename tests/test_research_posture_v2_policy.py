"""Owner-reconciled Grok matrix. Synthetic inputs only; no retained Daily reads."""
import copy
import json

import pytest

import stocklookup_core.decision.integrated_investment_decision_product as owner
import stocklookup_core.decision.daily_integrated_decision_brief as brief
import next_session_decision_brief as next_brief
import stocklookup_core.portfolio.portfolio_aware_decision as portfolio
import stocklookup_core.decision.current_research_decision_packet as packet
import stocklookup_core.decision.current_research_decision_packet_product as packet_product
from _integrated_decision_fixture import integrated_decision
from test_integrated_investment_decision_product import _sample_tactical_record, _sample_financial_record
from test_portfolio_aware_decision import make_snapshot, make_position

SESSION = "2026-08-28"


def tactical(**changes):
    result = _sample_tactical_record(breakout_state_v3="NO_VALID_PIVOT", trigger_state="BELOW_TRIGGER",
                                     trigger_type="NO_TRIGGER", bos_state="NO_BOS")
    result.update(base_status="NO_BASE", range_state="NORMAL", ma20_slope_state="RISING")
    result.update(changes)
    return result


FIRED = {"breakout_state_v3": "BREAKOUT", "trigger_state": "TRIGGERED", "trigger_type": "PIVOT_BREAKOUT_TRIGGER"}
BEAR = {"bos_state": "BEARISH_BOS_DETECTED_BY_RULE"}
REVERSAL = {"market_structure_state": "EARLY_BULLISH_REVERSAL", "choch_state": "BULLISH_CHOCH_DETECTED_BY_RULE"}
FAILED = {"breakout_state_v3": "FAILED_BREAKOUT"}
CASES = [
    ("A1", "INSUFFICIENT", {}, {}, {}, "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY"),
    ("A5", "MIXED", {}, {}, {}, "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY"),
    ("A6", "IMPROVING", {}, {}, {}, "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY"),
    # Owner reconciliation of Grok A7/P10: qualified base is early monitoring.
    ("A7", "INSUFFICIENT", {"base_status": "IN_BASE", "ma20_slope_state": "FLAT"}, {}, {}, "BASE_UNCONFIRMED"),
    ("B1", "IMPROVING", {**FIRED, "market_structure_state": "DOWNTREND"}, {}, {}, "EARLY_REVERSAL_AWAITING_HIGHER_LOW"),
    ("B2", "INSUFFICIENT", REVERSAL, {}, {}, "EARLY_MONITOR_NO_TRIGGER"),
    ("B3", "DETERIORATING", REVERSAL, {}, {}, "FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY"),
    ("C1", "IMPROVING", BEAR, {}, {"sector_leadership": "LEADING"}, "BEARISH_STRUCTURE_ADVERSE"),
    ("D1", "INSUFFICIENT", {"market_structure_state": "EARLY_BEARISH_REVERSAL"}, {}, {}, "DISTRIBUTION_RISK_NO_FRESH_ENTRY"),
    ("D2", "DETERIORATING", {"market_structure_state": "EARLY_BEARISH_REVERSAL"}, {}, {}, "DISTRIBUTION_OR_BREAKDOWN_WITH_DETERIORATION"),
    ("E1", "INSUFFICIENT", FAILED, {}, {}, "FAILED_BREAKOUT_REBASE_REQUIRED"),
    ("E2", "DETERIORATING", FAILED, {}, {}, "FAILED_BREAKOUT_WITH_DETERIORATION"),
    ("E3", "IMPROVING", {**FAILED, **BEAR}, {}, {}, "BEARISH_STRUCTURE_ADVERSE"),
    ("F1", "INSUFFICIENT", FIRED, {}, {"market_regime": "UNKNOWN"}, "FRESH_ENTRY_TRIGGER"),
    ("F2", "DETERIORATING", FIRED, {}, {}, "FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY"),
    ("F3", "IMPROVING", FIRED, {"status": "AVAILABLE", "volume_acceleration_ratio": .45}, {}, "PARTICIPATION_CONTRADICTION_NARROWS_ENTRY"),
    ("F4", "IMPROVING", FIRED, {}, {"market_regime": "DETERIORATING_BREADTH"}, "BEARISH_BREADTH_NARROWS_FRESH_ENTRY"),
    ("F5", "INSUFFICIENT", {}, {"status": "AVAILABLE", "volume_acceleration_ratio": .45}, {"market_regime": "BEARISH"}, "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY"),
    ("G1", "IMPROVING", {**FIRED, "breakout_state_v3": "EXTENDED_AFTER_BREAKOUT", "distance_to_pivot_pct": .12}, {}, {}, "EXTENDED_NO_CHASE"),
    ("G2", "INSUFFICIENT", {"eligible": False}, {}, {}, "UNQUALIFIED_TACTICAL_AND_FUNDAMENTAL"),
    ("G3", "IMPROVING", {"eligible": False, **BEAR}, {}, {}, "UNQUALIFIED_TACTICAL_STRUCTURE"),
    ("H1", "IMPROVING", {**FIRED, **BEAR, "trigger_type": "CONFIRMED_BOS_TRIGGER"}, {}, {}, "BEARISH_STRUCTURE_ADVERSE"),
]

BOUNDARIES = [
    ("R1", "INSUFFICIENT", {"pivot_retest_confirmed": True, "distance_to_invalidation_pct": .01}, {}, {}, "CONFIRMED_RETEST_ENTRY"),
    ("R2", "MIXED", {"pivot_retest_confirmed": True, "distance_to_invalidation_pct": 0}, {}, {}, "OBSERVATIONAL_NO_ENTRY"),
    ("R3", "DETERIORATING", {"pivot_retest_confirmed": True}, {}, {}, "FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY"),
    ("R4", "IMPROVING", {"pivot_retest_confirmed": True}, {}, {"market_regime": "BEARISH"}, "BEARISH_BREADTH_NARROWS_FRESH_ENTRY"),
    ("T1", "INSUFFICIENT", {"trigger_state": "TRIGGERED", "trigger_type": "NO_TRIGGER"}, {}, {}, "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY"),
    ("T2", "INSUFFICIENT", {**FIRED, "distance_to_pivot_pct": .05}, {}, {}, "FRESH_ENTRY_TRIGGER"),
    ("T3", "INSUFFICIENT", {**FIRED, "distance_to_pivot_pct": .050001}, {}, {}, "EXTENDED_NO_CHASE"),
    ("P1", "INSUFFICIENT", FIRED, {"status": "AVAILABLE", "volume_acceleration_ratio": .60}, {}, "PARTICIPATION_CONTRADICTION_NARROWS_ENTRY"),
    ("P2", "INSUFFICIENT", FIRED, {"status": "AVAILABLE", "volume_acceleration_ratio": .600001}, {}, "FRESH_ENTRY_TRIGGER"),
    ("P3", "INSUFFICIENT", FIRED, {"status": "AVAILABLE", "relative_volume_percentile": .25}, {}, "PARTICIPATION_CONTRADICTION_NARROWS_ENTRY"),
    ("P4", "INSUFFICIENT", FIRED, {"status": "BLOCKED", "volume_acceleration_ratio": .1}, {}, "FRESH_ENTRY_TRIGGER"),
    ("M1", "INSUFFICIENT", FIRED, {}, {"market_regime": "NARROW_LEADERSHIP"}, "FRESH_ENTRY_TRIGGER"),
    ("O1", "INSUFFICIENT", {"market_structure_state": "SIDEWAYS", "trigger_state": "APPROACHING"}, {}, {}, "PENDING_DEFINED_CONFIRMATION"),
    ("O2", "INSUFFICIENT", {"market_structure_state": "SIDEWAYS"}, {}, {}, "OBSERVATIONAL_NO_ENTRY"),
]


def policy_case(case):
    _, fundamental, changes, participation, market, _ = case
    rec = tactical(**changes)
    phase, supports, counters = owner.evaluate_tactical_phase(rec)
    return owner.decide_research_action_posture(
        ticker="SYN", fundamental_state=fundamental, tactical_phase=phase, tactical_rec=rec,
        fund_supports=[], fund_counters=[], tac_supports=supports, tac_counters=counters,
        val_supports=[], val_counters=[], part_supports=[], part_counters=[],
        participation_summary=participation, market_sector_summary=market)


@pytest.mark.parametrize("case", CASES + BOUNDARIES, ids=lambda c: c[0])
def test_owner_reconciled_grok_first_match_matrix(case):
    posture, why, effect, klass = policy_case(case)
    assert klass == case[-1]
    assert posture == owner.POSTURE_CLASS_COMPATIBILITY[klass]
    assert posture != "HOLD"
    if klass == "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY":
        assert all(text in why for text in ("no fresh entry trigger", "not an entry instruction", case[1], "no owner position is inferred"))
        assert "awaiting" not in why.lower()


@pytest.mark.parametrize("fundamental", ["INSUFFICIENT", "MIXED", "IMPROVING", "STABLE", "TURNAROUND"])
def test_qualified_base_never_means_trade_entry(fundamental):
    result = policy_case(("BASE", fundamental, {"base_status": "IN_BASE", "ma20_slope_state": "FLAT"}, {}, {}, None))
    assert result[0] == "EARLY_WATCH" and result[3] == "BASE_UNCONFIRMED"


@pytest.mark.parametrize("changes", [
    {"eligible": False, **BEAR}, {"market_structure_state": "CONFLICTED", **BEAR},
    {"evidence_status": "CONFLICTING", **BEAR}, {"bos_state": "CONFLICTING", **FIRED},
    {"market_structure_state": "INSUFFICIENT_HISTORY", **BEAR},
])
def test_unqualified_or_conflicted_structure_cannot_create_adverse_or_entry(changes):
    posture, _, _, klass = policy_case(("UNQUALIFIED", "IMPROVING", changes, {}, {}, None))
    assert posture == "WAIT_FOR_CONFIRMATION" and klass == "UNQUALIFIED_TACTICAL_STRUCTURE"


@pytest.mark.parametrize("currency", ["CURRENT_SESSION", "LAST_TRADE_AS_OF:2026-08-27", "NO_CURRENT_EVIDENCE"])
@pytest.mark.parametrize("changes", [{}, FIRED, BEAR, FAILED, {**FIRED, "distance_to_pivot_pct": .12}])
def test_current_dated_absent_evidence_gate_and_original_conditions(changes, currency):
    a = integrated_decision(SESSION, ["SYN"], tactical_records={"SYN": tactical(**changes)},
                            currency_by_ticker={"SYN": currency})
    record = a["records"]["SYN"]
    owner.validate_posture_policy(record)
    assert record["decision_identity"] == owner.decision_identity(record)
    assert record["trigger"]["trigger_state"] == tactical(**changes)["trigger_state"]
    assert record["invalidation"]["invalidation_level"] == tactical(**changes)["invalidation_level"]
    if currency == "NO_CURRENT_EVIDENCE":
        assert record["research_action_posture"] == "INSUFFICIENT_CURRENT_RESEARCH"
        assert record["posture_condition_class"] == "MISSING_CURRENT_EVIDENCE"
        assert record["missing_evidence_decision_effect"] == owner.EFFECT_BLOCKS_DECISION
        assert "ungated_posture_condition_class" in record["evidence_currency_gate"]
    else:
        assert record["posture_condition_class"] != "MISSING_CURRENT_EVIDENCE"
    assert record["authority_boundary"]["is_actionable"] is False


def test_a1_a4_public_artifact_and_decision_identity_independent_of_all_private_states():
    artifacts = [integrated_decision(SESSION, ["SYN"], tactical_records={"SYN": tactical()},
                    currency_by_ticker={"SYN": "CURRENT_SESSION"}, portfolio_record=context)
                 for context in (None, {"status": "AVAILABLE", "is_held": True, "quantity": 123456},
                                 {"status": "AVAILABLE", "is_held": False},
                                 {"status": "AVAILABLE", "is_held": "UNRESOLVED", "private_secret": "SYN_PRIVATE"})]
    assert all(a == artifacts[0] for a in artifacts)
    assert "SYN_PRIVATE" not in json.dumps(artifacts)
    assert "ownership_context" not in artifacts[0]["records"]["SYN"]


@pytest.mark.parametrize("held", [True, False, None])
def test_constructive_trend_portfolio_only_hold_or_no_add_and_no_quantity(held):
    decision = integrated_decision(SESSION, ["SYN"], tactical_records={"SYN": tactical()},
                                  currency_by_ticker={"SYN": "CURRENT_SESSION"})["records"]["SYN"]
    state = (portfolio.derive_portfolio_state(portfolio_snapshot=make_snapshot(positions=[make_position("SYN", 10)] if held else []),
                                             prices={"SYN": 40}, sector_by_ticker={"SYN": "SYN_SECTOR"})
             if held is not None else {"status": "NOT_PROVIDED"})
    result = portfolio.build_ticker_portfolio_aware_decision(ticker="SYN", security_decision=decision, portfolio_state=state)
    assert result["sizing_mode"] == "NOT_APPLICABLE"
    assert result["portfolio_action_research"] == ("HOLD_EXISTING_NO_ACTION" if held else "NO_ADD" if held is False else "NOT_EVALUATED")
    if held is None:
        assert result["position_state"] == "CURRENT_POSITION_UNRESOLVED"
    assert result["posture_condition_class"] == decision["posture_condition_class"]


@pytest.mark.parametrize("before,after", [(None, "v2"), ("v1", "v2"), ("v2", "v1")])
def test_epoch_change_precedes_even_unchanged_posture_or_bearish_phase(before, after):
    prior = {"research_action_posture": "WAIT_FOR_CONFIRMATION", "tactical_phase": "TREND_CONTINUATION"}
    current = {"research_action_posture": "AVOID", "tactical_phase": "BREAKDOWN"}
    if before: prior["research_action_policy_version"] = before
    if after: current["research_action_policy_version"] = after
    assert next_brief._classify_posture_transition(prior, current) == "NOT_COMPARABLE_POLICY_CHANGE"
    current["research_action_posture"] = prior["research_action_posture"]
    assert next_brief._classify_posture_transition(prior, current) == "NOT_COMPARABLE_POLICY_CHANGE"


def test_v1_identity_readability_and_class_pair_tamper_refusal():
    legacy = {"ticker": "SYN", "research_action_posture": "HOLD", "tactical_phase": "TREND_CONTINUATION"}
    missing_epoch = owner.decision_identity(legacy)
    assert missing_epoch == "decision:SYN:bb4e33e57612f4dd"  # exact baseline v1 implementation
    legacy["research_action_policy_version"] = "v1"
    assert owner.decision_identity(legacy) == missing_epoch
    owner.validate_posture_policy(legacy)
    assert brief.classify_opportunity_set(legacy) == brief.HOLD_MANAGE
    new = integrated_decision(SESSION, ["SYN"], tactical_records={"SYN": tactical()},
                              currency_by_ticker={"SYN": "CURRENT_SESSION"})["records"]["SYN"]
    assert brief.classify_opportunity_set(new) == brief.CONSTRUCTIVE_NO_NEW_ENTRY
    assert new["research_action_posture"] not in portfolio.ADD_ELIGIBLE_POSTURES | portfolio.PROBE_ELIGIBLE_POSTURES
    new["posture_condition_class"] = "FRESH_ENTRY_TRIGGER"
    with pytest.raises(owner.IntegratedDecisionProductError, match="INCOMPATIBLE"):
        owner.validate_posture_policy(new)


def test_actual_epoch_transition_materialization_and_daily_class_groups(tmp_path):
    import daily_session_level2_package as level2
    previous = integrated_decision("2026-08-27", ["SYN"], tactical_records={"SYN": tactical()},
                                  currency_by_ticker={"SYN": "CURRENT_SESSION"})
    previous.pop("research_action_policy_version")
    legacy = previous["records"]["SYN"]
    legacy.pop("research_action_policy_version")
    legacy.pop("posture_condition_class")
    legacy["decision_identity"] = owner.decision_identity(legacy)
    previous.update(owner.content_identity(previous))
    current = integrated_decision(SESSION, ["SYN"], tactical_records={"SYN": tactical()},
                                 currency_by_ticker={"SYN": "CURRENT_SESSION"})
    for session, artifact in (("2026-08-27", previous), (SESSION, current)):
        path = level2.session_artifact_paths(tmp_path, session)["integrated_investment_decision_product"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact), encoding="utf-8")
    transition = next_brief._posture_transition(root=tmp_path, current_session=SESSION, previous_session="2026-08-27")
    assert transition["records"]["SYN"]["transition"] == "NOT_COMPARABLE_POLICY_CHANGE"
    assert "NOT_COMPARABLE_POLICY_CHANGE" in next_brief.POSTURE_TRANSITION_LABELS
    artifact = brief.build_artifact(session=SESSION, requested_at="synthetic",
        integrated_decision_current=current, next_session_brief={"current_session": SESSION, "posture_transition": transition})
    assert artifact["posture_condition_classes"]["CONSTRUCTIVE_TREND_NO_FRESH_ENTRY"]["tickers"] == ["SYN"]
    assert artifact["decision_surface_index"]["rows"][0]["research_action_policy_version"] == "v2"


def test_absent_price_evidence_gates_real_reduce_not_only_wait():
    deteriorating = _sample_financial_record(profitability_state="LOSS_MAKING", growth_state="CONTRACTING",
        balance_sheet_state="DETERIORATING", margin_state="MARGIN_COMPRESSING")
    source = integrated_decision(SESSION, ["SYN"], tactical_records={"SYN": tactical(**FAILED)},
        financial_records={"SYN": deteriorating}, currency_by_ticker={"SYN": "NO_CURRENT_EVIDENCE"})
    row = source["records"]["SYN"]
    assert row["evidence_currency_gate"]["ungated_policy_output"] == "REDUCE"
    assert row["posture_condition_class"] == "MISSING_CURRENT_EVIDENCE"


def test_actual_workspace_reads_legacy_v1_hold_without_class(tmp_path):
    import canonical_current_product_projections as projections
    from test_current_decision_surface_convergence import _workspace_inputs
    legacy = integrated_decision(SESSION, ["SYN"], currency_by_ticker={"SYN": "CURRENT_SESSION"})
    legacy["research_action_policy_version"] = "v1"
    row = legacy["records"]["SYN"]
    row.pop("research_action_policy_version")
    row.pop("posture_condition_class")
    row["research_action_posture"] = "HOLD"
    row["decision_identity"] = owner.decision_identity(row)
    legacy.update(owner.content_identity(legacy))
    result = projections.materialize_current_investment_decision_workspace(session=SESSION,
        registry_inputs=_workspace_inputs(["SYN"], session=SESSION), supplementary={}, requested_at="synthetic",
        integrated_investment_decision_product=legacy)
    card = result["workspace"]["cards"]["SYN"]
    assert card["research_action_posture"] == "HOLD"
    assert card["research_action_policy_version"] == "v1"
    assert card["posture_condition_class"] is None
    assert card["action_presentation"]["condition"] == "IF_CURRENTLY_HELD"


def test_actual_offline_packet_materialization_and_projection(tmp_path):
    import stocklookup_core.decision.current_opportunity_prioritization as opportunity
    integrated = integrated_decision(SESSION, ["SYN"], tactical_records={"SYN": tactical()},
                                    currency_by_ticker={"SYN": "CURRENT_SESSION"})
    source = {"contract_version": "current_opportunity_prioritization/v1", "research_session": SESSION,
              "records": {"SYN": {"priority_tier": "MONITOR"}}}
    source.update(opportunity.content_identity(source))
    result = packet.build_artifact(opportunity=source, integrated_decision=integrated)
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    retained = json.loads(path.read_text(encoding="utf-8"))
    packet.replay(retained)
    view = packet_product.project_shadow_panel(retained)
    assert view is not None
    projected = packet_product.project_ticker(retained["records"]["SYN"], retained)
    assert projected["security_decision"] == retained["records"]["SYN"]["security_decision"]
    assert projected["security_decision"]["posture_condition_class"] == "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY"
    import canonical_post_close_pipeline as canonical
    actual = canonical.build_decision_packet(tmp_path, SESSION, opportunity=source,
        enrichment={"integrated_investment_decision_product": {"artifact": integrated}})
    assert actual["records"]["SYN"]["security_decision"] == projected["security_decision"]
    malformed = copy.deepcopy(retained)
    malformed["records"]["SYN"]["security_decision"]["posture_condition_class"] = "FRESH_ENTRY_TRIGGER"
    malformed.update(packet.content_identity(malformed))
    with pytest.raises(owner.IntegratedDecisionProductError, match="INCOMPATIBLE"):
        packet.replay(malformed)
    broken = copy.deepcopy(integrated)
    broken["records"]["SYN"]["posture_condition_class"] = "FRESH_ENTRY_TRIGGER"
    broken.update(owner.content_identity(broken))
    with pytest.raises(owner.IntegratedDecisionProductError, match="INCOMPATIBLE"):
        packet.build_artifact(opportunity=source, integrated_decision=broken)


def _opportunity(tickers):
    import stocklookup_core.decision.current_opportunity_prioritization as opportunity
    source = {"contract_version": "current_opportunity_prioritization/v1", "research_session": SESSION,
              "records": {ticker: {"priority_tier": "MONITOR"} for ticker in tickers}}
    source.update(opportunity.content_identity(source))
    return source


def test_packet_keeps_official_opportunity_universe_when_integrated_decision_is_wider():
    integrated = integrated_decision(SESSION, ["OUT", "SYN"],
        tactical_records={"OUT": tactical(), "SYN": tactical()},
        currency_by_ticker={"OUT": "CURRENT_SESSION", "SYN": "CURRENT_SESSION"})
    result = packet.build_artifact(opportunity=_opportunity(["SYN"]), integrated_decision=integrated)
    assert set(result["records"]) == {"SYN"}
    assert "OUT" not in result["records"]
    assert result["records"]["SYN"]["security_decision"]["decision_identity"] == integrated["records"]["SYN"]["decision_identity"]
    packet.replay(result)
    equal = packet.build_artifact(opportunity=_opportunity(["SYN"]), integrated_decision=integrated_decision(
        SESSION, ["SYN"], tactical_records={"SYN": tactical()}, currency_by_ticker={"SYN": "CURRENT_SESSION"}))
    assert set(equal["records"]) == {"SYN"}


def test_packet_rejects_opportunity_ticker_absent_from_integrated_decision():
    integrated = integrated_decision(SESSION, ["OUT"], tactical_records={"OUT": tactical()},
                                    currency_by_ticker={"OUT": "CURRENT_SESSION"})
    with pytest.raises(packet.CurrentResearchDecisionPacketError, match="INTEGRATED_DECISION_PACKET_BINDING_INVALID"):
        packet.build_artifact(opportunity=_opportunity(["SYN"]), integrated_decision=integrated)
