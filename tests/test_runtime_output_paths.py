"""Path-contract tests for mutable producer outputs."""
from __future__ import annotations
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candle_scan
import macro_sync
import news_sync
from runtime_paths import RUNTIME_ROOT_ENV

class RuntimeOutputPathTests(unittest.TestCase):
    def test_configured_runtime_root_routes_all_script_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = (Path(temp_dir) / "runtime").resolve()
            source_cwd = (Path(temp_dir) / "source").resolve()
            with mock.patch.dict(os.environ, {RUNTIME_ROOT_ENV: str(root)}, clear=False):
                macro = macro_sync.resolve_runtime_paths(source_cwd)
                news = news_sync.resolve_runtime_paths(source_cwd)
                candle = candle_scan.resolve_runtime_paths(source_cwd)
            self.assertEqual(macro[1], root / "vn_stock.db")
            self.assertEqual(macro[2:], (root / "macro_snapshot.csv", root / "data" / "macro_snapshot.json", root / "data" / "macro_snapshot.js"))
            self.assertEqual(news[1:], (root / "vn_stock.db", root / "news_latest.csv"))
            self.assertEqual(candle[1], root / "vn_stock.db")
            self.assertEqual(candle[2:7], (root / "ta_signals.csv", root / "ta_signals.json", root / "screen_snapshot.csv", root / "market_breadth.csv", root / "data"))
            for path in (*macro[1:], *news[1:], *candle[1:]):
                self.assertTrue(path.is_relative_to(root))
                self.assertFalse(path.is_relative_to(source_cwd))

    def test_unset_runtime_root_preserves_cwd_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cwd = (Path(temp_dir) / "legacy-cwd").resolve()
            with mock.patch.dict(os.environ, {RUNTIME_ROOT_ENV: ""}, clear=False):
                macro = macro_sync.resolve_runtime_paths(cwd)
                news = news_sync.resolve_runtime_paths(cwd)
                candle = candle_scan.resolve_runtime_paths(cwd)
            for paths in (macro, news, candle):
                self.assertEqual(paths[0], cwd)
                for path in paths[1:]:
                    self.assertTrue(path.is_relative_to(cwd))

if __name__ == "__main__":
    unittest.main()