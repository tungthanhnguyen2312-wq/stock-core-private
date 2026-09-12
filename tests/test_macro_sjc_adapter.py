"""Offline tests for macro_sjc_adapter.py -- the first-party SJC gold-price adapter that
replaces the vnstock wrapper (see docs/DECISIONS.md
MACRO_NETWORK_GOVERNANCE_AND_VNSTOCK_DECOUPLING_V1). No real network is used: `requests.post`
is monkeypatched with tiny fixtures shaped like SJC's real PriceService.ashx response.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import macro_sjc_adapter as adapter  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, raise_on_json=None):
        self.status_code = status_code
        self._json_data = json_data
        self._raise_on_json = raise_on_json

    def json(self):
        if self._raise_on_json is not None:
            raise self._raise_on_json
        return self._json_data


class SjcAdapterSuccessTests(unittest.TestCase):
    def test_prefers_ho_chi_minh_branch_row(self):
        payload = {
            "success": True,
            "data": [
                {"TypeName": "SJC", "BranchName": "Hà Nội", "BuyValue": "80000000", "SellValue": "82000000"},
                {"TypeName": "SJC", "BranchName": "Hồ Chí Minh", "BuyValue": "80100000", "SellValue": "82100000"},
            ],
        }
        with mock.patch.object(adapter.requests, "post", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.pairs, [("2026-09-10", 82100000.0)])

    def test_falls_back_to_first_row_when_no_hcm_branch_present(self):
        payload = {"success": True, "data": [{"BranchName": "Hà Nội", "SellValue": "82000000"}]}
        with mock.patch.object(adapter.requests, "post", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.pairs, [("2026-09-10", 82000000.0)])

    def test_uses_dd_mm_yyyy_date_in_request_body(self):
        payload = {"success": True, "data": [{"BranchName": "Hồ Chí Minh", "SellValue": "82000000"}]}
        captured = {}

        def fake_post(url, headers=None, data=None, timeout=None):
            captured["data"] = data
            return FakeResponse(200, payload)

        with mock.patch.object(adapter.requests, "post", side_effect=fake_post):
            adapter.fetch_sjc_gold_sell_price(date="2026-09-05")
        self.assertIn("toDate=05/09/2026", captured["data"])


class SjcAdapterFailureTests(unittest.TestCase):
    def test_timeout_is_classified_request_failed(self):
        with mock.patch.object(adapter.requests, "post", side_effect=requests.Timeout("timed out")):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10", timeout=5)
        self.assertEqual(result.status, "REQUEST_FAILED")
        self.assertEqual(result.reason, "TIMEOUT")
        self.assertEqual(result.pairs, [])

    def test_connection_error_is_classified_request_failed(self):
        with mock.patch.object(adapter.requests, "post", side_effect=requests.ConnectionError("dns fail")):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.status, "REQUEST_FAILED")

    def test_non_200_status_is_classified_request_failed(self):
        with mock.patch.object(adapter.requests, "post", return_value=FakeResponse(500, None)):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.status, "REQUEST_FAILED")
        self.assertEqual(result.reason, "HTTP_500")

    def test_malformed_json_is_classified_parse_failed(self):
        with mock.patch.object(
            adapter.requests, "post",
            return_value=FakeResponse(200, None, raise_on_json=ValueError("bad json")),
        ):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.status, "PARSE_FAILED")

    def test_success_false_is_classified_source_returned_no_value(self):
        with mock.patch.object(adapter.requests, "post", return_value=FakeResponse(200, {"success": False})):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.status, "SOURCE_RETURNED_NO_VALUE")
        self.assertEqual(result.reason, "SUCCESS_FALSE_OR_MALFORMED")

    def test_empty_data_list_is_classified_source_returned_no_value(self):
        with mock.patch.object(adapter.requests, "post", return_value=FakeResponse(200, {"success": True, "data": []})):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.status, "SOURCE_RETURNED_NO_VALUE")
        self.assertEqual(result.reason, "EMPTY_DATA_LIST")

    def test_non_numeric_sell_value_is_classified_parse_failed(self):
        payload = {"success": True, "data": [{"BranchName": "Hồ Chí Minh", "SellValue": "N/A"}]}
        with mock.patch.object(adapter.requests, "post", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_sjc_gold_sell_price(date="2026-09-10")
        self.assertEqual(result.status, "PARSE_FAILED")
        self.assertEqual(result.reason, "SELL_VALUE_NOT_NUMERIC")

    def test_invalid_date_format_is_rejected_before_any_request(self):
        with mock.patch.object(adapter.requests, "post") as post:
            result = adapter.fetch_sjc_gold_sell_price(date="10-09-2026")
        post.assert_not_called()
        self.assertEqual(result.status, "REQUEST_FAILED")
        self.assertEqual(result.reason, "INVALID_DATE_FORMAT")


if __name__ == "__main__":
    unittest.main()
