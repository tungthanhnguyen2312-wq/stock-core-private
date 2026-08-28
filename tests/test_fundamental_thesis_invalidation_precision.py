from __future__ import annotations

import unittest

from fundamental_thesis_invalidation_precision import QUALITY_COHORT, build_artifact


def _source(*, posture="INITIATE_CANDIDATE", archetype="QUALITY_BREAKOUT_THESIS", percentile=.9,
            disposition="OPPORTUNITY_CASE_ELIGIBLE", prior=None):
    return {
        "terminal_case_disposition": disposition, "shadow_posture": posture, "thesis_archetype": archetype,
        "action_readiness_gate": "CONDITIONAL_SHADOW", "technical_invalidation": {"status": "CONDITIONAL", "source_rule": "R1"},
        "fundamental_quality_context": {
            "comparable_cohort_percentile": percentile, "ranking_basis": QUALITY_COHORT,
            "quality_method": "AVAILABLE_FUNDAMENTAL_AXIS_MEAN/v1", "cohort_size": 449,
            "as_of": "2026-08-25", "period_basis": "CURRENT_CROSS_SECTIONAL_RESEARCH",
            "statement_scope": "CORPORATE_VALID_COMPARABLE_COHORT", "evidence_tier": "OPERATIONAL_PROXY",
        },
        "fundamental_invalidation": prior or {"status": "CONDITIONAL", "source_rule": "axis/v1", "trigger_type": "AXIS", "reason": "no state"},
    }


class FundamentalThesisInvalidationPrecisionTest(unittest.TestCase):
    def _build(self, records):
        return build_artifact(shadow={"denominator": len(records), "artifact_identity": "shadow", "records": records})

    def test_existing_initiate_threshold_is_reused_with_corporate_cohort_lineage(self):
        boundary = self._build({"AAA": _source()})["records"]["AAA"]["fundamental_boundary"]
        self.assertEqual(boundary["status"], "READY")
        self.assertEqual(boundary["threshold"], .80)
        self.assertEqual(boundary["rule_identity"], "SUPER_SETUP_PERCENTILE_FLOOR/v1")
        self.assertEqual(boundary["cohort_definition"], QUALITY_COHORT)
        self.assertNotIn("sector", boundary["cohort_definition"].lower())
        self.assertIn("AVAILABLE_FUNDAMENTAL_AXIS_MEAN/v1", boundary["future_evaluation_contract"])
        self.assertEqual(boundary["current_trigger_state"], "NOT_TRIGGERED")

    def test_accumulate_wait_and_avoid_use_only_existing_thresholds(self):
        result = self._build({
            "ACC": _source(posture="ACCUMULATE_CANDIDATE", archetype="QUALITY_MOMENTUM_THESIS", percentile=.8),
            "WAIT": _source(posture="WAIT_FOR_CONFIRMATION_CANDIDATE", archetype="HIGH_QUALITY_WAIT_THESIS", percentile=.8),
            "AVD": _source(posture="AVOID_CANDIDATE", archetype="NO_BULLISH_ARCHETYPE", percentile=.2),
        })["records"]
        self.assertEqual(result["ACC"]["fundamental_boundary"]["threshold"], .75)
        self.assertEqual(result["WAIT"]["fundamental_boundary"]["status"], "READY")
        self.assertEqual(result["WAIT"]["shadow_posture"], "WAIT_FOR_CONFIRMATION_CANDIDATE")
        avoid = result["AVD"]["fundamental_boundary"]
        self.assertEqual(avoid["status"], "READY")
        self.assertEqual(avoid["boundary_type"], "FUNDAMENTAL_POSTURE_REVERSAL_BOUNDARY")
        self.assertEqual(avoid["direction"], "ABOVE_TO_REVERSE_NEGATIVE")
        self.assertEqual(avoid["threshold"], .25)

    def test_high_risk_is_risk_state_not_fabricated_positive_thesis(self):
        boundary = self._build({"AAA": _source(posture="HIGH_RISK_SPECULATION_CANDIDATE", archetype="HIGH_RISK_SPECULATION_THESIS", percentile=.2)})["records"]["AAA"]["fundamental_boundary"]
        self.assertEqual(boundary["status"], "CONDITIONAL")
        self.assertEqual(boundary["boundary_type"], "FUNDAMENTAL_RISK_STATE")
        self.assertIn("RESEARCH_WARNING", boundary["warnings"][0])

    def test_missing_lineage_is_conditional_not_zero_or_ready(self):
        source = _source()
        source["fundamental_quality_context"]["ranking_basis"] = None
        source["fundamental_quality_context"]["comparable_cohort_percentile"] = None
        boundary = self._build({"AAA": source})["records"]["AAA"]["fundamental_boundary"]
        self.assertEqual(boundary["status"], "CONDITIONAL")
        self.assertIsNone(boundary["baseline_value"])
        self.assertEqual(boundary["current_trigger_state"], "UNKNOWN")

    def test_margin_contract_is_preserved_only_when_existing_case_is_ready(self):
        margin = {"status": "READY", "trigger_type": "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT", "threshold": .2,
                  "baseline": .25, "period_basis": "TTM", "scope": "CONSOLIDATED", "method": "margin/v1",
                  "evidence_tier": "OPERATIONAL_PROXY"}
        source = _source(posture="WAIT_FOR_CONFIRMATION_CANDIDATE", archetype="NO_BULLISH_ARCHETYPE", prior=margin)
        boundary = self._build({"AAA": source})["records"]["AAA"]["fundamental_boundary"]
        self.assertEqual(boundary["status"], "READY")
        self.assertEqual(boundary["threshold"], .2)
        self.assertEqual(boundary["baseline_value"] * .80, boundary["threshold"])
        self.assertEqual(boundary["statement_scope"], "CONSOLIDATED")

    def test_non_eligible_is_unavailable_and_artifact_is_complete_deterministic_and_non_authoritative(self):
        records = {"AAA": _source(), "BBB": _source(disposition="MARKET_ONLY_RESEARCH_CASE", percentile=None)}
        first, second = self._build(records), self._build(records)
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["denominator"], 2)
        self.assertEqual(first["residual"], 0)
        self.assertEqual(first["records"]["BBB"]["fundamental_boundary"]["status"], "UNAVAILABLE")
        text = str(first)
        for forbidden in ("target_price", "expected_return", "probability", "position_size", "portfolio_weight", "leverage", "debt_from_equity_multiplier"):
            self.assertNotIn(forbidden, text)
