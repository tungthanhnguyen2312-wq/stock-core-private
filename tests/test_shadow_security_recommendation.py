from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from export_ai_bundle import attach_shadow_security_recommendation, load_shadow_security_recommendation_artifact
from shadow_security_recommendation import LABELS, build_artifact, content_identity


ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "research_cases": "operations-review/thesis-catalyst-downside-and-dual-invalidation-v1-20260828/artifact.json",
    "shadow_readiness": "operations-review/shadow-action-readiness-v1-20260828/artifact.json",
    "action_instrumentation": "operations-review/action-instrumentation-and-invalidation-precision-v1-20260828/artifact.json",
    "fundamental_invalidation": "operations-review/fundamental-thesis-invalidation-precision-v1-20260828/artifact.json",
    "risk_research": "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json",
    "valuation_research": "operations-review/current-valuation-research-proxy-and-relative-value-axis-v1-20260828/artifact.json",
    "a1_temporal": "operations-review/a1-bitemporal-semantic-contract-v1-20260828/artifact.json",
    "a2_temporal": "operations-review/a2-provider-publication-first-seen-retention-v1-20260829/artifact.json",
}


def source_inputs():
    return {key: json.loads((ROOT / path).read_text(encoding="utf-8")) for key, path in PATHS.items()}


class ShadowSecurityRecommendationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = build_artifact(**source_inputs())

    def test_full_denominator_and_exact_vocabulary(self):
        self.assertEqual(tuple(self.artifact["metadata"]["recommendation_vocabulary"]), LABELS)
        self.assertEqual((self.artifact["denominator"], self.artifact["residual"]), (523, 0))
        self.assertEqual(self.artifact["validation"]["recommendation_counts"], {
            "ACCUMULATE_RESEARCH_CANDIDATE": 30, "AVOID_NEW_ENTRY": 70,
            "HIGH_RISK_SPECULATION_ONLY": 17, "INITIATE_RESEARCH_CANDIDATE": 13,
            "INSUFFICIENT_EVIDENCE": 77, "WAIT_FOR_CONFIRMATION": 316,
        })
        self.assertEqual(self.artifact["validation"]["readiness_counts"], {
            "RECOMMENDATION_CONDITIONAL": 406, "RECOMMENDATION_NOT_READY": 77, "RECOMMENDATION_READY": 40,
        })

    def test_label_and_readiness_remain_independent(self):
        records = self.artifact["records"]
        conditional_accumulate = [record for record in records.values() if record["recommendation"]["recommendation_label"] == "ACCUMULATE_RESEARCH_CANDIDATE" and record["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_CONDITIONAL"]
        self.assertEqual(len(conditional_accumulate), 3)
        self.assertTrue(all(record["recommendation"]["recommendation_label"] == "WAIT_FOR_CONFIRMATION" for record in records.values() if record["recommendation"]["shadow_posture"] == "WAIT_FOR_CONFIRMATION_CANDIDATE"))
        self.assertTrue(all(record["recommendation"]["recommendation_label"] == "INSUFFICIENT_EVIDENCE" for record in records.values() if record["recommendation"]["recommendation_readiness"] == "RECOMMENDATION_NOT_READY"))

    def test_risk_is_optional_and_never_reclassifies(self):
        absent = build_artifact(**{key: value for key, value in source_inputs().items() if key != "risk_research"})
        for ticker, record in self.artifact["records"].items():
            self.assertEqual(record["recommendation"]["recommendation_label"], absent["records"][ticker]["recommendation"]["recommendation_label"])
        self.assertEqual(self.artifact["validation"]["risk_context_available"], 40)
        self.assertEqual(sum(record["risk_context"]["status"] == "ABSENT" for record in absent["records"].values()), 523)

    def test_trigger_conflict_fails_positive_packet_closed(self):
        inputs = source_inputs()
        inputs["fundamental_invalidation"] = copy.deepcopy(inputs["fundamental_invalidation"])
        inputs["fundamental_invalidation"]["records"]["BFC"]["fundamental_boundary"]["current_trigger_state"] = "TRIGGERED"
        artifact = build_artifact(**inputs)
        record = artifact["records"]["BFC"]
        self.assertEqual(record["integrity_status"], "RECOMMENDATION_POSTURE_TRIGGER_CONFLICT")
        self.assertEqual(record["recommendation"]["recommendation_label"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(record["recommendation"]["recommendation_readiness"], "RECOMMENDATION_NOT_READY")

    def test_avoid_high_risk_and_authority_boundaries(self):
        records = self.artifact["records"].values()
        self.assertEqual(sum(record["recommendation"]["recommendation_label"] == "AVOID_NEW_ENTRY" for record in records), 70)
        self.assertEqual(sum(record["recommendation"]["recommendation_label"] == "HIGH_RISK_SPECULATION_ONLY" for record in self.artifact["records"].values()), 17)
        high = next(record for record in self.artifact["records"].values() if record["recommendation"]["recommendation_label"] == "HIGH_RISK_SPECULATION_ONLY")
        self.assertIn("HIGH_RISK_SPECULATION_IS_A_RESEARCH_WARNING_NOT_A_POSITIVE_FUNDAMENTAL_THESIS", high["fundamental_invalidation"]["warnings"])
        self.assertFalse(high["authority_boundaries"]["position_sizing_authority"])
        self.assertEqual(high["temporal_context"]["close_price_execution_eligibility"], "NOT_ESTABLISHED")

    def test_determinism_and_opt_in_bundle_attachment(self):
        self.assertEqual(content_identity(self.artifact)["artifact_sha256"], self.artifact["artifact_sha256"])
        path = ROOT / "operations-review/shadow-security-recommendation-v1-20260829/artifact.json"
        loaded = load_shadow_security_recommendation_artifact(path)
        self.assertIsNotNone(loaded)
        entries = {"BFC": {"existing": True}, "MISSING": {"existing": True}}
        attached = attach_shadow_security_recommendation(entries, True, str(path))
        self.assertIn("shadow_security_recommendation", attached["BFC"])
        self.assertNotIn("shadow_security_recommendation", attached["MISSING"])
