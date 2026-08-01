# ==========================================================================
# Focused tests for Phase 4B analysis_lane_eligibility.py (schema + eligibility
# gates MVP only -- no ranking, no scoring, no fact/catalyst/scenario generation).
# Run: `python -m unittest tests.test_analysis_lane_eligibility` from the repo root.
# Pure unit tests against synthetic dicts -- no real data, no database, no bundle.
# ==========================================================================

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analysis_lane_eligibility as ale  # noqa: E402


def _lane(results: list[dict], name: str) -> dict:
    for r in results:
        if r["lane"] == name:
            return r
    raise AssertionError(f"lane {name!r} not found in results")


VERIFIED_FPC = {
    "ticker": "TEST",
    "latest_raw_period": "2026-Q1",
    "latest_calendar_eligible_period": "2026-Q1",
    "latest_verified_period": "2026-Q1",
    "latest_complete_period": None,
    "coverage_status": "verified_only",
    "limitations": ["some limitation"],
    "is_actionable": False,
}

UNVERIFIED_FPC = {
    "ticker": "TEST",
    "latest_raw_period": "2026-Q1",
    "latest_calendar_eligible_period": "2026-Q1",
    "latest_verified_period": None,
    "latest_complete_period": None,
    "coverage_status": "calendar_eligible_only",
    "limitations": [],
    "is_actionable": False,
}

NOT_OBSERVED_ANOMALY = {"status": "not_observed", "explanation_status": "not_applicable", "limitations": []}
UNRESOLVED_ANOMALY = {"status": "anomaly_observed", "explanation_status": "decomposition_available_unreconciled", "limitations": []}

AVAILABLE_OPP_RANKING = {
    "schema_version": "1.0.0", "ticker": "TEST", "entity_type": "corporate", "state": "available",
    "dimensions": {
        "financial_quality": {"state": "available"},
        "valuation": {"state": "available"},
        "technical_current_market_readiness": {"state": "available"},
        "catalyst_evidence": {"state": "available"},
        "downside_invalidation": {"state": "available"},
        "data_confidence": {"state": "available"},
    },
}

VERIFIED_BASIS = {
    "price_basis": "raw", "price_basis_verified": True,
    "volume_basis": "raw", "volume_basis_verified": True,
    "is_actionable": False,
}

UNKNOWN_BASIS = {
    "price_basis": "unknown", "price_basis_verified": False,
    "volume_basis": "unknown", "volume_basis_verified": False,
    "is_actionable": False,
}


class LaneSchemaShapeTests(unittest.TestCase):
    def test_all_five_lanes_always_returned_with_required_fields(self):
        results = ale.evaluate_ticker_lanes("TEST")
        self.assertEqual([r["lane"] for r in results], list(ale.LANES))
        required_fields = {
            "lane", "status", "eligible", "blocking_reasons", "data_warnings",
            "required_evidence", "supporting_paths", "limitations", "is_actionable",
        }
        for r in results:
            self.assertEqual(set(r.keys()), required_fields)
            self.assertIn(r["status"], ale.STATUSES)
            self.assertEqual(r["eligible"], r["status"] == "eligible_for_analysis")
            self.assertIs(r["is_actionable"], False)


class Gate1PriceVolumeBasisTests(unittest.TestCase):
    def test_unknown_price_and_volume_basis_blocks_dependent_claims(self):
        results = ale.evaluate_ticker_lanes("TEST", price_basis_provenance=UNKNOWN_BASIS)
        for r in results:
            joined = " ".join(r["data_warnings"])
            self.assertIn("adjusted_return_claims_blocked", joined)
            self.assertIn("liquidity_claims_blocked", joined)
            self.assertIn("backtest_claims_blocked", joined)

    def test_verified_price_and_volume_basis_does_not_block_claims(self):
        results = ale.evaluate_ticker_lanes("TEST", price_basis_provenance=VERIFIED_BASIS)
        for r in results:
            joined = " ".join(r["data_warnings"])
            self.assertNotIn("adjusted_return_claims_blocked", joined)
            self.assertNotIn("liquidity_claims_blocked", joined)
            self.assertNotIn("backtest_claims_blocked", joined)

    def test_missing_price_basis_provenance_fails_closed_as_blocked_claims(self):
        results = ale.evaluate_ticker_lanes("TEST", price_basis_provenance=None)
        joined = " ".join(_lane(results, "quality_growth")["data_warnings"])
        self.assertIn("price_basis_provenance_missing", joined)


class Gate2FinancialCoverageTests(unittest.TestCase):
    def test_missing_verified_financial_coverage_blocks_quality_growth(self):
        result = ale.evaluate_quality_growth(
            "TEST", entity_type="corporate",
            financial_period_coverage=UNVERIFIED_FPC,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["eligible"])
        self.assertIn("no_verified_financial_period", result["blocking_reasons"])

    def test_wholly_missing_financial_coverage_is_blocked_not_insufficient(self):
        result = ale.evaluate_quality_growth(
            "TEST", entity_type="corporate",
            financial_period_coverage=None,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("financial_period_coverage_missing", result["blocking_reasons"])


class Gate5EarningsAnomalyTests(unittest.TestCase):
    def test_unexplained_earnings_anomaly_blocks_quality_growth(self):
        result = ale.evaluate_quality_growth(
            "TEST", entity_type="corporate",
            financial_period_coverage=VERIFIED_FPC,
            earnings_anomaly=UNRESOLVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["eligible"])
        self.assertTrue(any("unexplained_earnings_anomaly" in reason for reason in result["blocking_reasons"]))

    def test_not_observed_anomaly_does_not_block_quality_growth(self):
        result = ale.evaluate_quality_growth(
            "TEST", entity_type="corporate",
            financial_period_coverage=VERIFIED_FPC,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertEqual(result["status"], "eligible_for_analysis")


class Gate3ValuationComparabilityTests(unittest.TestCase):
    def test_incomparable_valuation_namespaces_block_valuation_change_claims(self):
        valuation_namespaces = {
            "live_vendor": {"metrics": {"pe": {"value": 11.98}}},
            "historical_calculated": {"metrics": {"pe": {"value": 10.55}}},
            "comparability": {"metrics": {"pe": {"status": "incomparable", "is_actionable": False}}},
        }
        results = ale.evaluate_ticker_lanes("TEST", valuation_namespaces=valuation_namespaces)
        for r in results:
            joined = " ".join(r["data_warnings"])
            self.assertIn("valuation_change_claims_blocked:pe:incomparable", joined)

    def test_comparable_valuation_namespaces_do_not_block_valuation_change_claims(self):
        valuation_namespaces = {
            "live_vendor": {"metrics": {"pe": {"value": 11.98}}},
            "historical_calculated": {"metrics": {"pe": {"value": 11.98}}},
            "comparability": {"metrics": {"pe": {"status": "comparable", "is_actionable": False}}},
        }
        results = ale.evaluate_ticker_lanes("TEST", valuation_namespaces=valuation_namespaces)
        for r in results:
            joined = " ".join(r["data_warnings"])
            self.assertNotIn("valuation_change_claims_blocked:pe", joined)


class Gate4ShareBasisIdentityTests(unittest.TestCase):
    def test_missing_share_basis_identity_blocks_applicable_per_share_analysis(self):
        share_basis_identities = {
            "current_market": {"value": None},
            "financial_period_end": {"value": 6396250200},
            "weighted_average": {"value": 6396250200},
            "comparability": {"pairs": {
                "current_vs_period_end": {"status": "insufficient_identity", "is_actionable": False},
            }},
        }
        result = ale.evaluate_income_defensive(
            "TEST", entity_type="corporate", risk_semantics=None,
            share_basis_identities=share_basis_identities, financial_period_coverage=VERIFIED_FPC,
        )
        self.assertTrue(any(
            reason.startswith("share_basis_identity_insufficient_identity:current_vs_period_end")
            for reason in result["blocking_reasons"]
        ))


class Gate6NonActionableMetadataTests(unittest.TestCase):
    def test_non_actionable_risk_ranking_ta_and_news_contracts_remain_non_actionable(self):
        risk_semantics = {
            "legacy_field": "risk", "polarity": "higher_is_safer", "score_value": 100,
            "interpretation": "...", "limitations": [], "is_actionable": False,
        }
        ta_signal_semantics = {
            "coverage_status": "available", "evaluation_status": "record_available", "reason": None,
            "presence_interpretation": "presence only", "null_interpretation": None,
            "is_no_signal_claim": False, "is_actionable": False,
        }
        news_window_semantics = {
            "cutoff_semantics": "lookback_window_start", "mapping_coverage_status": "unqualified",
            "is_no_relevant_news_claim": False, "is_actionable": False, "interpretation_limits": [],
        }
        results = ale.evaluate_ticker_lanes(
            "TEST",
            entity_type="corporate",
            financial_period_coverage=VERIFIED_FPC,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
            risk_semantics=risk_semantics,
            ta_signal_semantics=ta_signal_semantics,
            news_window_semantics=news_window_semantics,
            price_basis_provenance=VERIFIED_BASIS,
        )
        for r in results:
            self.assertIs(r["is_actionable"], False)
            self.assertTrue(any("not investment signals" in lim for lim in r["limitations"]))


class Gate7NewsAndGate8TATests(unittest.TestCase):
    def test_zero_mapped_news_does_not_become_a_no_news_claim(self):
        news_window_semantics = {
            "mapping_coverage_status": "unqualified", "is_no_relevant_news_claim": False, "is_actionable": False,
        }
        results = ale.evaluate_ticker_lanes("TEST", news_window_semantics=news_window_semantics)
        joined = " ".join(_lane(results, "structural_catalyst")["data_warnings"])
        self.assertIn("zero_or_partial_news_mapping_is_not_a_no_news_claim", joined)

    def test_missing_ta_signal_does_not_become_neutral_or_no_signal_claim(self):
        ta_signal_semantics = {
            "coverage_status": "missing", "evaluation_status": "unqualified",
            "reason": "absent_from_ta_signals_csv",
            "null_interpretation": "null indicates absence, not a confirmed no-signal claim or neutral conclusion.",
            "is_no_signal_claim": False, "is_actionable": False,
        }
        results = ale.evaluate_ticker_lanes("TEST", ta_signal_semantics=ta_signal_semantics)
        joined = " ".join(_lane(results, "quality_growth")["data_warnings"])
        self.assertIn("ta_signal_missing", joined)
        self.assertIn("not a confirmed no-signal claim", joined)


class Gate10FailClosedTests(unittest.TestCase):
    def test_all_contracts_missing_fails_closed_on_every_lane(self):
        """With every contract missing, the four analytical lanes must never reach
        eligible_for_analysis. blocked_avoid is the one lane whose own
        eligible_for_analysis IS the fail-closed outcome -- it means "correctly
        routed to blocked/avoid due to insufficient evidence", not an analysis result."""
        results = ale.evaluate_ticker_lanes("TEST")
        for r in results:
            self.assertIs(r["is_actionable"], False)
            if r["lane"] == "blocked_avoid":
                self.assertEqual(r["status"], "eligible_for_analysis")
                self.assertTrue(r["eligible"])
            else:
                self.assertNotEqual(r["status"], "eligible_for_analysis")
                self.assertFalse(r["eligible"])

    def test_malformed_contract_fails_closed_locally_without_raising(self):
        result = ale.evaluate_quality_growth(
            "TEST", entity_type="corporate",
            financial_period_coverage="not_a_dict",  # type: ignore[arg-type]
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("financial_period_coverage_missing", result["blocking_reasons"])


class FullyEvidencedEligibilityTests(unittest.TestCase):
    def test_fully_evidenced_synthetic_input_reaches_eligible_for_analysis(self):
        result = ale.evaluate_quality_growth(
            "TEST", entity_type="corporate",
            financial_period_coverage=VERIFIED_FPC,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertEqual(result["status"], "eligible_for_analysis")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["blocking_reasons"], [])


class SectorApplicabilityTests(unittest.TestCase):
    def test_bank_entity_type_returns_not_applicable_for_quality_growth(self):
        result = ale.evaluate_quality_growth(
            "TEST", entity_type="bank",
            financial_period_coverage=VERIFIED_FPC,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertEqual(result["status"], "not_applicable")
        self.assertFalse(result["eligible"])


class DeterminismAndProvenanceTests(unittest.TestCase):
    def test_results_are_deterministic_across_repeated_calls(self):
        kwargs = dict(
            entity_type="corporate",
            financial_period_coverage=VERIFIED_FPC,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
            price_basis_provenance=UNKNOWN_BASIS,
        )
        first = ale.evaluate_ticker_lanes("HPG", **copy.deepcopy(kwargs))
        second = ale.evaluate_ticker_lanes("HPG", **copy.deepcopy(kwargs))
        self.assertEqual(first, second)

    def test_supporting_paths_are_preserved_and_ticker_scoped(self):
        result = ale.evaluate_quality_growth(
            "HPG", entity_type="corporate",
            financial_period_coverage=UNVERIFIED_FPC,
            earnings_anomaly=NOT_OBSERVED_ANOMALY,
            opportunity_ranking=AVAILABLE_OPP_RANKING,
        )
        self.assertTrue(result["supporting_paths"])
        self.assertTrue(all(p.startswith("tickers.HPG.") for p in result["supporting_paths"]))


if __name__ == "__main__":
    unittest.main()
