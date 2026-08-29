from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from correlation_concentration_guard import (
    MATERIAL_CORRELATION_THRESHOLD,
    CorrelationConcentrationGuardError,
    build_artifact,
    content_identity,
)


ROOT = Path(__file__).resolve().parents[1]


def _risk(*, pairs=None, joint_status="JOINT_MATRIX_READY"):
    pairs = pairs if pairs is not None else [
        {"ticker_i": "AAA", "ticker_j": "BBB", "lookback_sessions": 20, "status": "PAIRWISE_CORRELATION_READY",
         "correlation": 0.81, "return_observations": 19, "warnings": []},
        {"ticker_i": "AAA", "ticker_j": "CCC", "lookback_sessions": 20, "status": "PAIRWISE_CORRELATION_READY",
         "correlation": 0.20, "return_observations": 19, "warnings": []},
        {"ticker_i": "BBB", "ticker_j": "CCC", "lookback_sessions": 20, "status": "PAIRWISE_CORRELATION_READY",
         "correlation": 0.81, "return_observations": 19, "warnings": []},
    ]
    return {
        "contract_version": "current_portfolio_risk_research/v1", "artifact_identity": "current_portfolio_risk_research:fixture",
        "artifact_sha256": "fixture", "metadata": {"as_of_session": "2026-08-25"},
        "ticker_risk_context": {ticker: {} for ticker in ("AAA", "BBB", "CCC")},
        "pairwise_relationships": pairs,
        "joint_matrix_context": {"L20": {"status": joint_status, "N": 3, "T": 19}},
    }


class CorrelationConcentrationGuardTest(unittest.TestCase):
    def test_pair_and_group_ordering_and_connected_component(self):
        artifact = build_artifact(risk_research=_risk(), securities=["CCC", "AAA", "BBB"], lookback=20)
        self.assertEqual([(row["ticker_i"], row["ticker_j"]) for row in artifact["pairwise_correlation_context"]],
                         [("AAA", "BBB"), ("AAA", "CCC"), ("BBB", "CCC")])
        self.assertEqual(artifact["guard_context"]["status"], "CONCENTRATED_CORRELATED_GROUP")
        self.assertEqual(artifact["concentration_groups"][0]["tickers"], ["AAA", "BBB", "CCC"])
        self.assertEqual(artifact["concentration_groups"][0]["group_id"], "CORRELATION_COMPONENT_001")

    def test_strict_threshold_boundary_below_and_above(self):
        for correlation, expected_edges in ((MATERIAL_CORRELATION_THRESHOLD, 0), (0.7999, 0), (0.8001, 1)):
            risk = _risk(pairs=[{"ticker_i": "AAA", "ticker_j": "BBB", "lookback_sessions": 20,
                                 "status": "PAIRWISE_CORRELATION_READY", "correlation": correlation,
                                 "return_observations": 19, "warnings": []}])
            artifact = build_artifact(risk_research=risk, securities=["BBB", "AAA"], lookback=20)
            self.assertEqual(artifact["validation"]["triggered_edge_count"], expected_edges)

    def test_symmetric_pair_is_normalized(self):
        risk = _risk(pairs=[{"ticker_i": "BBB", "ticker_j": "AAA", "lookback_sessions": 20,
                            "status": "PAIRWISE_CORRELATION_READY", "correlation": 0.81,
                            "return_observations": 19, "warnings": []}])
        artifact = build_artifact(risk_research=risk, securities=["AAA", "BBB"], lookback=20)
        self.assertEqual(artifact["pairwise_correlation_context"][0]["ticker_i"], "AAA")
        self.assertEqual(artifact["guard_context"]["status"], "CORRELATED_PAIR_CONTEXT")

    def test_conflicting_duplicate_pair_fails_closed(self):
        rows = [
            {"ticker_i": "AAA", "ticker_j": "BBB", "lookback_sessions": 20, "status": "PAIRWISE_CORRELATION_READY", "correlation": 0.81, "return_observations": 19},
            {"ticker_i": "BBB", "ticker_j": "AAA", "lookback_sessions": 20, "status": "PAIRWISE_CORRELATION_READY", "correlation": 0.60, "return_observations": 19},
        ]
        artifact = build_artifact(risk_research=_risk(pairs=rows), securities=["AAA", "BBB"], lookback=20)
        self.assertEqual(artifact["pairwise_correlation_context"][0]["status"], "PAIRWISE_EVIDENCE_CONFLICT")
        self.assertEqual(artifact["guard_context"]["status"], "INSUFFICIENT_PAIRWISE_EVIDENCE")

    def test_insufficient_pair_and_unknown_security_are_explicit(self):
        risk = _risk(pairs=[{"ticker_i": "AAA", "ticker_j": "BBB", "lookback_sessions": 20,
                            "status": "PAIRWISE_PARTIAL_OVERLAP", "correlation": None, "return_observations": None, "warnings": []}])
        artifact = build_artifact(risk_research=risk, securities=["AAA", "BBB", "ZZZ"], lookback=20)
        self.assertEqual(artifact["guard_context"]["status"], "INSUFFICIENT_PAIRWISE_EVIDENCE")
        self.assertIn("ZZZ", artifact["input_cohort"]["unknown_security_identifiers"])
        self.assertEqual(artifact["pairwise_correlation_context"][1]["status"], "UNKNOWN_SECURITY_IDENTITY")

    def test_missing_and_malformed_c1_pairwise_material_fail_closed(self):
        missing = build_artifact(risk_research=_risk(pairs=[]), securities=["AAA", "BBB"], lookback=20)
        self.assertEqual(missing["pairwise_correlation_context"][0]["status"], "C1_PAIRWISE_MATERIAL_MISSING")
        malformed = build_artifact(risk_research=_risk(pairs=[{
            "ticker_i": "AAA", "ticker_j": "BBB", "lookback_sessions": 20,
            "status": "PAIRWISE_CORRELATION_READY", "correlation": float("nan"), "return_observations": 19,
        }]), securities=["AAA", "BBB"], lookback=20)
        self.assertEqual(malformed["pairwise_correlation_context"][0]["status"], "PAIRWISE_INPUT_INVALID")

    def test_ready_pairwise_remains_usable_when_joint_matrix_is_blocked(self):
        artifact = build_artifact(risk_research=_risk(joint_status="JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N"),
                                  securities=["AAA", "BBB"], lookback=20)
        self.assertEqual(artifact["pairwise_correlation_context"][0]["status"], "PAIRWISE_CORRELATION_READY")
        self.assertIn("JOINT_MATRIX_UNAVAILABLE_PAIRWISE_CONTEXT_USABLE", artifact["guard_context"]["reason_codes"])

    def test_mixed_readiness_invalid_lookback_one_and_empty_edges(self):
        mixed = _risk(pairs=[
            {"ticker_i": "AAA", "ticker_j": "BBB", "lookback_sessions": 20, "status": "PAIRWISE_CORRELATION_READY", "correlation": 0.1, "return_observations": 19},
            {"ticker_i": "AAA", "ticker_j": "CCC", "lookback_sessions": 20, "status": "PAIRWISE_PARTIAL_OVERLAP", "correlation": None, "return_observations": None},
            {"ticker_i": "BBB", "ticker_j": "CCC", "lookback_sessions": 20, "status": "PAIRWISE_PARTIAL_OVERLAP", "correlation": None, "return_observations": None},
        ])
        self.assertEqual(build_artifact(risk_research=mixed, securities=["AAA", "BBB", "CCC"], lookback=20)["guard_context"]["status"], "PARTIAL_PAIRWISE_VIEW")
        with self.assertRaisesRegex(CorrelationConcentrationGuardError, "LOOKBACK_OUTSIDE"):
            build_artifact(risk_research=mixed, securities=["AAA", "BBB"], lookback=21)
        self.assertEqual(build_artifact(risk_research=mixed, securities=["AAA"], lookback=20)["guard_context"]["status"], "INPUT_COHORT_TOO_SMALL_FOR_CONCENTRATION_ANALYSIS")
        self.assertEqual(build_artifact(risk_research=mixed, securities=[], lookback=20)["validation"]["pair_count"], 0)

    def test_recommendations_are_passed_through_without_mutation_or_portfolio_outputs(self):
        recommendations = {"artifact_identity": "shadow", "records": {"AAA": {"recommendation": {"recommendation_label": "INITIATE_RESEARCH_CANDIDATE", "recommendation_readiness": "RECOMMENDATION_READY"}}}}
        before = copy.deepcopy(recommendations)
        artifact = build_artifact(risk_research=_risk(), securities=["AAA", "BBB"], lookback=20, shadow_recommendations=recommendations)
        self.assertEqual(recommendations, before)
        self.assertEqual(artifact["validation"]["recommendation_mutation_count"], 0)
        self.assertEqual(artifact["upstream_recommendation_context"]["AAA"]["recommendation_label"], "INITIATE_RESEARCH_CANDIDATE")
        self.assertEqual(artifact["authority_boundaries"]["portfolio_weights"], "NOT_EMITTED")
        self.assertEqual(artifact["validation"]["forbidden_output_audit"]["risk_budget"], 0)

    def test_deterministic_identity_and_real_c1_replay(self):
        risk = json.loads((ROOT / "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json").read_text(encoding="utf-8"))
        recommendations = json.loads((ROOT / "operations-review/shadow-security-recommendation-v1-20260829/artifact.json").read_text(encoding="utf-8"))
        first = build_artifact(risk_research=risk, securities=risk["cohort_summary"]["tickers"], lookback=20, shadow_recommendations=recommendations)
        second = build_artifact(risk_research=risk, securities=risk["cohort_summary"]["tickers"], lookback=20, shadow_recommendations=recommendations)
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(content_identity(first)["artifact_sha256"], first["artifact_sha256"])
        self.assertEqual(first["guard_context"]["joint_matrix_status"], "JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N")
        self.assertEqual(first["validation"]["triggered_edge_count"], 1)
        self.assertEqual(first["concentration_groups"][0]["tickers"], ["BSR", "GAS"])
        self.assertEqual(first["validation"]["recommendation_mutation_count"], 0)

    def test_real_mixed_l60_readiness_is_explicit(self):
        risk = json.loads((ROOT / "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json").read_text(encoding="utf-8"))
        artifact = build_artifact(risk_research=risk, securities=risk["cohort_summary"]["tickers"], lookback=60)
        self.assertEqual(artifact["guard_context"]["status"], "PARTIAL_PAIRWISE_VIEW")
        self.assertGreater(artifact["validation"]["pairwise_ready_count"], 0)
        self.assertGreater(artifact["validation"]["pairwise_insufficient_or_unavailable_count"], 0)


if __name__ == "__main__":
    unittest.main()
