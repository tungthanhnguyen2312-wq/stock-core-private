"""Direct-call tests for publish_dashboard.py's dashboard_home_summary handling
(validate_dashboard_home_summary / copy_dashboard_home_summary).

These call the two functions directly, never through publish_dashboard.main() / the
CLI entrypoint -- main() calls assert_producer_publisher_file(), which deliberately
REFUSES to run from anywhere but the one canonical
C:\\Projects\\StockLookup\\stock-core-private\\publish_dashboard.py path (verified:
identical refusal on a clean, unmodified checkout of this same worktree, in every one
of test_publish_dashboard.py's existing CLI-level tests -- a pre-existing, deliberate
safety property of any isolated worktree, not something this milestone introduces or
can bypass). Mirrors the already-established validate_screener_master_projection
behavior exactly; see tests/test_dashboard_home_summary.py for the module's own
build_home_summary() unit tests.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import publish_dashboard as pd  # noqa: E402
import dashboard_home_summary  # noqa: E402


def _home_summary_payload(*, session="2026-09-18", denominator=5, source_identity="screener_master_projection/v1:abc"):
    payload = {
        "schema_version": dashboard_home_summary.SCHEMA_VERSION,
        "contract_version": dashboard_home_summary.CONTRACT_VERSION,
        "as_of_session": session,
        "source_artifact_identity": source_identity,
        "denominator": denominator,
    }
    payload.update(dashboard_home_summary.content_identity(payload))
    return payload


class ValidateDashboardHomeSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="publish_dashboard_home_summary_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, payload):
        path = self.tmp / "dashboard_home_summary.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "DASHBOARD_HOME_SUMMARY_NOT_PUBLISHED"):
            pd.validate_dashboard_home_summary(self.tmp / "absent.json", "2026-09-18", screener_artifact_identity=None)

    def test_wrong_contract_version_is_rejected(self):
        payload = _home_summary_payload()
        payload["contract_version"] = "wrong/v1"
        path = self._write(payload)
        with self.assertRaisesRegex(ValueError, "DASHBOARD_HOME_SUMMARY_NOT_PUBLISHED"):
            pd.validate_dashboard_home_summary(path, "2026-09-18", screener_artifact_identity=None)

    def test_session_mismatch_is_rejected(self):
        path = self._write(_home_summary_payload(session="2026-09-17"))
        with self.assertRaisesRegex(ValueError, "DASHBOARD_HOME_SUMMARY_SESSION_MISMATCH"):
            pd.validate_dashboard_home_summary(path, "2026-09-18", screener_artifact_identity=None)

    def test_invalid_denominator_is_rejected(self):
        payload = _home_summary_payload()
        payload["denominator"] = 0
        path = self._write(payload)
        with self.assertRaisesRegex(ValueError, "DASHBOARD_HOME_SUMMARY_NOT_PUBLISHED"):
            pd.validate_dashboard_home_summary(path, "2026-09-18", screener_artifact_identity=None)

    def test_source_screener_identity_mismatch_is_rejected(self):
        path = self._write(_home_summary_payload(source_identity="screener_master_projection/v1:abc"))
        with self.assertRaisesRegex(ValueError, "DASHBOARD_HOME_SUMMARY_SOURCE_SCREENER_IDENTITY_MISMATCH"):
            pd.validate_dashboard_home_summary(path, "2026-09-18", screener_artifact_identity="screener_master_projection/v1:different")

    def test_valid_summary_bound_to_the_right_screener_identity_is_accepted(self):
        payload = _home_summary_payload(source_identity="screener_master_projection/v1:abc")
        path = self._write(payload)
        result = pd.validate_dashboard_home_summary(path, "2026-09-18", screener_artifact_identity="screener_master_projection/v1:abc")
        self.assertEqual(result["artifact_identity"], payload["artifact_identity"])

    def test_no_screener_identity_supplied_skips_the_cross_check(self):
        # screener may legitimately be absent (optional in the same sense as the
        # projection itself) -- the Home summary is still independently valid on its
        # own contract in that case.
        path = self._write(_home_summary_payload())
        result = pd.validate_dashboard_home_summary(path, "2026-09-18", screener_artifact_identity=None)
        self.assertEqual(result["denominator"], 5)


class CopyDashboardHomeSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="publish_dashboard_home_summary_copy_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._original_web_root = pd.WEB_ROOT
        pd.WEB_ROOT = self.tmp / "web"
        self.addCleanup(setattr, pd, "WEB_ROOT", self._original_web_root)

    def test_copy_writes_json_and_js_fallback_and_reports_changed(self):
        source = self.tmp / "dashboard_home_summary.json"
        payload = _home_summary_payload()
        source.write_text(json.dumps(payload), encoding="utf-8")
        changed = pd.copy_dashboard_home_summary(source)
        self.assertTrue(changed)
        target = pd.WEB_ROOT / pd.HOME_SUMMARY_ASSET
        js_target = pd.WEB_ROOT / pd.HOME_SUMMARY_JS_ASSET
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)
        self.assertIn(dashboard_home_summary.JS_GLOBAL, js_target.read_text(encoding="utf-8"))

    def test_copy_is_idempotent_second_call_reports_unchanged(self):
        source = self.tmp / "dashboard_home_summary.json"
        source.write_text(json.dumps(_home_summary_payload()), encoding="utf-8")
        pd.copy_dashboard_home_summary(source)
        changed_again = pd.copy_dashboard_home_summary(source)
        self.assertFalse(changed_again)

    def test_home_summary_asset_names_are_in_optional_safe_web_artifacts(self):
        self.assertIn(pd.HOME_SUMMARY_ASSET, pd.OPTIONAL_SAFE_WEB_ARTIFACTS)
        self.assertIn(pd.HOME_SUMMARY_JS_ASSET, pd.OPTIONAL_SAFE_WEB_ARTIFACTS)


if __name__ == "__main__":
    unittest.main()
