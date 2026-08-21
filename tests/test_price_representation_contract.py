from __future__ import annotations

import ast
import inspect
import unittest
from decimal import Decimal

import price_representation_contract as contract


class ProviderNativePreservedTests(unittest.TestCase):
    def test_provider_native_value_and_unit_are_preserved(self):
        result = contract.to_canonical(
            "21.15", source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="close",
        )
        self.assertEqual("21.15", result["provider_native_value"])
        self.assertEqual("thousands_of_vnd_per_share", result["provider_native_unit"])

    def test_canonical_value_is_deterministically_derived(self):
        result = contract.to_canonical(
            "21.15", source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="close",
        )
        self.assertEqual(Decimal("21150.00"), Decimal(result["canonical_value"]))
        self.assertEqual("vnd_per_share", result["canonical_unit"])

    def test_accepts_numeric_and_string_input_identically(self):
        from_float = contract.to_canonical(
            21.15, source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="close",
        )
        from_string = contract.to_canonical(
            "21.15", source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="close",
        )
        self.assertEqual(from_float["canonical_value"], from_string["canonical_value"])


class UniformOhlcTests(unittest.TestCase):
    def test_all_four_fields_use_the_same_resolved_contract(self):
        result = contract.to_canonical_ohlc(
            open_=22.05, high=22.30, low=21.90, close=22.15,
            source="DNSE", capability_id="ohlc_1D", instrument_class="VN_LISTED_EQUITY",
        )
        contract_ids = {result["fields"][f]["contract_id"] for f in ("open", "high", "low", "close")}
        self.assertEqual(1, len(contract_ids))
        self.assertTrue(result["uniform_transformation"])

    def test_each_field_scaled_by_the_same_factor(self):
        result = contract.to_canonical_ohlc(
            open_=22.05, high=22.30, low=21.90, close=22.15,
            source="DNSE", capability_id="ohlc_1D", instrument_class="VN_LISTED_EQUITY",
        )
        expected = {"open": "22050", "high": "22300", "low": "21900", "close": "22150"}
        for field, expected_prefix in expected.items():
            canonical = Decimal(result["fields"][field]["canonical_value"])
            self.assertEqual(Decimal(expected_prefix), canonical)

    def test_close_only_scaling_defect_is_structurally_impossible(self):
        # The historical P3F9B defect scaled close but left open/high/low provider-native.
        # Prove the four fields can never diverge in whether they were scaled.
        result = contract.to_canonical_ohlc(
            open_=10, high=10, low=10, close=10,
            source="DNSE", capability_id="ohlc_1D", instrument_class="VN_LISTED_EQUITY",
        )
        canonical_values = {Decimal(result["fields"][f]["canonical_value"]) for f in ("open", "high", "low", "close")}
        self.assertEqual({Decimal("10000")}, canonical_values)


class NoMagnitudeHeuristicTests(unittest.TestCase):
    """Statically prove the transform is a table lookup, never a numeric-threshold branch."""

    def test_source_contains_no_magnitude_comparison_on_the_input_value(self):
        source = inspect.getsource(contract)
        forbidden_patterns = ("< 1000", "<1000", "> 1000", ">1000", "if price", "if value <", "if native <")
        for pattern in forbidden_patterns:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, source)

    def test_to_canonical_signature_has_no_magnitude_threshold_parameter(self):
        signature = inspect.signature(contract.to_canonical)
        self.assertNotIn("threshold", signature.parameters)


class IndependenceFromAdjustmentBasisTests(unittest.TestCase):
    """PRICE UNIT NORMALIZATION != RAW_AS_TRADED QUALIFICATION (owner Section 4)."""

    def test_module_does_not_import_price_basis_or_adjustment_modules(self):
        # Parses actual `import`/`from ... import` nodes rather than searching raw text --
        # the module's own docstring legitimately *names* these modules as things it is
        # independent of, which a substring search would misreport as a forbidden import.
        tree = ast.parse(inspect.getsource(contract))
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
        forbidden_imports = (
            "provider_price_basis_registry", "corporate_action_factors",
            "price_basis_contract", "price_basis_events",
        )
        for name in forbidden_imports:
            with self.subTest(module=name):
                self.assertNotIn(name, imported_names)

    def test_result_never_claims_raw_as_traded_or_pit_eligibility(self):
        result = contract.to_canonical(
            "21.15", source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="close",
        )
        self.assertNotIn("raw_as_traded", result)
        self.assertNotIn("pit_backtest_eligible", result)
        self.assertEqual("NONE", result["authority_effect"])


class DeterministicReplayTests(unittest.TestCase):
    def test_two_calls_with_identical_input_agree_exactly(self):
        first = contract.to_canonical(
            "26.65", source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="open",
        )
        second = contract.to_canonical(
            "26.65", source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="open",
        )
        self.assertEqual(first, second)

    def test_assert_deterministic_replay_helper_passes_for_valid_input(self):
        contract.assert_deterministic_replay(
            "26.65", source="DNSE", capability_id="ohlc_1D",
            instrument_class="VN_LISTED_EQUITY", field="open",
        )


class FailClosedLookupTests(unittest.TestCase):
    def test_unknown_source_raises_no_fallback(self):
        with self.assertRaises(contract.RepresentationContractError):
            contract.to_canonical(
                "21.15", source="FHSC", capability_id="ohlc_1D",
                instrument_class="VN_LISTED_EQUITY", field="close",
            )

    def test_unknown_capability_raises(self):
        with self.assertRaises(contract.RepresentationContractError):
            contract.lookup_contract("DNSE", "not_a_real_capability", "VN_LISTED_EQUITY")

    def test_field_not_covered_by_contract_raises(self):
        with self.assertRaises(contract.RepresentationContractError):
            contract.to_canonical(
                "21.15", source="DNSE", capability_id="ohlc_1D",
                instrument_class="VN_LISTED_EQUITY", field="not_a_real_field",
            )

    def test_non_numeric_value_raises_rather_than_coercing(self):
        with self.assertRaises(contract.RepresentationContractError):
            contract.to_canonical(
                "not_a_number", source="DNSE", capability_id="ohlc_1D",
                instrument_class="VN_LISTED_EQUITY", field="close",
            )

    def test_ohlc_helper_raises_if_contract_does_not_cover_all_four_fields(self):
        with self.assertRaises(contract.RepresentationContractError):
            contract.to_canonical_ohlc(
                open_=1, high=1, low=1, close=1,
                source="DNSE", capability_id="bid_ask_depth", instrument_class="VN_LISTED_EQUITY",
            )


class ForeignFlowExclusionTests(unittest.TestCase):
    """Foreign-flow VALUE fields are natively raw VND, not thousands -- they must never be
    reachable through this module's scale factor, which would silently fabricate a 1000x
    error rather than fix a real one."""

    def test_no_contract_entry_covers_foreign_trading(self):
        capability_ids = {c["capability_id"] for c in contract.REPRESENTATION_CONTRACTS}
        self.assertNotIn("foreign_trading", capability_ids)

    def test_foreign_trading_lookup_fails_closed(self):
        with self.assertRaises(contract.RepresentationContractError):
            contract.lookup_contract("DNSE", "foreign_trading", "VN_LISTED_EQUITY")

    def test_native_vnd_no_transform_table_documents_the_exclusion(self):
        sources = {c["source"] for c in contract.NATIVE_VND_NO_TRANSFORM_CAPABILITIES}
        self.assertIn("DNSE", sources)


if __name__ == "__main__":
    unittest.main()
