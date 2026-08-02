from __future__ import annotations

import unittest

from share_transition_bridge import resolve_share_transition


def opening(**more):
    return {"value": 100, "effective_date": "2024-12-31", "unit": "shares",
            "share_class": "common_outstanding", "qualification": "qualified",
            "identity_scope": "issuer",
            "source_hash": "opening-hash", "citation_id": "opening-citation"} | more


def event(event_id="e1", **more):
    return {"event_id": event_id, "action_type": "stock_dividend", "lifecycle": "completed",
            "effective_date": "2025-07-01", "opening_shares": 100, "resulting_shares": 120,
            "resulting_identity_type": "common_outstanding_shares", "unit": "shares",
            "identity_scope": "issuer",
            "ratio": 0.2, "qualification": "qualified", "source_hash": "event-hash",
            "citation_id": "event-citation"} | more


class ShareTransitionBridgeTests(unittest.TestCase):
    def resolve(self, events, coverage="2026-07-30"):
        return resolve_share_transition(opening(), events, target_date="2026-07-30", coverage_through=coverage)

    def test_completed_transition_with_coverage_qualifies_current(self):
        result = self.resolve([event()])
        self.assertEqual("current_qualified", result["status"])
        self.assertEqual(120, result["current_shares"]["value"])
        self.assertFalse(result["market_value_ready"])

    def test_cash_dividend_leaves_shares_unchanged(self):
        cash = event(action_type="cash_dividend", lifecycle="completed", resulting_shares=100, share_delta=0)
        result = self.resolve([cash])
        self.assertEqual(100, result["latest_qualified_identity"]["value"])

    def test_announcement_without_completion_is_blocked(self):
        result = self.resolve([event(lifecycle="announced")])
        self.assertEqual("latest_historical_only", result["status"])
        self.assertEqual("share_action_completion_unqualified", result["blocked_events"][0]["reason"])

    def test_missing_effective_date_is_blocked(self):
        result = self.resolve([event(effective_date=None)])
        self.assertEqual("event_effective_date_invalid", result["blocked_events"][0]["reason"])

    def test_missing_opening_effective_date_is_blocked(self):
        result = resolve_share_transition(opening(effective_date=None), [],
                                          target_date="2026-07-30", coverage_through="2026-07-30")
        self.assertEqual("opening_effective_date_invalid", result["current_shares"]["reason"])

    def test_conflicting_duplicate_event_is_blocked(self):
        result = self.resolve([event(), event(resulting_shares=121, ratio=0.21)])
        self.assertIn("conflicting_duplicate_event", [item["reason"] for item in result["blocked_events"]])
        self.assertEqual([], result["applied_events"])
        self.assertEqual(100, result["latest_qualified_identity"]["value"])

    def test_ordered_multiple_actions_are_deterministic(self):
        later = event("e2", effective_date="2026-07-02", opening_shares=120, resulting_shares=132,
                      ratio=0.1, citation_id="c2", source_hash="h2")
        first = self.resolve([later, event()])
        second = self.resolve([event(), later])
        self.assertEqual(first, second)
        self.assertEqual(["e1", "e2"], [item["event_id"] for item in first["applied_events"]])
        self.assertEqual(132, first["current_shares"]["value"])

    def test_direct_result_required_instead_of_ratio_arithmetic(self):
        result = self.resolve([event(resulting_shares=None)])
        self.assertEqual("direct_resulting_share_identity_missing", result["blocked_events"][0]["reason"])

    def test_opening_identity_and_treasury_basis_fail_closed(self):
        result = resolve_share_transition(opening(share_class="issued_unknown_treasury"), [],
                                          target_date="2026-07-30", coverage_through="2026-07-30")
        self.assertEqual("opening_identity_unqualified", result["current_shares"]["reason"])

    def test_listed_shares_cannot_be_promoted_to_outstanding(self):
        result = self.resolve([event(resulting_identity_type="listed_shares")])
        self.assertEqual("resulting_share_identity_unqualified", result["blocked_events"][0]["reason"])

    def test_event_unit_or_scope_mismatch_fails_closed(self):
        for mismatch in ({"unit": "lots"}, {"identity_scope": "consolidated_group"}):
            with self.subTest(mismatch=mismatch):
                result = self.resolve([event(**mismatch)])
                self.assertEqual("resulting_share_identity_unqualified", result["blocked_events"][0]["reason"])

    def test_scope_stays_historical_when_coverage_stops_before_target(self):
        result = self.resolve([event()], coverage="2026-06-30")
        self.assertEqual("latest_historical_only", result["status"])
        self.assertEqual(120, result["latest_qualified_identity"]["value"])
        self.assertIsNone(result["current_shares"]["value"])
        self.assertEqual("coverage_through_target_not_proven", result["current_shares"]["reason"])

    def test_opening_share_conflict_blocks_chain(self):
        result = self.resolve([event(opening_shares=99)])
        self.assertEqual("event_opening_share_conflict", result["blocked_events"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
