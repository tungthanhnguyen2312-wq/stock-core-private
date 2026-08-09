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


if __name__ == "__main__":
    unittest.main()
