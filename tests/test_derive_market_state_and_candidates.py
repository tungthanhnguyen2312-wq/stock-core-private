"""tests/test_derive_market_state_and_candidates.py — Unit tests for market state and research candidate engine."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.derive_market_state_and_candidates import (
    COHORT_FHSC_ENRICHED_FLOW,
    COHORT_HIGH_ACTIVITY_REVERSAL,
    COHORT_HIGH_VOLATILITY_WATCH,
    COHORT_MOMENTUM_PARTICIPATION,
    COHORT_TREND_WITHOUT_PARTICIPATION,
    REGIME_BROAD_RISK_ON,
    REGIME_BROAD_RISK_OFF,
    REGIME_POSITIVE_BUT_NARROW,
    REGIME_STRESS,
    derive_market_regime,
    derive_market_state_and_candidates,
    generate_candidate_markdown_summary,
)


class TestMarketStateAndCandidates(unittest.TestCase):
    def setUp(self) -> None:
        # Mock 5-symbol coverage-aware digest
        self.mock_digest = {
            "schema_version": "1.0.0",
            "contract_version": "capability_first_coverage_aware_digest/v1",
            "session_date": "2026-08-21",
            "digest_identity": "capability_research_digest:mock_sha12345",
            "digest_sha256": "mock_sha12345",
            "market_wide_core": {
                "aggregate_scope": "FULL_RESEARCH_UNIVERSE",
                "universe_count": 5,
                "available_symbol_count": 5,
                "coverage_ratio": 1.0,
                "session_date": "2026-08-21",
                "breadth_summary": {
                    "advancers_count": 3,
                    "decliners_count": 1,
                    "unchanged_count": 1,
                    "advance_decline_ratio": 3.0,
                },
                "return_distribution": {
                    "mean_return_1d": 0.015,
                    "median_return_1d": 0.020,
                    "p25_return_1d": 0.000,
                    "p75_return_1d": 0.030,
                    "min_return_1d": -0.020,
                    "max_return_1d": 0.050,
                },
                "moving_average_breadth": {
                    "above_ma20_count": 4,
                    "at_or_below_ma20_count": 1,
                    "above_ma20_ratio": 0.80,
                },
                "volatility_distribution": {
                    "mean_volatility_20d": 0.025,
                    "median_volatility_20d": 0.020,
                    "min_volatility_20d": 0.010,
                    "max_volatility_20d": 0.050,
                },
                "relative_volume_breadth": {
                    "elevated_volume_count": 2,
                    "normal_volume_count": 2,
                    "depressed_volume_count": 1,
                    "median_relative_volume": 1.20,
                },
                "descriptive_tails": {
                    "top_5_gainers": [{"ticker": "SYM_A", "close_vnd": 25000.0, "return_1d": 0.050}],
                    "top_5_decliners": [{"ticker": "SYM_D", "close_vnd": 15000.0, "return_1d": -0.020}],
                },
            },
            "fhsc_enrichment": {
                "aggregate_scope": "ACQUIRED_ENRICHMENT_COHORT",
                "universe_count": 5,
                "coverage_denominators": {
                    "trading_composition": {
                        "universe_count": 5,
                        "acquired_symbol_count": 2,
                        "coverage_ratio": 0.4,
                        "requested_symbol_count": 3,
                        "affected_rate_limited_count": 1,
                    },
                },
                "cohort_aggregates": {
                    "total_acquired_traded_value_vnd": 500000000000.0,
                    "matched_traded_value_vnd": 400000000000.0,
                    "put_through_traded_value_vnd": 100000000000.0,
                    "cohort_matched_value_ratio": 0.8,
                    "cohort_put_through_value_ratio": 0.2,
                },
            },
            "coverage_summary": {
                "total_universe_symbols": 5,
                "trading_history_scaleout_decomposition": {
                    "total_universe_count": 5,
                    "acquired_count": 2,
                    "rate_limited_count": 1,
                    "missing_requested_session_count": 0,
                    "budget_exhausted_count": 0,
                    "unattempted_count": 2,
                    "reconciled_sum": 5,
                    "reconciliation_valid": True,
                },
            },
            "records": [
                # SYM_A: Momentum candidate (pos return + above MA20 + rel vol >= 1.5) + FHSC acquired
                {
                    "ticker": "SYM_A",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 25000.0,
                        "return_1d": 0.050,
                        "ma_20_vnd": 23000.0,
                        "relative_volume_provider_scoped": 2.10,
                        "volatility_20d": 0.018,
                    },
                    "fhsc_value_volume_composition": {
                        "status": "ACQUIRED",
                        "matched_traded_value_vnd": 400000000000.0,
                        "put_through_traded_value_vnd": 100000000000.0,
                        "matched_value_ratio": 0.80,
                        "put_through_value_ratio": 0.20,  # >= 15% put through -> FHSC flow watch
                    },
                    "fhsc_foreign_room": {
                        "status": "ACQUIRED",
                        "foreign_room_utilization_ratio": 0.95,  # >= 80% -> FHSC flow watch
                    },
                    "fhsc_proprietary_flow": {
                        "status": "ACQUIRED",
                        "net_value_vnd": 25000000000.0,  # >= 10B -> FHSC flow watch
                        "net_volume": 1000000.0,
                    },
                    "fhsc_microstructure": {
                        "status": "ACQUIRED",
                        "order_volume_imbalance_ratio": 0.25,  # >= 0.10 -> FHSC flow watch
                    },
                },
                # SYM_B: Trend without participation (above MA20 + rel vol <= 0.8)
                {
                    "ticker": "SYM_B",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 50000.0,
                        "return_1d": 0.010,
                        "ma_20_vnd": 48000.0,
                        "relative_volume_provider_scoped": 0.60,
                        "volatility_20d": 0.012,
                    },
                    "fhsc_value_volume_composition": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_foreign_room": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_proprietary_flow": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_microstructure": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                },
                # SYM_C: High volatility candidate (vol >= P90)
                {
                    "ticker": "SYM_C",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 12000.0,
                        "return_1d": 0.020,
                        "ma_20_vnd": 11500.0,
                        "relative_volume_provider_scoped": 1.10,
                        "volatility_20d": 0.050,  # Max volatility in sample
                    },
                    "fhsc_value_volume_composition": {"status": "ACQUIRED", "matched_traded_value_vnd": 100000000.0, "put_through_value_ratio": 0.0},
                    "fhsc_foreign_room": {"status": "ACQUIRED", "foreign_room_utilization_ratio": 0.30},
                    "fhsc_proprietary_flow": {"status": "ACQUIRED", "net_value_vnd": 1000000.0},
                    "fhsc_microstructure": {"status": "ACQUIRED", "order_volume_imbalance_ratio": 0.02},
                },
                # SYM_D: High activity reversal (neg return + rel vol >= 1.5)
                {
                    "ticker": "SYM_D",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 15000.0,
                        "return_1d": -0.020,
                        "ma_20_vnd": 16000.0,
                        "relative_volume_provider_scoped": 1.95,
                        "volatility_20d": 0.022,
                    },
                    "fhsc_value_volume_composition": {"status": "PROVIDER_RATE_LIMITED"},
                    "fhsc_foreign_room": {"status": "PROVIDER_RATE_LIMITED"},
                    "fhsc_proprietary_flow": {"status": "PROVIDER_RATE_LIMITED"},
                    "fhsc_microstructure": {"status": "PROVIDER_RATE_LIMITED"},
                },
                # SYM_E: Unchanged neutral name
                {
                    "ticker": "SYM_E",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 30000.0,
                        "return_1d": 0.000,
                        "ma_20_vnd": 29000.0,
                        "relative_volume_provider_scoped": 1.00,
                        "volatility_20d": 0.015,
                    },
                    "fhsc_value_volume_composition": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_foreign_room": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_proprietary_flow": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_microstructure": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                },
            ],
        }

    def test_regime_derivation_rules(self) -> None:
        # 1. Broad Risk On
        r_on = derive_market_regime(
            advancers_count=350,
            decliners_count=90,
            total_universe_count=524,
            above_ma20_count=320,
            median_return_1d=0.015,
            negative_return_and_elevated_volume_count=15,
        )
        self.assertEqual(r_on["regime_label"], REGIME_BROAD_RISK_ON)

        # 2. Broad Risk Off
        r_off = derive_market_regime(
            advancers_count=80,
            decliners_count=380,
            total_universe_count=524,
            above_ma20_count=150,
            median_return_1d=-0.012,
            negative_return_and_elevated_volume_count=60,
        )
        self.assertEqual(r_off["regime_label"], REGIME_BROAD_RISK_OFF)

        # 3. Stress
        r_stress = derive_market_regime(
            advancers_count=30,
            decliners_count=450,
            total_universe_count=524,
            above_ma20_count=50,
            median_return_1d=-0.035,
            negative_return_and_elevated_volume_count=120,
        )
        self.assertEqual(r_stress["regime_label"], REGIME_STRESS)

    def test_market_state_metrics_and_universe_denominator(self) -> None:
        artifact = derive_market_state_and_candidates(self.mock_digest)
        m_state = artifact["market_state"]

        # Proves full-market scope and 5-symbol denominator
        self.assertEqual(m_state["aggregate_scope"], "FULL_RESEARCH_UNIVERSE")
        self.assertEqual(m_state["universe_count"], 5)

        # Cross-metric counts
        x = m_state["cross_metric_intersections"]
        self.assertEqual(x["positive_return_and_above_ma20_count"], 3)  # SYM_A, SYM_B, SYM_C
        self.assertEqual(x["positive_return_and_elevated_volume_count"], 1)  # SYM_A
        self.assertEqual(x["negative_return_and_elevated_volume_count"], 1)  # SYM_D
        self.assertEqual(x["above_ma20_and_elevated_volume_count"], 1)  # SYM_A

    def test_candidate_cohort_inclusion_rules_and_reasons(self) -> None:
        artifact = derive_market_state_and_candidates(self.mock_digest)
        cohorts = artifact["research_candidate_cohorts"]["cohort_entries"]

        # 1. MOMENTUM_PARTICIPATION: SYM_A only
        mom = cohorts[COHORT_MOMENTUM_PARTICIPATION]
        self.assertEqual(len(mom), 1)
        self.assertEqual(mom[0]["ticker"], "SYM_A")
        self.assertTrue(any("POSITIVE_RETURN_1D" in r for r in mom[0]["reason_codes"]))
        self.assertTrue(any("ABOVE_20D_MOVING_AVERAGE" in r for r in mom[0]["reason_codes"]))
        self.assertTrue(any("ELEVATED_RELATIVE_VOLUME" in r for r in mom[0]["reason_codes"]))

        # 2. TREND_WITHOUT_PARTICIPATION: SYM_B only
        trend = cohorts[COHORT_TREND_WITHOUT_PARTICIPATION]
        self.assertEqual(len(trend), 1)
        self.assertEqual(trend[0]["ticker"], "SYM_B")
        self.assertTrue(any("DEPRESSED_RELATIVE_VOLUME" in r for r in trend[0]["reason_codes"]))

        # 3. HIGH_ACTIVITY_REVERSAL: SYM_D only
        rev = cohorts[COHORT_HIGH_ACTIVITY_REVERSAL]
        self.assertEqual(len(rev), 1)
        self.assertEqual(rev[0]["ticker"], "SYM_D")
        self.assertTrue(any("NEGATIVE_RETURN_1D" in r for r in rev[0]["reason_codes"]))

        # 4. HIGH_VOLATILITY_WATCH: SYM_C (highest volatility)
        vol_watch = cohorts[COHORT_HIGH_VOLATILITY_WATCH]
        self.assertTrue(any(e["ticker"] == "SYM_C" for e in vol_watch))

        # 5. FHSC_ENRICHED_FLOW_WATCH: SYM_A (triggered 4 enrichment criteria)
        flow = cohorts[COHORT_FHSC_ENRICHED_FLOW]
        self.assertEqual(len(flow), 1)
        self.assertEqual(flow[0]["ticker"], "SYM_A")
        self.assertTrue(any("SIGNIFICANT_PUT_THROUGH_SHARE" in r for r in flow[0]["reason_codes"]))
        self.assertTrue(any("LARGE_PROPRIETARY_FLOW_NET_BUY" in r for r in flow[0]["reason_codes"]))
        self.assertTrue(any("HIGH_FOREIGN_ROOM_UTILIZATION" in r for r in flow[0]["reason_codes"]))
        self.assertTrue(any("AGGRESSIVE_BUY_IMBALANCE" in r for r in flow[0]["reason_codes"]))

    def test_missing_fhsc_values_do_not_become_zero(self) -> None:
        artifact = derive_market_state_and_candidates(self.mock_digest)
        flow = artifact["research_candidate_cohorts"]["cohort_entries"][COHORT_FHSC_ENRICHED_FLOW]

        # SYM_B (unacquired) must not be in FHSC flow watch
        self.assertNotIn("SYM_B", [e["ticker"] for e in flow])

    def test_authority_boundaries_preserved(self) -> None:
        artifact = derive_market_state_and_candidates(self.mock_digest)
        auth = artifact["authority_boundaries"]

        self.assertEqual(auth["authority_effect"], "NONE")
        self.assertFalse(auth["raw_as_traded_promoted"])
        self.assertFalse(auth["pit_backtest_eligible"])
        self.assertEqual(auth["liquidity_sizing_authority"], "BLOCKED")
        self.assertFalse(auth["valuation_authority"])
        self.assertFalse(auth["recommendation_authority"])
        self.assertFalse(auth["ranking_authority"])

    def test_deterministic_identity_stability_and_sensitivity(self) -> None:
        a1 = derive_market_state_and_candidates(self.mock_digest)
        a2 = derive_market_state_and_candidates(self.mock_digest)
        self.assertEqual(a1["artifact_sha256"], a2["artifact_sha256"])
        self.assertEqual(a1["artifact_identity"], a2["artifact_identity"])

        # Change in input record must change sha256
        mutated_digest = json.loads(json.dumps(self.mock_digest))
        mutated_digest["records"][0]["dnse_market_data"]["return_1d"] = 0.080
        a3 = derive_market_state_and_candidates(mutated_digest)
        self.assertNotEqual(a1["artifact_sha256"], a3["artifact_sha256"])

    def test_markdown_summary_generation(self) -> None:
        artifact = derive_market_state_and_candidates(self.mock_digest)
        md = generate_candidate_markdown_summary(artifact)

        self.assertIn("Daily Market State & Research Candidate Digest", md)
        self.assertIn("MOMENTUM_PARTICIPATION", md)
        self.assertIn("HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION", md)
        self.assertIn("FHSC Enriched Flow Watch", md)
        self.assertIn("SYM_A", md)


if __name__ == "__main__":
    unittest.main()
