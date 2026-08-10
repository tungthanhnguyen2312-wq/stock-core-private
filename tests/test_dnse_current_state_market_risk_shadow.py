from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import dnse_current_state_market_risk as market_risk
from tools.dnse_current_state_market_risk_shadow import build_report, find_ohlc_result, main
from vn_time import VN_TZ

REAL_STOCK_EVIDENCE = (
    Path(__file__).resolve().parents[2] / "operations-review"
    / "dnse-current-state-price-analytics-20260810" / "probe_results.json"
)
REAL_BENCHMARK_EVIDENCE = (
    Path(__file__).resolve().parents[2] / "operations-review"
    / "dnse-index-return-series-qualification-20260810" / "probe_results.json"
)


def _epoch(date_str: str, hour: int = 9) -> int:
    y, mo, d = (int(x) for x in date_str.split("-"))
    return int(datetime(y, mo, d, hour, 0, tzinfo=VN_TZ).timestamp())


def _make_runtime(tmp_dir: str, rows_by_symbol: dict[str, list[tuple[str, float]]]) -> Path:
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    for symbol, rows in rows_by_symbol.items():
        conn.executemany(
            "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, 'VCI')",
            [(symbol, d, c, c, c, c) for d, c in rows],
        )
    conn.commit()
    conn.close()
    return root


def _stock_evidence(dates: list[str], closes: list[float]) -> dict:
    body = {"o": [c - 0.05 for c in closes], "h": [c + 0.10 for c in closes],
            "l": [c - 0.10 for c in closes], "c": list(closes), "t": [_epoch(d) for d in dates]}
    return {"results": [
        {"capability": "working_dates", "ok": True},
        {"capability": "ohlc", "ok": True, "endpoint": "/price/ohlc",
         "query_sent": {"symbol": "HPG", "type": "STOCK", "resolution": "1D"}, "body_redacted": body},
    ]}


def _benchmark_evidence(dates: list[str], closes: list[float]) -> dict:
    body = {"o": [c - 1.0 for c in closes], "h": [c + 2.0 for c in closes],
            "l": [c - 2.0 for c in closes], "c": list(closes), "t": [_epoch(d) for d in dates]}
    return {"results": [
        {"capability": "working_dates", "ok": True},
        {"capability": "ohlc", "ok": True, "endpoint": "/price/ohlc",
         "query_sent": {"symbol": "VNINDEX", "type": "INDEX", "resolution": "1D"}, "body_redacted": body},
    ]}


class FindOhlcResultTests(unittest.TestCase):
    def test_picks_the_result_matching_the_requested_symbol(self):
        evidence = _stock_evidence(["2026-07-14", "2026-07-15"], [24.0, 24.5])
        result = find_ohlc_result(evidence, "HPG")
        self.assertEqual("HPG", result["query_sent"]["symbol"])

    def test_is_case_insensitive(self):
        evidence = _stock_evidence(["2026-07-14", "2026-07-15"], [24.0, 24.5])
        self.assertIsNotNone(find_ohlc_result(evidence, "hpg"))

    def test_returns_none_for_an_absent_symbol(self):
        evidence = _stock_evidence(["2026-07-14", "2026-07-15"], [24.0, 24.5])
        self.assertIsNone(find_ohlc_result(evidence, "VNM"))


class BuildReportOfflineTests(unittest.TestCase):
    def test_synthetic_qualified_pair_produces_real_beta_and_correlation(self):
        dates = ["2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20"]
        hpg_closes = [24.0, 24.3, 24.1, 24.5, 24.4]
        vnindex_closes = [1250.0, 1256.0, 1252.0, 1261.0, 1258.0]
        with tempfile.TemporaryDirectory() as tmp:
            stock_path = Path(tmp) / "stock_evidence.json"
            bmk_path = Path(tmp) / "bmk_evidence.json"
            stock_path.write_text(json.dumps(_stock_evidence(dates, hpg_closes)), encoding="utf-8")
            bmk_path.write_text(json.dumps(_benchmark_evidence(dates, vnindex_closes)), encoding="utf-8")
            root = _make_runtime(tmp, {
                "HPG": list(zip(dates, hpg_closes)), "VNINDEX": list(zip(dates, vnindex_closes)),
            })
            report = build_report("HPG", "VNINDEX", stock_path, bmk_path, runtime_root=root)
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_QUALIFIED", report["qualification_status"])
        self.assertEqual(4, report["paired_return_count"])
        self.assertIsInstance(report["beta"]["value"], float)
        self.assertIsInstance(report["correlation"]["value"], float)

    def test_ineligible_ticker_and_benchmark_fail_closed_with_no_evidence_at_all(self):
        # Both VNM (stock) and VN30 (benchmark) are ineligible before any
        # OHLC payload is inspected, so no evidence file -- and no raw_ohlc
        # -- is ever required to reach a fail-closed result. An *eligible*
        # symbol (HPG/VNINDEX) with a missing payload instead raises inside
        # normalize_bars, per dnse_current_state_price_analytics.py's own
        # documented contract ("raises only for a structurally malformed
        # raw_ohlc on an already-eligible ticker") -- not this module's
        # concern to soften.
        report = build_report("VNM", "VN30", None, None, runtime_root=Path("."))
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED", report["qualification_status"])
        self.assertFalse(report["input_gates"]["stock_qualified"])
        self.assertFalse(report["input_gates"]["benchmark_qualified"])


@unittest.skipUnless(
    REAL_STOCK_EVIDENCE.exists() and REAL_BENCHMARK_EVIDENCE.exists(),
    "real retained HPG + VNINDEX evidence not present",
)
class RealHpgVnindexShadowTests(unittest.TestCase):
    """Steps 9 & 15: the real, bounded HPG x VNINDEX current-state shadow
    experiment, reusing evidence already retained by the two prior DNSE
    qualification milestones -- zero new network calls."""

    def _real_runtime_root(self, tmp: str) -> Path:
        stock_evidence = json.loads(REAL_STOCK_EVIDENCE.read_text(encoding="utf-8"))
        bmk_evidence = json.loads(REAL_BENCHMARK_EVIDENCE.read_text(encoding="utf-8"))
        stock_ohlc = find_ohlc_result(stock_evidence, "HPG")["body_redacted"]
        bmk_ohlc = find_ohlc_result(bmk_evidence, "VNINDEX")["body_redacted"]
        stock_rows = [
            (datetime.fromtimestamp(t, tz=VN_TZ).date().isoformat(), c)
            for t, c in zip(stock_ohlc["t"], stock_ohlc["c"])
        ]
        bmk_rows = [
            (datetime.fromtimestamp(t, tz=VN_TZ).date().isoformat(), c)
            for t, c in zip(bmk_ohlc["t"], bmk_ohlc["c"])
        ]
        return _make_runtime(tmp, {"HPG": stock_rows, "VNINDEX": bmk_rows})

    def test_real_shadow_qualifies_with_real_numeric_beta_and_correlation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._real_runtime_root(tmp)
            report = build_report(
                "HPG", "VNINDEX", REAL_STOCK_EVIDENCE, REAL_BENCHMARK_EVIDENCE, runtime_root=root,
            )
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_QUALIFIED", report["qualification_status"])
        self.assertEqual(18, report["paired_return_count"])
        self.assertEqual([], report["aligned_sessions"]["dropped_stock_sessions"])
        self.assertEqual([], report["aligned_sessions"]["dropped_benchmark_sessions"])
        self.assertIsInstance(report["beta"]["value"], float)
        self.assertIsInstance(report["correlation"]["value"], float)
        self.assertTrue(-1.0 <= report["correlation"]["value"] <= 1.0)
        self.assertFalse(report["pit_backtest_eligible"])
        # Printed (not asserted to an exact value) so the real numbers are
        # visible in the test log for this milestone's own reporting step.
        print(
            "\nREAL HPG x VNINDEX CURRENT-STATE SHADOW:",
            {"beta": report["beta"]["value"], "correlation": report["correlation"]["value"],
             "paired_return_count": report["paired_return_count"],
             "window": {
                 "first": report["aligned_sessions"]["aligned_pairs"][0]["session_date"],
                 "last": report["aligned_sessions"]["aligned_pairs"][-1]["session_date"],
             }},
        )

    def test_real_shadow_is_byte_identical_across_two_separate_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._real_runtime_root(tmp)
            first = build_report(
                "HPG", "VNINDEX", REAL_STOCK_EVIDENCE, REAL_BENCHMARK_EVIDENCE, runtime_root=root,
            )
            second = build_report(
                "HPG", "VNINDEX", REAL_STOCK_EVIDENCE, REAL_BENCHMARK_EVIDENCE, runtime_root=root,
            )
        self.assertEqual(market_risk.serialize(first), market_risk.serialize(second))


class FailClosedTickerCliTests(unittest.TestCase):
    """Step 10: VNM (unqualified DNSE price-analytics stock side) fails
    closed via the actual CLI. Robust regardless of whether the real
    evidence files exist -- VNM is absent from the HPG evidence file's own
    `query_sent.symbol`, so it fails purely on eligibility either way."""

    def test_vnm_fails_closed_via_cli(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--ticker", "VNM", "--benchmark", "VNINDEX",
                          "--stock-evidence", str(REAL_STOCK_EVIDENCE),
                          "--benchmark-evidence", str(REAL_BENCHMARK_EVIDENCE),
                          "--runtime-root", "."])
        self.assertEqual(0, code)
        summary = json.loads(output.getvalue())
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED", summary["qualification_status"])
        self.assertFalse(summary["input_gates"]["stock_qualified"])
        self.assertIsNone(summary["beta"]["value"])
        self.assertIsNone(summary["correlation"]["value"])


class CliWriteTests(unittest.TestCase):
    def test_write_flag_produces_a_deterministic_file(self):
        dates = ["2026-07-14", "2026-07-15", "2026-07-16"]
        hpg_closes = [24.0, 24.3, 24.1]
        vnindex_closes = [1250.0, 1256.0, 1252.0]
        with tempfile.TemporaryDirectory() as tmp:
            stock_path = Path(tmp) / "stock_evidence.json"
            bmk_path = Path(tmp) / "bmk_evidence.json"
            stock_path.write_text(json.dumps(_stock_evidence(dates, hpg_closes)), encoding="utf-8")
            bmk_path.write_text(json.dumps(_benchmark_evidence(dates, vnindex_closes)), encoding="utf-8")
            _make_runtime(tmp, {
                "HPG": list(zip(dates, hpg_closes)), "VNINDEX": list(zip(dates, vnindex_closes)),
            })
            out_dir = Path(tmp) / "out"
            args = ["--ticker", "HPG", "--benchmark", "VNINDEX",
                     "--stock-evidence", str(stock_path), "--benchmark-evidence", str(bmk_path),
                     "--runtime-root", tmp, "--out-dir", str(out_dir), "--write"]
            with redirect_stdout(io.StringIO()):
                main(args)
            written_path = out_dir / "shadow_report_HPG_VNINDEX.json"
            self.assertTrue(written_path.exists())
            first = written_path.read_text(encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                main(args)
            second = written_path.read_text(encoding="utf-8")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
