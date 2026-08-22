"""Tests for market_price_volume_basis_authority.py (MARKET_PRICE_VOLUME_BASIS_QUALIFICATION_V1).

Validation coverage intentionally spans: price representation/unit safety, current-vs-historical
basis separation, corporate-action event-window boundaries, board-semantic regressions, numeric
board-composition fail-closed behavior, volume/value arithmetic-identity citation, odd-lot /
put-through non-conflation, missing-!=-zero, provider-disagreement preservation, current-valuation
authority-boundary preservation, liquidity/sizing gates, PIT/backtest fail-closed behavior, and
deterministic artifact identity across two independent builds.
"""
from __future__ import annotations

import unittest

import market_price_volume_basis_authority as basis_authority
import market_data_source_authority as source_authority


class BuildMatrixShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = basis_authority.build_matrix()

    def test_every_row_declares_all_use_cases(self) -> None:
        for row in self.matrix["capability_rows"]:
            self.assertEqual(set(row["fitness"]), set(basis_authority.USE_CASES))

    def test_every_fitness_cell_is_a_registered_state_with_a_citation(self) -> None:
        for row in self.matrix["capability_rows"]:
            for use_case, cell in row["fitness"].items():
                self.assertIn(cell["state"], basis_authority.FITNESS_STATES)
                self.assertTrue(cell["cites"], f"{row['capability_id']}:{use_case} has no citation")

    def test_authority_effect_is_none_throughout(self) -> None:
        self.assertEqual(self.matrix["authority_effect"], "NONE")

    def test_rows_cover_both_domains(self) -> None:
        domains = {row["domain"] for row in self.matrix["capability_rows"]}
        self.assertEqual(domains, set(basis_authority.DOMAINS))


class PriceRepresentationUnitTests(unittest.TestCase):
    """No magnitude heuristic; unit representation is an explicit contract lookup."""

    def test_current_session_row_cites_explicit_contract_not_magnitude(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_OHLC_CURRENT_SESSION_CLOSE")
        self.assertIn("unit_representation_contract_id", row["evidence"])
        self.assertTrue(row["evidence"]["unit_representation_contract_id"].startswith("DNSE:ohlc_1D:VN_LISTED_EQUITY"))

    def test_unit_representation_row_is_independent_of_pit_and_backtest(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_KVND_TO_VND_UNIT_REPRESENTATION_CONTRACT")
        self.assertEqual(row["fitness"][basis_authority.PIT]["state"], basis_authority.NOT_APPLICABLE)
        self.assertEqual(row["fitness"][basis_authority.BACKTEST]["state"], basis_authority.NOT_APPLICABLE)
        # Eligible for descriptive/valuation representation, which is the point of Invariant 6.
        self.assertEqual(row["fitness"][basis_authority.CURRENT_DESCRIPTIVE_RESEARCH]["state"], basis_authority.ELIGIBLE)


class CurrentVsHistoricalSeparationTests(unittest.TestCase):
    def test_current_session_is_eligible_for_current_valuation(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_OHLC_CURRENT_SESSION_CLOSE")
        self.assertEqual(row["fitness"][basis_authority.CURRENT_VALUATION_RESEARCH]["state"], basis_authority.ELIGIBLE)

    def test_historical_series_is_not_applicable_for_current_valuation(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_OHLC_HISTORICAL_SERIES")
        self.assertEqual(row["fitness"][basis_authority.CURRENT_VALUATION_RESEARCH]["state"], basis_authority.NOT_APPLICABLE)

    def test_neither_current_nor_historical_reaches_pit_or_backtest(self) -> None:
        matrix = basis_authority.build_matrix()
        for capability_id in ("DNSE_OHLC_CURRENT_SESSION_CLOSE", "DNSE_OHLC_HISTORICAL_SERIES"):
            row = next(r for r in matrix["capability_rows"] if r["capability_id"] == capability_id)
            self.assertEqual(row["fitness"][basis_authority.PIT]["state"], basis_authority.BLOCKED)
            self.assertEqual(row["fitness"][basis_authority.BACKTEST]["state"], basis_authority.BLOCKED)

    def test_one_blocked_use_does_not_block_an_independent_eligible_use(self) -> None:
        """Milestone section 12's explicit example: PIT blocked must not erase a qualified
        current-session descriptive price."""
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_OHLC_CURRENT_SESSION_CLOSE")
        self.assertEqual(row["fitness"][basis_authority.PIT]["state"], basis_authority.BLOCKED)
        self.assertEqual(row["fitness"][basis_authority.CURRENT_DESCRIPTIVE_RESEARCH]["state"], basis_authority.ELIGIBLE)


class CorporateActionEventWindowTests(unittest.TestCase):
    def test_bounded_windows_row_is_backtest_blocked_despite_current_analysis_safety(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_BOUNDED_CORPORATE_ACTION_WINDOWS")
        self.assertEqual(row["fitness"][basis_authority.CURRENT_DESCRIPTIVE_RESEARCH]["state"], basis_authority.ELIGIBLE)
        self.assertEqual(row["fitness"][basis_authority.BACKTEST]["state"], basis_authority.BLOCKED)
        self.assertIs(row["evidence"]["current_analysis_price_basis_safe"], True)
        self.assertIs(row["evidence"]["backtest_point_in_time_safe"], False)

    def test_ex_date_row_documents_missing_evidence_not_inference(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "OFFICIAL_CORPORATE_ACTION_EX_DATE_EVIDENCE")
        self.assertEqual(row["evidence"]["blocking_reason_code"], "missing_explicit_official_ex_date")
        self.assertEqual(row["fitness"][basis_authority.PIT]["state"], basis_authority.BLOCKED)
        self.assertIn("record/payment/approval/new-shares-listing dates", row["evidence"]["finding"])


class BoardSemanticRegressionTests(unittest.TestCase):
    """Pins the exact, previously-established G1/G4/T1/T3/T4/T6 mapping so a silent change is caught."""

    def test_board_semantics_snapshot_matches_established_mapping(self) -> None:
        self.assertEqual(
            basis_authority.board_semantics_snapshot(),
            {
                "G1": "ROUND_LOT",
                "G4": "ODD_LOT",
                "T1": "PUT_THROUGH_ROUND_LOT",
                "T3": "PUT_THROUGH_ROUND_LOT",
                "T4": "PUT_THROUGH_ODD_LOT",
                "T6": "PUT_THROUGH_ODD_LOT",
            },
        )

    def test_board_semantics_not_silently_reopened_without_new_evidence(self) -> None:
        # market_phase2_foundation.DNSE_BOARD_SEMANTICS is DOCUMENTED, not re-derived here.
        import market_phase2_foundation
        self.assertEqual(basis_authority.board_semantics_snapshot(), dict(market_phase2_foundation.DNSE_BOARD_SEMANTICS))


class OddLotPutThroughSeparationTests(unittest.TestCase):
    def test_four_categories_are_pairwise_distinct_and_nonempty(self) -> None:
        categories = basis_authority.assert_lot_and_route_not_conflated()
        self.assertEqual(
            set(categories),
            {"MATCHED_ROUND_LOT", "MATCHED_ODD_LOT", "PUT_THROUGH_ROUND_LOT", "PUT_THROUGH_ODD_LOT"},
        )
        all_codes = [code for codes in categories.values() for code in codes]
        self.assertEqual(len(all_codes), len(set(all_codes)), "a board code appears in more than one category")

    def test_matched_and_put_through_are_never_merged(self) -> None:
        categories = basis_authority.assert_lot_and_route_not_conflated()
        matched_codes = set(categories["MATCHED_ROUND_LOT"]) | set(categories["MATCHED_ODD_LOT"])
        put_through_codes = set(categories["PUT_THROUGH_ROUND_LOT"]) | set(categories["PUT_THROUGH_ODD_LOT"])
        self.assertEqual(matched_codes & put_through_codes, set())

    def test_odd_lot_and_round_lot_are_never_merged(self) -> None:
        categories = basis_authority.assert_lot_and_route_not_conflated()
        round_lot_codes = set(categories["MATCHED_ROUND_LOT"]) | set(categories["PUT_THROUGH_ROUND_LOT"])
        odd_lot_codes = set(categories["MATCHED_ODD_LOT"]) | set(categories["PUT_THROUGH_ODD_LOT"])
        self.assertEqual(round_lot_codes & odd_lot_codes, set())


class NumericBoardCompositionTests(unittest.TestCase):
    def test_numeric_composition_row_is_not_reproducible_from_current_head(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_NUMERIC_BOARD_COMPOSITION")
        self.assertEqual(row["evidence"]["numeric_source_status"], "SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY")
        self.assertFalse(row["data_acquired"])

    def test_numeric_composition_never_reaches_eligible_for_sizing_or_liquidity(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_NUMERIC_BOARD_COMPOSITION")
        for use_case in (basis_authority.LIQUIDITY_RESEARCH, basis_authority.ADV_ADTV_RESEARCH, basis_authority.POSITION_SIZING, basis_authority.BACKTEST):
            self.assertEqual(row["fitness"][use_case]["state"], basis_authority.BLOCKED)

    def test_scaled_shadow_candidate_residuals_preserved_not_hidden(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_NUMERIC_BOARD_COMPOSITION")
        self.assertEqual(row["evidence"]["shadow_candidate_residuals_unresolved"], 67)
        self.assertEqual(row["evidence"]["shadow_candidate"]["scale_status"], "EMPIRICAL_CANDIDATE")
        self.assertEqual(row["evidence"]["shadow_candidate"]["semantic_unit_interpretation"], "UNKNOWN")


class VolumeValueArithmeticIdentityTests(unittest.TestCase):
    def test_fhsc_volume_identity_is_cited_not_invented(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "FHSC_MATCHED_PUT_THROUGH_TOTAL_VOLUME_DECOMPOSITION")
        self.assertIn("matched + put_through = total", row["evidence"]["documented_arithmetic_identity"])

    def test_dnse_traded_value_provider_disagreement_is_not_forced(self) -> None:
        """DNSE has no comparator at all; this must remain a documented absence, never a forced
        agreement or a fabricated zero."""
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_DAILY_TRADED_VALUE")
        self.assertFalse(row["data_acquired"])
        self.assertEqual(row["evidence"]["cross_check_verdict"], "DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE")


class MissingNotZeroTests(unittest.TestCase):
    def test_traded_value_absence_is_not_represented_as_a_zero_value(self) -> None:
        matrix = basis_authority.build_matrix()
        row = next(r for r in matrix["capability_rows"] if r["capability_id"] == "DNSE_DAILY_TRADED_VALUE")
        serialized = basis_authority.serialize(row)
        self.assertNotIn('"value": 0', serialized)
        self.assertNotIn('"value":0', serialized)


class CurrentValuationAuthorityBoundaryTests(unittest.TestCase):
    def test_price_input_impact_does_not_promote_shares_or_valuation(self) -> None:
        impact = basis_authority.current_valuation_price_input_impact()
        self.assertFalse(impact["common_shares_outstanding_promoted"])
        self.assertFalse(impact["new_formulas_added"])
        self.assertFalse(impact["market_wide_current_valuation_input_scaleout_touched"])
        self.assertEqual(impact["share_leg_unchanged_blocker"], "SHARE_BLOCKED")


class LiquidityAndSizingGateTests(unittest.TestCase):
    def test_no_volume_value_row_ever_reaches_eligible_or_partial_for_liquidity_or_sizing(self) -> None:
        matrix = basis_authority.build_matrix()
        for row in matrix["capability_rows"]:
            if row["domain"] != basis_authority.VOLUME_VALUE_BASIS_DOMAIN:
                continue
            for use_case in (basis_authority.LIQUIDITY_RESEARCH, basis_authority.ADV_ADTV_RESEARCH, basis_authority.POSITION_SIZING):
                self.assertIn(
                    row["fitness"][use_case]["state"], (basis_authority.BLOCKED, basis_authority.NOT_APPLICABLE),
                    f"{row['capability_id']}:{use_case} must not be open",
                )

    def test_liquidity_impact_reports_no_new_unlock(self) -> None:
        impact = basis_authority.liquidity_and_sizing_impact()
        self.assertFalse(impact["descriptive_turnover_or_liquidity_research_newly_unlocked"])
        self.assertFalse(impact["sizing_or_execution_capacity_newly_unlocked"])
        self.assertFalse(impact["position_sizing_is_safe"])


class PitBacktestFailClosedTests(unittest.TestCase):
    def test_no_row_anywhere_reaches_eligible_or_partial_for_pit_or_backtest(self) -> None:
        matrix = basis_authority.build_matrix()
        for row in matrix["capability_rows"]:
            for use_case in (basis_authority.PIT, basis_authority.BACKTEST):
                self.assertIn(
                    row["fitness"][use_case]["state"], (basis_authority.BLOCKED, basis_authority.NOT_APPLICABLE),
                    f"{row['capability_id']}:{use_case} must not be open",
                )

    def test_pit_backtest_impact_reports_no_readiness_change(self) -> None:
        impact = basis_authority.pit_and_backtest_impact()
        self.assertFalse(impact["pit_readiness_changed"])
        self.assertFalse(impact["backtest_readiness_changed"])
        self.assertEqual(impact["raw_as_traded"], "NOT_PROMOTED")
        self.assertFalse(impact["new_backtest_engine_implemented"])


class AssertRegistryFailClosedTests(unittest.TestCase):
    def test_passes_on_the_real_matrix(self) -> None:
        basis_authority.assert_registry_fail_closed()

    def test_rejects_a_tampered_matrix_that_opens_pit(self) -> None:
        matrix = basis_authority.build_matrix()
        tampered = dict(matrix)
        tampered["capability_rows"] = list(matrix["capability_rows"])
        row0 = dict(tampered["capability_rows"][0])
        row0["fitness"] = dict(row0["fitness"])
        row0["fitness"][basis_authority.PIT] = {"state": basis_authority.ELIGIBLE, "reason": "tampered", "cites": ["x"]}
        tampered["capability_rows"][0] = row0
        with self.assertRaises(basis_authority.BasisAuthorityError):
            basis_authority.assert_registry_fail_closed(tampered)

    def test_rejects_a_tampered_matrix_that_flips_the_liquidity_invariant(self) -> None:
        matrix = basis_authority.build_matrix()
        tampered = dict(matrix)
        tampered["global_invariants"] = dict(matrix["global_invariants"])
        tampered["global_invariants"]["qualified_liquidity_inputs"] = True
        with self.assertRaises(basis_authority.BasisAuthorityError):
            basis_authority.assert_registry_fail_closed(tampered)


class DeterministicArtifactIdentityTests(unittest.TestCase):
    def test_identical_build_produces_identical_identity(self) -> None:
        first = basis_authority.build_matrix()
        second = basis_authority.build_matrix()
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(basis_authority.serialize(first), basis_authority.serialize(second))

    def test_source_authority_constant_is_read_live_not_copied(self) -> None:
        matrix = basis_authority.build_matrix()
        self.assertEqual(matrix["global_invariants"]["dnse_ohlc_price_basis"], source_authority.DNSE_OHLC_PRICE_BASIS)
        self.assertEqual(matrix["global_invariants"]["dnse_market_volume_basis"], source_authority.DNSE_MARKET_VOLUME_BASIS)


class RowConstructionGuardTests(unittest.TestCase):
    def test_row_rejects_missing_use_case(self) -> None:
        incomplete = {use: basis_authority._fitness(basis_authority.NOT_APPLICABLE, reason="x", cites=["y"])
                      for use in basis_authority.USE_CASES if use != basis_authority.PIT}
        with self.assertRaises(basis_authority.BasisAuthorityError):
            basis_authority._row("X", basis_authority.PRICE_BASIS_DOMAIN, data_acquired=True, data_semantics_qualified=True,
                                 scope={}, source_modules=[], evidence={}, fitness=incomplete)

    def test_fitness_rejects_unregistered_state(self) -> None:
        with self.assertRaises(basis_authority.BasisAuthorityError):
            basis_authority._fitness("SORT_OF", reason="x", cites=["y"])

    def test_fitness_rejects_missing_citation(self) -> None:
        with self.assertRaises(basis_authority.BasisAuthorityError):
            basis_authority._fitness(basis_authority.BLOCKED, reason="x", cites=[])


if __name__ == "__main__":
    unittest.main()
