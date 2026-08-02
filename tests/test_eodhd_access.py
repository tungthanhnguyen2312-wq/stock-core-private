from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from eodhd_access import credential_status, sanitize_url
from eodhd_market_data import EodhdQualificationError, qualify_eod_sample
from tools.check_eodhd_access import main


class Response:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload, sort_keys=True).encode("utf-8")

    def json(self):
        return self._payload


def row(session="2026-07-31", close=25000.0, adjusted=24000.0, volume=123456):
    return [{"date": session, "open": 24900.0, "high": 25200.0, "low": 24800.0,
             "close": close, "adjusted_close": adjusted, "volume": volume}]


class EodhdAccessTests(unittest.TestCase):
    def test_missing_and_environment_credential_status(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(credential_status()["configured"])
        with patch.dict(os.environ, {"EODHD_API_TOKEN": "secret"}, clear=True):
            self.assertTrue(credential_status()["configured"])
            self.assertNotIn("secret", json.dumps(credential_status()))

    def test_url_sanitization_never_exposes_token(self):
        value = sanitize_url("https://eodhd.com/api/eod/HPG.VN?fmt=json&api_token=secret")
        self.assertNotIn("secret", value)
        self.assertIn("api_token=%3Credacted%3E", value)

    def test_non_live_mode_makes_no_request(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output), patch(
            "eodhd_market_data._default_request_get"
        ) as request:
            self.assertEqual(0, main([]))
        request.assert_not_called()
        self.assertEqual("not_checked", json.loads(output.getvalue())["validation_status"])

    def test_live_mode_without_token_is_structured(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
            self.assertEqual(2, main(["--live"]))
        self.assertEqual("access_not_configured", json.loads(output.getvalue())["validation_status"])

    def test_qualified_sample_preserves_raw_adjusted_and_volume_semantics(self):
        calls = []
        def request(url, *, params, timeout):
            calls.append((url, params, timeout))
            return Response(row(close=25000.0 if "HPG" in url else 62000.0))
        result = qualify_eod_sample("secret", from_date="2026-07-30", to_date="2026-07-31", request_get=request)
        self.assertEqual(2, len(calls))
        self.assertEqual("raw_unadjusted_close", result["price_basis"]["raw"])
        self.assertEqual("split_and_dividend_adjusted_close", result["price_basis"]["adjusted"])
        self.assertEqual({"value": "split_adjusted_volume", "unit": "shares", "verified": True}, result["volume_basis"])
        self.assertEqual(25000.0, result["observations"][0]["price_raw_eod"])
        self.assertEqual(24000.0, result["observations"][0]["price_adjusted_eod"])
        self.assertNotIn("secret", json.dumps(result))

    def test_auth_timeout_schema_and_mixed_session_fail_closed_without_secret(self):
        cases = [
            (lambda *_a, **_k: Response({}, 401), "authentication_failed"),
            (lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError("secret")), "request_failed_TimeoutError"),
            (lambda *_a, **_k: Response({"close": 1}), "response_schema_invalid"),
        ]
        for request, code in cases:
            with self.subTest(code=code), self.assertRaises(EodhdQualificationError) as caught:
                qualify_eod_sample("secret", from_date="2026-07-30", to_date="2026-07-31", request_get=request)
            self.assertEqual(code, caught.exception.code)
            self.assertNotIn("secret", str(caught.exception))
        responses = iter([Response(row("2026-07-31")), Response(row("2026-07-30"))])
        with self.assertRaisesRegex(EodhdQualificationError, "mixed_ticker_sessions"):
            qualify_eod_sample("secret", from_date="2026-07-30", to_date="2026-07-31",
                               request_get=lambda *_a, **_k: next(responses))

    def test_missing_fields_and_invalid_units_fail_closed(self):
        for payload, code in [
            ([{"date": "2026-07-31", "close": 1, "volume": 1}], "invalid_adjusted_close"),
            (row(volume=1.5), "invalid_volume"),
        ]:
            with self.subTest(code=code), self.assertRaises(EodhdQualificationError) as caught:
                qualify_eod_sample("secret", from_date="2026-07-30", to_date="2026-07-31",
                                   request_get=lambda *_a, **_k: Response(payload))
            self.assertEqual(code, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
