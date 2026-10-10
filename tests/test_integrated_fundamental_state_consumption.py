"""INTEGRATED_FUNDAMENTAL_STATE_CONSUMPTION_RECONCILIATION_V1: the fundamental signal contract.

Level, direction and transition stay separate; the producer's own vocabulary maps deterministically;
freshness and entity applicability gate what may enter the fundamental synthesis. The vote policy
is the FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1 one (only CURRENT periods vote; the working-capital
amount trajectory is evidence only); ``test_fundamental_signal_policy_hardening`` covers it in depth.
"""
from __future__ import annotations

import sys

import stocklookup_core.financial.financial_analysis_engine_v2 as engine
import stocklookup_core.financial.financial_analysis_product_projection as projection
import stocklookup_core.financial.fundamental_signal_consumption_contract as contract
import stocklookup_core.decision.integrated_investment_decision_product as iidp

SESSION = "2026-09-24"  # last completed quarter 2026-Q2
CURRENT_PERIOD = "2026-Q2"
STALE_PERIOD = "2024-Q4"
FUTURE_PERIOD = "2026-Q3"
_SOURCES = ("net_income_sign", "net_margin", "net_margin_direction", "gross_margin_direction", "revenue_qoq",
            "revenue_same_quarter_yoy", "net_income_qoq", "net_income_same_quarter_yoy", "net_income_ttm_yoy",
            "cfo_to_net_income", "cfo_to_net_income_ttm", "equity_to_assets_direction", "debt_to_equity_direction",
            "net_working_capital_direction", "current_ratio_direction", "net_working_capital",
            "free_cash_flow_proxy_direction")


def _compact(periods: dict | None = None, fitness: dict | None = None, **states) -> dict:
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


# ── Direction versus level ────────────────────────────────────────────────────────────────────

def test_improving_leverage_direction_never_implies_a_safe_level() -> None:
    synthesis = _synthesis(_compact(leverage_state="IMPROVING"))
    signal = _signal(synthesis, "debt_to_equity_direction")
    assert (signal["axis"], signal["value"], signal["polarity"]) == (contract.DIRECTION, contract.IMPROVING, contract.FAVORABLE)
    dimension = synthesis["dimensions"]["CAPITAL_STRUCTURE"]
    assert dimension["direction"] == contract.IMPROVING
    assert dimension["level"] == contract.UNAVAILABLE
    assert dimension["level_reason"] == "NO_PRODUCER_LEVERAGE_LEVEL_CLASSIFICATION"
    assert "CONSERVATIVE_LEVERAGE" not in synthesis["supporting_reason_codes"]
    assert "DEBT_TO_EQUITY_DECREASING" in synthesis["supporting_reason_codes"]
    assert synthesis["strengths"] == []  # a direction is never a strength (level)


def test_stressed_level_and_improving_direction_coexist_without_collapsing() -> None:
    synthesis = _synthesis(_compact(profitability_state="LOSS_MAKING", leverage_state="IMPROVING",
                                    balance_sheet_state="STRENGTHENING"))
    assert synthesis["dimensions"]["PROFITABILITY"]["level"] == contract.STRESSED
    assert synthesis["dimensions"]["CAPITAL_STRUCTURE"]["direction"] == contract.IMPROVING
    assert synthesis["weaknesses"] == ["profitability_level"]
    assert synthesis["improving"] == ["debt_to_equity_direction", "equity_to_assets_direction"]
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_MIXED


def test_absolute_level_does_not_erase_direction() -> None:
    synthesis = _synthesis(_compact(profitability_state="PROFITABLE", margin_state="MARGIN_COMPRESSING"))
    assert synthesis["dimensions"]["PROFITABILITY"]["level"] == contract.HEALTHY
    assert synthesis["dimensions"]["MARGINS"]["direction"] == contract.WORSENING
    assert synthesis["dimensions"]["MARGINS"]["level_reason"] == "NO_PRODUCER_MARGIN_LEVEL_CLASSIFICATION"
    assert "MARGIN_COMPRESSION" in synthesis["contradicting_reason_codes"]
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_MIXED


def test_gross_margin_trajectory_uses_the_engine_prefixed_vocabulary() -> None:
    synthesis = _synthesis(_compact(gross_margin_trajectory_state="GROSS_MARGIN_WORSENING", profitability_state="PROFITABLE"))
    assert _signal(synthesis, "gross_margin_direction")["value"] == contract.WORSENING
    assert "GROSS_MARGIN_COMPRESSION" in synthesis["contradicting_reason_codes"]


# ── Transitions and negative-base semantics ───────────────────────────────────────────────────

def test_same_quarter_yoy_loss_to_profit_is_turnaround_and_stays_a_transition() -> None:
    record = _compact(profitability_state="TURNAROUND_CONTEXT", earnings_turnaround_state="LOSS_TO_PROFIT",
                      fitness={"net_income_same_quarter_yoy": {"fitness": "READY", "semantic_transition": "LOSS_TO_PROFIT",
                                                               "growth_basis": "SAME_QUARTER_YOY"}})
    synthesis = _synthesis(record)
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_TURNAROUND
    transition = _signal(synthesis, "earnings_transition")
    assert (transition["axis"], transition["value"], transition["fitness"]["basis"]) == (
        contract.TRANSITION, contract.LOSS_TO_PROFIT, "SAME_QUARTER_YOY")
    assert transition["fitness"]["source_features"] == ["net_income_same_quarter_yoy"]
    # The turnaround is not a quality level and not a growth direction.
    assert synthesis["dimensions"]["PROFITABILITY"]["level"] == contract.UNAVAILABLE
    assert synthesis["strengths"] == [] and "GROWTH" not in synthesis["derivation"]["favorable_votes"]
    assert "EARNINGS_TURNAROUND_DETECTED" in synthesis["supporting_reason_codes"]


def test_sequential_loss_to_profit_is_a_visible_observation_never_a_vote_or_turnaround() -> None:
    # CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1: a QoQ sign flip is seasonality-prone;
    # it stays visible and never votes (it was a transition vote under 66d0fc0/5729c52).
    record = _compact(profitability_state="PROFITABLE", earnings_turnaround_state="LOSS_TO_PROFIT",
                      fitness={"net_income_qoq": {"fitness": "READY", "semantic_transition": "LOSS_TO_PROFIT",
                                                  "growth_basis": "QOQ_STANDALONE"}})
    synthesis = _synthesis(record)
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_STABLE
    assert synthesis["derivation"]["turnaround"]["triggered"] is False
    assert synthesis["derivation"]["favorable_votes"] == ["PROFITABILITY.LEVEL"]
    assert "EARNINGS_LOSS_TO_PROFIT_SEQUENTIAL" not in synthesis["supporting_reason_codes"]
    transition = _signal(synthesis, "earnings_transition")
    assert transition["non_vote_reason"] == contract.SEQUENTIAL_TRANSITION_NOT_A_VOTE
    assert synthesis["research_observations"]["earnings_transition"]["value"] == contract.LOSS_TO_PROFIT


def test_stale_loss_to_profit_is_historical_context_never_a_current_turnaround() -> None:
    record = _compact(profitability_state="TURNAROUND_CONTEXT", earnings_turnaround_state="LOSS_TO_PROFIT",
                      fitness={"net_income_same_quarter_yoy": {"fitness": "READY", "semantic_transition": "LOSS_TO_PROFIT",
                                                               "growth_basis": "SAME_QUARTER_YOY", "as_of_period": "2018-Q1"}})
    synthesis = _synthesis(record)
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    assert synthesis["derivation"]["turnaround"] == {
        "triggered": False, "transition": contract.LOSS_TO_PROFIT, "basis": "SAME_QUARTER_YOY",
        "freshness": "STALE_BUT_RESEARCH_USABLE", "current": False, "required_bases": ["SAME_QUARTER_YOY", "TTM"],
        "required_freshness": sorted(contract.TURNAROUND_FRESHNESS)}
    assert synthesis["derivation"]["favorable_votes"] == []
    assert synthesis["stale_research_evidence"] == ["earnings_transition"]
    assert synthesis["historical_context"]["earnings_transition"]["as_of_period"] == "2018-Q1"
    assert synthesis["evidence_availability"]["state"] == contract.AVAILABLE


def _yoy_transition(value: str) -> dict:
    return {"net_income_same_quarter_yoy": {"fitness": "READY", "semantic_transition": value,
                                            "growth_basis": "SAME_QUARTER_YOY"}}


def test_loss_narrowing_and_widening_are_transitions_not_growth() -> None:
    narrowed = _synthesis(_compact(profitability_state="LOSS_MAKING", earnings_turnaround_state="LOSS_NARROWED",
                                   fitness=_yoy_transition("LOSS_NARROWED")))
    assert narrowed["dimensions"]["PROFITABILITY"] == {"level": contract.STRESSED, "transition": contract.LOSS_NARROWED}
    assert narrowed["dimensions"]["GROWTH"]["direction"] == contract.UNAVAILABLE
    assert narrowed["fundamental_state"] == iidp.FUNDAMENTAL_MIXED  # a loss, but narrowing (comparable basis)
    widened = _synthesis(_compact(profitability_state="LOSS_MAKING", earnings_turnaround_state="LOSS_WIDENED",
                                  fitness=_yoy_transition("LOSS_WIDENED")))
    assert widened["fundamental_state"] == iidp.FUNDAMENTAL_DETERIORATING
    assert "EARNINGS_LOSS_WIDENING" in widened["contradicting_reason_codes"]
    assert "REVENUE_CONTRACTION" not in widened["contradicting_reason_codes"]
    # The same narrowing observed only QoQ is visible, never a vote: the loss level alone decides.
    sequential = _synthesis(_compact(profitability_state="LOSS_MAKING", earnings_turnaround_state="LOSS_NARROWED",
                                     fitness={"net_income_qoq": {"fitness": "READY", "semantic_transition": "LOSS_NARROWED",
                                                                 "growth_basis": "QOQ_STANDALONE"}}))
    assert sequential["dimensions"]["PROFITABILITY"]["transition"] == contract.UNAVAILABLE
    assert sequential["research_observations"]["earnings_transition"]["value"] == contract.LOSS_NARROWED
    assert sequential["fundamental_state"] == iidp.FUNDAMENTAL_DETERIORATING


def test_growth_consensus_sources_exclude_negative_base_transition_features() -> None:
    record = _compact(growth_state="GROWING",
                      fitness={"net_income_qoq": {"fitness": "READY", "semantic_transition": "LOSS_NARROWED"}})
    growth = _signal(_synthesis(record), "growth_direction")
    assert "net_income_qoq" not in growth["fitness"]["source_features"]
    assert growth["value"] == contract.IMPROVING


def test_operational_bridge_contracting_is_an_earnings_transition_not_revenue_growth() -> None:
    bridge = {"status": "RESEARCH_USABLE",
              "financial_context": {"status": "AVAILABLE", "source": contract.DIALECT_OPERATIONAL_BRIDGE,
                                    "fitness": "OPERATIONAL_PROVIDER_RESEARCH_ONLY", "profitability_state": "LOSS_MAKING",
                                    "earnings_turnaround_state": "UNAVAILABLE", "growth_state": "CONTRACTING"},
              "usable_features": {"profit_state": {"input_periods": ["2026-Q2"]},
                                  "net_income_same_period_yoy": {"categorical_state": "TURNED_TO_LOSS",
                                                                 "input_periods": ["2025-Q2", "2026-Q2"]}}}
    synthesis = iidp.evaluate_fundamental_synthesis(bridge, decision_session=SESSION,
                                                    dialect=contract.DIALECT_OPERATIONAL_BRIDGE)
    assert synthesis["dimensions"]["PROFITABILITY"] == {"level": contract.STRESSED, "transition": contract.PROFIT_TO_LOSS}
    assert "GROWTH" not in synthesis["dimensions"]
    assert synthesis["contradicting_reason_codes"] == ["OBSERVED_LOSS_MAKING", "EARNINGS_TURNED_TO_LOSS"]
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_DETERIORATING


# ── Freshness ─────────────────────────────────────────────────────────────────────────────────

def test_stale_but_research_usable_signal_stays_labelled_and_never_votes() -> None:
    record = _compact(profitability_state="PROFITABLE", balance_sheet_state="STRENGTHENING",
                      periods={"net_income_sign": STALE_PERIOD, "equity_to_assets_direction": STALE_PERIOD})
    synthesis = _synthesis(record)
    signal = _signal(synthesis, "profitability_level")
    assert signal["fitness"]["freshness"] == "STALE_BUT_RESEARCH_USABLE"
    assert (signal["decision_eligible"], signal["research_usable"]) == (False, True)
    assert signal["consumption_class"] == contract.RESEARCH_EVIDENCE_ONLY
    assert contract.STALE_NOT_A_CURRENT_VOTE in signal["reason_codes"]
    assert synthesis["stale_research_evidence"] == ["equity_to_assets_direction", "profitability_level"]
    assert synthesis["derivation"]["stale_research_dimensions"] == ["CAPITAL_STRUCTURE.DIRECTION", "PROFITABILITY.LEVEL"]
    assert synthesis["decision_signal_freshness"] == {}
    assert synthesis["signal_freshness_voting"] == {"CURRENT_VOTING": 0, "STALE_RESEARCH_ONLY": 2, "UNAVAILABLE_EXCLUDED": 0}
    assert synthesis["strengths"] == ["profitability_level"]  # a level observation, labelled stale
    assert synthesis["improving"] == []  # a stale direction is history, not a current direction
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT


def test_stale_measurement_never_joins_a_current_one_in_the_same_dimension() -> None:
    record = _compact(margin_state="MARGIN_EXPANDING", gross_margin_trajectory_state="GROSS_MARGIN_WORSENING",
                      periods={"gross_margin_direction": "2015-Q3"})
    synthesis = _synthesis(record)
    margins = synthesis["dimensions"]["MARGINS"]
    assert margins["direction"] == contract.IMPROVING
    assert margins["stale_research_evidence"]["gross_margin_direction"]["as_of_period"] == "2015-Q3"
    assert "GROSS_MARGIN_COMPRESSION" not in synthesis["contradicting_reason_codes"]
    assert synthesis["historical_reason_codes"]["adverse"] == ["GROSS_MARGIN_COMPRESSION"]


def test_unavailable_future_period_cannot_enter_the_synthesis() -> None:
    record = _compact(profitability_state="PROFITABLE", margin_state="MARGIN_EXPANDING",
                      periods={"net_income_sign": FUTURE_PERIOD, "net_margin": FUTURE_PERIOD})
    synthesis = _synthesis(record)
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    for signal_id in ("profitability_level", "net_margin_direction"):
        signal = _signal(synthesis, signal_id)
        assert signal["decision_eligible"] is False
        assert "FINANCIAL_PERIOD_AFTER_DECISION_SESSION" in signal["reason_codes"]
    assert synthesis["excluded"]["profitability_level"]


def test_missing_source_period_is_never_decision_evidence() -> None:
    record = _compact(profitability_state="PROFITABLE")
    record["feature_fitness"]["net_income_sign"].pop("as_of_period")
    assert _signal(_synthesis(record), "profitability_level")["decision_eligible"] is False


# ── Entity applicability ──────────────────────────────────────────────────────────────────────

def test_corporate_states_are_non_applicable_for_a_bank_and_bank_states_apply() -> None:
    record = _compact(analysis_family="OTHER_FINANCIAL_LIMITED_ANALYSIS", issuer_type="bank",
                      bank_asset_quality_state="WORSENING",
                      fitness={"bank_npl_ratio": {"fitness": "READY", "as_of_period": CURRENT_PERIOD}})
    synthesis = _synthesis(record)
    assert "growth_direction" in synthesis["non_applicable"] and "debt_to_equity_direction" in synthesis["non_applicable"]
    assert synthesis["contradicting_reason_codes"] == ["BANK_ASSET_QUALITY_WORSENING"]
    assert set(synthesis["dimensions"]) == {"BANK_ASSET_QUALITY", "BANK_FUNDING", "BANK_EFFICIENCY"}


def test_securities_composition_trajectories_are_evidence_only() -> None:
    record = _compact(analysis_family="OTHER_FINANCIAL_LIMITED_ANALYSIS", issuer_type="securities",
                      brokerage_mix_trajectory_state="BROKERAGE_MIX_RISING",
                      fitness={"brokerage_revenue_mix": {"fitness": "READY", "as_of_period": CURRENT_PERIOD}})
    synthesis = _synthesis(record)
    assert synthesis["supporting_reason_codes"] == [] and synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    assert synthesis["context_only"] == ["securities_brokerage_mix"]


def test_unresolved_entity_keeps_only_producer_permitted_generic_primitives() -> None:
    record = _compact(analysis_family="UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS", issuer_type="unknown",
                      profitability_state="PROFITABLE", margin_state="MARGIN_EXPANDING",
                      fitness={"net_income_sign": {"fitness": "RESEARCH_PROXY", "as_of_period": CURRENT_PERIOD}})
    synthesis = _synthesis(record)
    profitability = _signal(synthesis, "profitability_level")
    assert profitability["applicability"] == contract.UNRESOLVED
    # Research evidence kept; decision applicability fails closed (it voted under 5729c52).
    assert (profitability["research_usable"], profitability["decision_eligible"]) == (True, False)
    assert profitability["non_vote_reason"] == contract.ENTITY_UNRESOLVED_NOT_A_VOTE
    assert _signal(synthesis, "net_margin_direction")["exclusion"] == "ENTITY_UNRESOLVED"
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    assert synthesis["fundamental_evidence_availability"] == contract.NOT_APPLICABLE_ENTITY
    assert synthesis["strengths"] == ["profitability_level"]


# ── Vocabulary and dimension semantics ───────────────────────────────────────────────────────

def test_hypothesised_consumer_vocabulary_stays_unknown() -> None:
    synthesis = _synthesis(_compact(leverage_state="SAFE", growth_state="EXPANDING",
                                    working_capital_trajectory_state="IMPROVING"))
    for signal_id in ("debt_to_equity_direction", "growth_direction", "net_working_capital_direction"):
        signal = _signal(synthesis, signal_id)
        assert signal["value"] == contract.UNKNOWN
        assert signal["exclusion"] == "PRODUCER_VALUE_OUTSIDE_CONTRACT_VOCABULARY"
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT


def test_correlated_measurements_of_one_dimension_vote_once_and_conflict_is_shown() -> None:
    agree = _synthesis(_compact(balance_sheet_state="DETERIORATING", leverage_state="WORSENING",
                                working_capital_trajectory_state="WORKING_CAPITAL_WORSENING",
                                current_ratio_trajectory_state="CURRENT_RATIO_WORSENING"))
    # Two dimensions of one balance-sheet observation that agree are one vote (promotion hardening).
    assert agree["derivation"]["adverse_votes"] == ["CAPITAL_STRUCTURE.DIRECTION"]
    assert agree["derivation"]["vote_grouping"]["folded_votes"] == ["SHORT_TERM_LIQUIDITY.DIRECTION"]
    conflict = _synthesis(_compact(balance_sheet_state="STRENGTHENING", leverage_state="WORSENING",
                                   profitability_state="PROFITABLE"))
    assert conflict["dimensions"]["CAPITAL_STRUCTURE"]["direction"] == contract.MIXED
    assert "BALANCE_SHEET_STRENGTHENING" in conflict["supporting_reason_codes"]
    assert "DEBT_TO_EQUITY_INCREASING" in conflict["contradicting_reason_codes"]
    assert conflict["derivation"]["favorable_votes"] == ["PROFITABILITY.LEVEL"]
    assert conflict["fundamental_state"] == iidp.FUNDAMENTAL_STABLE


def test_current_ratio_direction_is_the_short_term_liquidity_improving_driver() -> None:
    synthesis = _synthesis(_compact(profitability_state="PROFITABLE",
                                    current_ratio_trajectory_state="CURRENT_RATIO_IMPROVING"))
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_IMPROVING
    assert synthesis["derivation"]["improving_drivers"] == ["SHORT_TERM_LIQUIDITY.DIRECTION=IMPROVING"]
    assert synthesis["dimensions"]["SHORT_TERM_LIQUIDITY"]["direction"] == contract.IMPROVING
    # The working-capital amount alone is never an improving driver.
    amount = _synthesis(_compact(profitability_state="PROFITABLE",
                                 working_capital_trajectory_state="WORKING_CAPITAL_IMPROVING"))
    assert amount["fundamental_state"] == iidp.FUNDAMENTAL_STABLE and amount["derivation"]["improving_drivers"] == []


def test_evidence_only_states_never_vote() -> None:
    synthesis = _synthesis(_compact(free_cash_flow_proxy_direction_state="WORSENING",
                                    working_capital_state="NEGATIVE_NET_WORKING_CAPITAL", resilience_state="STRESSED"))
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    assert synthesis["contradicting_reason_codes"] == []
    assert synthesis["context_only"] == ["free_cash_flow_proxy_direction", "net_working_capital_level", "resilience_level"]
    assert synthesis["dimensions"]["SHORT_TERM_LIQUIDITY"]["context_only"] == {
        "net_working_capital_level": "NEGATIVE_NET_WORKING_CAPITAL"}


def test_cash_conversion_level_needs_positive_same_period_earnings() -> None:
    aligned = _synthesis(_compact(profitability_state="PROFITABLE", cash_conversion_state="HEALTHY",
                                  fitness={"cfo_to_net_income_ttm": {"fitness": "BLOCKED_BY_EVIDENCE"}}))
    assert _signal(aligned, "cash_conversion_level")["decision_eligible"] is True
    loss = _synthesis(_compact(profitability_state="LOSS_MAKING", cash_conversion_state="HEALTHY",
                               fitness={"cfo_to_net_income_ttm": {"fitness": "BLOCKED_BY_EVIDENCE"}}))
    assert _signal(loss, "cash_conversion_level")["exclusion"] == (
        "CASH_CONVERSION_SIGN_UNDEFINED_WITHOUT_POSITIVE_SAME_PERIOD_EARNINGS")
    assert "POSITIVE_CASH_CONVERSION_PROXY" not in loss["supporting_reason_codes"]


def test_missing_metric_does_not_erase_unrelated_valid_evidence() -> None:
    record = _compact(profitability_state="PROFITABLE", growth_state="GROWING")
    record["feature_fitness"]["net_margin_direction"] = {"fitness": "BLOCKED_BY_EVIDENCE", "reason_codes": ["X"]}
    synthesis = _synthesis(record)
    assert "net_margin_direction" in synthesis["missing"]
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_IMPROVING
    assert synthesis["supporting_reason_codes"] == ["PROFITABLE_CORE_OPERATIONS", "REVENUE_GROWTH_EXPANDING"]


def test_absent_financial_context_stays_insufficient_with_its_reason() -> None:
    state, supports, counters = iidp.evaluate_fundamental_direction({"status": "ABSENT"}, decision_session=SESSION)
    assert (state, supports, counters) == (iidp.FUNDAMENTAL_INSUFFICIENT, [], [])
    assert contract.evaluate({"status": "ABSENT"}, decision_session=SESSION)["evidence_gap_reason_codes"] == ["FUNDAMENTAL_CONTEXT_ABSENT"]


# ── Real producer vocabulary (engine -> compact projection -> contract) ──────────────────────

def _row(metric, value, period, *, semantic="STANDALONE_QUARTER"):
    source = f"AAA_KBS_{'income' if semantic == 'STANDALONE_QUARTER' else 'balance'}"
    return {"ticker": "AAA", "canonical_metric": metric, "reported_value": value, "native_period_label": period,
            "period_end": period, "period_semantic_state": semantic, "source_status": "provider_reported",
            "lineage_complete": True, "source_conflicts": [], "statement_scope": "consolidated",
            "normalized_candidate_unit": {"currency": "unknown", "scale": "unknown"},
            "source_lineage": {"provider": "KBS", "source_file": source, "source_sha256": "sha",
                               "fact_id": f"{metric}-{period}"}}


def _engine_compact(net_income: dict) -> dict:
    rows = [_row("net_income", value, period) for period, value in net_income.items()]
    rows += [_row("revenue", value, period) for period, value in {"2025-Q2": 100, "2026-Q1": 110, "2026-Q2": 120}.items()]
    for metric, (prior, current) in {"total_assets": (1000, 1100), "shareholders_equity": (400, 480),
                                     "total_interest_bearing_debt": (300, 280), "current_assets": (500, 560),
                                     "current_liabilities": (300, 310)}.items():
        rows += [_row(metric, prior, "2025-Q2", semantic="POINT_IN_TIME_BALANCE_SHEET"),
                 _row(metric, current, "2026-Q2", semantic="POINT_IN_TIME_BALANCE_SHEET")]
    artifact = engine.build_artifact(tickers=["AAA"], rows=rows, issuer_types={"AAA": "corporate"},
                                     source_identities={"semantics": "test"}, requested_at="2026-09-24T15:00:00+07:00")
    product = projection.build_product_projection(financial_context=artifact, product_tickers=["AAA"],
                                                  requested_at="2026-09-24T15:00:00+07:00")
    return product["records"]["AAA"]


def test_real_engine_vocabulary_maps_deterministically_and_never_to_unknown() -> None:
    record = _engine_compact({"2025-Q2": -10, "2026-Q1": 4, "2026-Q2": 5})
    first, second = _synthesis(record), _synthesis(record)
    assert first == second
    present = {signal["signal_id"]: signal for signal in first["signals"]}
    assert all(signal["value"] != contract.UNKNOWN for signal in present.values())
    assert present["debt_to_equity_direction"]["value"] == contract.IMPROVING
    assert present["net_working_capital_direction"]["value"] == contract.RISING  # an amount, no polarity
    assert present["net_working_capital_direction"]["decision_eligible"] is False
    assert present["current_ratio_direction"]["value"] == contract.IMPROVING
    assert present["earnings_transition"]["value"] == contract.LOSS_TO_PROFIT
    assert present["earnings_transition"]["fitness"]["basis"] == "SAME_QUARTER_YOY"
    assert first["fundamental_state"] == iidp.FUNDAMENTAL_TURNAROUND


def test_real_engine_sequential_turnaround_carries_its_qoq_basis() -> None:
    record = _engine_compact({"2025-Q2": 2, "2026-Q1": -3, "2026-Q2": 5})
    transition = _signal(_synthesis(record), "earnings_transition")
    assert (transition["value"], transition["fitness"]["basis"]) == (contract.LOSS_TO_PROFIT, "QOQ_STANDALONE")
    assert transition["fitness"]["source_features"] == ["net_income_qoq"]
    assert _synthesis(record)["fundamental_state"] != iidp.FUNDAMENTAL_TURNAROUND


def test_projection_carries_transition_class_and_basis_but_never_a_value() -> None:
    record = _engine_compact({"2025-Q2": -10, "2026-Q1": 4, "2026-Q2": 5})
    entry = record["feature_fitness"]["net_income_same_quarter_yoy"]
    assert entry["semantic_transition"] == "LOSS_TO_PROFIT" and entry["growth_basis"] == "SAME_QUARTER_YOY"
    assert "value" not in entry


# ── Integrated Decision record ────────────────────────────────────────────────────────────────

def test_decision_record_carries_components_alongside_the_compatible_state() -> None:
    record = _compact(profitability_state="LOSS_MAKING", leverage_state="IMPROVING")
    decision = iidp.build_ticker_integrated_decision(
        ticker="AAA", as_of_session=SESSION, tactical_record=None, financial_record=record,
        valuation_record=None, relative_volume_record=None, market_sector_record=None)
    synthesis = decision["fundamental_synthesis"]
    assert decision["fundamental_state"] == synthesis["fundamental_state"] == iidp.FUNDAMENTAL_MIXED
    assert decision["evidence_axes"]["FUNDAMENTAL"]["context"]["favorable_votes"] == ["CAPITAL_STRUCTURE.DIRECTION"]
    components = decision["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["components"]
    assert components["dimensions"]["CAPITAL_STRUCTURE"]["direction"] == contract.IMPROVING
    assert components["weaknesses"] == ["profitability_level"]


def test_bridge_eligibility_uses_the_same_session_freshness_gate() -> None:
    record = _compact(profitability_state="PROFITABLE", periods={"net_income_sign": FUTURE_PERIOD})
    assert iidp.operational_fundamental_bridge_eligible(record, decision_session=SESSION) is True
    assert iidp.operational_fundamental_bridge_eligible(record, decision_session="2026-12-31") is False


def test_downstream_change_is_attributed_to_the_exact_restored_signal() -> None:
    from tools import run_integrated_fundamental_state_consumption_proof as proof

    record = _compact(profitability_state="PROFITABLE", growth_state="CONTRACTING",
                      current_ratio_trajectory_state="CURRENT_RATIO_WORSENING")
    legacy = ("MIXED", ["PROFITABLE_CORE_OPERATIONS"], ["REVENUE_CONTRACTION"])
    after = {"fundamental_state": None, "fundamental_synthesis": _synthesis(record), "evidence_axes": {}}
    after["fundamental_state"] = after["fundamental_synthesis"]["fundamental_state"]
    entry = proof._attribution("AAA", {"fundamental_state": "MIXED", "evidence_axes": {}}, after, legacy)
    assert entry["fundamental_state"] == ["MIXED", iidp.FUNDAMENTAL_DETERIORATING]
    assert entry["causes"] == [{"dimension": "SHORT_TERM_LIQUIDITY.DIRECTION", "category": "RESTORED_SIGNAL",
                                "dimension_value_after": contract.WORSENING,
                                "signals": ["current_ratio_direction"],
                                "producer_values": {"current_ratio_direction": "CURRENT_RATIO_WORSENING"},
                                "before": None, "after": contract.ADVERSE}]


def test_contract_evaluation_makes_no_network_call() -> None:
    events: list[str] = []

    def hook(event: str, _args: tuple) -> None:
        if event.startswith(("socket.", "http.client", "urllib")):
            events.append(event)

    sys.addaudithook(hook)
    _synthesis(_compact(profitability_state="PROFITABLE", leverage_state="IMPROVING"))
    assert events == []
