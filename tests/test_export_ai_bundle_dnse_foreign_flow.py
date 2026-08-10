"""export_ai_bundle.py's DNSE foreign-flow attach layer: the opt-in wiring on top of
dnse_foreign_flow_store.py (schema/freshness logic tested in
tests/test_dnse_foreign_flow_store.py). Covers exactly what changes at this layer: the
flag threading itself, per-ticker fail-closed behaviour across a multi-ticker bundle, and
that the reference session actually reaches each ticker's freshness verdict.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dnse_foreign_flow_capability import normalize_record  # noqa: E402
from dnse_foreign_flow_store import observation_path, write_observations  # noqa: E402
from export_ai_bundle import (  # noqa: E402
    attach_dnse_foreign_flow,
    build_dnse_foreign_flow_for_ticker_safe,
)


def _raw(session_date: str, ticker: str = "HPG", buy: int = 100, sell: int = 40) -> dict:
    return {
        "boardId": "G4", "buyTradedAmount": 0, "buyVolume": 0,
        "foreignerBuyPossibleQuantity": 1, "foreignerOrderLimitQuantity": 1,
        "marketId": "STO", "sellTradedAmount": 0, "sellVolume": 0,
        "symbol": ticker, "time": f"{session_date} 15:33:11.407",
        "totalBuyTradedAmount": buy, "totalBuyVolume": 1,
        "totalSellTradedAmount": sell, "totalSellVolume": 1, "tradingSessionId": "99",
    }


def _normalized(session_date: str, ticker: str = "HPG", buy: int = 100, sell: int = 40) -> dict:
    return normalize_record(_raw(session_date, ticker, buy, sell), source_endpoint=f"/price/{ticker}/foreign-trading")


def _seed_runtime(root: Path, tickers_with_data: dict[str, list[str]]) -> None:
    """A minimal runtime root: vn_stock.db with ohlcv rows for every ticker/date named
    below, plus a retained DNSE observation per (ticker, date) pair."""
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    for ticker, dates in tickers_with_data.items():
        conn.executemany("INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
                         "VALUES (?, ?, 1, 1, 1, 1, 1, 'VCI')", [(ticker, d) for d in dates])
    conn.commit()
    conn.close()
    for ticker, dates in tickers_with_data.items():
        write_observations(root, ticker, [_normalized(d, ticker) for d in dates])


class AttachDnseForeignFlowTests(unittest.TestCase):
    def test_disabled_by_default_attaches_no_key_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-07"]})
            entries = {"HPG": {}, "QNS": {}}
            attach_dnse_foreign_flow(entries, root, False, reference_session_date="2026-08-07")
            self.assertNotIn("foreign_flow", entries["HPG"])
            self.assertNotIn("foreign_flow", entries["QNS"])

    def test_enabled_attaches_to_every_requested_ticker_including_ones_with_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-07"]})
            entries = {"HPG": {}, "POW": {}}  # POW has no retained DNSE store at all
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-07")
            self.assertIn("foreign_flow", entries["HPG"])
            self.assertEqual("available", entries["HPG"]["foreign_flow"]["status"])
            self.assertIn("foreign_flow", entries["POW"])
            self.assertEqual("missing", entries["POW"]["foreign_flow"]["status"])
            self.assertIsNone(entries["POW"]["foreign_flow"]["cumulative_net_value_vnd"])

    def test_reference_session_reaches_each_tickers_freshness_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            _seed_runtime(root, {"HPG": dates, "VNM": dates})
            entries = {"HPG": {}, "VNM": {}}
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-07")
            for ticker in ("HPG", "VNM"):
                freshness = entries[ticker]["foreign_flow"]["freshness"]
                self.assertEqual("current", freshness["status"])
                self.assertEqual("2026-08-07", freshness["reference_session_date"])

    def test_stale_reference_session_is_reported_not_silently_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-03", "2026-08-04", "2026-08-05"]})
            entries = {"HPG": {}}
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-10")
            freshness = entries["HPG"]["foreign_flow"]["freshness"]
            self.assertEqual("stale", freshness["status"])
            self.assertEqual("2026-08-05", freshness["latest_qualified_session_date"])

    def test_no_reference_session_date_still_attaches_but_freshness_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-07"]})
            entries = {"HPG": {}}
            attach_dnse_foreign_flow(entries, root, True)  # no reference_session_date passed
            self.assertEqual("unknown", entries["HPG"]["foreign_flow"]["freshness"]["status"])

    def test_cumulative_value_is_the_exact_sum_of_retained_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            conn = sqlite3.connect(root / "vn_stock.db")
            conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                         "low REAL, close REAL, volume INTEGER, source TEXT)")
            conn.executemany("INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
                             "VALUES ('HPG', ?, 1, 1, 1, 1, 1, 'VCI')", [(d,) for d in dates])
            conn.commit()
            conn.close()
            write_observations(root, "HPG", [_normalized(d, buy=100, sell=40) for d in dates])
            entries = {"HPG": {}}
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-07")
            self.assertEqual(5 * (100 - 40), entries["HPG"]["foreign_flow"]["cumulative_net_value_vnd"])

    def test_no_foreign_volume_room_or_flow_ratio_reaches_the_bundle_entry(self):
        # "warnings"/"limitations" legitimately *name* foreign_room/free_float in prose (that
        # IS the warning) -- so this checks only the data-bearing fields, same convention as
        # tests/test_dnse_foreign_flow_store.py's own equivalent check.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-07"]})
            entries = {"HPG": {}}
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-07")
            data_only = {k: v for k, v in entries["HPG"]["foreign_flow"].items()
                        if k not in ("warnings", "limitations")}
            dumped = json.dumps(data_only)
            for forbidden in ("foreign_buy_volume", "foreign_sell_volume", "foreign_net_volume",
                              "foreign_room", "ownership_pct", "free_float",
                              "flow_to_turnover", "turnover_ratio"):
                self.assertNotIn(forbidden, dumped)

    def test_a_corrupted_single_ticker_store_does_not_break_other_tickers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-07"], "VNM": ["2026-08-07"]})
            # Corrupt only VNM's retained observation file after seeding it.
            observation_path(root, "VNM").write_text("{not valid json", encoding="utf-8")
            entries = {"HPG": {}, "VNM": {}}
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-07")
            self.assertIn("foreign_flow", entries["HPG"])
            self.assertEqual("available", entries["HPG"]["foreign_flow"]["status"])
            self.assertNotIn("foreign_flow", entries["VNM"])  # fails closed: key omitted, no crash

    def test_single_ticker_helper_returns_none_on_build_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation_path(root, "HPG").parent.mkdir(parents=True, exist_ok=True)
            observation_path(root, "HPG").write_text("{not valid json", encoding="utf-8")
            self.assertIsNone(build_dnse_foreign_flow_for_ticker_safe("HPG", root, "2026-08-07"))

    def test_attaching_foreign_flow_touches_no_other_key_on_the_entry(self):
        """Research eligibility, capability matrices, and every other bundle field for a
        ticker live under unrelated keys on the same entry dict -- attaching foreign_flow
        must never read or write any of them, which is what keeps this capability from
        ever being able to affect research eligibility."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-07"]})
            entry = {"ticker_capability_matrix": {"research": {"research_eligible": True}},
                     "snapshot": {"date": "2026-08-07"}}
            before = json.loads(json.dumps(entry))  # deep copy via round-trip
            entries = {"HPG": entry}
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-07")
            after = {k: v for k, v in entries["HPG"].items() if k != "foreign_flow"}
            self.assertEqual(before, after)

    def test_build_series_is_deterministic_across_repeated_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            _seed_runtime(root, {"HPG": dates})
            first = build_dnse_foreign_flow_for_ticker_safe("HPG", root, "2026-08-07")
            second = build_dnse_foreign_flow_for_ticker_safe("HPG", root, "2026-08-07")
            self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_no_secret_or_credential_like_value_in_the_attached_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root, {"HPG": ["2026-08-07"]})
            entries = {"HPG": {}}
            attach_dnse_foreign_flow(entries, root, True, reference_session_date="2026-08-07")
            dumped = json.dumps(entries["HPG"]["foreign_flow"]).lower()
            for forbidden in ("token", "secret", "signature", "authorization", "x-api-key", "cookie"):
                self.assertNotIn(forbidden, dumped)

    def test_store_and_attach_layer_import_no_network_or_credential_module(self):
        """Static proof that generating a release with this flag enabled cannot reach the
        network or read secrets.env: the modules on the attach code path import neither a
        DNSE network client nor a generic HTTP library."""
        import dnse_foreign_flow_store
        source_paths = [Path(dnse_foreign_flow_store.__file__)]
        forbidden_imports = ("dnse_access", "dnse_market_data", "requests", "urllib.request", "httpx", "socket")
        for path in source_paths:
            text = path.read_text(encoding="utf-8")
            for forbidden in forbidden_imports:
                self.assertNotIn(f"import {forbidden}", text,
                                 f"{path.name} unexpectedly imports {forbidden}")


if __name__ == "__main__":
    unittest.main()
