"""Tests for tactical_confirmation_context.py.

Uses direct per-ticker dicts against evaluate_ticker() (the pure synthesis function) plus a
minimal build_artifact() wiring test, rather than full upstream artifact fixtures -- structure,
momentum, and participation each already have their own dedicated fixture-heavy test suites.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tactical_confirmation_context as confirmation


def _structure(*, eligible=True, market_structure_state=None, breakout_state_v3=None, breakout_event=None, base_status=None) -> dict:
    return {
        "eligible": eligible, "market_structure_state": market_structure_state,
        "breakout_state_v3": breakout_state_v3, "breakout_event": breakout_event, "base_status": base_status,
    }


def _momentum(*, rsi_direction=None, rsi_status="AVAILABLE", macd_sign=None, macd_status="AVAILABLE",
              bullish_divergence=None, bearish_divergence=None, divergence_status="AVAILABLE", price_direction="UP") -> dict:
    return {
        "price_direction_1d": price_direction,
        "rsi": {"status": rsi_status, "direction": rsi_direction},
        "macd": {"status": macd_status, "sign": macd_sign},
        "rsi_divergence": {"status": divergence_status, "bullish_divergence_candidate": bullish_divergence, "bearish_divergence_candidate": bearish_divergence},
    }


def _participation(*, ratio=None, status="READY") -> dict:
    return {"acceleration_status": status, "volume_acceleration_ratio": ratio}


class StructureStanceTests(unittest.TestCase):
    def test_not_eligible_is_insufficient_evidence(self) -> None:
        stance, phase = confirmation.structure_stance(_structure(eligible=False))
        self.assertEqual(stance, "INSUFFICIENT_EVIDENCE")

    def test_breakout_is_bullish(self) -> None:
        stance, phase = confirmation.structure_stance(_structure(breakout_state_v3="BREAKOUT"))
        self.assertEqual(stance, "BULLISH")
        self.assertEqual(phase, "BREAKOUT_CONFIRMED")

    def test_breakdown_is_bearish(self) -> None:
        stance, phase = confirmation.structure_stance(_structure(market_structure_state="DOWNTREND"))
        self.assertEqual(stance, "BEARISH")
        self.assertEqual(phase, "BREAKDOWN")

    def test_failed_breakout_is_bearish(self) -> None:
        stance, phase = confirmation.structure_stance(_structure(breakout_state_v3="FAILED_BREAKOUT"))
        self.assertEqual(stance, "BEARISH")
        self.assertEqual(phase, "DISTRIBUTION_RISK")

    def test_early_bullish_reversal(self) -> None:
        stance, phase = confirmation.structure_stance(_structure(market_structure_state="EARLY_BULLISH_REVERSAL"))
        self.assertEqual(stance, "BULLISH")
        self.assertEqual(phase, "EARLY_REVERSAL")

    def test_base_building_is_neutral(self) -> None:
        stance, phase = confirmation.structure_stance(_structure(base_status="IN_BASE"))
        self.assertEqual(stance, "NEUTRAL")
        self.assertEqual(phase, "BASE_BUILDING")

    def test_insufficient_history_is_insufficient_evidence(self) -> None:
        stance, phase = confirmation.structure_stance(_structure(market_structure_state="INSUFFICIENT_HISTORY"))
        self.assertEqual(stance, "INSUFFICIENT_EVIDENCE")


class WorkedExampleTests(unittest.TestCase):
    """Directly mirrors the task's own worked examples."""

    def test_breakout_with_rising_momentum_and_expanding_participation_is_confirmed(self) -> None:
        result = confirmation.evaluate_ticker(
            structure_record=_structure(breakout_state_v3="BREAKOUT"),
            momentum_record=_momentum(rsi_direction="RISING", macd_sign="POSITIVE", price_direction="UP"),
            participation_record=_participation(ratio=1.8),
        )
        self.assertEqual(result["structure_stance"], "BULLISH")
        self.assertEqual(result["tactical_confirmation_state"], "CONFIRMED")
        self.assertIn("MOMENTUM_DIRECTION_ALIGNED", result["supporting_reasons"])
        self.assertIn("PRICE_VOLUME_CONFIRMATION", result["supporting_reasons"])
        self.assertEqual(result["contradicting_reasons"], [])

    def test_breakout_with_weak_volume_and_weakening_momentum_is_contradicted(self) -> None:
        result = confirmation.evaluate_ticker(
            structure_record=_structure(breakout_state_v3="BREAKOUT"),
            momentum_record=_momentum(rsi_direction="FALLING", macd_sign="NEGATIVE", price_direction="UP"),
            participation_record=_participation(ratio=0.5),
        )
        self.assertEqual(result["tactical_confirmation_state"], "CONTRADICTED")
        self.assertIn("MOMENTUM_DIRECTION_MISALIGNED", result["contradicting_reasons"])
        self.assertIn("PRICE_VOLUME_CONTRADICTION", result["contradicting_reasons"])
        self.assertEqual(result["supporting_reasons"], [])

    def test_early_bullish_reversal_with_bullish_divergence_and_improving_participation_is_confirmed(self) -> None:
        result = confirmation.evaluate_ticker(
            structure_record=_structure(market_structure_state="EARLY_BULLISH_REVERSAL"),
            momentum_record=_momentum(rsi_direction="RISING", bullish_divergence={"kind": "BULLISH_DIVERGENCE_CANDIDATE"}, price_direction="UP"),
            participation_record=_participation(ratio=1.5),
        )
        self.assertEqual(result["tactical_confirmation_state"], "CONFIRMED")
        self.assertIn("BULLISH_RSI_DIVERGENCE_CANDIDATE", result["supporting_reasons"])
        self.assertIn("MOMENTUM_DIRECTION_ALIGNED", result["supporting_reasons"])

    def test_base_building_with_volume_contraction_and_stable_momentum_is_neutral_not_alarming(self) -> None:
        """BASE_BUILDING has no directional thesis; volume contraction during a base is a
        constructive-retreat read, not a contradiction -- the overall state must stay NEUTRAL,
        never CONTRADICTED, since a NEUTRAL stance never accumulates contradicting reasons."""
        result = confirmation.evaluate_ticker(
            structure_record=_structure(base_status="IN_BASE"),
            momentum_record=_momentum(rsi_direction="FLAT", macd_sign="ZERO", price_direction="DOWN"),
            participation_record=_participation(ratio=0.5),
        )
        self.assertEqual(result["structure_stance"], "NEUTRAL")
        self.assertEqual(result["tactical_confirmation_state"], "NEUTRAL")
        self.assertEqual(result["contradicting_reasons"], [])


class NoVoteCountingTests(unittest.TestCase):
    def test_rsi_and_macd_agreement_is_one_reason_not_two(self) -> None:
        """RSI rising AND MACD positive must fold into exactly one MOMENTUM_DIRECTION_ALIGNED
        reason, never two separate reasons for what is fundamentally one price-momentum read."""
        result = confirmation.evaluate_ticker(
            structure_record=_structure(breakout_state_v3="BREAKOUT"),
            momentum_record=_momentum(rsi_direction="RISING", macd_sign="POSITIVE", price_direction="UP"),
            participation_record=_participation(status="UNAVAILABLE"),
        )
        self.assertEqual(result["supporting_reasons"].count("MOMENTUM_DIRECTION_ALIGNED"), 1)
        self.assertNotIn("RSI_MOMENTUM_RISING", result["supporting_reasons"])
        self.assertNotIn("MACD_BULLISH", result["supporting_reasons"])

    def test_rsi_and_macd_disagreement_is_mixed_not_a_contradiction(self) -> None:
        result = confirmation.evaluate_ticker(
            structure_record=_structure(breakout_state_v3="BREAKOUT"),
            momentum_record=_momentum(rsi_direction="RISING", macd_sign="NEGATIVE", price_direction="UP"),
            participation_record=_participation(status="UNAVAILABLE"),
        )
        self.assertEqual(result["momentum_direction"], "MIXED")
        self.assertNotIn("MOMENTUM_DIRECTION_ALIGNED", result["supporting_reasons"])
        self.assertNotIn("MOMENTUM_DIRECTION_MISALIGNED", result["contradicting_reasons"])


class InsufficientEvidenceTests(unittest.TestCase):
    def test_insufficient_structure_short_circuits_to_insufficient_evidence(self) -> None:
        result = confirmation.evaluate_ticker(
            structure_record=_structure(eligible=False),
            momentum_record=_momentum(rsi_direction="RISING", macd_sign="POSITIVE"),
            participation_record=_participation(ratio=2.0),
        )
        self.assertEqual(result["tactical_confirmation_state"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["supporting_reasons"], [])
        self.assertEqual(result["contradicting_reasons"], [])

    def test_missing_momentum_and_participation_with_directional_structure_is_neutral(self) -> None:
        result = confirmation.evaluate_ticker(
            structure_record=_structure(breakout_state_v3="BREAKOUT"), momentum_record=None, participation_record=None,
        )
        self.assertEqual(result["structure_stance"], "BULLISH")
        self.assertEqual(result["tactical_confirmation_state"], "NEUTRAL")
        self.assertEqual(result["supporting_reasons"], [])
        self.assertEqual(result["contradicting_reasons"], [])


class ParticipationStateTests(unittest.TestCase):
    def test_expanding_contracting_neutral_thresholds(self) -> None:
        self.assertEqual(confirmation.participation_state(_participation(ratio=1.3)), "PARTICIPATION_EXPANDING")
        self.assertEqual(confirmation.participation_state(_participation(ratio=0.7)), "PARTICIPATION_CONTRACTING")
        self.assertEqual(confirmation.participation_state(_participation(ratio=1.0)), "PARTICIPATION_NEUTRAL")
        self.assertEqual(confirmation.participation_state(_participation(status="UNAVAILABLE")), "INSUFFICIENT_EVIDENCE")

    def test_price_volume_state_is_direction_agnostic(self) -> None:
        self.assertEqual(confirmation.price_volume_state("UP", "PARTICIPATION_EXPANDING"), "PRICE_VOLUME_CONFIRMATION")
        self.assertEqual(confirmation.price_volume_state("DOWN", "PARTICIPATION_EXPANDING"), "PRICE_VOLUME_CONFIRMATION")
        self.assertEqual(confirmation.price_volume_state("UP", "PARTICIPATION_CONTRACTING"), "PRICE_VOLUME_CONTRADICTION")
        self.assertEqual(confirmation.price_volume_state("DOWN", "PARTICIPATION_CONTRACTING"), "PRICE_VOLUME_CONTRADICTION")
        self.assertEqual(confirmation.price_volume_state(None, "PARTICIPATION_EXPANDING"), "INSUFFICIENT_EVIDENCE")


class BuildArtifactTests(unittest.TestCase):
    def test_zero_silent_drops_and_deterministic_identity(self) -> None:
        structure_projection = {
            "session": "2026-08-28",
            "records": {
                "AAA": {"eligible": True, "breakout_state_v3": "BREAKOUT"},
                "BBB": {"eligible": False},
            },
        }
        momentum = {"target_session": "2026-08-28", "records": {"AAA": _momentum(rsi_direction="RISING", macd_sign="POSITIVE")}}
        participation = {"records": {"AAA": _participation(ratio=1.5)}}
        artifact1 = confirmation.build_artifact(structure_projection=structure_projection, momentum=momentum, participation=participation, requested_at="t1")
        artifact2 = confirmation.build_artifact(structure_projection=structure_projection, momentum=momentum, participation=participation, requested_at="t2")
        self.assertEqual(len(artifact1["records"]), 2)
        self.assertEqual(artifact1["records"]["BBB"]["tactical_confirmation_state"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(artifact1["artifact_sha256"], artifact2["artifact_sha256"])

    def test_session_mismatch_fails_closed(self) -> None:
        structure_projection = {"session": "2026-08-28", "records": {}}
        momentum = {"target_session": "2026-08-27", "records": {}}
        with self.assertRaises(confirmation.TacticalConfirmationContextError):
            confirmation.build_artifact(structure_projection=structure_projection, momentum=momentum, participation={"records": {}}, requested_at="t1")


if __name__ == "__main__":
    unittest.main()
