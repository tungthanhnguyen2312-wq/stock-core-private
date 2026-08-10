from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from dnse_market_data import (
    MARKET_DATA_ENDPOINTS,
    DnseProbeError,
    request_capability,
    resolve_endpoint,
    top_level_schema,
)

# Exact forbidden paths, taken from the official dnse-tech/openapi-sdk client's own
# account/order/position/trading/broker methods (read 2026-08-10). None of these -- or
# any capability name that maps to them -- may ever appear in MARKET_DATA_ENDPOINTS.
FORBIDDEN_PATH_PREFIXES = ("/accounts", "/positions", "/registration", "/brokers")
FORBIDDEN_CAPABILITY_NAMES = (
    "accounts", "get_accounts", "balances", "get_balances", "positions", "get_positions",
    "orders", "get_orders", "post_order", "put_order", "cancel_order", "order_history",
    "order_detail", "execution_detail", "loan_packages", "ppse", "corporate_action_history",
    "create_trading_token", "send_email_otp", "close_position", "care_by", "pnl_configs",
)


class ForbiddenEndpointTests(unittest.TestCase):
    def test_allowlist_contains_no_mutation_or_account_paths(self):
        for capability, spec in MARKET_DATA_ENDPOINTS.items():
            for prefix in FORBIDDEN_PATH_PREFIXES:
                self.assertFalse(
                    spec["path"].startswith(prefix),
                    f"{capability} maps to forbidden path prefix {prefix}",
                )

    def test_forbidden_capability_names_are_not_reachable(self):
        for name in FORBIDDEN_CAPABILITY_NAMES:
            self.assertNotIn(name, MARKET_DATA_ENDPOINTS)
            with self.assertRaises(DnseProbeError) as caught:
                resolve_endpoint(name, symbol="HPG")
            self.assertEqual("unknown_capability", caught.exception.code)

    def test_every_allowlisted_endpoint_is_a_price_or_market_get(self):
        # Documents the allowlist's own shape: every path lives under /price or /market,
        # the two namespaces the official SDK uses for market-data (as opposed to
        # /accounts, /positions, /registration, /brokers for trading/account concerns).
        for capability, spec in MARKET_DATA_ENDPOINTS.items():
            self.assertTrue(
                spec["path"].startswith("/price") or spec["path"].startswith("/market"),
                f"{capability} path {spec['path']} is outside the market-data namespace",
            )


class ResolveEndpointTests(unittest.TestCase):
    def test_unknown_capability_raises(self):
        with self.assertRaises(DnseProbeError) as caught:
            resolve_endpoint("not_a_real_capability")
        self.assertEqual("unknown_capability", caught.exception.code)

    def test_symbol_required_capability_without_symbol_raises(self):
        with self.assertRaises(DnseProbeError) as caught:
            resolve_endpoint("security_definition")
        self.assertEqual("symbol_required", caught.exception.code)

    def test_symbol_is_interpolated_into_path(self):
        self.assertEqual("/price/HPG/secdef", resolve_endpoint("security_definition", symbol="HPG"))

    def test_no_symbol_capability_ignores_symbol(self):
        self.assertEqual("/market/working-dates", resolve_endpoint("working_dates"))


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class RequestCapabilityTests(unittest.TestCase):
    def test_only_get_style_call_is_ever_issued(self):
        calls = []

        def fake_get(url, *, params, headers, timeout):
            calls.append((url, params, headers, timeout))
            return _FakeResponse(200, {"date": "2026-08-10"})

        request_capability("working_dates", api_key="k", api_secret="s", request_get=fake_get)
        self.assertEqual(1, len(calls))
        url, params, headers, timeout = calls[0]
        self.assertTrue(url.endswith("/market/working-dates"))
        self.assertIn("X-Signature", headers)

    def test_zero_retries_on_transport_failure(self):
        calls = []

        def fake_get(*_a, **_k):
            calls.append(1)
            raise TimeoutError("connection to secret-host timed out with key=abc123")

        result = request_capability("working_dates", api_key="k", api_secret="abc123", request_get=fake_get)
        self.assertEqual(1, len(calls))
        self.assertFalse(result["ok"])
        self.assertEqual("request_failed_TimeoutError", result["error_code"])
        self.assertNotIn("abc123", json.dumps(result))

    def test_401_and_403_map_to_authentication_failed_without_raising(self):
        for status in (401, 403):
            result = request_capability(
                "working_dates", api_key="k", api_secret="s",
                request_get=lambda *_a, **_k: _FakeResponse(status, {"message": "unauthorized"}),
            )
            self.assertFalse(result["ok"])
            self.assertEqual("authentication_failed", result["error_code"])

    def test_success_response_body_is_redacted_before_return(self):
        payload = {"accessToken": "should-not-appear", "date": "2026-08-10", "sessions": [1, 2]}
        result = request_capability(
            "working_dates", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(200, payload),
        )
        self.assertTrue(result["ok"])
        self.assertNotIn("should-not-appear", json.dumps(result))
        self.assertEqual("<redacted>", result["body_redacted"]["accessToken"])

    def test_result_never_contains_request_headers_or_signature(self):
        result = request_capability(
            "working_dates", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(200, {"date": "2026-08-10"}),
        )
        dumped = json.dumps(result)
        self.assertNotIn("X-Signature", dumped)
        self.assertNotIn("x-api-key", dumped)

    def test_deterministic_sanitized_output_for_identical_input(self):
        def fake_get(*_a, **_k):
            return _FakeResponse(200, {"date": "2026-08-10", "sessions": ["2026-08-10"]})

        first = request_capability("working_dates", api_key="k", api_secret="s", request_get=fake_get)
        second = request_capability("working_dates", api_key="k", api_secret="s", request_get=fake_get)
        first.pop("elapsed_ms", None)
        second.pop("elapsed_ms", None)
        self.assertEqual(first, second)

    def test_long_lists_are_bounded_not_string_truncated(self):
        payload = {"total": 137, "page": 1, "data": [{"symbol": f"T{i}"} for i in range(60)]}
        result = request_capability(
            "instruments", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(200, payload),
        )
        body = result["body_redacted"]
        # Sibling scalar fields must survive even though `data` is huge.
        self.assertEqual(137, body["total"])
        self.assertEqual(1, body["page"])
        self.assertTrue(body["data"]["list_truncated"])
        self.assertEqual(60, body["data"]["item_count"])
        self.assertEqual(5, len(body["data"]["sample_first"]))

    def test_top_level_schema_reports_keys_not_values(self):
        schema = top_level_schema({"open": 1, "close": 2, "secret_looking_value": "abc"})
        self.assertEqual(["close", "open", "secret_looking_value"], schema)
        list_schema = top_level_schema([{"a": 1}, {"a": 2}])
        self.assertEqual(["a"], list_schema)


if __name__ == "__main__":
    unittest.main()
