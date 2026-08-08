"""generated_at field of watchlist_eval.build_report -- reuses the exact in-memory DB / calendar
fixture from test_watchlist_eval.py's EvaluateNoLookaheadTests so this stays a real call through
we.evaluate() -> we.build_report(), not a hand-built DataFrame guessing at column shape.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import watchlist_eval as we  # noqa: E402
from test_watchlist_eval import CALENDAR, _build_memory_db  # noqa: E402

D1 = CALENDAR[0]


class BuildReportGeneratedAtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn = _build_memory_db()
        try:
            history = pd.DataFrame([
                {"session_date": D1, "ticker": "ABC", "score": 75.0, "fundamental": 70, "technical": 80,
                 "momentum": 70, "liquidity": 90, "macro": 60, "risk": 80, "close": 100.0, "strategies": "momentum"},
            ])
            cls.evaluated = we.evaluate(history, conn, horizons=(3,))
        finally:
            conn.close()

    def test_uses_vn_now_iso(self):
        with mock.patch.object(we, "vn_now_iso", return_value="2026-08-08T16:00:00+07:00") as fake:
            report = we.build_report(self.evaluated, horizons=(3,))
        fake.assert_called_once_with()
        self.assertEqual(report["generated_at"], "2026-08-08T16:00:00+07:00")

    def test_real_call_is_vn_offset(self):
        report = we.build_report(self.evaluated, horizons=(3,))
        self.assertRegex(report["generated_at"], r"\+07:00$")

    def test_no_bare_astimezone_left_in_source(self):
        source = (ROOT / "watchlist_eval.py").read_text(encoding="utf-8")
        self.assertNotIn("astimezone()", source)


if __name__ == "__main__":
    unittest.main()
