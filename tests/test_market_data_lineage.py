from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vn_stock_pipeline as pipeline
from market_data_lineage import build_ohlcv_lineage_records, init_ohlcv_lineage_schema, upsert_ohlcv_lineage
from tools.qualify_price_basis import _series


def frame(source: str = "VCI") -> pd.DataFrame:
    result = pd.DataFrame([{"ticker": "HPG", "date": "2026-07-30", "open": 21000.0, "high": 22000.0,
                            "low": 20500.0, "close": 21800.0, "volume": 29968000, "source": source}])
    result.attrs["unit_scale"] = 1000
    return result


class MarketDataLineageTests(unittest.TestCase):
    def test_new_observation_retains_provider_version_and_source_record_hash(self):
        records = build_ohlcv_lineage_records(frame(), source="VCI", endpoint="https://provider.test/history",
                                              retrieved_at="2026-08-02T00:00:00Z", provider_version="4.0.4")
        self.assertEqual(records[0]["provider_version"], "4.0.4")
        self.assertEqual(records[0]["canonical_field"], "ohlcv.close")
        self.assertEqual(records[0]["unit_scale"], 1000)
        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(Path(tmp) / "market.db")
            init_ohlcv_lineage_schema(conn)
            upsert_ohlcv_lineage(conn, records)
            self.assertEqual(conn.execute("SELECT provider_version FROM ohlcv_lineage").fetchone()[0], "4.0.4")
            conn.close()

    def test_legacy_observation_remains_version_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "market.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE ohlcv(ticker TEXT, date TEXT, close REAL, source TEXT)")
            conn.execute("INSERT INTO ohlcv VALUES ('HPG', '2026-07-30', 21800, 'VCI')")
            conn.commit()
            self.assertEqual(_series(conn, "HPG")[0]["provider_version"], "legacy_version_unknown")
            conn.close()

    def test_source_scale_remains_provider_specific(self):
        raw = pd.DataFrame({"time": ["2026-07-30"], "open": [21.8], "high": [22.0], "low": [20.5],
                            "close": [21.8], "volume": [100]})
        self.assertEqual(pipeline.normalize(raw, "HPG", "VCI").attrs["unit_scale"], 1000)
        self.assertEqual(pipeline.normalize(raw, "HPG", "KBS").attrs["unit_scale"], 1000)
