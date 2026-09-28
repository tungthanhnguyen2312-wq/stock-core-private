"""CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1: the promotion blockers of the fundamental chain.

Evidence availability is five explicit states, apart from the direction; the risk level is read
from qualified LEVEL evidence only, never from a direction; one balance-sheet observation casts one
vote; a sign transition votes only on a comparable basis; an unresolved entity family never votes;
a post-session quarter label is a non-calendar fiscal label only when its evidence was known by the
session; and a fundamental policy epoch keeps states from different policies from being compared.
"""
from __future__ import annotations

import sys

import asymmetric_dislocation_research as adr
import current_research_decision_input as decision_input
import financial_analysis_engine_v2 as engine
import financial_analysis_product_projection as projection
import fundamental_signal_consumption_contract as contract
import integrated_investment_decision_product as iidp
import market_wide_financial_analysis_v2_scaleout as scaleout
import multi_session_signal_velocity as velocity
import next_session_decision_brief as next_brief
import prospective_decision_outcome_feedback as feedback
import prospective_decision_outcome_measurement as measurement

SESSION = "2026-09-24"  # last completed quarter 2026-Q2
CURRENT_PERIOD = "2026-Q2"
STALE_PERIOD = "2012-Q4"
FISCAL_LABEL = "2026-Q3"  # calendar end 2026-09-30, after the session
KNOWN_BEFORE_SESSION = "2026-09-05T00:00:00+07:00"
_SOURCES = ("net_income_sign", "net_margin", "net_margin_direction", "gross_margin_direction", "revenue_qoq",
            "revenue_same_quarter_yoy", "net_income_qoq", "net_income_same_quarter_yoy", "net_income_ttm_yoy",
            "cfo_to_net_income", "cfo_to_net_income_ttm", "equity_to_assets_direction", "debt_to_equity_direction",
            "net_working_capital_direction", "current_ratio_direction", "net_working_capital",
            "free_cash_flow_proxy_direction", "bank_npl_ratio", "bank_ldr", "bank_cir", "brokerage_revenue_mix")


def _compact(periods: dict | None = None, fitness: dict | None = None, known_at: str | None = None, **states) -> dict:
    record = {
        "contract_version": projection.COMPACT_CONTRACT, "status": "AVAILABLE",
        "analysis_family": "INDUSTRIAL_FINANCIAL_ANALYSIS", "issuer_type": "corporate",
        "profitability_state": "UNAVAILABLE", "margin_state": "UNAVAILABLE", "growth_state": "UNAVAILABLE",
        "earnings_turnaround_state": "UNAVAILABLE", "cash_conversion_state": "UNAVAILABLE",
        "balance_sheet_state": "UNAVAILABLE", "leverage_state": "UNAVAILABLE", "capital_efficiency_state": "UNAVAILABLE",
        "resilience_state": "UNAVAILABLE", "working_capital_state": "WORKING_CAPITAL_UNAVAILABLE",
        "working_capital_trajectory_state": "UNAVAILABLE", "current_ratio_trajectory_state": "UNAVAILABLE",
        "gross_margin_trajectory_state": "UNAVAILABLE", "free_cash_flow_proxy_direction_state": "UNAVAILABLE",
        "bank_asset_quality_state": "NOT_APPLICABLE", "bank_funding_state": "NOT_APPLICABLE",
        "bank_efficiency_state": "NOT_APPLICABLE", "fvtpl_asset_intensity_trajectory_state": "NOT_APPLICABLE",
        "margin_lending_intensity_trajectory_state": "NOT_APPLICABLE", "brokerage_mix_trajectory_state": "NOT_APPLICABLE",
        "feature_fitness": {feature: {"fitness": "READY", "reason_codes": [], "as_of_period": CURRENT_PERIOD}
                            for feature in _SOURCES},
    }
    if known_at:
        record["lineage"] = {"source_identities": {"period_semantics_knowledge_time": known_at}}
    record.update(states)
    for feature, period in (periods or {}).items():
        record["feature_fitness"][feature]["as_of_period"] = period
    for feature, entry in (fitness or {}).items():
        record["feature_fitness"][feature] = {"reason_codes": [], "as_of_period": CURRENT_PERIOD, **entry}
    return record


def _synthesis(record: dict, session: str | None = SESSION) -> dict:
    return iidp.evaluate_fundamental_synthesis(record, decision_session=session)


def _signal(synthesis: dict, signal_id: str) -> dict:
    return next(signal for signal in synthesis["signals"] if signal["signal_id"] == signal_id)


def _decision(record: dict, tactical: dict | None = None) -> dict:
    return iidp.build_ticker_integrated_decision(
        ticker="AAA", as_of_session=SESSION, tactical_record=tactical, financial_record=record,
        valuation_record=None, relative_volume_record=None, market_sector_record=None)


# ── Risk level versus direction ──────────────────────────────────────────────────────────────

def test_improving_direction_never_implies_a_healthy_risk_level() -> None:
    synthesis = _synthesis(_compact(profitability_state="LOSS_MAKING", balance_sheet_state="STRENGTHENING",
                                    leverage_state="IMPROVING", current_ratio_trajectory_state="CURRENT_RATIO_IMPROVING"))
    risk = synthesis["fundamental_risk_level"]
    assert risk["state"] == contract.ADVERSE_LEVEL_CURRENT
    assert risk["adverse_level_dimensions"] == ["PROFITABILITY"]
    assert (risk["derived_from_direction"], risk["healthy_level_asserted"]) == (False, False)
    assert set(risk["unassessed_level_dimensions"]) == {"CAPITAL_STRUCTURE", "MARGINS", "SHORT_TERM_LIQUIDITY"}
    # A direction alone establishes no level at all.
    only_direction = _synthesis(_compact(leverage_state="IMPROVING", balance_sheet_state="STRENGTHENING"))
    assert only_direction["fundamental_state"] in (contract.FUNDAMENTAL_STABLE, contract.FUNDAMENTAL_IMPROVING)
    assert only_direction["fundamental_risk_level"]["state"] == contract.LEVEL_UNKNOWN


def test_constructive_level_is_never_called_healthy_and_stale_adverse_stays_known() -> None:
    profitable = _synthesis(_compact(profitability_state="PROFITABLE"))["fundamental_risk_level"]
    assert profitable["state"] == contract.NO_QUALIFIED_ADVERSE_LEVEL
    assert profitable["constructive_current_level_without_adverse"] is True
    assert "HEALTHY" not in profitable["state"]
    stale = _synthesis(_compact(profitability_state="LOSS_MAKING", periods={"net_income_sign": STALE_PERIOD}))
    assert stale["fundamental_risk_level"]["state"] == contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT
    assert stale["fundamental_risk_level"]["level_dimensions"]["PROFITABILITY"]["currency"] == "NOT_CURRENT"
    # The negative net-working-capital sign stays a descriptive observation, never an adverse level.
    nwc = _synthesis(_compact(working_capital_state="NEGATIVE_NET_WORKING_CAPITAL"))["fundamental_risk_level"]
    assert nwc["state"] == contract.LEVEL_UNKNOWN
    assert nwc["descriptive_level_observations"]["net_working_capital_level"]["observed"] == "NEGATIVE_NET_WORKING_CAPITAL"


# ── Evidence availability (five states) ──────────────────────────────────────────────────────

def test_evidence_exists_while_direction_is_insufficient() -> None:
    stale = _synthesis(_compact(profitability_state="LOSS_MAKING", periods={f: STALE_PERIOD for f in _SOURCES}))
    assert (stale["fundamental_state"], stale["fundamental_evidence_availability"]) == (
        contract.FUNDAMENTAL_INSUFFICIENT, contract.STALE_ONLY)
    neutral = _synthesis(_compact(margin_state="MARGIN_STABLE"))
    assert (neutral["fundamental_state"], neutral["fundamental_evidence_availability"]) == (
        contract.FUNDAMENTAL_INSUFFICIENT, contract.CURRENT_NON_DIRECTIONAL)
    directional = _synthesis(_compact(profitability_state="PROFITABLE"))
    assert directional["fundamental_evidence_availability"] == contract.CURRENT_DIRECTIONAL
    absent = iidp.evaluate_fundamental_synthesis({"status": "ABSENT"}, decision_session=SESSION)
    assert absent["fundamental_evidence_availability"] == contract.ABSENT


def test_known_evidence_is_never_described_as_missing_fundamental_data() -> None:
    record = _compact(profitability_state="LOSS_MAKING", periods={f: STALE_PERIOD for f in _SOURCES})
    decision = _decision(record)
    assert decision["research_action_posture"] == iidp.POSTURE_INSUFFICIENT  # posture policy unchanged
    assert decision["fundamental_evidence_availability"] == contract.STALE_ONLY
    assert "fundamental analysis data" not in decision["why_now"] and "stale-only" in decision["why_now"]
    assert decision["evidence_axes"]["FUNDAMENTAL"]["blocker_reason_codes"] == [
        "FUNDAMENTAL_STALE_EVIDENCE_ONLY_NO_CURRENT_DIRECTION"]
    fundamental = decision["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]
    assert (fundamental["state"], fundamental["fundamental_evidence_availability"]) == (decision_input.AVAILABLE, contract.STALE_ONLY)
    assert fundamental["risk_level"]["state"] == contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT
    absent = _decision({"status": "ABSENT"})
    assert "fundamental analysis data" in absent["why_now"]  # truly absent keeps the original wording
    assert absent["evidence_axes"]["FUNDAMENTAL"]["blocker_reason_codes"] == ["FUNDAMENTAL_CONTEXT_ABSENT"]


# ── One vote per economic balance-sheet event ─────────────────────────────────────────────────

def _row(metric, value, period, *, semantic="STANDALONE_QUARTER"):
    source = f"AAA_KBS_{'income' if semantic == 'STANDALONE_QUARTER' else 'balance'}"
    return {"ticker": "AAA", "canonical_metric": metric, "reported_value": value, "native_period_label": period,
            "period_end": period, "period_semantic_state": semantic, "source_status": "provider_reported",
            "lineage_complete": True, "source_conflicts": [], "statement_scope": "consolidated",
            "normalized_candidate_unit": {"currency": "unknown", "scale": "unknown"},
            "source_lineage": {"provider": "KBS", "source_file": source, "source_sha256": "sha", "fact_id": f"{metric}-{period}"}}


def _engine_compact(balance: dict, net_income: dict | None = None) -> dict:
    net_income = net_income or {"2025-Q2": 5, "2026-Q1": 5, "2026-Q2": 5}
    rows = [_row("net_income", value, period) for period, value in net_income.items()]
    rows += [_row("revenue", value, period) for period, value in {"2025-Q2": 100, "2026-Q1": 100, "2026-Q2": 100}.items()]
    for metric, (prior, current) in balance.items():
        rows += [_row(metric, prior, "2025-Q2", semantic="POINT_IN_TIME_BALANCE_SHEET"),
                 _row(metric, current, "2026-Q2", semantic="POINT_IN_TIME_BALANCE_SHEET")]
    artifact = engine.build_artifact(tickers=["AAA"], rows=rows, issuer_types={"AAA": "corporate"},
                                     source_identities={"semantics": "test"}, requested_at="2026-09-24T15:00:00+07:00")
    return projection.build_product_projection(financial_context=artifact, product_tickers=["AAA"],
                                               requested_at="2026-09-24T15:00:00+07:00")["records"]["AAA"]


def test_single_short_term_borrowing_casts_one_capital_structure_vote() -> None:
    # One event: borrow 100 short-term, hold it as cash. Current assets and current liabilities both
    # rise by 100; debt rises by 100; equity is unchanged.
    record = _engine_compact({"total_assets": (1000, 1100), "shareholders_equity": (400, 400),
                              "total_interest_bearing_debt": (300, 400), "current_assets": (500, 600),
                              "current_liabilities": (300, 400)})
    assert (record["balance_sheet_state"], record["leverage_state"], record["current_ratio_trajectory_state"]) == (
        "DETERIORATING", "WORSENING", "CURRENT_RATIO_WORSENING")
    synthesis = _synthesis(record)
    derivation = synthesis["derivation"]
    assert derivation["adverse_votes"] == ["CAPITAL_STRUCTURE.DIRECTION"]
    assert derivation["favorable_votes"] == ["PROFITABILITY.LEVEL"]
    group = derivation["vote_grouping"]["groups"][0]
    assert (group["outcome"], group["counted"], group["folded"], group["shared_observation"]) == (
        "SAME_OBSERVATION_AGREEING_COUNTED_ONCE", "CAPITAL_STRUCTURE.DIRECTION", ["SHORT_TERM_LIQUIDITY.DIRECTION"], ["2026-Q2"])
    # Both labels stay visible; the event is counted once, so a profitable issuer reads MIXED, not DETERIORATING.
    assert synthesis["dimensions"]["SHORT_TERM_LIQUIDITY"]["direction"] == contract.WORSENING
    assert synthesis["dimensions"]["SHORT_TERM_LIQUIDITY"]["vote_counted_once_with"] == ["CAPITAL_STRUCTURE.DIRECTION"]
    assert synthesis["fundamental_state"] == contract.FUNDAMENTAL_MIXED


def test_opposing_capital_structure_and_current_ratio_dimensions_both_stay() -> None:
    # Long-term borrowing held as cash: current ratio improves while debt/equity worsens.
    record = _engine_compact({"total_assets": (1000, 1100), "shareholders_equity": (400, 400),
                              "total_interest_bearing_debt": (300, 400), "current_assets": (500, 600),
                              "current_liabilities": (300, 300)})
    synthesis = _synthesis(record)
    derivation = synthesis["derivation"]
    assert "CAPITAL_STRUCTURE.DIRECTION" in derivation["adverse_votes"]
    assert "SHORT_TERM_LIQUIDITY.DIRECTION" in derivation["favorable_votes"]
    assert derivation["vote_grouping"]["groups"][0]["outcome"] == "OPPOSING_DIMENSIONS_PRESERVED"
    assert derivation["vote_grouping"]["folded_votes"] == []


def test_distinct_balance_sheet_observations_count_separately() -> None:
    synthesis = _synthesis(_compact(balance_sheet_state="DETERIORATING", current_ratio_trajectory_state="CURRENT_RATIO_WORSENING",
                                    periods={"current_ratio_direction": "2026-Q1"}))
    assert synthesis["derivation"]["adverse_votes"] == ["CAPITAL_STRUCTURE.DIRECTION", "SHORT_TERM_LIQUIDITY.DIRECTION"]
    assert synthesis["derivation"]["vote_grouping"]["groups"][0]["outcome"] == "DISTINCT_OBSERVATIONS_COUNTED_SEPARATELY"


def test_equity_to_assets_leverage_duplicate_never_casts_a_second_vote() -> None:
    fallback = _synthesis(_compact(balance_sheet_state="DETERIORATING", leverage_state="WORSENING",
                                   fitness={"debt_to_equity_direction": {"fitness": "BLOCKED_BY_EVIDENCE"}}))
    duplicate = _signal(fallback, "debt_to_equity_direction")
    assert duplicate["role"] == contract.EVIDENCE_ONLY and duplicate["decision_eligible"] is False
    assert fallback["derivation"]["adverse_votes"] == ["CAPITAL_STRUCTURE.DIRECTION"]
    both = _synthesis(_compact(balance_sheet_state="DETERIORATING", leverage_state="WORSENING"))
    assert both["derivation"]["adverse_votes"] == ["CAPITAL_STRUCTURE.DIRECTION"]  # one dimension, one vote


# ── Transition basis ──────────────────────────────────────────────────────────────────────────

def test_qoq_profit_to_loss_is_visible_but_never_drives_direction_or_posture() -> None:
    tactical = {"eligible": True, "market_structure_state": "EARLY_BEARISH_REVERSAL"}
    base = {"profitability_state": "LOSS_MAKING", "balance_sheet_state": "STRENGTHENING"}
    qoq = _decision(_compact(**base, earnings_turnaround_state="PROFIT_TO_LOSS",
                             fitness={"net_income_qoq": {"fitness": "READY", "semantic_transition": "PROFIT_TO_LOSS",
                                                         "growth_basis": "QOQ_STANDALONE"}}), tactical)
    none = _decision(_compact(**base), tactical)
    yoy = _decision(_compact(**base, earnings_turnaround_state="PROFIT_TO_LOSS",
                             fitness={"net_income_same_quarter_yoy": {"fitness": "READY", "semantic_transition": "PROFIT_TO_LOSS",
                                                                      "growth_basis": "SAME_QUARTER_YOY"}}), tactical)
    assert (qoq["fundamental_state"], qoq["research_action_posture"]) == (none["fundamental_state"], none["research_action_posture"])
    transition = next(item for item in qoq["fundamental_synthesis"]["transitions"] if item["value"] == contract.PROFIT_TO_LOSS)
    assert (transition["basis"], transition["decision_eligible"], transition["non_vote_reason"]) == (
        "QOQ_STANDALONE", False, contract.SEQUENTIAL_TRANSITION_NOT_A_VOTE)
    assert qoq["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["components"]["transition_observations"] == [
        {"value": contract.PROFIT_TO_LOSS, "basis": "QOQ_STANDALONE", "non_vote_reason": contract.SEQUENTIAL_TRANSITION_NOT_A_VOTE}]
    # A governed comparable basis may drive the direction (and so the posture).
    assert "PROFITABILITY.TRANSITION" in yoy["fundamental_synthesis"]["derivation"]["adverse_votes"]
    assert yoy["fundamental_state"] == contract.FUNDAMENTAL_DETERIORATING
    assert yoy["research_action_posture"] != none["research_action_posture"]


def test_a_transition_seen_on_both_bases_is_read_on_the_comparable_basis() -> None:
    both = {"fitness": "READY", "semantic_transition": "PROFIT_TO_LOSS"}
    synthesis = _synthesis(_compact(profitability_state="LOSS_MAKING", earnings_turnaround_state="PROFIT_TO_LOSS",
                                    fitness={"net_income_qoq": {**both, "growth_basis": "QOQ_STANDALONE"},
                                             "net_income_same_quarter_yoy": {**both, "growth_basis": "SAME_QUARTER_YOY"}}))
    transition = _signal(synthesis, "earnings_transition")
    assert (transition["fitness"]["basis"], transition["decision_eligible"]) == ("SAME_QUARTER_YOY", True)


# ── Entity family ─────────────────────────────────────────────────────────────────────────────

def test_generic_and_limited_families_never_cast_industrial_votes() -> None:
    states = {"profitability_state": "PROFITABLE", "balance_sheet_state": "STRENGTHENING", "leverage_state": "IMPROVING",
              "margin_state": "MARGIN_EXPANDING", "current_ratio_trajectory_state": "CURRENT_RATIO_IMPROVING"}
    for family, issuer, expected in (
            ("UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS", "unknown", contract.ENTITY_FAMILY_UNRESOLVED),
            ("OTHER_FINANCIAL_LIMITED_ANALYSIS", "finance_company", contract.ENTITY_NO_DECISION_SIGNAL_FAMILY),
            ("OTHER_FINANCIAL_LIMITED_ANALYSIS", "insurance", contract.ENTITY_NO_DECISION_SIGNAL_FAMILY),
            ("OTHER_FINANCIAL_LIMITED_ANALYSIS", "bank", contract.ENTITY_SPECIALIST_SIGNALS_ONLY)):
        synthesis = _synthesis(_compact(analysis_family=family, issuer_type=issuer, **states))
        assert synthesis["entity_decision_applicability"] == expected
        assert [s["signal_id"] for s in synthesis["signals"] if s["decision_eligible"]] == [], family
        assert synthesis["fundamental_state"] == contract.FUNDAMENTAL_INSUFFICIENT
        assert synthesis["fundamental_evidence_availability"] == contract.NOT_APPLICABLE_ENTITY
    # A consumer-finance-like issuer the classifier left generic keeps its evidence for research only.
    generic = _synthesis(_compact(analysis_family="UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS", issuer_type="unknown", **states))
    assert generic["strengths"] == ["profitability_level"]
    assert _signal(generic, "equity_to_assets_direction")["non_vote_reason"] == contract.ENTITY_UNRESOLVED_NOT_A_VOTE
    # Bank specialist signals still vote for a bank.
    bank = _synthesis(_compact(analysis_family="OTHER_FINANCIAL_LIMITED_ANALYSIS", issuer_type="bank",
                               bank_asset_quality_state="IMPROVING"))
    assert [s["signal_id"] for s in bank["signals"] if s["decision_eligible"]] == ["bank_asset_quality_direction"]


# ── Fiscal-period knowledge time ─────────────────────────────────────────────────────────────

def test_post_session_label_known_before_session_is_fiscal_research_evidence_never_a_vote() -> None:
    record = _compact(profitability_state="LOSS_MAKING", periods={"net_income_sign": FISCAL_LABEL}, known_at=KNOWN_BEFORE_SESSION)
    synthesis = _synthesis(record)
    signal = _signal(synthesis, "profitability_level")
    assert signal["fitness"]["freshness"] == contract.NON_CALENDAR_FISCAL_PERIOD
    assert (signal["research_usable"], signal["decision_eligible"]) == (True, False)
    assert signal["non_vote_reason"] == contract.FISCAL_CALENDAR_UNRESOLVED_NOT_A_VOTE
    assert synthesis["research_observations"]["profitability_level"]["non_vote_reason"] == contract.FISCAL_CALENDAR_UNRESOLVED_NOT_A_VOTE
    assert synthesis["fundamental_evidence_availability"] == contract.STALE_ONLY
    assert synthesis["fundamental_risk_level"]["state"] == contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT
    assert contract.fiscal_period_semantics(FISCAL_LABEL, SESSION, KNOWN_BEFORE_SESSION)["calendar_period"] == (
        "UNRESOLVED_NO_GOVERNED_FISCAL_YEAR_REGISTRY")


def test_post_session_label_without_knowledge_proof_fails_closed() -> None:
    for known_at in (None, "2026-10-15T00:00:00+07:00"):
        synthesis = _synthesis(_compact(profitability_state="LOSS_MAKING", periods={"net_income_sign": FISCAL_LABEL}, known_at=known_at))
        signal = _signal(synthesis, "profitability_level")
        assert (signal["research_usable"], signal["decision_eligible"]) == (False, False)
        assert "KNOWLEDGE_TIME_UNPROVEN_FAIL_CLOSED" in signal["reason_codes"]
        assert synthesis["weaknesses"] == []
    # A label that ended before the session is read as calendar, whatever the knowledge time says.
    assert contract.fiscal_period_semantics("2026-Q2", SESSION, KNOWN_BEFORE_SESSION)["status"] == "CALENDAR_READING_NOT_AFTER_SESSION"


def test_engine_lineage_carries_the_period_semantics_knowledge_time() -> None:
    rows = [_row("net_income", 5, period) for period in ("2025-Q2", "2026-Q2")]
    store = {"AAA": {"ticker": "AAA", "entity_type": "corporate", "entity_applicability": "ENTITY_SPECIFIC", "features": {}}}
    artifact = scaleout.build_scaleout(semantic_rows=rows, feature_records=store,
                                       feature_store_artifact={"artifact_identity": "store:1"},
                                       period_semantics_identity="semantics:1", requested_at="2026-09-24T15:00:00+07:00",
                                       period_semantics_knowledge_time=KNOWN_BEFORE_SESSION)
    compact = projection.build_product_projection(financial_context=artifact, product_tickers=["AAA"],
                                                  requested_at="2026-09-24T15:00:00+07:00")["records"]["AAA"]
    assert contract.evidence_known_at(compact) == KNOWN_BEFORE_SESSION
    without = scaleout.build_scaleout(semantic_rows=rows, feature_records=store,
                                      feature_store_artifact={"artifact_identity": "store:1"},
                                      period_semantics_identity="semantics:1", requested_at="2026-09-24T15:00:00+07:00")
    assert "period_semantics_knowledge_time" not in without["source_identities"]


# ── Policy epoch ──────────────────────────────────────────────────────────────────────────────

def test_policy_epoch_is_explicit_resolved_for_history_and_part_of_decision_identity() -> None:
    decision = _decision(_compact(profitability_state="PROFITABLE"))
    assert decision["fundamental_decision_policy_version"] == contract.DECISION_POLICY_VERSION
    assert contract.policy_epoch(decision) == contract.DECISION_POLICY_VERSION
    assert contract.policy_epoch({"fundamental_state": "MIXED"}) == contract.LEGACY_POLICY_EPOCH
    assert contract.policy_epoch({"fundamental_synthesis": {"signal_policy": "fundamental_signal_policy_hardening/v1"}}) == (
        "fundamental_signal_policy_hardening/v1")
    assert contract.policy_epoch({"fundamental_synthesis": {}}) == contract.CONSUMPTION_POLICY_EPOCH
    other = {**decision, "fundamental_decision_policy_version": "fundamental_signal_policy_hardening/v1"}
    assert iidp.decision_identity(other) != iidp.decision_identity(decision)


def _velocity_row(record: dict, session: str) -> dict:
    axis = velocity._axis(record, "fundamental_trajectory")
    axis["session"] = session
    return axis


def test_policy_epoch_blocks_false_velocity_transitions() -> None:
    legacy = {"fundamental_state": "MIXED", "evidence_axes": {"FUNDAMENTAL": {"state": "MIXED"}}}
    current = _decision(_compact(profitability_state="LOSS_MAKING", balance_sheet_state="DETERIORATING"))
    assert current["fundamental_state"] == contract.FUNDAMENTAL_DETERIORATING
    cross = velocity._trajectory("fundamental_trajectory", [_velocity_row(legacy, "2026-09-23"), _velocity_row(current, SESSION)])
    assert cross["latest_transition"] == contract.NOT_COMPARABLE_POLICY_CHANGE
    assert cross["policy_epoch_excluded_observation_count"] == 1
    same = velocity._trajectory("fundamental_trajectory", [
        _velocity_row(_decision(_compact(profitability_state="PROFITABLE")), "2026-09-23"), _velocity_row(current, SESSION)])
    assert same["latest_transition"] == "DETERIORATING"


def test_next_session_posture_transition_across_epochs_is_not_comparable() -> None:
    previous = {"research_action_posture": "WAIT_FOR_CONFIRMATION", "tactical_phase": "BASE_BUILDING", "fundamental_state": "MIXED"}
    current = {"research_action_posture": "AVOID", "tactical_phase": "BASE_BUILDING", "fundamental_state": "DETERIORATING",
               "fundamental_decision_policy_version": contract.DECISION_POLICY_VERSION}
    assert next_brief._classify_posture_transition(previous, current) == contract.NOT_COMPARABLE_POLICY_CHANGE
    # The same fundamental state across epochs: the posture change is non-fundamental and stays comparable.
    assert next_brief._classify_posture_transition({**previous, "fundamental_state": "DETERIORATING"}, current) == "POSTURE_CHANGED_OTHER"


def test_outcome_feedback_and_measurement_reject_cross_policy_comparison() -> None:
    pending = {"forward_outcomes": {"horizons": {"forward_close_return_5": {"status": "PENDING"}}}}
    rows = [{**pending, "fundamental_decision_policy_version": contract.LEGACY_POLICY_EPOCH},
            {**pending, "fundamental_decision_policy_version": contract.DECISION_POLICY_VERSION}]
    summary = feedback._summary({"DETERIORATING": rows}, dimension="evidence_axis_state")
    assert [(row["fundamental_decision_policy_version"], row["sample_size"]) for row in summary["groups"]] == [
        (contract.DECISION_POLICY_VERSION, 1), (contract.LEGACY_POLICY_EPOCH, 1)]
    assert summary["cross_policy_epoch_comparison"] == contract.NOT_COMPARABLE_POLICY_CHANGE
    outcome = {"horizons": {h: {"status": "PENDING", "return": None} for h in measurement.HORIZONS},
               "confirmation": {"status": "PENDING"}, "invalidation": {"status": "PENDING"}}
    cohort = measurement.cohort_observation_summary([
        {**outcome, "fundamental_context_at_t0": "DETERIORATING", "fundamental_decision_policy_version_at_t0": contract.LEGACY_POLICY_EPOCH},
        {**outcome, "fundamental_context_at_t0": "DETERIORATING", "fundamental_decision_policy_version_at_t0": contract.DECISION_POLICY_VERSION}])
    fundamental = [row for row in cohort["groups"] if row["axis"] == "fundamental_state"]
    assert len(fundamental) == 2 and all(row["case_count"] == 1 for row in fundamental)


# ── Valuation labelling and determinism ───────────────────────────────────────────────────────

def test_research_p_b_never_reads_as_an_exact_common_shareholder_claim() -> None:
    research = {"status": "RESEARCH_USABLE", "value": 1.25, "equity_definition": "TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT",
                "limitations": ["CURRENT_RESEARCH_ONLY", "NCI_NOT_DEDUCTED"]}
    summary, _s, _c, uncertainties = iidp.evaluate_valuation_context(
        {"methods": {"P/B_CURRENT_RESEARCH": research, "P/B": {"status": "INPUT_BLOCKED", "value": None}}}, {})
    assert summary["pb_multiple"] == 1.25  # the value is unchanged
    assert summary["pb_basis"]["claim"] == "RESEARCH_ONLY_NOT_EXACT_NOT_COMMON_SHAREHOLDER"
    assert "NCI_NOT_DEDUCTED" in summary["pb_basis"]["limitations"]
    assert "P_B_IS_RESEARCH_TOTAL_EQUITY_NCI_NOT_DEDUCTED_NOT_COMMON_SHAREHOLDER" in uncertainties
    exact, *_ = iidp.evaluate_valuation_context({"methods": {"P/B": {"status": "READY", "value": 2.0}}}, {})
    assert exact["pb_basis"] == {"method": "P/B", "claim": None}
    # The dislocation research carries the basis with the multiple.
    record = {"fundamental_state": "STABLE", "valuation_context_summary": summary}
    assert adr.evaluate_valuation_dislocation(record)["pb_basis"]["claim"] == "RESEARCH_ONLY_NOT_EXACT_NOT_COMMON_SHAREHOLDER"


def test_evaluation_is_deterministic_and_makes_no_network_or_provider_call() -> None:
    events: list[str] = []

    def hook(event: str, _args: tuple) -> None:
        if event.startswith(("socket.", "http.client", "urllib")):
            events.append(event)

    sys.addaudithook(hook)
    record = _compact(profitability_state="LOSS_MAKING", balance_sheet_state="DETERIORATING",
                      current_ratio_trajectory_state="CURRENT_RATIO_WORSENING", known_at=KNOWN_BEFORE_SESSION)
    first, second = _decision(record), _decision(record)
    assert first == second
    adr.build_ticker_record(ticker="AAA", session=SESSION, integrated_record=first)
    assert events == []


def test_changed_decision_modules_never_import_a_provider() -> None:
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    probe = ("import sys; import fundamental_signal_consumption_contract, integrated_investment_decision_product, "
             "asymmetric_dislocation_research, multi_session_signal_velocity, next_session_decision_brief, "
             "prospective_decision_outcome_feedback, prospective_decision_outcome_measurement, current_research_decision_input; "
             "print(sorted(m for m in sys.modules if m.split('.')[0] in ('vnstock', 'vnai', 'vnstock_data')))")
    completed = subprocess.run([sys.executable, "-c", probe], cwd=root, capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == "[]"
