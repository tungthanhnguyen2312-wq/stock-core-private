"""Unit tests for P1 Multi-Session Cross-Sectional Research Export & Normalization."""

from __future__ import annotations

import copy
import json
import unittest

import pandas as pd

from cross_sectional_export import (
    CONTRACT_VERSION,
    MULTI_SESSION_EXPORT_ARTIFACT_TYPE,
    SCHEMA_VERSION,
    SESSION_EXPORT_ARTIFACT_TYPE,
    UNIVERSE_TYPE,
    CrossSectionalExportError,
    build_cross_sectional_session_export,
    build_multi_session_cross_sectional_export,
    compute_vectorized_market_features,
)
from field_temporal_contract import FreshnessState, PitStatus
from market_data_contracts import PriceBasis


class TestCrossSectionalExport(unittest.TestCase):

    def setUp(self):
        self.candidates = [
            {
                "candidate_id": "candidate:VCB",
                "instrument_identity_key": "id:VCB",
                "symbol": "VCB",
                "instrument_class": "EQUITY",
                "exchange": "HOSE",
                "listing_status": "unknown_not_provided_by_dataset",
            },
            {
                "candidate_id": "candidate:HPG",
                "instrument_identity_key": "id:HPG",
                "symbol": "HPG",
                "instrument_class": "EQUITY",
                "exchange": "HOSE",
                "listing_status": "unknown_not_provided_by_dataset",
            },
            {
                "candidate_id": "candidate:UNKNOWN_SEC",
                "instrument_identity_key": "id:UNKNOWN_SEC",
                "symbol": "UNK1",
                "instrument_class": "UNKNOWN_SECURITY_GROUP",
                "exchange": None,
                "listing_status": "unknown_not_provided_by_dataset",
            },
        ]

        # Multi-session market frame (2 sessions: 2026-08-10, 2026-08-11)
        self.market_frame = pd.DataFrame([
            {"ticker": "HPG", "date": "2026-08-05", "open": 28.0, "high": 28.5, "low": 27.8, "close": 28.2, "volume": 1000.0},
            {"ticker": "HPG", "date": "2026-08-06", "open": 28.2, "high": 28.8, "low": 28.0, "close": 28.5, "volume": 1100.0},
            {"ticker": "HPG", "date": "2026-08-07", "open": 28.5, "high": 29.0, "low": 28.2, "close": 28.9, "volume": 1200.0},
            {"ticker": "HPG", "date": "2026-08-10", "open": 29.0, "high": 29.5, "low": 28.8, "close": 29.2, "volume": 1300.0},
            {"ticker": "HPG", "date": "2026-08-11", "open": 29.2, "high": 30.0, "low": 29.0, "close": 29.8, "volume": 1500.0},
            # VCB present only on 2026-08-11 (missing on 2026-08-10)
            {"ticker": "VCB", "date": "2026-08-11", "open": 90.0, "high": 92.0, "low": 89.5, "close": 91.5, "volume": 800.0},
        ])

        # Foreign flows only for 2026-08-11
        self.foreign_frame = pd.DataFrame([
            {
                "ticker": "HPG",
                "date": "2026-08-11",
                "foreign_buy_value": 50000000.0,
                "foreign_sell_value": 20000000.0,
                "foreign_net_value": 30000000.0,
            }
        ])

    def test_clean_taxonomy_structure(self):
        """Verify foreign flows are under foreign_flow_features and NOT financial_statement_features."""
        session_export = build_cross_sectional_session_export(
            candidates=self.candidates,
            market_frame=self.market_frame,
            foreign_flows_frame=self.foreign_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
            knowledge_cutoff="2026-08-11T16:00:00+07:00",
        )

        hpg_rec = next(r for r in session_export["records"] if r["instrument_identity"]["symbol"] == "HPG")

        # Must have clean distinct categories
        self.assertIn("market_features", hpg_rec)
        self.assertIn("foreign_flow_features", hpg_rec)
        self.assertIn("financial_statement_features", hpg_rec)
        self.assertIn("corporate_action_features", hpg_rec)
        self.assertIn("qualification_and_capabilities", hpg_rec)

        # Foreign flows must be in foreign_flow_features
        self.assertEqual(hpg_rec["foreign_flow_features"]["dnse.foreign_net_value"], 30000000.0)

        # Financial statements must NOT contain foreign flows
        self.assertEqual(hpg_rec["financial_statement_features"], {})
        self.assertNotIn("dnse.foreign_net_value", hpg_rec["financial_statement_features"])

    def test_deterministic_session_ordering_and_hash(self):
        """Two independent runs must produce byte-identical content hashes and sorted candidate ordering."""
        e1 = build_cross_sectional_session_export(
            candidates=self.candidates,
            market_frame=self.market_frame,
            foreign_flows_frame=self.foreign_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
            generated_at="2026-08-19T12:00:00Z",
        )
        e2 = build_cross_sectional_session_export(
            candidates=list(reversed(self.candidates)),  # Reversed input order
            market_frame=self.market_frame,
            foreign_flows_frame=self.foreign_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
            generated_at="2026-08-19T12:00:00Z",
        )

        self.assertEqual(e1["content_hash"], e2["content_hash"])
        symbols_order = [r["instrument_identity"]["symbol"] for r in e1["records"]]
        self.assertEqual(symbols_order, ["HPG", "UNK1", "VCB"])

    def test_missing_observation_preservation_no_silent_forward_fill(self):
        """VCB on 2026-08-10 is missing and must remain missing (not forward-filled from future)."""
        export_0810 = build_cross_sectional_session_export(
            candidates=self.candidates,
            market_frame=self.market_frame,
            as_of_session="2026-08-10",
            reference_at="2026-08-10T16:00:00+07:00",
        )

        vcb_rec = next(r for r in export_0810["records"] if r["instrument_identity"]["symbol"] == "VCB")
        self.assertIsNone(vcb_rec["observed_at"])
        self.assertIsNone(vcb_rec["market_features"]["market.close"])
        self.assertEqual(vcb_rec["temporal_fields"]["market.close"]["freshness_status"], FreshnessState.MISSING.value)
        self.assertFalse(vcb_rec["qualification_and_capabilities"]["capability_flags"]["provider_scoped_analytics_eligible"])

    def test_lookahead_violation_rejection(self):
        """Requesting an as_of_session beyond reference_at must fail closed with lookahead error."""
        with self.assertRaises(CrossSectionalExportError) as ctx:
            build_cross_sectional_session_export(
                candidates=self.candidates,
                market_frame=self.market_frame,
                as_of_session="2026-08-15",
                reference_at="2026-08-11T16:00:00+07:00",
            )
        self.assertIn("lookahead_violation", str(ctx.exception))

    def test_fail_closed_governance_invariants(self):
        """Verify PIT gating, active universe fail-closed, and liquidity/sizing prohibitions."""
        export = build_cross_sectional_session_export(
            candidates=self.candidates,
            market_frame=self.market_frame,
            as_of_session="2026-08-11",
            reference_at="2026-08-11T16:00:00+07:00",
            price_basis=PriceBasis.ADJUSTED_RETROSPECTIVE,
        )

        hpg_rec = next(r for r in export["records"] if r["instrument_identity"]["symbol"] == "HPG")

        # Active universe must remain UNKNOWN
        self.assertEqual(hpg_rec["universe_tier_membership"]["active_universe"]["state"], "UNKNOWN")
        self.assertEqual(hpg_rec["universe_tier_membership"]["canonical_candidate_universe"]["state"], "INCLUDED")

        # Price field pit_eligible must be False for unpromoted price basis
        self.assertFalse(hpg_rec["temporal_fields"]["market.close"]["pit_eligible"])
        self.assertEqual(hpg_rec["temporal_fields"]["market.close"]["pit_status"], PitStatus.UNQUALIFIED_PRICE_BASIS.value)

        # Liquidity and sizing prohibited
        caps = hpg_rec["qualification_and_capabilities"]
        self.assertFalse(caps["capability_flags"]["market_liquidity_eligible"])
        self.assertFalse(caps["capability_flags"]["execution_sizing_eligible"])
        self.assertFalse(caps["capability_flags"]["market_wide_turnover_eligible"])
        self.assertEqual(caps["blocked_capabilities"]["market_liquidity"]["reason_code"], "LIQUIDITY_INPUTS_UNQUALIFIED")
        self.assertEqual(caps["blocked_capabilities"]["execution_sizing"]["reason_code"], "POSITION_SIZING_PROHIBITED")
        self.assertEqual(caps["blocked_capabilities"]["market_wide_turnover"]["reason_code"], "NO_MARKET_WIDE_TURNOVER_AUTHORITY")

    def test_multi_session_export_aggregation(self):
        """Verify multi-session export bundles session dates chronologically with stable hash."""
        multi_export = build_multi_session_cross_sectional_export(
            candidates=self.candidates,
            market_frame=self.market_frame,
            foreign_flows_frame=self.foreign_frame,
            session_dates=["2026-08-10", "2026-08-11"],
            reference_at="2026-08-11T16:00:00+07:00",
            generated_at="2026-08-19T14:00:00Z",
        )

        self.assertEqual(multi_export["artifact_type"], MULTI_SESSION_EXPORT_ARTIFACT_TYPE)
        self.assertEqual(multi_export["session_count"], 2)
        self.assertEqual(multi_export["session_dates"], ["2026-08-10", "2026-08-11"])
        self.assertEqual(multi_export["total_canonical_candidates"], 3)

        # 2026-08-10 has 1 observed (HPG), 2 missing
        self.assertEqual(multi_export["coverage_by_session"]["2026-08-10"]["observed_count"], 1)
        self.assertEqual(multi_export["coverage_by_session"]["2026-08-10"]["missing_count"], 2)

        # 2026-08-11 has 2 observed (HPG, VCB), 1 missing (UNK1)
        self.assertEqual(multi_export["coverage_by_session"]["2026-08-11"]["observed_count"], 2)
        self.assertEqual(multi_export["coverage_by_session"]["2026-08-11"]["missing_count"], 1)

        self.assertIn("content_hash", multi_export)
        self.assertTrue(multi_export["artifact_id"].startswith("multi-session-cross-sectional-export:2026-08-10_to_2026-08-11:"))


if __name__ == "__main__":
    unittest.main()
