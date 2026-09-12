"""Offline tests for macro_vcb_adapter.py -- the first-party Vietcombank exchange-rate
adapter that replaces the vnstock wrapper (see docs/DECISIONS.md
MACRO_NETWORK_GOVERNANCE_AND_VNSTOCK_DECOUPLING_V1). No real network is used: `requests.get`
is monkeypatched with tiny fixtures shaped like Vietcombank's real export-excel response.
"""
from __future__ import annotations

import base64
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import macro_vcb_adapter as adapter  # noqa: E402


def _make_workbook_bytes(rows):
    """rows: list of (currency_code, currency_name, buy_cash, buy_transfer, sell) tuples,
    NOT including the header/footer rows the real export always carries -- those are
    prepended/appended here to match the real sheet shape the adapter expects: one row
    consumed as the pandas column header by ``pd.read_excel``'s default header=0 (written with
    ``header=False`` below so it lands as an ordinary data row first), then 2 more header rows
    and 4 footer rows stripped by the adapter's own ``iloc[2:-4]``."""
    # openpyxl trims trailing/interior rows written as all-empty-string, collapsing the
    # intended row count -- non-empty placeholder text keeps every row real and positioned.
    header_rows = [
        ("h0", "h0", "h0", "h0", "h0"),  # consumed as the pandas column header (header=0 default)
        ("h1", "h1", "h1", "h1", "h1"),
        ("Code", "Name", "Buy Cash", "Buy Transfer", "Sell"),
    ]
    footer_rows = [("f0", "f0", "f0", "f0", "f0")] * 4
    frame = pd.DataFrame(header_rows + list(rows) + footer_rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="ExchangeRate", index=False, header=False)
    return buf.getvalue()


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class VcbAdapterSuccessTests(unittest.TestCase):
    def test_parses_usd_sell_rate_from_fixture_workbook(self):
        workbook = _make_workbook_bytes([("USD", "US DOLLAR", "26,300.00", "26,330.00", "26,690.00")])
        payload = {"Data": base64.b64encode(workbook).decode("ascii")}
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "OK")
        self.assertIsNone(result.reason)
        self.assertEqual(result.pairs, [("2026-09-10", 26690.00)])

    def test_strips_thousands_separators_from_sell_value(self):
        workbook = _make_workbook_bytes([("USD", "US DOLLAR", "1", "1", "26,471")])
        payload = {"Data": base64.b64encode(workbook).decode("ascii")}
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.pairs, [("2026-09-10", 26471.0)])

    def test_default_date_is_todays_local_date_when_omitted(self):
        from datetime import datetime
        workbook = _make_workbook_bytes([("USD", "US DOLLAR", "1", "1", "26,000")])
        payload = {"Data": base64.b64encode(workbook).decode("ascii")}
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_vcb_usd_sell_rate()
        self.assertEqual(result.pairs[0][0], datetime.now().strftime("%Y-%m-%d"))


class VcbAdapterFailureTests(unittest.TestCase):
    def test_timeout_is_classified_request_failed(self):
        with mock.patch.object(adapter.requests, "get", side_effect=requests.Timeout("timed out")):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10", timeout=5)
        self.assertEqual(result.status, "REQUEST_FAILED")
        self.assertEqual(result.reason, "TIMEOUT")
        self.assertEqual(result.pairs, [])

    def test_connection_error_is_classified_request_failed(self):
        with mock.patch.object(adapter.requests, "get", side_effect=requests.ConnectionError("dns fail")):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "REQUEST_FAILED")
        self.assertEqual(result.pairs, [])

    def test_non_200_status_is_classified_request_failed(self):
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(503, None)):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "REQUEST_FAILED")
        self.assertEqual(result.reason, "HTTP_503")

    def test_malformed_json_is_classified_parse_failed(self):
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, {"unexpected": "shape"})):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "PARSE_FAILED")

    def test_corrupt_base64_payload_is_classified_parse_failed(self):
        payload = {"Data": "not-valid-base64!!"}
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "PARSE_FAILED")

    def test_missing_usd_row_is_classified_source_returned_no_value(self):
        workbook = _make_workbook_bytes([("EUR", "EURO", "1", "1", "28,000.00")])
        payload = {"Data": base64.b64encode(workbook).decode("ascii")}
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "SOURCE_RETURNED_NO_VALUE")
        self.assertEqual(result.reason, "USD_ROW_ABSENT")

    def test_non_numeric_sell_value_is_classified_parse_failed(self):
        workbook = _make_workbook_bytes([("USD", "US DOLLAR", "1", "1", "not_a_number")])
        payload = {"Data": base64.b64encode(workbook).decode("ascii")}
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "PARSE_FAILED")
        self.assertEqual(result.reason, "SELL_VALUE_NOT_NUMERIC")

    def test_na_like_sell_cell_is_not_fabricated_as_a_value(self):
        # pandas' Excel reader silently parses tokens like "N/A" to NaN; that must never be
        # reported as a successfully parsed value (float("nan") does not raise).
        workbook = _make_workbook_bytes([("USD", "US DOLLAR", "1", "1", "N/A")])
        payload = {"Data": base64.b64encode(workbook).decode("ascii")}
        with mock.patch.object(adapter.requests, "get", return_value=FakeResponse(200, payload)):
            result = adapter.fetch_vcb_usd_sell_rate(date="2026-09-10")
        self.assertEqual(result.status, "SOURCE_RETURNED_NO_VALUE")
        self.assertEqual(result.reason, "SELL_CELL_EMPTY_OR_NA")
        self.assertEqual(result.pairs, [])


if __name__ == "__main__":
    unittest.main()
