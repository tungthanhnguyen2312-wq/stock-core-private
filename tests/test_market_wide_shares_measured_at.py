"""measured_at field of market_wide_current_shares_resolver.resolve_market_wide_shares.

Uses an empty temp directory as runtime_root: _Store(runtime_root) fails fast with
ShareStoreUnreadable (no data/official-evidence/ present) before touching any DB, which lets
resolve_market_wide_shares's early "unresolved_error" return carry measured_at through a real
call to the function -- no vn_stock.db or CSV fixtures needed for this specific field.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import market_wide_current_shares_resolver as shares_resolver  # noqa: E402


class MeasuredAtTests(unittest.TestCase):
    def test_unresolved_error_path_uses_vn_now_iso(self):
        with tempfile.TemporaryDirectory() as empty_root:
            with mock.patch.object(shares_resolver, "vn_now_iso", return_value="2026-08-08T16:00:00+07:00") as fake:
                result = shares_resolver.resolve_market_wide_shares(empty_root, "2026-01-15")
        fake.assert_called_once_with()
        self.assertEqual(result["status"], "unresolved_error")
        self.assertEqual(result["measured_at"], "2026-08-08T16:00:00+07:00")

    def test_real_call_is_vn_offset(self):
        with tempfile.TemporaryDirectory() as empty_root:
            result = shares_resolver.resolve_market_wide_shares(empty_root, "2026-01-15")
        self.assertEqual(result["status"], "unresolved_error")
        self.assertRegex(result["measured_at"], r"\+07:00$")

    def test_no_bare_astimezone_left_in_source(self):
        source = (ROOT / "market_wide_current_shares_resolver.py").read_text(encoding="utf-8")
        self.assertNotIn("astimezone()", source)


if __name__ == "__main__":
    unittest.main()
