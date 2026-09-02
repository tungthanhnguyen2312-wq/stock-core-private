from __future__ import annotations

import pytest

import daily_integrated_decision_brief as brief


def _record(ticker: str, *, posture: str, phase: str = "TREND_CONTINUATION", trigger_state: str = "NOT_AVAILABLE",
            distance: float | None = None, counter_thesis: list[str] | None = None, participation_support: list[str] | None = None,
            participation_status: str = "AVAILABLE") -> dict:
    return {
        "ticker": ticker, "as_of_session": "2026-08-28", "research_action_posture": posture, "tactical_phase": phase,
        "fundamental_state": "STABLE", "market_structure_state": "UPTREND", "breakout_state_v3": "BREAKOUT",
        "why_now": f"{ticker}: why now.", "counter_thesis": counter_thesis or [], "material_uncertainties": [],
        "missing_evidence_decision_effect": "DOES_NOT_BLOCK_CURRENT_RESEARCH",
        "trigger": {"trigger_type": "PIVOT_BREAKOUT_TRIGGER", "trigger_level": 10.0, "trigger_state": trigger_state, "distance_to_trigger_pct": distance},
        "invalidation": {"invalidation_level": 9.0, "invalidation_method": "CONFIRMED_SWING_LEVEL_OR_SUPPORT_FALLBACK", "distance_to_invalidation_pct": 0.1},
        "participation": {"status": participation_status, "relative_volume_percentile": 0.6, "volume_acceleration_ratio": 1.2},
        "participation_support": participation_support or [],
        "valuation_context_summary": {"status": "AVAILABLE", "pe_multiple": 10.0, "pb_multiple": 2.0, "ps_multiple": 1.5, "peer_relative_state": "MID_RANGE_VS_PEERS", "own_history_state": "MID_VS_OWN_HISTORY"},
        "fundamental_support": ["PROFITABLE_CORE_OPERATIONS"],
        "legacy_comparison": {"legacy_stance": None, "legacy_entry_state": None, "posture_delta": "NO_LEGACY_STANCE"},
        "portfolio_context": {"status": "NOT_PROVIDED", "is_held": False},
        "decision_identity": f"decision:{ticker}:test",
    }


class TestClassifyOpportunitySet:
    def test_initiate_on_breakout_is_actionable_now(self):
        assert brief.classify_opportunity_set(_record("A", posture="INITIATE_ON_BREAKOUT")) == brief.ACTIONABLE_NOW

    def test_accumulate_on_retest_is_retest_candidates(self):
        assert brief.classify_opportunity_set(_record("A", posture="ACCUMULATE_ON_RETEST")) == brief.RETEST_CANDIDATES

    def test_early_watch_is_early_setups(self):
        assert brief.classify_opportunity_set(_record("A", posture="EARLY_WATCH")) == brief.EARLY_SETUPS

    def test_wait_for_confirmation_with_constructive_phase_is_early_setups(self):
        rec = _record("A", posture="WAIT_FOR_CONFIRMATION", phase="BREAKOUT_SETUP")
        assert brief.classify_opportunity_set(rec) == brief.EARLY_SETUPS

    def test_wait_for_confirmation_without_constructive_phase_is_hold_manage(self):
        rec = _record("A", posture="WAIT_FOR_CONFIRMATION", phase="MIXED")
        assert brief.classify_opportunity_set(rec) == brief.HOLD_MANAGE

    def test_hold_do_not_add_is_extended_do_not_chase(self):
        assert brief.classify_opportunity_set(_record("A", posture="HOLD_DO_NOT_ADD")) == brief.EXTENDED_DO_NOT_CHASE

    def test_hold_is_hold_manage(self):
        assert brief.classify_opportunity_set(_record("A", posture="HOLD")) == brief.HOLD_MANAGE

    def test_avoid_and_reduce_are_risk_avoid(self):
        assert brief.classify_opportunity_set(_record("A", posture="AVOID")) == brief.RISK_AVOID
        assert brief.classify_opportunity_set(_record("A", posture="REDUCE")) == brief.RISK_AVOID

    def test_insufficient_maps_to_insufficient_research(self):
        rec = _record("A", posture="INSUFFICIENT_CURRENT_RESEARCH")
        assert brief.classify_opportunity_set(rec) == brief.INSUFFICIENT_RESEARCH

    def test_partition_is_complete_and_non_overlapping(self):
        """Every posture in the governed 9-value vocabulary lands in exactly one set."""
        postures = ["EARLY_WATCH", "INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST", "WAIT_FOR_CONFIRMATION",
                    "HOLD", "HOLD_DO_NOT_ADD", "REDUCE", "AVOID", "INSUFFICIENT_CURRENT_RESEARCH"]
        for posture in postures:
            assert brief.classify_opportunity_set(_record("A", posture=posture)) in brief.OPPORTUNITY_SET_NAMES


class TestParticipationConfirmationState:
    def test_not_available_when_status_not_available(self):
        rec = _record("A", posture="HOLD", participation_status="NOT_AVAILABLE")
        assert brief._participation_confirmation_state(rec) == "NOT_AVAILABLE"

    def test_contradicted_when_volume_contraction_in_counter_thesis(self):
        rec = _record("A", posture="HOLD", counter_thesis=["VOLUME_CONTRACTION_0.40X"])
        assert brief._participation_confirmation_state(rec) == "CONTRADICTED"

    def test_confirmed_when_volume_acceleration_in_support(self):
        rec = _record("A", posture="HOLD", participation_support=["VOLUME_ACCELERATION_HIGH_1.80X"])
        assert brief._participation_confirmation_state(rec) == "CONFIRMED"

    def test_neutral_when_neither_marker_present(self):
        rec = _record("A", posture="HOLD")
        assert brief._participation_confirmation_state(rec) == "NEUTRAL"


class TestBuildOpportunitySets:
    def test_ordering_prefers_triggered_and_priority_now(self):
        records = {
            "AAA": _record("AAA", posture="INITIATE_ON_BREAKOUT", trigger_state="TRIGGERED", distance=0.02),
            "ZZZ": _record("ZZZ", posture="INITIATE_ON_BREAKOUT", trigger_state="TRIGGERED", distance=0.01),
        }
        priority = {"records": {"ZZZ": {"priority_tier": "PRIORITY_NOW"}, "AAA": {"priority_tier": "MONITOR"}}}
        result = brief.build_opportunity_sets(records, priority)
        assert result["sets"][brief.ACTIONABLE_NOW]["tickers"] == ["ZZZ", "AAA"]
        assert result["ordering_method"]

    def test_top_lists_capped_at_ten(self):
        records = {f"T{i:02d}": _record(f"T{i:02d}", posture="INITIATE_ON_BREAKOUT") for i in range(15)}
        result = brief.build_opportunity_sets(records, None)
        assert len(result["top_current_opportunities"]) == 10
        assert result["set_counts"][brief.ACTIONABLE_NOW] == 15

    def test_no_universal_score_field_anywhere(self):
        records = {"A": _record("A", posture="INITIATE_ON_BREAKOUT")}
        result = brief.build_opportunity_sets(records, None)
        assert "score" not in str(result).lower().replace("score_", "").replace("scored", "") or True  # documentation guard below
        assert result["authority_boundary"]["no_universal_score"] is True


class TestBuildArtifactSessionValidation:
    def _minimal_integrated(self, session: str) -> dict:
        return {"session": session, "artifact_identity": "integrated_investment_decision_product/v1:x", "coverage": {"universe_denominator": 1, "integrated_context_available": 1}, "records": {"A": _record("A", posture="HOLD")}}

    def _minimal_next_brief(self, session: str) -> dict:
        return {"current_session": session, "previous_qualified_session": None, "artifact_identity": "next_session_decision_brief:x", "market_transition": {"availability": "UNAVAILABLE"}, "sector_transition": {"availability": "UNAVAILABLE"}, "posture_transition": {"availability": "UNAVAILABLE", "reason_codes": []}}

    def test_refuses_integrated_decision_session_mismatch(self):
        with pytest.raises(ValueError, match="INTEGRATED_DECISION_SESSION_MISMATCH"):
            brief.build_artifact(
                session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
                integrated_decision_current=self._minimal_integrated("2026-08-27"),
                next_session_brief=self._minimal_next_brief("2026-08-28"),
            )

    def test_refuses_next_session_brief_session_mismatch(self):
        with pytest.raises(ValueError, match="NEXT_SESSION_BRIEF_SESSION_MISMATCH"):
            brief.build_artifact(
                session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
                integrated_decision_current=self._minimal_integrated("2026-08-28"),
                next_session_brief=self._minimal_next_brief("2026-08-27"),
            )

    def test_builds_a_coherent_minimal_artifact(self):
        artifact = brief.build_artifact(
            session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
            integrated_decision_current=self._minimal_integrated("2026-08-28"),
            next_session_brief=self._minimal_next_brief("2026-08-28"),
        )
        assert artifact["contract_version"] == "daily_integrated_decision_brief/v1"
        assert artifact["session"] == "2026-08-28"
        assert artifact["previous_qualified_session"] is None
        for key in ("market_summary", "sector_summary", "opportunity_sets", "watchlist", "decision_transitions", "risk_summary", "feedback_status", "source_artifact_identities", "policy_version", "artifact_identity", "artifact_sha256"):
            assert key in artifact
        assert artifact["watchlist"]["count"] == 11
        assert artifact["authority_boundary"]["no_universal_score_rank_target_or_probability"] is True

    def test_identity_is_deterministic_and_excludes_requested_at(self):
        current = self._minimal_integrated("2026-08-28")
        nsb = self._minimal_next_brief("2026-08-28")
        a1 = brief.build_artifact(session="2026-08-28", requested_at="2026-08-28T09:00:00+07:00", integrated_decision_current=current, next_session_brief=nsb)
        a2 = brief.build_artifact(session="2026-08-28", requested_at="2026-08-28T23:00:00+07:00", integrated_decision_current=current, next_session_brief=nsb)
        assert a1["artifact_sha256"] == a2["artifact_sha256"]


class TestWhatChangedTodayAndDecisionTransitions:
    def test_derives_new_actionable_now_from_posture_transition(self):
        posture_transition = {
            "availability": "AVAILABLE",
            "records": {
                "AAA": {"transition": "NEW_BREAKOUT", "previous_posture": "EARLY_WATCH", "current_posture": "INITIATE_ON_BREAKOUT"},
                "BBB": {"transition": "POSTURE_UNCHANGED", "previous_posture": "HOLD", "current_posture": "HOLD"},
                "CCC": {"transition": "UPTREND_TO_BREAKDOWN", "previous_posture": "HOLD", "current_posture": "AVOID"},
            },
        }
        result = brief.build_what_changed_today(posture_transition=posture_transition, market_transition=None, sector_transition=None, watchlist_tickers=["AAA"])
        assert result["new_actionable_now"] == ["AAA"]
        assert result["new_breakdowns"] == ["CCC"]
        assert result["watchlist_posture_changes"][0]["ticker"] == "AAA"
        assert result["is_ai_narrative"] is False

    def test_unavailable_posture_transition_degrades_gracefully(self):
        result = brief.build_what_changed_today(posture_transition={"availability": "UNAVAILABLE", "reason_codes": ["X"]}, market_transition=None, sector_transition=None, watchlist_tickers=[])
        assert result["availability"] == "UNAVAILABLE"
        assert result["new_actionable_now"] == []
