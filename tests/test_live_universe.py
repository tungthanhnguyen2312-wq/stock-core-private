from __future__ import annotations
import os, tempfile, unittest
from pathlib import Path
from unittest import mock
import pandas as pd
import live_universe as universe
import stock_analyzer
import export_ai_bundle as exporter

class LiveUniverseTests(unittest.TestCase):
    def base(self):
        return pd.DataFrame([
            {"ticker":"AAA","date":"2026-07-22","exchange":"HSX"},
            {"ticker":"OLD","date":"2026-07-19","exchange":"HSX"},
            {"ticker":"DEL","date":"2026-07-22","exchange":"DELISTED"},
            {"ticker":"VNINDEX","date":"2026-07-22","exchange":"HSX"},
            {"ticker":"UNK","date":"2026-07-22","exchange":"HSX"},
        ])
    def master(self):
        return pd.DataFrame([{ "ticker":"AAA", "instrument_type":"STOCK", "listing_exchange":"HSX"},
                             { "ticker":"OLD", "instrument_type":"STOCK", "listing_exchange":"HSX"},
                             { "ticker":"DEL", "instrument_type":"STOCK", "listing_exchange":"DELISTED"},
                             { "ticker":"VNINDEX", "instrument_type":"INDEX", "listing_exchange":"HSX"}])
    def test_active_stale_delisted_index_and_unknown(self):
        out=universe.evaluate(self.base(),self.master()).set_index("ticker")
        self.assertEqual(out.at["AAA","live_universe_status"],"live")
        self.assertEqual(out.at["OLD","live_universe_reason"],"stale_price")
        self.assertEqual(out.at["DEL","live_universe_reason"],"listing_inactive_or_delisted")
        self.assertEqual(out.at["VNINDEX","live_universe_reason"],"index_or_synthetic")
        self.assertEqual(out.at["UNK","live_universe_status"],"unknown")
        self.assertEqual(out.at["AAA","reference_market_date"],"2026-07-22")
        self.assertEqual(out.at["OLD","days_stale"],3)
    def test_missing_master_fails_closed(self):
        out=universe.evaluate(self.base(),None)
        self.assertFalse(out["is_live"].any())
        self.assertTrue((out["live_universe_status"] != "live").all())
    def test_summary_hash_and_reasons(self):
        result=universe.summary(universe.evaluate(self.base(),self.master()))
        self.assertEqual(result["live_universe_count"],1); self.assertEqual(result["excluded_count"],4)
        self.assertEqual(result["reference_market_date"],"2026-07-22"); self.assertEqual(len(result["universe_hash"]),64)
    def test_analyzer_uses_same_live_status(self):
        frame=universe.evaluate(self.base(),self.master())
        self.assertEqual(stock_analyzer.current_live_universe(frame)["ticker"].tolist(),["AAA"])
    def test_exporter_requires_live_only_and_exposes_summary(self):
        with tempfile.TemporaryDirectory(prefix="live universe ") as raw:
            root=Path(raw); frame=universe.evaluate(self.base(),self.master())
            frame.to_csv(root/"screen_snapshot.csv",index=False,encoding="utf-8-sig")
            frame[frame.is_live].to_csv(root/"screen_snapshot_live.csv",index=False,encoding="utf-8-sig")
            with mock.patch.dict(os.environ,{exporter.RUNTIME_ROOT_ENV:str(root)},clear=False):
                _, info=exporter.load_live_snapshot_rows(["AAA"])
            self.assertEqual(info["live_universe"]["live_universe_count"],1); self.assertEqual(info["live_universe"]["excluded_count"],4); self.assertIn("stale_price", info["live_universe"]["excluded_by_reason"])
            frame.to_csv(root/"screen_snapshot_live.csv",index=False,encoding="utf-8-sig")
            with mock.patch.dict(os.environ,{exporter.RUNTIME_ROOT_ENV:str(root)},clear=False):
                with self.assertRaises(ValueError): exporter.load_live_snapshot_rows(["AAA"])
if __name__ == '__main__': unittest.main()
