"""Capability-contract proofs for the market-volume and liquidity closeout.

Eighteen required proofs, plus the guards that make them stick. Nothing here touches the
network: the only external thing any test reads is a JSON file already committed at
``63ecc48``, and one test asserts that reading it issues no request.

The organising claim is that every one of the following is true at once, and that no
combination of them adds up to a liquidity permission:

* the provider's own arithmetic closes exactly;
* the unit is shares;
* one opening-auction quantity was demonstrated to sit inside the accumulator.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import analysis_lane_eligibility as lanes
import market_volume_capability_matrix as capability
import official_authority_candidates as candidates
import risk_liquidity
import vci_volume_basis
import vci_volume_composition as composition

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSITION_DIR = REPO_ROOT / "operations-review" / "vci-volume-composition-20260804"


def active():
    return composition.active_contract()


# ---------------------------------------------------------------------------------
# 1-4. What the demonstrated opening-auction leg does and does not carry
# ---------------------------------------------------------------------------------

class OpeningAuctionInclusionIsNarrow(unittest.TestCase):
    """1/2. One observed ATO field is one observed ATO field."""

    def test_opening_auction_inclusion_does_not_imply_general_auction_qualification(self):
        contract = active()
        self.assertEqual(
            contract["opening_auction_inclusion"], "demonstrated_for_observed_ato_field"
        )
        # The roll-up cannot read "qualified" -- it is not a reachable value.
        self.assertEqual(contract["general_auction_composition"], "partially_observed")
        self.assertEqual(contract["auction_inclusion"], "partially_observed")
        self.assertNotEqual(contract["general_auction_composition"], "qualified")
        # And the narrow result is stated at the width it was demonstrated at.
        self.assertEqual(contract["opening_auction_labeled_quantity"], "observed")
        self.assertEqual(
            contract["opening_auction_referent"], "qualified_by_exchange_standard_term"
        )
        self.assertEqual(
            contract["opening_auction_included_in_provider_accumulated_volume"], "demonstrated"
        )

    def test_a_broad_auction_inclusion_field_cannot_be_asserted(self):
        with self.assertRaises(composition.CompositionError):
            composition.composition_contract(
                provider_internal_volume_reconciled=True,
                dimension_verdicts={"auction_inclusion": "qualified"},
                unit="shares",
                corporate_action_adjustment="unknown",
                surfaces_examined=[],
            )

    def test_opening_auction_inclusion_does_not_qualify_the_closing_leg(self):
        contract = active()
        self.assertEqual(contract["closing_auction_inclusion"], "unknown")
        self.assertEqual(contract["auction_inclusion_unresolved_legs"], ["closing_auction_inclusion"])
        # Copying the opening leg's verdict onto the closing leg is refused outright.
        with self.assertRaises(composition.CompositionError):
            composition.composition_contract(
                provider_internal_volume_reconciled=True,
                dimension_verdicts={"closing_auction_inclusion": "qualified"},
                unit="shares",
                corporate_action_adjustment="unknown",
                surfaces_examined=[],
            )
        leaked = dict(contract)
        leaked["closing_auction_inclusion"] = "demonstrated_for_observed_ato_field"
        with self.assertRaises(composition.CompositionError):
            composition.assert_canonical_vocabulary(leaked)


class ReconciliationIsNotComposition(unittest.TestCase):
    """3/4. Internal arithmetic, and partial observation, unlock nothing."""

    def test_provider_internal_reconciliation_does_not_qualify_market_composition(self):
        contract = active()
        self.assertTrue(contract["provider_internal_volume_reconciled"])
        self.assertEqual(contract["volume_unit"], "shares")
        self.assertEqual(contract["volume_field_identity"], "qualified")
        for dimension in ("matched_trade_inclusion", "negotiated_inclusion", "odd_lot_inclusion"):
            self.assertEqual(contract[dimension], "unavailable_from_observed_vci_surfaces", dimension)
        self.assertEqual(contract["overall_market_scope"], "partially_observed_but_not_qualified")

    def test_partially_observed_composition_cannot_enable_liquidity_actionability(self):
        contract = active()
        self.assertFalse(contract["liquidity_actionable"])
        self.assertEqual(composition.liquidity_eligibility(contract)["available"], [])
        leaked = dict(contract)
        leaked["liquidity_actionable"] = True
        with self.assertRaises(composition.CompositionError):
            composition.assert_canonical_vocabulary(leaked)

    def test_the_superseded_word_cannot_re_enter_an_active_contract(self):
        leaked = dict(active())
        leaked["market_scope"] = "partially_qualified"
        leaked["overall_market_scope"] = "partially_qualified"
        # Still safe -- but no longer canonical, and refused as active.
        composition.assert_fail_closed(leaked)
        with self.assertRaises(composition.CompositionError):
            composition.assert_canonical_vocabulary(leaked)


# ---------------------------------------------------------------------------------
# 5-9. What survives, and what does not
# ---------------------------------------------------------------------------------

class DescriptiveCapabilitiesSurvive(unittest.TestCase):
    """5. Descriptive volume history stays available under the VCI namespace."""

    def test_descriptive_volume_history_remains_available(self):
        for name in (
            "provider_volume_history_display",
            "provider_volume_moving_average",
            "provider_relative_volume",
            "provider_volume_trend_indicator",
            "provider_volume_anomaly_detection",
        ):
            decision = capability.evaluate(name, provider="VCI", existing_gates_passed=True)
            self.assertTrue(decision["available"], name)
            self.assertEqual(decision["capability_class"], capability.CLASS_DESCRIPTIVE, name)
            self.assertEqual(decision["namespace"], "provider_scoped", name)
            for warning in capability.DESCRIPTIVE_WARNINGS:
                self.assertIn(warning, decision["required_warnings"], f"{name}:{warning}")

    def test_a_descriptive_capability_still_answers_to_its_own_gates(self):
        decision = capability.evaluate(
            "provider_volume_history_display", provider="VCI", existing_gates_passed=False
        )
        self.assertFalse(decision["available"])
        self.assertEqual(decision["blocked_by"], "existing_freshness_or_provenance_gate")

    def test_the_average_volume_consumer_still_computes(self):
        """The one live descriptive consumer keeps working -- with its labels attached."""
        rows = [{"close": 10, "volume": 100}, {"close": 11, "volume": 200}, {"close": 9, "volume": 300}]
        result = risk_liquidity.evaluate_market_risk(
            {"price_adjustment": "qualified", "volume_units": "qualified", "ohlcv": rows}
        )
        average = result["liquidity_risk"]["average_volume"]
        self.assertEqual(average["state"], "available")
        self.assertEqual(average["value"], 200.0)
        self.assertEqual(average["source"], "VCI")
        self.assertFalse(average["is_actionable"])
        for warning in capability.DESCRIPTIVE_WARNINGS:
            self.assertIn(warning, average["warnings"])


class LiquidityAndExecutionAreUnavailableByContract(unittest.TestCase):
    """6/7/8. Terminal, not pending."""

    def _assert_terminal(self, name: str):
        decision = capability.evaluate(name, provider="VCI", existing_gates_passed=True)
        self.assertFalse(decision["available"], name)
        self.assertEqual(decision["availability"], "unavailable_by_contract", name)
        self.assertEqual(decision["reason"], "complete_market_composition_not_qualified", name)
        self.assertEqual(decision["reopen_condition"], "new_authoritative_source_contract", name)
        # The reopen condition must not read as "paginate VCI once more".
        self.assertIn("Not reopenable by further VCI pagination", decision["reopen_note"])
        return decision

    def test_average_volume_cannot_be_used_for_days_to_liquidate(self):
        self._assert_terminal("days_to_liquidate")
        self._assert_terminal("average_daily_volume_portfolio_sizing")
        # And the live consumer says so rather than listing inputs it wants.
        result = risk_liquidity.evaluate_market_risk(
            {"price_adjustment": "qualified", "volume_units": "qualified",
             "ohlcv": [{"close": 10, "volume": 100}, {"close": 11, "volume": 200}, {"close": 9, "volume": 300}]}
        )
        dtl = result["liquidity_risk"]["days_to_liquidate"]
        self.assertEqual(dtl["state"], "unavailable")
        self.assertEqual(dtl["availability"], "unavailable_by_contract")
        self.assertEqual(dtl["reason"], "complete_market_composition_not_qualified")
        self.assertEqual(dtl["reopen_condition"], "new_authoritative_source_contract")
        self.assertEqual(dtl["missing_inputs"], [], "a terminal refusal must not offer a shopping list")
        # Even with a qualified average volume sitting beside it.
        self.assertEqual(result["liquidity_risk"]["average_volume"]["state"], "available")

    def test_participation_rate_sizing_remains_unavailable(self):
        self._assert_terminal("participation_rate_sizing")
        self._assert_terminal("liquidity_adjusted_position_sizing")
        self._assert_terminal("execution_simulation")
        self._assert_terminal("production_backtest_liquidity_constraint")

    def test_market_impact_calculations_remain_unavailable(self):
        self._assert_terminal("market_impact_estimation")
        self._assert_terminal("capacity_estimation")

    def test_no_input_opens_a_contract_unavailable_capability(self):
        for gates in (True, False):
            for provider in ("VCI", "KBS", "SSI"):
                decision = capability.evaluate(
                    "days_to_liquidate", provider=provider, existing_gates_passed=gates
                )
                self.assertFalse(decision["available"])
                self.assertFalse(decision["liquidity_actionable"])

    def test_every_liquidity_and_execution_capability_is_shut(self):
        snapshot = capability.assert_matrix_fail_closed()
        for klass in (capability.CLASS_LIQUIDITY, capability.CLASS_EXECUTION):
            names = capability.capabilities_in_class(klass)
            self.assertTrue(names, klass)
            for name in names:
                self.assertEqual(
                    snapshot["capabilities"][name]["availability"], "unavailable_by_contract", name
                )

    def test_an_opened_liquidity_capability_is_refused(self):
        snapshot = json.loads(json.dumps(capability.matrix_snapshot()))
        snapshot["capabilities"]["days_to_liquidate"]["availability"] = "available_under_existing_gates"
        with self.assertRaises(capability.CapabilityError):
            capability.assert_matrix_fail_closed(snapshot)


class RelativeVolumeIsNotLiquidity(unittest.TestCase):
    """9. A technical reading may not be presented as official liquidity."""

    def test_relative_volume_is_descriptive_not_liquidity(self):
        decision = capability.evaluate("provider_relative_volume", existing_gates_passed=True)
        self.assertEqual(decision["capability_class"], capability.CLASS_DESCRIPTIVE)
        self.assertNotIn(decision["capability_class"], (capability.CLASS_LIQUIDITY, capability.CLASS_EXECUTION))
        self.assertIn("not_an_official_exchange_volume_contract", decision["required_warnings"])
        self.assertIn("value_is_provider_scoped", decision["required_warnings"])
        self.assertFalse(decision["liquidity_actionable"])

    def test_research_indicators_are_analytical_and_carry_the_same_warnings(self):
        for name in ("research_only_volume_technical_indicator", "volume_confirmation_signal",
                     "turnover_tier_screening_score"):
            decision = capability.evaluate(name, existing_gates_passed=True)
            self.assertEqual(decision["capability_class"], capability.CLASS_ANALYTICAL, name)
            self.assertFalse(decision["liquidity_actionable"], name)
            for warning in capability.DESCRIPTIVE_WARNINGS:
                self.assertIn(warning, decision["required_warnings"], f"{name}:{warning}")

    def test_ranking_on_volume_as_market_liquidity_is_unavailable(self):
        decision = capability.evaluate("volume_based_ranking_or_recommendation")
        self.assertEqual(decision["availability"], "unavailable_by_contract")
        self.assertEqual(decision["capability_class"], capability.CLASS_LIQUIDITY)


# ---------------------------------------------------------------------------------
# 10-13. Inheritance, ambiguity and probing
# ---------------------------------------------------------------------------------

class NothingInherits(unittest.TestCase):
    """10/11. Not a generic field, not another provider."""

    def test_generic_market_volume_fields_are_not_upgraded(self):
        for field in ("volume", "market_volume", "total_volume", "official_exchange_volume",
                      "matched_volume", "exchange_volume", "traded_volume"):
            with self.assertRaises(capability.CapabilityError, msg=field):
                capability.assert_no_generic_field_upgrade(field)
            with self.assertRaises(capability.CapabilityError, msg=field):
                capability.evaluate(
                    "provider_volume_history_display", field_name=field, existing_gates_passed=True
                )

    def test_a_provider_namespaced_field_is_accepted(self):
        capability.assert_no_generic_field_upgrade("vci_volume")
        decision = capability.evaluate(
            "provider_volume_history_display", field_name="vci_volume", existing_gates_passed=True
        )
        self.assertTrue(decision["available"])

    def test_other_providers_do_not_inherit_the_vci_contract(self):
        for provider in ("KBS", "SSI", "EODHD", "VNSTOCK"):
            scope = capability.provider_scope(provider)
            self.assertFalse(scope["contract_applies"], provider)
            self.assertEqual(scope["volume_composition"], "unknown", provider)
            self.assertEqual(scope["reason"], "vci_composition_verdict_does_not_transfer", provider)
            with self.assertRaises(composition.CompositionError):
                composition.assert_no_provider_inheritance(active(), other_provider=provider)
            # A descriptive capability is not open for them either -- they have no closeout.
            decision = capability.evaluate(
                "provider_volume_history_display", provider=provider, existing_gates_passed=True
            )
            self.assertFalse(decision["available"], provider)
            self.assertEqual(decision["availability"], "unavailable_pending_classification", provider)

    def test_the_contract_belongs_to_vci(self):
        composition.assert_no_provider_inheritance(active(), other_provider="vci")
        leaked = dict(active())
        leaked["provider"] = "KBS"
        with self.assertRaises(composition.CompositionError):
            composition.assert_canonical_vocabulary(leaked)


class UnknownConsumersFailClosed(unittest.TestCase):
    """12. A consumer nobody classified is refused."""

    def test_an_unregistered_consumer_is_unavailable(self):
        for consumer_id in ("some_new_module.volume_thing", "", "risk_liquidity.not_a_real_metric"):
            result = capability.classify_consumer(consumer_id)
            self.assertEqual(result["capability_class"], capability.CLASS_UNKNOWN, consumer_id)
            self.assertEqual(result["availability"], "unavailable_pending_classification", consumer_id)

    def test_an_unregistered_capability_name_raises(self):
        with self.assertRaises(capability.CapabilityError):
            capability.capability("slippage_model")
        with self.assertRaises(capability.CapabilityError):
            capability.evaluate("slippage_model")

    def test_registered_consumers_resolve_to_their_class(self):
        self.assertEqual(
            capability.classify_consumer("risk_liquidity.days_to_liquidate")["availability"],
            "unavailable_by_contract",
        )
        self.assertEqual(
            capability.classify_consumer("risk_liquidity.average_volume")["availability"],
            "available_under_existing_gates",
        )
        self.assertEqual(
            capability.classify_consumer("vnm_shadow_backtest")["availability"],
            "unavailable_by_contract",
        )

    def test_every_classified_consumer_uses_a_known_class(self):
        for consumer_id, klass in capability.CONSUMER_CLASSIFICATION.items():
            self.assertIn(klass, capability.CAPABILITY_CLASSES, consumer_id)
            self.assertNotEqual(klass, capability.CLASS_UNKNOWN, consumer_id)

    def test_the_lane_gate_refuses_liquidity_even_on_a_verified_basis(self):
        """The regression this milestone exists to prevent.

        Gate 1's basis warning lifts when the basis verifies. If that were the only
        liquidity gate, verifying the volume basis -- which the shares finding invites --
        would silently open liquidity claims. The contract warning does not lift."""
        verified = {
            "price_basis": "adjusted", "price_basis_verified": True,
            "volume_basis": "raw_shares_traded", "volume_basis_verified": True,
        }
        warnings = lanes._price_volume_basis_warnings(verified, "TEST")
        self.assertNotIn("liquidity_claims_blocked", " ".join(warnings))
        self.assertIn(lanes.LIQUIDITY_CONTRACT_WARNING, warnings)
        self.assertIn("complete_market_composition_not_qualified", lanes.LIQUIDITY_CONTRACT_WARNING)
        for provenance in (None, {}, {"volume_basis": "unknown", "volume_basis_verified": False}):
            self.assertIn(
                lanes.LIQUIDITY_CONTRACT_WARNING,
                lanes._price_volume_basis_warnings(provenance, "TEST"),
            )

    def test_a_verified_volume_basis_does_not_grant_liquidity_activation(self):
        validated = vci_volume_basis.validate_forward({
            "provider": "VCI",
            "raw_volume_field": "v",
            "raw_volume_alias_field": "accumulatedVolume",
            "volume_basis": "raw_shares_traded",
            "volume_basis_verified": True,
            "basis_evidence_id": "hypothetical",
        })
        self.assertFalse(validated["liquidity_activation_permitted"])
        self.assertEqual(validated["liquidity_block_reason"], "complete_market_composition_not_qualified")
        declaration = vci_volume_basis.declaration()
        self.assertEqual(
            declaration["forward_gate"]["action"], "block_liquidity_activation_unconditionally"
        )
        self.assertFalse(declaration["forward_gate"]["liquidity_activation_permitted"])
        # The unit finding is recorded without pretending the basis is verified.
        self.assertEqual(declaration["observed_volume_unit"], "shares")
        self.assertFalse(declaration["volume_basis_verified"])


class ProbingRemainsClosed(unittest.TestCase):
    """13. Pagination and endpoint probing stay unauthorized."""

    def test_pagination_and_endpoint_probing_are_unauthorized(self):
        self.assertFalse(composition.FURTHER_PAGINATION_AUTHORIZED)
        self.assertFalse(composition.FURTHER_SPECULATIVE_ENDPOINT_PROBE_AUTHORIZED)
        contract = active()
        self.assertFalse(contract["further_vci_pagination_authorized"])
        self.assertFalse(contract["further_vci_endpoint_probe_authorized"])
        self.assertFalse(contract["further_speculative_endpoint_probe_authorized"])
        for key in ("further_vci_pagination_authorized", "further_vci_endpoint_probe_authorized",
                    "further_speculative_endpoint_probe_authorized"):
            leaked = dict(contract)
            leaked[key] = True
            with self.assertRaises(composition.CompositionError, msg=key):
                composition.assert_fail_closed(leaked)

    def test_the_capability_matrix_carries_the_same_refusal(self):
        snapshot = capability.assert_matrix_fail_closed()
        self.assertFalse(snapshot["further_vci_pagination_authorized"])
        self.assertFalse(snapshot["further_vci_endpoint_probe_authorized"])
        opened = json.loads(json.dumps(snapshot))
        opened["further_vci_endpoint_probe_authorized"] = True
        with self.assertRaises(capability.CapabilityError):
            capability.assert_matrix_fail_closed(opened)


# ---------------------------------------------------------------------------------
# 14-15. The future official candidate
# ---------------------------------------------------------------------------------

class HoseIsACandidateOnly(unittest.TestCase):
    """14/15. Registered, unacquired, and incapable of issuing a request."""

    def test_hose_is_registered_only_as_a_future_qualification_candidate(self):
        record = candidates.candidate("hose_trading_statistics")
        candidates.assert_candidate_only(record)
        self.assertEqual(record["source"], "HOSE")
        self.assertEqual(record["authority"], "official_exchange")
        self.assertEqual(record["status"], "future_qualification_candidate")
        self.assertFalse(record["automatic_acquisition_authorized"])
        self.assertEqual(record["acquisition_state"], "nothing_acquired")
        self.assertEqual(candidates.active_sources(), ())
        self.assertEqual(candidates.registry_snapshot()["active_market_composition_sources"], [])

    def test_the_eight_semantic_questions_are_recorded_and_open(self):
        record = candidates.candidate("hose_trading_statistics")
        self.assertEqual(
            list(record["candidate_questions"]),
            [
                "matched volume definition",
                "negotiated volume definition",
                "relationship between matched and total volume",
                "units and scaling",
                "ticker-level availability",
                "date coverage",
                "machine-readable access",
                "access and reuse terms",
            ],
        )

    def test_hose_is_the_preferred_path_not_the_sole_possible_authority(self):
        record = candidates.candidate("hose_trading_statistics")
        self.assertEqual(
            record["authority_position"], "preferred_currently_identified_official_authority_path"
        )
        blob = json.dumps(candidates.registry_snapshot()).lower()
        for overclaim in ("sole authority", "only authority", "only possible", "sole possible"):
            self.assertNotIn(overclaim, blob)

    def test_no_url_or_api_route_is_fabricated(self):
        record = candidates.candidate("hose_trading_statistics")
        self.assertIsNone(record["locator"])
        for forbidden in ("url", "endpoint", "host", "api_route", "path"):
            self.assertNotIn(forbidden, record, forbidden)
        blob = json.dumps(candidates.registry_snapshot())
        for scheme in ("http://", "https://", "www.", ".vn/"):
            self.assertNotIn(scheme, blob, scheme)

    def test_a_candidate_that_drifts_towards_a_source_is_refused(self):
        for mutation in (
            {"status": "active_qualified_source"},
            {"automatic_acquisition_authorized": True},
            {"acquisition_state": "downloaded"},
            {"locator": "somewhere"},
            {"url": "somewhere"},
            {"authority_position": "sole_possible_authority"},
        ):
            drifted = dict(candidates.candidate("hose_trading_statistics"))
            drifted.update(mutation)
            with self.assertRaises(candidates.AuthorityCandidateError, msg=str(mutation)):
                candidates.assert_candidate_only(drifted)

    def test_candidate_registration_causes_no_network_request(self):
        """Proved structurally, not by watching for traffic.

        Every socket-opening entry point is monkeypatched to raise for the duration of the
        registration path. A request would surface as an error, not as an assertion about
        what was observed."""
        import socket
        import urllib.request

        calls: list[str] = []

        def refuse(*args, **kwargs):  # pragma: no cover - must never run
            calls.append("called")
            raise AssertionError("candidate registration attempted a network call")

        originals = {
            (socket.socket, "connect"): socket.socket.connect,
            (socket, "create_connection"): socket.create_connection,
            (urllib.request, "urlopen"): urllib.request.urlopen,
        }
        socket.socket.connect = refuse  # type: ignore[method-assign]
        socket.create_connection = refuse  # type: ignore[assignment]
        urllib.request.urlopen = refuse  # type: ignore[assignment]
        try:
            record = candidates.candidate("hose_trading_statistics")
            candidates.assert_candidate_only(record)
            snapshot = candidates.registry_snapshot()
            verdict = candidates.assert_not_acquirable()
        finally:
            socket.socket.connect = originals[(socket.socket, "connect")]  # type: ignore[method-assign]
            socket.create_connection = originals[(socket, "create_connection")]  # type: ignore[assignment]
            urllib.request.urlopen = originals[(urllib.request, "urlopen")]  # type: ignore[assignment]

        self.assertEqual(calls, [])
        self.assertEqual(verdict["requests_issued"], 0)
        self.assertFalse(verdict["acquirable"])
        self.assertTrue(snapshot["candidates"])

    def test_the_network_registry_cannot_admit_trading_statistics(self):
        verdict = candidates.assert_not_acquirable()
        self.assertIn("hose", verdict["checked_sources"])
        self.assertFalse(verdict["acquirable"])

    def test_adding_a_trading_statistics_document_type_to_an_approved_source_fails(self):
        import official_source_registry as sources

        registry = json.loads(json.dumps(sources.load_registry()))
        for source in registry["sources"]:
            if source["source_id"] == "hose":
                source["document_types"].append("matched_order_trading_statistics")
        with self.assertRaises(candidates.AuthorityCandidateError):
            candidates.assert_not_acquirable(registry)


# ---------------------------------------------------------------------------------
# 16-18. Non-effects
# ---------------------------------------------------------------------------------

class PriceAndProductionAreUntouched(unittest.TestCase):
    """16/17/18. Nothing here moved the price supersession, P2a, or actionability."""

    def test_the_vci_price_supersession_remains_active(self):
        import provider_price_basis_registry as registry

        self.assertTrue(registry.is_superseded("phase3a_vci_price_basis"))
        verdict = registry.active_verdict("VCI")
        self.assertEqual(verdict["price_basis"], "empirically_event_adjusted")
        self.assertEqual(verdict["historical_mutability"], "retrospectively_rewritten")
        self.assertFalse(verdict["official_exchange_price"])

    def test_p2a_remains_blocked(self):
        import provider_price_basis_registry as registry

        self.assertFalse(registry.raw_as_traded_eligible("VCI"))
        self.assertTrue(registry.blocks_raw_as_traded("VCI"))
        self.assertEqual(
            registry.ineligibility_reason("VCI"), "provider_series_retrospectively_rewritten"
        )

    def test_the_volume_closeout_did_not_touch_the_price_gates(self):
        from price_basis_contract import qualify_price_basis, qualify_volume_basis

        self.assertFalse(qualify_price_basis("adjusted", verified=False)["is_actionable"])
        self.assertEqual(
            qualify_volume_basis("raw_shares_traded", verified=False)["volume_basis"], "unknown"
        )
        self.assertEqual(vci_volume_basis.declaration()["volume_basis"], "unknown")

    def test_a_price_finding_is_not_a_volume_adjustment_finding(self):
        for price_basis in ("raw_as_quoted", "empirically_event_adjusted", "unknown"):
            self.assertEqual(
                composition.price_adjustment_does_not_imply_volume_adjustment(
                    price_basis=price_basis, retained_volume_evidence_determines_adjustment=False
                ),
                "unknown",
            )
        self.assertEqual(active()["volume_corporate_action_adjustment"], "unknown")

    def test_production_is_actionable_is_unchanged_by_any_volume_finding(self):
        rows = [{"close": 10, "volume": 100}, {"close": 11, "volume": 200}, {"close": 9, "volume": 300}]
        result = risk_liquidity.evaluate_market_risk(
            {"price_adjustment": "qualified", "volume_units": "qualified", "ohlcv": rows,
             "current_actionable": False}
        )
        self.assertFalse(result["liquidity_risk"]["average_volume"]["is_actionable"])
        self.assertFalse(result["position_sizing"]["is_actionable"])
        self.assertEqual(result["dimensions"]["position_sizing_readiness"], "unavailable")
        self.assertEqual(result["dimensions"]["liquidity"], "unavailable_by_contract")
        # Descriptive volume is reported under its own dimension, not as liquidity.
        self.assertEqual(result["dimensions"]["descriptive_provider_volume"], "available")
        self.assertEqual(
            capability.evaluate("volume_derived_actionability_upgrade")["availability"],
            "unavailable_by_contract",
        )


class EvidenceIsNotRewritten(unittest.TestCase):
    """The frozen artifact keeps its own words, and is recorded as superseded."""

    def test_the_retained_artifact_still_uses_its_original_vocabulary(self):
        summary = COMPOSITION_DIR / "composition_summary.json"
        if not summary.exists():
            self.skipTest("composition evidence not generated in this checkout")
        blob = json.loads(summary.read_text(encoding="utf-8"))["volume_contract"]
        # Unchanged, and still safe.
        self.assertEqual(blob["market_scope"], "partially_qualified")
        composition.assert_fail_closed(blob)
        # But not admissible as an active contract.
        with self.assertRaises(composition.CompositionError):
            composition.assert_canonical_vocabulary(blob)

    def test_the_active_contract_names_what_it_supersedes(self):
        supersedes = active()["supersedes"]
        self.assertEqual(supersedes["commit"], "63ecc48")
        self.assertEqual(supersedes["vocabulary"], "partially_qualified")
        self.assertFalse(supersedes["evidence_changed"])
        self.assertTrue((COMPOSITION_DIR / supersedes["path"].split("/")[-1]).exists()
                        or not COMPOSITION_DIR.exists())

    def test_the_dimension_verdicts_did_not_move_only_their_wording(self):
        summary = COMPOSITION_DIR / "composition_summary.json"
        if not summary.exists():
            self.skipTest("composition evidence not generated in this checkout")
        old = json.loads(summary.read_text(encoding="utf-8"))["volume_contract"]
        new = active()
        # The three closed dimensions were already resolved as unavailable in the sidecar;
        # this milestone promoted that resolution to the top-level verdict. Same finding.
        for dimension in ("matched_trade_inclusion", "negotiated_inclusion", "odd_lot_inclusion"):
            self.assertEqual(old[dimension], "unknown", dimension)
            self.assertEqual(
                old["unresolved_dimension_resolution"][dimension],
                "unavailable_from_observed_vci_surfaces",
                dimension,
            )
            self.assertEqual(new[dimension], "unavailable_from_observed_vci_surfaces", dimension)
        self.assertEqual(old["closing_auction_inclusion"], new["closing_auction_inclusion"])
        self.assertEqual(old["volume_unit"], new["volume_unit"])
        self.assertEqual(
            old["volume_corporate_action_adjustment"], new["volume_corporate_action_adjustment"]
        )
        self.assertEqual(old["liquidity_actionable"], new["liquidity_actionable"])


if __name__ == "__main__":
    unittest.main()
