from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dnse_secrets_env import (
    DEFAULT_SECRETS_PATH,
    ensure_credentials_loaded,
    load_secrets_env,
    secrets_path,
)


class SecretsPathResolutionTests(unittest.TestCase):
    def test_explicit_path_wins(self):
        self.assertEqual(Path("explicit.env"), secrets_path("explicit.env"))

    @patch.dict(os.environ, {"STOCK_LOOKUP_SECRETS_FILE": "/from/env/secrets.env"}, clear=False)
    def test_env_override_used_when_no_explicit_path(self):
        self.assertEqual(Path("/from/env/secrets.env"), secrets_path())

    @patch.dict(os.environ, {}, clear=False)
    def test_default_path_when_nothing_configured(self):
        os.environ.pop("STOCK_LOOKUP_SECRETS_FILE", None)
        self.assertEqual(r"C:\Users\tungt\.stocklookup\secrets.env", DEFAULT_SECRETS_PATH)
        self.assertNotEqual(r"C:\Users\tungt.stocklookup\secrets.env", DEFAULT_SECRETS_PATH)
        self.assertEqual(Path(DEFAULT_SECRETS_PATH), secrets_path())


class LoadSecretsEnvTests(unittest.TestCase):
    def test_missing_file_reports_not_found_without_raising(self):
        result = load_secrets_env("Z:/definitely/does/not/exist/secrets.env")
        self.assertFalse(result["file_found"])
        self.assertEqual([], result["keys_injected"])

    @patch.dict(os.environ, {}, clear=False)
    def test_parses_and_injects_known_keys_only(self):
        os.environ.pop("LIVESPEED_API_KEY", None)
        os.environ.pop("LIVESPEED_API_SECRET", None)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.env"
            path.write_text(
                "# a comment\n"
                "\n"
                "LIVESPEED_API_KEY=my-test-key-value\n"
                "LIVESPEED_API_SECRET=\"my-test-secret-value\"\n"
                "SOME_UNRELATED_KEY=should-not-be-touched\n",
                encoding="utf-8",
            )
            result = load_secrets_env(path)
        self.assertTrue(result["file_found"])
        self.assertEqual(["LIVESPEED_API_KEY", "LIVESPEED_API_SECRET"], result["keys_found_in_file"])
        self.assertEqual(["LIVESPEED_API_KEY", "LIVESPEED_API_SECRET"], sorted(result["keys_injected"]))
        self.assertEqual("my-test-key-value", os.environ["LIVESPEED_API_KEY"])
        self.assertEqual("my-test-secret-value", os.environ["LIVESPEED_API_SECRET"])
        self.assertNotIn("SOME_UNRELATED_KEY", os.environ)

    @patch.dict(os.environ, {}, clear=False)
    def test_does_not_override_already_configured_env_var(self):
        os.environ["LIVESPEED_API_KEY"] = "already-set-value"
        os.environ.pop("LIVESPEED_API_SECRET", None)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.env"
            path.write_text(
                "LIVESPEED_API_KEY=from-file-value\n"
                "LIVESPEED_API_SECRET=from-file-secret\n",
                encoding="utf-8",
            )
            result = load_secrets_env(path)
        self.assertEqual("already-set-value", os.environ["LIVESPEED_API_KEY"])
        self.assertEqual(["LIVESPEED_API_KEY"], result["keys_already_set"])
        self.assertEqual(["LIVESPEED_API_SECRET"], result["keys_injected"])

    def test_result_never_contains_any_credential_value(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.env"
            path.write_text(
                "LIVESPEED_API_KEY=super-secret-key-xyz\n"
                "LIVESPEED_API_SECRET=super-secret-value-abc\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("LIVESPEED_API_KEY", None)
                os.environ.pop("LIVESPEED_API_SECRET", None)
                result = load_secrets_env(path)
        dumped = json.dumps(result)
        self.assertNotIn("super-secret-key-xyz", dumped)
        self.assertNotIn("super-secret-value-abc", dumped)

    @patch.dict(os.environ, {}, clear=False)
    def test_blank_value_is_not_injected(self):
        os.environ.pop("LIVESPEED_API_KEY", None)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.env"
            path.write_text("LIVESPEED_API_KEY=\n", encoding="utf-8")
            result = load_secrets_env(path)
        self.assertNotIn("LIVESPEED_API_KEY", os.environ)
        self.assertEqual([], result["keys_injected"])


class EnsureCredentialsLoadedTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=False)
    def test_skips_file_when_already_configured(self):
        os.environ["DNSE_API_KEY"] = "k"
        os.environ["DNSE_API_SECRET"] = "s"
        try:
            status = ensure_credentials_loaded("Z:/should/not/be/read.env")
            self.assertFalse(status["secrets_file_consulted"])
            self.assertTrue(status["configured"])
        finally:
            os.environ.pop("DNSE_API_KEY", None)
            os.environ.pop("DNSE_API_SECRET", None)

    @patch.dict(os.environ, {}, clear=False)
    def test_consults_file_when_not_configured(self):
        for key in ("DNSE_API_KEY", "DNSE_API_SECRET", "LIVESPEED_API_KEY", "LIVESPEED_API_SECRET"):
            os.environ.pop(key, None)
        status = ensure_credentials_loaded("Z:/definitely/not/found.env")
        self.assertTrue(status["secrets_file_consulted"])
        self.assertFalse(status["secrets_file_found"])
        self.assertFalse(status["configured"])


if __name__ == "__main__":
    unittest.main()
