"""Tests for feature_input_fitness_contract.py.

Two concerns matter most for a consolidation/catalog module: (1) it must never drift from the
authoritative modules it points at -- every named module/function must actually exist -- and
(2) its thin evaluate_* wrappers must produce byte-identical output to calling the authoritative
function directly, proving they delegate rather than re-derive.
"""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feature_input_fitness_contract as fitness
import financial_entity_applicability
import monetary_basis_contract
import multi_source_market_evidence_contract
import technical_structure_context


class RegistryShapeTests(unittest.TestCase):
    def test_every_declared_family_is_registered(self) -> None:
        self.assertEqual(set(fitness.USE_CASE_FAMILIES), set(fitness.FAMILY_REGISTRY))

    def test_describe_returns_required_fields_for_every_family(self) -> None:
        required_keys = {
            "description", "required_dimensions", "fitness_tiers", "authoritative_module",
            "authoritative_functions", "known_blockers", "notes", "standing_block_reason",
        }
        for family in fitness.USE_CASE_FAMILIES:
            entry = fitness.describe(family)
            self.assertEqual(required_keys, set(entry.keys()), msg=family)
            self.assertTrue(entry["required_dimensions"], msg=f"{family} lists no required dimensions")
            self.assertTrue(entry["description"], msg=f"{family} has no description")

    def test_describe_unknown_family_fails_closed(self) -> None:
        with self.assertRaises(fitness.FeatureInputFitnessError):
            fitness.describe("NOT_A_REAL_FAMILY")

    def test_is_standing_blocked_unknown_family_fails_closed(self) -> None:
        with self.assertRaises(fitness.FeatureInputFitnessError):
            fitness.is_standing_blocked("NOT_A_REAL_FAMILY")

    def test_execution_liquidity_is_standing_blocked(self) -> None:
        blocked, reason = fitness.is_standing_blocked(fitness.EXECUTION_LIQUIDITY)
        self.assertTrue(blocked)
        self.assertIn("LIQUIDITY_AND_POSITION_SIZING_AUTHORITY", reason)

    def test_current_session_price_is_not_standing_blocked(self) -> None:
        blocked, reason = fitness.is_standing_blocked(fitness.CURRENT_SESSION_PRICE)
        self.assertFalse(blocked)
        self.assertIsNone(reason)

    def test_snapshot_shape(self) -> None:
        snap = fitness.snapshot()
        self.assertEqual(snap["contract_version"], fitness.CONTRACT_VERSION)
        self.assertEqual(set(snap["registry"]), set(fitness.USE_CASE_FAMILIES))
        self.assertEqual(snap["authority_effect"], "NONE")
        self.assertIn(fitness.EXECUTION_LIQUIDITY, snap["standing_blocked_families"])

    def test_financial_scaleout_families_are_explicit_and_keep_their_existing_authorities(self) -> None:
        expected = {
            fitness.FINANCIAL_REVENUE_GROWTH, fitness.FINANCIAL_EARNINGS_GROWTH,
            fitness.FINANCIAL_MARGIN, fitness.FINANCIAL_ROE_ROA,
            fitness.FINANCIAL_LEVERAGE_LIQUIDITY, fitness.FINANCIAL_CASH_FLOW_QUALITY,
            fitness.FINANCIAL_FREE_CASH_FLOW_PROXY, fitness.ENTERPRISE_VALUE,
            fitness.EV_SALES, fitness.FUNDAMENTAL_PEER_RELATIVE,
            fitness.FUNDAMENTAL_OWN_HISTORY, fitness.FINANCIAL_POINT_IN_TIME_BACKTEST,
        }
        self.assertTrue(expected.issubset(fitness.USE_CASE_FAMILIES))
        self.assertEqual(
            fitness.describe(fitness.FINANCIAL_POINT_IN_TIME_BACKTEST)["fitness_tiers"],
            ("BLOCKED",),
        )


class RegistryPointersAreRealTests(unittest.TestCase):
    """Every authoritative_module/authoritative_functions entry that names an importable Python
    module (as opposed to a doc/consumer reference like 'docs/ROADMAP_STATE.json#...' or a
    consumer name in parentheses) must actually resolve -- this is the guard against the
    registry silently drifting from the real code it claims to describe."""

    def test_python_module_pointers_resolve(self) -> None:
        for family in fitness.USE_CASE_FAMILIES:
            entry = fitness.FAMILY_REGISTRY[family]
            module_name = entry["authoritative_module"]
            if "/" in module_name or "#" in module_name:
                continue  # a doc/registry reference, not a Python module
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                self.fail(f"{family}: authoritative_module {module_name!r} does not import: {exc}")
            for function_name in entry["authoritative_functions"]:
                base_name = function_name.split(" ")[0]  # strip "(consumer)"/parenthetical annotations
                if base_name.isupper() or "(" in function_name:
                    continue  # a constant name or an annotated consumer reference, not a callable
                self.assertTrue(
                    hasattr(module, base_name),
                    msg=f"{family}: {module_name}.{base_name} does not exist",
                )


class DelegationIsByteIdenticalTests(unittest.TestCase):
    """Each evaluate_* wrapper must reproduce the authoritative function's own output exactly --
    proving it delegates rather than re-derives even a slightly different verdict."""

    def test_evaluate_current_session_price_matches_direct_call(self) -> None:
        observations = [
            {"status": "EXACT_SESSION_OBSERVED", "source": "DNSE", "native": {"close": 10.0}, "normalized": {"close": 10.0}},
        ]
        direct = multi_source_market_evidence_contract.resolve_ticker("HPG", observations)
        via_registry = fitness.evaluate_current_session_price("HPG", observations)
        self.assertEqual(direct, via_registry)

    def test_evaluate_current_session_price_all_missing_matches_direct_call(self) -> None:
        observations = [{"status": "SESSION_MISSING", "source": "DNSE"}]
        direct = multi_source_market_evidence_contract.resolve_ticker("HPG", observations)
        via_registry = fitness.evaluate_current_session_price("HPG", observations)
        self.assertEqual(direct, via_registry)
        self.assertEqual(via_registry["resolution"], "SESSION_MISSING_ALL_SOURCES")

    def test_evaluate_technical_close_history_matches_direct_call_on_agreement(self) -> None:
        session = "2026-08-28"
        pf_record = {"observations": [{"session": session, "close": 10.0}]}
        recovery_override = {
            "state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY",
            "observations": [{"session": session, "close": 10.0}],
        }
        direct_record, direct_source = technical_structure_context.resolve_target_session_observations(
            pf_record=pf_record, recovery_override=recovery_override, target_session=session,
        )
        via_registry = fitness.evaluate_technical_close_history(
            pf_record=pf_record, recovery_override=recovery_override, target_session=session,
        )
        self.assertEqual(via_registry, {"winning_record": direct_record, "source": direct_source})
        self.assertEqual(via_registry["source"], "RETAINED_TECHNICAL_HISTORY_RECOVERY")

    def test_evaluate_technical_close_history_rejects_close_mismatch(self) -> None:
        session = "2026-08-28"
        pf_record = {"observations": [{"session": session, "close": 99.0}]}
        recovery_override = {
            "state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY",
            "observations": [{"session": session, "close": 91.0}],  # disagrees
        }
        via_registry = fitness.evaluate_technical_close_history(
            pf_record=pf_record, recovery_override=recovery_override, target_session=session,
        )
        self.assertEqual(via_registry["source"], "RECOVERY_REJECTED_TARGET_SESSION_CLOSE_MISMATCH")
        self.assertEqual(via_registry["winning_record"], pf_record)

    def test_evaluate_valuation_monetary_basis_matches_direct_call(self) -> None:
        basis_a = monetary_basis_contract.build_basis(currency="VND", scale="units", basis_source="test_a")
        basis_b = monetary_basis_contract.build_basis(currency="USD", scale="units", basis_source="test_b")
        direct = monetary_basis_contract.compatible(basis_a, basis_b)
        via_registry = fitness.evaluate_valuation_monetary_basis(basis_a, basis_b)
        self.assertEqual(via_registry, {"compatible": direct[0], "reason": direct[1]})
        self.assertFalse(via_registry["compatible"])
        self.assertEqual(via_registry["reason"], monetary_basis_contract.INCOMPATIBLE_REASON)

    def test_evaluate_entity_class_applicability_matches_direct_call(self) -> None:
        archetype = {"issuer_entity_type": "bank", "template_family": "credit_institution", "authority": "manual_profile"}
        direct = financial_entity_applicability.metric_applicability(archetype, "ev_ebitda")
        via_registry = fitness.evaluate_entity_class_applicability(archetype, "ev_ebitda")
        self.assertEqual(direct, via_registry)
        self.assertEqual(via_registry["status"], "not_applicable")

    def test_evaluate_entity_class_applicability_corporate_is_applicable(self) -> None:
        archetype = {"issuer_entity_type": "corporate", "authority": "manual_profile"}
        via_registry = fitness.evaluate_entity_class_applicability(archetype, "ev_ebitda")
        self.assertEqual(via_registry["status"], "applicable_subject_to_inputs")


class RelativeVolumeVsCurrentSessionPriceAreDistinctTests(unittest.TestCase):
    """Section 9's exact concern: a CURRENT_SESSION_PRICE verdict must never be mistaken for a
    RELATIVE_VOLUME verdict. This test proves the registry documents them as genuinely different
    authorities (different module/functions), not merely different names for the same check."""

    def test_families_point_at_the_same_module_but_document_the_distinction(self) -> None:
        current_price = fitness.describe(fitness.CURRENT_SESSION_PRICE)
        relative_volume = fitness.describe(fitness.RELATIVE_VOLUME)
        self.assertNotEqual(current_price["authoritative_module"], relative_volume["authoritative_module"])
        self.assertIn("does NOT imply", relative_volume["notes"])


if __name__ == "__main__":
    unittest.main()
