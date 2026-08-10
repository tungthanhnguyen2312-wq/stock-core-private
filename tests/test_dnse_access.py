from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from dnse_access import (
    auth_headers,
    build_signature,
    credential_status,
    credentials_for_request,
    redact_headers,
    redact_value,
    sanitize_url,
    scrub_text,
)


class DnseAccessTests(unittest.TestCase):
    def test_missing_credentials_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            status = credential_status()
            self.assertFalse(status["configured"])
            self.assertIsNone(credentials_for_request())

    def test_primary_and_alternate_env_pairs_both_supported(self):
        with patch.dict(os.environ, {"DNSE_API_KEY": "k", "DNSE_API_SECRET": "s"}, clear=True):
            self.assertTrue(credential_status()["configured"])
            self.assertEqual(("k", "s"), credentials_for_request())
        with patch.dict(os.environ, {"LIVESPEED_API_KEY": "k2", "LIVESPEED_API_SECRET": "s2"}, clear=True):
            self.assertTrue(credential_status()["configured"])
            self.assertEqual(("k2", "s2"), credentials_for_request())

    def test_partial_pair_is_not_configured(self):
        with patch.dict(os.environ, {"DNSE_API_KEY": "k"}, clear=True):
            self.assertFalse(credential_status()["configured"])
            self.assertIsNone(credentials_for_request())
        with patch.dict(os.environ, {"LIVESPEED_API_SECRET": "s"}, clear=True):
            self.assertFalse(credential_status()["configured"])

    def test_credential_status_never_names_which_pair_or_leaks_value(self):
        with patch.dict(os.environ, {"LIVESPEED_API_KEY": "very-secret-key",
                                      "LIVESPEED_API_SECRET": "very-secret-value"}, clear=True):
            dumped = json.dumps(credential_status())
            self.assertNotIn("very-secret-key", dumped)
            self.assertNotIn("very-secret-value", dumped)
            self.assertNotIn("LIVESPEED", dumped)

    def test_signature_and_headers_never_contain_the_raw_secret(self):
        signature = build_signature("top-secret-hmac-key", "GET", "/market/working-dates",
                                     "Mon, 10 Aug 2026 00:00:00 +0000", "nonce123")
        self.assertNotIn("top-secret-hmac-key", signature)
        headers = auth_headers("my-api-key", "top-secret-hmac-key", "GET", "/market/working-dates")
        dumped = json.dumps(headers)
        self.assertNotIn("top-secret-hmac-key", dumped)
        # The api key itself is expected to appear -- it is the public keyId, sent by design.
        self.assertIn("my-api-key", dumped)

    def test_auth_headers_are_deterministic_in_shape(self):
        headers = auth_headers("k", "s", "GET", "/market/working-dates")
        self.assertEqual({"Date", "X-Signature", "x-api-key", "version"}, set(headers.keys()))
        self.assertTrue(headers["X-Signature"].startswith('Signature keyId="k"'))

    def test_redact_value_strips_credential_shaped_keys_recursively(self):
        payload = {
            "accessToken": "abc123",
            "nested": {"apiKey": "xyz", "safe_field": "keep-me"},
            "list": [{"authorization": "Bearer zzz"}, {"price": 25000}],
            "ordinary": "value",
        }
        redacted = redact_value(payload)
        self.assertEqual("<redacted>", redacted["accessToken"])
        self.assertEqual("<redacted>", redacted["nested"]["apiKey"])
        self.assertEqual("keep-me", redacted["nested"]["safe_field"])
        self.assertEqual("<redacted>", redacted["list"][0]["authorization"])
        self.assertEqual(25000, redacted["list"][1]["price"])
        self.assertEqual("value", redacted["ordinary"])
        dumped = json.dumps(redacted)
        self.assertNotIn("abc123", dumped)
        self.assertNotIn("xyz", dumped)
        self.assertNotIn("zzz", dumped)

    def test_redact_value_passes_through_falsy_sensitive_fields(self):
        # nextPageToken: null/0/"" means "no further pages" -- a pagination
        # completeness signal this qualification pilot needs to see, not a
        # secret. A populated token under the same key must still redact.
        payload = {"nextPageToken": None, "otherToken": 0, "accessToken": "real-value"}
        redacted = redact_value(payload)
        self.assertIsNone(redacted["nextPageToken"])
        self.assertEqual(0, redacted["otherToken"])
        self.assertEqual("<redacted>", redacted["accessToken"])

    def test_trading_session_fields_are_not_treated_as_credentials(self):
        payload = {"tradingSessionId": "AM_CONTINUOUS", "tradingSessions": ["A", "B"]}
        redacted = redact_value(payload)
        self.assertEqual("AM_CONTINUOUS", redacted["tradingSessionId"])
        self.assertEqual(["A", "B"], redacted["tradingSessions"])

    def test_sanitize_url_redacts_token_like_query_params_only(self):
        value = sanitize_url("https://openapi.dnse.com.vn/price/HPG/secdef?boardId=G1&token=secretvalue")
        self.assertNotIn("secretvalue", value)
        self.assertIn("boardId=G1", value)

    def test_scrub_text_removes_known_secret_values(self):
        text = "request failed for key=my-key secret=my-secret-value"
        scrubbed = scrub_text(text, "my-key", "my-secret-value")
        self.assertNotIn("my-key", scrubbed)
        self.assertNotIn("my-secret-value", scrubbed)

    def test_redact_headers_masks_signature_and_api_key(self):
        headers = auth_headers("k", "s", "GET", "/market/working-dates")
        safe = redact_headers(headers)
        self.assertEqual("<redacted>", safe["X-Signature"])
        self.assertEqual("<redacted>", safe["x-api-key"])
        self.assertEqual(headers["version"], safe["version"])


if __name__ == "__main__":
    unittest.main()
