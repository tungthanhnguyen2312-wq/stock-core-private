"""tests/test_derive_cross_dimension_research_digest.py — Unit tests for cross-dimension research digest."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.derive_cross_dimension_research_digest import (
    CODE_ABOVE_MA20,
    CODE_ACTIVE_BUY_SKEW,
    CODE_ACTIVE_SELL_SKEW,
    CODE_BELOW_MA20,
    CODE_DEPRESSED_REL_VOL,
    CODE_ELEVATED_REL_VOL,
    CODE_FULL_FOREIGN_ROOM,
    CODE_HIGH_FOREIGN_ROOM,
    CODE_MATERIAL_ACTIVE_BUY_IMBALANCE,
    CODE_MATERIAL_ACTIVE_SELL_IMBALANCE,
    CODE_MATERIAL_PROP_NET_BUY,
    CODE_MATERIAL_PROP_NET_SELL,
    CODE_MOMENTUM_WITH_PROP_BUY,
    CODE_MOMENTUM_WITH_PROP_SELL,
    CODE_NO_PROP_ACTIVITY,
    CODE_PROP_NET_BUY,
    CODE_PROP_NET_SELL,
    CODE_PUT_THROUGH_DOMINANT,
    CODE_REVERSAL_WITH_ACTIVE_SELLING,
    CODE_SIGNIFICANT_PUT_THROUGH,
    CODE_TREND_WITH_PUT_THROUGH_DOMINANCE,
    TIER_FULLY_ENRICHED,
    TIER_PARTIALLY_ENRICHED,
    build_cross_dimension_research_digest,
    derive_cross_dimension_target_record,
    generate_cross_dimension_markdown_summary,
)


class TestCrossDimensionResearchDigest(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_digest = {
            "schema_version": "1.0.0",
            "session_date": "2026-08-21",
            "digest_identity": "capability_research_digest:mock_digest_sha",
            "records": [
                # ACB: High prop buy (+3.25B VND < 10B), Room 79.45% (< 80%), PT 15.3%, RelVol 1.13x (NOT in MOMENTUM)
                {
                    "ticker": "ACB",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 22750.0,
                        "ma_20_vnd": 22287.5,
                        "return_1d": 0.0364,
                        "relative_volume_provider_scoped": 1.13,
                    },
                    "fhsc_value_volume_composition": {
                        "status": "ACQUIRED",
                        "matched_traded_value_vnd": 272646415000.0,
                        "put_through_traded_value_vnd": 49197500000.0,
                        "put_through_value_ratio": 0.152861,
                        "matched_volume_shares": 12000000.0,
                        "put_through_volume_shares": 2162527.0,
                        "total_volume_shares": 14162527.0,
                    },
                    "fhsc_foreign_room": {
                        "status": "ACQUIRED",
                        "max_shares": 1741326587,
                        "owned_shares": 1383410234,
                        "available_shares": 357916353,
                        "foreign_room_utilization_ratio": 0.794458,
                    },
                    "fhsc_proprietary_flow": {
                        "status": "ACQUIRED",
                        "buy_value_vnd": 54973430000.0,
                        "sell_value_vnd": 51721180000.0,
                        "net_value_vnd": 3252250000.0,
                        "buy_volume": 2443900.0,
                        "sell_volume": 2315400.0,
                        "net_volume": 128500.0,
                    },
                    "fhsc_microstructure": {
                        "status": "ACQUIRED",
                        "active_buy_orders": 4482,
                        "active_sell_orders": 6163,
                        "active_buy_volume": 20865737.0,
                        "active_sell_volume": 20535677.0,
                        "active_net_volume": 330060.0,
                        "order_volume_imbalance_ratio": 0.007972,
                    },
                },
                # BAF: Momentum member (+0.93%, 2.16x rel vol), PT 34.0%, Prop net buy +122.3M VND
                {
                    "ticker": "BAF",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 32500.0,
                        "ma_20_vnd": 30937.5,
                        "return_1d": 0.0093,
                        "relative_volume_provider_scoped": 2.16,
                    },
                    "fhsc_value_volume_composition": {
                        "status": "ACQUIRED",
                        "matched_traded_value_vnd": 126455890000.0,
                        "put_through_traded_value_vnd": 65000000000.0,
                        "put_through_value_ratio": 0.339504,
                        "matched_volume_shares": 3890950.0,
                        "put_through_volume_shares": 2000000.0,
                        "total_volume_shares": 5890950.0,
                    },
                    "fhsc_foreign_room": {
                        "status": "ACQUIRED",
                        "max_shares": 182412453,
                        "owned_shares": 10811985,
                        "available_shares": 171600468,
                        "foreign_room_utilization_ratio": 0.059272,
                    },
                    "fhsc_proprietary_flow": {
                        "status": "ACQUIRED",
                        "buy_value_vnd": 125580000.0,
                        "sell_value_vnd": 3250000.0,
                        "net_value_vnd": 122330000.0,
                        "buy_volume": 3900.0,
                        "sell_volume": 100.0,
                        "net_volume": 3800.0,
                    },
                    "fhsc_microstructure": {
                        "status": "ACQUIRED",
                        "active_buy_orders": 520,
                        "active_sell_orders": 568,
                        "active_buy_volume": 7792792.0,
                        "active_sell_volume": 7048303.0,
                        "active_net_volume": 744489.0,
                        "order_volume_imbalance_ratio": 0.050164,
                    },
                },
                # BWS: Reversal member (-0.93%, 23.96x rel vol), PT 22.4%, Active sell imbalance -0.3785, Zero prop flow
                {
                    "ticker": "BWS",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 32000.0,
                        "ma_20_vnd": 32670.0,
                        "return_1d": -0.0093,
                        "relative_volume_provider_scoped": 23.96,
                    },
                    "fhsc_value_volume_composition": {
                        "status": "ACQUIRED",
                        "matched_traded_value_vnd": 1775620000.0,
                        "put_through_traded_value_vnd": 512380000.0,
                        "put_through_value_ratio": 0.223942,
                        "matched_volume_shares": 55488.0,
                        "put_through_volume_shares": 16012.0,
                        "total_volume_shares": 71500.0,
                    },
                    "fhsc_foreign_room": {
                        "status": "ACQUIRED",
                        "max_shares": 49003708,
                        "owned_shares": 595985,
                        "available_shares": 48407723,
                        "foreign_room_utilization_ratio": 0.012162,
                    },
                    "fhsc_proprietary_flow": {
                        "status": "ACQUIRED",
                        "buy_value_vnd": 0.0,
                        "sell_value_vnd": 0.0,
                        "net_value_vnd": 0.0,
                        "buy_volume": 0.0,
                        "sell_volume": 0.0,
                        "net_volume": 0.0,
                    },
                    "fhsc_microstructure": {
                        "status": "ACQUIRED",
                        "active_buy_orders": 56,
                        "active_sell_orders": 206,
                        "active_buy_volume": 110278.0,
                        "active_sell_volume": 244618.0,
                        "active_net_volume": -134340.0,
                        "order_volume_imbalance_ratio": -0.378533,
                    },
                },
                # DHM: Trend without volume member (-3.68%, 0.19x rel vol), PT 99.6%, Foreign Room 404, Zero prop flow
                {
                    "ticker": "DHM",
                    "dnse_market_data": {
                        "exact_session_close_vnd": 6550.0,
                        "ma_20_vnd": 6478.0,
                        "return_1d": -0.0368,
                        "relative_volume_provider_scoped": 0.19,
                    },
                    "fhsc_value_volume_composition": {
                        "status": "ACQUIRED",
                        "matched_traded_value_vnd": 7425000.0,
                        "put_through_traded_value_vnd": 2033200000.0,
                        "put_through_value_ratio": 0.996361,
                        "matched_volume_shares": 1100.0,
                        "put_through_volume_shares": 299000.0,
                        "total_volume_shares": 300100.0,
                    },
                    "fhsc_foreign_room": {
                        "status": "FAILED_http_status_404",
                        "foreign_room_utilization_ratio": None,
                    },
                    "fhsc_proprietary_flow": {
                        "status": "ACQUIRED",
                        "buy_value_vnd": 0.0,
                        "sell_value_vnd": 0.0,
                        "net_value_vnd": 0.0,
                        "buy_volume": 0.0,
                        "sell_volume": 0.0,
                        "net_volume": 0.0,
                    },
                    "fhsc_microstructure": {
                        "status": "ACQUIRED",
                        "active_buy_orders": 26,
                        "active_sell_orders": 319,
                        "active_buy_volume": 316787.0,
                        "active_sell_volume": 332194.0,
                        "active_net_volume": -15407.0,
                        "order_volume_imbalance_ratio": -0.02374,
                    },
                },
                # Extra symbols to test coverage reconciliation
                {
                    "ticker": "TH_ONLY_SYM",
                    "dnse_market_data": {"return_1d": 0.01},
                    "fhsc_value_volume_composition": {"status": "ACQUIRED", "matched_traded_value_vnd": 1000.0},
                    "fhsc_foreign_room": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_proprietary_flow": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                    "fhsc_microstructure": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                },
                {
                    "ticker": "RATE_LIM_SYM",
                    "dnse_market_data": {"return_1d": 0.01},
                    "fhsc_value_volume_composition": {"status": "PROVIDER_RATE_LIMITED"},
                },
                {
                    "ticker": "TIMEOUT_SYM",
                    "dnse_market_data": {"return_1d": 0.01},
                    "fhsc_value_volume_composition": {"status": "TRANSPORT_TIMEOUT"},
                },
                {
                    "ticker": "UNATTEMPTED_SYM",
                    "dnse_market_data": {"return_1d": 0.01},
                    "fhsc_value_volume_composition": {"status": "NOT_ACQUIRED_IN_THIS_SCALEOUT"},
                },
            ],
        }

        self.mock_candidates = {
            "schema_version": "1.0.0",
            "artifact_identity": "market_state_and_candidates:mock_cand_sha",
            "research_candidate_cohorts": {
                "cohort_entries": {
                    "MOMENTUM_PARTICIPATION": [{"ticker": "BAF"}],
                    "HIGH_ACTIVITY_REVERSAL_OR_DISTRIBUTION": [{"ticker": "BWS"}],
                    "TREND_WITHOUT_PARTICIPATION": [{"ticker": "DHM"}],
                    "FHSC_ENRICHED_FLOW_WATCH": [{"ticker": "ACB"}, {"ticker": "BAF"}, {"ticker": "BWS"}, {"ticker": "DHM"}],
                }
            },
        }

    def test_coverage_reconciliation_invariants(self) -> None:
        digest = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)
        rec = digest["coverage_reconciliation"]

        self.assertEqual(rec["total_universe_count"], 8)
        self.assertEqual(rec["trading_history_acquired_count"], 5)  # ACB, BAF, BWS, DHM, TH_ONLY_SYM
        self.assertEqual(rec["fully_enriched_count"], 3)            # ACB, BAF, BWS
        self.assertEqual(rec["partially_enriched_count"], 1)        # DHM
        self.assertEqual(rec["trading_history_only_count"], 1)      # TH_ONLY_SYM
        self.assertEqual(rec["provider_rate_limited_count"], 1)     # RATE_LIM_SYM
        self.assertEqual(rec["transport_failure_count"], 1)         # TIMEOUT_SYM
        self.assertEqual(rec["genuinely_unattempted_count"], 1)     # UNATTEMPTED_SYM

        # Invariant 1: trading_history_acquired == fully + partially + th_only
        self.assertEqual(
            rec["trading_history_acquired_count"],
            rec["fully_enriched_count"] + rec["partially_enriched_count"] + rec["trading_history_only_count"]
        )

        # Invariant 2: total_universe == sum of all mutually exclusive categories
        self.assertEqual(rec["reconciled_sum"], 8)
        self.assertTrue(rec["reconciliation_valid"])

    def test_acb_threshold_and_compound_code_boundaries(self) -> None:
        """ACB has prop net buy +3.25B VND (< 10B threshold) and is NOT in MOMENTUM_PARTICIPATION."""
        digest = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)
        records_by_ticker = {r["ticker"]: r for r in digest["target_records"]}
        acb = records_by_ticker["ACB"]

        self.assertEqual(acb["enrichment_tier"], TIER_FULLY_ENRICHED)
        self.assertEqual(acb["price_and_trend"]["relative_volume"], 1.13)
        self.assertEqual(acb["proprietary_flow"]["net_value_vnd"], 3252250000.0)

        codes = acb["reason_codes"]
        # Must have simple directional descriptors
        self.assertIn(CODE_PROP_NET_BUY, codes)
        self.assertIn(CODE_ACTIVE_BUY_SKEW, codes)
        self.assertIn(CODE_ABOVE_MA20, codes)
        self.assertIn(CODE_SIGNIFICANT_PUT_THROUGH, codes)

        # Must NOT have threshold trigger (since 3.25B < 10B VND)
        self.assertNotIn(CODE_MATERIAL_PROP_NET_BUY, codes)

        # Must NOT have compound code MOMENTUM_WITH_PROP_BUY because not in MOMENTUM_PARTICIPATION
        self.assertNotIn(CODE_MOMENTUM_WITH_PROP_BUY, codes)

    def test_baf_compound_code_eligibility(self) -> None:
        """BAF is in MOMENTUM_PARTICIPATION and has prop_net_value > 0 -> MOMENTUM_WITH_PROP_BUY applies."""
        digest = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)
        records_by_ticker = {r["ticker"]: r for r in digest["target_records"]}
        baf = records_by_ticker["BAF"]

        self.assertEqual(baf["enrichment_tier"], TIER_FULLY_ENRICHED)
        codes = baf["reason_codes"]

        self.assertIn(CODE_ELEVATED_REL_VOL, codes)
        self.assertIn(CODE_PROP_NET_BUY, codes)
        self.assertIn(CODE_SIGNIFICANT_PUT_THROUGH, codes)
        self.assertIn(CODE_MOMENTUM_WITH_PROP_BUY, codes)

    def test_bws_reversal_compound_code_and_zero_prop_flow(self) -> None:
        """BWS is in HIGH_ACTIVITY_REVERSAL, has active sell imbalance, and zero prop flow."""
        digest = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)
        records_by_ticker = {r["ticker"]: r for r in digest["target_records"]}
        bws = records_by_ticker["BWS"]

        self.assertEqual(bws["enrichment_tier"], TIER_FULLY_ENRICHED)
        codes = bws["reason_codes"]

        self.assertIn(CODE_REVERSAL_WITH_ACTIVE_SELLING, codes)
        self.assertIn(CODE_MATERIAL_ACTIVE_SELL_IMBALANCE, codes)
        self.assertIn(CODE_NO_PROP_ACTIVITY, codes)
        self.assertIn(CODE_BELOW_MA20, codes)

        # Zero prop flow must not be labeled as prop buy or prop sell
        self.assertNotIn(CODE_PROP_NET_BUY, codes)
        self.assertNotIn(CODE_PROP_NET_SELL, codes)

    def test_dhm_foreign_room_preservation_and_put_through_dominance(self) -> None:
        """DHM has foreign room 404 preserved as None with status FAILED_http_status_404."""
        digest = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)
        records_by_ticker = {r["ticker"]: r for r in digest["target_records"]}
        dhm = records_by_ticker["DHM"]

        self.assertEqual(dhm["enrichment_tier"], TIER_PARTIALLY_ENRICHED)
        self.assertIsNone(dhm["foreign_room"]["utilization_ratio"])
        self.assertEqual(dhm["foreign_room"]["status"], "FAILED_http_status_404")

        codes = dhm["reason_codes"]
        self.assertIn(CODE_PUT_THROUGH_DOMINANT, codes)
        self.assertIn(CODE_TREND_WITH_PUT_THROUGH_DOMINANCE, codes)
        self.assertIn(CODE_DEPRESSED_REL_VOL, codes)

    def test_deterministic_identity_and_reproducibility(self) -> None:
        d1 = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)
        d2 = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)

        self.assertEqual(d1["digest_sha256"], d2["digest_sha256"])
        self.assertEqual(d1["digest_identity"], d2["digest_identity"])

    def test_markdown_summary_rendering(self) -> None:
        digest = build_cross_dimension_research_digest(self.mock_digest, self.mock_candidates)
        md = generate_cross_dimension_markdown_summary(digest)

        self.assertIn("FHSC Cross-Dimension Research Digest", md)
        self.assertIn("ACB", md)
        self.assertIn("BAF", md)
        self.assertIn("BWS", md)
        self.assertIn("DHM", md)
        self.assertIn("Coverage Reconciliation", md)


if __name__ == "__main__":
    unittest.main()
