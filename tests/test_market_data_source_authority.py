from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import market_data_source_authority as authority  # noqa: E402


class SourceAuthorityDecisionTests(unittest.TestCase):
    def test_exactly_three_bounded_candidates_and_no_active_paid_source(self):
        self.assertEqual(len(authority.CANDIDATES), 3)
        snap = authority.decision_snapshot()
        self.assertIsNone(snap["selected_source_id"])
        self.assertFalse(snap["raw_price_authority_source_selected"])
        self.assertEqual(snap["next_roadmap_milestone"], authority.NEXT_PILLAR_B_MILESTONE)

    def test_existing_adjusted_paths_cannot_win_raw_authority(self):
        existing = authority.candidate("existing_integrated_vci_kbs_provider_paths")
        self.assertEqual(existing["requirements"]["raw_as_traded_price"], authority.STATUS_REJECTED)
        self.assertNotEqual(existing["candidate_id"], authority.FIINGROUP_CANDIDATE_ID)

    def test_commercial_documentation_does_not_open_a_gate(self):
        snap = authority.decision_snapshot()
        self.assertEqual(snap["raw_price_authority"], "PARTIAL")
        self.assertEqual(snap["volume_scope_authority"], "BLOCKED")
        self.assertEqual(snap["historical_valuation_unlock"], "BLOCKED")
        self.assertFalse(snap["network_or_credentials_used"])

    def test_minimum_package_preserves_raw_adjusted_and_volume_namespaces(self):
        package = authority.UNAPPROVED_COMMERCIAL_CANDIDATE_REVIEW
        self.assertIn("ClosePrice", package["minimum_data_package"]["price_fields"])
        self.assertIn("ClosePriceAdjusted", package["minimum_data_package"]["raw_adjusted_fields"])
        self.assertIn("TotalDealVolume", package["minimum_data_package"]["volume_fields"])
        self.assertIn("odd-lot", " ".join(package["contractual_confirmations_required"]).lower())

    def test_policy_refuses_implicit_commercial_promotion(self):
        authority.assert_decision_policy()
        snap = authority.decision_snapshot()
        snap["raw_price_authority"] = "QUALIFIED"
        with self.assertRaisesRegex(ValueError, "unqualified_commercial_source"):
            authority.assert_decision_policy(snap)

    def test_absent_access_blocks_the_pilot_without_reading_a_secret(self):
        snap = authority.access_snapshot()
        self.assertEqual(snap["fiingroup_access_state"], "NOT_OWNER_AUTHORIZED_NO_CONFIGURED_ACCESS")
        self.assertEqual(snap["license_authority"], "NO_LEGITIMATE_ACCESS_OR_CONTRACTUAL_RIGHTS")
        self.assertEqual(snap["fiingroup_raw_price_pilot"], "NOT_AUTHORIZED_NOT_EXECUTED")
        self.assertFalse(snap["access_audit"]["credentials_read_or_logged"])
        authority.assert_access_policy()

    def test_acquisition_package_requests_only_hose_daily_history_fields(self):
        package = authority.UNAPPROVED_COMMERCIAL_CANDIDATE_REVIEW["minimum_data_package"]
        self.assertEqual(package["endpoint"], "/Market/GetHoseStockv2")
        self.assertEqual(package["companion_endpoints"], [])
        self.assertIn("Ticker", package["identity_fields"])
        self.assertNotIn("fundamentals", str(package).lower())

    def test_dnse_contract_records_enabled_foreign_flow_and_remaining_fail_closed_gaps(self):
        snap = authority.access_snapshot()
        self.assertEqual(snap["dnse_market_data_access"], "PARTIALLY_QUALIFIED_EXISTING_DNSE_CONTRACT")
        route = snap["dnse_next_qualification_route"]
        self.assertFalse(route["network_called"])
        self.assertFalse(route["credentials_read_or_logged"])
        self.assertEqual(route["market_basis_effect"], "none_until_retained_qualification_pilot_passes")
        self.assertEqual(route["foreign_flow_value_authority"], "PRODUCTION_ENABLED_HPG_VNM_QNS")
        self.assertEqual(route["ohlc_price_basis"], "ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME")
        self.assertEqual(route["market_volume_basis"], "UNQUALIFIED_BACKLOG")
        self.assertIsNone(snap["fiingroup_fallback_candidate"])


if __name__ == "__main__":
    unittest.main()
