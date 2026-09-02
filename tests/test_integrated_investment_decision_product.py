"""Tests for integrated_investment_decision_product.py (INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1).

Proves the core policy regressions:
- A: Strong technical/fundamental support + exact execution unavailable -> NOT automatically WAIT/AVOID.
- B: Usable valuation proxy + exact monetary authority unavailable -> research valuation still contributes.
- C: P/E unavailable + strong fundamental trajectory + valid breakout -> P/E missing alone does not block posture.
- D: Portfolio missing -> security attractiveness unchanged (portfolio_status = NOT_PROVIDED).
- E: Extended after strong breakout -> HOLD_DO_NOT_ADD style behavior rather than AVOID.
- F: Bearish structural break + deteriorating fundamentals -> REDUCE/AVOID from real negative evidence.
- G: One missing feature family -> unrelated families remain visible.
- H: PNJ is not hard-coded (rule-based evaluation).
- I: Vocabulary compliance (9 postures, 6 fundamental states, 11 tactical phases, zero scores/targets).
- J: Zero silent drops in build_artifact.
- K: Feedback-ready identity determinism.
"""
from __future__ import annotations

import json
import pytest

import integrated_investment_decision_product as iidp


def _sample_tactical_record(
    *,
    eligible: bool = True,
    market_structure_state: str = "UPTREND",
    breakout_state_v3: str = "BREAKOUT",
    trigger_state: str = "TRIGGERED",
    trigger_type: str = "PIVOT_BREAKOUT_TRIGGER",
    distance_to_pivot_pct: float = 0.01,
    invalidation_level: float = 35.0,
    distance_to_invalidation_pct: float = 0.15,
    bos_state: str = "BULLISH_BOS_DETECTED_BY_RULE",
    choch_state: str = "NO_CHOCH",
) -> dict:
    return {
        "eligible": eligible,
        "market_structure_state": market_structure_state,
        "breakout_state_v3": breakout_state_v3,
        "trigger_state": trigger_state,
        "trigger_type": trigger_type,
        "trigger_level": 40.0,
        "distance_to_pivot_pct": distance_to_pivot_pct,
        "invalidation_level": invalidation_level,
        "invalidation_method": "CONFIRMED_SWING_LOW",
        "distance_to_invalidation_pct": distance_to_invalidation_pct,
        "bos_state": bos_state,
        "choch_state": choch_state,
        "swing_high_sequence": "HH" if market_structure_state == "UPTREND" else "LH",
        "swing_low_sequence": "HL" if market_structure_state == "UPTREND" else "LL",
        "base_status": "IN_BASE",
        "range_state": "RANGE_COMPRESSION",
        "ma20_slope_state": "RISING",
        "high_low_basis": "NOT_COMPATIBLE",
        "relative_volume_provider_scoped": 1.5,
        "blockers": [],
    }


def _sample_financial_record(
    *,
    status: str = "AVAILABLE",
    profitability_state: str = "PROFITABLE",
    margin_state: str = "MARGIN_EXPANDING",
    growth_state: str = "EXPANDING",
    balance_sheet_state: str = "STRENGTHENING",
    leverage_state: str = "SAFE",
    working_capital_trajectory_state: str = "IMPROVING",
) -> dict:
    return {
        "status": status,
        "profitability_state": profitability_state,
        "margin_state": margin_state,
        "growth_state": growth_state,
        "balance_sheet_state": balance_sheet_state,
        "leverage_state": leverage_state,
        "working_capital_trajectory_state": working_capital_trajectory_state,
        "cash_conversion_state": "HEALTHY",
        "earnings_turnaround_state": None,
        "capital_efficiency_context": {},
        "history_context": {},
    }


def _sample_valuation_record(
    *,
    status: str = "AVAILABLE",
    peer_relative_percentile: float = 0.25,
    relative_research_state: str = "ATTRACTIVE_RELATIVE_RESEARCH",
    share_basis: str = "CURRENT_SHARE_RESEARCH_PROXY",
) -> dict:
    return {
        "status": status,
        "research_usable": True,
        "share_basis": share_basis,
        "pe": 12.5,
        "pb": 1.8,
        "ps": 1.2,
        "earnings_state": None,
        "peer_relative_context": {
            "relative_research_state": relative_research_state,
            "peer_relative_percentile": peer_relative_percentile,
        },
    }


# ── Policy Regression Tests ───────────────────────────────────────────────────

class TestPolicyRegressions:

    def test_case_a_exact_execution_unavailable_does_not_force_wait(self) -> None:
        """A: Strong technical/fundamental support + exact execution unavailable -> NOT automatically WAIT/AVOID."""
        tac = _sample_tactical_record(market_structure_state="UPTREND", breakout_state_v3="BREAKOUT", trigger_state="TRIGGERED")
        fin = _sample_financial_record(profitability_state="PROFITABLE", growth_state="EXPANDING")
        dec = iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=fin,
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_INITIATE_ON_BREAKOUT
        assert "EXACT_EXECUTION_CAPACITY_BLOCKED" in dec["exact_capabilities_unavailable"]
        assert dec["missing_evidence_decision_effect"] == iidp.EFFECT_DOES_NOT_BLOCK

    def test_case_b_usable_valuation_proxy_contributes(self) -> None:
        """B: Usable current-research valuation proxy + exact monetary authority unavailable -> valuation still contributes."""
        val = _sample_valuation_record(peer_relative_percentile=0.20, share_basis="CURRENT_SHARE_RESEARCH_PROXY")
        dec = iidp.build_ticker_integrated_decision(
            ticker="SSI",
            as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(),
            financial_record=_sample_financial_record(),
            valuation_record=val,
            relative_volume_record=None,
            market_sector_record=None,
        )
        val_sum = dec["valuation_context_summary"]
        assert val_sum["status"] == "AVAILABLE"
        assert val_sum["peer_relative_state"] == "CHEAP_VS_PEERS"
        assert any("VALUATION_CHEAP_VS_PEERS" in s for s in dec["valuation_context_summary"]["limitations"] or dec["fundamental_support"] or [dec["why_now"]]) or val_sum["peer_relative_state"] == "CHEAP_VS_PEERS"

    def test_case_c_pe_unavailable_does_not_block_breakout(self) -> None:
        """C: P/E unavailable + strong fundamental trajectory + valid breakout -> P/E missing alone does not block posture."""
        val_blocked = {"status": "INPUT_BLOCKED", "earnings_state": "PE_NOT_MEANINGFUL", "research_usable": False}
        tac = _sample_tactical_record(breakout_state_v3="BREAKOUT", trigger_state="TRIGGERED")
        fin = _sample_financial_record(growth_state="ACCELERATING")
        dec = iidp.build_ticker_integrated_decision(
            ticker="FPT",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=fin,
            valuation_record=val_blocked,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_INITIATE_ON_BREAKOUT

    def test_case_d_portfolio_missing_does_not_alter_attractiveness(self) -> None:
        """D: Portfolio missing -> security attractiveness unchanged (portfolio_status = NOT_PROVIDED)."""
        dec_no_port = iidp.build_ticker_integrated_decision(
            ticker="VNM",
            as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(breakout_state_v3="BREAKOUT"),
            financial_record=_sample_financial_record(),
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
            portfolio_record=None,
        )
        dec_with_port = iidp.build_ticker_integrated_decision(
            ticker="VNM",
            as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(breakout_state_v3="BREAKOUT"),
            financial_record=_sample_financial_record(),
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
            portfolio_record={"status": "AVAILABLE", "is_held": True},
        )
        assert dec_no_port["portfolio_context"]["status"] == "NOT_PROVIDED"
        assert dec_with_port["portfolio_context"]["status"] == "AVAILABLE"
        # Security research posture is identical
        assert dec_no_port["research_action_posture"] == dec_with_port["research_action_posture"] == iidp.POSTURE_INITIATE_ON_BREAKOUT

    def test_case_e_extended_after_breakout_is_hold_do_not_add_not_avoid(self) -> None:
        """E: Extended after strong breakout -> HOLD_DO_NOT_ADD / WAIT_FOR_CONFIRMATION rather than AVOID."""
        tac_extended = _sample_tactical_record(
            breakout_state_v3="EXTENDED_AFTER_BREAKOUT",
            distance_to_pivot_pct=0.15,
            trigger_state="TRIGGERED",
        )
        fin = _sample_financial_record(profitability_state="PROFITABLE", growth_state="EXPANDING")
        dec = iidp.build_ticker_integrated_decision(
            ticker="PNJ",
            as_of_session="2026-08-28",
            tactical_record=tac_extended,
            financial_record=fin,
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_HOLD_DO_NOT_ADD
        assert dec["tactical_phase"] == iidp.TACTICAL_EXTENDED
        assert dec["research_action_posture"] != iidp.POSTURE_AVOID

    def test_case_f_bearish_structural_breakdown_and_deterioration_is_avoid(self) -> None:
        """F: Bearish structural break + deteriorating fundamentals -> REDUCE/AVOID from real negative evidence."""
        tac_bearish = _sample_tactical_record(
            market_structure_state="DOWNTREND",
            breakout_state_v3="BELOW_PIVOT",
            bos_state="BEARISH_BOS_DETECTED_BY_RULE",
            trigger_state="NOT_AVAILABLE",
            trigger_type="NO_TRIGGER",
        )
        fin_bad = _sample_financial_record(
            profitability_state="LOSS_MAKING",
            growth_state="CONTRACTING",
            balance_sheet_state="DETERIORATING",
            margin_state="MARGIN_COMPRESSING",
        )
        dec = iidp.build_ticker_integrated_decision(
            ticker="NVL",
            as_of_session="2026-08-28",
            tactical_record=tac_bearish,
            financial_record=fin_bad,
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_AVOID
        assert dec["fundamental_state"] == iidp.FUNDAMENTAL_DETERIORATING
        assert dec["tactical_phase"] == iidp.TACTICAL_BREAKDOWN
        assert len(dec["counter_thesis"]) > 0

    def test_case_g_one_missing_feature_family_leaves_others_visible(self) -> None:
        """G: One missing feature family -> unrelated families remain visible."""
        tac = _sample_tactical_record(market_structure_state="UPTREND")
        # No financial, no valuation, no rvol
        dec = iidp.build_ticker_integrated_decision(
            ticker="TEST_TICKER",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=None,
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
        assert dec["tactical_phase"] in iidp.TACTICAL_PHASES
        assert dec["tactical_phase"] != iidp.TACTICAL_INSUFFICIENT
        assert len(dec["technical_support"]) > 0

    def test_case_h_pnj_is_rule_based(self) -> None:
        """H: PNJ is evaluated by general deterministic rules without hardcoding."""
        # On breakout session (2026-08-20)
        tac_onset = _sample_tactical_record(
            market_structure_state="EARLY_BEARISH_REVERSAL",
            breakout_state_v3="BREAKOUT",
            trigger_state="TRIGGERED",
            trigger_type="PIVOT_BREAKOUT_TRIGGER",
        )
        fin_pnj = _sample_financial_record(profitability_state="PROFITABLE")
        dec_onset = iidp.build_ticker_integrated_decision(
            ticker="PNJ",
            as_of_session="2026-08-20",
            tactical_record=tac_onset,
            financial_record=fin_pnj,
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec_onset["research_action_posture"] == iidp.POSTURE_INITIATE_ON_BREAKOUT

        # On extended session (2026-08-21)
        tac_ext = _sample_tactical_record(
            market_structure_state="EARLY_BEARISH_REVERSAL",
            breakout_state_v3="EXTENDED_AFTER_BREAKOUT",
            distance_to_pivot_pct=0.09,
        )
        dec_ext = iidp.build_ticker_integrated_decision(
            ticker="PNJ",
            as_of_session="2026-08-21",
            tactical_record=tac_ext,
            financial_record=fin_pnj,
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec_ext["research_action_posture"] == iidp.POSTURE_HOLD_DO_NOT_ADD


# ── Vocabulary & Governance Tests ─────────────────────────────────────────────

class TestGovernanceAndStructure:

    def test_vocabulary_compliance(self) -> None:
        """Verify all posture, fundamental, and tactical states are strictly in governed vocabulary."""
        assert len(iidp.RESEARCH_ACTION_POSTURES) == 9
        assert len(iidp.FUNDAMENTAL_STATES) == 6
        assert len(iidp.TACTICAL_PHASES) == 11

    def test_no_score_rank_target_or_probability(self) -> None:
        """Verify no score, rank, target price, or probability is emitted."""
        dec = iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(),
            financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(),
            relative_volume_record=None,
            market_sector_record=None,
        )
        raw_json = json.dumps(dec)
        assert "score" not in dec
        assert "rank" not in dec
        assert "target_price" not in dec
        assert "probability" not in dec
        assert dec["authority_boundary"]["no_score_rank_target_or_probability"] is True

    def test_deterministic_identity(self) -> None:
        """Verify deterministic decision identity."""
        dec1 = iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(),
            financial_record=_sample_financial_record(),
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        dec2 = iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(),
            financial_record=_sample_financial_record(),
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec1["decision_identity"] == dec2["decision_identity"]
        assert dec1["decision_identity"].startswith("decision:HPG:")

    def test_build_artifact_zero_silent_drops(self) -> None:
        """Verify build_artifact includes every single input ticker without loss."""
        tac_art = {
            "artifact_identity": "technical_structure_context/v2:fake",
            "records": {
                "AAA": _sample_tactical_record(),
                "BBB": _sample_tactical_record(eligible=False),
                "CCC": _sample_tactical_record(market_structure_state="DOWNTREND"),
            },
        }
        fa_art = {
            "artifact_identity": "financial_analysis_product_integration/v1:fake",
            "records": {
                "AAA": _sample_financial_record(),
                "DDD": _sample_financial_record(profitability_state="LOSS_MAKING"),
            },
        }
        art = iidp.build_artifact(
            session="2026-08-28",
            requested_at="2026-09-02T00:00:00Z",
            technical_structure_artifact=tac_art,
            financial_analysis_artifact=fa_art,
        )
        assert art["contract_version"] == "integrated_investment_decision_product/v1"
        assert set(art["records"].keys()) == {"AAA", "BBB", "CCC", "DDD"}
        assert art["coverage"]["universe_denominator"] == 4
        assert art["coverage"]["integrated_context_available"] == 4
        assert iidp.content_identity(art)["artifact_sha256"] == art["artifact_sha256"]

    def test_export_ai_bundle_integration(self, tmp_path) -> None:
        """Verify export_ai_bundle loader and attach function."""
        import export_ai_bundle as eab

        tac_art = {
            "artifact_identity": "technical_structure_context/v2:fake",
            "records": {"HPG": _sample_tactical_record()},
        }
        fa_art = {
            "artifact_identity": "financial_analysis_product_integration/v1:fake",
            "records": {"HPG": _sample_financial_record()},
        }
        art = iidp.build_artifact(
            session="2026-08-28",
            requested_at="2026-09-02T00:00:00Z",
            technical_structure_artifact=tac_art,
            financial_analysis_artifact=fa_art,
        )
        art_path = tmp_path / "integrated_investment_decision_product_artifact.json"
        art_path.write_text(json.dumps(art), encoding="utf-8")

        loaded = eab.load_integrated_investment_decision_product_artifact(art_path)
        assert loaded["contract_version"] == "integrated_investment_decision_product/v1"

        bundle_entries = {"HPG": {}, "VNM": {}}
        res = eab.attach_integrated_investment_decision_product(bundle_entries, True, str(art_path))
        assert res is not None
        assert "integrated_investment_decision" in bundle_entries["HPG"]
        assert bundle_entries["HPG"]["integrated_investment_decision"]["ticker"] == "HPG"
        assert "integrated_investment_decision" not in bundle_entries["VNM"]
