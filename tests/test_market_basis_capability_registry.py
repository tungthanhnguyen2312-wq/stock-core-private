"""Proofs for the cross-provider capability registry (market_basis_capability_registry.py).

Organised around the specific claims the milestone brief asks every reader to be able to
trust: provider namespace is preserved, the generic gate stays shut, a qualified capability
becomes available only under correct evidence, an unsupported capability stays blocked, and
none of this composition work invented a new liquidity or point-in-time-truth permission.
"""

from __future__ import annotations

import unittest

import kbs_capability_matrix as kbs
import market_basis_capability_registry as registry
import market_volume_capability_matrix as vci_volume
import provider_price_basis_registry as price_registry


class DelegationIsPassThroughNotRederivation(unittest.TestCase):
    """KBS and VCI-volume capabilities come from the existing matrices, unchanged."""

    def test_kbs_capability_matches_source_matrix_exactly(self):
        for name in kbs.CAPABILITY_MATRIX:
            self.assertEqual(registry.capability("KBS", name), kbs.capability(name))

    def test_vci_volume_capability_matches_source_matrix_exactly(self):
        for name in vci_volume.CAPABILITY_MATRIX:
            self.assertEqual(registry.capability("VCI", name), vci_volume.capability(name))

    def test_unregistered_provider_refused(self):
        with self.assertRaises(registry.RegistryError):
            registry.capability("EODHD", "anything")

    def test_unregistered_kbs_capability_refused(self):
        with self.assertRaises(registry.RegistryError):
            registry.capability("KBS", "not_a_real_capability")

    def test_unregistered_vci_capability_refused(self):
        with self.assertRaises(registry.RegistryError):
            registry.capability("VCI", "not_a_real_capability")


class VCIPriceMatrixIsEvidenceGrounded(unittest.TestCase):
    """The one real gap this module fills: VCI price capabilities, named and gated."""

    def test_five_shadow_capabilities_are_open(self):
        open_names = {
            "vci_namespaced_price_display", "vci_controlled_source_comparison",
            "vci_anomaly_detection", "vci_isolated_shadow_evaluation",
        }
        for name in open_names:
            record = registry.capability("VCI", name)
            self.assertEqual(record["availability"], kbs.AVAILABLE_UNDER_EXISTING_GATES)

    def test_conditional_capabilities_require_the_shared_label(self):
        for name in ("vci_namespaced_historical_returns", "vci_namespaced_technical_indicators"):
            record = registry.capability("VCI", name)
            self.assertEqual(record["availability"], kbs.AVAILABLE_WITH_REQUIRED_LABEL)
            self.assertEqual(record["required_label"], registry.PROVIDER_SERIES_RETURN_LABEL)
            self.assertEqual(record["required_label"], kbs.PROVIDER_SERIES_RETURN_LABEL)

    def test_point_in_time_truth_capabilities_are_unavailable_by_contract(self):
        for name in (
            "vci_point_in_time_valuation", "vci_official_exchange_price_claim",
            "vci_official_total_return_claim",
        ):
            record = registry.capability("VCI", name)
            self.assertEqual(record["availability"], kbs.UNAVAILABLE_BY_CONTRACT)
            self.assertIsNotNone(record["reason"])
            self.assertIsNotNone(record["reopen_condition"])

    def test_vci_price_verdict_is_read_from_the_canonical_registry_not_reinvented(self):
        """No string here is hardcoded independently of provider_price_basis_registry."""
        record = registry.capability("VCI", "vci_namespaced_historical_returns")
        canonical = price_registry.active_verdict("VCI")
        self.assertIn(canonical["price_basis"], record["note"])

    def test_vci_required_warnings_never_say_kbs(self):
        record = registry.capability("VCI", "vci_namespaced_historical_returns")
        for warning in record["required_warnings"]:
            self.assertNotIn("kbs", warning.lower())


class NoGenericPromotionAndNoCrossProviderInheritance(unittest.TestCase):
    def test_distinct_providers_pass_the_guard_cleanly(self):
        """Neither matrix's provider_scope claims to apply to the other provider, so the
        guard raises nothing -- it exists to catch a *regression* where one did."""
        registry.assert_no_cross_provider_inheritance("KBS", "VCI")
        registry.assert_no_cross_provider_inheritance("VCI", "KBS")

    def test_same_provider_is_a_no_op(self):
        registry.assert_no_cross_provider_inheritance("KBS", "KBS")
        registry.assert_no_cross_provider_inheritance("VCI", "VCI")

    def test_kbs_matrix_scope_correctly_reports_vci_as_foreign(self):
        scope = kbs.provider_scope("VCI")
        self.assertFalse(scope["contract_applies"])

    def test_vci_matrix_scope_correctly_reports_kbs_as_foreign(self):
        scope = vci_volume.provider_scope("KBS")
        self.assertFalse(scope["contract_applies"])


class Evaluate(unittest.TestCase):
    def test_kbs_descriptive_available_when_gates_passed(self):
        result = registry.evaluate("KBS", "kbs_ohlcv_display", existing_gates_passed=True)
        self.assertTrue(result["available"])

    def test_kbs_descriptive_unavailable_when_gates_not_passed(self):
        result = registry.evaluate("KBS", "kbs_ohlcv_display", existing_gates_passed=False)
        self.assertFalse(result["available"])

    def test_vci_liquidity_capability_never_opens_regardless_of_gates(self):
        result = registry.evaluate("VCI", "days_to_liquidate", existing_gates_passed=True)
        self.assertFalse(result["available"])
        self.assertEqual(result["availability"], kbs.UNAVAILABLE_BY_CONTRACT)

    def test_vci_conditional_requires_correct_label(self):
        with self.assertRaises(registry.RegistryError):
            registry.evaluate(
                "VCI", "vci_namespaced_historical_returns",
                existing_gates_passed=True, label="raw_as_traded_return",
            )

    def test_vci_conditional_missing_label_unavailable(self):
        result = registry.evaluate("VCI", "vci_namespaced_historical_returns", existing_gates_passed=True)
        self.assertFalse(result["available"])

    def test_vci_conditional_correct_label_available(self):
        result = registry.evaluate(
            "VCI", "vci_namespaced_historical_returns",
            existing_gates_passed=True, label=registry.PROVIDER_SERIES_RETURN_LABEL,
        )
        self.assertTrue(result["available"])

    def test_liquidity_actionable_always_false(self):
        for provider, name in (("KBS", "kbs_ohlcv_display"), ("VCI", "days_to_liquidate")):
            result = registry.evaluate(provider, name, existing_gates_passed=True)
            self.assertFalse(result["liquidity_actionable"])


class LadderLevelClassification(unittest.TestCase):
    """Class strings collide across matrices (both spell "descriptive_provider_scoped"
    identically); the ladder must still separate price from volume by name."""

    def test_price_descriptive_is_level_1_not_level_3(self):
        record = registry.capability("VCI", "vci_namespaced_price_display")
        self.assertEqual(registry.ladder_level(record), registry.LEVEL_PROVIDER_DESCRIPTIVE)

    def test_volume_descriptive_is_level_3(self):
        record = registry.capability("VCI", "provider_volume_history_display")
        self.assertEqual(registry.ladder_level(record), registry.LEVEL_QUALIFIED_VOLUME_DESCRIPTIVE)
        record = registry.capability("KBS", "kbs_descriptive_volume_statistics")
        self.assertEqual(registry.ladder_level(record), registry.LEVEL_QUALIFIED_VOLUME_DESCRIPTIVE)

    def test_kbs_price_descriptive_is_level_1(self):
        record = registry.capability("KBS", "kbs_ohlcv_display")
        self.assertEqual(registry.ladder_level(record), registry.LEVEL_PROVIDER_DESCRIPTIVE)

    def test_technical_and_conditional_are_level_2(self):
        for provider, name in (
            ("KBS", "kbs_rsi"), ("KBS", "kbs_provider_series_return"),
            ("VCI", "vci_namespaced_historical_returns"),
        ):
            record = registry.capability(provider, name)
            self.assertEqual(registry.ladder_level(record), registry.LEVEL_PROVIDER_ADJUSTED_ANALYTICS)

    def test_liquidity_and_execution_are_level_4(self):
        for provider, name in (
            ("KBS", "kbs_days_to_liquidate"), ("VCI", "days_to_liquidate"),
            ("VCI", "participation_rate_sizing"),
        ):
            record = registry.capability(provider, name)
            self.assertEqual(registry.ladder_level(record), registry.LEVEL_MARKET_SCOPE_QUALIFIED_LIQUIDITY)

    def test_point_in_time_truth_is_level_5(self):
        for provider, name in (
            ("KBS", "kbs_official_exchange_price_claim"), ("VCI", "vci_point_in_time_valuation"),
        ):
            record = registry.capability(provider, name)
            self.assertEqual(registry.ladder_level(record), registry.LEVEL_GENERIC_RAW_AUTHORITATIVE)

    def test_every_ladder_level_is_named(self):
        for level in range(6):
            self.assertIn(level, registry.LADDER_LEVELS)


class MatrixSnapshotAndFailClosed(unittest.TestCase):
    def test_snapshot_is_deterministic(self):
        self.assertEqual(registry.matrix_snapshot(), registry.matrix_snapshot())

    def test_snapshot_liquidity_actionable_false(self):
        self.assertFalse(registry.matrix_snapshot()["liquidity_actionable"])

    def test_assert_registry_fail_closed_does_not_raise(self):
        registry.assert_registry_fail_closed()

    def test_no_level_4_or_5_capability_is_open(self):
        snap = registry.matrix_snapshot()
        for key, record in snap["capabilities"].items():
            if registry.ladder_level(record) >= registry.LEVEL_MARKET_SCOPE_QUALIFIED_LIQUIDITY:
                self.assertEqual(
                    record["availability"], kbs.UNAVAILABLE_BY_CONTRACT,
                    msg=f"{key} is a Level 4/5 capability but is not unavailable_by_contract",
                )

    def test_snapshot_includes_both_providers(self):
        snap = registry.matrix_snapshot()
        providers = {v["provider"] for v in snap["capabilities"].values()}
        self.assertEqual(providers, {"KBS", "VCI"})


class GapTable(unittest.TestCase):
    def test_gap_table_nonempty_and_covers_required_capabilities(self):
        table = registry.generic_unlock_gap_table()
        self.assertGreaterEqual(len(table), 5)
        names = {row["capability"] for row in table}
        for expected in (
            "raw_as_traded_price", "generic_adjusted_price", "current_market_cap",
            "historical_point_in_time_valuation", "average_daily_volume_and_tradability",
        ):
            self.assertIn(expected, names)

    def test_every_row_has_all_five_columns(self):
        for row in registry.generic_unlock_gap_table():
            for column in (
                "capability", "already_proven", "missing_evidence",
                "required_authority", "next_bounded_action",
            ):
                self.assertIn(column, row)
                self.assertTrue(str(row[column]).strip())

    def test_gap_table_is_a_copy_not_the_live_constant(self):
        table = registry.generic_unlock_gap_table()
        table[0]["capability"] = "mutated"
        self.assertNotEqual(registry.generic_unlock_gap_table()[0]["capability"], "mutated")


class GenericMarketBasisUnlockMilestone(unittest.TestCase):
    """2026-08-09: bounded official raw-price pilot and no-fallback authority rule."""

    def test_explicit_raw_adjusted_namespace_is_a_bounded_pilot(self):
        self.assertEqual(registry.EXPLICIT_RAW_ADJUSTED_NAMESPACE, "PILOT_PARTIAL")

    def test_raw_as_traded_price_authority_is_partial(self):
        self.assertEqual(registry.RAW_AS_TRADED_PRICE_AUTHORITY, "PARTIAL")

    def test_inspection_record_keeps_provider_search_negative_and_official_pilot_positive(self):
        self.assertEqual(registry.RAW_PRICE_NAMESPACE_INSPECTION["adjust_vocabulary_matches"], 0)
        self.assertEqual(
            registry.RAW_PRICE_NAMESPACE_INSPECTION["official_sources_with_price_bearing_document_types"],
            ("hose:official_exchange_annual_trading_statistics",),
        )
        self.assertEqual(
            registry.RAW_PRICE_NAMESPACE_INSPECTION["official_sources_with_daily_statistics_candidates"],
            ("hose:official_exchange_daily_trading_summary",),
        )

    def test_daily_summary_route_is_a_precise_terminal_schema_blocker(self):
        self.assertEqual(registry.OFFICIAL_DAILY_TICKER_SESSION_ROUTE_MILESTONE, "TERMINAL_BLOCKER")
        self.assertEqual(
            registry.OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE,
            "BLOCKED_NONCONFORMING_SUMMARY_ONLY",
        )
        route = registry.OFFICIAL_DAILY_ROUTE_QUALIFICATION
        self.assertEqual(route["daily_raw_price_observations_added"], 0)
        self.assertEqual(route["identity_fields"]["price"], "absent for individual equities; 'Closing value' is an index field")

    def test_daily_summary_finding_does_not_reopen_generic_raw_price(self):
        gap = {row["capability"]: row for row in registry.generic_unlock_gap_table()}["raw_as_traded_price"]
        self.assertEqual(
            gap["missing_evidence"],
            "OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_NONCONFORMING_SUMMARY_ONLY",
        )
        self.assertEqual(registry.RAW_AS_TRADED_PRICE_AUTHORITY, "PARTIAL")

    def test_source_authority_selection_is_not_a_capability_transition(self):
        selection = registry.MARKET_DATA_SOURCE_AUTHORITY_SELECTION
        self.assertEqual(selection["selection_state"], "OWNER_SOURCE_ACQUISITION_DECISION")
        self.assertTrue(selection["raw_price_authority_source_selected"])
        self.assertEqual(selection["raw_price_authority_after_selection"], "PARTIAL")
        self.assertEqual(selection["generic_actionable_price_basis"], "BLOCKED")

    def test_selected_source_records_external_access_without_promoting_authority(self):
        selection = registry.MARKET_DATA_SOURCE_AUTHORITY_SELECTION
        self.assertEqual(selection["fiingroup_access_state"], "OWNER_ACQUISITION_REQUIRED")
        self.assertEqual(selection["license_authority"], "OWNER_CONFIRMATION_REQUIRED")
        self.assertEqual(selection["market_data_track"], "WAITING_EXTERNAL_ACCESS")

    def test_official_raw_observation_carries_source_identity_and_unit(self):
        observation = registry.official_raw_price_observation("HPG", "2024-12-31")
        self.assertEqual(observation["source_id"], "HOSE")
        self.assertEqual(observation["value_vnd_per_share"], 26650)
        self.assertEqual(observation["namespace"], "official_raw_as_traded_pilot")
        self.assertTrue(observation["sha256"])

    def test_official_raw_observation_has_no_nearest_date_or_provider_fallback(self):
        with self.assertRaises(registry.RegistryError):
            registry.official_raw_price_observation("HPG", "2024-12-30")
        result = registry.select_price_authority(
            "raw_eod_observation", provider="VCI", ticker="HPG", trading_session_date="2024-12-30"
        )
        self.assertEqual(result["tier"], registry.AUTHORITY_TIER_BLOCKED)
        self.assertIn("not_retained", result["reason"])

    def test_raw_and_adjusted_namespaces_stay_explicitly_separate(self):
        reconciliation = registry.reconcile_raw_and_provider_adjusted(
            ticker="HPG", trading_session_date="2024-12-31",
            provider_adjusted_value_vnd_per_share=19830, provider="VCI",
        )
        self.assertEqual(reconciliation["status"], "partial_distinct_namespaces")
        self.assertEqual(reconciliation["official_raw"]["value_vnd_per_share"], 26650)
        self.assertEqual(reconciliation["provider_adjusted"]["value_vnd_per_share"], 19830.0)
        self.assertNotEqual(
            reconciliation["official_raw"]["namespace"], reconciliation["provider_adjusted"]["namespace"]
        )

    def test_exact_official_raw_identity_selects_tier_one_only_for_raw_capability(self):
        result = registry.select_price_authority(
            "point_in_time_price", ticker="HPG", trading_session_date="2024-12-31"
        )
        self.assertEqual(result["tier"], registry.AUTHORITY_TIER_OFFICIAL_RAW)
        valuation = registry.select_price_authority(
            "current_valuation", ticker="HPG", trading_session_date="2024-12-31"
        )
        self.assertEqual(valuation["tier"], registry.AUTHORITY_TIER_BLOCKED)

    def test_kbs_gains_a_new_volume_composition_capability(self):
        record = registry.capability("KBS", "kbs_volume_composition_disclosure")
        self.assertEqual(record["availability"], kbs.AVAILABLE_UNDER_EXISTING_GATES)

    def test_kbs_volume_trade_scope_reachable_through_matrix_snapshot(self):
        snap = kbs.matrix_snapshot()
        self.assertEqual(snap["volume_trade_scope"]["overall_composition_state"], "partial_composition_qualified")
        # The pre-existing, separately-guarded field is untouched by this milestone.
        self.assertEqual(snap["volume_market_scope"], "unknown")

    def test_days_to_liquidate_still_unavailable_after_the_new_finding(self):
        """Partial composition qualification must not, by itself, open a liquidity
        capability -- odd_lot_inclusion is still unknown."""
        record = registry.capability("KBS", "kbs_days_to_liquidate")
        self.assertEqual(record["availability"], kbs.UNAVAILABLE_BY_CONTRACT)

    def test_authority_tier_3_only_for_descriptive_capability_kinds(self):
        result = registry.select_price_authority("descriptive_price", provider="VCI")
        self.assertEqual(result["tier"], registry.AUTHORITY_TIER_PROVIDER_ADJUSTED_DESCRIPTIVE)

    def test_authority_blocked_for_valuation_regardless_of_provider(self):
        for provider in ("VCI", "KBS"):
            result = registry.select_price_authority("current_valuation", provider=provider)
            self.assertEqual(result["tier"], registry.AUTHORITY_TIER_BLOCKED)

    def test_authority_blocked_when_no_provider_named(self):
        """No implicit best-available-provider selection."""
        result = registry.select_price_authority("descriptive_price", provider=None)
        self.assertEqual(result["tier"], registry.AUTHORITY_TIER_BLOCKED)
        self.assertIsNone(result["provider"])

    def test_authority_result_names_exactly_one_provider_never_merges(self):
        result = registry.select_price_authority("descriptive_price", provider="KBS")
        self.assertEqual(result["provider"], "KBS")

    def test_fallback_merging_across_providers_for_same_capability_raises(self):
        with self.assertRaises(registry.RegistryError):
            registry.assert_no_fallback_merging(
                [
                    {"capability_kind": "descriptive_price", "provider": "VCI"},
                    {"capability_kind": "descriptive_price", "provider": "KBS"},
                ]
            )

    def test_fallback_merging_guard_passes_distinct_capabilities(self):
        registry.assert_no_fallback_merging(
            [
                {"capability_kind": "descriptive_price", "provider": "VCI"},
                {"capability_kind": "descriptive_volume", "provider": "KBS"},
            ]
        )

    def test_gap_table_average_daily_volume_reflects_kbs_partial_finding(self):
        table = {row["capability"]: row for row in registry.generic_unlock_gap_table()}
        row = table["average_daily_volume_and_tradability"]
        self.assertIn("kbs_trade_scope_qualification", row["already_proven"])


if __name__ == "__main__":
    unittest.main()
