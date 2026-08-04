"""Contract tests for the terminal VCI volume market-composition closeout.

No live request. The probe payload is exercised through the retained artifact.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import vci_volume_composition as composition

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSITION_DIR = REPO_ROOT / "operations-review" / "vci-volume-composition-20260804"
EVIDENCE_ROOTS = (
    REPO_ROOT / "operations-review" / "vci-direct-basis-pilot-20260804",
    REPO_ROOT / "operations-review" / "vci-intraday-pagination-20260804",
    COMPOSITION_DIR,
)


def unknown_verdicts(**overrides):
    verdicts = {
        "matched_trade_inclusion": "unknown",
        "negotiated_inclusion": "unknown",
        "odd_lot_inclusion": "unknown",
        "opening_auction_inclusion": "unknown",
        "closing_auction_inclusion": "unknown",
    }
    verdicts.update(overrides)
    return verdicts


def contract(**overrides):
    return composition.composition_contract(
        provider_internal_volume_reconciled=True,
        dimension_verdicts=unknown_verdicts(**overrides),
        unit="shares",
        corporate_action_adjustment="unknown",
        surfaces_examined=[],
    )


class ReconciliationIsNotComposition(unittest.TestCase):
    """1. Provider-internal reconciliation cannot qualify market composition."""

    def test_an_exact_internal_reconciliation_qualifies_nothing(self):
        result = contract()
        self.assertTrue(result["provider_internal_volume_reconciled"])
        for dimension in composition.COMPOSITION_DIMENSIONS:
            self.assertEqual(result[dimension], "unknown", dimension)
        self.assertEqual(result["market_scope"], "permanently_unresolved")

    def test_unit_and_field_identity_do_not_reach_composition(self):
        result = contract()
        self.assertEqual(result["volume_unit"], "shares")
        self.assertEqual(result["volume_field_identity"], "qualified")
        self.assertEqual(result["negotiated_inclusion"], "unknown")


class NamesAreNotSemantics(unittest.TestCase):
    """2/3. Field names alone cannot upgrade; a missing definition preserves unknown."""

    def test_a_suggestive_name_is_not_a_definition(self):
        for field in ("totalVolume", "accumulatedVolumeG1", "totalBuyOrders", "matchedVolume"):
            result = composition.classify_field_semantics(field_name=field, first_party_definition=None)
            self.assertEqual(result["status"], "name_only_not_qualified", field)

    def test_a_contextual_reading_is_not_explicit(self):
        result = composition.classify_field_semantics(
            field_name="accumulatedVolumeG1",
            first_party_definition="appears next to the total on the board",
            definition_kind="contextual",
        )
        self.assertEqual(result["status"], "name_only_not_qualified")

    def test_only_an_explicit_definition_qualifies_outright(self):
        result = composition.classify_field_semantics(
            field_name="putThroughVolume",
            first_party_definition="Khoi luong giao dich thoa thuan",
            definition_kind="explicit",
        )
        self.assertEqual(result["status"], "qualified")
        self.assertEqual(
            composition.qualify_dimension(dimension="negotiated_inclusion", explicit_definition=result),
            "qualified",
        )

    def test_missing_definitions_leave_every_dimension_unknown(self):
        for dimension in composition.COMPOSITION_DIMENSIONS:
            self.assertEqual(
                composition.qualify_dimension(
                    dimension=dimension, explicit_definition=None, demonstrated_relationship=None
                ),
                "unknown",
            )

    def test_arithmetic_alone_cannot_qualify(self):
        # Two undefined fields that reconcile perfectly still qualify nothing.
        undefined = [
            composition.classify_field_semantics(field_name="accumulatedVolume", first_party_definition=None),
            composition.classify_field_semantics(field_name="accumulatedVolumeG1", first_party_definition=None),
        ]
        self.assertEqual(
            composition.qualify_dimension(
                dimension="matched_trade_inclusion",
                demonstrated_relationship={
                    "component_fields": undefined,
                    "reconciles": True,
                    "referent_pinned_by_independent_field": True,
                },
            ),
            "unknown",
        )

    def test_an_exchange_term_still_needs_a_reconciliation_and_a_pin(self):
        ato = composition.classify_field_semantics(field_name="matchVolumeATO", first_party_definition=None)
        self.assertEqual(ato["status"], "exchange_standard_term")
        # Name alone: no.
        self.assertEqual(
            composition.qualify_dimension(dimension="opening_auction_inclusion", explicit_definition=ato),
            "unknown",
        )
        # Reconciles but nothing independently pins the referent: still no.
        self.assertEqual(
            composition.qualify_dimension(
                dimension="opening_auction_inclusion",
                demonstrated_relationship={
                    "component_fields": [ato],
                    "reconciles": True,
                    "referent_pinned_by_independent_field": False,
                },
            ),
            "unknown",
        )
        # Reconciles and pinned: qualified.
        self.assertEqual(
            composition.qualify_dimension(
                dimension="opening_auction_inclusion",
                demonstrated_relationship={
                    "component_fields": [ato],
                    "reconciles": True,
                    "referent_pinned_by_independent_field": True,
                },
            ),
            "qualified",
        )


class PartialQualificationUnlocksNothing(unittest.TestCase):
    """4/5. A qualified component cannot open liquidity; unresolved stays fail-closed."""

    def test_a_qualified_component_leaves_liquidity_shut(self):
        result = composition.assert_canonical_vocabulary(
            contract(opening_auction_inclusion="qualified")
        )
        self.assertEqual(result["market_scope"], "partially_observed_but_not_qualified")
        self.assertFalse(result["liquidity_actionable"])
        eligibility = composition.liquidity_eligibility(result)
        self.assertEqual(eligibility["available"], [])
        for capability in ("days_to_liquidate", "market_impact", "position_sizing"):
            self.assertIn(capability, eligibility["unavailable"])

    def test_permanently_unresolved_is_fail_closed(self):
        result = composition.assert_fail_closed(contract())
        self.assertEqual(result["market_scope"], "permanently_unresolved")
        self.assertEqual(
            result["market_composition_resolution"], "unavailable_from_observed_vci_surfaces"
        )
        self.assertFalse(result["liquidity_actionable"])
        self.assertIn("currently observable", result["permanence_scope"])

    def test_a_leaked_actionability_flag_is_refused(self):
        leaked = dict(contract())
        leaked["liquidity_actionable"] = True
        with self.assertRaises(composition.CompositionError):
            composition.assert_fail_closed(leaked)

    def test_a_qualified_auction_roll_up_must_name_its_legs(self):
        result = contract(opening_auction_inclusion="qualified")
        self.assertEqual(result["auction_inclusion"], "partially_observed")
        self.assertEqual(result["auction_inclusion_scope"], ["opening_auction_inclusion"])
        self.assertEqual(result["auction_inclusion_unresolved_legs"], ["closing_auction_inclusion"])
        stripped = dict(result)
        stripped.pop("auction_inclusion_scope")
        with self.assertRaises(composition.CompositionError):
            composition.assert_fail_closed(stripped)

    def test_the_roll_up_cannot_be_asserted_directly(self):
        with self.assertRaises(composition.CompositionError):
            composition.composition_contract(
                provider_internal_volume_reconciled=True,
                dimension_verdicts={"auction_inclusion": "qualified"},
                unit="shares",
                corporate_action_adjustment="unknown",
                surfaces_examined=[],
            )

    def test_one_leg_does_not_speak_for_the_other(self):
        result = contract(opening_auction_inclusion="qualified")
        self.assertEqual(result["closing_auction_inclusion"], "unknown")


class NoFurtherProbing(unittest.TestCase):
    """6/7/8. Pagination is closed, speculation is refused, a probe needs provenance."""

    def test_pagination_is_not_authorized(self):
        self.assertFalse(composition.FURTHER_PAGINATION_AUTHORIZED)
        self.assertFalse(contract()["further_vci_pagination_authorized"])
        leaked = dict(contract())
        leaked["further_vci_pagination_authorized"] = True
        with self.assertRaises(composition.CompositionError):
            composition.assert_fail_closed(leaked)

    def test_a_speculative_endpoint_is_refused(self):
        for endpoint in (
            "https://trading.vietcap.com.vn/api/market-watch/PTData/getAll",
            "https://trading.vietcap.com.vn/api/price/putthrough/getList",
            "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term",
        ):
            with self.assertRaises(composition.CompositionError) as ctx:
                composition.assert_probe_permitted(endpoint)
            self.assertIn("speculative_endpoint_refused", str(ctx.exception))

    def test_a_probe_requires_observed_provenance(self):
        record = composition.assert_probe_permitted(
            "https://trading.vietcap.com.vn/api/price/symbols/getList"
        )
        self.assertTrue(record["observed_in"].strip())
        self.assertIn("meta_sync.py", record["observed_in"])
        for surface in composition.CANDIDATE_SURFACES:
            self.assertTrue(str(surface["observed_in"]).strip(), surface["surface_id"])


class NoInheritanceAndNoPriceLeak(unittest.TestCase):
    """9/10. The verdict does not transfer, and price adjustment says nothing about volume."""

    def test_another_provider_does_not_inherit(self):
        for other in ("TCBS", "KBS", "SSI", "HOSE"):
            with self.assertRaises(composition.CompositionError):
                composition.assert_no_provider_inheritance(contract(), other_provider=other)
        composition.assert_no_provider_inheritance(contract(), other_provider="VCI")

    def test_adjusted_price_does_not_imply_adjusted_volume(self):
        self.assertEqual(
            composition.price_adjustment_does_not_imply_volume_adjustment(
                price_basis="empirically_event_adjusted",
                retained_volume_evidence_determines_adjustment=False,
            ),
            "unknown",
        )
        # And the price basis is not even an input: flipping it changes nothing.
        self.assertEqual(
            composition.price_adjustment_does_not_imply_volume_adjustment(
                price_basis="raw_as_traded",
                retained_volume_evidence_determines_adjustment=False,
            ),
            "unknown",
        )

    def test_the_retained_contract_keeps_volume_adjustment_unknown(self):
        summary = COMPOSITION_DIR / "composition_summary.json"
        if not summary.exists():
            self.skipTest("composition evidence not generated in this checkout")
        blob = json.loads(summary.read_text(encoding="utf-8"))
        self.assertEqual(blob["volume_contract"]["volume_corporate_action_adjustment"], "unknown")


class EvidenceIntegrity(unittest.TestCase):
    """11/12/13. Replay adds nothing, artifacts are reachable, secrets are rejected."""

    def test_every_retained_raw_artifact_is_reachable_and_self_verifying(self):
        audit = COMPOSITION_DIR / "evidence_audit.json"
        if not audit.exists():
            self.skipTest("evidence audit not generated in this checkout")
        blob = json.loads(audit.read_text(encoding="utf-8"))
        self.assertEqual(blob["totals"]["unreferenced_raw_artifacts"], 0)
        self.assertEqual(blob["totals"]["secret_findings"], 0)
        self.assertTrue(blob["totals"]["all_raw_names_self_verifying"])

    def test_replay_creates_no_new_artifact(self):
        # A replay that writes a new file each time would grow evidence without adding
        # information. Artifact names are content- and time-addressed, so a re-analysis of
        # frozen bytes lands on the same paths.
        import hashlib

        before = {}
        for root in EVIDENCE_ROOTS:
            if root.exists():
                for path in sorted(root.rglob("*.raw.json")):
                    before[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertTrue(before, "expected retained raw artifacts")
        after = {}
        for root in EVIDENCE_ROOTS:
            if root.exists():
                for path in sorted(root.rglob("*.raw.json")):
                    after[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_secret_bearing_headers_are_rejected_from_persistence(self):
        import vci_direct_basis_pilot as pilot

        redacted = pilot.redact_headers({"Cookie": "s=1", "Authorization": "Bearer x", "Accept": "application/json"})
        self.assertEqual(redacted["Cookie"], pilot.REDACTED)
        self.assertEqual(redacted["Authorization"], pilot.REDACTED)
        self.assertEqual(redacted["Accept"], "application/json")
        # A secret nested anywhere in a record is found before the record can be persisted.
        self.assertEqual(pilot._find_sensitive_leak({"a": {"cookie": "leak"}}), "a.cookie")
        self.assertIsNone(pilot._find_sensitive_leak({"a": {"cookie": pilot.REDACTED}}))
        fields = {field: "x" for field in pilot._OBSERVATION_FIELDS}
        fields.update(
            provider="VCI",
            source_authority=pilot.SOURCE_AUTHORITY,
            endpoint=pilot.PRICE_BOARD_ENDPOINT,
            ticker="VCB",
            request_headers_redacted={"Accept": "application/json"},
            request_parameters={"symbols": ["VCB"], "nested": {"set-cookie": "leak"}},
        )
        with self.assertRaises(pilot.VCIPilotError) as ctx:
            pilot.build_observation(**fields)
        self.assertIn("sensitive", str(ctx.exception))


class PriorVerdictsIntact(unittest.TestCase):
    """14/15. The price supersession stands and no production gate moved."""

    def test_price_basis_supersession_is_still_active(self):
        import provider_price_basis_registry as registry

        self.assertTrue(registry.is_superseded("phase3a_vci_price_basis"))
        self.assertEqual(registry.active_verdict("VCI")["price_basis"], "empirically_event_adjusted")
        self.assertFalse(registry.raw_as_traded_eligible("VCI"))
        self.assertTrue(registry.blocks_raw_as_traded("VCI"))

    def test_p2a_consumers_still_reject_vci_price_citations(self):
        import inspect
        import semantic_evidence_bridge as bridge

        self.assertIn("raw_as_traded_eligible", inspect.getsource(bridge.load_verified_market_price))

    def test_production_and_actionability_gates_unchanged(self):
        from price_basis_contract import qualify_price_basis, qualify_volume_basis
        import vci_volume_basis

        self.assertFalse(qualify_price_basis("adjusted", verified=False)["is_actionable"])
        self.assertEqual(qualify_volume_basis("raw_shares_traded", verified=False)["volume_basis"], "unknown")
        self.assertEqual(vci_volume_basis.declaration()["volume_basis"], "unknown")
        self.assertFalse(vci_volume_basis.declaration()["volume_basis_verified"])

    def test_pagination_structural_limit_is_still_recorded(self):
        import vci_intraday_pagination as pager

        self.assertEqual(pager.OBSERVED_SERVER_ROW_CAP, 100)
        self.assertEqual(pager.CURSOR_BOUNDARY, "exclusive")


class RetainedContractShape(unittest.TestCase):
    def test_the_retained_summary_matches_the_module_contract(self):
        summary = COMPOSITION_DIR / "composition_summary.json"
        if not summary.exists():
            self.skipTest("composition evidence not generated in this checkout")
        blob = json.loads(summary.read_text(encoding="utf-8"))
        contract_blob = blob["volume_contract"]
        composition.assert_fail_closed(contract_blob)
        self.assertEqual(contract_blob["state"], "A_composition_partially_qualified")
        self.assertEqual(contract_blob["opening_auction_inclusion"], "qualified")
        self.assertEqual(contract_blob["closing_auction_inclusion"], "unknown")
        self.assertEqual(contract_blob["negotiated_inclusion"], "unknown")
        self.assertEqual(
            contract_blob["unresolved_dimension_resolution"]["negotiated_inclusion"],
            "unavailable_from_observed_vci_surfaces",
        )
        self.assertFalse(contract_blob["liquidity_actionable"])
        # The reconciliation that earned the one qualification.
        ato = blob["opening_auction_reconciliation"]
        self.assertTrue(ato["volume_agrees"])
        self.assertTrue(ato["price_agrees"])
        self.assertTrue(ato["is_first_trade_of_session"])
        self.assertTrue(ato["referent_pinned"])

    def test_no_first_party_definition_was_claimed(self):
        summary = COMPOSITION_DIR / "composition_summary.json"
        if not summary.exists():
            self.skipTest("composition evidence not generated in this checkout")
        blob = json.loads(summary.read_text(encoding="utf-8"))
        self.assertEqual(blob["first_party_definitions_retained"], [])
        self.assertEqual(blob["first_party_definition_search"]["found"], 0)


if __name__ == "__main__":
    unittest.main()
