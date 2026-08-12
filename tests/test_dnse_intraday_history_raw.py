from __future__ import annotations

import unittest

import dnse_intraday_history_raw as contract


class IntradayHistoryContractTests(unittest.TestCase):
    def test_same_session_request_preserves_optional_scope_and_cursor(self):
        query = contract.request_query("trades_history", "2026-08-11", limit=20,
                                       cursor="cursor", board_id="G1")
        self.assertEqual({"from", "to", "limit", "order", "nextPageToken", "boardId"}, set(query))
        self.assertEqual("DESC", query["order"])
        self.assertLess(query["from"], query["to"])

    def test_envelopes_empty_and_nested_records_are_preserved(self):
        self.assertEqual([], contract.extract_records("trades_history", {"trades": []}))
        quote = {"bid": [{"price": 1, "quantity": 2}], "offer": []}
        self.assertEqual([quote], contract.extract_records("quotes_history", {"quotes": [quote]}))

    def test_malformed_envelope_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "quotes_field_not_a_list"):
            contract.extract_records("quotes_history", {"quotes": {}})

    def test_page_and_record_identities_include_content_and_page_context(self):
        query = contract.request_query("trades_history", "2026-08-11")
        page = contract.page_identity(dataset="trades_history", symbol="HPG", session_date="2026-08-11",
                                      query=query, cursor=None, body={"trades": [{"time": "t", "x": 1}]})
        a = contract.record_identity(dataset="trades_history", symbol="HPG", session_date="2026-08-11", page_id=page, record={"time": "t", "x": 1})
        b = contract.record_identity(dataset="trades_history", symbol="HPG", session_date="2026-08-11", page_id=page, record={"time": "t", "x": 2})
        self.assertNotEqual(a, b)

    def test_continuation_terminates_or_fails_closed(self):
        self.assertEqual("p2", contract.continuation_token(
            {"nextPageToken": "p2"}, seen_tokens={"p1"}, seen_pages={"page-1"}, page_id="page-2"))
        self.assertIsNone(contract.continuation_token({}, seen_tokens=set(), seen_pages=set(), page_id="p"))
        with self.assertRaisesRegex(ValueError, "repeated_next_page_token"):
            contract.continuation_token({"nextPageToken": "p2"}, seen_tokens={"p2"}, seen_pages=set(), page_id="p")
        with self.assertRaisesRegex(ValueError, "repeated_page_detected"):
            contract.continuation_token({"nextPageToken": "p2"}, seen_tokens=set(), seen_pages={"p"}, page_id="p")

    def test_observed_null_terminal_is_separate_from_defensive_states(self):
        self.assertEqual("NULL", contract.OBSERVED_PROVIDER_TERMINATION["trades_history"])
        self.assertEqual("NULL", contract.OBSERVED_PROVIDER_TERMINATION["quotes_history"])
        self.assertIn("FIELD_ABSENT", contract.DEFENSIVE_SUPPORTED_TERMINATION_STATES)

    def test_unsupported_dataset_order_and_token_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unsupported_intraday_history_dataset"):
            contract.request_query("not_a_dataset", "2026-08-11")
        with self.assertRaisesRegex(ValueError, "unsupported_order"):
            contract.request_query("quotes_history", "2026-08-11", order="RANDOM")
        with self.assertRaisesRegex(ValueError, "malformed_next_page_token"):
            contract.continuation_token({"nextPageToken": 2}, seen_tokens=set(), seen_pages=set(), page_id="p")


if __name__ == "__main__":
    unittest.main()
