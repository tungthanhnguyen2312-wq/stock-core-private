from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

from tools.dnse_index_return_series_shadow import build_report, find_ohlc_result, main
from vn_time import VN_TZ

REAL_INDEX_EVIDENCE = (
    Path(__file__).resolve().parents[2] / "operations-review"
    / "dnse-index-return-series-qualification-20260810" / "probe_results.json"
)


def _epoch(date_str: str, hour: int = 9) -> int:
    y, mo, d = (int(x) for x in date_str.split("-"))
    return int(datetime(y, mo, d, hour, 0, tzinfo=VN_TZ).timestamp())


def _make_runtime_with_index_ohlcv(tmp_dir: str, benchmark_id: str, rows: list[tuple[str, float]]) -> Path:
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, 'VCI')",
        [(benchmark_id, d, c, c, c, c) for d, c in rows],
    )
    conn.commit()
    conn.close()
    return root


def _two_identical_calls_evidence() -> dict:
    body = {"o": [1799.0, 1801.0], "h": [1810.0, 1812.0], "l": [1790.0, 1795.0],
            "c": [1806.63, 1801.5], "t": [_epoch("2026-07-14"), _epoch("2026-07-15")]}
    return {
        "results": [
            {"capability": "working_dates", "ok": True},
            {"capability": "ohlc", "ok": True, "endpoint": "/price/ohlc",
             "query_sent": {"symbol": "VNINDEX", "type": "INDEX", "resolution": "1D"},
             "body_redacted": body},
            {"capability": "ohlc", "ok": True, "endpoint": "/price/ohlc",
             "query_sent": {"symbol": "VNINDEX", "type": "INDEX", "resolution": "1D"},
             "body_redacted": body},
        ]
    }


class FindOhlcResultTests(unittest.TestCase):
    def test_picks_the_result_matching_the_requested_benchmark(self):
        evidence = _two_identical_calls_evidence()
        result = find_ohlc_result(evidence, "VNINDEX")
        self.assertEqual("VNINDEX", result["query_sent"]["symbol"])

    def test_is_case_insensitive(self):
        evidence = _two_identical_calls_evidence()
        self.assertIsNotNone(find_ohlc_result(evidence, "vnindex"))

    def test_returns_none_for_an_absent_benchmark(self):
        evidence = _two_identical_calls_evidence()
        self.assertIsNone(find_ohlc_result(evidence, "VN30"))


class BuildReportOfflineTests(unittest.TestCase):
    def test_no_evidence_for_ineligible_benchmark_fails_closed(self):
        report = build_report("VN30", None, runtime_root=Path("."))
        self.assertEqual("NOT_QUALIFIED_FOR_DNSE_INDEX_RETURN_SERIES", report["status"])
        self.assertEqual([], report["cross_check"])
        self.assertEqual("unqualified", report["level_unit_classification_this_window"])

    def test_evidence_file_resolves_and_cross_checks_the_correct_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "probe_results.json"
            evidence_path.write_text(json.dumps(_two_identical_calls_evidence()), encoding="utf-8")
            dates = ["2026-07-14", "2026-07-15"]
            closes = [1806.63, 1801.5]
            root = _make_runtime_with_index_ohlcv(tmp, "VNINDEX", list(zip(dates, closes)))
            report = build_report("VNINDEX", evidence_path, runtime_root=root)
        self.assertEqual("VNINDEX", report["benchmark_id"])
        self.assertEqual("/price/ohlc", report["provenance"]["fetch"]["endpoint"])
        self.assertEqual(2, len(report["cross_check"]))
        self.assertTrue(all(r["verdict"] == "consistent" for r in report["cross_check"]))
        self.assertEqual("index_points", report["level_unit_classification_this_window"])


@unittest.skipUnless(REAL_INDEX_EVIDENCE.exists(), "real retained VNINDEX index-return-series evidence not present")
class RealRetainedEvidenceCliTests(unittest.TestCase):
    """Step 12: real bounded VNINDEX experiment, via the actual CLI."""

    def test_real_evidence_produces_a_qualified_report_with_exact_cross_check(self):
        evidence = json.loads(REAL_INDEX_EVIDENCE.read_text(encoding="utf-8"))
        ohlc = find_ohlc_result(evidence, "VNINDEX")
        self.assertIsNotNone(ohlc)
        import datetime as _dt

        from vn_time import VN_TZ
        rows = [
            (_dt.datetime.fromtimestamp(t, tz=VN_TZ).date().isoformat(), c)
            for t, c in zip(ohlc["body_redacted"]["t"], ohlc["body_redacted"]["c"])
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_index_ohlcv(tmp, "VNINDEX", rows)
            report = build_report("VNINDEX", REAL_INDEX_EVIDENCE, runtime_root=root)
        self.assertEqual("QUALIFIED_CURRENT_STATE_BENCHMARK_RETURN_SERIES", report["status"])
        self.assertTrue(report["current_state_qualified"])
        self.assertEqual(19, report["coverage"]["session_count"])
        self.assertEqual(0.0, max(r["absolute_difference"] for r in report["cross_check"]))


class CliTests(unittest.TestCase):
    def test_missing_evidence_file_reports_error_and_exits_2(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--benchmark", "VNINDEX", "--evidence", "does-not-exist.json"])
        self.assertEqual(2, code)
        self.assertEqual("evidence_not_found", json.loads(output.getvalue())["status"])

    def test_no_evidence_flag_skips_file_lookup_for_a_fail_closed_benchmark(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--benchmark", "VN30", "--no-evidence", "--runtime-root", "."])
        self.assertEqual(0, code)
        summary = json.loads(output.getvalue())
        self.assertEqual("NOT_QUALIFIED_FOR_DNSE_INDEX_RETURN_SERIES", summary["status"])

    def test_write_flag_produces_a_deterministic_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "probe_results.json"
            evidence_path.write_text(json.dumps(_two_identical_calls_evidence()), encoding="utf-8")
            _make_runtime_with_index_ohlcv(tmp, "VNINDEX", [("2026-07-14", 1806.63), ("2026-07-15", 1801.5)])
            out_dir = Path(tmp) / "out"
            args = ["--benchmark", "VNINDEX", "--evidence", str(evidence_path),
                     "--runtime-root", tmp, "--out-dir", str(out_dir), "--write"]
            with redirect_stdout(io.StringIO()):
                main(args)
            written_path = out_dir / "shadow_report_VNINDEX.json"
            self.assertTrue(written_path.exists())
            first = written_path.read_text(encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                main(args)
            second = written_path.read_text(encoding="utf-8")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
