"""Proofs for qualified_market_observations.py -- the provider-scoped descriptive/technical
price and volume section this milestone connects into the research product.

Covers exactly the properties section 20 of the milestone brief asks for: provider
namespace preserved, the generic gate untouched, unsupported input fails closed, volume
shares never imply liquidity eligibility, a provider-adjusted price never implies
raw-as-traded eligibility, no provider-to-generic silent promotion, and deterministic
output.
"""

from __future__ import annotations

import unittest

import qualified_market_observations as qmo


def _rows(n: int, *, start: float = 50_000.0, day_offset: int = 0) -> list[dict]:
    rows = []
    price = start
    for i in range(n):
        price *= 1.001
        day = ((i + day_offset) % 28) + 1
        rows.append({
            "date": f"2026-01-{day:02d}",
            "open": price, "high": price * 1.01, "low": price * 0.99,
            "close": price, "volume": 100_000 + i * 10,
        })
    return rows


def _entry(rows, provider="VCI", pure=True, sources_seen=None):
    return {
        "ohlcv_recent": rows,
        "ohlcv_provider_provenance": {
            "provider": provider if pure else None,
            "pure": pure,
            "sources_seen": sources_seen if sources_seen is not None else ([provider] if provider else []),
        },
    }


class FailsClosedOnBadInput(unittest.TestCase):
    def test_none_entry(self):
        result = qmo.evaluate("HPG", None)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["is_actionable"])

    def test_missing_provenance(self):
        result = qmo.evaluate("HPG", {"ohlcv_recent": _rows(30)})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "ohlcv_provider_provenance_absent")

    def test_mixed_provider_window_refused(self):
        entry = _entry(_rows(30), pure=False, sources_seen=["VCI", "KBS"])
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "ohlcv_window_mixes_more_than_one_provider")

    def test_unsupported_provider_refused(self):
        entry = _entry(_rows(30), provider="SSI")
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["reason"].startswith("provider_not_in_capability_registry"))

    def test_missing_ohlcv_recent(self):
        entry = {"ohlcv_provider_provenance": {"provider": "VCI", "pure": True}}
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "ohlcv_recent_absent")

    def test_insufficient_history_refused(self):
        entry = _entry(_rows(qmo.MIN_SESSIONS - 1))
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "insufficient_session_history")

    def test_exactly_min_sessions_is_sufficient(self):
        entry = _entry(_rows(qmo.MIN_SESSIONS))
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["status"], "available")

    def test_unavailable_result_still_carries_provider_when_known(self):
        entry = _entry(_rows(3), provider="VCI")
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["provider"], "VCI")


class ActionabilityNeverLeaks(unittest.TestCase):
    """No combination of inputs may turn is_actionable or liquidity_actionable on."""

    def test_available_result_is_actionable_false(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["status"], "available")
        self.assertFalse(result["is_actionable"])
        self.assertFalse(result["liquidity_actionable"])
        self.assertFalse(result["market_dependent"])

    def test_unavailable_result_is_actionable_false(self):
        result = qmo.evaluate("HPG", None)
        self.assertFalse(result["is_actionable"])
        self.assertFalse(result["liquidity_actionable"])

    def test_kbs_result_is_also_never_actionable(self):
        entry = _entry(_rows(60), provider="KBS")
        result = qmo.evaluate("VNM", entry)
        self.assertFalse(result["is_actionable"])
        self.assertFalse(result["liquidity_actionable"])


class ProviderNamespacePreserved(unittest.TestCase):
    def test_vci_provider_recorded(self):
        entry = _entry(_rows(60), provider="VCI")
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["provider"], "VCI")
        self.assertEqual(result["namespace"], "provider_scoped")
        self.assertTrue(result["descriptive_only"])

    def test_kbs_provider_recorded(self):
        entry = _entry(_rows(60), provider="KBS")
        result = qmo.evaluate("VNM", entry)
        self.assertEqual(result["provider"], "KBS")
        self.assertEqual(result["namespace"], "provider_scoped")

    def test_ticker_is_upper_cased_and_matches_input(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("hpg", entry)
        self.assertEqual(result["ticker"], "HPG")


class VolumeSharesDoNotImplyLiquidityEligibility(unittest.TestCase):
    def test_descriptive_volume_present_but_no_liquidity_fields_exist(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        self.assertIsNotNone(result["descriptive_volume"])
        for forbidden_key in ("days_to_liquidate", "participation_rate", "market_impact", "tradable_size"):
            self.assertNotIn(forbidden_key, result)
            self.assertNotIn(forbidden_key, result["descriptive_volume"])

    def test_prohibited_claims_include_liquidity_and_sizing(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        for claim in ("current_market_liquidity", "position_sizing", "market_impact", "days_to_liquidate"):
            self.assertIn(claim, result["prohibited_claims"])


class ProviderAdjustedPriceDoesNotImplyRawEligibility(unittest.TestCase):
    def test_price_basis_reports_raw_as_traded_eligible_false(self):
        entry = _entry(_rows(60), provider="VCI")
        result = qmo.evaluate("HPG", entry)
        self.assertFalse(result["price_basis"]["raw_as_traded_eligible"])

    def test_prohibited_claims_include_raw_and_official_exchange(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        self.assertIn("raw_as_traded_price", result["prohibited_claims"])
        self.assertIn("official_exchange_price", result["prohibited_claims"])
        self.assertIn("total_shareholder_return", result["prohibited_claims"])

    def test_return_descriptors_carry_the_required_label_when_present(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        self.assertIsNotNone(result["return_descriptors"])
        self.assertEqual(result["return_descriptors"]["required_label"], "provider_series_return")


class NoProviderToGenericSilentPromotion(unittest.TestCase):
    def test_output_never_contains_generic_field_names(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        for generic_field in ("price_basis_verified", "volume_basis_verified", "official_close", "adjusted_close"):
            self.assertNotIn(generic_field, result)

    def test_two_different_providers_produce_different_verdicts(self):
        vci_entry = _entry(_rows(60), provider="VCI")
        kbs_entry = _entry(_rows(60), provider="KBS")
        vci_result = qmo.evaluate("HPG", vci_entry)
        kbs_result = qmo.evaluate("HPG", kbs_entry)
        self.assertNotEqual(vci_result["provider"], kbs_result["provider"])
        # KBS carries an extra volume_market_scope fact VCI's summary does not.
        self.assertIn("volume_market_scope", kbs_result["price_basis"])
        self.assertNotIn("volume_market_scope", vci_result["price_basis"])


class NullVsZero(unittest.TestCase):
    def test_zero_volume_session_is_retained_not_dropped(self):
        rows = _rows(60)
        rows[-1]["volume"] = 0
        entry = _entry(rows)
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["descriptive_volume"]["session_count"], 60)
        self.assertEqual(result["descriptive_volume"]["latest_volume"], 0)

    def test_none_close_session_is_excluded_from_price_stats(self):
        rows = _rows(30) + [{"date": "2026-02-01", "open": None, "high": None, "low": None, "close": None, "volume": 100}]
        entry = _entry(rows)
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["descriptive_price"]["session_count"], 30)


class DeterministicOutput(unittest.TestCase):
    def test_same_input_produces_identical_output(self):
        entry = _entry(_rows(60))
        first = qmo.evaluate("HPG", entry)
        second = qmo.evaluate("HPG", entry)
        self.assertEqual(first, second)

    def test_as_of_date_comes_from_data_not_wall_clock(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        self.assertEqual(result["descriptive_price"]["as_of_date"], entry["ohlcv_recent"][-1]["date"])


class CapabilityRegistryIntegration(unittest.TestCase):
    """Every computed field's availability is decided by the registry, not re-derived here."""

    def test_descriptive_price_capability_matches_registry(self):
        import market_basis_capability_registry as registry
        entry = _entry(_rows(60), provider="VCI")
        result = qmo.evaluate("HPG", entry)
        expected = registry.evaluate("VCI", "vci_namespaced_price_display", existing_gates_passed=True)
        self.assertEqual(result["descriptive_price"]["capability"]["capability"], expected["capability"])

    def test_ladder_level_present_on_every_computed_field(self):
        entry = _entry(_rows(60))
        result = qmo.evaluate("HPG", entry)
        for section in ("descriptive_price", "descriptive_volume", "return_descriptors"):
            self.assertIn("ladder_level", result[section]["capability"])


if __name__ == "__main__":
    unittest.main()
