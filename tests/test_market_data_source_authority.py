from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import market_data_source_authority as authority  # noqa: E402


class SourceAuthorityDecisionTests(unittest.TestCase):
    def test_exactly_three_bounded_candidates_and_one_preferred(self):
        self.assertEqual(len(authority.CANDIDATES), 3)
        snap = authority.decision_snapshot()
        self.assertEqual(snap["selected_source_id"], authority.PREFERRED_SOURCE_ID)
        self.assertTrue(snap["raw_price_authority_source_selected"])

    def test_existing_adjusted_paths_cannot_win_raw_authority(self):
        existing = authority.candidate("existing_integrated_vci_kbs_provider_paths")
        self.assertEqual(existing["requirements"]["raw_as_traded_price"], authority.STATUS_REJECTED)
        self.assertNotEqual(existing["candidate_id"], authority.PREFERRED_SOURCE_ID)

    def test_commercial_documentation_does_not_open_a_gate(self):
        snap = authority.decision_snapshot()
        self.assertEqual(snap["raw_price_authority"], "PARTIAL")
        self.assertEqual(snap["volume_scope_authority"], "BLOCKED")
        self.assertEqual(snap["historical_valuation_unlock"], "BLOCKED")
        self.assertFalse(snap["network_or_credentials_used"])

    def test_minimum_package_preserves_raw_adjusted_and_volume_namespaces(self):
        package = authority.OWNER_ACQUISITION_PACKAGE
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
        self.assertEqual(snap["fiingroup_access_state"], "OWNER_ACQUISITION_REQUIRED")
        self.assertEqual(snap["license_authority"], "OWNER_CONFIRMATION_REQUIRED")
        self.assertEqual(snap["fiingroup_raw_price_pilot"], "BLOCKED_EXTERNAL_ACCESS")
        self.assertFalse(snap["access_audit"]["credentials_read_or_logged"])
        authority.assert_access_policy()

    def test_acquisition_package_requests_only_hose_daily_history_fields(self):
        package = authority.OWNER_ACQUISITION_PACKAGE["minimum_data_package"]
        self.assertEqual(package["endpoint"], "/Market/GetHoseStockv2")
        self.assertEqual(package["companion_endpoints"], [])
        self.assertIn("Ticker", package["identity_fields"])
        self.assertNotIn("fundamentals", str(package).lower())

    def test_dnse_route_is_pending_and_does_not_change_any_gate(self):
        snap = authority.access_snapshot()
        self.assertEqual(snap["dnse_market_data_access"], "PENDING_OWNER_ACCOUNT_ACTIVATION")
        route = snap["dnse_next_qualification_route"]
        self.assertFalse(route["network_called"])
        self.assertFalse(route["credentials_read_or_logged"])
        self.assertEqual(route["market_basis_effect"], "none_until_retained_qualification_pilot_passes")
        self.assertEqual(snap["fiingroup_fallback_candidate"], authority.PREFERRED_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
