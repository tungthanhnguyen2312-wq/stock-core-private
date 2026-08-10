from __future__ import annotations

import sqlite3
import statistics
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import dnse_current_state_market_risk as m
import dnse_current_state_price_analytics as price_analytics
import dnse_index_return_series_capability as index_capability
from vn_time import VN_TZ

# Real, shape-matched HPG/VNINDEX-like values over 10 consecutive trading
# sessions (no corporate action in this window -- values chosen only to
# exercise the math, not reused from any retained evidence file). Mirrors
# tests/test_dnse_current_state_price_analytics.py's own convention.
_SESSION_DATES = [
    "2026-06-18", "2026-06-19", "2026-06-22", "2026-06-23", "2026-06-24",
    "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30", "2026-07-01",
]
_HPG_CLOSES = [
    24.10, 24.30, 24.20, 24.50, 24.40,
    24.60, 24.55, 24.70, 24.65, 24.80,
]
_VNINDEX_CLOSES = [
    1250.0, 1255.0, 1252.0, 1260.0, 1258.0,
    1265.0, 1262.0, 1270.0, 1268.0, 1275.0,
]


def _epoch(date_str: str, hour: int = 2) -> int:
    y, mo, d = (int(x) for x in date_str.split("-"))
    return int(datetime(y, mo, d, hour, 0, tzinfo=VN_TZ).timestamp())


def _stock_ohlc_payload(dates: list[str], closes: list[float]) -> dict:
    return {
        "o": [c - 0.05 for c in closes], "h": [c + 0.10 for c in closes],
        "l": [c - 0.10 for c in closes], "c": list(closes),
        "t": [_epoch(d) for d in dates],
    }


def _index_ohlc_payload(dates: list[str], closes: list[float]) -> dict:
    return {
        "o": [c - 1.0 for c in closes], "h": [c + 2.0 for c in closes],
        "l": [c - 2.0 for c in closes], "c": list(closes),
        "t": [_epoch(d) for d in dates],
    }


def _make_runtime(tmp_dir: str, rows_by_symbol: dict[str, list[str]]) -> Path:
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    for symbol, dates in rows_by_symbol.items():
        conn.executemany(
            "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
            "VALUES (?, ?, 1, 1, 1, 1, 1, 'VCI')",
            [(symbol, d) for d in dates],
        )
    conn.commit()
    conn.close()
    return root


def _qualified_hpg_vnindex_reports(tmp_dir: str) -> tuple[dict, dict]:
    root = _make_runtime(tmp_dir, {"HPG": _SESSION_DATES, "VNINDEX": _SESSION_DATES})
    stock_report = price_analytics.build_shadow_report(
        "HPG", _stock_ohlc_payload(_SESSION_DATES, _HPG_CLOSES), runtime_root=root,
        include_technical_indicators=False,
    )
    benchmark_series = index_capability.build_index_return_series(
        "VNINDEX", _index_ohlc_payload(_SESSION_DATES, _VNINDEX_CLOSES), runtime_root=root,
    )
    return stock_report, benchmark_series


def _returns_row(date: str, prior_date: str, ret: float) -> dict:
    return {"session_date": date, "prior_session_date": prior_date,
            "close": 1.0, "prior_close": 1.0, "simple_return": ret}


class QualifiedInputAcceptedTests(unittest.TestCase):
    """Step 14 items 1-2: qualified HPG stock input and qualified VNINDEX
    benchmark input are both accepted."""

    def test_hpg_stock_gate_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, _ = _qualified_hpg_vnindex_reports(tmp)
        ok, reason = m._stock_input_gate(stock_report)
        self.assertTrue(ok, reason)
        self.assertIsNone(reason)

    def test_vnindex_benchmark_gate_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
        ok, reason = m._benchmark_input_gate(benchmark_series)
        self.assertTrue(ok, reason)
        self.assertIsNone(reason)

    def test_full_contract_qualifies_with_real_shaped_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            record = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        self.assertEqual(m.STATUS_QUALIFIED, record["qualification_status"])
        self.assertEqual(9, record["paired_return_count"])
        self.assertIsInstance(record["beta"]["value"], float)
        self.assertIsInstance(record["correlation"]["value"], float)


class UnqualifiedStockRejectedTests(unittest.TestCase):
    """Step 14 item 3 / Step 10: an unqualified stock ticker (VNM) is rejected."""

    def test_vnm_stock_gate_fails_closed(self):
        vnm_report = price_analytics.build_shadow_report("VNM", None, runtime_root=None)
        ok, reason = m._stock_input_gate(vnm_report)
        self.assertFalse(ok)
        self.assertEqual("stock_ticker_not_qualified_for_dnse_current_state_price_analytics", reason)

    def test_full_contract_not_qualified_for_vnm(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
        vnm_report = price_analytics.build_shadow_report("VNM", None, runtime_root=None)
        record = m.compute_current_state_beta_correlation(vnm_report, benchmark_series)
        self.assertEqual(m.STATUS_NOT_QUALIFIED, record["qualification_status"])
        self.assertEqual(
            "stock_ticker_not_qualified_for_dnse_current_state_price_analytics",
            record["input_gates"]["stock_reason"],
        )
        self.assertIsNone(record["beta"]["value"])
        self.assertIsNone(record["correlation"]["value"])

    def test_every_other_production_ticker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            for ticker in ("POW", "SSI", "EVF", "PAN", "PNJ", "FPT", "QNS", "VNM", "PVD", "NVL"):
                report = price_analytics.build_shadow_report(ticker, None, runtime_root=None)
                record = m.compute_current_state_beta_correlation(report, benchmark_series)
                self.assertEqual(m.STATUS_NOT_QUALIFIED, record["qualification_status"], ticker)


class UnsupportedBenchmarkRejectedTests(unittest.TestCase):
    """Step 14 item 4: an unsupported benchmark (VN30) is rejected."""

    def test_vn30_benchmark_gate_fails_closed(self):
        vn30_series = index_capability.build_index_return_series("VN30", None, runtime_root=None)
        ok, reason = m._benchmark_input_gate(vn30_series)
        self.assertFalse(ok)
        self.assertEqual("benchmark_not_qualified_for_dnse_current_state_return_series", reason)

    def test_full_contract_not_qualified_for_vn30(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, _ = _qualified_hpg_vnindex_reports(tmp)
        vn30_series = index_capability.build_index_return_series("VN30", None, runtime_root=None)
        record = m.compute_current_state_beta_correlation(stock_report, vn30_series)
        self.assertEqual(m.STATUS_NOT_QUALIFIED, record["qualification_status"])
        self.assertIsNone(record["beta"]["value"])


class SessionAlignmentTests(unittest.TestCase):
    """Step 14 items 5, 7, 8, 9: exact session alignment, missing sessions
    visible, no forward fill, deterministic pairing."""

    def test_exact_intersection_only(self):
        stock_returns = [
            _returns_row("2026-07-01", "2026-06-30", 0.01),
            _returns_row("2026-07-02", "2026-07-01", 0.02),
            _returns_row("2026-07-03", "2026-07-02", -0.01),  # stock-only
        ]
        bmk_returns = [
            _returns_row("2026-07-01", "2026-06-30", 0.005),
            _returns_row("2026-07-02", "2026-07-01", 0.006),
            _returns_row("2026-07-06", "2026-07-03", 0.001),  # benchmark-only
        ]
        alignment = m.align_current_state_returns(stock_returns, bmk_returns)
        self.assertEqual("aligned", alignment["status"])
        self.assertEqual(2, alignment["paired_return_count"])
        self.assertEqual(["2026-07-01", "2026-07-02"],
                          [p["session_date"] for p in alignment["aligned_pairs"]])

    def test_missing_sessions_are_visible_not_hidden(self):
        stock_returns = [_returns_row("2026-07-01", "2026-06-30", 0.01),
                          _returns_row("2026-07-03", "2026-07-02", -0.01)]
        bmk_returns = [_returns_row("2026-07-01", "2026-06-30", 0.005)]
        alignment = m.align_current_state_returns(stock_returns, bmk_returns)
        self.assertEqual(["2026-07-03"], alignment["dropped_stock_sessions"])
        self.assertEqual([], alignment["dropped_benchmark_sessions"])
        self.assertEqual(2, alignment["stock_return_count"])
        self.assertEqual(1, alignment["benchmark_return_count"])

    def test_no_forward_fill_unmatched_dates_never_appear_in_pairs(self):
        stock_returns = [_returns_row("2026-07-01", "2026-06-30", 0.01)]
        bmk_returns = [_returns_row("2026-07-02", "2026-07-01", 0.005)]
        alignment = m.align_current_state_returns(stock_returns, bmk_returns)
        self.assertEqual(0, alignment["paired_return_count"])
        self.assertEqual([], alignment["aligned_pairs"])

    def test_alignment_is_deterministic(self):
        stock_returns = [_returns_row("2026-07-01", "2026-06-30", 0.01),
                          _returns_row("2026-07-02", "2026-07-01", 0.02)]
        bmk_returns = [_returns_row("2026-07-01", "2026-06-30", 0.005),
                        _returns_row("2026-07-02", "2026-07-01", 0.006)]
        first = m.align_current_state_returns(stock_returns, bmk_returns)
        second = m.align_current_state_returns(stock_returns, bmk_returns)
        self.assertEqual(first, second)


class DuplicateSessionRejectedTests(unittest.TestCase):
    """Step 14 item 6: a duplicate session_date on either side is rejected."""

    def test_duplicate_stock_session_rejected(self):
        stock_returns = [_returns_row("2026-07-01", "2026-06-30", 0.01),
                          _returns_row("2026-07-01", "2026-06-30", 0.02)]
        bmk_returns = [_returns_row("2026-07-01", "2026-06-30", 0.005)]
        alignment = m.align_current_state_returns(stock_returns, bmk_returns)
        self.assertEqual("rejected", alignment["status"])
        self.assertEqual("duplicate_session_date_on_stock_side", alignment["reason"])

    def test_duplicate_benchmark_session_rejected(self):
        stock_returns = [_returns_row("2026-07-01", "2026-06-30", 0.01)]
        bmk_returns = [_returns_row("2026-07-01", "2026-06-30", 0.005),
                        _returns_row("2026-07-01", "2026-06-30", 0.006)]
        alignment = m.align_current_state_returns(stock_returns, bmk_returns)
        self.assertEqual("rejected", alignment["status"])
        self.assertEqual("duplicate_session_date_on_benchmark_side", alignment["reason"])


class BetaCorrelationFormulaTests(unittest.TestCase):
    """Step 14 items 10-11: beta/correlation formulas match project
    convention (sample covariance/variance, n - 1 denominator) -- verified
    against Python's stdlib `statistics` module as an independent oracle,
    not against a second copy of this module's own arithmetic."""

    _STOCK = [0.012, -0.008, 0.020, -0.015, 0.005, 0.010, -0.002, 0.018]
    _BMK = [0.006, -0.004, 0.011, -0.009, 0.002, 0.007, -0.001, 0.010]

    def _pairs(self) -> list[dict]:
        return [{"session_date": f"d{i}", "stock_return": s, "benchmark_return": b}
                 for i, (s, b) in enumerate(zip(self._STOCK, self._BMK))]

    def test_beta_matches_cov_over_var_sample_convention(self):
        result = m.compute_beta_and_correlation(self._pairs())
        expected_beta = statistics.covariance(self._STOCK, self._BMK) / statistics.variance(self._BMK)
        self.assertAlmostEqual(expected_beta, result["beta"], places=9)

    def test_correlation_matches_pearson_sample_convention(self):
        result = m.compute_beta_and_correlation(self._pairs())
        expected_corr = statistics.correlation(self._STOCK, self._BMK)
        self.assertAlmostEqual(expected_corr, result["correlation"], places=9)

    def test_mathematically_computable_is_not_labelled_statistically_strong(self):
        result = m.compute_beta_and_correlation(self._pairs())
        self.assertEqual(m.SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE, result["sample_adequacy"])
        self.assertNotIn("STATISTICALLY_STRONG", str(result))


class ZeroBenchmarkVarianceTests(unittest.TestCase):
    """Step 14 item 12: zero benchmark variance fails closed for both
    metrics (correlation's denominator also includes benchmark variance)."""

    def test_zero_benchmark_variance_fails_closed(self):
        pairs = [{"session_date": f"d{i}", "stock_return": r, "benchmark_return": 0.01}
                  for i, r in enumerate([0.01, -0.02, 0.015, 0.03])]
        result = m.compute_beta_and_correlation(pairs)
        self.assertIsNone(result["beta"])
        self.assertIsNone(result["correlation"])
        self.assertEqual("zero_or_near_zero_benchmark_variance", result["beta_reason"])
        self.assertEqual("zero_or_near_zero_benchmark_variance", result["correlation_reason"])
        self.assertEqual(m.SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE, result["sample_adequacy"])


class InsufficientObservationsTests(unittest.TestCase):
    """Step 14 item 13: fewer than MIN_PAIRED_OBSERVATIONS fails closed."""

    def test_zero_pairs_fails_closed(self):
        result = m.compute_beta_and_correlation([])
        self.assertIsNone(result["beta"])
        self.assertEqual(m.SAMPLE_ADEQUACY_INSUFFICIENT, result["sample_adequacy"])

    def test_one_pair_fails_closed(self):
        pairs = [{"session_date": "d0", "stock_return": 0.01, "benchmark_return": 0.005}]
        result = m.compute_beta_and_correlation(pairs)
        self.assertIsNone(result["beta"])
        self.assertEqual(m.SAMPLE_ADEQUACY_INSUFFICIENT, result["sample_adequacy"])

    def test_two_pairs_is_the_mathematical_floor_and_succeeds(self):
        pairs = [{"session_date": "d0", "stock_return": 0.01, "benchmark_return": 0.005},
                  {"session_date": "d1", "stock_return": -0.02, "benchmark_return": -0.01}]
        result = m.compute_beta_and_correlation(pairs)
        self.assertEqual(m.SAMPLE_ADEQUACY_MATHEMATICALLY_COMPUTABLE, result["sample_adequacy"])


class NonFiniteReturnTests(unittest.TestCase):
    """Step 14 item 14: NaN/inf fails closed."""

    def test_nan_in_stock_return_fails_closed(self):
        pairs = [{"session_date": "d0", "stock_return": float("nan"), "benchmark_return": 0.005},
                  {"session_date": "d1", "stock_return": 0.01, "benchmark_return": -0.01}]
        result = m.compute_beta_and_correlation(pairs)
        self.assertIsNone(result["beta"])
        self.assertEqual(m.SAMPLE_ADEQUACY_INVALID_INPUT, result["sample_adequacy"])

    def test_inf_in_benchmark_return_fails_closed(self):
        pairs = [{"session_date": "d0", "stock_return": 0.01, "benchmark_return": float("inf")},
                  {"session_date": "d1", "stock_return": -0.02, "benchmark_return": -0.01}]
        result = m.compute_beta_and_correlation(pairs)
        self.assertIsNone(result["correlation"])
        self.assertEqual(m.SAMPLE_ADEQUACY_INVALID_INPUT, result["sample_adequacy"])


class PitEligibilityAlwaysFalseTests(unittest.TestCase):
    """Step 14 item 15."""

    def test_pit_backtest_eligible_false_when_qualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            record = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        self.assertIs(False, record["pit_backtest_eligible"])

    def test_pit_backtest_eligible_false_when_not_qualified(self):
        vnm_report = price_analytics.build_shadow_report("VNM", None, runtime_root=None)
        vn30_series = index_capability.build_index_return_series("VN30", None, runtime_root=None)
        record = m.compute_current_state_beta_correlation(vnm_report, vn30_series)
        self.assertIs(False, record["pit_backtest_eligible"])


class ProvenanceAndContractVersionTests(unittest.TestCase):
    """Step 14 items 16-17."""

    def test_provenance_retained_from_both_sides(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            record = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        self.assertEqual(stock_report["provenance"], record["provenance"]["stock_provenance"])
        self.assertEqual(benchmark_series["provenance"], record["provenance"]["benchmark_provenance"])

    def test_contract_versions_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            record = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        self.assertEqual(stock_report["price_basis_contract_version"],
                          record["stock_price_contract"]["price_basis_contract_version"])
        self.assertEqual(benchmark_series["source_contract_version"],
                          record["benchmark_return_contract"]["source_contract_version"])


class DeterministicOutputTests(unittest.TestCase):
    """Step 14 item 18."""

    def test_repeated_computation_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
        first = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        second = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        self.assertEqual(m.serialize(first), m.serialize(second))


class NoVolumeDependencyTests(unittest.TestCase):
    """Step 14 item 19."""

    def test_serialized_report_never_mentions_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            record = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        self.assertNotIn("volume", m.serialize(record).lower())


class NoSecretsSerializedTests(unittest.TestCase):
    """Step 14 item 20."""

    def test_serialized_report_never_contains_credential_shaped_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            record = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        dumped = m.serialize(record).lower()
        for forbidden in ("token", "secret", "signature", "authorization", "x-api-key",
                          "cookie", "api_key", "api_secret", "bearer"):
            self.assertNotIn(forbidden, dumped)


class NoResearchEligibilityImplicationTests(unittest.TestCase):
    """Step 14 item 21: a qualified beta/correlation result does not imply
    or touch research eligibility -- this module has zero wiring into the
    research/bundle/ranking/publication surfaces."""

    def test_module_does_not_import_research_or_publication_surfaces(self):
        import inspect
        source = inspect.getsource(m)
        for forbidden in ("export_ai_bundle", "opportunity_ranking", "qualified_research",
                          "release_orchestrator", "publish_dashboard", "operate_stocklookup"):
            self.assertNotIn(forbidden, source)

    def test_qualified_result_carries_no_research_eligibility_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
            record = m.compute_current_state_beta_correlation(stock_report, benchmark_series)
        self.assertNotIn("research_eligible", record)
        self.assertNotIn("research_eligibility", record)


class VcbNeverEntersProductionUniverseTests(unittest.TestCase):
    """Step 14 item 22: VCB stays evidence-valid-but-non-production even
    though it is DNSE price-analytics eligible -- the same two-axis
    distinction test_dnse_current_state_price_analytics.py already
    established, plus proof this module never wires VCB in itself."""

    def test_vcb_not_in_production_ticker_universe(self):
        import export_ai_bundle
        self.assertNotIn("VCB", export_ai_bundle.DEFAULT_TICKERS)
        self.assertIn("HPG", export_ai_bundle.DEFAULT_TICKERS)

    def test_vcb_stock_gate_passes_eligibility_but_stays_outside_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime(tmp, {"VCB": _SESSION_DATES})
            vcb_report = price_analytics.build_shadow_report(
                "VCB", _stock_ohlc_payload(_SESSION_DATES, _HPG_CLOSES), runtime_root=root,
                include_technical_indicators=False,
            )
        ok, reason = m._stock_input_gate(vcb_report)
        self.assertTrue(ok, reason)
        import export_ai_bundle
        self.assertNotIn("VCB", export_ai_bundle.DEFAULT_TICKERS)


class CrossProviderSourceMixingTests(unittest.TestCase):
    """Step 4: no fallback provider mixing -- differing sources on each side
    fails closed even when both sides are individually eligible."""

    def test_mismatched_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock_report, benchmark_series = _qualified_hpg_vnindex_reports(tmp)
        mutated_benchmark = dict(benchmark_series)
        mutated_benchmark["source"] = "OTHER_PROVIDER"
        record = m.compute_current_state_beta_correlation(stock_report, mutated_benchmark)
        self.assertEqual(m.STATUS_NOT_QUALIFIED, record["qualification_status"])
        self.assertFalse(record["source_scope"]["same_source_no_fallback_mixing"])
        self.assertIsNone(record["beta"]["value"])


class InputGateDetailTests(unittest.TestCase):
    """Extra coverage on individual gate failure reasons."""

    def test_stock_gate_fails_when_coverage_incomplete(self):
        report = {"eligibility": {"eligible_for_current_state_price_analytics": True},
                   "coverage": {"status": "incomplete"}, "returns": {"status": "incomplete"},
                   "pit_backtest_eligible": False,
                   "analysis_time_semantics": price_analytics.ANALYSIS_TIME_SEMANTICS}
        ok, reason = m._stock_input_gate(report)
        self.assertFalse(ok)
        self.assertEqual("stock_side_session_coverage_incomplete", reason)

    def test_stock_gate_fails_when_pit_flag_not_explicitly_false(self):
        report = {"eligibility": {"eligible_for_current_state_price_analytics": True},
                   "coverage": {"status": "complete"}, "returns": {"status": "complete"},
                   "pit_backtest_eligible": None,
                   "analysis_time_semantics": price_analytics.ANALYSIS_TIME_SEMANTICS}
        ok, reason = m._stock_input_gate(report)
        self.assertFalse(ok)
        self.assertEqual("stock_side_pit_backtest_eligible_flag_not_explicitly_false", reason)

    def test_benchmark_gate_fails_when_not_current_state_qualified(self):
        series = {"eligibility": {"eligible_for_current_state_return_series": True},
                   "benchmark_id": "VNINDEX", "coverage": {"status": "complete"},
                   "current_state_qualified": False, "pit_backtest_eligible": False,
                   "analysis_time_semantics": index_capability.ANALYSIS_TIME_SEMANTICS}
        ok, reason = m._benchmark_input_gate(series)
        self.assertFalse(ok)
        self.assertEqual("benchmark_side_not_current_state_qualified", reason)

    def test_benchmark_gate_fails_when_identity_outside_evidence_qualified_set(self):
        series = {"eligibility": {"eligible_for_current_state_return_series": True},
                   "benchmark_id": "VN30", "coverage": {"status": "complete"},
                   "current_state_qualified": True, "pit_backtest_eligible": False,
                   "analysis_time_semantics": index_capability.ANALYSIS_TIME_SEMANTICS}
        ok, reason = m._benchmark_input_gate(series)
        self.assertFalse(ok)
        self.assertEqual("benchmark_identity_not_in_evidence_qualified_benchmark_set", reason)


if __name__ == "__main__":
    unittest.main()
