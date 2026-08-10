from __future__ import annotations

import inspect
import json
import unittest

import dnse_bid_ask_capability as bid_ask
import dnse_foreign_flow_capability as foreign_flow

RAW_QUOTE_WITH_ROGUE_FIELDS = {
    "bid": [{"price": 22.0, "quantity": 100}],
    "boardId": "G1",
    "isin": "VN000000HPG4",
    "marketId": "STO",
    "offer": [{"price": 22.1, "quantity": 100}],
    "symbol": "HPG",
    "time": "2026-08-10 10:00:00.000",
    # Fields that must never appear in normalized output, simulating a future
    # response (or a wiring mistake) that echoes something sensitive back.
    "authorization": "Bearer super-secret-token",
    "x-api-key": "leaked-api-key",
    "sessionCookie": "leaked-cookie-value",
}

RAW_FOREIGN_RECORD_WITH_ROGUE_FIELDS = {
    "boardId": "G1",
    "buyTradedAmount": 100,
    "buyVolume": 10,
    "foreignerBuyPossibleQuantity": 1000,
    "foreignerOrderLimitQuantity": 900,
    "marketId": "STO",
    "sellTradedAmount": 50,
    "sellVolume": 5,
    "symbol": "HPG",
    "time": "2026-08-10 10:00:00.000",
    "totalBuyTradedAmount": 100,
    "totalBuyVolume": 10,
    "totalSellTradedAmount": 50,
    "totalSellVolume": 5,
    "tradingSessionId": "40",
    "authorization": "Bearer super-secret-token",
    "x-api-key": "leaked-api-key",
}


class NoSecretFieldsSerializedTests(unittest.TestCase):
    def test_bid_ask_normalization_never_serializes_rogue_credential_fields(self):
        result = bid_ask.normalize_snapshot(RAW_QUOTE_WITH_ROGUE_FIELDS, source_endpoint="/price/HPG/quotes/latest")
        dumped = json.dumps(result)
        self.assertNotIn("super-secret-token", dumped)
        self.assertNotIn("leaked-api-key", dumped)
        self.assertNotIn("leaked-cookie-value", dumped)
        self.assertNotIn("authorization", dumped.lower())

    def test_foreign_flow_normalization_never_serializes_rogue_credential_fields(self):
        result = foreign_flow.normalize_record(
            RAW_FOREIGN_RECORD_WITH_ROGUE_FIELDS, source_endpoint="/price/HPG/foreign-trading"
        )
        dumped = json.dumps(result)
        self.assertNotIn("super-secret-token", dumped)
        self.assertNotIn("leaked-api-key", dumped)


class NoAuthHeaderRetainedTests(unittest.TestCase):
    def test_canonical_bid_ask_schema_has_no_header_shaped_field(self):
        result = bid_ask.normalize_snapshot(RAW_QUOTE_WITH_ROGUE_FIELDS, source_endpoint="/price/HPG/quotes/latest")
        forbidden_keys = {"headers", "authorization", "signature", "x-api-key", "cookie", "token"}
        self.assertFalse(forbidden_keys & set(result.keys()))
        self.assertFalse(forbidden_keys & set(result["provenance"].keys()))

    def test_canonical_foreign_flow_schema_has_no_header_shaped_field(self):
        result = foreign_flow.normalize_record(
            RAW_FOREIGN_RECORD_WITH_ROGUE_FIELDS, source_endpoint="/price/HPG/foreign-trading"
        )
        forbidden_keys = {"headers", "authorization", "signature", "x-api-key", "cookie", "token"}
        self.assertFalse(forbidden_keys & set(result.keys()))
        self.assertFalse(forbidden_keys & set(result["provenance"].keys()))


class NoNetworkOrPrivateEndpointCapabilityTests(unittest.TestCase):
    """These two modules are pure normalizers: no network call, no endpoint
    construction, no credential handling at all -- structurally, not just by
    policy. The probe's own read-only market-data allowlist (which already
    refuses every account/order/trading path) is covered exhaustively in
    tests/test_dnse_market_data.py; this only needs to confirm the new
    capability modules don't reopen that surface."""

    def test_bid_ask_module_imports_no_network_library(self):
        source = inspect.getsource(bid_ask)
        for forbidden in ("import requests", "import urllib", "socket.", "http.client"):
            self.assertNotIn(forbidden, source)

    def test_foreign_flow_module_imports_no_network_library(self):
        source = inspect.getsource(foreign_flow)
        for forbidden in ("import requests", "import urllib", "socket.", "http.client"):
            self.assertNotIn(forbidden, source)

    def test_neither_module_references_trading_or_account_paths(self):
        forbidden_paths = ("/accounts", "/positions", "/registration", "/brokers", "/orders")
        for module in (bid_ask, foreign_flow):
            source = inspect.getsource(module)
            for path in forbidden_paths:
                self.assertNotIn(path, source)


if __name__ == "__main__":
    unittest.main()
