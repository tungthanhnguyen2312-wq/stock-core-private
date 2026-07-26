import unittest

from corporate_actions import canonicalize_corporate_actions
from corporate_actions_export import build_corporate_actions_section


P = {"provider": "VCI", "vnstock_version": "4.0.4", "method": "events", "parameters": {}, "retrieved_at": "t"}
C = "partial_unqualified_50_row_cap"


class CorporateActionsTests(unittest.TestCase):
    def map(self, records): return canonicalize_corporate_actions(records, coverage_status=C, provenance=P)

    def test_cash_dividend_keeps_date_roles_null_and_zero(self):
        result = self.map([{"id":"d1", "event_code":"DIV", "event_name_en":"Cash Dividend", "value_per_share":0, "record_date":None, "exright_date":"2026-01-02", "payout_date":"2026-02-01"}])
        row = result["records"][0]
        self.assertEqual(row["cash_dividend_per_share"], 0)
        self.assertIsNone(row["date_roles"]["record_date"])
        self.assertEqual(row["date_roles"]["exright_date"], "2026-01-02")
        self.assertEqual(row["date_roles"]["payout_date"], "2026-02-01")
        self.assertIsNone(row["cash_dividend_currency"])

    def test_stock_and_rights_ratios_are_not_adjustments(self):
        rows = self.map([{"id":"s", "event_code":"ISS", "event_title_en":"Stock dividend ratio 10%", "exercise_ratio":0.1}, {"id":"r", "event_code":"ISS", "event_title_en":"Rights issue ratio 20%", "exercise_ratio":0.2}])["records"]
        self.assertEqual([row["action_type"] for row in rows], ["stock_dividend", "rights_issue"])
        self.assertEqual([row["issue_ratio"] for row in rows], [0.1, 0.2])
        self.assertTrue(all(row["adjustment_provenance"] == "unqualified_no_price_adjustment_claim" for row in rows))

    def test_duplicate_malformed_and_partial_coverage_fail_closed(self):
        self.assertEqual(self.map([{"id":"x"}, {"id":"x"}])["status"], "malformed")
        self.assertEqual(self.map([{"id":"x", "event_code":"DIV", "event_name_en":"Cash Dividend", "value_per_share":"bad"}])["status"], "malformed")
        self.assertEqual(canonicalize_corporate_actions([], coverage_status="complete", provenance=P)["status"], "unavailable")

    def test_action_type_and_repeated_export(self):
        events = {"status":"partial", "coverage_status":C, "sources":[{"source_name":"VCI", "coverage_status":C, "records":[{"provider_event_id":"d", "fields":{"event_code":"DIV", "event_name_en":"Cash Dividend", "value_per_share":500, "action_type_vi":"Mua", "action_type_en":"Buy"}}]}]}
        one = build_corporate_actions_section(events)
        self.assertEqual(one, build_corporate_actions_section(events))
        row = one["sources"][0]["records"][0]
        self.assertEqual(row["source_fields"]["action_type_en"], "Buy")

    def test_legacy_missing_events_stays_missing(self):
        self.assertEqual(build_corporate_actions_section({"status":"missing", "reason":"none"})["status"], "missing")


if __name__ == "__main__":
    unittest.main()
