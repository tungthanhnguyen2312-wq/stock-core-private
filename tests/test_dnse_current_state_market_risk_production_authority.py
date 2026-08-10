"""Tests for the production (durable-evidence-store-backed) market-risk entry
point: dnse_current_state_market_risk.build_current_state_market_risk_from_evidence_store().

Covers the durable-evidence-authority milestone's own focused-test checklist:
exact reconstruction from a synthetic store, workspace-independence, freshness,
and fail-closed behaviour on missing/malformed durable evidence. The
underlying beta/correlation formula is untouched and separately tested in
tests/test_dnse_current_state_market_risk.py -- nothing here recomputes it.
"""
from __future__ import annotations

import inspect
import statistics
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import dnse_current_state_market_risk as m
import dnse_current_state_price_analytics as price_analytics
import dnse_index_return_series_capability as index_capability
import dnse_market_risk_evidence_store as evidence_store
from vn_time import VN_TZ

_SESSION_DATES = [
    "2026-06-18", "2026-06-19", "2026-06-22", "2026-06-23", "2026-06-24",
    "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30", "2026-07-01",
]
_HPG_CLOSES = [24.10, 24.30, 24.20, 24.50, 24.40, 24.60, 24.55, 24.70, 24.65, 24.80]
_VNINDEX_CLOSES = [1250.0, 1255.0, 1252.0, 1260.0, 1258.0, 1265.0, 1262.0, 1270.0, 1268.0, 1275.0]


def _epoch(date_str: str, hour: int = 2) -> int:
    y, mo, d = (int(x) for x in date_str.split("-"))
    return int(datetime(y, mo, d, hour, 0, tzinfo=VN_TZ).timestamp())


def _stock_raw(dates: list[str], closes: list[float]) -> dict:
    return {"o": [c - 0.05 for c in closes], "h": [c + 0.10 for c in closes],
            "l": [c - 0.10 for c in closes], "c": list(closes), "t": [_epoch(d) for d in dates]}


def _bmk_raw(dates: list[str], closes: list[float]) -> dict:
    return {"o": [c - 1.0 for c in closes], "h": [c + 2.0 for c in closes],
            "l": [c - 2.0 for c in closes], "c": list(closes), "t": [_epoch(d) for d in dates]}


def _seed_runtime(tmp_dir: str, *, with_evidence: bool = True) -> Path:
    """A minimal runtime root with vn_stock.db trading-date rows for HPG and
    VNINDEX, plus (unless with_evidence=False) a fully materialized durable
    evidence store -- exercising the same store module the real ingestion
    tool writes into, not a hand-rolled shortcut."""
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    for symbol, dates in (("HPG", _SESSION_DATES), ("VNINDEX", _SESSION_DATES)):
        conn.executemany(
            "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
            "VALUES (?, ?, 1, 1, 1, 1, 1, 'VCI')", [(symbol, d) for d in dates],
        )
    conn.commit()
    conn.close()
    if with_evidence:
        evidence_store.write_stock_ohlc(root, "HPG", _stock_raw(_SESSION_DATES, _HPG_CLOSES),
                                        provenance={"materialized_from": "test"})
        evidence_store.write_benchmark_ohlc(root, "VNINDEX", _bmk_raw(_SESSION_DATES, _VNINDEX_CLOSES),
                                            provenance={"materialized_from": "test"})
    return root


class ExactReconstructionTests(unittest.TestCase):
    """Step 12 items 3-7: retained evidence reconstructs exact stock/benchmark
    returns, beta, correlation, and paired count -- cross-checked against
    Python's stdlib statistics module as an independent oracle, same
    convention as tests/test_dnse_current_state_market_risk.py."""

    def test_qualifies_with_exact_expected_paired_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_QUALIFIED", result["qualification_status"])
        self.assertEqual(9, result["paired_return_count"])

    def test_beta_and_correlation_match_independent_recomputation(self):
        stock_returns = [c / p - 1.0 for p, c in zip(_HPG_CLOSES, _HPG_CLOSES[1:])]
        bmk_returns = [c / p - 1.0 for p, c in zip(_VNINDEX_CLOSES, _VNINDEX_CLOSES[1:])]
        expected_beta = statistics.covariance(stock_returns, bmk_returns) / statistics.variance(bmk_returns)
        expected_corr = statistics.correlation(stock_returns, bmk_returns)
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertAlmostEqual(expected_beta, result["beta"]["value"], places=9)
        self.assertAlmostEqual(expected_corr, result["correlation"]["value"], places=9)

    def test_real_materialized_store_reproduces_the_exact_qualified_values(self):
        """Against the actual dashboard-runtime durable store materialized by
        this milestone (not a synthetic fixture) -- the same real numbers
        reported throughout this milestone's own validation."""
        root = Path(__file__).resolve().parents[1].parent / "dashboard-runtime"
        if not evidence_store.read_stock_ohlc(root, "HPG"):
            self.skipTest("real materialized dashboard-runtime store not present")
        result = m.build_current_state_market_risk_from_evidence_store(
            "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-08-07",
        )
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_QUALIFIED", result["qualification_status"])
        self.assertEqual(0.8093285134496059, result["beta"]["value"])
        self.assertEqual(0.5664164065437041, result["correlation"]["value"])
        self.assertEqual(18, result["paired_return_count"])
        self.assertEqual("current", result["freshness"]["status"])


class WorkspaceIndependenceTests(unittest.TestCase):
    """Step 12 items 1-2: the production loader depends only on the durable
    store; the workspace-relative operations-review/ path is never touched."""

    def test_production_loader_never_references_the_workspace_evidence_constants(self):
        # The function's own docstring legitimately *names* operations-review/
        # in prose (clarifying that it does NOT depend on it) -- so this checks
        # the real proof (the workspace-evidence constant names are absent from
        # the code), not a bare "operations-review" substring.
        source = inspect.getsource(m.build_current_state_market_risk_from_evidence_store)
        self.assertNotIn("DEFAULT_STOCK_EVIDENCE_PATH", source)
        self.assertNotIn("DEFAULT_BENCHMARK_EVIDENCE_PATH", source)
        self.assertNotIn("_load_raw_ohlc_from_evidence", source)

    def test_reproduces_correctly_with_workspace_evidence_path_pointed_at_nothing(self):
        """Directly simulates 'operations-review access removed': the old
        workspace-evidence constants are repointed at a path that cannot
        exist, and the production entry point is proven unaffected."""
        original_stock = m.DEFAULT_STOCK_EVIDENCE_PATH
        original_bmk = m.DEFAULT_BENCHMARK_EVIDENCE_PATH
        try:
            m.DEFAULT_STOCK_EVIDENCE_PATH = Path("Z:/does/not/exist/stock.json")
            m.DEFAULT_BENCHMARK_EVIDENCE_PATH = Path("Z:/does/not/exist/bmk.json")
            with tempfile.TemporaryDirectory() as tmp:
                root = _seed_runtime(tmp)
                result = m.build_current_state_market_risk_from_evidence_store(
                    "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
                )
            self.assertEqual("CURRENT_STATE_BETA_CORRELATION_QUALIFIED", result["qualification_status"])
        finally:
            m.DEFAULT_STOCK_EVIDENCE_PATH = original_stock
            m.DEFAULT_BENCHMARK_EVIDENCE_PATH = original_bmk


class ReplayDeterminismTests(unittest.TestCase):
    """Step 12 item 8."""

    def test_two_runs_against_the_same_store_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            first = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
            second = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual(m.serialize(first), m.serialize(second))


class FailClosedDurableEvidenceTests(unittest.TestCase):
    """Step 12 items 9-10: malformed/missing durable evidence fails closed,
    never crashes, never fabricates a value."""

    def test_missing_evidence_for_an_eligible_ticker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp, with_evidence=False)
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED", result["qualification_status"])
        self.assertIsNone(result["beta"]["value"])
        self.assertIsNone(result["correlation"]["value"])

    def test_malformed_stock_evidence_fails_closed_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            evidence_store.stock_ohlc_path(root, "HPG").write_text("{not valid json", encoding="utf-8")
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED", result["qualification_status"])
        self.assertIsNone(result["beta"]["value"])

    def test_malformed_benchmark_evidence_fails_closed_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            evidence_store.benchmark_ohlc_path(root, "VNINDEX").write_text("{not valid json", encoding="utf-8")
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED", result["qualification_status"])
        self.assertIsNone(result["correlation"]["value"])

    def test_structurally_incomplete_but_valid_json_evidence_fails_closed(self):
        """Valid JSON, but the raw_ohlc sub-object is missing a required key
        (e.g. a hand-corrupted or version-incompatible file) -- a different
        malformation class from a JSON parse error, must fail closed the
        same way."""
        import json as _json
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            path = evidence_store.stock_ohlc_path(root, "HPG")
            payload = _json.loads(path.read_text(encoding="utf-8"))
            del payload["raw_ohlc"]["c"]
            path.write_text(_json.dumps(payload), encoding="utf-8")
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual("CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED", result["qualification_status"])
        self.assertIsNone(result["beta"]["value"])

    def test_other_production_tickers_fail_closed_via_the_production_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            for ticker in ("POW", "SSI", "EVF", "PAN", "PNJ", "FPT", "QNS", "VNM", "PVD", "NVL"):
                result = m.build_current_state_market_risk_from_evidence_store(
                    ticker, "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
                )
                self.assertEqual("CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED",
                                 result["qualification_status"], ticker)
                self.assertIsNone(result["beta"]["value"], ticker)


class FreshnessTests(unittest.TestCase):
    """Step 9 / Step 12 item 21: stale reference session handled honestly --
    a stale result stays visible with a warning, never silently relabelled
    current, never suppressed."""

    def test_matching_reference_session_is_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual("current", result["freshness"]["status"])
        self.assertEqual(0, result["freshness"]["sessions_behind"])

    def test_future_reference_session_is_stale_but_beta_correlation_remain_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            # A later trading date than any retained evidence -- must not be
            # silently treated as "current".
            conn = sqlite3.connect(root / "vn_stock.db")
            conn.execute("INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
                        "VALUES ('HPG', '2026-07-02', 1,1,1,1,1,'VCI')")
            conn.commit()
            conn.close()
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-02",
            )
        self.assertEqual("stale", result["freshness"]["status"])
        self.assertEqual(1, result["freshness"]["sessions_behind"])
        # Not hidden, not fabricated as current -- still the real, exact,
        # bounded historical value.
        self.assertIsNotNone(result["beta"]["value"])
        self.assertIsNotNone(result["correlation"]["value"])
        self.assertIn("retained_market_risk_evidence_is_stale_relative_to_the_release_reference_session",
                      result["warnings"])

    def test_no_reference_session_date_is_unknown_not_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            result = m.build_current_state_market_risk_from_evidence_store("HPG", "VNINDEX", runtime_root=root)
        self.assertEqual("unknown", result["freshness"]["status"])

    def test_not_qualified_ticker_has_not_applicable_freshness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            result = m.build_current_state_market_risk_from_evidence_store(
                "VNM", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual("not_applicable", result["freshness"]["status"])


class SampleAdequacyUnchangedTests(unittest.TestCase):
    """Step 10 / Step 12 item 20: no new statistical-confidence threshold is
    introduced by the production path."""

    def test_sample_adequacy_is_mathematically_computable_not_a_new_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            result = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertEqual(m.SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE, result["beta"]["sample_adequacy"])
        for forbidden in ("STATISTICALLY_STRONG", "HIGH_CONFIDENCE", "ROBUST", "STABLE"):
            self.assertNotIn(forbidden, m.serialize(result))

    def test_min_paired_observations_constant_unchanged(self):
        self.assertEqual(2, m.MIN_PAIRED_OBSERVATIONS)


class NoNetworkRequiredTests(unittest.TestCase):
    """Step 12 items 11/24: no network/secrets import anywhere on the
    production durable-evidence chain."""

    def test_evidence_store_and_production_loader_import_no_network_module(self):
        source_paths = [
            Path(evidence_store.__file__),
            Path(m.__file__),
        ]
        forbidden_imports = ("dnse_access", "dnse_market_data", "requests", "urllib.request",
                             "httpx", "socket")
        for path in source_paths:
            text = path.read_text(encoding="utf-8")
            for forbidden in forbidden_imports:
                self.assertNotIn(f"import {forbidden}", text, f"{path.name} unexpectedly imports {forbidden}")


class PitStillFalseTests(unittest.TestCase):
    """Step 12 item 19."""

    def test_pit_backtest_eligible_always_false_via_production_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _seed_runtime(tmp)
            qualified = m.build_current_state_market_risk_from_evidence_store(
                "HPG", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
            not_qualified = m.build_current_state_market_risk_from_evidence_store(
                "VNM", "VNINDEX", runtime_root=root, reference_session_date="2026-07-01",
            )
        self.assertIs(False, qualified["pit_backtest_eligible"])
        self.assertIs(False, not_qualified["pit_backtest_eligible"])


if __name__ == "__main__":
    unittest.main()
