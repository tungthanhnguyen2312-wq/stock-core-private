"""Tests for technical_structure_context.py.

Hand-builds a small synthetic market_wide_current_descriptive_research artifact and a matching
synthetic P3F9B exact-session snapshot. Close series are deliberately engineered per ticker to
exercise one feature each, rather than one combinatorial fixture covering everything at once.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import market_wide_current_descriptive_research as descriptive_module
import market_wide_current_technical_coverage_scaleout as recovery_module
import technical_structure_context as structure
from field_temporal_contract import stable_id

SESSION = "2026-08-28"


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
        # Sessions counted back from SESSION so the *last* close lands exactly on SESSION.
        sessions = [f"2026-07-{max(1, 30 - n + i + 1):02d}" if 30 - n + i + 1 >= 1 else f"2026-06-{30 - n + i + 1 + 30:02d}" for i in range(n)]
        sessions[-1] = SESSION
        records[ticker] = {"observations": [{"session": s, "close": c, "volume": 1000} for s, c in zip(sessions, closes)]}
    payload = {
        "artifact_type": "p3f9b_mva_exact_session_snapshot", "resolved_completed_session": SESSION,
        "sessions": [SESSION], "records": records,
    }
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9b_mva_exact_session_snapshot:{digest}"}


def _build(tickers: dict[str, dict], closes: dict[str, list[float] | None]) -> dict:
    descriptive = _descriptive_source(tickers)
    p3f9b = _p3f9b_snapshot(closes)
    return structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")


class StructureFeatureTests(unittest.TestCase):
    def test_recovered_history_is_the_tactical_close_series_when_lineage_matches(self) -> None:
        descriptive = _descriptive_source({"REC": {"technical": {"close": 119.0, "ma20": 110.0, "momentum": 0.1, "return_1d": 0.01}}})
        p3f9b = _p3f9b_snapshot({"REC": [119.0]})
        observations = [
            {"session": f"2026-08-{day:02d}", "close": float(100 + day)} for day in range(1, 20)
        ] + [{"session": SESSION, "close": 119.0}]
        recovery = {
            "target_session": SESSION,
            "source_lineage": {"p3f9b_snapshot_identity": p3f9b["snapshot_identity"]},
            "recovered_history_overrides": {
                "REC": {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "payload_sha256": "payload:rec", "observations": observations}
            },
        }
        recovery.update(recovery_module.content_identity(recovery))
        artifact = structure.build_artifact(
            current_descriptive=descriptive, p3f9b_snapshot=p3f9b,
            technical_history_recovery_artifact=recovery, requested_at="2026-08-31T00:00:00+00:00",
        )
        record = artifact["records"]["REC"]
        self.assertEqual(record["close_history_depth"], 20)
        self.assertEqual(record["technical_history_lineage"]["source"], "RETAINED_TECHNICAL_HISTORY_RECOVERY")
        self.assertEqual(record["structure_context"]["status"], "AVAILABLE")

    def test_recovery_rejected_when_target_session_close_disagrees_with_snapshot(self) -> None:
        """Real 2026-09-04 evidence: 34/952 recovered tickers had a DNSE recovery close that
        disagreed with the multi-source-resolved P3F9B snapshot close for the same session
        (the snapshot fell back to a KBS sole-source print before DNSE had published that day).
        Adopting the recovery series there would price Tactical V3 off a close current-research
        valuation never accepted. Must fall back to the P3F9B-only (here: 1-bar) behavior."""
        descriptive = _descriptive_source({"DIS": {"technical": {"close": 91.0, "ma20": 90.0, "momentum": 0.1, "return_1d": 0.01}}})
        p3f9b = _p3f9b_snapshot({"DIS": [99.0]})  # snapshot's own resolved close for SESSION
        observations = [
            {"session": f"2026-08-{day:02d}", "close": float(100 + day)} for day in range(1, 20)
        ] + [{"session": SESSION, "close": 91.0}]  # recovery's own close disagrees (91.0 != 99.0)
        recovery = {
            "target_session": SESSION,
            "source_lineage": {"p3f9b_snapshot_identity": p3f9b["snapshot_identity"]},
            "recovered_history_overrides": {
                "DIS": {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "payload_sha256": "payload:dis", "observations": observations}
            },
        }
        recovery.update(recovery_module.content_identity(recovery))
        artifact = structure.build_artifact(
            current_descriptive=descriptive, p3f9b_snapshot=p3f9b,
            technical_history_recovery_artifact=recovery, requested_at="2026-08-31T00:00:00+00:00",
        )
        record = artifact["records"]["DIS"]
        self.assertEqual(record["eligibility"]["status"], "ELIGIBLE")
        self.assertEqual(record["close_history_depth"], 1)
        self.assertEqual(record["technical_history_lineage"]["source"], "RECOVERY_REJECTED_TARGET_SESSION_CLOSE_MISMATCH")
        self.assertEqual(record["structure_context"]["status"], "NOT_AVAILABLE")

    def test_breakout_confirmed_by_rule(self) -> None:
        # 19 prior closes oscillating 95-105 (max 105), current close 115 -> above prior max.
        prior = [95.0, 100.0, 105.0, 98.0, 102.0] * 3 + [100.0, 101.0, 99.0, 100.0]
        closes = prior + [115.0]
        artifact = _build({"BOB": {"technical": {"close": 115.0, "ma20": 100.0, "momentum": 0.15, "return_1d": 0.1}}}, {"BOB": closes})
        record = artifact["records"]["BOB"]
        self.assertEqual(record["structure_context"]["structure_status"], "BREAKOUT_CONFIRMED_BY_RULE")
        self.assertEqual(record["close_history_depth"], len(closes))

    def test_range_compression(self) -> None:
        first10 = [90.0, 110.0, 95.0, 105.0, 92.0, 108.0, 94.0, 106.0, 91.0, 109.0]  # range 20
        last10 = [99.5, 100.5, 99.8, 100.2, 99.6, 100.4, 99.9, 100.1, 99.7, 100.3]   # range 1
        artifact = _build({"CMP": {"technical": {"close": 100.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"CMP": first10 + last10})
        self.assertEqual(artifact["records"]["CMP"]["contraction_context"]["range_state"], "RANGE_COMPRESSION")

    def test_range_expansion(self) -> None:
        first10 = [99.5, 100.5, 99.8, 100.2, 99.6, 100.4, 99.9, 100.1, 99.7, 100.3]  # range 1
        last10 = [90.0, 110.0, 95.0, 105.0, 92.0, 108.0, 94.0, 106.0, 91.0, 109.0]   # range 20
        artifact = _build({"EXP": {"technical": {"close": 109.0, "ma20": 100.0, "momentum": 0.0, "return_1d": 0.0}}}, {"EXP": first10 + last10})
        self.assertEqual(artifact["records"]["EXP"]["contraction_context"]["range_state"], "RANGE_EXPANSION")

    def test_ma20_slope_rising_needs_25_sessions(self) -> None:
        closes = [90.0 + i for i in range(25)]  # strictly rising: today's MA20 > MA20 5 sessions ago
        artifact = _build({"SLP": {"technical": {"close": closes[-1], "ma20": sum(closes[-20:]) / 20, "momentum": 0.1, "return_1d": 0.01}}}, {"SLP": closes})
        slope = artifact["records"]["SLP"]["trend_context"]["ma20_slope"]
        self.assertEqual(slope["status"], "AVAILABLE")
        self.assertEqual(slope["slope_state"], "RISING")

    def test_ma20_slope_not_available_below_25_sessions(self) -> None:
        closes = [100.0 + i * 0.1 for i in range(20)]  # exactly 20: enough for structure, not for slope (needs 25)
        artifact = _build({"SHT": {"technical": {"close": closes[-1], "ma20": sum(closes) / 20, "momentum": 0.01, "return_1d": 0.001}}}, {"SHT": closes})
        record = artifact["records"]["SHT"]
        self.assertEqual(record["trend_context"]["ma20_slope"]["status"], "NOT_AVAILABLE")
        self.assertEqual(record["structure_context"]["status"], "AVAILABLE")  # structure still computable at exactly 20

    def test_self_relative_volatility_needs_31_sessions(self) -> None:
        closes = [100.0] * 20  # exactly 20 closes: below the 31-session self-relative-volatility requirement
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
        # Day-2-ago through day-21-ago: flat-ish base with max 105. Yesterday closes at 110 (breakout).
        # Today closes at 103 (back below yesterday's resistance of 105) -> BREAKOUT_FAILURE.
        base = [95.0, 100.0, 105.0, 98.0, 102.0] * 3 + [100.0, 101.0, 99.0, 100.0]  # 19 values, max 105
        closes = base + [110.0, 103.0]  # yesterday breakout, today fails back below
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
        """A ticker with no P3F9B record at all gets an explicit insufficient record; other tickers unaffected."""
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
        closes["T3"] = None  # one deliberately missing close series
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
        for forbidden in ("\"score\":", "\"rank\":", "\"target_price\":", "\"probability\":"):
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


if __name__ == "__main__":
    unittest.main()
