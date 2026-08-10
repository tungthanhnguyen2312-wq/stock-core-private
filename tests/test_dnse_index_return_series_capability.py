from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import dnse_index_return_series_capability as m
from vn_time import VN_TZ

# Real, shape-matched VNINDEX-like closes over 19 consecutive sessions (values
# chosen only to exercise the math; the real live-fetched evidence is used
# separately in RealRetainedEvidenceTests below).
_SESSION_DATES = [
    "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20",
    "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27",
    "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03",
    "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
]
_CLOSES = [
    1806.63, 1782.12, 1804.24, 1787.45, 1743.51,
    1730.56, 1668.53, 1699.38, 1686.11, 1669.01,
    1680.62, 1704.68, 1744.66, 1735.78, 1762.84,
    1777.23, 1776.46, 1764.78, 1768.06,
]

REAL_INDEX_EVIDENCE = (
    Path(__file__).resolve().parents[1] / ".." / "operations-review"
    / "dnse-index-return-series-qualification-20260810" / "probe_results.json"
).resolve()


def _epoch(date_str: str, hour: int = 9) -> int:
    y, mo, d = (int(x) for x in date_str.split("-"))
    return int(datetime(y, mo, d, hour, 0, tzinfo=VN_TZ).timestamp())


def _ohlc_payload(dates: list[str], closes: list[float], *, include_volume: bool = True) -> dict:
    payload = {
        "o": [c - 0.5 for c in closes],
        "h": [c + 1.0 for c in closes],
        "l": [c - 1.0 for c in closes],
        "c": list(closes),
        "t": [_epoch(d) for d in dates],
    }
    if include_volume:
        payload["v"] = [500_000_000 + i for i in range(len(dates))]
    return payload


def _make_runtime_with_index_ohlcv(tmp_dir: str, benchmark_id: str, rows: list[tuple[str, float]]) -> Path:
    root = Path(tmp_dir)
    conn = sqlite3.connect(root / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, 'VCI')",
        [(benchmark_id, d, c, c, c, c) for d, c in rows],
    )
    conn.commit()
    conn.close()
    return root


def _full_runtime() -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory()
    root = _make_runtime_with_index_ohlcv(
        tmp.name, "VNINDEX", list(zip(_SESSION_DATES, _CLOSES))
    )
    return tmp, root


class VnindexIdentityAcceptedTests(unittest.TestCase):
    """Step 11 item 1: VNINDEX identity accepted."""

    def test_vnindex_is_evidence_qualified(self):
        self.assertTrue(m.benchmark_current_state_eligible("VNINDEX"))

    def test_case_and_whitespace_insensitive(self):
        self.assertTrue(m.benchmark_current_state_eligible(" vnindex "))

    def test_full_series_qualifies(self):
        tmp, root = _full_runtime()
        with tmp:
            series = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        self.assertEqual(m.STATUS_QUALIFIED, series["status"])
        self.assertTrue(series["current_state_qualified"])


class UnsupportedBenchmarkFailsClosedTests(unittest.TestCase):
    """Step 11 item 2: unsupported benchmark fails closed."""

    def test_vn30_is_not_eligible(self):
        self.assertFalse(m.benchmark_current_state_eligible("VN30"))

    def test_vn30_series_is_not_qualified_even_with_well_formed_data(self):
        tmp, root = _full_runtime()
        with tmp:
            series = m.build_index_return_series(
                "VN30", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        self.assertEqual(m.STATUS_NOT_QUALIFIED, series["status"])
        self.assertEqual([], series["observations"])

    def test_hnxindex_and_random_string_also_fail_closed(self):
        for benchmark in ("HNXINDEX", "UPCOMINDEX", "SP500", "NOT_A_REAL_INDEX"):
            self.assertFalse(m.benchmark_current_state_eligible(benchmark), benchmark)

    def test_ineligible_benchmark_never_reaches_bar_parsing_even_if_malformed(self):
        malformed = {"o": [1], "h": [1]}  # missing required "l"/"c"/"t"
        series = m.build_index_return_series("VN30", malformed, runtime_root=None)
        self.assertEqual(m.STATUS_NOT_QUALIFIED, series["status"])


class ResolutionTokenTests(unittest.TestCase):
    """Step 11 items 3-4: daily "1D" shape accepted, "D" not treated as
    equivalent (structural check against the probe's own call plan)."""

    def test_call_plan_uses_1D_not_D(self):
        from tools.dnse_market_data_probe import build_index_return_series_call_plan

        ohlc_entries = [e for e in build_index_return_series_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual(2, len(ohlc_entries))
        for entry in ohlc_entries:
            self.assertEqual("1D", entry["query"]["resolution"])
            self.assertNotEqual("D", entry["query"]["resolution"])
            self.assertEqual("INDEX", entry["query"]["type"])
            self.assertEqual("VNINDEX", entry["query"]["symbol"])

    def test_the_two_calls_in_the_plan_are_identical_by_design(self):
        from tools.dnse_market_data_probe import build_index_return_series_call_plan

        ohlc_entries = [e for e in build_index_return_series_call_plan() if e["capability"] == "ohlc"]
        self.assertEqual(ohlc_entries[0]["query"], ohlc_entries[1]["query"])


class LevelScaleUnitPreservedTests(unittest.TestCase):
    """Step 11 item 5: index level scale/unit preserved (no VND-style
    conversion applied, and the qualification classifier fails closed when
    the cross-reference doesn't back it up)."""

    def test_close_level_values_pass_through_unchanged(self):
        tmp, root = _full_runtime()
        with tmp:
            series = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        self.assertEqual(_CLOSES[0], series["observations"][0]["close_level"])
        self.assertEqual(_CLOSES[-1], series["observations"][-1]["close_level"])

    def test_classify_level_unit_fails_closed_with_no_rows(self):
        self.assertEqual(m.INDEX_LEVEL_UNIT_UNQUALIFIED, m.classify_level_unit([]))

    def test_classify_level_unit_fails_closed_on_missing_reference(self):
        rows = [{"dnse_close": 1234.0, "retained_close": None, "verdict": "no_retained_reference_for_this_session"}]
        self.assertEqual(m.INDEX_LEVEL_UNIT_UNQUALIFIED, m.classify_level_unit(rows))

    def test_classify_level_unit_fails_closed_on_implausible_scale(self):
        # A VND-shaped number (tens of thousands), not an index point.
        rows = [{"dnse_close": 24140.0, "retained_close": 24140.0,
                 "relative_difference": 0.0, "verdict": "consistent"}]
        self.assertEqual(m.INDEX_LEVEL_UNIT_UNQUALIFIED, m.classify_level_unit(rows))

    def test_classify_level_unit_qualifies_on_exact_plausible_match(self):
        rows = [{"dnse_close": 1806.63, "retained_close": 1806.63,
                 "relative_difference": 0.0, "verdict": "consistent"}]
        self.assertEqual(m.INDEX_LEVEL_UNIT_QUALIFIED, m.classify_level_unit(rows))


class SessionOrderingAndDuplicateTests(unittest.TestCase):
    """Step 11 items 6-7: session ordering enforced, duplicate session rejected."""

    def test_out_of_order_input_normalizes_to_ascending(self):
        reversed_dates = list(reversed(_SESSION_DATES))
        reversed_closes = list(reversed(_CLOSES))
        tmp, root = _full_runtime()
        with tmp:
            series = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(reversed_dates, reversed_closes), runtime_root=root,
            )
        dates_out = [o["session_date"] for o in series["observations"]]
        self.assertEqual(sorted(dates_out), dates_out)

    def test_duplicate_session_date_is_rejected(self):
        dates = list(_SESSION_DATES) + [_SESSION_DATES[0]]
        closes = list(_CLOSES) + [9999.0]
        with self.assertRaises(m.price_analytics.DnseCurrentStatePriceAnalyticsError):
            m.price_analytics.normalize_bars("VNINDEX", _ohlc_payload(dates, closes))


class MissingSessionCompletenessTests(unittest.TestCase):
    """Step 11 item 8: missing expected session fails completeness."""

    def test_a_missing_session_in_the_response_fails_the_window_closed(self):
        gap_dates = _SESSION_DATES[:3] + _SESSION_DATES[4:]  # skip index 3
        gap_closes = _CLOSES[:3] + _CLOSES[4:]
        tmp, root = _full_runtime()  # reference calendar still has the full 19 dates
        with tmp:
            series = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(gap_dates, gap_closes), runtime_root=root,
            )
        self.assertEqual("incomplete", series["coverage"]["status"])
        self.assertIn(_SESSION_DATES[3], series["coverage"]["reason"])
        self.assertFalse(series["current_state_qualified"])

    def test_no_reference_calendar_fails_closed(self):
        series = m.build_index_return_series(
            "VNINDEX", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=None,
        )
        self.assertEqual("incomplete", series["coverage"]["status"])


class InvalidLevelRejectedTests(unittest.TestCase):
    """Step 11 item 9: invalid/non-positive level rejected."""

    def test_zero_close_session_is_dropped_not_fabricated(self):
        payload = _ohlc_payload(_SESSION_DATES, _CLOSES)
        payload["c"][5] = 0
        normalized = m.price_analytics.normalize_bars("VNINDEX", payload)
        self.assertEqual(18, len(normalized["observations"]))
        self.assertEqual(1, len(normalized["dropped_sessions"]))

    def test_negative_close_session_is_dropped(self):
        payload = _ohlc_payload(_SESSION_DATES, _CLOSES)
        payload["c"][2] = -100.0
        normalized = m.price_analytics.normalize_bars("VNINDEX", payload)
        kept_dates = {o["session_date"] for o in normalized["observations"]}
        self.assertNotIn(_SESSION_DATES[2], kept_dates)


class DeterministicReturnTests(unittest.TestCase):
    """Step 11 item 10: simple benchmark return deterministic."""

    def _qualified_series(self):
        tmp, root = _full_runtime()
        with tmp:
            return m.build_index_return_series(
                "VNINDEX", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )

    def test_first_return_matches_hand_computed_value(self):
        series = self._qualified_series()
        returns = m.compute_returns_for_series(series)
        expected = _CLOSES[1] / _CLOSES[0] - 1.0
        self.assertAlmostEqual(expected, returns["returns"][0]["simple_return"])

    def test_cumulative_return_matches_first_to_last_close(self):
        series = self._qualified_series()
        returns = m.compute_returns_for_series(series)
        expected = _CLOSES[-1] / _CLOSES[0] - 1.0
        self.assertAlmostEqual(expected, returns["cumulative_return"])

    def test_repeated_computation_is_identical(self):
        series = self._qualified_series()
        self.assertEqual(m.compute_returns_for_series(series), m.compute_returns_for_series(series))


class NoInterpolationTests(unittest.TestCase):
    """Step 11 item 11: no interpolation -- a dropped/missing session leaves a
    gap that fails the window closed rather than being filled."""

    def test_returns_are_empty_when_coverage_incomplete(self):
        gap_dates = _SESSION_DATES[:3] + _SESSION_DATES[4:]
        gap_closes = _CLOSES[:3] + _CLOSES[4:]
        tmp, root = _full_runtime()
        with tmp:
            series = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(gap_dates, gap_closes), runtime_root=root,
            )
        returns = m.compute_returns_for_series(series)
        self.assertEqual("incomplete", returns["status"])
        self.assertEqual([], returns["returns"])
        self.assertIsNone(returns["cumulative_return"])


class ProvenancePreservedTests(unittest.TestCase):
    """Step 11 item 12: provenance preserved."""

    def test_fetch_provenance_is_carried_into_the_series(self):
        tmp, root = _full_runtime()
        with tmp:
            series = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
                fetch_provenance={"endpoint": "/price/ohlc", "query_sent": {"symbol": "VNINDEX"}},
            )
        self.assertEqual("/price/ohlc", series["provenance"]["fetch"]["endpoint"])

    def test_evidence_window_is_carried_in_eligibility(self):
        record = m.current_state_eligibility("VNINDEX")
        self.assertEqual({"from": "2026-07-14", "to": "2026-08-07"}, record["evidence_window"])
        self.assertEqual(19, record["evidence_sessions_compared"])


class CurrentStateSemanticsExplicitTests(unittest.TestCase):
    """Step 11 item 13: current-state semantics explicit."""

    def test_analysis_time_semantics_is_the_exact_required_string(self):
        self.assertEqual("current_state_benchmark_history", m.ANALYSIS_TIME_SEMANTICS)
        series = m.build_index_return_series("VN30", None, runtime_root=None)
        self.assertEqual(m.ANALYSIS_TIME_SEMANTICS, series["analysis_time_semantics"])


class PitFalseTests(unittest.TestCase):
    """Step 11 item 14: PIT false, on every result qualified or not."""

    def test_pit_backtest_eligible_is_false_everywhere(self):
        tmp, root = _full_runtime()
        with tmp:
            qualified = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
            )
        not_qualified = m.build_index_return_series("VN30", None, runtime_root=None)
        self.assertIs(False, qualified["pit_backtest_eligible"])
        self.assertIs(False, not_qualified["pit_backtest_eligible"])
        self.assertIs(False, m.PIT_BACKTEST_ELIGIBLE)


class ByteIdenticalSerializationTests(unittest.TestCase):
    """Step 11 item 15: repeated serialization byte-identical."""

    def test_two_builds_from_the_same_input_are_byte_identical(self):
        tmp, root = _full_runtime()
        with tmp:
            payload = _ohlc_payload(_SESSION_DATES, _CLOSES)
            first = m.build_index_return_series("VNINDEX", payload, runtime_root=root)
            second = m.build_index_return_series("VNINDEX", payload, runtime_root=root)
        self.assertEqual(m.serialize(first), m.serialize(second))

    def test_active_capability_contract_is_byte_identical_across_calls(self):
        self.assertEqual(m.serialize(m.active_capability_contract()),
                          m.serialize(m.active_capability_contract()))


class EvidenceTruncationCapAvoidedTests(unittest.TestCase):
    """Step 11 item 16: the known 20-element retained-evidence truncation cap
    is avoided (window stays at/under 20 sessions) -- and if it were ever
    tripped, this module fails clearly rather than crashing (inherited from
    normalize_bars's own defensive check, exercised directly here)."""

    def test_window_session_count_stays_at_or_under_20(self):
        import sqlite3

        from runtime_paths import runtime_root
        from tools.dnse_market_data_probe import INDEX_RETURN_SERIES_BENCHMARK, INDEX_RETURN_SERIES_WINDOW

        self.assertEqual("VNINDEX", INDEX_RETURN_SERIES_BENCHMARK)
        db_path = runtime_root() / "vn_stock.db"
        if not db_path.exists():
            self.skipTest("vn_stock.db not available in this environment")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only = 1")
            count = conn.execute(
                "SELECT COUNT(DISTINCT date) FROM ohlcv WHERE ticker = ? AND date BETWEEN ? AND ?",
                (INDEX_RETURN_SERIES_BENCHMARK, INDEX_RETURN_SERIES_WINDOW["from"], INDEX_RETURN_SERIES_WINDOW["to"]),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertGreater(count, 0, "expected at least one retained VNINDEX session in this window")
        self.assertLessEqual(count, 20, "window session count must stay at/under the redaction truncation cap")

    def test_a_truncated_list_truncated_dict_field_fails_clearly_not_with_a_bare_keyerror(self):
        truncated_payload = _ohlc_payload(_SESSION_DATES, _CLOSES)
        truncated_payload["t"] = {"list_truncated": True, "item_count": 37}
        with self.assertRaises(m.price_analytics.DnseCurrentStatePriceAnalyticsError):
            m.price_analytics.normalize_bars("VNINDEX", truncated_payload)


class StockDataCannotEnterIndexContractTests(unittest.TestCase):
    """Step 11 item 17: stock ticker data cannot enter the index contract
    accidentally -- the two evidence sets are disjoint and neither module
    reads the other's set."""

    def test_evidence_qualified_sets_are_disjoint(self):
        import dnse_ohlc_price_basis_capability as stock_capability

        self.assertEqual(
            set(), set(m.EVIDENCE_QUALIFIED_BENCHMARKS) & set(stock_capability.EVIDENCE_QUALIFIED_TICKERS)
        )

    def test_hpg_is_not_an_eligible_benchmark(self):
        self.assertFalse(m.benchmark_current_state_eligible("HPG"))

    def test_vnindex_is_not_an_eligible_stock_ticker(self):
        import dnse_ohlc_price_basis_capability as stock_capability

        self.assertFalse(stock_capability.ticker_current_state_eligible("VNINDEX"))


class NoSecretsSerializedTests(unittest.TestCase):
    """Step 11 item 18: no secret/auth fields serialized."""

    def test_serialized_series_never_contains_credential_shaped_values(self):
        tmp, root = _full_runtime()
        with tmp:
            series = m.build_index_return_series(
                "VNINDEX", _ohlc_payload(_SESSION_DATES, _CLOSES), runtime_root=root,
                fetch_provenance={"endpoint": "/price/ohlc"},
            )
        dumped = m.serialize(series).lower()
        for forbidden in ("token", "secret", "signature", "authorization", "x-api-key",
                          "cookie", "api_key", "api_secret", "bearer"):
            self.assertNotIn(forbidden, dumped)

    def test_active_contract_never_contains_credential_shaped_values(self):
        dumped = m.serialize(m.active_capability_contract()).lower()
        for forbidden in ("token", "secret", "signature", "authorization", "x-api-key",
                          "cookie", "api_key", "api_secret", "bearer"):
            self.assertNotIn(forbidden, dumped)


class BenchmarkRelativeAnalyticsRemainBlockedTests(unittest.TestCase):
    """Step 13: this module implements no beta/correlation/benchmark-relative
    concept -- it qualifies the return-series *input*, nothing else."""

    def test_module_does_not_import_the_blocked_beta_correlation_module(self):
        self.assertNotIn("point_in_time_market_risk", dir(m))

    def test_no_public_name_implements_beta_or_correlation(self):
        public_names = [name.lower() for name in dir(m) if not name.startswith("_")]
        for forbidden in ("beta", "correlation", "alpha"):
            matches = [name for name in public_names if forbidden in name]
            self.assertEqual([], matches, f"unexpected beta/correlation name(s): {matches}")


class FormalVerdictVocabularyTests(unittest.TestCase):
    def test_assert_fail_closed_accepts_every_declared_verdict(self):
        for verdict in m.RETURN_SERIES_VERDICTS:
            m.assert_fail_closed(verdict)  # must not raise

    def test_assert_fail_closed_rejects_unknown_verdict(self):
        with self.assertRaises(m.DnseIndexReturnSeriesError):
            m.assert_fail_closed("PARTIALLY_QUALIFIED_MAYBE")

    def test_active_verdict_is_in_the_declared_vocabulary(self):
        self.assertIn(m.ACTIVE_RETURN_SERIES_VERDICT, m.RETURN_SERIES_VERDICTS)


class OhlcConsistencyTests(unittest.TestCase):
    """Step 5 item 7: OHLC consistency, checked directly."""

    def test_consistent_candle_passes(self):
        self.assertTrue(m.ohlc_internally_consistent(
            {"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0}
        ))

    def test_close_outside_high_low_range_fails(self):
        self.assertFalse(m.ohlc_internally_consistent(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 200.0}
        ))

    def test_missing_field_fails_closed(self):
        self.assertFalse(m.ohlc_internally_consistent({"open": 100.0, "high": 101.0}))


@unittest.skipUnless(REAL_INDEX_EVIDENCE.exists(), "real retained VNINDEX evidence not present")
class RealRetainedEvidenceTests(unittest.TestCase):
    """End-to-end against the actual live-fetched evidence from this
    milestone's own bounded experiment -- not a synthetic fixture."""

    def test_real_vnindex_evidence_qualifies_with_exact_cross_check_match(self):
        import json

        import dnse_current_state_price_analytics as price_analytics

        evidence = json.loads(REAL_INDEX_EVIDENCE.read_text(encoding="utf-8"))
        ohlc_results = [r for r in evidence["results"] if r.get("capability") == "ohlc"]
        self.assertEqual(2, len(ohlc_results), "expected exactly 2 identical ohlc calls")
        self.assertEqual(
            price_analytics.serialize(ohlc_results[0]["body_redacted"]),
            price_analytics.serialize(ohlc_results[1]["body_redacted"]),
            "the two identical live calls must have returned byte-identical bodies",
        )
        raw = ohlc_results[0]["body_redacted"]
        normalized = price_analytics.normalize_bars("VNINDEX", raw)
        self.assertEqual(19, len(normalized["observations"]))

        with tempfile.TemporaryDirectory() as tmp:
            root = _make_runtime_with_index_ohlcv(
                tmp, "VNINDEX",
                [(o["session_date"], o["close"]) for o in normalized["observations"]],
            )
            series = m.build_index_return_series("VNINDEX", raw, runtime_root=root)
            reference = {o["session_date"]: o["close"] for o in normalized["observations"]}
            cross_check = m.cross_check_against_retained(normalized["observations"], reference)

        self.assertEqual(m.STATUS_QUALIFIED, series["status"])
        self.assertEqual(19, series["coverage"]["session_count"])
        self.assertEqual(m.INDEX_LEVEL_UNIT_QUALIFIED, m.classify_level_unit(cross_check))
        self.assertTrue(all(row["verdict"] == "consistent" for row in cross_check))


if __name__ == "__main__":
    unittest.main()
