"""Focused, fixture-only tests for next_session_decision_brief/v2's additive posture_transition
section -- no real retained evidence required (unlike tests/test_next_session_decision_brief.py's
real-replay class, which stays skipped outside the primary checkout)."""
from __future__ import annotations

import json

import next_session_decision_brief as nsdb


def _rec(posture: str, phase: str = "TREND_CONTINUATION") -> dict:
    return {"research_action_posture": posture, "tactical_phase": phase, "decision_identity": f"decision:X:{posture}:{phase}"}


class TestClassifyPostureTransition:
    def test_no_longer_available(self):
        assert nsdb._classify_posture_transition(_rec("HOLD"), None) == "NO_LONGER_AVAILABLE"

    def test_newly_available(self):
        assert nsdb._classify_posture_transition(None, _rec("EARLY_WATCH")) == "NEWLY_AVAILABLE"

    def test_posture_unchanged(self):
        assert nsdb._classify_posture_transition(_rec("HOLD"), _rec("HOLD")) == "POSTURE_UNCHANGED"

    def test_wait_to_initiate(self):
        assert nsdb._classify_posture_transition(_rec("WAIT_FOR_CONFIRMATION"), _rec("INITIATE_ON_BREAKOUT")) == "WAIT_TO_INITIATE"

    def test_early_watch_to_initiate(self):
        assert nsdb._classify_posture_transition(_rec("EARLY_WATCH"), _rec("INITIATE_ON_BREAKOUT")) == "EARLY_WATCH_TO_INITIATE"

    def test_generic_new_breakout_from_uncovered_origin(self):
        assert nsdb._classify_posture_transition(_rec("ACCUMULATE_ON_RETEST"), _rec("INITIATE_ON_BREAKOUT")) == "NEW_BREAKOUT"

    def test_new_early_watch(self):
        assert nsdb._classify_posture_transition(_rec("WAIT_FOR_CONFIRMATION"), _rec("EARLY_WATCH")) == "NEW_EARLY_WATCH"

    def test_new_retest_candidate(self):
        assert nsdb._classify_posture_transition(_rec("EARLY_WATCH"), _rec("ACCUMULATE_ON_RETEST")) == "NEW_RETEST_CANDIDATE"

    def test_initiate_to_hold(self):
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD")) == "INITIATE_TO_HOLD"

    def test_initiate_to_extended(self):
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD_DO_NOT_ADD")) == "INITIATE_TO_EXTENDED"

    def test_breakout_failed(self):
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("WAIT_FOR_CONFIRMATION")) == "BREAKOUT_FAILED"
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("AVOID")) == "BREAKOUT_FAILED"

    def test_avoid_to_recovery_watch(self):
        assert nsdb._classify_posture_transition(_rec("AVOID"), _rec("EARLY_WATCH")) == "AVOID_TO_RECOVERY_WATCH"

    def test_uptrend_to_breakdown_checked_before_posture_pair_rules(self):
        prev = _rec("HOLD", phase="TREND_CONTINUATION")
        curr = _rec("AVOID", phase="BREAKDOWN")
        assert nsdb._classify_posture_transition(prev, curr) == "UPTREND_TO_BREAKDOWN"

    def test_posture_changed_other_fallback(self):
        assert nsdb._classify_posture_transition(_rec("HOLD"), _rec("HOLD_DO_NOT_ADD")) == "POSTURE_CHANGED_OTHER"

    def test_every_label_is_in_the_documented_vocabulary(self):
        pairs = [
            (None, _rec("HOLD")), (_rec("HOLD"), None), (_rec("HOLD"), _rec("HOLD")),
            (_rec("WAIT_FOR_CONFIRMATION"), _rec("INITIATE_ON_BREAKOUT")), (_rec("EARLY_WATCH"), _rec("INITIATE_ON_BREAKOUT")),
            (_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD")), (_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD_DO_NOT_ADD")),
            (_rec("INITIATE_ON_BREAKOUT"), _rec("REDUCE")), (_rec("AVOID"), _rec("WAIT_FOR_CONFIRMATION")),
            (_rec("HOLD"), _rec("REDUCE")),
        ]
        for prev, curr in pairs:
            assert nsdb._classify_posture_transition(prev, curr) in nsdb.POSTURE_TRANSITION_LABELS


class TestResolveIntegratedDecisionArtifact:
    def test_returns_none_when_session_absent(self, tmp_path):
        assert nsdb._resolve_integrated_decision_artifact(tmp_path, None) is None

    def test_returns_none_when_file_missing(self, tmp_path):
        assert nsdb._resolve_integrated_decision_artifact(tmp_path, "2026-08-28") is None

    def test_fails_closed_on_session_mismatch(self, tmp_path):
        import daily_session_level2_package as level2
        path = level2.session_artifact_paths(tmp_path, "2026-08-28")["integrated_investment_decision_product"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"session": "2026-08-27", "records": {}}), encoding="utf-8")
        try:
            nsdb._resolve_integrated_decision_artifact(tmp_path, "2026-08-28")
            assert False, "expected NextSessionDecisionBriefError"
        except nsdb.NextSessionDecisionBriefError as exc:
            assert "INTEGRATED_DECISION_ARTIFACT_SESSION_MISMATCH" in str(exc)

    def test_loads_matching_session_artifact(self, tmp_path):
        import daily_session_level2_package as level2
        path = level2.session_artifact_paths(tmp_path, "2026-08-28")["integrated_investment_decision_product"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"session": "2026-08-28", "records": {"HPG": {}}}), encoding="utf-8")
        loaded = nsdb._resolve_integrated_decision_artifact(tmp_path, "2026-08-28")
        assert loaded["records"] == {"HPG": {}}


class TestPostureTransitionSection:
    def test_no_current_artifact_is_unavailable(self, tmp_path):
        section = nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session="2026-08-27")
        assert section["availability"] == "UNAVAILABLE"
        assert "CURRENT_INTEGRATED_DECISION_ARTIFACT_NOT_MATERIALIZED" in section["reason_codes"]

    def test_full_pair_produces_records_and_counts(self, tmp_path):
        import daily_session_level2_package as level2
        prev_path = level2.session_artifact_paths(tmp_path, "2026-08-27")["integrated_investment_decision_product"]
        curr_path = level2.session_artifact_paths(tmp_path, "2026-08-28")["integrated_investment_decision_product"]
        prev_path.parent.mkdir(parents=True, exist_ok=True)
        curr_path.parent.mkdir(parents=True, exist_ok=True)
        prev_path.write_text(json.dumps({"session": "2026-08-27", "artifact_identity": "prev:x", "records": {"HPG": _rec("EARLY_WATCH")}}), encoding="utf-8")
        curr_path.write_text(json.dumps({"session": "2026-08-28", "artifact_identity": "curr:x", "records": {"HPG": _rec("INITIATE_ON_BREAKOUT")}}), encoding="utf-8")
        section = nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session="2026-08-27")
        assert section["availability"] == "AVAILABLE"
        assert section["records"]["HPG"]["transition"] == "EARLY_WATCH_TO_INITIATE"
        assert section["transition_counts"] == {"EARLY_WATCH_TO_INITIATE": 1}
