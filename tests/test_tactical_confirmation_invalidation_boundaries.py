"""Tests for tactical_confirmation_invalidation_boundaries.py.

Hand-builds a minimal tactical (watchlist_tactical_entry_classifier) artifact -- one ticker per
entry_state -- and a matching current_descriptive artifact. Runs once without a technical_structure
input (MA20/momentum-only fallback) and once with one (structure-level boundaries).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import market_wide_current_descriptive_research as descriptive_module
import tactical_confirmation_invalidation_boundaries as boundaries_module
import technical_structure_context as structure
import watchlist_tactical_entry_classifier as tactical_module
from field_temporal_contract import stable_id

SESSION = "2026-08-28"
_STATES = ("BREAKOUT_READY", "UPTREND_CONFIRMED", "EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING",
           "SELLING_PRESSURE_EASING", "SIDEWAYS_NEUTRAL", "DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND")


def _descriptive_source(tactical_ticker_keys: list[str]) -> dict:
    records = {}
    for ticker in tactical_ticker_keys:
        records[ticker] = {
            "ticker": ticker, "in_current_descriptive_scope": True, "activity_and_session_state": "ACTIVE_LISTED_OBSERVED",
            "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": SESSION,
                                    "values": {"close": 100.0, "ma_20": 100.0, "momentum_20d": 0.0, "return_1d": 0.0}},
            "trend_state": "ABOVE_MA20", "liquidity": {"status": "ELIGIBLE"}, "sector_classification": {},
        }
    source = {"schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": SESSION, "records": records}
    return {**source, **descriptive_module.content_identity(source)}


def _p3f9b_snapshot(tickers: list[str]) -> dict:
    flat19 = [95.0, 100.0, 105.0, 98.0, 102.0] * 3 + [100.0, 101.0, 99.0, 100.0]
    closes = flat19 + [100.0]
    records = {}
    for ticker in tickers:
        n = len(closes)
        sessions = [f"2026-08-{max(1, 28 - n + i + 1):02d}" for i in range(n)]
        sessions[-1] = SESSION
        records[ticker] = {"observations": [{"session": s, "close": c, "volume": 1000} for s, c in zip(sessions, closes)]}
    payload = {"artifact_type": "p3f9b_mva_exact_session_snapshot", "resolved_completed_session": SESSION, "sessions": [SESSION], "records": records}
    digest = stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9b_mva_exact_session_snapshot:{digest}"}


def _build(with_structure: bool):
    tactical_records = {f"T_{state}": {"entry_state": state, "rule_id": f"R_{state}"} for state in _STATES}
    tactical_records["NO_STATE"] = {"entry_state": None, "rule_id": "R0_TECHNICAL_FEATURES_UNAVAILABLE"}
    ticker_keys = list(tactical_records)
    descriptive = _descriptive_source(ticker_keys)
    tactical_source = {"schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": SESSION,
                       "source_artifacts": {"descriptive": descriptive["artifact_identity"]}, "records": tactical_records}
    tactical = {**tactical_source, **tactical_module.content_identity(tactical_source)}
    technical_structure = None
    if with_structure:
        p3f9b = _p3f9b_snapshot(ticker_keys)
        technical_structure = structure.build_artifact(current_descriptive=descriptive, p3f9b_snapshot=p3f9b, requested_at="2026-08-31T00:00:00+00:00")
    artifact = boundaries_module.build_artifact(tactical=tactical, current_descriptive=descriptive, technical_structure=technical_structure, requested_at="2026-08-31T00:00:00+00:00")
    return artifact


class BoundaryTests(unittest.TestCase):
    def test_zero_silent_drops_all_ten_records(self) -> None:
        artifact = _build(with_structure=False)
        self.assertEqual(artifact["denominator"], len(_STATES) + 1)
        self.assertEqual(len(artifact["records"]), len(_STATES) + 1)

    def test_breakout_ready_confirmation_ready_with_structure(self) -> None:
        artifact = _build(with_structure=True)
        record = artifact["records"]["T_BREAKOUT_READY"]
        self.assertEqual(record["confirmation_boundary"]["status"], "READY")
        self.assertEqual(record["confirmation_boundary"]["source_metric"], "resistance")
        self.assertTrue(record["structure_level_used"])

    def test_breakout_ready_falls_back_to_ma20_without_structure(self) -> None:
        artifact = _build(with_structure=False)
        record = artifact["records"]["T_BREAKOUT_READY"]
        self.assertIn(record["confirmation_boundary"]["status"], ("READY", "CONDITIONAL"))
        self.assertFalse(record["structure_level_used"])

    def test_base_building_is_honestly_conditional_confirmation(self) -> None:
        record = _build(with_structure=False)["records"]["T_BASE_BUILDING"]
        self.assertEqual(record["confirmation_boundary"]["status"], "CONDITIONAL")
        self.assertIn("DISJUNCTIVE_CONFIRMATION_NOT_A_SINGLE_FIXED_BOUNDARY", record["confirmation_boundary"]["warnings"])

    def test_sideways_neutral_has_no_invalidation_thesis(self) -> None:
        record = _build(with_structure=False)["records"]["T_SIDEWAYS_NEUTRAL"]
        self.assertEqual(record["technical_invalidation_boundary"]["status"], "UNAVAILABLE")

    def test_downtrend_has_no_confirmation_thesis(self) -> None:
        record = _build(with_structure=False)["records"]["T_DOWNTREND"]
        self.assertEqual(record["confirmation_boundary"]["status"], "UNAVAILABLE")
        self.assertEqual(record["technical_invalidation_boundary"]["status"], "READY")

    def test_missing_entry_state_localized_unavailable(self) -> None:
        record = _build(with_structure=False)["records"]["NO_STATE"]
        self.assertEqual(record["confirmation_boundary"]["status"], "UNAVAILABLE")
        self.assertEqual(record["technical_invalidation_boundary"]["status"], "UNAVAILABLE")

    def test_no_fixed_stop_percentage_anywhere(self) -> None:
        """No boundary ever carries a computed stop-distance value; every boundary's own
        no_fixed_stop_percentage marker (a compliant field this module DOES emit) stays True."""
        for record in _build(with_structure=False)["records"].values():
            self.assertTrue(record["authority_boundary"]["no_fixed_stop_percentage"])
            for boundary in (record["confirmation_boundary"], record["technical_invalidation_boundary"]):
                self.assertNotEqual(boundary.get("unit"), "PERCENTAGE_BELOW_ENTRY")
                self.assertNotIn("stop_distance", boundary)

    def test_research_boundary_authority_markers_present(self) -> None:
        for record in _build(with_structure=False)["records"].values():
            self.assertTrue(record["authority_boundary"]["research_boundary_only"])
            self.assertTrue(record["authority_boundary"]["not_an_executable_order"])
            self.assertFalse(record["authority_boundary"]["decision_authority_promoted"])

    def test_not_bounded_to_frozen_thirteen_issuer_snapshot(self) -> None:
        """Structural regression guard: this module must accept an arbitrary-size cohort, not the
        frozen 13-issuer action_instrumentation.py execute() snapshot."""
        artifact = _build(with_structure=False)
        self.assertNotEqual(artifact["denominator"], 13)
        self.assertTrue(artifact["authority_boundary"]["market_wide_not_bounded_snapshot_cohort"])

    def test_deterministic_identity(self) -> None:
        self.assertEqual(_build(with_structure=True)["artifact_sha256"], _build(with_structure=True)["artifact_sha256"])

    # -----------------------------------------------------------------------
    # Decision-quality corrective pass: displayed boundary text must name only the metric
    # actually instrumented (value/operator/source_metric), never a broader disjunctive sentence
    # pulled from the classifier's own multi-signal narrative.
    # -----------------------------------------------------------------------

    def test_breakout_ready_invalidation_text_names_resistance_not_momentum_when_level_available(self) -> None:
        record = _build(with_structure=True)["records"]["T_BREAKOUT_READY"]
        invalidation = record["technical_invalidation_boundary"]
        self.assertEqual(invalidation["source_metric"], "resistance")
        self.assertIn("resistance", invalidation["reason"])
        self.assertNotIn("momentum", invalidation["reason"])

    def test_breakout_ready_invalidation_text_names_ma20_only_when_level_unavailable(self) -> None:
        record = _build(with_structure=False)["records"]["T_BREAKOUT_READY"]
        invalidation = record["technical_invalidation_boundary"]
        self.assertIn("moving average", invalidation["reason"])
        self.assertNotIn("momentum", invalidation["reason"])
        self.assertNotIn("resistance", invalidation["reason"])

    def test_base_building_invalidation_text_names_support_only_when_level_available(self) -> None:
        record = _build(with_structure=True)["records"]["T_BASE_BUILDING"]
        invalidation = record["technical_invalidation_boundary"]
        if invalidation["status"] != "READY" or invalidation.get("source_metric") != "support":
            self.skipTest("no qualified support level for this ticker/session in the fixture")
        self.assertIn("support", invalidation["reason"])
        self.assertNotIn("momentum", invalidation["reason"])
        self.assertNotIn("relative-volume", invalidation["reason"])

    def test_base_building_invalidation_text_names_ma20_only_when_level_unavailable(self) -> None:
        record = _build(with_structure=False)["records"]["T_BASE_BUILDING"]
        invalidation = record["technical_invalidation_boundary"]
        self.assertIn("moving average", invalidation["reason"])
        self.assertNotIn("momentum", invalidation["reason"])
        self.assertNotIn("relative-volume", invalidation["reason"])

    def test_selling_pressure_easing_confirmation_text_names_ma20_reclaim_only(self) -> None:
        record = _build(with_structure=False)["records"]["T_SELLING_PRESSURE_EASING"]
        confirmation = record["confirmation_boundary"]
        self.assertIn("moving average", confirmation["reason"])
        self.assertNotIn("momentum", confirmation["reason"])

    def test_requested_at_excluded_from_identity(self) -> None:
        tactical_records = {"T_BREAKOUT_READY": {"entry_state": "BREAKOUT_READY", "rule_id": "R2"}}
        descriptive = _descriptive_source(list(tactical_records))
        tactical_source = {"schema_version": "1.0.0", "contract_version": "watchlist_tactical_entry_classifier/v1", "session": SESSION,
                           "source_artifacts": {"descriptive": descriptive["artifact_identity"]}, "records": tactical_records}
        tactical = {**tactical_source, **tactical_module.content_identity(tactical_source)}
        a = boundaries_module.build_artifact(tactical=tactical, current_descriptive=descriptive, technical_structure=None, requested_at="2026-08-31T00:00:00+00:00")
        b = boundaries_module.build_artifact(tactical=tactical, current_descriptive=descriptive, technical_structure=None, requested_at="2099-01-01T00:00:00+00:00")
        self.assertEqual(a["artifact_sha256"], b["artifact_sha256"])


if __name__ == "__main__":
    unittest.main()
