from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.dnse_current_state_analytics_shadow import build_report, find_ohlc_result, main

REAL_VCB_EVIDENCE = (
    Path(__file__).resolve().parents[2] / "operations-review"
    / "dnse-ohlc-price-basis-qualification-20260810" / "probe_results.json"
)


def _make_runtime_with_ohlcv(tmp_dir: str, ticker: str, dates: list[str]) -> Path:
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    conn.executemany("INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
                      "VALUES (?, ?, 1, 1, 1, 1, 1, 'VCI')", [(ticker, d) for d in dates])
    conn.commit()
    conn.close()
    return root


def _multi_ticker_evidence() -> dict:
    return {
        "results": [
            {"capability": "working_dates", "ok": True},
            {"capability": "ohlc", "ok": True, "endpoint": "/price/ohlc",
             "query_sent": {"symbol": "HPG", "resolution": "1D"},
             "body_redacted": {"o": [24.0], "h": [24.2], "l": [23.9], "c": [24.1], "t": [1781755200]}},
            {"capability": "ohlc", "ok": True, "endpoint": "/price/ohlc",
             "query_sent": {"symbol": "VCB", "resolution": "1D"},
             "body_redacted": {"o": [58.0], "h": [58.2], "l": [57.9], "c": [58.1], "t": [1781755200]}},
            {"capability": "ohlc", "ok": False, "endpoint": "/price/ohlc",
             "query_sent": {"symbol": "QNS", "resolution": "1D"}},
        ]
    }


class FindOhlcResultTests(unittest.TestCase):
    def test_picks_the_result_matching_the_requested_ticker(self):
        evidence = _multi_ticker_evidence()
        result = find_ohlc_result(evidence, "VCB")
        self.assertEqual("VCB", result["query_sent"]["symbol"])

    def test_is_case_insensitive(self):
        evidence = _multi_ticker_evidence()
        self.assertIsNotNone(find_ohlc_result(evidence, "hpg"))

    def test_returns_none_when_ticker_absent_or_result_not_ok(self):
        evidence = _multi_ticker_evidence()
        self.assertIsNone(find_ohlc_result(evidence, "QNS"))  # present but ok=False
        self.assertIsNone(find_ohlc_result(evidence, "VNM"))  # absent entirely


class BuildReportOfflineTests(unittest.TestCase):
    def test_no_evidence_path_for_ineligible_ticker_fails_closed(self):
        report = build_report("VNM", None, runtime_root=Path("."))
        self.assertEqual("NOT_QUALIFIED_FOR_DNSE_PRICE_ANALYTICS", report["status"])
        self.assertEqual({}, report["provenance"]["fetch"])

    def test_evidence_file_resolves_the_correct_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "probe_results.json"
            evidence_path.write_text(json.dumps(_multi_ticker_evidence()), encoding="utf-8")
            root = _make_runtime_with_ohlcv(tmp, "HPG", [])
            report = build_report("HPG", evidence_path, runtime_root=root)
        self.assertEqual("HPG", report["ticker"])
        self.assertEqual("/price/ohlc", report["provenance"]["fetch"]["endpoint"])
        self.assertEqual("HPG", report["provenance"]["fetch"]["query_sent"]["symbol"])


@unittest.skipUnless(REAL_VCB_EVIDENCE.exists(), "real retained VCB price-basis evidence not present")
class RealRetainedVcbEvidenceTests(unittest.TestCase):
    """Step 10: reuse the existing retained VCB price-basis evidence to prove
    gating, without any new network call."""

    def test_vcb_qualifies_from_the_real_retained_evidence_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = json.loads(REAL_VCB_EVIDENCE.read_text(encoding="utf-8"))
            ohlc = find_ohlc_result(evidence, "VCB")
            self.assertIsNotNone(ohlc, "expected a VCB ohlc result in the retained evidence")
            dates = set()
            import datetime as _dt
            from vn_time import VN_TZ
            for t in ohlc["body_redacted"]["t"]:
                dates.add(_dt.datetime.fromtimestamp(t, tz=VN_TZ).date().isoformat())
            root = _make_runtime_with_ohlcv(tmp, "VCB", sorted(dates))
            report = build_report("VCB", REAL_VCB_EVIDENCE, runtime_root=root)
        self.assertEqual("QUALIFIED_FOR_DNSE_CURRENT_STATE_PRICE_ANALYTICS", report["status"])
        self.assertEqual("complete", report["coverage"]["status"])
        self.assertGreater(report["returns"]["return_count"], 0)


class CliTests(unittest.TestCase):
    def test_missing_evidence_file_reports_error_and_exits_2(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--ticker", "HPG", "--evidence", "does-not-exist.json"])
        self.assertEqual(2, code)
        self.assertEqual("evidence_not_found", json.loads(output.getvalue())["status"])

    def test_no_evidence_flag_skips_file_lookup_for_a_fail_closed_ticker(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--ticker", "VNM", "--no-evidence", "--runtime-root", "."])
        self.assertEqual(0, code)
        summary = json.loads(output.getvalue())
        self.assertEqual("NOT_QUALIFIED_FOR_DNSE_PRICE_ANALYTICS", summary["status"])

    def test_write_flag_produces_a_deterministic_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "probe_results.json"
            evidence_path.write_text(json.dumps(_multi_ticker_evidence()), encoding="utf-8")
            _make_runtime_with_ohlcv(tmp, "HPG", [])
            out_dir = Path(tmp) / "out"
            args = ["--ticker", "HPG", "--evidence", str(evidence_path),
                    "--runtime-root", tmp, "--out-dir", str(out_dir), "--write"]
            with redirect_stdout(io.StringIO()):
                main(args)
            written_path = out_dir / "shadow_report_HPG.json"
            self.assertTrue(written_path.exists())
            first = written_path.read_text(encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                main(args)
            second = written_path.read_text(encoding="utf-8")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
