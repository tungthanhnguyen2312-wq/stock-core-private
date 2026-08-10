from __future__ import annotations

import json
import unittest

from dnse_bid_ask_capability import (
    DISPLAY_ONLY,
    LIQUIDITY_ANALYTICS,
    QUANTITY_UNIT_QUALIFIED,
    DnseBidAskError,
    active_capability_contract,
    assert_fail_closed,
    assert_point_in_time_consistency,
    normalize_response,
    normalize_snapshot,
    serialize,
)

# A shape-matched, already-sanitized sample from the retained evidence
# (operations-review/dnse-market-data-qualification-20260810/probe_results.json,
# HPG G1 board) -- real field names and realistic values, not fabricated.
HPG_G1_SNAPSHOT = {
    "bid": [{"price": 22.05, "quantity": 12210}, {"price": 22, "quantity": 53930}],
    "boardId": "G1",
    "isin": "VN000000HPG4",
    "marketId": "STO",
    "offer": [{"price": 22.1, "quantity": 16850}, {"price": 22.15, "quantity": 29880}],
    "symbol": "HPG",
    "time": "2026-08-10 10:47:26.663",
    "totalBidQtty": 0,
    "totalOfferQtty": 0,
}

PAST_SESSION_SNAPSHOT = {
    "bid": [{"price": 22, "quantity": 11200}],
    "boardId": "G1",
    "isin": "VN000000HPG4",
    "marketId": "STO",
    "offer": [{"price": 22.05, "quantity": 2070}],
    "symbol": "HPG",
    "time": "2026-08-07 14:45:02.851",
}

EMPTY_BOARD_RESPONSE = {"quotes": []}  # HPG boardId=T1, directly observed 2026-08-10


class NormalizeSnapshotTests(unittest.TestCase):
    def test_valid_snapshot_normalized_deterministically(self):
        first = normalize_snapshot(HPG_G1_SNAPSHOT, source_endpoint="/price/HPG/quotes/latest")
        second = normalize_snapshot(HPG_G1_SNAPSHOT, source_endpoint="/price/HPG/quotes/latest")
        self.assertEqual(serialize(first), serialize(second))
        self.assertEqual("HPG", first["ticker"])
        self.assertEqual("G1", first["board_id"])
        self.assertEqual("2026-08-10", first["session_date"])

    def test_level_ordering_preserved(self):
        result = normalize_snapshot(HPG_G1_SNAPSHOT, source_endpoint="/price/HPG/quotes/latest")
        self.assertEqual([1, 2], [level["level"] for level in result["bid_levels"]])
        self.assertEqual(22.05, result["bid_levels"][0]["price"])
        self.assertEqual(22.1, result["ask_levels"][0]["price"])

    def test_bid_ask_never_inverted(self):
        crossed = dict(HPG_G1_SNAPSHOT, bid=[{"price": 23.0, "quantity": 10}],
                        offer=[{"price": 22.0, "quantity": 10}])
        with self.assertRaises(DnseBidAskError) as caught:
            normalize_snapshot(crossed, source_endpoint="/price/HPG/quotes/latest")
        self.assertEqual("bid_ask_inverted_or_crossed", str(caught.exception))

    def test_timestamps_and_session_preserved(self):
        result = normalize_snapshot(PAST_SESSION_SNAPSHOT, source_endpoint="/price/HPG/quotes")
        self.assertEqual("2026-08-07 14:45:02.851", result["observed_at"])
        self.assertEqual("2026-08-07", result["session_date"])

    def test_missing_quantity_unit_authority_blocks_liquidity_analytics(self):
        self.assertFalse(QUANTITY_UNIT_QUALIFIED)
        result = normalize_snapshot(HPG_G1_SNAPSHOT, source_endpoint="/price/HPG/quotes/latest")
        self.assertEqual(DISPLAY_ONLY, result["qualification_status"])
        self.assertNotEqual(LIQUIDITY_ANALYTICS, result["qualification_status"])
        with self.assertRaises(DnseBidAskError):
            assert_fail_closed(LIQUIDITY_ANALYTICS)

    def test_malformed_depth_fails_closed(self):
        cases = [
            dict(HPG_G1_SNAPSHOT, bid=[{"price": -1, "quantity": 10}]),
            dict(HPG_G1_SNAPSHOT, bid=[{"price": 22, "quantity": -5}]),
            dict(HPG_G1_SNAPSHOT, bid="not-a-list"),
            {**HPG_G1_SNAPSHOT, "symbol": None},
            {**HPG_G1_SNAPSHOT, "boardId": ""},
            {**HPG_G1_SNAPSHOT, "time": None},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(DnseBidAskError):
                    normalize_snapshot(payload, source_endpoint="/price/HPG/quotes/latest")

    def test_empty_book_represented_honestly(self):
        result = normalize_response(EMPTY_BOARD_RESPONSE, source_endpoint="/price/HPG/quotes/latest")
        self.assertEqual([], result)  # empty, not an error, not fabricated levels

    def test_historical_and_current_snapshots_cannot_be_silently_mixed(self):
        current = normalize_snapshot(HPG_G1_SNAPSHOT, source_endpoint="/price/HPG/quotes/latest")
        past = normalize_snapshot(PAST_SESSION_SNAPSHOT, source_endpoint="/price/HPG/quotes")
        with self.assertRaises(DnseBidAskError):
            assert_point_in_time_consistency(
                requested_session_date="2026-08-07", observations=[current, past]
            )
        assert_point_in_time_consistency(requested_session_date="2026-08-07", observations=[past])

    def test_provenance_retained_and_no_unexpected_keys_leak(self):
        poisoned = dict(HPG_G1_SNAPSHOT, headers={"Authorization": "Bearer x"}, apiKey="should-not-leak")
        result = normalize_snapshot(poisoned, source_endpoint="/price/HPG/quotes/latest",
                                     query_window={"from": 1, "to": 2})
        self.assertEqual("/price/HPG/quotes/latest", result["provenance"]["source_endpoint"])
        self.assertEqual({"from": 1, "to": 2}, result["provenance"]["query_window"])
        dumped = json.dumps(result)
        self.assertNotIn("Authorization", dumped)
        self.assertNotIn("should-not-leak", dumped)


class CapabilityContractTests(unittest.TestCase):
    def test_active_contract_is_internally_consistent_and_serializable(self):
        contract = active_capability_contract()
        self.assertEqual(DISPLAY_ONLY, contract["formal_result"])
        self.assertEqual(17, len(contract["dimensions"]))
        json.dumps(contract)  # must not raise


if __name__ == "__main__":
    unittest.main()
