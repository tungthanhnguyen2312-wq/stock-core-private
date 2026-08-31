"""Tests for tactical_behavior_context.py: the compact end-to-end composition.

Runs a full small pipeline through the REAL modules (descriptive -> screening -> p3f9b ->
technical_structure_context -> tactical_setup_tags -> tactical_confirmation_invalidation_boundaries
-> tactical_behavior_context) rather than hand-faking any intermediate artifact, so this test also
exercises the real wiring between all four new V2 modules.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import current_market_screening_opportunity_comparison_foundation as screening_module
import current_market_sector_leadership_context as leadership_module
import market_wide_current_descriptive_research as descriptive_module
import tactical_behavior_context as compact_module
import tactical_confirmation_invalidation_boundaries as boundaries_module
import tactical_setup_tags as tags_module
import technical_structure_context as structure
import watchlist_tactical_entry_classifier as tactical_module
from field_temporal_contract import stable_id

SESSION = "2026-08-28"
_FLAT19 = [95.0, 100.0, 105.0, 98.0, 102.0] * 3 + [100.0, 101.0, 99.0, 100.0]
_SPECS = {
    "BRK": {"close": 112.0, "ma20": 100.0, "momentum": 0.15, "return_1d": 0.05, "relvol": 3.0, "trend": "ABOVE_MA20", "entry_state": "BREAKOUT_READY", "close_series": _FLAT19 + [112.0]},
    "DWN": {"close": 88.0, "ma20": 100.0, "momentum": -0.08, "return_1d": -0.01, "relvol": 0.9, "trend": "AT_OR_BELOW_MA20", "entry_state": "DOWNTREND", "close_series": _FLAT19 + [88.0]},
}


def _descriptive_source() -> dict:
    records = {}
    for ticker, spec in _SPECS.items():
        records[ticker] = {
            "ticker": ticker, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": SESSION,
                                    "values": {"close": spec["close"], "ma_3": spec["close"], "ma_5": spec["close"], "ma_20": spec["ma20"],
                                               "momentum_20d": spec["momentum"], "return_1d": spec["return_1d"], "volatility_20d": 0.02,
                                               "relative_volume_provider_scoped": spec["relvol"]}},
            "trend_state": spec["trend"], "liquidity": {"status": "ELIGIBLE"}, "sector_classification": {},
        }
    source = {"schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": SESSION,
              "records": records, "input_lineage": {"p3f9b_snapshot_identity": None},
              "market_breadth": {"breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED"}, "momentum_descriptor": {"descriptor": "MOMENTUM_BREADTH_MIXED"}},
              "validation": {"coverage": {"current_active_equity_denominator": len(records), "observed_session_cohort": len(records)}, "lineage": {}}}
    return source  # identity computed after p3f9b_snapshot_identity is filled in by the caller


def _p3f9b_snapshot() -> dict:
    records = {}
    for ticker, spec in _SPECS.items():
        closes = spec["close_series"]
        n = len(closes)
        sessions = [f"2026-08-{max(1, 28 - n + i + 1):02d}" for i in range(n)]
        sessions[-1] = SESSION
        records[ticker] = {"observations": [{"session": s, "close": c, "volume": 1000} for s, c in zip(sessions, closes)]}
    payload = {"artifact_type": "p3f9b_mva_exact_session_snapshot", "resolved_completed_session": SESSION, "sessions": [SESSION], "records": records}
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9b_mva_exact_session_snapshot:{digest}"}


def _leadership_source() -> dict:
    ticker_contexts = {ticker: {"market_relative_momentum": {"status": "AVAILABLE", "momentum_bucket": "UPPER_QUARTILE" if ticker == "BRK" else "LOWER_QUARTILE"},
                                "sector_relative_momentum": {"status": "UNAVAILABLE"}, "sector_leadership_context": {"status": "UNAVAILABLE"}} for ticker in _SPECS}
    source = {"schema_version": "1.0.0", "contract_version": "current_market_sector_leadership_context/v1", "session": SESSION,
              "market": {"current_breadth_state": "MIXED_BREADTH"}, "ticker_contexts": ticker_contexts}
    return {**source, **leadership_module.content_identity(source)}


def _build():
    p3f9b = _p3f9b_snapshot()
    descriptive_draft = _descriptive_source()
    descriptive_draft["input_lineage"]["p3f9b_snapshot_identity"] = p3f9b["snapshot_identity"]
    descriptive = {**descriptive_draft, **descriptive_module.content_identity(descriptive_draft)}
    screening = screening_module.build_artifact(descriptive)
    technical_structure = structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")
    tactical_records = {ticker: {"entry_state": spec["entry_state"], "rule_id": "R_FIXTURE"} for ticker, spec in _SPECS.items()}
    tactical_source = {"schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": SESSION,
                       "source_artifacts": {"descriptive": descriptive["artifact_identity"]}, "records": tactical_records}
    tactical = {**tactical_source, **tactical_module.content_identity(tactical_source)}
    leadership = _leadership_source()
    setup_tags = tags_module.build_artifact(technical_structure=technical_structure, current_descriptive=descriptive, current_screening=screening,
                                            current_leadership=leadership, tactical=tactical, requested_at="2026-08-31T00:00:00+00:00")
    boundaries = boundaries_module.build_artifact(tactical=tactical, current_descriptive=descriptive, technical_structure=technical_structure, requested_at="2026-08-31T00:00:00+00:00")
    compact = compact_module.build_artifact(tactical=tactical, technical_structure=technical_structure, tactical_setup_tags=setup_tags,
                                            confirmation_invalidation_boundaries=boundaries, current_leadership=leadership, requested_at="2026-08-31T00:00:00+00:00")
    return compact


class CompactProductTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = _build()
        self.records = self.artifact["records"]

    def test_primary_entry_state_preserved_unchanged(self) -> None:
        self.assertEqual(self.records["BRK"]["primary_entry_state"], "BREAKOUT_READY")
        self.assertEqual(self.records["DWN"]["primary_entry_state"], "DOWNTREND")

    def test_setup_tags_present(self) -> None:
        self.assertIn("BREAKOUT_CONFIRMED_BY_RULE", self.records["BRK"]["setup_tags"])

    def test_confirmation_and_invalidation_boundaries_present(self) -> None:
        self.assertIn("status", self.records["BRK"]["confirmation_boundary"])
        self.assertIn("status", self.records["DWN"]["technical_invalidation_boundary"])

    def test_market_and_sector_context_present(self) -> None:
        self.assertEqual(self.records["BRK"]["market_regime_context"]["current_breadth_state"], "MIXED_BREADTH")
        self.assertEqual(self.records["BRK"]["market_regime_context"]["authority"], "CONTEXT_ONLY_NOT_A_GATE")

    def test_no_full_price_history_embedded(self) -> None:
        self.assertTrue(self.artifact["authority_boundary"]["no_full_price_history_embedded"])
        for record in self.records.values():
            self.assertNotIn("observations", record)
            self.assertNotIn("close_history", record)
            self.assertNotIn("close_series", record)

    def test_zero_silent_drops(self) -> None:
        self.assertEqual(self.artifact["coverage"]["candidate_count"], len(_SPECS))

    def test_ticker_set_mismatch_fails_closed(self) -> None:
        """A tactical artifact naming a ticker absent from technical_structure/setup_tags must raise,
        never silently produce a partial compact record for it."""
        bad_tactical_source = {"schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": SESSION,
                               "source_artifacts": {}, "records": {"EXTRA_TICKER_NOT_IN_OTHER_SOURCES": {"entry_state": "UPTREND_CONFIRMED"}}}
        bad_tactical = {**bad_tactical_source, **tactical_module.content_identity(bad_tactical_source)}
        p3f9b = _p3f9b_snapshot()
        descriptive_draft = _descriptive_source()
        descriptive_draft["input_lineage"]["p3f9b_snapshot_identity"] = p3f9b["snapshot_identity"]
        descriptive = {**descriptive_draft, **descriptive_module.content_identity(descriptive_draft)}
        technical_structure = structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")
        screening = screening_module.build_artifact(descriptive)
        leadership = _leadership_source()
        real_tactical_records = {ticker: {"entry_state": spec["entry_state"]} for ticker, spec in _SPECS.items()}
        real_tactical_source = {"schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": SESSION,
                                "source_artifacts": {}, "records": real_tactical_records}
        real_tactical = {**real_tactical_source, **tactical_module.content_identity(real_tactical_source)}
        setup_tags = tags_module.build_artifact(technical_structure=technical_structure, current_descriptive=descriptive, current_screening=screening,
                                                current_leadership=leadership, tactical=real_tactical, requested_at="2026-08-31T00:00:00+00:00")
        with self.assertRaises(compact_module.TacticalBehaviorContextError):
            compact_module.build_artifact(tactical=bad_tactical, technical_structure=technical_structure, tactical_setup_tags=setup_tags,
                                          confirmation_invalidation_boundaries=None, current_leadership=None, requested_at="2026-08-31T00:00:00+00:00")

    def test_deterministic_identity(self) -> None:
        self.assertEqual(_build()["artifact_sha256"], self.artifact["artifact_sha256"])

    def test_no_score_rank_or_target(self) -> None:
        blob = str(self.artifact)
        for forbidden in ("\"score\":", "\"rank\":", "\"target_price\":"):
            self.assertNotIn(forbidden, blob)


if __name__ == "__main__":
    unittest.main()
