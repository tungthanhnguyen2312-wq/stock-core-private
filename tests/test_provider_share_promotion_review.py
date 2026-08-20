"""P3-F5 review-policy contracts; no production authority is activated."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import provider_share_promotion_review as review  # noqa: E402


class ProviderSharePromotionReviewTests(unittest.TestCase):
    def test_issued_field_cannot_masquerade_as_current_common_even_when_equal(self):
        result = review.classify_official_comparison(
            {"identity": "ISSUED_SHARES", "value": 100, "observed_on": "2026-08-14"},
            {"identity": "common_shares_outstanding", "value": 100, "effective_on": "2026-08-14"},
        )
        self.assertEqual("SEMANTICALLY_COMPATIBLE_DIFFERENT_SCOPE", result)

    def test_value_date_and_corporate_action_cases_remain_distinct(self):
        provider = {"identity": "ISSUED_SHARES", "value": 100, "observed_on": "2026-08-14"}
        self.assertEqual("VALUE_DIFFERENCE", review.classify_official_comparison(provider, {"identity": "period_end_shares", "value": 99, "effective_on": "2024-12-31"}))
        self.assertEqual("CORPORATE_ACTION_AMBIGUOUS", review.classify_official_comparison(provider, None, corporate_action_ambiguous=True))

    def test_freshness_and_proxy_projection_fail_closed(self):
        self.assertEqual("PROVIDER_REPORTED_STALE", review.provider_freshness_state({"authority": "provider_reported_lagged"}))
        projection = review.projected_provider_proxy_coverage([
            {"provider_value": 100, "resolver_authority": "provider_reported_lagged"},
            {"provider_value": 100, "resolver_authority": "provider_reported_unverifiable_freshness"},
        ])
        self.assertEqual(0, projection["authoritative_share_ready"])
        self.assertEqual(1, projection["hypothetical_provider_proxy_share_observations"])

    def test_mva_namespace_and_authority_state_are_explicit(self):
        self.assertEqual("AUTHORITY_NOT_PROMOTED_PENDING_OWNER_DECISION", review.AUTHORITY_STATE)
        self.assertFalse(review.MVA_ENVELOPE["is_actionable_for_execution"])
        self.assertEqual("CURRENT_DESCRIPTIVE_ONLY", review.MVA_ENVELOPE["valuation_scope"])


if __name__ == "__main__":
    unittest.main()
