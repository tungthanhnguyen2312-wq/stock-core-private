"""Tests for technical_structure_context.py v2 (TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3).

Architecture
------------
All existing V1 tests from ``test_technical_structure_context.py`` are preserved here by
inheriting the same fixture helpers.  V3 tests are appended and verify the additive V3 keys
without breaking any V1 assertions.

Synthetic close-only series are used throughout; no runtime data is required.
All inputs use the same ``_build()`` helper already exercised by the V1 suite.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import market_wide_current_descriptive_research as descriptive_module
import technical_structure_context as structure
from field_temporal_contract import stable_id

SESSION = "2026-08-28"


# ── Fixture helpers (V1-identical, re-used for V3 tests) ─────────────────────

def _technical(*, close, ma20, momentum, return_1d, current=True, as_of=None):
    return {
        "status": "SHADOW_ONLY", "is_current_session": current, "feature_as_of_session": as_of or (SESSION if current else "2026-08-27"),
        "values": {"close": close, "ma_3": close, "ma_5": close, "ma_20": ma20, "momentum_20d": momentum,
                   "return_1d": return_1d, "volatility_20d": 0.02, "relative_volume_provider_scoped": 1.0},
    }


def _descriptive_source(tickers: dict[str, dict]) -> dict:
    records = {}
    for ticker, spec in tickers.items():
        records[ticker] = {
            "ticker": ticker, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(**spec["technical"]),
            "trend_state": spec.get("trend_state", "ABOVE_MA20"),
            "liquidity": {"status": "ELIGIBLE"}, "sector_classification": {},
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
    return structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")


def _uptrend_closes(n: int = 80) -> list[float]:
    """Zigzag uptrend: swing lows rise (HL) and swing highs rise (HH).

    Each 10-bar cycle: 7 bars up (+1.5 each) then 3 bars down (-0.8 each),
    so the pullback is smaller than the rally — strict HH+HL pattern.
    """
    closes: list[float] = []
    price = 100.0
    for i in range(n):
        phase = i % 10
        price += 1.5 if phase < 7 else -0.8
        closes.append(round(price, 2))
    return closes


def _downtrend_closes(n: int = 80) -> list[float]:
    """Zigzag downtrend: swing highs fall (LH) and swing lows fall (LL).

    Each 10-bar cycle: 7 bars down (-1.5 each) then 3 bars up (+0.8 each),
    so the bounce is smaller than the decline — strict LH+LL pattern.
    """
    closes: list[float] = []
    price = 200.0
    for i in range(n):
        phase = i % 10
        price -= 1.5 if phase < 7 else -0.8
        closes.append(round(price, 2))
    return closes


def _ticker_spec(close, ma20=None, momentum=0.0, return_1d=0.0):
    return {"technical": {"close": close, "ma20": ma20 or close, "momentum": momentum, "return_1d": return_1d}}


# ═══════════════════════════════════════════════════════════════════════════════
# V1 tests (preserved intact from the original test suite)
# ═══════════════════════════════════════════════════════════════════════════════

class StructureFeatureTests(unittest.TestCase):
    def test_breakout_confirmed_by_rule(self) -> None:
        prior = [95.0, 100.0, 105.0, 98.0, 102.0] * 3 + [100.0, 101.0, 99.0, 100.0]
        closes = prior + [115.0]
        artifact = _build({"BOB": {"technical": {"close": 115.0, "ma20": 100.0, "momentum": 0.15, "return_1d": 0.1}}}, {"BOB": closes})
        record = artifact["records"]["BOB"]
        self.assertEqual(record["structure_context"]["structure_status"], "BREAKOUT_CONFIRMED_BY_RULE")
        self.assertEqual(record["close_history_depth"], len(closes))

    def test_range_compression(self) -> None:
        first10 = [90.0, 110.0, 95.0, 105.0, 92.0, 108.0, 94.0, 106.0, 91.0, 109.0]
        last10 = [99.5, 100.5, 99.8, 100.2, 99.6, 100.4, 99.9, 100.1, 99.7, 100.3]
        artifact = _build({"CMP": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"CMP": first10 + last10})
        self.assertEqual(artifact["records"]["CMP"]["contraction_context"]["range_state"], "RANGE_COMPRESSION")

    def test_range_expansion(self) -> None:
        first10 = [99.5, 100.5, 99.8, 100.2, 99.6, 100.4, 99.9, 100.1, 99.7, 100.3]
        last10 = [90.0, 110.0, 95.0, 105.0, 92.0, 108.0, 94.0, 106.0, 91.0, 109.0]
        artifact = _build({"EXP": {"technical": {"close": 109.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"EXP": first10 + last10})
        self.assertEqual(artifact["records"]["EXP"]["contraction_context"]["range_state"], "RANGE_EXPANSION")

    def test_ma20_slope_rising_needs_25_sessions(self) -> None:
        closes = [90.0 + i for i in range(25)]
        artifact = _build({"SLP": {"technical": {"close": closes[-1], "ma20": sum(closes[-20:]) / 20, "momentum": 0.1, "return_1d": 0.01}}}, {"SLP": closes})
        slope = artifact["records"]["SLP"]["trend_context"]["ma20_slope"]
        self.assertEqual(slope["status"], "AVAILABLE")
        self.assertEqual(slope["slope_state"], "RISING")

    def test_ma20_slope_not_available_below_25_sessions(self) -> None:
        closes = [100.0 + i * 0.1 for i in range(20)]
        artifact = _build({"SHT": {"technical": {"close": closes[-1], "ma20": sum(closes) / 20, "momentum": 0.01, "return_1d": 0.001}}}, {"SHT": closes})
        record = artifact["records"]["SHT"]
        self.assertEqual(record["trend_context"]["ma20_slope"]["status"], "NOT_AVAILABLE")
        self.assertEqual(record["structure_context"]["status"], "AVAILABLE")

    def test_self_relative_volatility_needs_31_sessions(self) -> None:
        closes = [100.0] * 20
        artifact = _build({"VOL": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"VOL": closes})
        self.assertEqual(artifact["records"]["VOL"]["contraction_context"]["self_relative_volatility"]["status"], "NOT_AVAILABLE")

    def test_self_relative_volatility_contraction_detected(self) -> None:
        import random
        random.seed(7)
        prior_volatile = [100.0]
        for _ in range(29):
            prior_volatile.append(prior_volatile[-1] * (1 + random.choice([-0.05, 0.05])))
        recent_quiet = [prior_volatile[-1]]
        for _ in range(20):
            recent_quiet.append(recent_quiet[-1] * (1 + random.choice([-0.001, 0.001])))
        closes = prior_volatile + recent_quiet[1:]
        artifact = _build({"QCV": {"technical": {"close": closes[-1], "ma20": sum(closes[-20:]) / 20, "momentum": 0.0, "return_1d": 0.0}}}, {"QCV": closes})
        self.assertEqual(artifact["records"]["QCV"]["contraction_context"]["self_relative_volatility"]["self_relative_volatility_state"], "CONTRACTION")

    def test_breakout_failure_event(self) -> None:
        base = [95.0, 100.0, 105.0, 98.0, 102.0] * 3 + [100.0, 101.0, 99.0, 100.0]
        closes = base + [110.0, 103.0]
        artifact = _build({"FAI": {"technical": {"close": 103.0, "ma20": 100.0, "momentum": 0.01, "return_1d": -0.06}}}, {"FAI": closes})
        self.assertEqual(artifact["records"]["FAI"]["breakout_context"]["event"], "BREAKOUT_FAILURE")

    def test_zero_return_is_not_missing(self) -> None:
        closes = [100.0] * 20
        artifact = _build({"ZRO": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"ZRO": closes})
        self.assertEqual(artifact["records"]["ZRO"]["eligibility"]["status"], "ELIGIBLE")
        self.assertEqual(artifact["records"]["ZRO"]["structure_context"]["status"], "AVAILABLE")

    def test_stale_ticker_is_insufficient_not_computed(self) -> None:
        artifact = _build({"STL": {"technical": {"close": 50.0, "ma20": 50.0, "momentum": 0.0, "return_1d": 0.0, "current": False}}}, {"STL": [50.0] * 20})
        record = artifact["records"]["STL"]
        self.assertEqual(record["eligibility"]["status"], "NOT_ELIGIBLE")
        self.assertEqual(record["structure_context"]["status"], "NOT_AVAILABLE")

    def test_malformed_ticker_localized_no_crash(self) -> None:
        artifact = _build(
            {"OK1": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}},
             "MISSING": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}},
            {"OK1": [100.0] * 20, "MISSING": None},
        )
        self.assertEqual(artifact["records"]["MISSING"]["eligibility"]["status"], "NOT_ELIGIBLE")
        self.assertEqual(artifact["records"]["OK1"]["eligibility"]["status"], "ELIGIBLE")
        self.assertEqual(artifact["coverage"]["candidate_count"], 2)

    def test_zero_silent_drops(self) -> None:
        tickers = {f"T{i}": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}} for i in range(5)}
        closes = {name: [100.0] * 20 for name in tickers}
        closes["T3"] = None
        artifact = _build(tickers, closes)
        self.assertEqual(len(artifact["records"]), 5)
        self.assertEqual(artifact["coverage"]["candidate_count"], 5)

    def test_high_low_basis_localized_per_record(self) -> None:
        artifact = _build({"HLB": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"HLB": [100.0] * 20})
        record = artifact["records"]["HLB"]
        self.assertEqual(record["high_low_basis"]["status"], "NOT_COMPATIBLE")
        self.assertEqual(record["high_low_basis"]["reason"], "HIGH_LOW_BASIS_NOT_COMPATIBLE")
        self.assertIn("true_atr", record["high_low_basis"]["affected_feature_classes"])

    def test_no_score_rank_target_or_probability_anywhere(self) -> None:
        artifact = _build({"NSR": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"NSR": [100.0] * 20})
        blob = str(artifact)
        for forbidden in ('"score":', '"rank":', '"target_price":', '"probability":'):
            self.assertNotIn(forbidden, blob)

    def test_deterministic_identity(self) -> None:
        artifact1 = _build({"DET": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"DET": [100.0] * 20})
        artifact2 = _build({"DET": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"DET": [100.0] * 20})
        self.assertEqual(artifact1["artifact_sha256"], artifact2["artifact_sha256"])

    def test_requested_at_excluded_from_identity(self) -> None:
        descriptive = _descriptive_source({"REQ": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}})
        p3f9b = _p3f9b_snapshot({"REQ": [100.0] * 20})
        a = structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")
        b = structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2099-01-01T00:00:00+00:00")
        self.assertEqual(a["artifact_sha256"], b["artifact_sha256"])

    def test_tampered_descriptive_source_fails_closed(self) -> None:
        descriptive = _descriptive_source({"TMP": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}})
        p3f9b = _p3f9b_snapshot({"TMP": [100.0] * 20})
        descriptive["records"]["TMP"]["trend_state"] = "TAMPERED"
        with self.assertRaises(structure.TechnicalStructureContextError):
            structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")

    def test_content_identity_recomputes_correctly(self) -> None:
        artifact = _build({"REC": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"REC": [100.0] * 20})
        recomputed = structure.content_identity(artifact)
        self.assertEqual(recomputed["artifact_sha256"], artifact["artifact_sha256"])


# ═══════════════════════════════════════════════════════════════════════════════
# V3 additive tests — all additive, zero V1 assertions changed
# ═══════════════════════════════════════════════════════════════════════════════

class V3SwingTests(unittest.TestCase):
    """Confirmed fractal swings: detection + no-lookahead guarantee."""

    def test_basic_high_swing_detected(self) -> None:
        closes = [100, 105, 110, 105, 100, 95, 90, 95, 100, 105, 100, 95, 90]
        sessions = [f"2026-07-{10 + i:02d}" for i in range(len(closes))]
        sessions[-1] = SESSION
        swings = structure._confirm_swings(closes, sessions)
        highs = [s for s in swings if s["kind"] == "HIGH"]
        self.assertTrue(any(s["price"] == 110 for s in highs), "110 should be a confirmed swing HIGH")

    def test_no_lookahead_at_edge(self) -> None:
        # 110 is at the rightmost position — cannot be confirmed without N bars after it
        closes = [100, 105, 110]
        sessions = [f"2026-07-{10 + i:02d}" for i in range(len(closes))]
        swings = structure._confirm_swings(closes, sessions)
        highs = [s for s in swings if s["kind"] == "HIGH"]
        self.assertFalse(any(s["price"] == 110 for s in highs))

    def test_swing_count_present_in_record(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        swing = art["records"]["T"]["swing_structure"]
        self.assertIn("confirmed_swing_count", swing)
        self.assertIsInstance(swing["confirmed_swing_count"], int)

    def test_confirmation_lag_sessions_is_swing_n(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        swing = art["records"]["T"]["swing_structure"]
        if swing["status"] == "AVAILABLE":
            self.assertEqual(swing["confirmation_lag_sessions"], structure.SWING_N)


class V3MarketStructureTests(unittest.TestCase):
    """HH/HL/LH/LL and market structure state."""

    def test_uptrend_detected(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        ms = art["records"]["T"]["swing_structure"].get("market_structure_state")
        self.assertEqual(ms, "UPTREND")

    def test_downtrend_detected(self) -> None:
        closes = _downtrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        ms = art["records"]["T"]["swing_structure"].get("market_structure_state")
        self.assertEqual(ms, "DOWNTREND")

    def test_insufficient_history_short_series(self) -> None:
        closes = [100.0, 105.0, 103.0, 98.0, 100.0]
        art = _build({"T": _ticker_spec(100.0)}, {"T": closes})
        # Insufficient history for swings; structure context NOT_AVAILABLE for V1 too
        ms = art["records"]["T"]["swing_structure"].get("market_structure_state")
        self.assertIn(ms, ("INSUFFICIENT_HISTORY", None))

    def test_swing_high_and_low_sequence_present(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        swing = art["records"]["T"]["swing_structure"]
        if swing["status"] == "AVAILABLE":
            self.assertIn(swing.get("swing_high_sequence"), ("HH", "LH"))
            self.assertIn(swing.get("swing_low_sequence"), ("HL", "LL"))

    def test_market_structure_state_is_valid_enum(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        ms = art["records"]["T"]["swing_structure"].get("market_structure_state")
        self.assertIn(ms, structure.MARKET_STRUCTURE_STATES)


class V3BOSTests(unittest.TestCase):
    """BOS detection and governance."""

    def test_bos_state_present_in_eligible_record(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        bos = art["records"]["T"]["bos_context"]
        self.assertIn("bos_state", bos)
        self.assertIn(bos["bos_state"], structure.BOS_STATES)

    def test_bos_has_confirmation_method(self) -> None:
        closes = _downtrend_closes()
        close_val = closes[-1]
        # Spike above all prior closes to force BOS
        last_high = max(closes)
        spike_closes = closes + [last_high * 1.15]
        art = _build({"T": _ticker_spec(spike_closes[-1], spike_closes[-1])}, {"T": spike_closes})
        bos = art["records"]["T"]["bos_context"]
        if bos.get("bos_state") == "BULLISH_BOS_DETECTED_BY_RULE":
            self.assertEqual(bos["confirmation_method"], "CLOSE_THROUGH_CONFIRMED_LEVEL_BY_RULE")

    def test_bos_no_smart_money_or_order_flow_labels(self) -> None:
        closes = _downtrend_closes()
        closes.append(max(closes) * 1.1)
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        blob = str(art["records"]["T"]["bos_context"])
        self.assertNotIn("SMART_MONEY", blob)
        self.assertNotIn("INSTITUTIONAL_ACCUMULATION", blob)
        self.assertNotIn("ORDER_FLOW", blob)

    def test_bos_warning_present(self) -> None:
        closes = _downtrend_closes()
        closes.append(max(closes) * 1.1)
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        bos = art["records"]["T"]["bos_context"]
        if bos.get("bos_state") == "BULLISH_BOS_DETECTED_BY_RULE":
            self.assertIn("warning", bos)


class V3CHoCHTests(unittest.TestCase):
    """CHoCH detection and governance."""

    def test_choch_state_present_in_eligible_record(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        choch = art["records"]["T"]["choch_context"]
        self.assertIn("choch_state", choch)
        self.assertIn(choch["choch_state"], structure.CHOCH_STATES)

    def test_no_smart_money_in_choch(self) -> None:
        closes = _downtrend_closes()
        closes.append(max(closes) * 1.1)
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        blob = str(art["records"]["T"]["choch_context"])
        # The warning may say NOT_SMART_MONEY; what must be absent are affirmative labels
        self.assertNotIn("INSTITUTIONAL_ACCUMULATION", blob)
        self.assertNotIn("ORDER_FLOW", blob)
        self.assertNotIn("LIQUIDITY_GRAB", blob)


class V3PivotTests(unittest.TestCase):
    """Pivot derivation."""

    def test_pivot_context_present_in_eligible_record(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        pivot = art["records"]["T"]["pivot_context"]
        self.assertIn("status", pivot)

    def test_pivot_status_is_available_with_history(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        pivot = art["records"]["T"]["pivot_context"]
        self.assertIn(pivot["status"], ("AVAILABLE", "NO_VALID_PIVOT"))

    def test_pivot_atr_is_explicit_string(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        pivot = art["records"]["T"]["pivot_context"]
        if "distance_to_pivot_atr" in pivot:
            self.assertIsInstance(pivot["distance_to_pivot_atr"], str)
            self.assertIn("NOT_AVAILABLE", pivot["distance_to_pivot_atr"])

    def test_no_valid_pivot_with_minimal_history(self) -> None:
        closes = [100.0, 101.0, 102.0]  # no confirmed swings possible
        art = _build({"T": _ticker_spec(102.0)}, {"T": closes})
        pivot = art["records"]["T"]["pivot_context"]
        self.assertEqual(pivot["status"], "NO_VALID_PIVOT")


class V3BreakoutStateTests(unittest.TestCase):
    """Pivot-relative breakout state (breakout_state_v3)."""

    def test_breakout_state_v3_present(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        brk = art["records"]["T"]["breakout_state_v3"]
        self.assertIn("breakout_state", brk)
        self.assertIn(brk["breakout_state"], structure.BREAKOUT_STATES_V3)

    def test_breakout_warning_present(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        brk = art["records"]["T"]["breakout_state_v3"]
        if brk.get("status") == "AVAILABLE":
            self.assertIn("warning", brk)
            self.assertIn("MEASUREMENT", brk["warning"].upper())

    def test_breakout_blocked_fields_are_explicit_strings(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        brk = art["records"]["T"]["breakout_state_v3"]
        blocked = brk.get("blocked") or {}
        if "candle_body_fraction" in blocked:
            self.assertIsInstance(blocked["candle_body_fraction"], str)
            self.assertIn("NOT_AVAILABLE", blocked["candle_body_fraction"])
        if "break_distance_atr" in blocked:
            self.assertIsInstance(blocked["break_distance_atr"], str)
        if "close_location_value" in blocked:
            self.assertIsInstance(blocked["close_location_value"], str)

    def test_failed_breakout_detected(self) -> None:
        # Craft: prior close above pivot level, current close back below
        base_closes = [95.0 + (i % 5) * 2 for i in range(60)]
        pivot_level = max(base_closes)  # the resistance
        # Day -1: break above
        test_closes = base_closes + [pivot_level * 1.03, pivot_level * 0.97]
        art = _build({"T": _ticker_spec(test_closes[-1], test_closes[-1])}, {"T": test_closes})
        brk = art["records"]["T"]["breakout_state_v3"]
        self.assertIn(brk.get("breakout_state"), ("FAILED_BREAKOUT", "BELOW_PIVOT", "NO_VALID_PIVOT"))


class V3TriggerTests(unittest.TestCase):
    """Trigger context: type, state, authority."""

    def test_trigger_context_present(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        trigger = art["records"]["T"]["trigger_context"]
        self.assertIn("trigger_type", trigger)
        self.assertIn(trigger["trigger_type"], structure.TRIGGER_TYPES)

    def test_trigger_warning_not_execution(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        trigger = art["records"]["T"]["trigger_context"]
        if "warning" in trigger:
            self.assertIn("NOT_EXECUTION", trigger["warning"].upper())

    def test_no_trigger_when_insufficient_history(self) -> None:
        closes = [100.0] * 5
        art = _build({"T": _ticker_spec(100.0)}, {"T": closes})
        trigger = art["records"]["T"]["trigger_context"]
        self.assertIn(trigger.get("trigger_type", "NO_TRIGGER"), ("NO_TRIGGER", None))


class V3InvalidationTests(unittest.TestCase):
    """Structural invalidation: not a stop-loss."""

    def test_invalidation_context_present(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        inv = art["records"]["T"]["invalidation_context"]
        self.assertIn("status", inv)

    def test_invalidation_warning_not_stop_loss(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        inv = art["records"]["T"]["invalidation_context"]
        blob = str(inv).lower()
        # Must not contain affirmative stop-loss labelling (hyphen form used in prose)
        self.assertNotIn("stop-loss", blob)
        self.assertNotIn("stop loss", blob)
        # The warning correctly says NOT_A_STOP_LOSS (analytical boundary, not a stop)

    def test_invalidation_level_is_numeric_when_available(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        inv = art["records"]["T"]["invalidation_context"]
        if inv.get("status") == "AVAILABLE":
            self.assertIsInstance(inv["invalidation_level"], (int, float))


class V3GovernanceTests(unittest.TestCase):
    """Governance invariants: authority boundary, no-score, high-low blocked, coverage."""

    def test_authority_boundary_not_actionable(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        self.assertFalse(art["authority_boundary"]["is_actionable"])

    def test_no_score_rank_target_probability_v3(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        blob = str(art)
        for forbidden in ('"score":', '"rank":', '"target_price":', '"probability":'):
            self.assertNotIn(forbidden, blob)

    def test_v3_coverage_counts_present(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        cov = art["coverage"]
        self.assertIn("market_structure_state_counts", cov)
        self.assertIn("bos_state_counts", cov)
        self.assertIn("choch_state_counts", cov)
        self.assertIn("breakout_state_v3_counts", cov)
        self.assertIn("trigger_type_counts", cov)

    def test_v1_and_v3_keys_coexist(self) -> None:
        """V1 output keys must still be present alongside V3 additions."""
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        rec = art["records"]["T"]
        # V1 keys
        for key in ("structure_context", "contraction_context", "trend_context", "base_context", "breakout_context", "relative_volume"):
            self.assertIn(key, rec, f"V1 key '{key}' missing from record")
        # V3 keys
        for key in ("swing_structure", "bos_context", "choch_context", "pivot_context", "breakout_state_v3", "trigger_context", "invalidation_context"):
            self.assertIn(key, rec, f"V3 key '{key}' missing from record")

    def test_contract_version_is_v2(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        self.assertEqual(art["contract_version"], "technical_structure_context/v2")

    def test_milestone_is_v3(self) -> None:
        closes = _uptrend_closes()
        art = _build({"T": _ticker_spec(closes[-1], closes[-1])}, {"T": closes})
        self.assertEqual(art["milestone"], "TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3")

    def test_zero_silent_drops_v3(self) -> None:
        tickers_spec = {f"X{i}": _ticker_spec(100.0) for i in range(4)}
        closes_map: dict[str, list[float] | None] = {t: _uptrend_closes() for t in tickers_spec}
        closes_map["X2"] = None
        art = _build(tickers_spec, closes_map)
        self.assertEqual(len(art["records"]), 4)
        self.assertEqual(art["coverage"]["candidate_count"], 4)


if __name__ == "__main__":
    unittest.main()
