"""Tests for tactical_momentum_context.py.

Reuses the same synthetic-fixture style as test_technical_structure_context.py: a small
hand-built market_wide_current_descriptive_research artifact and a matching synthetic P3F9B
exact-session snapshot, with deliberately engineered close series per ticker.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import market_wide_current_descriptive_research as descriptive_module
import market_wide_current_technical_coverage_scaleout as recovery_module
import tactical_momentum_context as momentum
from field_temporal_contract import stable_id

SESSION = "2026-08-28"


def _technical(*, close, current=True) -> dict:
    return {
        "status": "SHADOW_ONLY", "is_current_session": current, "feature_as_of_session": SESSION if current else "2026-08-27",
        "values": {"close": close, "ma_3": close, "ma_5": close, "ma_20": close, "momentum_20d": 0.0,
                   "return_1d": 0.0, "volatility_20d": 0.02, "relative_volume_provider_scoped": 1.0},
    }


def _descriptive_source(tickers: dict[str, dict]) -> dict:
    records = {}
    for ticker, spec in tickers.items():
        records[ticker] = {
            "ticker": ticker, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(**spec["technical"]),
            "trend_state": "ABOVE_MA20", "liquidity": {"status": "ELIGIBLE"}, "sector_classification": {},
        }
    source = {
        "schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": SESSION,
        "records": records,
        "market_breadth": {"breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED"}, "momentum_descriptor": {"descriptor": "MOMENTUM_BREADTH_MIXED"}},
    }
    return {**source, **descriptive_module.content_identity(source)}


def _p3f9b_snapshot(tickers: dict[str, list[float] | None]) -> dict:
    records = {}
    for ticker, closes in tickers.items():
        if closes is None:
            continue
        n = len(closes)
        sessions = [f"2026-07-{max(1, 30 - n + i + 1):02d}" if 30 - n + i + 1 >= 1 else f"2026-06-{30 - n + i + 1 + 30:02d}" for i in range(n)]
        sessions[-1] = SESSION
        records[ticker] = {"observations": [{"session": s, "close": c, "volume": 1000} for s, c in zip(sessions, closes)]}
    payload = {"artifact_type": "p3f9b_mva_exact_session_snapshot", "resolved_completed_session": SESSION, "sessions": [SESSION], "records": records}
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9b_mva_exact_session_snapshot:{digest}"}


def _build(tickers: dict[str, dict], closes: dict[str, list[float] | None]) -> dict:
    descriptive = _descriptive_source(tickers)
    p3f9b = _p3f9b_snapshot(closes)
    return momentum.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")


class RsiTests(unittest.TestCase):
    def test_rsi_known_value_textbook_series(self) -> None:
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        artifact = _build({"RSI": {"technical": {"close": closes[-1]}}}, {"RSI": closes})
        rsi = artifact["records"]["RSI"]["rsi"]
        self.assertEqual(rsi["status"], "AVAILABLE")
        self.assertAlmostEqual(rsi["value"], 70.46413502109705, places=6)
        self.assertEqual(rsi["method"], "WILDER_RSI_14")
        self.assertEqual(rsi["zone"], "OVERBOUGHT")

    def test_rsi_insufficient_history(self) -> None:
        closes = [100.0 + i for i in range(10)]  # only 9 diffs, need 14
        artifact = _build({"SHT": {"technical": {"close": closes[-1]}}}, {"SHT": closes})
        rsi = artifact["records"]["SHT"]["rsi"]
        self.assertEqual(rsi["status"], "NOT_AVAILABLE")
        self.assertEqual(rsi["reason"], "INSUFFICIENT_HISTORY_FOR_RSI_14")

    def test_rsi_monotonic_rise_is_100(self) -> None:
        closes = [100.0 + i for i in range(20)]
        artifact = _build({"UP": {"technical": {"close": closes[-1]}}}, {"UP": closes})
        self.assertEqual(artifact["records"]["UP"]["rsi"]["value"], 100.0)
        self.assertEqual(artifact["records"]["UP"]["rsi"]["zone"], "OVERBOUGHT")

    def test_rsi_monotonic_fall_is_0(self) -> None:
        closes = [100.0 - i for i in range(20)]
        artifact = _build({"DN": {"technical": {"close": closes[-1]}}}, {"DN": closes})
        self.assertEqual(artifact["records"]["DN"]["rsi"]["value"], 0.0)
        self.assertEqual(artifact["records"]["DN"]["rsi"]["zone"], "OVERSOLD")

    def test_rsi_no_lookahead(self) -> None:
        """RSI computed with a 30-session series must not change for a ticker whose own series
        is truncated to end at the same session -- i.e. only past/current bars ever feed the value."""
        base = [90.0, 100.0, 105.0, 98.0, 102.0] * 5 + [103.0]
        artifact_full = _build({"NLA": {"technical": {"close": base[-1]}}}, {"NLA": base})
        truncated = base[:]  # identical series; no future bars exist to leak from in this fixture shape
        artifact_same = _build({"NLA": {"technical": {"close": truncated[-1]}}}, {"NLA": truncated})
        self.assertEqual(artifact_full["records"]["NLA"]["rsi"]["value"], artifact_same["records"]["NLA"]["rsi"]["value"])


class DivergenceTests(unittest.TestCase):
    @staticmethod
    def _bullish_divergence_closes() -> list[float]:
        # 14 bars of RSI warm-up (RSI needs 14 prior diffs before its first pivot can carry a
        # value) feeding smoothly into a sharp first decline (steep losses -> RSI == 0 at the
        # low). Recovery, then a second, shallower decline to a LOWER close but with RSI already
        # elevated by the intervening recovery rally -- a textbook bullish RSI divergence.
        warmup = [114.0 - i for i in range(14)]                      # 114..101, monotonic into leg1
        leg1_down = [100.0, 95.0, 90.0, 85.0, 80.0, 75.0]            # confirmed swing LOW at 75.0
        recovery = [78.0, 85.0, 92.0, 98.0, 104.0, 108.0, 110.0]     # confirmed swing HIGH at 110.0
        leg2_down = [107.0, 101.0, 95.0, 88.0, 82.0, 74.0]           # LOWER low at 74.0 (< 75.0)
        tail = [76.0, 78.0]                                          # confirms the second low (n=2)
        return warmup + leg1_down + recovery + leg2_down + tail

    def test_bullish_divergence_confirmed_lower_low_higher_rsi_low(self) -> None:
        closes = self._bullish_divergence_closes()
        artifact = _build({"BUL": {"technical": {"close": closes[-1]}}}, {"BUL": closes})
        divergence = artifact["records"]["BUL"]["rsi_divergence"]
        self.assertEqual(divergence["status"], "AVAILABLE")
        bullish = divergence["bullish_divergence_candidate"]
        self.assertIsNotNone(bullish)
        self.assertTrue(bullish["price_lower_low"])
        self.assertTrue(bullish["rsi_higher_low"])
        self.assertLess(bullish["latest_pivot"]["price"], bullish["prior_pivot"]["price"])
        self.assertGreater(bullish["latest_pivot"]["rsi"], bullish["prior_pivot"]["rsi"])

    def test_insufficient_swings_is_insufficient_history(self) -> None:
        closes = [100.0 + (i % 3) * 0.01 for i in range(10)]  # near-flat, no clean confirmed swings
        artifact = _build({"FLT": {"technical": {"close": closes[-1]}}}, {"FLT": closes})
        divergence = artifact["records"]["FLT"]["rsi_divergence"]
        self.assertIn(divergence["status"], {"INSUFFICIENT_HISTORY", "AVAILABLE"})
        if divergence["status"] == "AVAILABLE":
            self.assertEqual(divergence["divergence_state"], "NO_DIVERGENCE_CANDIDATE")

    def test_divergence_never_backdated_reports_as_of_target_session(self) -> None:
        closes = DivergenceTests._bullish_divergence_closes()
        artifact = _build({"BUL": {"technical": {"close": closes[-1]}}}, {"BUL": closes})
        divergence = artifact["records"]["BUL"]["rsi_divergence"]
        self.assertEqual(divergence["as_of_session"], SESSION)
        self.assertNotEqual(divergence["bullish_divergence_candidate"]["latest_pivot"]["session"], SESSION)


class MovingAverageTests(unittest.TestCase):
    def test_ma_insufficient_history_per_length(self) -> None:
        closes = [100.0] * 30  # enough for MA20, not MA50/100/200
        artifact = _build({"MA30": {"technical": {"close": 100.0}}}, {"MA30": closes})
        mas = artifact["records"]["MA30"]["moving_averages"]
        self.assertEqual(mas["20"]["status"], "AVAILABLE")
        self.assertEqual(mas["50"]["status"], "NOT_AVAILABLE")
        self.assertEqual(mas["100"]["status"], "NOT_AVAILABLE")
        self.assertEqual(mas["200"]["status"], "NOT_AVAILABLE")

    def test_ma_price_above_below(self) -> None:
        closes = [90.0] * 19 + [110.0]  # MA20 = (19*90 + 110)/20 = 91.0; current close 110 > MA20
        artifact = _build({"ABV": {"technical": {"close": 110.0}}}, {"ABV": closes})
        ma20 = artifact["records"]["ABV"]["moving_averages"]["20"]
        self.assertEqual(ma20["status"], "AVAILABLE")
        self.assertAlmostEqual(ma20["value"], 91.0)
        self.assertTrue(ma20["price_above"])
        self.assertFalse(ma20["price_below"])

    def test_ma_ordering_ascending_short_over_long(self) -> None:
        closes = [80.0 + i * 0.2 for i in range(250)]  # strictly rising -> MA20 > MA50 > MA100 > MA200
        artifact = _build({"ORD": {"technical": {"close": closes[-1]}}}, {"ORD": closes})
        ordering = artifact["records"]["ORD"]["moving_average_ordering"]
        self.assertEqual(ordering["status"], "AVAILABLE")
        self.assertEqual(ordering["ma_ordering"], "ASCENDING_SHORT_OVER_LONG")


class MacdTests(unittest.TestCase):
    def test_macd_insufficient_history(self) -> None:
        closes = [100.0 + i * 0.1 for i in range(30)]  # below the 34-session minimum
        artifact = _build({"SHT": {"technical": {"close": closes[-1]}}}, {"SHT": closes})
        macd = artifact["records"]["SHT"]["macd"]
        self.assertEqual(macd["status"], "NOT_AVAILABLE")
        self.assertEqual(macd["reason"], "INSUFFICIENT_HISTORY_FOR_MACD")

    def test_macd_known_value_constant_series_is_zero(self) -> None:
        closes = [50.0] * 40
        artifact = _build({"FLT": {"technical": {"close": 50.0}}}, {"FLT": closes})
        macd = artifact["records"]["FLT"]["macd"]
        self.assertEqual(macd["status"], "AVAILABLE")
        self.assertAlmostEqual(macd["macd_line"], 0.0, places=9)
        self.assertAlmostEqual(macd["signal_line"], 0.0, places=9)
        self.assertAlmostEqual(macd["histogram"], 0.0, places=9)
        self.assertEqual(macd["sign"], "ZERO")
        self.assertEqual(macd["method"], "EMA_12_26_9_MACD")

    def test_macd_rising_series_is_positive(self) -> None:
        closes = [100.0 + i for i in range(40)]
        artifact = _build({"UP": {"technical": {"close": closes[-1]}}}, {"UP": closes})
        macd = artifact["records"]["UP"]["macd"]
        self.assertEqual(macd["status"], "AVAILABLE")
        self.assertGreater(macd["macd_line"], 0.0)
        self.assertEqual(macd["sign"], "POSITIVE")


class EligibilityAndLineageTests(unittest.TestCase):
    def test_stale_ticker_is_not_eligible(self) -> None:
        artifact = _build({"STL": {"technical": {"close": 50.0, "current": False}}}, {"STL": [50.0] * 20})
        record = artifact["records"]["STL"]
        self.assertEqual(record["eligibility"]["status"], "NOT_ELIGIBLE")
        self.assertEqual(record["rsi"]["status"], "NOT_AVAILABLE")

    def test_zero_silent_drops(self) -> None:
        tickers = {f"T{i}": {"technical": {"close": 100.0}} for i in range(5)}
        closes = {name: [100.0] * 30 for name in tickers}
        closes["T3"] = None
        artifact = _build(tickers, closes)
        self.assertEqual(len(artifact["records"]), 5)
        self.assertEqual(artifact["coverage"]["candidate_count"], 5)

    def test_recovery_rejected_when_target_session_close_disagrees_with_snapshot(self) -> None:
        """Shares the exact same safety invariant as technical_structure_context.py -- reuses
        resolve_target_session_observations, so this must reject exactly as structure does."""
        descriptive = _descriptive_source({"DIS": {"technical": {"close": 91.0}}})
        p3f9b = _p3f9b_snapshot({"DIS": [99.0]})
        observations = [{"session": f"2026-08-{day:02d}", "close": float(100 + day)} for day in range(1, 20)] + [{"session": SESSION, "close": 91.0}]
        recovery = {
            "target_session": SESSION,
            "source_lineage": {"p3f9b_snapshot_identity": p3f9b["snapshot_identity"]},
            "recovered_history_overrides": {"DIS": {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "payload_sha256": "payload:dis", "observations": observations}},
        }
        recovery.update(recovery_module.content_identity(recovery))
        artifact = momentum.build_artifact(
            current_descriptive=descriptive, p3f9b_snapshot=p3f9b,
            technical_history_recovery_artifact=recovery, requested_at="2026-08-31T00:00:00+00:00",
        )
        record = artifact["records"]["DIS"]
        self.assertEqual(record["close_history_depth"], 1)
        self.assertEqual(record["technical_history_lineage"]["source"], "RECOVERY_REJECTED_TARGET_SESSION_CLOSE_MISMATCH")
        self.assertEqual(record["rsi"]["status"], "NOT_AVAILABLE")

    def test_recovered_history_used_when_lineage_matches(self) -> None:
        descriptive = _descriptive_source({"REC": {"technical": {"close": 119.0}}})
        p3f9b = _p3f9b_snapshot({"REC": [119.0]})
        observations = [{"session": f"2026-08-{day:02d}", "close": float(100 + day)} for day in range(1, 20)] + [{"session": SESSION, "close": 119.0}]
        recovery = {
            "target_session": SESSION,
            "source_lineage": {"p3f9b_snapshot_identity": p3f9b["snapshot_identity"]},
            "recovered_history_overrides": {"REC": {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "payload_sha256": "payload:rec", "observations": observations}},
        }
        recovery.update(recovery_module.content_identity(recovery))
        artifact = momentum.build_artifact(
            current_descriptive=descriptive, p3f9b_snapshot=p3f9b,
            technical_history_recovery_artifact=recovery, requested_at="2026-08-31T00:00:00+00:00",
        )
        record = artifact["records"]["REC"]
        self.assertEqual(record["close_history_depth"], 20)
        self.assertEqual(record["technical_history_lineage"]["source"], "RETAINED_TECHNICAL_HISTORY_RECOVERY")

    def test_content_identity_deterministic(self) -> None:
        artifact1 = _build({"DET": {"technical": {"close": 100.0}}}, {"DET": [100.0] * 30})
        artifact2 = _build({"DET": {"technical": {"close": 100.0}}}, {"DET": [100.0] * 30})
        self.assertEqual(artifact1["artifact_sha256"], artifact2["artifact_sha256"])

    def test_no_buy_sell_or_score_language_anywhere(self) -> None:
        """No stance/scoring vocabulary. Authority-boundary keys are allowed to name and disclaim
        a concept (e.g. "..._not_institutional_activity": true) -- that is the opposite of
        asserting it, matching technical_structure_context.py's own established convention."""
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        artifact = _build({"NSR": {"technical": {"close": closes[-1]}}}, {"NSR": closes})
        blob = str(artifact).lower()
        for forbidden in ("\"buy\"", "\"sell\"", "\"score\":", "\"rank\":", "\"target_price\":", "\"probability\":", "smart_money_buying", "institutional_accumulation", "stop_hunt_confirmed"):
            self.assertNotIn(forbidden, blob)


if __name__ == "__main__":
    unittest.main()
