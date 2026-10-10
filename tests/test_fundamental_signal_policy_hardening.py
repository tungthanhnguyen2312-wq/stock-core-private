"""FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1: which fundamental signals may vote, and when.

Only a CURRENT period votes into the current fundamental direction; stale research evidence stays
visible and never votes; the working-capital amount trajectory is evidence only; current-ratio
direction is a narrow short-term liquidity-ratio direction; earnings sign transitions (including
PROFIT_TO_LOSS) are categorical and need one compatible series; and an insufficient current
direction never reads as absent fundamental evidence downstream.
"""
from __future__ import annotations

import sys

import stocklookup_core.decision.current_research_decision_input as decision_input
import stocklookup_core.financial.financial_analysis_engine_v2 as engine
import stocklookup_core.financial.financial_flow_semantics_ttm_bridge as bridge
import stocklookup_core.financial.financial_analysis_product_projection as projection
import stocklookup_core.financial.fundamental_signal_consumption_contract as contract
import stocklookup_core.decision.integrated_investment_decision_product as iidp
from tools import current_research_capability_map as capability_map

SESSION = "2026-09-24"  # last completed quarter 2026-Q2
CURRENT_PERIOD = "2026-Q2"
STALE_PERIOD = "2012-Q4"
FUTURE_PERIOD = "2026-Q3"
_SOURCES = ("net_income_sign", "net_margin", "net_margin_direction", "gross_margin_direction", "revenue_qoq",
            "revenue_same_quarter_yoy", "net_income_qoq", "net_income_same_quarter_yoy", "net_income_ttm_yoy",
            "cfo_to_net_income", "cfo_to_net_income_ttm", "equity_to_assets_direction", "debt_to_equity_direction",
            "net_working_capital_direction", "current_ratio_direction", "net_working_capital",
            "free_cash_flow_proxy_direction", "bank_npl_ratio", "bank_ldr", "bank_cir", "brokerage_revenue_mix")


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


def _all_stale(**states) -> dict:
    return _compact(periods={feature: STALE_PERIOD for feature in _SOURCES}, **states)


# ── Freshness voting ─────────────────────────────────────────────────────────────────────────

def test_current_evidence_votes() -> None:
    synthesis = _synthesis(_compact(profitability_state="PROFITABLE", leverage_state="WORSENING"))
    assert _signal(synthesis, "profitability_level")["consumption_class"] == contract.CURRENT_DECISION_VOTE
    assert synthesis["derivation"]["favorable_votes"] == ["PROFITABILITY.LEVEL"]
    assert synthesis["derivation"]["adverse_votes"] == ["CAPITAL_STRUCTURE.DIRECTION"]
    assert synthesis["decision_signal_freshness"] == {"CURRENT": 2}
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_MIXED


def test_stale_but_usable_evidence_is_visible_but_never_votes() -> None:
    synthesis = _synthesis(_all_stale(profitability_state="LOSS_MAKING", leverage_state="WORSENING",
                                      margin_state="MARGIN_COMPRESSING"))
    assert synthesis["derivation"]["favorable_votes"] == [] and synthesis["derivation"]["adverse_votes"] == []
    assert synthesis["contradicting_reason_codes"] == []  # never a current counter-thesis
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    # Visible: weakness (a level observation), historical context, stale list, narrative codes.
    assert synthesis["weaknesses"] == ["profitability_level"]
    assert set(synthesis["historical_context"]) == {"debt_to_equity_direction", "net_margin_direction"}
    assert synthesis["stale_research_evidence"] == ["debt_to_equity_direction", "net_margin_direction", "profitability_level"]
    assert synthesis["evidence_freshness"]["profitability_level"] == "STALE_BUT_RESEARCH_USABLE"
    assert synthesis["historical_reason_codes"]["adverse"] == [
        "OBSERVED_LOSS_MAKING", "MARGIN_COMPRESSION", "DEBT_TO_EQUITY_INCREASING"]
    assert synthesis["dimensions"]["PROFITABILITY"]["stale_research_evidence"]["profitability_level"]["as_of_period"] == STALE_PERIOD
    assert synthesis["signal_freshness_voting"] == {"CURRENT_VOTING": 0, "STALE_RESEARCH_ONLY": 3, "UNAVAILABLE_EXCLUDED": 0}


def test_stale_transition_never_triggers_a_current_turnaround() -> None:
    record = _all_stale(profitability_state="TURNAROUND_CONTEXT", earnings_turnaround_state="LOSS_TO_PROFIT",
                        fitness={"net_income_same_quarter_yoy": {"fitness": "READY", "semantic_transition": "LOSS_TO_PROFIT",
                                                                 "growth_basis": "SAME_QUARTER_YOY", "as_of_period": STALE_PERIOD}})
    synthesis = _synthesis(record)
    assert synthesis["derivation"]["turnaround"]["triggered"] is False
    assert synthesis["derivation"]["turnaround"]["current"] is False
    assert _signal(synthesis, "earnings_transition")["consumption_class"] == contract.RESEARCH_EVIDENCE_ONLY
    assert synthesis["fundamental_state"] != iidp.FUNDAMENTAL_TURNAROUND


def test_post_session_evidence_cannot_vote_or_count_as_evidence() -> None:
    synthesis = _synthesis(_compact(profitability_state="PROFITABLE", leverage_state="IMPROVING",
                                    periods={"net_income_sign": FUTURE_PERIOD, "debt_to_equity_direction": FUTURE_PERIOD}))
    for signal_id in ("profitability_level", "debt_to_equity_direction"):
        signal = _signal(synthesis, signal_id)
        assert (signal["decision_eligible"], signal["research_usable"]) == (False, False)
        assert signal["consumption_class"] == contract.UNKNOWN
        assert "FINANCIAL_PERIOD_AFTER_DECISION_SESSION" in signal["reason_codes"]
    assert synthesis["signal_freshness_voting"]["UNAVAILABLE_EXCLUDED"] == 2
    assert synthesis["evidence_availability"]["state"] == contract.UNAVAILABLE
    assert synthesis["strengths"] == [] and synthesis["stale_research_evidence"] == []


# ── Working capital and short-term liquidity ─────────────────────────────────────────────────

def test_raw_working_capital_amount_trajectory_is_evidence_only() -> None:
    for producer, value in (("WORKING_CAPITAL_IMPROVING", contract.RISING), ("WORKING_CAPITAL_WORSENING", contract.FALLING)):
        synthesis = _synthesis(_compact(profitability_state="PROFITABLE", working_capital_trajectory_state=producer))
        signal = _signal(synthesis, "net_working_capital_direction")
        assert (signal["value"], signal["polarity"], signal["decision_eligible"]) == (value, contract.NEUTRAL, False)
        assert signal["consumption_class"] == contract.RESEARCH_EVIDENCE_ONLY
        assert signal["reason_code"] is None
        assert synthesis["derivation"]["favorable_votes"] == ["PROFITABILITY.LEVEL"]
        assert synthesis["derivation"]["adverse_votes"] == []
        assert synthesis["dimensions"]["SHORT_TERM_LIQUIDITY"]["context_only"] == {"net_working_capital_direction": value}
        assert "SHORT_TERM_LIQUIDITY" not in str(synthesis["derivation"]["improving_drivers"])
    assert contract.policy_table()["working_capital_trajectory_state"]["policy_class"] == contract.RESEARCH_EVIDENCE_ONLY


def test_current_ratio_direction_is_narrowly_a_short_term_liquidity_ratio_direction() -> None:
    synthesis = _synthesis(_compact(current_ratio_trajectory_state="CURRENT_RATIO_WORSENING",
                                    working_capital_trajectory_state="WORKING_CAPITAL_IMPROVING"))
    signal = _signal(synthesis, "current_ratio_direction")
    assert (signal["dimension"], signal["axis"], signal["value"]) == ("SHORT_TERM_LIQUIDITY", contract.DIRECTION, contract.WORSENING)
    assert "short-term liquidity-ratio direction" in contract.SIGNALS["current_ratio_direction"]["semantic"].lower()
    liquidity = synthesis["dimensions"]["SHORT_TERM_LIQUIDITY"]
    # The ratio never manufactures an absolute liquidity level, and the amount moving the other way is shown.
    assert liquidity["direction"] == contract.WORSENING
    assert (liquidity["level"], liquidity["level_reason"]) == (contract.UNAVAILABLE, "NO_GOVERNED_ABSOLUTE_LIQUIDITY_LEVEL")
    assert liquidity["context_only"] == {"net_working_capital_direction": contract.RISING}
    assert "CAPITAL_STRUCTURE" not in synthesis["dimensions"] or synthesis["dimensions"]["CAPITAL_STRUCTURE"].get("direction") == contract.UNAVAILABLE
    assert synthesis["weaknesses"] == [] and synthesis["deteriorating"] == ["current_ratio_direction"]


def test_conflicting_current_liquidity_signals_are_exposed_never_voted() -> None:
    base = _signal(_synthesis(_compact(current_ratio_trajectory_state="CURRENT_RATIO_IMPROVING")), "current_ratio_direction")
    other = {**base, "signal_id": "independent_liquidity_direction", "value": contract.WORSENING,
             "polarity": contract.ADVERSE, "reason_code": "INDEPENDENT_LIQUIDITY_WORSENING"}
    synthesis = contract.synthesize([base, other], dialect=contract.DIALECT_FINANCIAL_V2, decision_session=SESSION,
                                    status="AVAILABLE")
    liquidity = synthesis["dimensions"]["SHORT_TERM_LIQUIDITY"]
    assert liquidity["direction"] == contract.MIXED and liquidity["conflicting_axes"] == [contract.DIRECTION]
    assert synthesis["derivation"]["favorable_votes"] == [] and synthesis["derivation"]["adverse_votes"] == []


def test_direction_never_creates_an_absolute_level() -> None:
    synthesis = _synthesis(_compact(leverage_state="IMPROVING", margin_state="MARGIN_EXPANDING",
                                    current_ratio_trajectory_state="CURRENT_RATIO_IMPROVING"))
    for dimension, reason in (("CAPITAL_STRUCTURE", "NO_PRODUCER_LEVERAGE_LEVEL_CLASSIFICATION"),
                              ("MARGINS", "NO_PRODUCER_MARGIN_LEVEL_CLASSIFICATION"),
                              ("SHORT_TERM_LIQUIDITY", "NO_GOVERNED_ABSOLUTE_LIQUIDITY_LEVEL")):
        assert synthesis["dimensions"][dimension]["level"] == contract.UNAVAILABLE
        assert synthesis["dimensions"][dimension]["level_reason"] == reason
    assert synthesis["strengths"] == [] and synthesis["weaknesses"] == []


def test_every_reviewed_state_has_an_explicit_policy_class() -> None:
    table = contract.policy_table()
    expected = {
        "working_capital_trajectory_state": contract.RESEARCH_EVIDENCE_ONLY,
        "current_ratio_trajectory_state": contract.CURRENT_DECISION_VOTE,
        "leverage_state": contract.CURRENT_DECISION_VOTE,
        "gross_margin_trajectory_state": contract.CURRENT_DECISION_VOTE,
        "margin_state": contract.CURRENT_DECISION_VOTE,
        "growth_state": contract.CURRENT_DECISION_VOTE,
        "free_cash_flow_proxy_direction_state": contract.RESEARCH_EVIDENCE_ONLY,
        "cash_conversion_state": contract.CURRENT_DECISION_VOTE,
        "resilience_state": contract.RESEARCH_EVIDENCE_ONLY,
        "profitability_state": contract.CURRENT_DECISION_VOTE,
        "earnings_turnaround_state": contract.TRANSITION_EVENT,
        "capital_efficiency_state": contract.UNKNOWN,
    }
    assert {field: table[field]["policy_class"] for field in expected} == expected
    assert all(entry["policy_class"] in contract.POLICY_CLASSES and entry["policy_reason"] for entry in table.values())


# ── Sign transitions (producer and consumer) ─────────────────────────────────────────────────

def _row(metric, value, period, *, provider="KBS", scope="consolidated", semantic="STANDALONE_QUARTER", scale="unknown"):
    return {"ticker": "AAA", "canonical_metric": metric, "reported_value": value, "native_period_label": period,
            "period_end": period, "period_semantic_state": semantic, "source_status": "provider_reported",
            "lineage_complete": True, "source_conflicts": [], "statement_scope": scope,
            "normalized_candidate_unit": {"currency": "unknown", "scale": scale},
            "source_lineage": {"provider": provider, "source_file": f"AAA_{provider}_income", "source_sha256": "sha",
                               "fact_id": f"{metric}-{period}-{provider}"}}


def _features(net_income: dict, **kwargs) -> dict:
    rows = [_row("net_income", value, period, **kwargs) for period, value in net_income.items()]
    return engine.build_ticker_context("AAA", rows, issuer_type="corporate", source_identities={"semantics": "x"})["features"]


def test_engine_detects_profit_to_loss_as_a_transition_never_growth() -> None:
    features = _features({"2025-Q2": 10, "2026-Q1": 4, "2026-Q2": -5})
    for feature_id, basis in (("net_income_same_quarter_yoy", "SAME_QUARTER_YOY"), ("net_income_qoq", "QOQ_STANDALONE")):
        feature = features[feature_id]
        assert (feature["semantic_transition"], feature["value"], feature["growth_basis"]) == ("PROFIT_TO_LOSS", None, basis)
        assert feature["warnings"] == ["EARNINGS_SIGN_CHANGED_PROFIT_TO_LOSS"]


def test_engine_detects_loss_to_profit() -> None:
    features = _features({"2025-Q2": -10, "2026-Q2": 5})
    assert features["net_income_same_quarter_yoy"]["semantic_transition"] == "LOSS_TO_PROFIT"


def test_engine_loss_narrowing_and_widening_including_ttm() -> None:
    features = _features({"2025-Q2": -10, "2026-Q2": -4})
    assert features["net_income_same_quarter_yoy"]["semantic_transition"] == "LOSS_NARROWED"
    features = _features({"2025-Q2": -4, "2026-Q2": -10})
    assert features["net_income_same_quarter_yoy"]["semantic_transition"] == "LOSS_WIDENED"
    quarters = ("2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2")
    narrowed = _features(dict(zip(quarters, (-5, -5, -5, -5, -1, -1, -1, -1))))["net_income_ttm_yoy"]
    widened = _features(dict(zip(quarters, (-1, -1, -1, -1, -5, -5, -5, -5))))["net_income_ttm_yoy"]
    turned = _features(dict(zip(quarters, (5, 5, 5, 5, -1, -1, -1, -1))))["net_income_ttm_yoy"]
    assert (narrowed["semantic_transition"], widened["semantic_transition"], turned["semantic_transition"]) == (
        "LOSS_NARROWED", "LOSS_WIDENED", "PROFIT_TO_LOSS")  # no longer collapsed into ZERO_BASE / growth


def test_revenue_sign_change_stays_ordinary_growth_and_positive_base_growth_is_unchanged() -> None:
    rows = [_row("revenue", 10, "2025-Q2"), _row("revenue", -2, "2026-Q2")]
    feature = engine.build_ticker_context("AAA", rows, issuer_type="corporate", source_identities={})["features"]["revenue_same_quarter_yoy"]
    assert feature["semantic_transition"] is None and feature["value"] == -1.2
    assert _features({"2025-Q2": 10, "2026-Q2": 5})["net_income_same_quarter_yoy"]["value"] == -0.5


def test_incompatible_periods_never_create_a_transition() -> None:
    # Different provider, scope or unit: separate semantic series, no pair.
    for prior_kwargs in ({"provider": "VCI"}, {"scope": "standalone"}, {"scale": "THOUSAND"}):
        rows = [_row("net_income", 10, "2025-Q2", **prior_kwargs), _row("net_income", -5, "2026-Q2")]
        feature = engine.build_ticker_context("AAA", rows, issuer_type="corporate", source_identities={})["features"]["net_income_same_quarter_yoy"]
        assert feature["semantic_transition"] is None and feature["fitness"] == "BLOCKED_BY_EVIDENCE"
    # A cumulative period never pairs with a standalone quarter; a non-adjacent quarter is not QoQ.
    rows = [_row("net_income", 10, "2025-Q2", semantic="YTD_CUMULATIVE_INTERIM"), _row("net_income", -5, "2026-Q2")]
    assert engine.build_ticker_context("AAA", rows, issuer_type="corporate", source_identities={})["features"][
        "net_income_same_quarter_yoy"]["semantic_transition"] is None
    features = _features({"2025-Q4": 10, "2026-Q2": -5})
    assert features["net_income_qoq"]["semantic_transition"] is None
    assert features["net_income_qoq"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_flow_bridge_detects_profit_to_loss_for_earnings_only() -> None:
    facts = [{"ticker": "AAA", "canonical_metric": metric, "provider": "KBS", "statement_family": "income_statement",
              "reporting_period": period, "period_type": "quarterly", "value": value, "status": "provider_reported",
              "statement_scope": "consolidated", "currency": "unknown", "scale": "unknown",
              "source_sha256": "s", "fact_id": f"{metric}-{period}"}
             for metric in ("net_income", "revenue") for period, value in (("2025-Q2", 10), ("2026-Q1", 3), ("2026-Q2", -5))]
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=facts)
    assert record["growth"]["net_income"]["same_quarter_yoy"]["semantic_transition"] == "PROFIT_TO_LOSS"
    assert "value" not in record["growth"]["net_income"]["same_quarter_yoy"]
    assert record["qualitative_states"]["earnings_turnaround_state"] == "PROFIT_TO_LOSS"
    assert "semantic_transition" not in record["growth"]["revenue"]["same_quarter_yoy"]


def test_consumer_keeps_profit_to_loss_a_current_adverse_transition() -> None:
    record = _compact(profitability_state="LOSS_MAKING", earnings_turnaround_state="PROFIT_TO_LOSS",
                      fitness={"net_income_same_quarter_yoy": {"fitness": "READY", "semantic_transition": "PROFIT_TO_LOSS",
                                                               "growth_basis": "SAME_QUARTER_YOY"}})
    synthesis = _synthesis(record)
    transition = _signal(synthesis, "earnings_transition")
    assert (transition["value"], transition["consumption_class"], transition["fitness"]["basis"]) == (
        contract.PROFIT_TO_LOSS, contract.TRANSITION_EVENT, "SAME_QUARTER_YOY")
    assert synthesis["dimensions"]["PROFITABILITY"]["transition"] == contract.PROFIT_TO_LOSS
    assert "EARNINGS_TURNED_TO_LOSS" in synthesis["contradicting_reason_codes"]
    assert "REVENUE_CONTRACTION" not in synthesis["contradicting_reason_codes"]
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_DETERIORATING


def test_real_engine_profit_to_loss_reaches_the_consumer_end_to_end() -> None:
    rows = [_row("net_income", value, period) for period, value in {"2025-Q2": 10, "2026-Q1": -2, "2026-Q2": -5}.items()]
    rows += [_row("revenue", value, period) for period, value in {"2025-Q2": 100, "2026-Q1": 90, "2026-Q2": 80}.items()]
    artifact = engine.build_artifact(tickers=["AAA"], rows=rows, issuer_types={"AAA": "corporate"},
                                     source_identities={"semantics": "test"}, requested_at="2026-09-24T15:00:00+07:00")
    product = projection.build_product_projection(financial_context=artifact, product_tickers=["AAA"],
                                                  requested_at="2026-09-24T15:00:00+07:00")
    synthesis = _synthesis(product["records"]["AAA"])
    transition = _signal(synthesis, "earnings_transition")
    # net income QoQ is loss widening (-2 -> -5); the same-quarter YoY is the profit-to-loss event.
    assert product["records"]["AAA"]["feature_fitness"]["net_income_same_quarter_yoy"]["semantic_transition"] == "PROFIT_TO_LOSS"
    assert transition["value"] in (contract.LOSS_WIDENED, contract.PROFIT_TO_LOSS)
    assert transition["polarity"] == contract.ADVERSE
    growth = _signal(synthesis, "growth_direction")
    assert "net_income_same_quarter_yoy" not in growth["fitness"]["source_features"]


# ── Evidence availability versus directional sufficiency ─────────────────────────────────────

def test_directional_insufficiency_keeps_qualified_adverse_evidence() -> None:
    # Loss-making, leverage rising, weak cash, but only from stale periods: no current trajectory.
    synthesis = _synthesis(_all_stale(profitability_state="LOSS_MAKING", leverage_state="WORSENING",
                                      free_cash_flow_proxy_direction_state="WORSENING"))
    evidence = synthesis["evidence_availability"]
    assert synthesis["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    assert (evidence["state"], evidence["polarity"], evidence["directional_sufficiency"]) == (
        contract.AVAILABLE, contract.ADVERSE, "INSUFFICIENT")
    assert evidence["adverse_signals"] == ["debt_to_equity_direction", "profitability_level"]
    assert synthesis["weaknesses"] == ["profitability_level"]


def _decision(record: dict) -> dict:
    return iidp.build_ticker_integrated_decision(
        ticker="AAA", as_of_session=SESSION, tactical_record=None, financial_record=record,
        valuation_record=None, relative_volume_record=None, market_sector_record=None)


def test_decision_input_keeps_fundamental_available_when_only_direction_is_insufficient() -> None:
    decision = _decision(_all_stale(profitability_state="LOSS_MAKING", leverage_state="WORSENING"))
    assert decision["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    dimension = decision["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]
    assert (dimension["state"], dimension["evidence_availability"], dimension["directional_sufficiency"]) == (
        decision_input.AVAILABLE, decision_input.AVAILABLE, "INSUFFICIENT")
    assert dimension["direction_reason_codes"] == ["FUNDAMENTAL_STALE_EVIDENCE_ONLY_NO_CURRENT_DIRECTION"]
    assert dimension["fundamental_evidence_availability"] == contract.STALE_ONLY
    assert dimension["freshness"]["signal_freshness_voting"]["STALE_RESEARCH_ONLY"] == 2
    assert dimension["components"]["weaknesses"] == ["profitability_level"]
    axis = decision["evidence_axes"]["FUNDAMENTAL"]
    assert axis["blocker_reason_codes"] == ["FUNDAMENTAL_STALE_EVIDENCE_ONLY_NO_CURRENT_DIRECTION"]
    assert axis["context"]["evidence_availability"] == contract.AVAILABLE
    assert axis["context"]["fundamental_evidence_availability"] == contract.STALE_ONLY
    assert decision["financial_composite_context"]["joined_axes"]["fundamental_evidence_availability"] == contract.STALE_ONLY
    assert decision["fundamental_risk_level"]["state"] == contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT
    assert "fundamental analysis data" not in decision["why_now"]
    # Posture policy is unchanged: without technical evidence and a current direction it stays
    # INSUFFICIENT_CURRENT_RESEARCH, and the decision input exposes that gate.
    assert decision["research_action_posture"] == iidp.POSTURE_INSUFFICIENT
    assert decision["current_research_decision_input"]["synthesis"]["action_posture_gated_by_current_evidence"] is True


def test_absent_fundamental_context_is_still_blocked() -> None:
    decision = _decision({"status": "ABSENT"})
    dimension = decision["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]
    assert (dimension["state"], dimension["evidence_availability"]) == (decision_input.BLOCKED, "UNAVAILABLE")
    assert decision["evidence_axes"]["FUNDAMENTAL"]["blocker_reason_codes"] == ["FUNDAMENTAL_CONTEXT_ABSENT"]


def test_evidence_class_does_not_downgrade_when_only_the_trajectory_is_unavailable() -> None:
    fundamental = decision_input._fundamental(
        {"fundamental_state": "INSUFFICIENT", "evidence_axes": {"FUNDAMENTAL": {}},
         "fundamental_synthesis": _synthesis(_all_stale(profitability_state="PROFITABLE"))},
        _all_stale(profitability_state="PROFITABLE"), None, {"entity_class": "corporate"}, SESSION)
    dimensions = {"MARKET": {"research_scope": "OFFICIAL_RESEARCH_SCOPE"}, "TECHNICAL": {"state": decision_input.AVAILABLE},
                  "VALUATION": {"state": decision_input.AVAILABLE}, "FUNDAMENTAL": fundamental}
    assert fundamental["state"] == decision_input.AVAILABLE
    assert decision_input.evidence_class(dimensions) == decision_input.CLASS_FULL
    absent = decision_input._fundamental({"fundamental_state": "INSUFFICIENT", "evidence_axes": {"FUNDAMENTAL": {}},
                                          "fundamental_synthesis": _synthesis({"status": "ABSENT"})},
                                         {"status": "ABSENT"}, None, {"entity_class": "corporate"}, SESSION)
    assert decision_input.evidence_class({**dimensions, "FUNDAMENTAL": absent}) == decision_input.CLASS_PARTIAL


def test_capability_map_readiness_reads_evidence_not_direction() -> None:
    decision = _decision(_all_stale(profitability_state="LOSS_MAKING", leverage_state="WORSENING"))
    assert decision["evidence_axes"]["FUNDAMENTAL"]["state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    assert capability_map.integrated_fundamental_available(decision) is True
    assert capability_map.integrated_fundamental_available(_decision({"status": "ABSENT"})) is False
    # A record produced before the decision input keeps the directional reading.
    legacy = {"evidence_axes": {"FUNDAMENTAL": {"state": iidp.FUNDAMENTAL_INSUFFICIENT}}}
    assert capability_map.integrated_fundamental_available(legacy) is False
    assert capability_map.integrated_fundamental_available({"evidence_axes": {"FUNDAMENTAL": {"state": "STABLE"}}}) is True


# ── Applicability and regression boundaries ──────────────────────────────────────────────────

def test_bank_and_securities_applicability_is_preserved() -> None:
    bank = _synthesis(_compact(analysis_family="OTHER_FINANCIAL_LIMITED_ANALYSIS", issuer_type="bank",
                               bank_asset_quality_state="WORSENING", working_capital_trajectory_state="WORKING_CAPITAL_WORSENING",
                               current_ratio_trajectory_state="CURRENT_RATIO_WORSENING", leverage_state="WORSENING"))
    assert {"growth_direction", "debt_to_equity_direction", "current_ratio_direction",
            "net_working_capital_direction"} <= set(bank["non_applicable"])
    assert _signal(bank, "current_ratio_direction")["consumption_class"] == contract.NON_APPLICABLE
    assert bank["contradicting_reason_codes"] == ["BANK_ASSET_QUALITY_WORSENING"]
    assert "SHORT_TERM_LIQUIDITY" not in bank["dimensions"]
    securities = _synthesis(_compact(analysis_family="OTHER_FINANCIAL_LIMITED_ANALYSIS", issuer_type="securities",
                                     brokerage_mix_trajectory_state="BROKERAGE_MIX_RISING",
                                     current_ratio_trajectory_state="CURRENT_RATIO_IMPROVING"))
    assert _signal(securities, "current_ratio_direction")["consumption_class"] == contract.NON_APPLICABLE
    assert _signal(securities, "securities_brokerage_mix")["consumption_class"] == contract.RESEARCH_EVIDENCE_ONLY
    assert securities["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT


def test_fundamental_policy_never_moves_valuation() -> None:
    stale = _decision(_all_stale(profitability_state="PROFITABLE", leverage_state="IMPROVING"))
    current = _decision(_compact(profitability_state="PROFITABLE", leverage_state="IMPROVING"))
    assert stale["fundamental_state"] != current["fundamental_state"]
    for key in ("valuation_context_summary", "valuation_methods"):
        assert stale[key] == current[key]


def test_policy_evaluation_is_deterministic_and_makes_no_network_call() -> None:
    events: list[str] = []

    def hook(event: str, _args: tuple) -> None:
        if event.startswith(("socket.", "http.client", "urllib")):
            events.append(event)

    sys.addaudithook(hook)
    record = _all_stale(profitability_state="LOSS_MAKING", leverage_state="WORSENING",
                        working_capital_trajectory_state="WORKING_CAPITAL_WORSENING")
    assert _synthesis(record) == _synthesis(record)
    _features({"2025-Q2": 10, "2026-Q2": -5})
    assert events == []
