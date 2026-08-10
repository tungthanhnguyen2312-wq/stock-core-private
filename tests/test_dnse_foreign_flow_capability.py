from __future__ import annotations

import json
import unittest

from dnse_foreign_flow_capability import (
    PARTIALLY_QUALIFIED,
    DnseForeignFlowError,
    active_capability_contract,
    assert_fail_closed,
    assert_point_in_time_consistency,
    assert_same_scope,
    derive_net,
    normalize_record,
    normalize_response,
    serialize,
)

# Shape-matched sample from retained evidence (HPG, 2026-08-07 past-session
# pit probe) -- real field names, realistic values.
HPG_PAST_SESSION_RECORD = {
    "boardId": "G1",
    "buyTradedAmount": 47905130000,
    "buyVolume": 2173700,
    "foreignerBuyPossibleQuantity": 3727215320,
    "foreignerOrderLimitQuantity": 3478309257,
    "marketId": "STO",
    "sellTradedAmount": 20343240000,
    "sellVolume": 920600,
    "symbol": "HPG",
    "time": "2026-08-07 15:33:11.407",
    "totalBuyTradedAmount": 47907362050,
    "totalBuyVolume": 2173801,
    "totalSellTradedAmount": 20350730400,
    "totalSellVolume": 920939,
    "tradingSessionId": "99",
}

TODAY_RECORD = dict(HPG_PAST_SESSION_RECORD, time="2026-08-10 10:52:10.215", tradingSessionId="40")


class NormalizeRecordTests(unittest.TestCase):
    def test_valid_buy_sell_fields_normalized(self):
        result = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        self.assertEqual("HPG", result["ticker"])
        self.assertEqual("2026-08-07", result["session_date"])
        self.assertEqual(2173801, result["foreign_buy_volume"])
        self.assertEqual(920939, result["foreign_sell_volume"])
        self.assertEqual(47907362050, result["foreign_buy_value"])
        self.assertEqual(20350730400, result["foreign_sell_value"])

    def test_net_derived_only_from_compatible_qualified_inputs(self):
        self.assertEqual(2173801 - 920939, derive_net(2173801, 920939))
        result = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        self.assertEqual(result["foreign_buy_volume"] - result["foreign_sell_volume"],
                          result["foreign_net_volume"])
        self.assertEqual(result["foreign_buy_value"] - result["foreign_sell_value"],
                          result["foreign_net_value"])

    def test_mismatched_date_session_rejected(self):
        past = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        today = normalize_record(TODAY_RECORD, source_endpoint="/price/HPG/foreign-trading")
        with self.assertRaises(DnseForeignFlowError) as caught:
            assert_same_scope(past, today)
        self.assertEqual("scope_mismatch_session_date", str(caught.exception))

    def test_unknown_unit_blocks_affected_metrics(self):
        # volume_unit is UNQUALIFIED (plausible shares, not proven) per the
        # module's own dimension table -- the field still normalizes (display
        # is not blocked), but the qualification status must never claim a
        # fully-qualified single-bucket result while that gap exists.
        result = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        self.assertEqual(PARTIALLY_QUALIFIED, result["qualification_status"])
        self.assertNotIn(result["qualification_status"], {"QUALIFIED_EOD_FLOW"})

    def test_room_field_remains_separate_from_flow(self):
        result = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        self.assertIn("foreign_room", result)
        self.assertNotIn("foreign_room", {"foreign_buy_volume", "foreign_sell_volume"})
        self.assertFalse(result["foreign_room"]["relationship_qualified"])
        self.assertEqual(3727215320, result["foreign_room"]["buy_possible_quantity"])

    def test_missing_side_does_not_fabricate_net(self):
        one_sided = dict(HPG_PAST_SESSION_RECORD)
        del one_sided["totalSellVolume"]
        result = normalize_record(one_sided, source_endpoint="/price/HPG/foreign-trading")
        self.assertIsNone(result["foreign_sell_volume"])
        self.assertIsNone(result["foreign_net_volume"])  # never a fabricated buy-0 result

    def test_provenance_retained(self):
        result = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading",
                                   query_window={"from": 1786035600, "to": 1786121999})
        self.assertEqual("/price/HPG/foreign-trading", result["provenance"]["source_endpoint"])
        self.assertEqual("99", result["provenance"]["trading_session_id"])
        self.assertEqual({"from": 1786035600, "to": 1786121999}, result["provenance"]["query_window"])
        self.assertEqual(2173700, result["provenance"]["event_scoped"]["buy_volume"])

    def test_deterministic_serialization(self):
        first = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        second = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        self.assertEqual(serialize(first), serialize(second))

    def test_malformed_amount_fails_closed(self):
        for field in ("totalBuyVolume", "totalSellTradedAmount", "buyVolume"):
            with self.subTest(field=field):
                with self.assertRaises(DnseForeignFlowError):
                    normalize_record(dict(HPG_PAST_SESSION_RECORD, **{field: -1}),
                                      source_endpoint="/price/HPG/foreign-trading")

    def test_point_in_time_consistency_check(self):
        past = normalize_record(HPG_PAST_SESSION_RECORD, source_endpoint="/price/HPG/foreign-trading")
        with self.assertRaises(DnseForeignFlowError):
            assert_point_in_time_consistency(requested_session_date="2026-08-07",
                                              observations=[normalize_record(TODAY_RECORD, source_endpoint="x")])
        assert_point_in_time_consistency(requested_session_date="2026-08-07", observations=[past])


class CapabilityContractTests(unittest.TestCase):
    def test_active_contract_is_internally_consistent_and_serializable(self):
        contract = active_capability_contract()
        self.assertEqual(PARTIALLY_QUALIFIED, contract["formal_result"])
        self.assertEqual(10, len(contract["dimensions"]))
        json.dumps(contract)  # must not raise

    def test_invalid_formal_result_rejected(self):
        with self.assertRaises(DnseForeignFlowError):
            assert_fail_closed("MADE_UP_STATUS")


if __name__ == "__main__":
    unittest.main()
