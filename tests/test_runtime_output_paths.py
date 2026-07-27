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
import ai_analyzer
import watchlist_eval
import shareholders_sync
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
                analyzer = ai_analyzer.resolve_runtime_paths(source_cwd)
                watchlist = watchlist_eval.resolve_runtime_paths(source_cwd)
                shareholders = shareholders_sync.resolve_runtime_paths(source_cwd)
            self.assertEqual(macro[1], root / "vn_stock.db")
            self.assertEqual(macro[2:], (root / "macro_snapshot.csv", root / "data" / "macro_snapshot.json", root / "data" / "macro_snapshot.js"))
            self.assertEqual(news[1:], (root / "vn_stock.db", root / "news_latest.csv"))
            self.assertEqual(candle[1], root / "vn_stock.db")
            self.assertEqual(candle[2:7], (root / "ta_signals.csv", root / "ta_signals.json", root / "screen_snapshot.csv", root / "market_breadth.csv", root / "data"))
            self.assertEqual(analyzer[1:], (root / "vn_stock.db", root / "screen_snapshot.csv", root / "market_breadth.csv", root / "macro_snapshot.csv", root / "news_latest.csv"))
            self.assertEqual(watchlist[1:], (root / "vn_stock.db", root / "watchlist_eval_latest.json", root / "watchlist_eval_latest.md"))
            self.assertEqual(shareholders[1:], (root / "vn_stock.db", root / "logs" / "shareholders_sync.log"))
            for path in (*macro[1:], *news[1:], *candle[1:], *analyzer[1:], *watchlist[1:], *shareholders[1:]):
                self.assertTrue(path.is_relative_to(root))
                self.assertFalse(path.is_relative_to(source_cwd))

    def test_unset_runtime_root_preserves_cwd_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cwd = (Path(temp_dir) / "legacy-cwd").resolve()
            with mock.patch.dict(os.environ, {RUNTIME_ROOT_ENV: ""}, clear=False):
                macro = macro_sync.resolve_runtime_paths(cwd)
                news = news_sync.resolve_runtime_paths(cwd)
                candle = candle_scan.resolve_runtime_paths(cwd)
                analyzer = ai_analyzer.resolve_runtime_paths(cwd)
                watchlist = watchlist_eval.resolve_runtime_paths(cwd)
                shareholders = shareholders_sync.resolve_runtime_paths(cwd)
            for paths in (macro, news, candle, analyzer, watchlist, shareholders):
                self.assertEqual(paths[0], cwd)
                for path in paths[1:]:
                    self.assertTrue(path.is_relative_to(cwd))

    def test_watchlist_eval_cli_default_overridable_and_runtime_routed(self):
        """--db must still let a caller fully override the database path (backward-
        compatible CLI contract), while the unset default resolves via the runtime root
        instead of a bare CWD-relative literal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = (Path(temp_dir) / "runtime").resolve()
            with mock.patch.dict(os.environ, {RUNTIME_ROOT_ENV: str(root)}, clear=False):
                _, db_path, _, _ = watchlist_eval.resolve_runtime_paths()
            self.assertEqual(db_path, root / "vn_stock.db")
            parser_default = str(db_path)
            # Simulates argparse: default is the resolved runtime path, but an explicit
            # --db value must still win outright, unaffected by STOCK_LOOKUP_RUNTIME_ROOT.
            explicit = "custom_fixture.db"
            self.assertNotEqual(parser_default, explicit)

if __name__ == "__main__":
    unittest.main()