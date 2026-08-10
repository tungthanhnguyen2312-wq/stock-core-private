from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnse_market_risk_evidence_store as store  # noqa: E402
from tools.ingest_dnse_market_risk_evidence import find_ohlc_result, main, materialize  # noqa: E402

# runtime_paths.runtime_root() prefers the STOCK_LOOKUP_RUNTIME_ROOT env var
# over an explicit --runtime-root argument (project convention, matched by
# every ingestion CLI in this repo). CLI-level tests must not inherit an
# ambient value for this var from the shell that ran the suite -- doing so
# once during this milestone's own development silently wrote synthetic test
# data into the real dashboard-runtime store, immediately caught and
# corrected by re-running the real materialization. main_without_ambient_root()
# clears it explicitly so --runtime-root is honored regardless of the
# calling environment.


def main_without_ambient_root(argv: list[str]) -> int:
    with mock.patch.dict(os.environ):
        os.environ.pop("STOCK_LOOKUP_RUNTIME_ROOT", None)
        return main(argv)


def _evidence(symbol: str, kind: str, n: int = 3) -> dict:
    body = {"o": [24.0 + i for i in range(n)], "h": [24.5 + i for i in range(n)],
            "l": [23.5 + i for i in range(n)], "c": [24.2 + i for i in range(n)],
            "t": [1783994400 + i * 86400 for i in range(n)], "v": [1000 + i for i in range(n)]}
    return {"results": [
        {"capability": "working_dates", "ok": True},
        {"capability": "ohlc", "ok": True, "endpoint": "/price/ohlc",
         "query_sent": {"symbol": symbol, "type": kind, "resolution": "1D"}, "body_redacted": body},
    ]}


class FindOhlcResultTests(unittest.TestCase):
    def test_matches_by_symbol_case_insensitive(self):
        evidence = _evidence("HPG", "STOCK")
        self.assertIsNotNone(find_ohlc_result(evidence, "hpg"))

    def test_returns_none_for_absent_symbol(self):
        evidence = _evidence("HPG", "STOCK")
        self.assertIsNone(find_ohlc_result(evidence, "VNM"))


class MaterializeTests(unittest.TestCase):
    def test_materializes_both_symbols_into_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_path = Path(tmp) / "stock.json"
            bmk_path = Path(tmp) / "bmk.json"
            stock_path.write_text(json.dumps(_evidence("HPG", "STOCK", 5)), encoding="utf-8")
            bmk_path.write_text(json.dumps(_evidence("VNINDEX", "INDEX", 5)), encoding="utf-8")
            runtime_root = Path(tmp) / "runtime"
            report = materialize(stock_path, bmk_path, runtime_root, dry_run=False)
            stock_record = store.read_stock_ohlc(runtime_root, "HPG")
            bmk_record = store.read_benchmark_ohlc(runtime_root, "VNINDEX")
        self.assertEqual("materialized", report["stock"]["status"])
        self.assertEqual("materialized", report["benchmark"]["status"])
        self.assertEqual(5, stock_record["session_count"])
        self.assertEqual(5, bmk_record["session_count"])

    def test_dry_run_reports_but_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_path = Path(tmp) / "stock.json"
            bmk_path = Path(tmp) / "bmk.json"
            stock_path.write_text(json.dumps(_evidence("HPG", "STOCK")), encoding="utf-8")
            bmk_path.write_text(json.dumps(_evidence("VNINDEX", "INDEX")), encoding="utf-8")
            runtime_root = Path(tmp) / "runtime"
            materialize(stock_path, bmk_path, runtime_root, dry_run=True)
            self.assertIsNone(store.read_stock_ohlc(runtime_root, "HPG"))
            self.assertIsNone(store.read_benchmark_ohlc(runtime_root, "VNINDEX"))

    def test_symbol_absent_from_its_evidence_file_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_path = Path(tmp) / "stock.json"
            bmk_path = Path(tmp) / "bmk.json"
            stock_path.write_text(json.dumps(_evidence("HPG", "STOCK")), encoding="utf-8")
            bmk_path.write_text(json.dumps(_evidence("VNINDEX", "INDEX")), encoding="utf-8")
            runtime_root = Path(tmp) / "runtime"
            report = materialize(stock_path, bmk_path, runtime_root, ticker="VNM", dry_run=False)
        self.assertEqual("not_found_in_evidence", report["stock"]["status"])

    def test_re_running_materialize_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_path = Path(tmp) / "stock.json"
            bmk_path = Path(tmp) / "bmk.json"
            stock_path.write_text(json.dumps(_evidence("HPG", "STOCK", 4)), encoding="utf-8")
            bmk_path.write_text(json.dumps(_evidence("VNINDEX", "INDEX", 4)), encoding="utf-8")
            runtime_root = Path(tmp) / "runtime"
            materialize(stock_path, bmk_path, runtime_root, dry_run=False)
            first = store.read_stock_ohlc(runtime_root, "HPG")
            materialize(stock_path, bmk_path, runtime_root, dry_run=False)
            second = store.read_stock_ohlc(runtime_root, "HPG")
        self.assertEqual(first["raw_ohlc"], second["raw_ohlc"])
        self.assertEqual(4, second["session_count"])


class CliTests(unittest.TestCase):
    def test_missing_evidence_file_reports_error_and_exits_2(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--stock-evidence", "does-not-exist.json",
                         "--benchmark-evidence", "also-does-not-exist.json"])
        self.assertEqual(2, code)
        self.assertEqual("evidence_not_found", json.loads(output.getvalue())["status"])

    def test_cli_end_to_end_writes_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_path = Path(tmp) / "stock.json"
            bmk_path = Path(tmp) / "bmk.json"
            stock_path.write_text(json.dumps(_evidence("HPG", "STOCK")), encoding="utf-8")
            bmk_path.write_text(json.dumps(_evidence("VNINDEX", "INDEX")), encoding="utf-8")
            runtime_root = Path(tmp) / "runtime"
            output = io.StringIO()
            with redirect_stdout(output):
                code = main_without_ambient_root(
                    ["--stock-evidence", str(stock_path), "--benchmark-evidence", str(bmk_path),
                     "--runtime-root", str(runtime_root)])
            self.assertEqual(0, code)
            self.assertIsNotNone(store.read_stock_ohlc(runtime_root, "HPG"))


if __name__ == "__main__":
    unittest.main()
