"""Focused tests for ASYMMETRIC_DISLOCATION_RESEARCH_V1.

Every fixture below is a synthetic, minimal `integrated_investment_decision_product/v1`
per-ticker record shape -- only the fields `asymmetric_dislocation_research.py` actually
reads. These tests do not exercise the real upstream engines; they prove this module's
own deterministic classification, evidence-axis extraction, ranking, and identity
contract given already-governed evidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asymmetric_dislocation_research as adr
import fundamental_signal_consumption_contract as contract

# Qualified LEVEL evidence (CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1): viable economics
# must be evidenced by a level, never inferred from the direction.
VIABLE = {"state": contract.NO_QUALIFIED_ADVERSE_LEVEL, "constructive_current_level_without_adverse": True,
          "adverse_level_dimensions": [], "constructive_level_dimensions": ["PROFITABILITY"]}
LOSS_MAKING_CURRENT = {"state": contract.ADVERSE_LEVEL_CURRENT, "constructive_current_level_without_adverse": False,
                       "adverse_level_dimensions": ["PROFITABILITY"], "constructive_level_dimensions": []}
LOSS_MAKING_STALE = {"state": contract.ADVERSE_LEVEL_KNOWN_NOT_CURRENT, "constructive_current_level_without_adverse": False,
                     "adverse_level_dimensions": ["PROFITABILITY"], "constructive_level_dimensions": []}


def _record(
    *,
    fundamental_state="STABLE",
    peer_relative_state="NOT_APPLICABLE",
    own_history_state="UNAVAILABLE",
    valuation_status="AVAILABLE",
    tactical_phase="INSUFFICIENT",
    market_structure_state=None,
    rsi_zone=None,
    corp_state="NOT_PROVIDED",
    corp_active_risk=0,
    invalidation_status="UNAVAILABLE",
    decision_identity="decision:fixture",
    risk_level=None,
    evidence_availability=None,
) -> dict:
    return {
        "fundamental_state": fundamental_state,
        **({"fundamental_risk_level": risk_level} if risk_level is not None else {}),
        **({"fundamental_evidence_availability": evidence_availability} if evidence_availability is not None else {}),
        "evidence_axes": {
            "FUNDAMENTAL": {"fitness": "AVAILABLE", "supporting_reason_codes": [], "contradicting_reason_codes": []},
            "TACTICAL_STRUCTURE": {"fitness": "AVAILABLE", "supporting_reason_codes": [], "contradicting_reason_codes": []},
        },
        "financial_composite_context": {"financial_composite_state": f"FUNDAMENTALS_{fundamental_state}"},
        "valuation_context_summary": {
            "status": valuation_status,
            "peer_relative_state": peer_relative_state,
            "own_history_state": own_history_state,
        },
        "tactical_phase": tactical_phase,
        "market_structure_state": market_structure_state,
        "breakout_state_v3": None,
        "momentum_context": {"rsi": {"zone": rsi_zone}} if rsi_zone is not None else {},
        "corporate_intelligence_context": {
            "state": corp_state, "fitness": "AVAILABLE" if corp_state != "NOT_PROVIDED" else "NOT_PROVIDED",
            "active_catalyst_count": 1 if corp_state == "CATALYST_PRESENT" else 0,
            "active_risk_count": corp_active_risk,
        },
        "invalidation": {"invalidation_level": 10.0, "condition": {"source_boundary_status": invalidation_status}},
        "decision_identity": decision_identity,
    }


def test_cheap_strong_economics_severe_price_dislocation_is_quality_dislocation():
    rec = _record(
        fundamental_state="STABLE", own_history_state="LOW_VS_OWN_HISTORY",
        valuation_status="AVAILABLE", tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND",
        risk_level=VIABLE,
    )
    out = adr.build_ticker_record(ticker="AAA", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.QUALITY_DISLOCATION
    assert out["research_eligibility"] == "ELIGIBLE_RESEARCH_CANDIDATE"
    assert out["economic_survivability_context"]["severe_deterioration_evidenced"] is False


def test_cheap_deteriorating_fundamentals_is_value_trap_risk():
    rec = _record(
        fundamental_state="DETERIORATING", own_history_state="LOW_VS_OWN_HISTORY",
        valuation_status="AVAILABLE", tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND",
    )
    out = adr.build_ticker_record(ticker="BBB", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.VALUE_TRAP_RISK
    assert out["research_eligibility"] == "NOT_ELIGIBLE"
    assert out["economic_survivability_context"]["severe_deterioration_evidenced"] is True
    # A cheap price never rescues a deteriorating fundamental read (mission requirement).
    assert "CHEAP_VALUATION_WITH_DETERIORATING_FUNDAMENTALS" in out["reason_codes"]


def test_improving_fundamentals_with_early_technical_recovery_is_cyclical_recovery_forming():
    rec = _record(
        fundamental_state="IMPROVING", own_history_state="MID_VS_OWN_HISTORY",
        valuation_status="AVAILABLE", tactical_phase="EARLY_REVERSAL", market_structure_state="EARLY_BULLISH_REVERSAL",
    )
    out = adr.build_ticker_record(ticker="CCC", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.CYCLICAL_RECOVERY_FORMING
    assert out["research_eligibility"] == "ELIGIBLE_RESEARCH_CANDIDATE"
    assert out["recovery_catalyst_context"]["technical_improving_evidenced"] is True


def test_explicit_turnaround_state_is_turnaround_evidence_forming():
    rec = _record(fundamental_state="TURNAROUND", valuation_status="UNAVAILABLE", tactical_phase="BASE_BUILDING")
    out = adr.build_ticker_record(ticker="DDD", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.TURNAROUND_EVIDENCE_FORMING
    assert out["research_eligibility"] == "ELIGIBLE_RESEARCH_CANDIDATE"


def test_distress_with_weak_survivability_and_active_risk_is_distress_speculative():
    rec = _record(
        fundamental_state="INSUFFICIENT", valuation_status="UNAVAILABLE",
        tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND",
        corp_state="RISK_PRESENT", corp_active_risk=1,
    )
    out = adr.build_ticker_record(ticker="EEE", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.DISTRESS_SPECULATIVE
    assert out["research_eligibility"] == "ELIGIBLE_RESEARCH_CANDIDATE"
    assert out["risk_invalidation_context"]["material_corporate_risk_active"] is True
    # Never a fabricated probability/target even for the high-risk/high-return case.
    assert out["scenario_asymmetry_context"]["state"] == adr.ASYMMETRY_NOT_QUANTIFIED


def test_oversold_only_case_is_no_qualified_dislocation():
    rec = _record(
        fundamental_state="STABLE", own_history_state="MID_VS_OWN_HISTORY",
        valuation_status="AVAILABLE", tactical_phase="INSUFFICIENT", rsi_zone="OVERSOLD",
    )
    out = adr.build_ticker_record(ticker="FFF", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.NO_QUALIFIED_DISLOCATION
    assert out["research_eligibility"] == "NOT_ELIGIBLE"
    assert "OVERSOLD_ALONE_NOT_SUFFICIENT" in out["reason_codes"]
    assert out["market_dislocation_context"]["oversold_only"] is True


def test_catalyst_with_no_economic_support_is_not_a_recovery_state():
    rec = _record(
        fundamental_state="DETERIORATING", own_history_state="MID_VS_OWN_HISTORY",
        valuation_status="AVAILABLE", tactical_phase="INSUFFICIENT",
        corp_state="CATALYST_PRESENT",
    )
    out = adr.build_ticker_record(ticker="GGG", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] not in {adr.CYCLICAL_RECOVERY_FORMING, adr.TURNAROUND_EVIDENCE_FORMING, adr.QUALITY_DISLOCATION}
    assert out["primary_research_state"] == adr.NO_QUALIFIED_DISLOCATION
    assert "CATALYST_PRESENT_BUT_NO_ECONOMIC_SUPPORT_EVIDENCED" in out["reason_codes"]


def test_financial_sector_applicability_is_explicit_and_non_gating():
    rec = _record(
        fundamental_state="STABLE", own_history_state="LOW_VS_OWN_HISTORY",
        valuation_status="AVAILABLE", tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND",
        risk_level=VIABLE,
    )
    out = adr.build_ticker_record(ticker="BANK1", session="2026-09-09", integrated_record=rec, entity_family="bank")
    # Same generic classification path as any other family -- no new bank-specific formula.
    assert out["primary_research_state"] == adr.QUALITY_DISLOCATION
    assert out["sector_model_applicability"]["entity_family"] == "bank"
    assert out["sector_model_applicability"]["specialist_financial_family"] is True


def test_missing_valuation_with_no_countervailing_evidence_is_insufficient_evidence():
    rec = _record(fundamental_state="STABLE", valuation_status="UNAVAILABLE", tactical_phase="INSUFFICIENT")
    out = adr.build_ticker_record(ticker="HHH", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.INSUFFICIENT_EVIDENCE
    assert "VALUATION_EVIDENCE_UNAVAILABLE" in out["missing_evidence_flags"]


def test_missing_fundamental_evidence_with_no_countervailing_evidence_is_insufficient_evidence():
    rec = _record(
        fundamental_state="INSUFFICIENT", own_history_state="LOW_VS_OWN_HISTORY",
        valuation_status="AVAILABLE", tactical_phase="INSUFFICIENT",
    )
    out = adr.build_ticker_record(ticker="III", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.INSUFFICIENT_EVIDENCE
    assert "FUNDAMENTAL_EVIDENCE_UNAVAILABLE" in out["missing_evidence_flags"]
    # Cheap valuation alone never rescues unknown survivability into a positive read.
    assert out["primary_research_state"] not in {adr.QUALITY_DISLOCATION, adr.VALUE_TRAP_RISK}


def test_deterministic_invalidation_present_and_absent():
    present = _record(invalidation_status="READY")
    absent = _record(invalidation_status="UNAVAILABLE")
    out_present = adr.build_ticker_record(ticker="JJJ", session="2026-09-09", integrated_record=present)
    out_absent = adr.build_ticker_record(ticker="JJJ", session="2026-09-09", integrated_record=absent)
    assert out_present["risk_invalidation_context"]["state"] == "READY"
    assert out_absent["risk_invalidation_context"]["state"] == "UNAVAILABLE"


def test_no_target_or_probability_fabrication_anywhere_in_record():
    rec = _record(
        fundamental_state="INSUFFICIENT", valuation_status="UNAVAILABLE",
        tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND", corp_active_risk=1, corp_state="RISK_PRESENT",
    )
    out = adr.build_ticker_record(ticker="KKK", session="2026-09-09", integrated_record=rec)

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if not lowered.startswith("no_") and not lowered.startswith("does_not"):
                    assert "probability" not in lowered
                    assert "target_price" not in lowered
                    assert "expected_return" not in lowered
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(out)


def test_artifact_is_deterministic_and_idempotent():
    product = {
        "session": "2026-09-09",
        "artifact_identity": "integrated_investment_decision_product:fixture",
        "records": {
            "AAA": _record(fundamental_state="STABLE", own_history_state="LOW_VS_OWN_HISTORY", tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND"),
            "BBB": _record(fundamental_state="DETERIORATING", own_history_state="LOW_VS_OWN_HISTORY"),
        },
    }
    first = adr.build_artifact(session="2026-09-09", integrated_product=product)
    second = adr.build_artifact(session="2026-09-09", integrated_product=product)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["coverage"]["universe_denominator"] == 2


def test_no_future_session_leakage():
    product_today = {
        "session": "2026-09-09",
        "records": {"AAA": _record(fundamental_state="STABLE")},
    }
    out = adr.build_artifact(session="2026-09-09", integrated_product=product_today)
    assert out["records"]["AAA"]["research_session"] == "2026-09-09"
    try:
        adr.build_artifact(session="2026-09-08", integrated_product=product_today)
        raised = False
    except adr.AsymmetricDislocationResearchError:
        raised = True
    assert raised, "a session mismatch between the requested session and the retained artifact must fail closed"


def test_ordering_is_stable_and_lexicographic():
    product = {
        "session": "2026-09-09",
        "records": {
            "ZQD": _record(fundamental_state="STABLE", own_history_state="LOW_VS_OWN_HISTORY", tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND", risk_level=VIABLE),
            "AQD": _record(fundamental_state="STABLE", own_history_state="LOW_VS_OWN_HISTORY", tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND", risk_level=VIABLE),
            "TEF": _record(fundamental_state="TURNAROUND", valuation_status="UNAVAILABLE"),
            "DSP": _record(fundamental_state="INSUFFICIENT", valuation_status="UNAVAILABLE", tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND", corp_state="RISK_PRESENT", corp_active_risk=1),
        },
    }
    first = adr.build_artifact(session="2026-09-09", integrated_product=product)["top_candidates"]
    reordered_product = {"session": "2026-09-09", "records": dict(reversed(list(product["records"].items())))}
    second = adr.build_artifact(session="2026-09-09", integrated_product=reordered_product)["top_candidates"]
    assert first == second
    # QUALITY_DISLOCATION tier ranks above TURNAROUND_EVIDENCE_FORMING above DISTRESS_SPECULATIVE;
    # within the same tier, AQD sorts before ZQD alphabetically.
    assert [c["ticker"] for c in first] == ["AQD", "ZQD", "TEF", "DSP"]


# ── CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1: survivability from level evidence ──────

def test_loss_making_with_improving_direction_cheap_and_breakdown_is_never_quality_dislocation():
    for state, recovery in (("IMPROVING", {}), ("STABLE", {}), ("MIXED", {"corp_state": "CATALYST_PRESENT"})):
        rec = _record(fundamental_state=state, own_history_state="LOW_VS_OWN_HISTORY", valuation_status="AVAILABLE",
                      tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND", risk_level=LOSS_MAKING_CURRENT,
                      **recovery)
        out = adr.build_ticker_record(ticker="LMI", session="2026-09-09", integrated_record=rec)
        assert out["primary_research_state"] != adr.QUALITY_DISLOCATION, state
        assert out["primary_research_state"] == adr.DISTRESS_SPECULATIVE
        survivability = out["economic_survivability_context"]
        assert survivability["survivability"] == "ADVERSE_LEVEL_EVIDENCED"
        assert survivability["survivability_inferred_from_direction"] is False


def test_direction_alone_never_evidences_viable_economics():
    rec = _record(fundamental_state="IMPROVING", own_history_state="LOW_VS_OWN_HISTORY", valuation_status="AVAILABLE",
                  tactical_phase="BREAKDOWN", market_structure_state="DOWNTREND")  # no level evidence at all
    out = adr.build_ticker_record(ticker="DIR", session="2026-09-09", integrated_record=rec)
    assert out["primary_research_state"] == adr.NO_QUALIFIED_DISLOCATION
    assert "CHEAP_PRICE_DISLOCATION_VIABLE_ECONOMICS_NOT_ESTABLISHED" in out["reason_codes"]
    assert out["economic_survivability_context"]["viable_economics_evidenced"] is False


def test_stale_adverse_level_stays_known_adverse_history_not_unknown_survivability():
    rec = _record(fundamental_state="INSUFFICIENT", own_history_state="LOW_VS_OWN_HISTORY", valuation_status="AVAILABLE",
                  tactical_phase="INSUFFICIENT", risk_level=LOSS_MAKING_STALE, evidence_availability=contract.STALE_ONLY)
    out = adr.build_ticker_record(ticker="STL", session="2026-09-09", integrated_record=rec)
    survivability = out["economic_survivability_context"]
    assert survivability["survivability"] == "ADVERSE_HISTORY_KNOWN"
    assert survivability["fundamental_evidence_availability"] == contract.STALE_ONLY
    assert "FUNDAMENTAL_EVIDENCE_UNAVAILABLE" not in out["missing_evidence_flags"]
    assert out["primary_research_state"] == adr.VALUE_TRAP_RISK
    breakdown = _record(fundamental_state="INSUFFICIENT", valuation_status="UNAVAILABLE", tactical_phase="BREAKDOWN",
                        market_structure_state="DOWNTREND", risk_level=LOSS_MAKING_STALE)
    out = adr.build_ticker_record(ticker="STB", session="2026-09-09", integrated_record=breakdown)
    assert out["primary_research_state"] == adr.DISTRESS_SPECULATIVE
    assert "PRICE_BREAKDOWN_WITH_KNOWN_ADVERSE_LEVEL" in out["reason_codes"]


def test_unknown_survivability_only_when_no_level_can_be_established():
    rec = _record(fundamental_state="INSUFFICIENT", own_history_state="LOW_VS_OWN_HISTORY", valuation_status="AVAILABLE",
                  tactical_phase="INSUFFICIENT", evidence_availability=contract.ABSENT)
    out = adr.build_ticker_record(ticker="UNK", session="2026-09-09", integrated_record=rec)
    assert out["economic_survivability_context"]["survivability"] == "UNKNOWN_SURVIVABILITY"
    assert "FUNDAMENTAL_EVIDENCE_UNAVAILABLE" in out["missing_evidence_flags"]


def test_survivability_reads_the_level_from_a_retained_synthesis_never_the_direction():
    import integrated_investment_decision_product as iidp
    compact = {"contract_version": "financial_analysis_compact/v1", "status": "AVAILABLE",
               "analysis_family": "INDUSTRIAL_FINANCIAL_ANALYSIS", "issuer_type": "corporate",
               "profitability_state": "LOSS_MAKING", "balance_sheet_state": "STRENGTHENING", "leverage_state": "IMPROVING",
               "current_ratio_trajectory_state": "CURRENT_RATIO_IMPROVING",
               "feature_fitness": {f: {"fitness": "READY", "as_of_period": "2026-Q2", "reason_codes": []}
                                   for f in ("net_income_sign", "equity_to_assets_direction", "debt_to_equity_direction",
                                             "current_ratio_direction")}}
    decision = iidp.build_ticker_integrated_decision(
        ticker="AAA", as_of_session="2026-09-24", tactical_record=None, financial_record=compact,
        valuation_record=None, relative_volume_record=None, market_sector_record=None)
    assert decision["fundamental_risk_level"]["state"] == contract.ADVERSE_LEVEL_CURRENT
    out = adr.build_ticker_record(ticker="AAA", session="2026-09-24", integrated_record=decision)
    assert out["economic_survivability_context"]["adverse_level_evidenced"] is True
    assert out["economic_survivability_context"]["viable_economics_evidenced"] is False


def test_known_non_current_constructive_level_is_never_flagged_as_unavailable_evidence():
    stale_profitable = {"state": contract.NO_QUALIFIED_ADVERSE_LEVEL, "constructive_current_level_without_adverse": False,
                        "adverse_level_dimensions": [], "constructive_level_dimensions": ["PROFITABILITY"]}
    rec = _record(fundamental_state="INSUFFICIENT", own_history_state="LOW_VS_OWN_HISTORY", valuation_status="AVAILABLE",
                  tactical_phase="INSUFFICIENT", risk_level=stale_profitable, evidence_availability=contract.STALE_ONLY)
    out = adr.build_ticker_record(ticker="SCP", session="2026-09-09", integrated_record=rec)
    assert "FUNDAMENTAL_EVIDENCE_UNAVAILABLE" not in out["missing_evidence_flags"]
    assert "FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT" in out["missing_evidence_flags"]
    assert out["economic_survivability_context"]["survivability"] == "NO_ADVERSE_LEVEL_NOT_CURRENT_CONSTRUCTIVE"
    assert out["primary_research_state"] != adr.QUALITY_DISLOCATION
    # Stale direction evidence without any level: known evidence, survivability not established.
    rec = _record(fundamental_state="INSUFFICIENT", valuation_status="AVAILABLE", tactical_phase="INSUFFICIENT",
                  evidence_availability=contract.STALE_ONLY)
    out = adr.build_ticker_record(ticker="SDR", session="2026-09-09", integrated_record=rec)
    assert out["missing_evidence_flags"] == ["FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT", "SURVIVABILITY_LEVEL_NOT_ESTABLISHED"]
    assert out["primary_research_state"] == adr.INSUFFICIENT_EVIDENCE
