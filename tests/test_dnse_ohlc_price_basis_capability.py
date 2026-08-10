from __future__ import annotations

import json
import unittest

from dnse_ohlc_price_basis_capability import (
    ADJUSTED_CONFIRMED,
    ADJUSTED_PATTERN,
    CONDITIONALLY_ADJUSTED,
    EVIDENCE_EVENTS,
    INCONCLUSIVE,
    INCONCLUSIVE_PATTERN,
    PRICE_BASIS_VERDICTS,
    QUALIFIED_ACTION_TYPES,
    RAW_CONFIRMED,
    RAW_PATTERN,
    DnseOhlcPriceBasisError,
    action_type_qualified,
    active_capability_contract,
    assert_consistent_ratios,
    assert_fail_closed,
    assert_ratio_semantics_unambiguous,
    classify_cross_reference_ratio,
    classify_internal_transition,
    combine_event_verdicts,
    field_ratios,
    serialize,
)

# Shape-matched to the real retained corporate_event_records rows
# (vn_stock.db, provider VCI) -- see EVIDENCE_EVENTS for the exact retained values.
HPG_EVENT = {"ticker": "HPG", "exercise_ratio": 0.1}
VCB_EVENT = {"ticker": "VCB", "value_per_share_vnd": 450.0}


class RatioSemanticsGateTests(unittest.TestCase):
    """Step 3 / Step 11 item 1-2: qualified ratio accepted, ambiguous ratio rejected."""

    def test_share_count_event_with_exercise_ratio_accepted(self):
        assert_ratio_semantics_unambiguous(HPG_EVENT)  # must not raise

    def test_cash_event_with_value_per_share_accepted(self):
        assert_ratio_semantics_unambiguous(VCB_EVENT)  # must not raise

    def test_event_with_neither_field_rejected(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            assert_ratio_semantics_unambiguous({"ticker": "XYZ"})

    def test_event_with_zero_ratio_rejected_not_inferred(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            assert_ratio_semantics_unambiguous({"ticker": "XYZ", "exercise_ratio": 0})

    def test_event_with_negative_cash_amount_rejected(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            assert_ratio_semantics_unambiguous({"ticker": "XYZ", "value_per_share_vnd": -100})

    def test_event_with_non_numeric_ratio_rejected(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            assert_ratio_semantics_unambiguous({"ticker": "XYZ", "exercise_ratio": "10%"})


class PatternClassificationTests(unittest.TestCase):
    """Step 11 items 3-4: raw-series and adjusted-series pattern classification."""

    def test_cross_reference_raw_pattern(self):
        # DNSE matches the archived/original reference almost exactly -> raw.
        pattern = classify_cross_reference_ratio(0.9995, adjusted_expected=0.90)
        self.assertEqual(RAW_PATTERN, pattern)

    def test_cross_reference_adjusted_pattern(self):
        # DNSE matches the known adjustment factor, not the original -> adjusted.
        pattern = classify_cross_reference_ratio(0.9917, adjusted_expected=0.9917, tolerance=0.001, min_separation=0.005)
        self.assertEqual(ADJUSTED_PATTERN, pattern)

    def test_internal_transition_raw_pattern(self):
        # A real ~9.09% step down at the ex-date, matching the theoretical
        # raw drop for a 10% stock dividend.
        pattern = classify_internal_transition(23950, 23950 / 1.1, theoretical_ratio=1.1)
        self.assertEqual(RAW_PATTERN, pattern)

    def test_internal_transition_adjusted_pattern(self):
        # The real HPG evidence: no structural jump at the ex-date.
        pattern = classify_internal_transition(23950, 24250, theoretical_ratio=1.1)
        self.assertEqual(ADJUSTED_PATTERN, pattern)

    def test_internal_transition_neither_pattern_is_inconclusive(self):
        # A move that matches neither the raw drop nor "no discontinuity".
        pattern = classify_internal_transition(23950, 20000, theoretical_ratio=1.1)
        self.assertEqual(INCONCLUSIVE_PATTERN, pattern)


class InconsistentTransformationTests(unittest.TestCase):
    """Step 6.C / Step 11 item 5: inconsistent OHLC transformation rejected."""

    def test_uniform_ratio_across_fields_accepted(self):
        observed = {"o": 60.0, "h": 60.0, "l": 58.31, "c": 58.41}
        reference = {"o": 60.5, "h": 60.5, "l": 58.8, "c": 58.9}
        ratios = field_ratios(observed, reference)
        assert_consistent_ratios(ratios)  # must not raise

    def test_divergent_ratio_across_fields_rejected(self):
        # Close moves by ~0.99, but open barely moves at all -- not a clean
        # single-factor adjustment signature.
        observed = {"o": 60.45, "h": 60.0, "l": 58.31, "c": 58.41}
        reference = {"o": 60.5, "h": 60.5, "l": 58.8, "c": 58.9}
        ratios = field_ratios(observed, reference)
        with self.assertRaises(DnseOhlcPriceBasisError):
            assert_consistent_ratios(ratios)

    def test_field_ratios_fails_closed_on_missing_field(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            field_ratios({"o": 1, "h": 1, "l": 1}, {"o": 1, "h": 1, "l": 1, "c": 1})

    def test_field_ratios_fails_closed_on_non_positive_reference(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            field_ratios({"o": 1, "h": 1, "l": 1, "c": 1}, {"o": 0, "h": 1, "l": 1, "c": 1})


class CombineEventVerdictsTests(unittest.TestCase):
    """Step 7 / Step 11 items 6-7: insufficient evidence stays inconclusive;
    multiple agreeing events reach a deterministic formal verdict."""

    def test_no_events_is_inconclusive(self):
        self.assertEqual(INCONCLUSIVE, combine_event_verdicts([]))

    def test_single_event_without_override_is_inconclusive(self):
        self.assertEqual(INCONCLUSIVE, combine_event_verdicts([ADJUSTED_PATTERN]))

    def test_single_event_with_explicit_override_reaches_a_verdict(self):
        self.assertEqual(
            ADJUSTED_CONFIRMED,
            combine_event_verdicts([ADJUSTED_PATTERN], single_event_sufficient=True),
        )

    def test_any_inconclusive_pattern_makes_the_whole_result_inconclusive(self):
        self.assertEqual(
            INCONCLUSIVE, combine_event_verdicts([ADJUSTED_PATTERN, INCONCLUSIVE_PATTERN])
        )

    def test_two_agreeing_adjusted_events_reach_adjusted_confirmed(self):
        self.assertEqual(
            ADJUSTED_CONFIRMED, combine_event_verdicts([ADJUSTED_PATTERN, ADJUSTED_PATTERN])
        )

    def test_two_agreeing_raw_events_reach_raw_confirmed(self):
        self.assertEqual(RAW_CONFIRMED, combine_event_verdicts([RAW_PATTERN, RAW_PATTERN]))

    def test_disagreeing_events_fail_closed_to_conditionally_adjusted(self):
        self.assertEqual(
            CONDITIONALLY_ADJUSTED, combine_event_verdicts([RAW_PATTERN, ADJUSTED_PATTERN])
        )

    def test_result_is_deterministic_across_repeated_calls(self):
        first = combine_event_verdicts([ADJUSTED_PATTERN, ADJUSTED_PATTERN])
        second = combine_event_verdicts([ADJUSTED_PATTERN, ADJUSTED_PATTERN])
        self.assertEqual(first, second)

    def test_invalid_pattern_input_rejected(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            combine_event_verdicts(["not_a_real_pattern"])


class ActionTypeGeneralizationTests(unittest.TestCase):
    """Step 11 item 8: unsupported action type does not get generalized."""

    def test_tested_action_types_are_qualified(self):
        self.assertTrue(action_type_qualified("stock_dividend_bonus_issue"))
        self.assertTrue(action_type_qualified("cash_dividend"))

    def test_untested_action_types_are_not_qualified(self):
        for untested in ("stock_split", "reverse_split", "rights_issue", "spin_off"):
            self.assertFalse(action_type_qualified(untested),
                             f"{untested} must not be silently generalized from a tested type")

    def test_qualified_action_types_constant_matches_what_was_actually_tested(self):
        tested_types = {event["event_type"] for event in EVIDENCE_EVENTS}
        self.assertEqual(tested_types, set(QUALIFIED_ACTION_TYPES))


class CurrentVsPointInTimeSeparationTests(unittest.TestCase):
    """Step 8 / Step 11 item 9: current-analysis safety and PIT-backtest safety
    are separate properties, never conflated."""

    def test_current_and_pit_safety_are_independent_and_not_equal(self):
        contract = active_capability_contract()
        self.assertIn("current_analysis_price_basis_safe", contract)
        self.assertIn("backtest_point_in_time_safe", contract)
        self.assertNotEqual(
            contract["current_analysis_price_basis_safe"],
            contract["backtest_point_in_time_safe"],
        )

    def test_current_analysis_is_safe_despite_pit_being_unsafe(self):
        contract = active_capability_contract()
        self.assertIs(True, contract["current_analysis_price_basis_safe"])
        self.assertIs(False, contract["backtest_point_in_time_safe"])

    def test_retrospective_adjustment_proven_is_what_makes_pit_unsafe(self):
        contract = active_capability_contract()
        self.assertIs(True, contract["retrospective_adjustment"])
        self.assertIs(False, contract["backtest_point_in_time_safe"])


class ProvenanceTests(unittest.TestCase):
    """Step 11 item 10: provenance retained."""

    def test_every_evidence_event_carries_qualified_source_and_record_id(self):
        for event in EVIDENCE_EVENTS:
            self.assertIn("qualified_source", event)
            self.assertIn("record_id", event)
            self.assertTrue(event["record_id"])
            self.assertIn("exright_date", event)

    def test_contract_carries_the_evidence_file_pointer(self):
        contract = active_capability_contract()
        self.assertIn("evidence", contract)
        self.assertIn("dnse-ohlc-price-basis-qualification-20260810", contract["evidence"])

    def test_evidence_events_survive_into_the_contract_unmodified(self):
        contract = active_capability_contract()
        self.assertEqual(len(EVIDENCE_EVENTS), len(contract["evidence_events"]))
        for original, carried in zip(EVIDENCE_EVENTS, contract["evidence_events"]):
            self.assertEqual(original["record_id"], carried["record_id"])
            self.assertEqual(original["ticker"], carried["ticker"])


class NoSecretsTests(unittest.TestCase):
    """Step 11 item 11: no secret/auth fields serialized."""

    def test_no_secret_or_credential_like_value_in_serialized_contract(self):
        dumped = serialize(active_capability_contract()).lower()
        for forbidden in ("token", "secret", "signature", "authorization", "x-api-key",
                          "cookie", "api_key", "api_secret", "bearer"):
            self.assertNotIn(forbidden, dumped)


class DeterministicSerializationTests(unittest.TestCase):
    """Step 11 item 12: deterministic evidence serialization."""

    def test_serialize_is_byte_identical_across_repeated_calls(self):
        first = serialize(active_capability_contract())
        second = serialize(active_capability_contract())
        self.assertEqual(first, second)

    def test_serialize_output_is_valid_json(self):
        json.loads(serialize(active_capability_contract()))  # must not raise


class OrdinaryNoEventDataCannotQualifyTests(unittest.TestCase):
    """Step 11 item 13: ordinary no-event matching data cannot qualify a basis."""

    def test_identical_raw_and_adjusted_expectation_refuses_to_discriminate(self):
        # An ordinary session where a raw and an adjusted series would look
        # identical (no real event) -- must never be read as proof of either.
        pattern = classify_cross_reference_ratio(1.0, adjusted_expected=1.0)
        self.assertEqual(INCONCLUSIVE_PATTERN, pattern)

    def test_near_identical_expectations_below_min_separation_refuse_to_discriminate(self):
        pattern = classify_cross_reference_ratio(0.995, adjusted_expected=0.999, min_separation=0.02)
        self.assertEqual(INCONCLUSIVE_PATTERN, pattern)

    def test_tiny_theoretical_ratio_effect_refuses_to_discriminate(self):
        # A "corporate action" with a negligible theoretical price effect
        # cannot be distinguished from ordinary daily noise.
        pattern = classify_internal_transition(50000, 50010, theoretical_ratio=1.0001)
        self.assertEqual(INCONCLUSIVE_PATTERN, pattern)

    def test_a_perfectly_matching_ratio_alone_cannot_force_a_verdict_without_separation(self):
        """Reproduces exactly the trap this milestone's own evidence hit: a
        real observed ratio (0.991746) that happens to fall within the
        default tolerance of BOTH raw_expected and adjusted_expected must
        not silently resolve to either -- it must refuse until the caller
        supplies parameters actually justified by measurement precision."""
        pattern = classify_cross_reference_ratio(0.991746, adjusted_expected=0.9917)
        self.assertEqual(INCONCLUSIVE_PATTERN, pattern)


class FormalVerdictVocabularyTests(unittest.TestCase):
    def test_assert_fail_closed_accepts_every_declared_verdict(self):
        for verdict in PRICE_BASIS_VERDICTS:
            assert_fail_closed(verdict)  # must not raise

    def test_assert_fail_closed_rejects_unknown_verdict(self):
        with self.assertRaises(DnseOhlcPriceBasisError):
            assert_fail_closed("PARTIALLY_RAW_MAYBE")

    def test_active_verdict_is_in_the_declared_vocabulary(self):
        contract = active_capability_contract()
        self.assertIn(contract["price_basis"], PRICE_BASIS_VERDICTS)


class ActiveContractReproducesRealEvidenceTests(unittest.TestCase):
    """End-to-end: the module's own generic classification primitives, fed
    the real retained evidence numbers, reproduce the frozen active verdict
    -- the contract is not hand-picked independently of the logic."""

    def test_hpg_and_vcb_evidence_reproduce_the_active_verdict(self):
        hpg_pattern = classify_internal_transition(23950, 24250, theoretical_ratio=1.1)
        vcb_pattern = classify_cross_reference_ratio(
            0.991746, adjusted_expected=0.9917, tolerance=0.001, min_separation=0.005,
        )
        reproduced = combine_event_verdicts([hpg_pattern, vcb_pattern])
        self.assertEqual(ADJUSTED_CONFIRMED, reproduced)
        self.assertEqual(reproduced, active_capability_contract()["price_basis"])


if __name__ == "__main__":
    unittest.main()
