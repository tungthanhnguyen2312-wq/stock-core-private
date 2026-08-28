from __future__ import annotations

import unittest

from shadow_action_readiness import build_artifact


def _case(*, disposition="OPPORTUNITY_CASE_ELIGIBLE", state="BREAKOUT_READY", percentile=.9,
          technical="CONDITIONAL", fundamental="CONDITIONAL", archetype="QUALITY_BREAKOUT_THESIS", valuation=True):
    return {"terminal_disposition": disposition, "case_readiness": "RESEARCH_CASE_READY_WITH_PARTIAL_INVALIDATION",
            "as_of_session": "2026-08-25", "thesis_archetype": archetype,
            "thesis_evidence": [
                {"source_dimension": "FUNDAMENTAL_QUALITY", "value": percentile, "method": "CORPORATE_VALID_FUNDAMENTAL_QUALITY_COHORT_EMPIRICAL_PERCENTILE/v1", "evidence_tier": "OPERATIONAL_PROXY"},
                {"source_dimension": "CURRENT_MARKET_SETUP", "metric_or_state": "STRONG", "value": .1},
                {"source_dimension": "TACTICAL_SETUP", "metric_or_state": state, "value": "R1"},
            ],
            "technical_invalidation": {"status": technical, "source_rule": "R1" if technical == "CONDITIONAL" else None, "threshold": None},
            "fundamental_invalidation": {"status": fundamental, "source_rule": "axis/v1" if fundamental == "CONDITIONAL" else None, "threshold": None},
            "market_confirmation_trigger": {"trigger_type": "MARKET_CONFIRMATION_TRIGGER"}, "catalysts": [],
            "retained_event_context": [{"context_status": "RETAINED_EVENT_CONTEXT"}],
            "valuation_context": {"relative_value": {"status": "READY_RESEARCH_ONLY" if valuation else "INSUFFICIENT_INPUTS"}},
            "ttm_context": {"derived_metrics": {}}, "counter_thesis_evidence": [], "evidence_gaps": [], "warnings": []}


class ShadowActionReadinessTest(unittest.TestCase):
    def _build(self, cases, fundamental_boundaries=None, technical_boundaries=None):
        return build_artifact(research_cases={"denominator": len(cases), "artifact_identity": "cases", "records": cases},
                              fundamental_boundaries_by_ticker=fundamental_boundaries,
                              technical_boundaries_by_ticker=technical_boundaries)

    def test_initiate_and_conditional_readiness_are_separate(self):
        record = self._build({"AAA": _case()})["records"]["AAA"]
        self.assertEqual(record["shadow_posture"], "INITIATE_CANDIDATE")
        self.assertEqual(record["action_readiness_gate"], "CONDITIONAL_SHADOW")
        self.assertIn("CORPORATE_VALID_FUNDAMENTAL_QUALITY_COHORT", record["fundamental_quality_context"]["ranking_basis"])
        self.assertNotIn("sector", record["fundamental_quality_context"])

    def test_unavailable_each_invalidation_forces_not_ready_without_threshold(self):
        for key, kwargs in (("AAA", {"technical": "UNAVAILABLE"}), ("BBB", {"fundamental": "UNAVAILABLE"})):
            record = self._build({key: _case(**kwargs)})["records"][key]
            self.assertEqual(record["action_readiness_gate"], "NOT_READY_SHADOW")
            self.assertIsNone(record["technical_invalidation"]["threshold"])

    def test_optional_catalyst_valuation_and_ttm_do_not_force_wait(self):
        record = self._build({"AAA": _case(valuation=False)})["records"]["AAA"]
        self.assertEqual(record["shadow_posture"], "INITIATE_CANDIDATE")
        self.assertEqual(record["qualified_catalyst"], [])
        self.assertEqual(record["retained_event_context"][0]["context_status"], "RETAINED_EVENT_CONTEXT")

    def test_existing_gate_requires_both_precise_channels_without_posture_reclassification(self):
        fundamental = {"AAA": {"fundamental_boundary": {"status": "READY", "rule_identity": "SUPER_SETUP_PERCENTILE_FLOOR/v1"}}}
        technical = {"AAA": {"technical_risk_boundary": {"status": "READY", "source_rule": "R1"}}}
        record = self._build({"AAA": _case()}, fundamental, technical)["records"]["AAA"]
        self.assertEqual(record["shadow_posture"], "INITIATE_CANDIDATE")
        self.assertEqual(record["action_readiness_gate"], "READY_SHADOW")
        wait = self._build({"AAA": _case(state="BASE_BUILDING", percentile=.5)}, fundamental)["records"]["AAA"]
        self.assertEqual(wait["shadow_posture"], "WAIT_FOR_CONFIRMATION_CANDIDATE")
        self.assertEqual(wait["action_readiness_gate"], "CONDITIONAL_SHADOW")

    def test_high_risk_is_not_avoid_and_adverse_weak_is_avoid(self):
        high_risk = self._build({"AAA": _case(percentile=.2, archetype="HIGH_RISK_SPECULATION_THESIS")})["records"]["AAA"]
        self.assertEqual(high_risk["shadow_posture"], "HIGH_RISK_SPECULATION_CANDIDATE")
        avoid = self._build({"AAA": _case(state="DOWNTREND", percentile=.2, archetype="NO_BULLISH_ARCHETYPE")})["records"]["AAA"]
        self.assertEqual(avoid["shadow_posture"], "AVOID_CANDIDATE")

    def test_market_only_does_not_invent_fundamental_quality(self):
        record = self._build({"AAA": _case(disposition="MARKET_ONLY_RESEARCH_CASE", percentile=None)})["records"]["AAA"]
        self.assertEqual(record["shadow_posture"], "INSUFFICIENT_ACTION_EVIDENCE")
        self.assertIsNone(record["fundamental_quality_context"]["comparable_cohort_percentile"])
        self.assertEqual(record["action_readiness_gate"], "NOT_READY_SHADOW")

    def test_full_termination_identity_and_no_global_score(self):
        cases = {"AAA": _case(), "BBB": _case(disposition="INSUFFICIENT_CASE_EVIDENCE", percentile=None)}
        first, second = self._build(cases), self._build(cases)
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["denominator"], len(first["records"]))
        self.assertEqual(first["residual"], 0)
        self.assertNotIn("action_score", str(first))
        self.assertTrue(first["authority_boundary"]["no_global_composite"])
        forbidden = {"target_price", "expected_return", "probability", "position_size", "portfolio_weight", "leverage", "scenario_support"}
        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(item) for item in value.values())) if value else set()
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value)) if value else set()
            return set()
        self.assertFalse(forbidden & keys(first))
