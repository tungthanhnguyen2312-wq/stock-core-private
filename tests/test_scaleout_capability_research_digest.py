"""tests/test_scaleout_capability_research_digest.py — Coverage-aware research digest unit tests."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.scaleout_capability_research_digest import (
    AUTHORITY_BOUNDARIES,
    STATUS_ACQUIRED,
    STATUS_BUDGET_EXHAUSTED,
    STATUS_CONFLICTING,
    STATUS_MISSING_SESSION,
    STATUS_NOT_ACQUIRED,
    STATUS_RATE_LIMITED,
    STATUS_REQUESTED_MISSING,
    build_research_digest,
    generate_markdown_summary,
)


class TestScaleoutCapabilityResearchDigest(unittest.TestCase):
    def setUp(self) -> None:
        # Mock universe snapshot with 5 symbols: HPG, ACC, VCB, SSI, AAA
        self.mock_snapshot = {
            "schema_version": "1.0.0",
            "contract_version": "prospective_daily_snapshot/v1",
            "research_session": "2026-08-21",
            "cohort": {
                "member_count": 5,
                "members": ["HPG", "ACC", "VCB", "SSI", "AAA"],
            },
            "records": [
                {
                    "ticker": "HPG",
                    "exact_session_close": 21500.0,
                    "daily_technical_state": {
                        "price_basis": "ADJUSTED_RETROSPECTIVE",
                        "values": {
                            "close": 21500.0,
                            "return_1d": 0.0260,
                            "volatility_20d": 0.0145,
                            "ma_20": 21300.0,
                            "relative_volume_provider_scoped": 1.25,
                        },
                    },
                },
                {
                    "ticker": "ACC",
                    "exact_session_close": 4720.0,
                    "daily_technical_state": {
                        "price_basis": "ADJUSTED_RETROSPECTIVE",
                        "values": {
                            "close": 4720.0,
                            "return_1d": 0.0151,
                            "volatility_20d": 0.0162,
                            "ma_20": 4650.0,
                            "relative_volume_provider_scoped": 1.10,
                        },
                    },
                },
                {
                    "ticker": "VCB",
                    "exact_session_close": 88000.0,
                    "daily_technical_state": {
                        "price_basis": "ADJUSTED_RETROSPECTIVE",
                        "values": {
                            "close": 88000.0,
                            "return_1d": -0.0050,
                            "volatility_20d": 0.0110,
                            "ma_20": 87500.0,
                            "relative_volume_provider_scoped": 0.85,
                        },
                    },
                },
                {
                    "ticker": "SSI",
                    "exact_session_close": 32000.0,
                    "daily_technical_state": {
                        "price_basis": "ADJUSTED_RETROSPECTIVE",
                        "values": {
                            "close": 32000.0,
                            "return_1d": 0.0696,
                            "volatility_20d": 0.0180,
                            "ma_20": 31200.0,
                            "relative_volume_provider_scoped": 1.80,
                        },
                    },
                },
                {
                    "ticker": "AAA",
                    "exact_session_close": 7120.0,
                    "daily_technical_state": {
                        "price_basis": "ADJUSTED_RETROSPECTIVE",
                        "values": {
                            "close": 7120.0,
                            "return_1d": 0.0319,
                            "volatility_20d": 0.0158,
                            "ma_20": 7092.5,
                            "relative_volume_provider_scoped": 0.94,
                        },
                    },
                },
            ],
        }

        # Mock retained packets with differentiated observation statuses
        self.mock_packets = [
            {
                "packet_schema_version": "1.0.0",
                "session_date": "2026-08-21",
                "packet_identity": "packet:mock12345",
                "observations": [
                    # HPG: Fully acquired
                    {
                        "instrument": "HPG",
                        "source": "FHSC",
                        "endpoint_id": "trading_history",
                        "status": STATUS_ACQUIRED,
                        "usability_state": "RESEARCH_USABLE",
                        "raw_sha256": "sha_hpg_trading",
                        "canonical_fields": {
                            "MATCHED_TRADED_VALUE_VND": {"value": 800000000000.0},
                            "PUT_THROUGH_TRADED_VALUE_VND": {"value": 200000000000.0},
                            "TOTAL_TRADED_VALUE_VND": {"value": 1000000000000.0},
                            "MATCHED_VOLUME_SHARES": {"value": 40000000.0},
                            "PUT_THROUGH_VOLUME_SHARES": {"value": 10000000.0},
                            "TOTAL_VOLUME_SHARES": {"value": 50000000.0},
                        },
                    },
                    {
                        "instrument": "HPG",
                        "source": "FHSC",
                        "endpoint_id": "foreign_room",
                        "status": STATUS_ACQUIRED,
                        "usability_state": "RESEARCH_USABLE",
                        "raw_sha256": "sha_hpg_room",
                        "canonical_fields": {
                            "FOREIGN_ROOM_MAX": {"value": 1000000000.0},
                            "FOREIGN_ROOM_OWNED": {"value": 400000000.0},
                            "FOREIGN_ROOM_AVAILABLE": {"value": 600000000.0},
                        },
                    },
                    {
                        "instrument": "HPG",
                        "source": "FHSC",
                        "endpoint_id": "proprietary_trading",
                        "status": STATUS_ACQUIRED,
                        "usability_state": "RESEARCH_USABLE",
                        "raw_sha256": "sha_hpg_prop",
                        "canonical_fields": {
                            "PROPRIETARY_BUY_VALUE": {"value": 50000000000.0},
                            "PROPRIETARY_SELL_VALUE": {"value": 30000000000.0},
                            "PROPRIETARY_NET_VALUE": {"value": 20000000000.0},
                            "PROPRIETARY_BUY_VOLUME": {"value": 2500000.0},
                            "PROPRIETARY_SELL_VOLUME": {"value": 1500000.0},
                            "PROPRIETARY_NET_VOLUME": {"value": 1000000.0},
                        },
                    },
                    {
                        "instrument": "HPG",
                        "source": "FHSC",
                        "endpoint_id": "order_statistics",
                        "status": STATUS_ACQUIRED,
                        "usability_state": "RESEARCH_USABLE",
                        "raw_sha256": "sha_hpg_micro",
                        "canonical_fields": {
                            "ACTIVE_BUY_VOLUME": {"value": 30000000.0},
                            "ACTIVE_SELL_VOLUME": {"value": 20000000.0},
                            "ACTIVE_BUY_ORDER_COUNT": {"value": 5000.0},
                            "ACTIVE_SELL_ORDER_COUNT": {"value": 4000.0},
                        },
                    },
                    # ACC: Acquired trading_history only
                    {
                        "instrument": "ACC",
                        "source": "FHSC",
                        "endpoint_id": "trading_history",
                        "status": STATUS_ACQUIRED,
                        "usability_state": "RESEARCH_USABLE",
                        "raw_sha256": "sha_acc_trading",
                        "canonical_fields": {
                            "MATCHED_TRADED_VALUE_VND": {"value": 2804408000.0},
                            "PUT_THROUGH_TRADED_VALUE_VND": {"value": 0.0},
                            "TOTAL_TRADED_VALUE_VND": {"value": 2804408000.0},
                            "MATCHED_VOLUME_SHARES": {"value": 594100.0},
                            "PUT_THROUGH_VOLUME_SHARES": {"value": 0.0},
                            "TOTAL_VOLUME_SHARES": {"value": 594100.0},
                        },
                    },
                    # SSI: Rate limited on trading_history
                    {
                        "instrument": "SSI",
                        "source": "FHSC",
                        "endpoint_id": "trading_history",
                        "status": STATUS_RATE_LIMITED,
                        "usability_state": "PROVIDER_RATE_LIMITED",
                    },
                    # VCB: Requested but missing session on trading_history
                    {
                        "instrument": "VCB",
                        "source": "FHSC",
                        "endpoint_id": "trading_history",
                        "status": STATUS_MISSING_SESSION,
                        "usability_state": "MISSING",
                    },
                    # AAA: NOT in packet (unattempted)
                ],
            }
        ]

    def test_layer1_market_wide_core_scope_and_breadth(self) -> None:
        digest = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        core = digest["market_wide_core"]

        # Proves Layer 1 is labeled FULL_RESEARCH_UNIVERSE with 5/5 symbols
        self.assertEqual(core["aggregate_scope"], "FULL_RESEARCH_UNIVERSE")
        self.assertEqual(core["universe_count"], 5)
        self.assertEqual(core["available_symbol_count"], 5)
        self.assertEqual(core["coverage_ratio"], 1.0)

        # Proves correct breadth: 4 gainers (HPG, ACC, SSI, AAA), 1 decliner (VCB)
        self.assertEqual(core["breadth_summary"]["advancers_count"], 4)
        self.assertEqual(core["breadth_summary"]["decliners_count"], 1)
        self.assertEqual(core["breadth_summary"]["unchanged_count"], 0)
        self.assertEqual(core["breadth_summary"]["advance_decline_ratio"], 4.0)

        # Proves tails
        self.assertEqual(core["descriptive_tails"]["top_5_gainers"][0]["ticker"], "SSI")
        self.assertEqual(core["descriptive_tails"]["top_5_decliners"][0]["ticker"], "VCB")

    def test_layer2_fhsc_enrichment_scope_and_denominators(self) -> None:
        digest = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        enr = digest["fhsc_enrichment"]

        # Proves Layer 2 cannot be labeled FULL_RESEARCH_UNIVERSE
        self.assertEqual(enr["aggregate_scope"], "ACQUIRED_ENRICHMENT_COHORT")
        self.assertNotEqual(enr["aggregate_scope"], "FULL_RESEARCH_UNIVERSE")

        # Proves explicit coverage denominators
        trading_denom = enr["coverage_denominators"]["trading_composition"]
        self.assertEqual(trading_denom["universe_count"], 5)
        self.assertEqual(trading_denom["acquired_symbol_count"], 2)  # HPG and ACC
        self.assertEqual(trading_denom["coverage_ratio"], 0.4)
        self.assertEqual(trading_denom["requested_symbol_count"], 4)  # HPG, ACC, SSI, VCB
        self.assertEqual(trading_denom["affected_rate_limited_count"], 1)  # SSI

        # Proves cohort aggregates
        total_val = 1000000000000.0 + 2804408000.0
        self.assertEqual(enr["cohort_aggregates"]["total_acquired_traded_value_vnd"], total_val)

    def test_coverage_semantics_distinctions(self) -> None:
        digest = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        records_by_ticker = {r["ticker"]: r for r in digest["records"]}

        # 1. HPG and ACC are ACQUIRED
        hpg = records_by_ticker["HPG"]
        self.assertEqual(hpg["fhsc_value_volume_composition"]["status"], STATUS_ACQUIRED)
        acc = records_by_ticker["ACC"]
        self.assertEqual(acc["fhsc_value_volume_composition"]["status"], STATUS_ACQUIRED)

        # 2. AAA is NOT_ACQUIRED_IN_THIS_SCALEOUT (unattempted != missing)
        aaa = records_by_ticker["AAA"]
        self.assertEqual(aaa["fhsc_value_volume_composition"]["status"], STATUS_NOT_ACQUIRED)
        self.assertEqual(aaa["fhsc_value_volume_composition"]["usability_state"], "NOT_ACQUIRED")
        self.assertIn("TRADED_VALUE_AND_VOLUME_COMPOSITION", aaa["coverage_diagnostics"]["not_acquired_capabilities"])
        self.assertNotIn("TRADED_VALUE_AND_VOLUME_COMPOSITION", aaa["coverage_diagnostics"]["missing_requested_capabilities"])

        # 3. SSI is PROVIDER_RATE_LIMITED (rate-limited != unattempted)
        ssi = records_by_ticker["SSI"]
        self.assertEqual(ssi["fhsc_value_volume_composition"]["status"], STATUS_RATE_LIMITED)
        self.assertEqual(ssi["fhsc_value_volume_composition"]["usability_state"], "PROVIDER_RATE_LIMITED")
        self.assertIn("TRADED_VALUE_AND_VOLUME_COMPOSITION", ssi["coverage_diagnostics"]["rate_limited_capabilities"])

        # 4. VCB is MISSING_REQUESTED_SESSION (requested but missing)
        vcb = records_by_ticker["VCB"]
        self.assertEqual(vcb["fhsc_value_volume_composition"]["status"], STATUS_MISSING_SESSION)
        self.assertEqual(vcb["fhsc_value_volume_composition"]["usability_state"], "MISSING")
        self.assertIn("TRADED_VALUE_AND_VOLUME_COMPOSITION", vcb["coverage_diagnostics"]["missing_requested_capabilities"])

    def test_missing_values_do_not_become_zero(self) -> None:
        digest = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        records_by_ticker = {r["ticker"]: r for r in digest["records"]}

        # Unacquired symbol AAA must have None for values, NOT 0 or 0.0
        aaa_trading = records_by_ticker["AAA"]["fhsc_value_volume_composition"]
        self.assertIsNone(aaa_trading["matched_traded_value_vnd"])
        self.assertIsNone(aaa_trading["put_through_traded_value_vnd"])
        self.assertIsNone(aaa_trading["total_traded_value_vnd"])
        self.assertIsNone(aaa_trading["matched_value_ratio"])

        # Rate-limited symbol SSI must have None for values
        ssi_trading = records_by_ticker["SSI"]["fhsc_value_volume_composition"]
        self.assertIsNone(ssi_trading["matched_traded_value_vnd"])
        self.assertIsNone(ssi_trading["total_traded_value_vnd"])

    def test_queue_invariants_and_coverage_reconciliation(self) -> None:
        digest = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        queue_info = digest["next_acquisition_queue"]
        queued_tickers = [q["ticker"] for q in queue_info["queue_entries"]]
        records_by_ticker = {r["ticker"]: r for r in digest["records"]}

        acquired_tickers = {
            r["ticker"] for r in digest["records"]
            if r["fhsc_value_volume_composition"]["status"] == STATUS_ACQUIRED
        }
        self.assertEqual(acquired_tickers, {"HPG", "ACC"})

        # Invariant 1: acquired_symbols ∩ next_acquisition_queue == empty
        self.assertTrue(acquired_tickers.isdisjoint(set(queued_tickers)))
        self.assertNotIn("HPG", queued_tickers)
        self.assertNotIn("ACC", queued_tickers)

        # Invariant 2: Tier 1 contains retry-eligible rate-limited symbols only
        tier_1 = [q["ticker"] for q in queue_info["queue_entries"] if q["priority_tier"] == 1]
        self.assertEqual(tier_1, ["SSI"])

        # Invariant 3: Tier 2 contains unattempted / missing symbols only, disjoint from Tier 1 and acquired
        tier_2 = [q["ticker"] for q in queue_info["queue_entries"] if q["priority_tier"] == 2]
        self.assertEqual(set(tier_2), {"AAA", "VCB"})
        self.assertTrue(set(tier_1).isdisjoint(set(tier_2)))
        self.assertTrue(acquired_tickers.isdisjoint(set(tier_2)))

        # Invariant 4: Union count reconciliation: acquired (2) + tier_1 (1) + tier_2 (2) == universe (5)
        self.assertEqual(len(acquired_tickers) + len(tier_1) + len(tier_2), 5)
        self.assertEqual(len(queue_info["queue_entries"]), 3)
        self.assertEqual(queue_info["excluded_already_acquired_count"], 2)

        # Invariant 5: Decomposition table in coverage summary
        decomp = digest["coverage_summary"]["trading_history_scaleout_decomposition"]
        self.assertEqual(decomp["total_universe_count"], 5)
        self.assertEqual(decomp["acquired_count"], 2)
        self.assertEqual(decomp["rate_limited_count"], 1)
        self.assertEqual(decomp["missing_requested_session_count"], 1)
        self.assertEqual(decomp["unattempted_count"], 1)
        self.assertEqual(decomp["budget_exhausted_count"], 0)
        self.assertEqual(decomp["reconciled_sum"], 5)
        self.assertTrue(decomp["reconciliation_valid"])

    def test_deterministic_reproducibility(self) -> None:
        d1 = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        d2 = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        self.assertEqual(d1["digest_sha256"], d2["digest_sha256"])
        self.assertEqual(d1["digest_identity"], d2["digest_identity"])

    def test_markdown_summary_generation(self) -> None:
        digest = build_research_digest("2026-08-21", self.mock_snapshot, self.mock_packets)
        md = generate_markdown_summary(digest)
        self.assertIn("FULL_RESEARCH_UNIVERSE", md)
        self.assertIn("ACQUIRED_ENRICHMENT_COHORT", md)
        self.assertIn("Market-Wide Core Layer", md)
        self.assertIn("FHSC Enrichment Layer", md)
        self.assertIn("Next Acquisition Queue", md)
        # Verify acquired symbols are not listed in queue summary
        self.assertNotIn("ACC symbols", md)


if __name__ == "__main__":
    unittest.main()
