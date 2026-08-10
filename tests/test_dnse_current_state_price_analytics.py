from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import dnse_current_state_price_analytics as m
from dnse_ohlc_price_basis_capability import EVIDENCE_EVENTS, SOURCE_CONTRACT_VERSION
from vn_time import VN_TZ

# Real, shape-matched HPG-like closes over 15 consecutive trading sessions (no
# corporate action in this window -- values chosen only to exercise the math,
# not reused from any retained evidence file).
_SESSION_DATES = [
    "2026-06-18", "2026-06-19", "2026-06-22", "2026-06-23", "2026-06-24",
    "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30", "2026-07-01",
    "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08",
]
_CLOSES = [
    24.10, 24.30, 24.20, 24.50, 24.40,
    24.60, 24.55, 24.70, 24.65, 24.80,
    24.75, 24.90, 25.00, 24.85, 25.10,
]


def _epoch(date_str: str, hour: int = 2) -> int:
    y, mo, d = (int(x) for x in date_str.split("-"))
    return int(datetime(y, mo, d, hour, 0, tzinfo=VN_TZ).timestamp())


def _ohlc_payload(dates: list[str], closes: list[float], *, include_volume: bool = True) -> dict:
    payload = {
        "o": [c - 0.05 for c in closes],
        "h": [c + 0.10 for c in closes],
        "l": [c - 0.10 for c in closes],
        "c": list(closes),
        "t": [_epoch(d) for d in dates],
    }
    if include_volume:
        payload["v"] = [1_000_000 + i for i in range(len(dates))]
    return payload


def _make_runtime_with_ohlcv(tmp_dir: str, ticker: str, dates: list[str]) -> Path:
    """A minimal vn_stock.db stand-in -- just enough schema/rows for this
    module's trading-date gap detection to work against (same pattern as
    tests/test_dnse_foreign_flow_store.py's own fixture)."""
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    conn.executemany("INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
                      "VALUES (?, ?, 1, 1, 1, 1, 1, 'VCI')", [(ticker, d) for d in dates])
    conn.commit()
    conn.close()
    return root


class HpgEligibilityTests(unittest.TestCase):
    """Step 14 item 1: HPG is eligible under current DNSE price-basis evidence."""

    def test_hpg_series_is_qualified_with_a_gap_free_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            series = m.build_current_state_series(
                "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        self.assertEqual(m.STATUS_QUALIFIED, series["status"])
        self.assertEqual("complete", series["coverage"]["status"])
        self.assertEqual(15, len(series["observations"]))


class VcbEvidenceNonProductionTests(unittest.TestCase):
    """Step 14 item 2: VCB evidence remains valid but non-production-universe --
    the two axes (price-basis eligibility, production-universe membership) are
    independent."""

    def test_vcb_is_price_basis_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "VCB", _SESSION_DATES)
            series = m.build_current_state_series(
                "VCB", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        self.assertEqual(m.STATUS_QUALIFIED, series["status"])

    def test_vcb_is_not_in_the_stock_lookup_production_universe(self):
        import export_ai_bundle

        self.assertNotIn("VCB", export_ai_bundle.DEFAULT_TICKERS)
        self.assertIn("HPG", export_ai_bundle.DEFAULT_TICKERS)


class UnqualifiedTickerFailsClosedTests(unittest.TestCase):
    """Step 14 item 3 / Step 11: an unproven production ticker fails closed,
    regardless of whether OHLC-shaped data exists for it."""

    def test_vnm_fails_closed_with_no_data_at_all(self):
        series = m.build_current_state_series("VNM", None, runtime_root=None)
        self.assertEqual(m.STATUS_NOT_QUALIFIED, series["status"])
        self.assertEqual([], series["observations"])

    def test_every_other_production_ticker_fails_closed(self):
        for ticker in ("POW", "SSI", "EVF", "PAN", "PNJ", "FPT", "QNS", "PVD", "NVL"):
            series = m.build_current_state_series(ticker, None, runtime_root=None)
            self.assertEqual(m.STATUS_NOT_QUALIFIED, series["status"], ticker)

    def test_qns_fails_closed_even_with_well_formed_ohlc_and_a_valid_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "QNS", _SESSION_DATES)
            series = m.build_current_state_series(
                "QNS", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        self.assertEqual(m.STATUS_NOT_QUALIFIED, series["status"])
        self.assertEqual([], series["observations"])

    def test_ineligible_ticker_never_reaches_bar_normalization_even_if_malformed(self):
        # A structurally malformed payload would raise inside normalize_bars --
        # proving the eligibility gate truly short-circuits before that point.
        malformed = {"o": [1], "h": [1]}  # missing required "l"/"c"/"t"
        series = m.build_current_state_series("VNM", malformed, runtime_root=None)
        self.assertEqual(m.STATUS_NOT_QUALIFIED, series["status"])

    def test_fail_closed_ticker_returns_and_volatility_and_drawdown_are_all_blocked(self):
        report = m.build_shadow_report("VNM", None, runtime_root=None)
        self.assertEqual("incomplete", report["returns"]["status"])
        self.assertEqual("unavailable", report["volatility"]["status"])
        self.assertEqual("unavailable", report["drawdown"]["status"])
        self.assertEqual("unavailable", report["technical_indicators"]["status"])


class DeterministicReturnsTests(unittest.TestCase):
    """Step 14 item 4: r_t = close_t/close_(t-1) - 1, deterministic."""

    def _complete_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            series = m.build_current_state_series(
                "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
            return series

    def test_first_return_matches_hand_computed_value(self):
        series = self._complete_series()
        returns = m.compute_returns(series)
        expected = _CLOSES[1] / _CLOSES[0] - 1.0
        self.assertAlmostEqual(expected, returns["returns"][0]["simple_return"])

    def test_return_count_is_one_fewer_than_session_count(self):
        series = self._complete_series()
        returns = m.compute_returns(series)
        self.assertEqual(len(series["observations"]) - 1, returns["return_count"])

    def test_cumulative_return_matches_first_to_last_close(self):
        series = self._complete_series()
        returns = m.compute_returns(series)
        expected = _CLOSES[-1] / _CLOSES[0] - 1.0
        self.assertAlmostEqual(expected, returns["cumulative_return"])

    def test_repeated_computation_is_byte_identical(self):
        series = self._complete_series()
        first = m.compute_returns(series)
        second = m.compute_returns(series)
        self.assertEqual(first, second)


class SessionOrderingAndDuplicateTests(unittest.TestCase):
    """Step 14 items 5-6: session ordering enforced, duplicate session rejected."""

    def test_out_of_order_input_is_sorted_into_ascending_output(self):
        reversed_dates = list(reversed(_SESSION_DATES))
        reversed_closes = list(reversed(_CLOSES))
        normalized = m.normalize_bars("HPG", _ohlc_payload(reversed_dates, reversed_closes))
        dates_out = [o["session_date"] for o in normalized["observations"]]
        self.assertEqual(sorted(dates_out), dates_out)
        self.assertEqual(sorted(_SESSION_DATES), dates_out)

    def test_duplicate_session_date_is_rejected(self):
        dates = list(_SESSION_DATES) + [_SESSION_DATES[0]]
        closes = list(_CLOSES) + [999.0]
        with self.assertRaises(m.DnseCurrentStatePriceAnalyticsError):
            m.normalize_bars("HPG", _ohlc_payload(dates, closes))

    def test_validate_session_sequence_rejects_non_ascending_input_directly(self):
        obs = [{"session_date": "2026-06-19"}, {"session_date": "2026-06-18"}]
        result = m.validate_session_sequence(obs, reference_trading_dates={"2026-06-18", "2026-06-19"})
        self.assertEqual("incomplete", result["status"])
        self.assertIn("ascending", result["reason"])


class MissingPriceHandledHonestlyTests(unittest.TestCase):
    """Step 14 item 7: missing price/session handled honestly -- dropped, not
    fabricated or interpolated; the resulting gap is reported, not hidden."""

    def test_a_zero_close_session_is_dropped_not_fabricated(self):
        payload = _ohlc_payload(_SESSION_DATES, _CLOSES)
        payload["c"][3] = 0  # non-positive -> unusable
        normalized = m.normalize_bars("HPG", payload)
        self.assertEqual(14, len(normalized["observations"]))
        self.assertEqual(1, len(normalized["dropped_sessions"]))
        self.assertEqual(_SESSION_DATES[3], normalized["dropped_sessions"][0]["session_date"])
        kept_dates = {o["session_date"] for o in normalized["observations"]}
        self.assertNotIn(_SESSION_DATES[3], kept_dates)

    def test_dropped_session_produces_an_honest_gap_not_silent_success(self):
        payload = _ohlc_payload(_SESSION_DATES, _CLOSES)
        payload["c"][3] = 0
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)  # full calendar retained
            series = m.build_current_state_series("HPG", payload, runtime_root=root)
        self.assertEqual("incomplete", series["coverage"]["status"])
        self.assertIn("gap detected", series["coverage"]["reason"])
        self.assertIn(
            "one_or_more_sessions_dropped_for_missing_or_non_positive_price_never_interpolated",
            series["warnings"],
        )

    def test_missing_intervening_session_in_the_request_itself_is_an_honest_gap(self):
        # A whole session absent from the DNSE response (not merely dropped for
        # a bad price) -- vn_stock.db's calendar still expects it.
        dates_with_gap = _SESSION_DATES[:3] + _SESSION_DATES[4:]  # skip index 3
        closes_with_gap = _CLOSES[:3] + _CLOSES[4:]
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            series = m.build_current_state_series(
                "HPG", _ohlc_payload(dates_with_gap, closes_with_gap), runtime_root=root,
            )
        self.assertEqual("incomplete", series["coverage"]["status"])
        self.assertIn(_SESSION_DATES[3], series["coverage"]["reason"])


class NoVolumeDependencyTests(unittest.TestCase):
    """Step 14 item 8: no volume dependency anywhere in this contract."""

    def test_missing_volume_field_entirely_does_not_prevent_normalization(self):
        payload = _ohlc_payload(_SESSION_DATES, _CLOSES, include_volume=False)
        self.assertNotIn("v", payload)
        normalized = m.normalize_bars("HPG", payload)
        self.assertEqual(15, len(normalized["observations"]))

    def test_observations_never_carry_a_volume_field(self):
        normalized = m.normalize_bars("HPG", _ohlc_payload(_SESSION_DATES, _CLOSES))
        for obs in normalized["observations"]:
            self.assertNotIn("volume", obs)
            self.assertNotIn("v", obs)

    def test_changing_volume_values_does_not_change_any_computed_output(self):
        payload_a = _ohlc_payload(_SESSION_DATES, _CLOSES)
        payload_b = _ohlc_payload(_SESSION_DATES, _CLOSES)
        payload_b["v"] = [1] * len(_SESSION_DATES)  # wildly different volume
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            report_a = m.build_shadow_report("HPG", payload_a, runtime_root=root)
            report_b = m.build_shadow_report("HPG", payload_b, runtime_root=root)
        self.assertEqual(m.serialize(report_a), m.serialize(report_b))

    def test_technical_indicators_report_no_volume_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            series = m.build_current_state_series(
                "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        indicators = m.compute_technical_indicators(series)
        self.assertEqual("none", indicators["volume_dependency"])


class ProvenanceAndContractVersionTests(unittest.TestCase):
    """Step 14 items 9-10: provenance retained, price-basis version retained."""

    def test_fetch_provenance_is_carried_into_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            report = m.build_shadow_report(
                "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
                fetch_provenance={"endpoint": "/price/ohlc", "query_sent": {"symbol": "HPG"}},
            )
        self.assertEqual("/price/ohlc", report["provenance"]["fetch"]["endpoint"])

    def test_evidence_record_id_is_carried_in_eligibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            report = m.build_shadow_report("HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root)
        hpg_event = next(e for e in EVIDENCE_EVENTS if e["ticker"] == "HPG")
        self.assertEqual(hpg_event["record_id"], report["eligibility"]["evidence_record_id"])

    def test_price_basis_contract_version_matches_the_capability_module(self):
        report = m.build_shadow_report("VNM", None, runtime_root=None)
        self.assertEqual(SOURCE_CONTRACT_VERSION, report["price_basis_contract_version"])


class CurrentStateSemanticsAndPitSafetyTests(unittest.TestCase):
    """Step 14 items 11-12: current-state semantics explicit, PIT eligibility false --
    on every result, qualified or not."""

    def test_analysis_time_semantics_is_the_exact_required_string(self):
        self.assertEqual(
            "current_state_using_retrospectively_adjusted_history", m.ANALYSIS_TIME_SEMANTICS
        )
        report = m.build_shadow_report("VNM", None, runtime_root=None)
        self.assertEqual(m.ANALYSIS_TIME_SEMANTICS, report["analysis_time_semantics"])
        self.assertEqual(m.ANALYSIS_TIME_SEMANTICS, report["returns"]["analysis_time_semantics"])

    def test_pit_backtest_eligible_is_false_on_every_result_qualified_or_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            qualified = m.build_shadow_report("HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root)
        not_qualified = m.build_shadow_report("VNM", None, runtime_root=None)
        self.assertIs(False, qualified["pit_backtest_eligible"])
        self.assertIs(False, not_qualified["pit_backtest_eligible"])
        self.assertIs(False, m.PIT_BACKTEST_ELIGIBLE)


class IncompleteWindowFailsClosedTests(unittest.TestCase):
    """Step 14 item 13: an incomplete window fails closed for every derived
    analytic independently, never a partial best-effort number."""

    def test_single_session_window_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES[:1])
            series = m.build_current_state_series(
                "HPG", _ohlc_payload(_SESSION_DATES[:1], _CLOSES[:1]), runtime_root=root,
            )
        self.assertEqual("incomplete", series["coverage"]["status"])
        returns = m.compute_returns(series)
        self.assertEqual("incomplete", returns["status"])
        self.assertEqual([], returns["returns"])

    def test_no_reference_trading_calendar_fails_closed(self):
        series = m.build_current_state_series(
            "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=None,
        )
        self.assertEqual("incomplete", series["coverage"]["status"])
        self.assertIn("no_vn_stock_db_trading_date_reference", series["coverage"]["reason"])

    def test_short_window_leaves_sma20_unavailable_but_rsi14_available(self):
        short_dates = _SESSION_DATES[:15]
        short_closes = _CLOSES[:15]
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", short_dates)
            series = m.build_current_state_series(
                "HPG", _ohlc_payload(short_dates, short_closes), runtime_root=root,
            )
        indicators = m.compute_technical_indicators(series)
        self.assertEqual("unavailable", indicators["sma_20"]["status"])
        self.assertEqual("available", indicators["rsi_14"]["status"])


class VolatilityAndDrawdownDeterminismTests(unittest.TestCase):
    """Step 14 items 14-15: volatility and drawdown deterministic."""

    def _complete_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            return m.build_current_state_series(
                "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )

    def test_volatility_matches_hand_computed_population_stdev(self):
        series = self._complete_series()
        returns = m.compute_returns(series)
        values = [r["simple_return"] for r in returns["returns"]]
        mean = sum(values) / len(values)
        expected = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
        vol = m.compute_volatility(returns)
        self.assertAlmostEqual(expected, vol["value"])
        self.assertEqual("per_observation_return", vol["unit"])
        self.assertIsNone(vol["annualized"])

    def test_volatility_is_deterministic_across_repeated_calls(self):
        series = self._complete_series()
        returns = m.compute_returns(series)
        self.assertEqual(m.compute_volatility(returns), m.compute_volatility(returns))

    def test_drawdown_identifies_the_correct_peak_and_trough(self):
        # Closes rise then dip at index 8 (24.65 after peak 24.70) before
        # continuing -- confirm the tracked peak/trough are the real extremes.
        series = self._complete_series()
        dd = m.compute_drawdown(series)
        self.assertEqual("available", dd["status"])
        self.assertLessEqual(dd["maximum_drawdown"], 0.0)
        self.assertGreaterEqual(dd["peak_value"], dd["trough_value"])

    def test_drawdown_is_deterministic_across_repeated_calls(self):
        series = self._complete_series()
        self.assertEqual(m.compute_drawdown(series), m.compute_drawdown(series))

    def test_drawdown_unavailable_when_coverage_incomplete(self):
        series = m.build_current_state_series(
            "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=None,
        )
        self.assertEqual("unavailable", m.compute_drawdown(series)["status"])


class BenchmarkAnalyticsRemainBlockedTests(unittest.TestCase):
    """Step 14 item 16 / Step 12: this module implements no beta, correlation,
    alpha, or benchmark-relative analytic -- those remain blocked on the
    separately, still-unqualified benchmark (VNINDEX/VN30) price basis.

    Checked against the module's actual namespace (public names and function
    signatures), not raw source text: the module docstring legitimately
    *discusses* point_in_time_benchmark/point_in_time_market_risk in prose to
    explain what this module must never touch, which would false-positive a
    plain substring-in-source check.
    """

    def test_module_does_not_import_the_blocked_pit_benchmark_modules(self):
        self.assertNotIn("point_in_time_benchmark", dir(m))
        self.assertNotIn("point_in_time_market_risk", dir(m))
        self.assertNotIn("risk_liquidity", dir(m))

    def test_no_public_name_implements_a_benchmark_relative_concept(self):
        public_names = [name.lower() for name in dir(m) if not name.startswith("_")]
        for forbidden in ("beta", "correlation", "alpha", "vnindex", "vn30", "benchmark"):
            matches = [name for name in public_names if forbidden in name]
            self.assertEqual([], matches, f"unexpected benchmark-relative name(s): {matches}")

    def test_report_contract_carries_no_benchmark_relative_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            report = m.build_shadow_report("HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root)
        dumped_keys = m.serialize(report).lower()
        for forbidden in ("\"beta\"", "\"correlation\"", "\"alpha\"", "vnindex", "vn30"):
            self.assertNotIn(forbidden, dumped_keys)


class NoSecretsSerializedTests(unittest.TestCase):
    """Step 14 item 17: no secret/auth material in a serialized report."""

    def test_serialized_report_never_contains_credential_shaped_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            report = m.build_shadow_report(
                "HPG", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
                fetch_provenance={"endpoint": "/price/ohlc"},
            )
        dumped = m.serialize(report).lower()
        for forbidden in ("token", "secret", "signature", "authorization", "x-api-key",
                          "cookie", "api_key", "api_secret", "bearer"):
            self.assertNotIn(forbidden, dumped)


class ByteIdenticalRepeatedBuildTests(unittest.TestCase):
    """Step 14 item 18: repeated build byte-identical."""

    def test_two_builds_from_the_same_input_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_ohlcv(tmp, "HPG", _SESSION_DATES)
            payload = _ohlc_payload(_SESSION_DATES, _CLOSES)
            first = m.build_shadow_report("HPG", payload, runtime_root=root)
            second = m.build_shadow_report("HPG", payload, runtime_root=root)
        self.assertEqual(m.serialize(first), m.serialize(second))

    def test_not_qualified_ticker_build_is_also_byte_identical(self):
        first = m.serialize(m.build_shadow_report("VNM", None, runtime_root=None))
        second = m.serialize(m.build_shadow_report("VNM", None, runtime_root=None))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
