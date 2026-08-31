"""Tests for tactical_setup_tags.py.

Builds current_descriptive by hand, derives current_screening through the REAL
current_market_screening_opportunity_comparison_foundation.build_artifact() (no hand-duplicated
percentile logic), builds technical_structure_context through the REAL
technical_structure_context.build_artifact(), and hand-builds current_leadership/tactical (their own
content_identity() is a pure hash function, same convention used by every other sibling test in this
codebase).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import current_market_screening_opportunity_comparison_foundation as screening_module
import current_market_sector_leadership_context as leadership_module
import market_wide_current_descriptive_research as descriptive_module
import tactical_setup_tags as tags_module
import technical_structure_context as structure
import watchlist_tactical_entry_classifier as tactical_module
from field_temporal_contract import stable_id

SESSION = "2026-08-28"


def _technical(*, close, ma20, momentum, return_1d, relvol=1.0):
    return {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": SESSION,
            "values": {"close": close, "ma_3": close, "ma_5": close, "ma_20": ma20, "momentum_20d": momentum,
                       "return_1d": return_1d, "volatility_20d": 0.02, "relative_volume_provider_scoped": relvol}}


# ticker: (close, ma20, momentum, return_1d, relative_volume, trend_state)
_SPECS = {
    "NSP": (96.0, 100.0, 0.02, 0.001, 1.0, "ABOVE_MA20"),    # near support (95, within 2% band), above MA20 -> PULLBACK_TO_SUPPORT_IN_UPTREND
    "BRK": (112.0, 100.0, 0.15, 0.05, 3.0, "ABOVE_MA20"),    # breakout, high relative volume
    "DET": (95.0, 100.0, -0.05, -0.01, 1.0, "AT_OR_BELOW_MA20"),  # technical deterioration
    "PVD": (98.0, 100.0, -0.02, 0.0, 3.0, "AT_OR_BELOW_MA20"),    # return_1d == 0.0 (not missing) with elevated volume
    "MID": (100.0, 100.0, 0.0, 0.0, 1.0, "ABOVE_MA20"),      # bland ticker: no forced tags
}
# Closes engineered so BRK's last bar clears the prior-19 max, others sit inside a flat 95-105 band.
_FLAT_19 = [95.0, 100.0, 105.0, 98.0, 102.0] * 3 + [100.0, 101.0, 99.0, 100.0]
_CLOSES = {
    "NSP": _FLAT_19 + [96.0],
    "BRK": _FLAT_19 + [112.0],
    "DET": _FLAT_19 + [95.0],
    "PVD": _FLAT_19 + [98.0],
    "MID": _FLAT_19 + [100.0],
}


def _descriptive_source() -> dict:
    records = {}
    for ticker, (close, ma20, momentum, return_1d, relvol, trend) in _SPECS.items():
        records[ticker] = {
            "ticker": ticker, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": _technical(close=close, ma20=ma20, momentum=momentum, return_1d=return_1d, relvol=relvol),
            "trend_state": trend, "liquidity": {"status": "ELIGIBLE"}, "sector_classification": {},
        }
    source = {
        "schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": SESSION,
        "records": records,
        "market_breadth": {"breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED"}, "momentum_descriptor": {"descriptor": "MOMENTUM_BREADTH_MIXED"}},
        "validation": {"coverage": {"current_active_equity_denominator": len(records), "observed_session_cohort": len(records)}, "lineage": {}},
    }
    return {**source, **descriptive_module.content_identity(source)}


def _p3f9b_snapshot(closes_by_ticker: dict[str, list[float]] | None = None) -> dict:
    records = {}
    for ticker, closes in (closes_by_ticker or _CLOSES).items():
        n = len(closes)
        sessions = [f"2026-08-{max(1, 28 - n + i + 1):02d}" for i in range(n)]
        sessions[-1] = SESSION
        records[ticker] = {"observations": [{"session": s, "close": c, "volume": 1000} for s, c in zip(sessions, closes)]}
    payload = {"artifact_type": "p3f9b_mva_exact_session_snapshot", "resolved_completed_session": SESSION, "sessions": [SESSION], "records": records}
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9b_mva_exact_session_snapshot:{digest}"}


def _leadership_source(descriptive) -> dict:
    ticker_contexts = {
        "NSP": {"market_relative_momentum": {"status": "AVAILABLE", "momentum_bucket": "UPPER_MIDDLE"}, "sector_relative_momentum": {"status": "UNAVAILABLE"}, "sector_leadership_context": {"status": "UNAVAILABLE"}},
        "BRK": {"market_relative_momentum": {"status": "AVAILABLE", "momentum_bucket": "UPPER_QUARTILE"}, "sector_relative_momentum": {"status": "AVAILABLE", "momentum_bucket": "UPPER_QUARTILE"}, "sector_leadership_context": {"status": "AVAILABLE", "leadership_state": "LEADING"}},
        "DET": {"market_relative_momentum": {"status": "AVAILABLE", "momentum_bucket": "LOWER_QUARTILE"}, "sector_relative_momentum": {"status": "AVAILABLE", "momentum_bucket": "LOWER_QUARTILE"}, "sector_leadership_context": {"status": "AVAILABLE", "leadership_state": "WEAKENING"}},
        "PVD": {"market_relative_momentum": {"status": "UNAVAILABLE"}, "sector_relative_momentum": {"status": "UNAVAILABLE"}, "sector_leadership_context": {"status": "UNAVAILABLE"}},
        "MID": {"market_relative_momentum": {"status": "AVAILABLE", "momentum_bucket": "UPPER_MIDDLE"}, "sector_relative_momentum": {"status": "UNAVAILABLE"}, "sector_leadership_context": {"status": "UNAVAILABLE"}},
    }
    source = {"schema_version": "1.0.0", "contract_version": "current_market_sector_leadership_context/v1", "session": SESSION,
              "market": {"current_breadth_state": "DETERIORATING_BREADTH"}, "ticker_contexts": ticker_contexts}
    return {**source, **leadership_module.content_identity(source)}


def _tactical_source() -> dict:
    records = {ticker: {"entry_state": "EARLY_REVERSAL_CANDIDATE" if ticker == "NSP" else "UPTREND_CONFIRMED"} for ticker in _SPECS}
    source = {"schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": SESSION,
              "source_artifacts": {}, "records": records}
    return {**source, **tactical_module.content_identity(source)}


def _build():
    descriptive = _descriptive_source()
    screening = screening_module.build_artifact(descriptive)
    p3f9b = _p3f9b_snapshot()
    technical_structure = structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")
    leadership = _leadership_source(descriptive)
    tactical = _tactical_source()
    artifact = tags_module.build_artifact(
        technical_structure=technical_structure, current_descriptive=descriptive, current_screening=screening,
        current_leadership=leadership, tactical=tactical, requested_at="2026-08-31T00:00:00+00:00",
    )
    return artifact


class TacticalSetupTagsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = _build()
        self.records = self.artifact["records"]

    def test_pullback_to_support_in_uptrend(self) -> None:
        self.assertIn("NEAR_SUPPORT", self.records["NSP"]["active_setup_ids"])
        self.assertIn("PULLBACK_TO_SUPPORT_IN_UPTREND", self.records["NSP"]["active_setup_ids"])

    def test_early_reversal_structure_is_passthrough_of_primary_state(self) -> None:
        self.assertIn("EARLY_REVERSAL_STRUCTURE", self.records["NSP"]["active_setup_ids"])
        self.assertNotIn("EARLY_REVERSAL_STRUCTURE", self.records["BRK"]["active_setup_ids"])

    def test_breakout_confirmed_and_sector_leading(self) -> None:
        active = self.records["BRK"]["active_setup_ids"]
        self.assertIn("BREAKOUT_CONFIRMED_BY_RULE", active)
        self.assertIn("RELATIVE_STRENGTH_LEADER", active)
        self.assertIn("SECTOR_LEADING", active)

    def test_technical_deterioration_and_sector_weakening(self) -> None:
        active = self.records["DET"]["active_setup_ids"]
        self.assertIn("TECHNICAL_DETERIORATION", active)
        self.assertIn("SECTOR_WEAKENING", active)
        self.assertIn("RELATIVE_STRENGTH_LAGGARD", active)

    def test_zero_return_with_elevated_volume_is_distribution_risk_not_missing(self) -> None:
        """return_1d == 0.0 must be treated as a real non-positive value, not as missing/UNAVAILABLE."""
        evaluation = next(item for item in self.records["PVD"]["setup_evaluations"] if item["setup_id"] == "PRICE_VOLUME_DISTRIBUTION_RISK")
        self.assertEqual(evaluation["qualification_state"], "QUALIFIED_SHADOW")
        self.assertIn("PRICE_VOLUME_DISTRIBUTION_RISK", self.records["PVD"]["active_setup_ids"])

    def test_no_universal_relative_volume_multiplier_gate(self) -> None:
        """Behavioral check, not a text search: a ticker whose relative_volume_provider_scoped sits
        BELOW the retired 1.5x heuristic must still trigger PRICE_VOLUME_DISTRIBUTION_RISK if it is
        above the real cross-sectional cohort median (the only rule this module actually applies)."""
        below_old_threshold_relvol = 1.2  # below 1.5x, but this fixture's cohort median is 1.0
        specs = dict(_SPECS)
        specs["LOW_MULT"] = (98.0, 100.0, -0.02, -0.01, below_old_threshold_relvol, "AT_OR_BELOW_MA20")
        closes = dict(_CLOSES)
        closes["LOW_MULT"] = _FLAT_19 + [98.0]
        records = {}
        for ticker, (close, ma20, momentum, return_1d, relvol, trend) in specs.items():
            records[ticker] = {
                "ticker": ticker, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
                "technical_features": _technical(close=close, ma20=ma20, momentum=momentum, return_1d=return_1d, relvol=relvol),
                "trend_state": trend, "liquidity": {"status": "ELIGIBLE"}, "sector_classification": {},
            }
        source = {"schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": SESSION,
                 "records": records, "market_breadth": {"breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED"}, "momentum_descriptor": {"descriptor": "MOMENTUM_BREADTH_MIXED"}},
                 "validation": {"coverage": {"current_active_equity_denominator": len(records), "observed_session_cohort": len(records)}, "lineage": {}}}
        descriptive = {**source, **descriptive_module.content_identity(source)}
        screening = screening_module.build_artifact(descriptive)
        membership = screening["records"]["LOW_MULT"]["screen_membership"]["RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN"]
        self.assertTrue(membership["member"], "fixture must actually place 1.2 above the cohort median for this test to prove anything")
        p3f9b = _p3f9b_snapshot(closes)
        technical_structure = structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")
        leadership = _leadership_source(descriptive)
        tactical_records = {ticker: {"entry_state": "UPTREND_CONFIRMED"} for ticker in specs}
        tactical_source = {"schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": SESSION, "source_artifacts": {}, "records": tactical_records}
        tactical = {**tactical_source, **tactical_module.content_identity(tactical_source)}
        artifact = tags_module.build_artifact(technical_structure=technical_structure, current_descriptive=descriptive, current_screening=screening,
                                              current_leadership=leadership, tactical=tactical, requested_at="2026-08-31T00:00:00+00:00")
        self.assertIn("PRICE_VOLUME_DISTRIBUTION_RISK", artifact["records"]["LOW_MULT"]["active_setup_ids"])

    def test_market_regime_headwind_is_context_not_forced(self) -> None:
        # DETERIORATING_BREADTH market state -> MARKET_REGIME_HEADWIND present for every ticker,
        # but it must never gate NEAR_SUPPORT/BREAKOUT/etc for BRK (still an uptrend/breakout ticker).
        self.assertIn("MARKET_REGIME_HEADWIND", self.records["BRK"]["active_setup_ids"])
        self.assertIn("BREAKOUT_CONFIRMED_BY_RULE", self.records["BRK"]["active_setup_ids"])

    def test_no_tag_forced_to_appear(self) -> None:
        self.assertEqual(self.records["MID"]["record_setup_state"] in ("NO_DISTINCT_SETUP", "SINGLE_SETUP_CONTEXT"), True)

    def test_unavailable_when_leadership_context_absent(self) -> None:
        evaluation = next(item for item in self.records["PVD"]["setup_evaluations"] if item["setup_id"] == "RELATIVE_STRENGTH_LEADER")
        self.assertEqual(evaluation["qualification_state"], "UNAVAILABLE")

    def test_no_score_rank_target_or_probability_anywhere(self) -> None:
        blob = str(self.artifact)
        for forbidden in ("\"score\":", "\"rank\":", "\"target_price\":", "\"probability\":"):
            self.assertNotIn(forbidden, blob)

    def test_rsi_adx_not_referenced_as_gates(self) -> None:
        """No tag's required_feature_identities or observed_feature_values ever names RSI/ADX/MACD:
        this module has no dependency on those indicators at all, gate or otherwise."""
        forbidden = ("rsi", "adx", "macd")
        for setup_id, entry in tags_module.REGISTRY.items():
            for feature in entry["required_features"]:
                self.assertFalse(any(term in feature.lower() for term in forbidden), f"{setup_id} required_features unexpectedly names an RSI/ADX/MACD feature: {feature}")
        for record in self.records.values():
            for evaluation in record["setup_evaluations"]:
                for key in evaluation["observed_feature_values"]:
                    self.assertFalse(any(term in key.lower() for term in forbidden), f"{evaluation['setup_id']} observed_feature_values unexpectedly names an RSI/ADX/MACD field: {key}")

    def test_deterministic_identity(self) -> None:
        self.assertEqual(_build()["artifact_sha256"], self.artifact["artifact_sha256"])

    def test_zero_silent_drops(self) -> None:
        self.assertEqual(self.artifact["coverage"]["candidate_count"], len(_SPECS))
        self.assertEqual(len(self.records), len(_SPECS))


if __name__ == "__main__":
    unittest.main()
