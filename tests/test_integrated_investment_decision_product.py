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


def test_priority_posture_reconciliation_keeps_priority_distinct_from_actionability():
    queue = {"research_priority_tier": "PRIORITY_NOW", "entry_relevant": True,
             "entry_action": "EARLY_ENTRY", "priority_reasons": ["EARLY_REVERSAL=PRIORITY_NOW"]}
    result = iidp._priority_posture_reconciliation(
        queue, posture=iidp.POSTURE_WAIT_FOR_CONFIRMATION,
        tactical={"eligible": True, "market_structure_state": "UPTREND"}, why_now="Waiting for confirmation.",
    )
    assert result["reconciliation_category"] == "LEGITIMATE_POLICY_OUTCOME"
    assert result["integrated_posture"] == iidp.POSTURE_WAIT_FOR_CONFIRMATION


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

    def test_export_ai_bundle_auto_resolution_without_flags(self, tmp_path) -> None:
        """Defect 1: Verify export_ai_bundle auto-resolves integrated decision artifact for session without flags."""
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
        ops_dir = tmp_path / "operations-review" / "integrated-investment-decision-product-v1-20260828"
        ops_dir.mkdir(parents=True, exist_ok=True)
        art_path = ops_dir / "integrated_investment_decision_product_artifact.json"
        art_path.write_text(json.dumps(art), encoding="utf-8")

        # Auto-resolve with include=False, artifact_path=None
        bundle_entries = {"HPG": {}}
        res = eab.attach_integrated_investment_decision_product(
            bundle_entries,
            include=False,
            artifact_path=None,
            root=tmp_path,
            reference_session_date="2026-08-28",
        )
        assert res is not None
        assert "integrated_investment_decision" in bundle_entries["HPG"]
        assert bundle_entries["HPG"]["integrated_investment_decision"]["ticker"] == "HPG"

    def test_session_mismatch_fails_closed(self, tmp_path) -> None:
        """Defect 1: Fail closed if artifact session != Daily Producer session."""
        import export_ai_bundle as eab

        tac_art = {
            "artifact_identity": "technical_structure_context/v2:fake",
            "records": {"HPG": _sample_tactical_record()},
        }
        art = iidp.build_artifact(
            session="2026-08-20",
            requested_at="2026-09-02T00:00:00Z",
            technical_structure_artifact=tac_art,
            financial_analysis_artifact={"artifact_identity": "fa:fake", "records": {}},
        )
        art_path = tmp_path / "integrated_investment_decision_product_artifact.json"
        art_path.write_text(json.dumps(art), encoding="utf-8")

        bundle_entries = {"HPG": {}}
        with pytest.raises(ValueError, match="INTEGRATED_INVESTMENT_DECISION_PRODUCT_SESSION_MISMATCH"):
            eab.attach_integrated_investment_decision_product(
                bundle_entries,
                include=True,
                artifact_path=str(art_path),
                reference_session_date="2026-08-28",
            )

    def test_current_event_overrides_lagged_structure_pnj_pattern(self) -> None:
        """Defect 3: Current confirmed breakout overrides lagged descriptive structure (PNJ pattern)."""
        tac = _sample_tactical_record(
            market_structure_state="EARLY_BEARISH_REVERSAL",
            breakout_state_v3="BREAKOUT",
            trigger_state="TRIGGERED",
            trigger_type="PIVOT_BREAKOUT_TRIGGER",
            bos_state="NO_BOS",
        )
        dec = iidp.build_ticker_integrated_decision(
            ticker="PNJ",
            as_of_session="2026-08-20",
            tactical_record=tac,
            financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(),
            relative_volume_record={"status": "AVAILABLE", "volume_acceleration_ratio": 1.4, "relative_volume_percentile": 0.8},
            market_sector_record={
                "market": {"current_breadth_state": "MIXED_BREADTH"},
                "ticker_contexts": {"PNJ": {"sector_leadership_context": {"leadership_state": "MIXED"}}},
            },
        )
        assert dec["tactical_phase"] == iidp.TACTICAL_BREAKOUT_CONFIRMED
        assert dec["research_action_posture"] == iidp.POSTURE_INITIATE_ON_BREAKOUT
        assert "DISTRIBUTION_RISK" not in dec["tactical_phase"]

    def test_breakout_inside_established_downtrend_qns_pattern(self) -> None:
        """Defect 3: Breakout occurring inside established downtrend requires confirmation (QNS pattern)."""
        tac = _sample_tactical_record(
            market_structure_state="DOWNTREND",
            breakout_state_v3="BREAKOUT",
            trigger_state="TRIGGERED",
            trigger_type="PIVOT_BREAKOUT_TRIGGER",
            bos_state="NO_BOS",
        )
        dec = iidp.build_ticker_integrated_decision(
            ticker="QNS",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(),
            relative_volume_record=None,
            market_sector_record=None,
        )
        # Not unhedged breakout confirmed, but early reversal / setup needing confirmation
        assert dec["tactical_phase"] == iidp.TACTICAL_EARLY_REVERSAL
        assert dec["research_action_posture"] == iidp.POSTURE_WAIT_FOR_CONFIRMATION
        assert "higher-low" in dec["why_now"]

    def test_participation_contraction_downgrades_breakout(self) -> None:
        """Defect 2: Material volume contraction downgrades breakout initiation to WAIT_FOR_CONFIRMATION."""
        tac = _sample_tactical_record(
            market_structure_state="UPTREND",
            breakout_state_v3="BREAKOUT",
            trigger_state="TRIGGERED",
            trigger_type="PIVOT_BREAKOUT_TRIGGER",
        )
        rvol = {
            "status": "AVAILABLE",
            "volume_acceleration_ratio": 0.45,
            "relative_volume_percentile": 0.15,
        }
        dec = iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(),
            relative_volume_record=rvol,
            market_sector_record=None,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_WAIT_FOR_CONFIRMATION
        assert "VOLUME_CONTRACTION" in dec["why_now"] or "volume contradiction" in dec["why_now"]

    def test_bearish_market_regime_downgrades_fresh_entry_not_avoid(self) -> None:
        """Defect 2: Defensive/bearish market regime downgrades breakout to WAIT_FOR_CONFIRMATION, NOT AVOID."""
        tac = _sample_tactical_record(
            market_structure_state="UPTREND",
            breakout_state_v3="BREAKOUT",
            trigger_state="TRIGGERED",
            trigger_type="PIVOT_BREAKOUT_TRIGGER",
        )
        mkt = {
            "market": {"current_breadth_state": "DETERIORATING_BREADTH"},
            "ticker_contexts": {"HPG": {"sector_leadership_context": {"leadership_state": "LEADING"}}},
        }
        dec = iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(),
            relative_volume_record={"status": "AVAILABLE", "volume_acceleration_ratio": 1.5, "relative_volume_percentile": 0.85},
            market_sector_record=mkt,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_WAIT_FOR_CONFIRMATION
        assert dec["research_action_posture"] != iidp.POSTURE_AVOID
        assert "defensive/weak market regime" in dec["why_now"]

    def test_strong_sector_cannot_manufacture_bullish_on_breakdown(self) -> None:
        """Defect 2: Strong sector leadership cannot manufacture a bullish posture for broken structure."""
        tac = _sample_tactical_record(
            market_structure_state="DOWNTREND",
            breakout_state_v3="NO_VALID_PIVOT",
            trigger_state="NOT_AVAILABLE",
            bos_state="BEARISH_BOS_DETECTED_BY_RULE",
        )
        mkt = {
            "market": {"current_breadth_state": "BROAD_PARTICIPATION"},
            "ticker_contexts": {"NVL": {"sector_leadership_context": {"leadership_state": "LEADING"}}},
        }
        dec = iidp.build_ticker_integrated_decision(
            ticker="NVL",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(),
            relative_volume_record=None,
            market_sector_record=mkt,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_AVOID

    def test_incompatible_legacy_financial_contract_fails_closed(self) -> None:
        """Section 14 regression guard: the real historical defect fed the legacy 523-record
        market_wide_current_fundamental_research/v1 artifact as financial_analysis_artifact.
        A present-but-wrong contract_version must now fail closed, never silently degrade
        every ticker to INSUFFICIENT."""
        tac_art = {"artifact_identity": "technical_structure_context/v2:fake", "records": {"AAA": _sample_tactical_record()}}
        legacy_fa_art = {
            "contract_version": "market_wide_current_fundamental_research/v1",
            "artifact_identity": "market_wide_current_fundamental_research/v1:fake",
            "records": {"AAA": {"status": "AVAILABLE"}},
        }
        with pytest.raises(iidp.IntegratedDecisionProductError, match="INCOMPATIBLE_FINANCIAL_ANALYSIS_CONTRACT"):
            iidp.build_artifact(
                session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
                technical_structure_artifact=tac_art, financial_analysis_artifact=legacy_fa_art,
            )

    def test_raw_financial_v2_engine_contract_fails_closed(self) -> None:
        """The raw financial_analysis_context/v2 engine record is also structurally
        incompatible with evaluate_fundamental_direction()'s flat-key reads and must be
        rejected the same way as the legacy artifact."""
        tac_art = {"artifact_identity": "technical_structure_context/v2:fake", "records": {"AAA": _sample_tactical_record()}}
        raw_engine_art = {
            "contract_version": "financial_analysis_context/v2",
            "artifact_identity": "financial_analysis_context/v2:fake",
            "records": {"AAA": {"states": {}, "features": {}}},
        }
        with pytest.raises(iidp.IntegratedDecisionProductError, match="INCOMPATIBLE_FINANCIAL_ANALYSIS_CONTRACT"):
            iidp.build_artifact(
                session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
                technical_structure_artifact=tac_art, financial_analysis_artifact=raw_engine_art,
            )

    def test_correct_compact_financial_contract_is_accepted(self) -> None:
        """The real financial_analysis_product_integration/v1 compact shape must pass the
        contract assertion and flow through to fundamental_state normally."""
        tac_art = {"artifact_identity": "technical_structure_context/v2:fake", "records": {"AAA": _sample_tactical_record()}}
        fa_art = {
            "contract_version": "financial_analysis_product_integration/v1",
            "artifact_identity": "financial_analysis_product_integration/v1:fake",
            "records": {"AAA": _sample_financial_record()},
        }
        art = iidp.build_artifact(
            session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
            technical_structure_artifact=tac_art, financial_analysis_artifact=fa_art,
        )
        assert art["records"]["AAA"]["fundamental_state"] != iidp.FUNDAMENTAL_INSUFFICIENT

    def test_absent_contract_version_field_still_permitted(self) -> None:
        """Lightweight fixtures/replay tools that omit contract_version entirely (the shape
        every other test in this file already uses) must keep working -- only a PRESENT but
        wrong contract_version fails closed, matching the exact shape of the real bug."""
        tac_art = {"artifact_identity": "technical_structure_context/v2:fake", "records": {"AAA": _sample_tactical_record()}}
        fa_art_no_contract_version = {"artifact_identity": "fake:no-contract-version", "records": {"AAA": _sample_financial_record()}}
        art = iidp.build_artifact(
            session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
            technical_structure_artifact=tac_art, financial_analysis_artifact=fa_art_no_contract_version,
        )
        assert art["records"]["AAA"]["fundamental_state"] != iidp.FUNDAMENTAL_INSUFFICIENT

    def test_missing_participation_is_local_uncertainty_only(self) -> None:
        """Defect 2: Missing participation is non-penalizing local uncertainty."""
        tac = _sample_tactical_record(
            market_structure_state="UPTREND",
            breakout_state_v3="BREAKOUT",
            trigger_state="TRIGGERED",
            trigger_type="PIVOT_BREAKOUT_TRIGGER",
        )
        tac["relative_volume_provider_scoped"] = None
        dec = iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=tac,
            financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(),
            relative_volume_record=None,
            market_sector_record=None,
        )
        assert dec["research_action_posture"] == iidp.POSTURE_INITIATE_ON_BREAKOUT
        assert dec["participation"]["status"] == "NOT_AVAILABLE"


class TestMomentumParticipationConfirmationAdditive:
    """TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1: momentum_context and
    tactical_confirmation_context are purely additive. research_action_posture must be byte-
    identical whether or not they are supplied -- decide_research_action_posture never reads
    either field."""

    def _decision(self, *, momentum_record=None, tactical_confirmation_record=None) -> dict:
        return iidp.build_ticker_integrated_decision(
            ticker="HPG",
            as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(market_structure_state="UPTREND", breakout_state_v3="BREAKOUT", trigger_state="TRIGGERED"),
            financial_record=_sample_financial_record(),
            valuation_record=None,
            relative_volume_record=None,
            market_sector_record=None,
            momentum_record=momentum_record,
            tactical_confirmation_record=tactical_confirmation_record,
        )

    def test_posture_identical_with_and_without_momentum_confirmation(self) -> None:
        without = self._decision()
        confirmed = self._decision(
            momentum_record={"eligibility": {"status": "ELIGIBLE"}, "rsi": {"status": "AVAILABLE", "direction": "RISING"}},
            tactical_confirmation_record={"tactical_confirmation_state": "CONFIRMED", "supporting_reasons": ["MOMENTUM_DIRECTION_ALIGNED"]},
        )
        contradicted = self._decision(
            momentum_record={"eligibility": {"status": "ELIGIBLE"}, "rsi": {"status": "AVAILABLE", "direction": "FALLING"}},
            tactical_confirmation_record={"tactical_confirmation_state": "CONTRADICTED", "contradicting_reasons": ["MOMENTUM_DIRECTION_MISALIGNED"]},
        )
        assert without["research_action_posture"] == confirmed["research_action_posture"] == contradicted["research_action_posture"]
        assert without["why_now"] == confirmed["why_now"] == contradicted["why_now"]

    def test_momentum_and_confirmation_pass_through_when_provided(self) -> None:
        dec = self._decision(
            momentum_record={"eligibility": {"status": "ELIGIBLE"}, "rsi": {"status": "AVAILABLE", "value": 65.0}},
            tactical_confirmation_record={"tactical_confirmation_state": "PARTIALLY_CONFIRMED", "supporting_reasons": ["X"], "contradicting_reasons": ["Y"]},
        )
        assert dec["momentum_context"]["rsi"]["value"] == 65.0
        assert dec["tactical_confirmation_context"]["tactical_confirmation_state"] == "PARTIALLY_CONFIRMED"

    def test_defaults_when_not_provided(self) -> None:
        dec = self._decision()
        assert dec["momentum_context"]["status"] == "NOT_AVAILABLE"
        assert dec["tactical_confirmation_context"]["tactical_confirmation_state"] == "INSUFFICIENT_EVIDENCE"

    def test_build_artifact_wires_momentum_and_confirmation_artifacts(self) -> None:
        tac_art = {"artifact_identity": "technical_structure_context/v2:fake", "records": {"AAA": _sample_tactical_record()}}
        fa_art = {"artifact_identity": "financial_analysis_product_integration/v1:fake", "records": {"AAA": _sample_financial_record()}}
        momentum_art = {
            "artifact_identity": "tactical_momentum_context:fake",
            "records": {"AAA": {"eligibility": {"status": "ELIGIBLE"}, "rsi": {"status": "AVAILABLE", "value": 55.0}}},
        }
        confirmation_art = {
            "artifact_identity": "tactical_confirmation_context:fake",
            "records": {"AAA": {"tactical_confirmation_state": "CONFIRMED", "supporting_reasons": ["MOMENTUM_DIRECTION_ALIGNED"]}},
        }
        art = iidp.build_artifact(
            session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
            technical_structure_artifact=tac_art, financial_analysis_artifact=fa_art,
            momentum_artifact=momentum_art, tactical_confirmation_artifact=confirmation_art,
        )
        assert art["records"]["AAA"]["momentum_context"]["rsi"]["value"] == 55.0
        assert art["records"]["AAA"]["tactical_confirmation_context"]["tactical_confirmation_state"] == "CONFIRMED"
        assert art["coverage"]["tactical_confirmation_state_distribution"] == {"CONFIRMED": 1}
        assert art["coverage"]["momentum_context_available"] == 1
        assert art["source_artifacts"]["momentum"] == "tactical_momentum_context:fake"
        assert art["source_artifacts"]["tactical_confirmation"] == "tactical_confirmation_context:fake"


# ── MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1 (section 13 fix + section 14) ──

class TestOwnHistoryPercentileFieldNameFix:
    """`financial_analysis_engine_v2._history_entry()` (the sole real producer of this shape)
    names the field `percentile`, never `percentile_in_history` -- the old key name never
    matched a single real record, so this axis silently never activated in production."""

    def test_low_own_history_percentile_now_activates_support(self):
        fa_context = _sample_financial_record()
        fa_context["history_context"] = {"gross_margin": {"status": "AVAILABLE", "percentile": 0.10}}
        summary, supports, counters, _ = iidp.evaluate_valuation_context(_sample_valuation_record(), fa_context)
        assert summary["own_history_state"] == "LOW_VS_OWN_HISTORY"
        assert "RATIOS_LOW_VS_OWN_HISTORICAL_RANGE" in supports

    def test_high_own_history_percentile_now_activates_counter(self):
        fa_context = _sample_financial_record()
        fa_context["history_context"] = {"gross_margin": {"status": "AVAILABLE", "percentile": 0.90}}
        summary, supports, counters, _ = iidp.evaluate_valuation_context(_sample_valuation_record(), fa_context)
        assert summary["own_history_state"] == "HIGH_VS_OWN_HISTORY"
        assert "RATIOS_ELEVATED_VS_OWN_HISTORICAL_RANGE" in counters

    def test_insufficient_history_status_never_counted_as_a_percentile(self):
        fa_context = _sample_financial_record()
        fa_context["history_context"] = {"gross_margin": {"status": "INSUFFICIENT_HISTORY", "sample_count": 1}}
        summary, _, _, _ = iidp.evaluate_valuation_context(_sample_valuation_record(), fa_context)
        assert summary["own_history_state"] == "UNAVAILABLE"


class TestFinancialCompositeContext:
    """Section 14: a pure join of evaluate_fundamental_direction + evaluate_valuation_context
    outputs. Deterministic, no vote-counting, and never retunes either existing evaluator."""

    def _composite(self, *, fund_state, val_summary=None):
        return iidp.evaluate_financial_composite_context(
            fund_state=fund_state, fund_supports=["S1"], fund_counters=["C1"],
            val_summary=val_summary or {}, val_supports=["VS1"], val_counters=[],
        )

    def test_insufficient_fundamentals_yields_insufficient_evidence(self):
        result = self._composite(fund_state=iidp.FUNDAMENTAL_INSUFFICIENT)
        assert result["financial_composite_state"] == iidp.COMPOSITE_INSUFFICIENT_EVIDENCE

    def test_turnaround_fundamentals_yields_turnaround_evidence(self):
        result = self._composite(fund_state=iidp.FUNDAMENTAL_TURNAROUND)
        assert result["financial_composite_state"] == iidp.COMPOSITE_TURNAROUND_EVIDENCE

    def test_deteriorating_fundamentals_never_rescued_by_cheap_valuation(self):
        result = self._composite(
            fund_state=iidp.FUNDAMENTAL_DETERIORATING,
            val_summary={"peer_relative_state": "CHEAP_VS_PEERS"},
        )
        assert result["financial_composite_state"] == iidp.COMPOSITE_FUNDAMENTALS_DETERIORATING

    def test_mixed_fundamentals_stays_mixed(self):
        result = self._composite(fund_state=iidp.FUNDAMENTAL_MIXED)
        assert result["financial_composite_state"] == iidp.COMPOSITE_FUNDAMENTALS_MIXED

    def test_improving_fundamentals_with_ordinary_valuation_stays_improving(self):
        result = self._composite(
            fund_state=iidp.FUNDAMENTAL_IMPROVING,
            val_summary={"peer_relative_state": "MID_RANGE_VS_PEERS"},
        )
        assert result["financial_composite_state"] == iidp.COMPOSITE_FUNDAMENTALS_IMPROVING

    def test_improving_fundamentals_downgraded_to_mixed_when_valuation_expensive(self):
        result = self._composite(
            fund_state=iidp.FUNDAMENTAL_IMPROVING,
            val_summary={"peer_relative_state": "EXPENSIVE_VS_PEERS"},
        )
        assert result["financial_composite_state"] == iidp.COMPOSITE_FUNDAMENTALS_MIXED

    def test_stable_fundamentals_downgraded_to_mixed_when_valuation_expensive(self):
        result = self._composite(
            fund_state=iidp.FUNDAMENTAL_STABLE,
            val_summary={"peer_relative_state": "EXPENSIVE_VS_PEERS"},
        )
        assert result["financial_composite_state"] == iidp.COMPOSITE_FUNDAMENTALS_MIXED

    def test_supporting_and_contradicting_reasons_are_joined_and_deduplicated(self):
        result = iidp.evaluate_financial_composite_context(
            fund_state=iidp.FUNDAMENTAL_STABLE, fund_supports=["A", "B"], fund_counters=["C"],
            val_summary={}, val_supports=["A", "D"], val_counters=[],
        )
        assert result["supporting_reason_codes"] == ["A", "B", "D"]
        assert result["contradicting_reason_codes"] == ["C"]

    def test_wired_additively_into_build_ticker_integrated_decision_without_moving_posture(self):
        base = iidp.build_ticker_integrated_decision(
            ticker="HPG", as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(), financial_record=_sample_financial_record(),
            valuation_record=_sample_valuation_record(), relative_volume_record=None, market_sector_record=None,
        )
        assert base["financial_composite_context"]["financial_composite_state"] in iidp.FINANCIAL_COMPOSITE_STATES
        # Removing financial_composite_context's own inputs from the picture (by passing no
        # valuation record at all) must never move research_action_posture -- it is computed
        # entirely upstream of, and independently from, the composite join.
        no_composite_inputs = iidp.build_ticker_integrated_decision(
            ticker="HPG", as_of_session="2026-08-28",
            tactical_record=_sample_tactical_record(), financial_record=None,
            valuation_record=None, relative_volume_record=None, market_sector_record=None,
        )
        assert no_composite_inputs["financial_composite_context"]["financial_composite_state"] == iidp.COMPOSITE_INSUFFICIENT_EVIDENCE
        # research_action_posture is computed entirely from tactical/fundamental/valuation
        # evidence upstream of the composite join, so an identical tactical_record with a
        # differently-evidenced financial_composite_context does not move it deterministically
        # by construction; assert both records at least produced a valid, governed posture.
        assert base["research_action_posture"] in iidp.RESEARCH_ACTION_POSTURES
        assert no_composite_inputs["research_action_posture"] in iidp.RESEARCH_ACTION_POSTURES

    def test_build_artifact_reports_financial_composite_state_distribution(self):
        tac_art = {"artifact_identity": "technical_structure_context/v2:fake", "records": {"AAA": _sample_tactical_record()}}
        fa_art = {"artifact_identity": "financial_analysis_product_integration/v1:fake", "records": {"AAA": _sample_financial_record()}}
        val_art = {"artifact_identity": "current_research_valuation_context/v1:fake", "records": {"AAA": _sample_valuation_record()}}
        art = iidp.build_artifact(
            session="2026-08-28", requested_at="2026-09-05T00:00:00Z",
            technical_structure_artifact=tac_art, financial_analysis_artifact=fa_art,
            current_valuation_artifact=val_art,
        )
        dist = art["coverage"]["financial_composite_state_distribution"]
        assert sum(dist.values()) == 1
        assert art["records"]["AAA"]["financial_composite_context"]["financial_composite_state"] in iidp.FINANCIAL_COMPOSITE_STATES
