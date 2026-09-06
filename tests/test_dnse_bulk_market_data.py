from __future__ import annotations

import json
import unittest

from dnse_bulk_market_data import (
    MARKET_DATA_ENDPOINTS,
    fetch_capability_raw,
    is_retryable,
)


class _FakeResponse:
    def __init__(self, status_code, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = {} if headers is None else headers

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class NoTruncationTests(unittest.TestCase):
    def test_large_list_is_returned_in_full_not_truncated(self):
        """The exact regression this module exists to prevent: a >20-item
        page must survive completely, unlike dnse_market_data's
        request_capability (see test_dnse_market_data.py's own >20-item test,
        which asserts the opposite -- truncation -- for that module)."""
        payload = {"total": 137, "page": 1, "pageSize": 100,
                   "data": [{"symbol": f"T{i}"} for i in range(60)]}
        result = fetch_capability_raw(
            "instruments", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(200, payload),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(60, len(result["body"]["data"]))
        self.assertEqual({"symbol": "T0"}, result["body"]["data"][0])
        self.assertEqual({"symbol": "T59"}, result["body"]["data"][59])
        self.assertNotIn("list_truncated", result["body"]["data"])

    def test_body_key_is_not_body_redacted(self):
        result = fetch_capability_raw(
            "working_dates", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(200, {"workingDates": ["2026-08-11"]}),
        )
        self.assertIn("body", result)
        self.assertNotIn("body_redacted", result)


class RequestBehaviorTests(unittest.TestCase):
    def test_only_get_style_call_is_ever_issued(self):
        calls = []

        def fake_get(url, *, params, headers, timeout):
            calls.append((url, params, headers, timeout))
            return _FakeResponse(200, {"date": "2026-08-11"})

        fetch_capability_raw("working_dates", api_key="k", api_secret="s", request_get=fake_get)
        self.assertEqual(1, len(calls))
        url, _params, headers, _timeout = calls[0]
        self.assertTrue(url.endswith("/market/working-dates"))
        self.assertIn("X-Signature", headers)

    def test_zero_retries_on_transport_failure(self):
        calls = []

        def fake_get(*_a, **_k):
            calls.append(1)
            raise TimeoutError("connection to secret-host timed out with key=abc123")

        result = fetch_capability_raw("working_dates", api_key="k", api_secret="abc123", request_get=fake_get)
        self.assertEqual(1, len(calls))
        self.assertFalse(result["ok"])
        self.assertEqual("request_failed_TimeoutError", result["error_code"])
        self.assertNotIn("abc123", json.dumps(result))

    def test_401_and_403_map_to_authentication_failed_without_raising(self):
        for status in (401, 403):
            result = fetch_capability_raw(
                "working_dates", api_key="k", api_secret="s",
                request_get=lambda *_a, **_k: _FakeResponse(status, {"message": "unauthorized"}),
            )
            self.assertFalse(result["ok"])
            self.assertEqual("authentication_failed", result["error_code"])

    def test_429_maps_to_rate_limited(self):
        result = fetch_capability_raw(
            "instruments", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(429, {"message": "slow down"}),
        )
        self.assertFalse(result["ok"])
        self.assertEqual("rate_limited", result["error_code"])

    def test_429_exposes_only_usable_numeric_retry_after(self):
        result = fetch_capability_raw(
            "instruments", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(429, {"message": "slow down"}, headers={"Retry-After": "2.5", "X-Secret": "nope"}),
        )
        self.assertEqual(2.5, result["retry_after_seconds"])
        self.assertNotIn("headers", result)
        invalid = fetch_capability_raw(
            "instruments", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(429, headers={"Retry-After": "not-a-number"}),
        )
        self.assertNotIn("retry_after_seconds", invalid)

    def test_result_never_contains_request_headers_signature_or_credentials(self):
        result = fetch_capability_raw(
            "working_dates", api_key="my-api-key", api_secret="my-secret",
            request_get=lambda *_a, **_k: _FakeResponse(200, {"date": "2026-08-11"}),
        )
        dumped = json.dumps(result)
        self.assertNotIn("X-Signature", dumped)
        self.assertNotIn("x-api-key", dumped)
        self.assertNotIn("my-api-key", dumped)
        self.assertNotIn("my-secret", dumped)

    def test_non_200_non_auth_status_still_captures_body_when_json(self):
        result = fetch_capability_raw(
            "instruments", api_key="k", api_secret="s",
            request_get=lambda *_a, **_k: _FakeResponse(400, {"message": "bad symbol"}),
        )
        self.assertFalse(result["ok"])
        self.assertEqual("http_status_400", result["error_code"])
        self.assertEqual({"message": "bad symbol"}, result["body"])

    def test_only_allowlisted_endpoints_are_reachable(self):
        for capability, spec in MARKET_DATA_ENDPOINTS.items():
            self.assertTrue(spec["path"].startswith("/price") or spec["path"].startswith("/market"))


class IsRetryableTests(unittest.TestCase):
    def test_rate_limited_is_retryable(self):
        self.assertTrue(is_retryable({"ok": False, "error_code": "rate_limited"}))

    def test_transport_failure_is_retryable(self):
        self.assertTrue(is_retryable({"ok": False, "error_code": "request_failed_TimeoutError"}))

    def test_authentication_failure_is_not_retryable(self):
        self.assertFalse(is_retryable({"ok": False, "error_code": "authentication_failed"}))

    def test_client_error_status_is_not_retryable(self):
        self.assertFalse(is_retryable({"ok": False, "error_code": "http_status_400"}))

    def test_success_is_not_retryable(self):
        self.assertFalse(is_retryable({"ok": True}))


if __name__ == "__main__":
    unittest.main()
