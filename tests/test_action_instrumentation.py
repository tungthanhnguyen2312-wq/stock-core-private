from __future__ import annotations

import unittest

from action_instrumentation import build_artifact


def _shadow(*, posture="INITIATE_CANDIDATE", gate="CONDITIONAL_SHADOW", fundamental=None):
    return {"shadow_posture": posture, "action_readiness_gate": gate, "research_case_readiness": "RESEARCH_CASE_READY_WITH_PARTIAL_INVALIDATION",
            "technical_invalidation": {"status": "CONDITIONAL"},
            "fundamental_invalidation": fundamental or {"status": "CONDITIONAL", "trigger_type": "COMPATIBLE_PROFITABILITY_QUALITY_DETERIORATION", "source_rule": "axis/v1", "reason": "no baseline"},
            "market_confirmation_trigger": None, "warnings": []}


def _tactical(state="EARLY_REVERSAL_CANDIDATE", rule="R6_EARLY_REVERSAL_CANDIDATE"):
    return {"entry_state": state, "rule_id": rule, "signals": {"close": 10.0, "ma_20": 9.5, "momentum_20d": .1}}


def _descriptive(basis="ADJUSTED_RETROSPECTIVE"):
    return {"technical_features": {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": "2026-08-25", "price_basis": basis,
            "technical_history_provenance": {"source": "retained"}, "values": {"close": 10.0, "ma_20": 9.5, "momentum_20d": .1}}}


class ActionInstrumentationTest(unittest.TestCase):
    def _build(self, shadow, tactical=None, descriptive=None, fundamental_boundaries=None):
        return build_artifact(shadow={"denominator": 1, "artifact_identity": "shadow", "records": {"AAA": shadow}},
                              tactical={"artifact_identity": "tactical", "records": {"AAA": tactical or _tactical()}},
                              descriptive={"artifact_identity": "descriptive", "records": {"AAA": descriptive or _descriptive()}},
                              fundamental_boundaries_by_ticker=fundamental_boundaries)

    def test_exact_early_reversal_boundaries_preserve_posture_but_not_ready_without_fundamental(self):
        record = self._build(_shadow())["records"]["AAA"]
        self.assertEqual(record["shadow_posture"], "INITIATE_CANDIDATE")
        self.assertEqual(record["entry_or_confirmation_boundary"]["status"], "READY")
        self.assertEqual(record["technical_risk_boundary"]["status"], "READY")
        self.assertEqual(record["fundamental_thesis_boundary"]["status"], "CONDITIONAL")
        self.assertEqual(record["action_readiness_gate"], "CONDITIONAL_SHADOW")
        self.assertEqual(record["technical_risk_boundary"]["source_rule"], "R6_EARLY_REVERSAL_CANDIDATE")

    def test_price_basis_mismatch_blocks_exact_price_boundary(self):
        record = self._build(_shadow(), descriptive=_descriptive("UNKNOWN"))["records"]["AAA"]
        self.assertEqual(record["entry_or_confirmation_boundary"]["status"], "CONDITIONAL")
        self.assertIn("EXACT_MA20_INPUT_OR_COMPATIBLE_PRICE_BASIS_UNAVAILABLE", record["entry_or_confirmation_boundary"]["warnings"])

    def test_wait_with_exact_confirmation_remains_conditional(self):
        record = self._build(_shadow(posture="WAIT_FOR_CONFIRMATION_CANDIDATE"))["records"]["AAA"]
        self.assertEqual(record["entry_or_confirmation_boundary"]["status"], "READY")
        self.assertEqual(record["action_readiness_gate"], "CONDITIONAL_SHADOW")

    def test_avoid_uses_reversal_not_bullish_stop(self):
        record = self._build(_shadow(posture="AVOID_CANDIDATE"), tactical=_tactical("DOWNTREND", "R9_DOWNTREND_DEFAULT"))["records"]["AAA"]
        self.assertEqual(record["posture_reversal_boundary"]["status"], "READY")
        self.assertEqual(record["posture_reversal_boundary"]["direction"], "ABOVE_TO_REVERSE_NEGATIVE")
        self.assertEqual(record["entry_or_confirmation_boundary"]["status"], "UNAVAILABLE")

    def test_margin_boundary_is_relative_and_requires_existing_ready_contract(self):
        fundamental = {"status": "READY", "trigger_type": "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT", "threshold": .2, "baseline": .25,
                       "period_basis": "TTM", "method": "margin/v1", "evidence_tier": "OPERATIONAL_PROXY", "scope": "consolidated"}
        record = self._build(_shadow(fundamental=fundamental))["records"]["AAA"]
        boundary = record["fundamental_thesis_boundary"]
        self.assertEqual(boundary["status"], "READY")
        self.assertEqual(boundary["value"], .2)
        self.assertEqual(boundary["baseline_value"] * .80, boundary["value"])

    def test_exact_existing_fundamental_boundary_unlocks_only_full_existing_contract(self):
        precise = {"AAA": {"fundamental_boundary": {"status": "READY", "boundary_type": "FUNDAMENTAL_QUALITY_QUALIFICATION_LOST",
                  "rule_identity": "SUPER_SETUP_PERCENTILE_FLOOR/v1", "current_trigger_state": "NOT_TRIGGERED", "warnings": []}}}
        record = self._build(_shadow(), fundamental_boundaries=precise)["records"]["AAA"]
        self.assertEqual(record["fundamental_thesis_boundary"]["status"], "READY")
        self.assertEqual(record["action_readiness_gate"], "READY_SHADOW")
        self.assertEqual(self._build(_shadow(), fundamental_boundaries=precise)["coverage"]["COMPLETE_TECHNICAL_PLUS_FUNDAMENTAL_INSTRUMENTATION"], 1)
        wait = self._build(_shadow(posture="WAIT_FOR_CONFIRMATION_CANDIDATE"), fundamental_boundaries=precise)["records"]["AAA"]
        self.assertEqual(wait["action_readiness_gate"], "CONDITIONAL_SHADOW")

    def test_identity_and_no_target_sizing_or_score(self):
        first, second = self._build(_shadow()), self._build(_shadow())
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["residual"], 0)
        self.assertNotIn("action_score", str(first))
        for forbidden in ("target_price", "expected_return", "probability", "position_size", "portfolio_weight", "leverage"):
            self.assertNotIn(forbidden, str(first))
