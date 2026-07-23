from __future__ import annotations
import io
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import vn_indicators as indicators

REPO_ROOT = Path(__file__).resolve().parent.parent
VN_INDICATORS_PATH = REPO_ROOT / "vn_indicators.py"
PROD_RUNTIME_DB = REPO_ROOT.parent / "dashboard-runtime" / "vn_stock.db"

class NoReconfigure:
    pass

class ClosedReconfigure:
    def reconfigure(self, **_kwargs):
        raise ValueError("closed")

class Utf8StreamTests(unittest.TestCase):
    def test_cp1252_stream_is_reconfigured_before_vietnamese_output(self):
        raw=io.BytesIO(); stream=io.TextIOWrapper(raw, encoding="cp1252")
        indicators.configure_utf8_streams(stream, NoReconfigure())
        stream.write("Tính cục bộ"); stream.flush()
        self.assertIn("Tính cục bộ".encode("utf-8"), raw.getvalue())
    def test_utf8_stream_remains_writable(self):
        raw=io.BytesIO(); stream=io.TextIOWrapper(raw, encoding="utf-8")
        indicators.configure_utf8_streams(stream, stream)
        stream.write("Đã xử lý"); stream.flush()
        self.assertEqual(raw.getvalue().decode("utf-8"), "Đã xử lý")
    def test_stream_without_or_failing_reconfigure_is_safe(self):
        indicators.configure_utf8_streams(NoReconfigure(), ClosedReconfigure())
    def test_import_does_not_configure_streams(self):
        self.assertTrue(callable(indicators.configure_utf8_streams))


def _seed_runtime_db(db_path: Path, ticker: str = "HPG", n_bars: int = 70) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
    conn.execute(
        "CREATE TABLE metadata (ticker TEXT PRIMARY KEY, exchange TEXT, industry TEXT, "
        "foreign_room_pct REAL, pe REAL, pb REAL, roe REAL, free_float_est REAL, margin_status TEXT)")
    rows, day = [], datetime(2025, 1, 1)
    for i in range(n_bars):
        price = 25.0 + 2.0 * math.sin(i / 5.0) + 0.02 * i
        rows.append((ticker, day.strftime("%Y-%m-%d"), price, price + 0.3, price - 0.3, price + 0.1,
                      1_000_000 + i * 1_000))
        day += timedelta(days=1)
    conn.executemany("INSERT INTO ohlcv VALUES (?,?,?,?,?,?,?)", rows)
    conn.execute(
        "INSERT INTO metadata (ticker, exchange, industry, foreign_room_pct, pe, pb, roe, "
        "free_float_est, margin_status) VALUES (?,?,?,?,?,?,?,?,?)",
        (ticker, "HOSE", "Steel", 49.0, 10.0, 1.5, 15.0, 60.0, None))
    conn.commit()
    conn.close()


class SubprocessSmokeTests(unittest.TestCase):
    """Temporary-runtime smoke test: proves the UTF-8 fix end-to-end under a forced
    CP1252 stream, without ever touching the production runtime directory."""

    def test_vietnamese_output_is_utf8_safe_under_forced_cp1252_with_spaced_runtime_root(self):
        prod_stat_before = PROD_RUNTIME_DB.stat() if PROD_RUNTIME_DB.exists() else None

        with tempfile.TemporaryDirectory(prefix="vn_indicators_smoke_") as tmp:
            runtime_root = Path(tmp) / "runtime root with space"
            runtime_root.mkdir()
            _seed_runtime_db(runtime_root / "vn_stock.db")

            env = dict(os.environ)
            env["STOCK_LOOKUP_RUNTIME_ROOT"] = str(runtime_root)
            env["PYTHONIOENCODING"] = "cp1252"  # force a non-UTF-8 stream regardless of host console
            env.pop("PYTHONUTF8", None)

            result = subprocess.run(
                [sys.executable, str(VN_INDICATORS_PATH)],
                cwd=str(REPO_ROOT), env=env, capture_output=True, timeout=120)

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            self.assertEqual(result.returncode, 0, msg=f"stdout={stdout}\nstderr={stderr}")
            self.assertNotIn("UnicodeEncodeError", stdout)
            self.assertNotIn("UnicodeEncodeError", stderr)
            self.assertIn("Tính cục bộ", stdout)

            produced = {p.name for p in runtime_root.iterdir()}
            self.assertIn("screen_snapshot.csv", produced)
            self.assertIn("screen_snapshot_live.csv", produced)
            self.assertIn("market_breadth.csv", produced)

        if prod_stat_before is not None:
            prod_stat_after = PROD_RUNTIME_DB.stat()
            self.assertEqual(prod_stat_before.st_mtime_ns, prod_stat_after.st_mtime_ns)
            self.assertEqual(prod_stat_before.st_size, prod_stat_after.st_size)


if __name__ == '__main__': unittest.main()
