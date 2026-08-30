"""tests/test_replay_fundamental_cohort_scaleout_downstream_v1.py -- synthetic-fixture unit
tests for the pure helper functions in the MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1
downstream-replay tool. The real end-to-end chain (daily_session_shadow_recommendation ->
current_daily_decision_research_product -> multi_session_thesis_recommendation_lifecycle) is
already covered by its own existing test suites, which this milestone does not modify; these
tests instead prove the comparison/report logic this milestone adds is correct and
deterministic, without requiring the large local retained-evidence stores."""
from __future__ import annotations

import unittest

from tools.replay_fundamental_cohort_scaleout_downstream_v1 import (
    build_comparison_report,
    _bundle_retention_coverage,
)


def _card(status: str, reason: str | None = None) -> dict:
    return {"recommendation_retention": {"status": status, "reason": reason}}


class BundleRetentionCoverageTest(unittest.TestCase):
    def test_counts_reconcile_and_reasons_grouped(self):
        cards = {
            "A": _card("RETAINED"),
            "B": _card("RETAINED"),
            "C": _card("UNAVAILABLE", "TICKER_NOT_IN_UPSTREAM_SHADOW_SECURITY_RECOMMENDATION"),
            "D": _card("UNAVAILABLE", "TICKER_NOT_IN_UPSTREAM_SHADOW_SECURITY_RECOMMENDATION"),
        }
        coverage = _bundle_retention_coverage(cards, "recommendation_retention")
        self.assertEqual(coverage["denominator"], 4)
        self.assertEqual(coverage["retained"], 2)
        self.assertEqual(coverage["unavailable"], 2)
        self.assertEqual(coverage["reason_code_distribution"], {"TICKER_NOT_IN_UPSTREAM_SHADOW_SECURITY_RECOMMENDATION": 2})

    def test_full_retention_has_empty_reason_distribution(self):
        cards = {"A": _card("RETAINED"), "B": _card("RETAINED")}
        coverage = _bundle_retention_coverage(cards, "recommendation_retention")
        self.assertEqual(coverage, {"denominator": 2, "retained": 2, "unavailable": 0, "reason_code_distribution": {}})


class ComparisonReportTest(unittest.TestCase):
    """Synthetic before/after variant results, in the exact shape run_variant() produces,
    proving build_comparison_report's arithmetic and structure without running the real chain."""

    @staticmethod
    def _variant(*, denominator: int, retained_map: dict[str, dict]) -> dict:
        return {
            "fundamental_denominator": denominator,
            "sessions": ["2026-08-27", "2026-08-28"],
            "per_session": {
                session: {
                    "session_bundle_denominator": 10,
                    "engine_coverage": {"opportunity_ranking_denominator": denominator, "recommendation_ready": retained["ready"]},
                    "bundle_retention": {
                        "recommendation": {"denominator": 10, "retained": retained["retained"], "unavailable": 10 - retained["retained"], "reason_code_distribution": {}},
                        "fundamental_invalidation": {"denominator": 10, "retained": retained["retained"], "unavailable": 10 - retained["retained"], "reason_code_distribution": {}},
                    },
                }
                for session, retained in retained_map.items()
            },
            "lifecycle_replay": {
                "comparable_count": 8,
                "recommendation_transition_matrix": {"UNCHANGED": retained_map["2026-08-27"]["retained"]},
                "invalidation_transition_matrix": {"UNCHANGED": retained_map["2026-08-27"]["retained"]},
            },
        }

    def test_before_after_deltas_computed_correctly(self):
        before = self._variant(denominator=523, retained_map={
            "2026-08-27": {"retained": 6, "ready": 3}, "2026-08-28": {"retained": 7, "ready": 4},
        })
        after = self._variant(denominator=1507, retained_map={
            "2026-08-27": {"retained": 10, "ready": 8}, "2026-08-28": {"retained": 10, "ready": 9},
        })
        report = build_comparison_report(before=before, after=after)
        self.assertEqual(report["fundamental_cohort"], {"before_denominator": 523, "after_denominator": 1507})
        self.assertEqual(report["per_session"]["2026-08-27"]["recommendation_bundle_retention"]["before"]["retained"], 6)
        self.assertEqual(report["per_session"]["2026-08-27"]["recommendation_bundle_retention"]["after"]["retained"], 10)
        self.assertEqual(report["per_session"]["2026-08-28"]["recommendation_bundle_retention"]["before"]["retained"], 7)
        self.assertEqual(report["per_session"]["2026-08-28"]["recommendation_bundle_retention"]["after"]["retained"], 10)
        self.assertEqual(report["per_session"]["2026-08-27"]["recommendation_ready_count"], {"before": 3, "after": 8})
        self.assertFalse(report["scoring_rule_changed"])
        self.assertEqual(report["authority_effect"], "NONE")
        self.assertFalse(report["is_actionable"])

    def test_report_is_deterministic(self):
        before = self._variant(denominator=523, retained_map={"2026-08-27": {"retained": 6, "ready": 3}, "2026-08-28": {"retained": 7, "ready": 4}})
        after = self._variant(denominator=1507, retained_map={"2026-08-27": {"retained": 10, "ready": 8}, "2026-08-28": {"retained": 10, "ready": 9}})
        report_a = build_comparison_report(before=before, after=after)
        report_b = build_comparison_report(before=before, after=after)
        self.assertEqual(report_a, report_b)

    def test_unchanged_coverage_produces_zero_delta(self):
        variant = self._variant(denominator=523, retained_map={"2026-08-27": {"retained": 6, "ready": 3}, "2026-08-28": {"retained": 7, "ready": 4}})
        report = build_comparison_report(before=variant, after=variant)
        for session in ("2026-08-27", "2026-08-28"):
            delta = report["per_session"][session]["recommendation_bundle_retention"]
            self.assertEqual(delta["before"], delta["after"])


if __name__ == "__main__":
    unittest.main()
