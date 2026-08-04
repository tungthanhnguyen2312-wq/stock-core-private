"""Regression tests for the VCI price-contract supersession and the pagination pilot.

No test here opens a socket. The pagination fixtures are trimmed, real page shapes taken
from the retained artifacts.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import provider_price_basis_registry as registry
import vci_intraday_pagination as pager

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGINATION_DIR = REPO_ROOT / "operations-review" / "vci-intraday-pagination-20260804"


def trade(trade_id, trunc_time, quantity, price=54000.0, accumulated_volume=None, accumulated_value=None):
    row = {
        "vci.raw_trade_id": str(trade_id),
        "vci.raw_trunc_time": int(trunc_time),
        "vci.raw_match_price": float(price),
        "vci.observed_intraday_trade_quantity": int(quantity),
        "vci.raw_match_type": "b",
    }
    if accumulated_volume is not None:
        row["vci.raw_accumulated_volume"] = float(accumulated_volume)
    if accumulated_value is not None:
        row["vci.raw_accumulated_value"] = float(accumulated_value)
    return row


# ---------------------------------------------------------------------------------
# Part A -- the price-contract reconciliation
# ---------------------------------------------------------------------------------


class NoLocalAdjustmentIsNotProviderRaw(unittest.TestCase):
    """1. "No local adjustment" cannot imply provider raw/as-traded."""

    def test_the_inference_is_refused_explicitly(self):
        with self.assertRaises(registry.PriceBasisConflict) as ctx:
            registry.assert_not_conflated(
                local_adjustment_applied=False, provider="VCI", claimed_basis="raw_as_traded"
            )
        self.assertIn("no_local_adjustment_does_not_establish_provider_raw", str(ctx.exception))

    def test_the_legacy_label_alone_never_qualifies_vci(self):
        self.assertEqual(
            registry.LEGACY_NO_LOCAL_ADJUSTMENT_LABEL, "raw_as_quoted_no_adjustment_applied"
        )
        self.assertTrue(registry.blocks_raw_as_traded("VCI"))
        self.assertEqual(
            registry.ineligibility_reason("VCI"), "provider_series_retrospectively_rewritten"
        )

    def test_a_citation_that_passes_every_local_check_is_still_rejected(self):
        import semantic_evidence_bridge as bridge
        import inspect

        source = inspect.getsource(bridge.load_verified_market_price)
        # The provider gate must sit after the local checks, so a citation cannot satisfy
        # the reader by being internally perfect.
        self.assertIn("raw_as_traded_eligible", source)
        self.assertLess(
            source.index("_SUPPORTED_ADJUSTMENT_STATUSES"), source.index("raw_as_traded_eligible")
        )


class SupersededVerdictIsNotActive(unittest.TestCase):
    """2. A superseded price verdict is not read as active."""

    def test_phase3a_is_superseded_and_retained(self):
        self.assertTrue(registry.is_superseded("phase3a_vci_price_basis"))
        record = registry.superseded_verdicts("VCI")[0]
        self.assertEqual(record["status"], "superseded")
        self.assertEqual(record["asserted_value"], registry.LEGACY_NO_LOCAL_ADJUSTMENT_LABEL)
        # Provenance is kept, not deleted.
        self.assertIn("phase3a-qualified-vci-price-benchmark.json", record["asserted_in"][0])
        self.assertTrue(record["superseding_evidence"])
        self.assertEqual(record["root_cause"], "unsupported_assumption_conflating_no_local_adjustment_with_provider_raw")

    def test_the_active_verdict_is_the_new_one(self):
        active = registry.active_verdict("VCI")
        self.assertEqual(active["status"], "active")
        self.assertEqual(active["price_basis"], "empirically_event_adjusted")
        self.assertNotEqual(active["price_basis"], "raw_as_traded")
        self.assertEqual(active["historical_mutability"], "retrospectively_rewritten")
        self.assertEqual(active["provider_methodology"], "unknown")
        self.assertEqual(active["coverage_generalization"], "not_authorized")
        self.assertFalse(active["official_exchange_price"])

    def test_resolve_ignores_superseded_records(self):
        resolved = registry.resolve_active(
            [
                {"status": "superseded", "price_basis": "raw_as_traded"},
                {"status": "active", "price_basis": "empirically_event_adjusted"},
            ]
        )
        self.assertEqual(resolved["price_basis"], "empirically_event_adjusted")

    def test_the_benchmark_generator_no_longer_hardcodes_the_old_value(self):
        import qualified_price_storage_benchmark as benchmark

        self.assertEqual(benchmark.BASIS, "empirically_event_adjusted")
        self.assertNotEqual(benchmark.BASIS, registry.LEGACY_NO_LOCAL_ADJUSTMENT_LABEL)


class ConflictingActiveVerdictsFailClosed(unittest.TestCase):
    """3. Conflicting active verdicts fail closed."""

    def test_two_disagreeing_active_verdicts_do_not_get_a_winner(self):
        records = [
            {"status": "active", "price_basis": "raw_as_traded"},
            {"status": "active", "price_basis": "empirically_event_adjusted"},
        ]
        resolved = registry.resolve_active(records)
        self.assertEqual(resolved["price_basis"], "conflicted")
        self.assertFalse(resolved["raw_as_traded_eligible"])
        self.assertIn("recency_is_not_evidence", resolved["reason"])
        with self.assertRaises(registry.PriceBasisConflict):
            registry.assert_single_active_verdict(records)

    def test_no_verdict_at_all_is_unknown_and_not_eligible_to_claim_raw(self):
        resolved = registry.resolve_active([])
        self.assertEqual(resolved["price_basis"], "unknown")
        self.assertFalse(resolved["raw_as_traded_eligible"])


class RetrospectiveRewritePreventsRawEligibility(unittest.TestCase):
    """4. Retrospective rewrite evidence prevents raw-series eligibility."""

    def test_rewrite_is_the_stated_reason(self):
        self.assertEqual(registry.active_verdict("VCI")["historical_mutability"], "retrospectively_rewritten")
        self.assertFalse(registry.raw_as_traded_eligible("VCI"))

    def test_the_adjustment_factor_path_refuses_an_already_adjusted_reference(self):
        import inspect
        import corporate_action_factors as factors

        source = inspect.getsource(factors)
        self.assertIn("raw_as_traded_eligible", source)

    def test_an_unexamined_provider_is_not_silently_reclassified(self):
        # Fixing VCI must not quietly disable providers this pilot never looked at.
        verdict = registry.active_verdict("SSI")
        self.assertEqual(verdict["status"], "no_established_verdict")
        self.assertIsNone(verdict["raw_as_traded_eligible"])
        self.assertFalse(registry.blocks_raw_as_traded("SSI"))
        self.assertIn("bounded pilot", registry.unexamined_providers_note())


# ---------------------------------------------------------------------------------
# Part B -- pagination
# ---------------------------------------------------------------------------------


class CursorDiscipline(unittest.TestCase):
    """5/6. Cursors must move monotonically; a repeat stops without another request."""

    def test_cursor_must_strictly_decrease(self):
        with self.assertRaises(pager.PaginationError) as ctx:
            pager.assert_cursor_advances(1000, 1000, seen=[])
        self.assertIn("cursor_did_not_advance", str(ctx.exception))
        with self.assertRaises(pager.PaginationError):
            pager.assert_cursor_advances(1000, 1001, seen=[])
        pager.assert_cursor_advances(1000, 999, seen=[])

    def test_a_repeated_cursor_is_rejected(self):
        with self.assertRaises(pager.PaginationError) as ctx:
            pager.assert_cursor_advances(1000, 900, seen=[900, 950])
        self.assertIn("cursor_repeated", str(ctx.exception))

    def test_next_cursor_accounts_for_the_exclusive_boundary(self):
        rows = [trade(1, 500, 100), trade(2, 400, 100)]
        self.assertEqual(pager.oldest_trunc_time(rows), 400)
        # oldest + 1, so the boundary second comes back whole under a `< cursor` filter.
        self.assertEqual(pager.next_cursor(rows), 401)
        self.assertEqual(pager.CURSOR_BOUNDARY, "exclusive")

    def test_a_single_second_page_is_detected(self):
        self.assertTrue(pager.page_is_single_second([trade(1, 400, 10), trade(2, 400, 20)]))
        self.assertFalse(pager.page_is_single_second([trade(1, 400, 10), trade(2, 401, 20)]))
        self.assertEqual(pager.dense_second_escape([trade(1, 400, 10), trade(2, 400, 20)]), 400)


class BoundaryOverlapAndDedup(unittest.TestCase):
    """7/8. Inclusive overlap must not double-count, and lookalike trades must survive."""

    def test_boundary_overlap_is_removed_by_id(self):
        page_one = [trade(1, 500, 100), trade(2, 450, 100)]
        page_two = [trade(2, 450, 100), trade(3, 400, 100)]
        result = pager.dedupe(page_one + page_two)
        self.assertEqual(result["raw_rows"], 4)
        self.assertEqual(result["unique_rows"], 3)
        self.assertEqual(result["duplicate_boundary_rows"], 1)
        self.assertEqual(sum(r["vci.observed_intraday_trade_quantity"] for r in result["rows"]), 300)

    def test_identical_looking_distinct_trades_are_all_kept(self):
        # Same second, same price, same quantity, different trade ids: three real trades.
        rows = [trade(11, 450, 100), trade(12, 450, 100), trade(13, 450, 100)]
        result = pager.dedupe(rows)
        self.assertEqual(result["unique_rows"], 3)
        self.assertEqual(result["duplicate_boundary_rows"], 0)
        self.assertEqual(sum(r["vci.observed_intraday_trade_quantity"] for r in result["rows"]), 300)
        self.assertIn("delete real volume", result["dedup_key_documentation"])

    def test_dedup_without_a_provider_id_fails_closed(self):
        row = trade(1, 450, 100)
        row["vci.raw_trade_id"] = "__index_0"
        with self.assertRaises(pager.PaginationError):
            pager.dedupe([row])


class Completeness(unittest.TestCase):
    """9/10. Cap exhaustion stays incomplete; session-boundary completion is explicit."""

    def rows(self):
        return [
            trade(1, 400, 100, 50000.0, accumulated_volume=100, accumulated_value=5.0),
            trade(2, 450, 200, 50000.0, accumulated_volume=300, accumulated_value=15.0),
        ]

    def test_request_cap_exhaustion_is_incomplete(self):
        result = pager.reconcile_session(
            rows=self.rows(), daily_volume=300, stop_reason="request_cap_reached",
            session_start_confirmed=True, covers_full_trading_day=True,
        )
        self.assertEqual(result["verdict"], "incomplete_request_cap")

    def test_cursor_failure_is_incomplete(self):
        for stop in ("cursor_did_not_advance", "cursor_repeated"):
            result = pager.reconcile_session(
                rows=self.rows(), daily_volume=300, stop_reason=stop,
                session_start_confirmed=True, covers_full_trading_day=True,
            )
            self.assertEqual(result["verdict"], "incomplete_cursor_failure")

    def test_session_boundary_must_be_explicit(self):
        result = pager.reconcile_session(
            rows=self.rows(), daily_volume=300, stop_reason="empty_page",
            session_start_confirmed=False, covers_full_trading_day=True,
        )
        self.assertEqual(result["verdict"], "incomplete_session_boundary_unknown")
        self.assertFalse(result["session_start_boundary_confirmed"])

    def test_a_confirmed_boundary_with_no_gaps_reconciles(self):
        result = pager.reconcile_session(
            rows=self.rows(), daily_volume=300, stop_reason="session_start_boundary_reached",
            session_start_confirmed=True, covers_full_trading_day=True,
        )
        self.assertEqual(result["verdict"], "complete_exact_match")
        self.assertTrue(result["trades_fully_enumerated"])

    def test_a_measured_gap_keeps_the_scan_incomplete(self):
        rows = self.rows()
        # accumulator jumps by 500 while the trade itself is 200: 300 shares never returned.
        rows[1]["vci.raw_accumulated_volume"] = 600.0
        result = pager.reconcile_session(
            rows=rows, daily_volume=600, stop_reason="session_start_boundary_reached",
            session_start_confirmed=True, covers_full_trading_day=True,
        )
        self.assertEqual(result["verdict"], "incomplete_cursor_failure")
        self.assertEqual(result["enumeration"]["unenumerated_quantity_total"], 300)
        self.assertFalse(result["trades_fully_enumerated"])
        # The books still balance once the measured gap is added back.
        self.assertTrue(result["accumulator_closure"]["closes_exactly"])

    def test_segment_completeness_is_not_trading_day_completeness(self):
        result = pager.reconcile_session(
            rows=self.rows(), daily_volume=300, stop_reason="session_start_boundary_reached",
            session_start_confirmed=True, covers_full_trading_day=False,
        )
        contract = pager.volume_contract(reconciliation=result, unit_qualified=True, field_identity_qualified=True)
        self.assertEqual(contract["endpoint_segment_completeness"], "complete")
        self.assertEqual(contract["endpoint_session_completeness"], "incomplete")

    def test_request_cap_is_computed_before_the_run_and_falls_back(self):
        derived = pager.compute_request_cap(expected_session_quantity=1_877_000, mean_trade_quantity=359.0)
        self.assertGreater(derived["cap"], derived["estimated_pages"])
        self.assertEqual(derived["row_cap"], 100)
        fixed = pager.compute_request_cap(expected_session_quantity=None, mean_trade_quantity=None)
        self.assertEqual(fixed["basis"], "fixed_safety_cap_no_supportable_estimate")


class ScopeIsNotReconciliation(unittest.TestCase):
    """11/12/13. Reconciliation and unit qualification never reach market composition."""

    def complete_reconciliation(self):
        rows = [
            trade(1, 400, 100, 50000.0, accumulated_volume=100, accumulated_value=5.0),
            trade(2, 450, 200, 50000.0, accumulated_volume=300, accumulated_value=15.0),
        ]
        return pager.reconcile_session(
            rows=rows, daily_volume=300, stop_reason="session_start_boundary_reached",
            session_start_confirmed=True, covers_full_trading_day=True,
        )

    def test_exact_match_leaves_every_composition_dimension_unknown(self):
        result = self.complete_reconciliation()
        self.assertEqual(result["verdict"], "complete_exact_match")
        contract = pager.volume_contract(
            reconciliation=result, unit_qualified=True, field_identity_qualified=True
        )
        for dimension in ("matched_trade_inclusion", "negotiated_trade_inclusion", "auction_inclusion",
                          "odd_lot_inclusion", "market_scope"):
            self.assertEqual(contract[dimension], "unknown", dimension)
        self.assertEqual(contract["daily_to_intraday_reconciliation"], "exact")
        self.assertFalse(contract["liquidity_actionable"])

    def test_unit_qualification_does_not_qualify_scope(self):
        contract = pager.volume_contract(
            reconciliation=self.complete_reconciliation(), unit_qualified=True, field_identity_qualified=True
        )
        self.assertEqual(contract["volume_unit"], "shares")
        self.assertEqual(contract["market_scope"], "unknown")
        self.assertEqual(contract["corporate_action_adjustment"], "unknown")

    def test_a_leaked_composition_value_is_refused(self):
        contract = pager.volume_contract(
            reconciliation=self.complete_reconciliation(), unit_qualified=True, field_identity_qualified=True
        )
        pager.assert_market_scope_not_upgraded(contract)
        for dimension in ("market_scope", "negotiated_trade_inclusion", "auction_inclusion", "odd_lot_inclusion"):
            leaked = dict(contract)
            leaked[dimension] = "matched_orders_only"
            with self.assertRaises(pager.PaginationError):
                pager.assert_market_scope_not_upgraded(leaked)
        leaked = dict(contract)
        leaked["liquidity_actionable"] = True
        with self.assertRaises(pager.PaginationError):
            pager.assert_market_scope_not_upgraded(leaked)

    def test_upgrade_path_is_named_and_is_not_reconciliation(self):
        contract = pager.volume_contract(
            reconciliation=self.complete_reconciliation(), unit_qualified=True, field_identity_qualified=True
        )
        requirements = " ".join(contract["market_scope_upgrade_requires"])
        self.assertIn("first_party_source_definition", requirements)
        self.assertNotIn("reconciliation", requirements)


class OfflineReplay(unittest.TestCase):
    """14/15. Replay is byte-identical, and no gate moved."""

    def test_retained_run_replays_to_the_recorded_verdict(self):
        summary_path = PAGINATION_DIR / "run-03-vcb-complete-segment" / "pagination_summary.json"
        if not summary_path.exists():
            self.skipTest("pagination evidence not generated in this checkout")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        run = json.loads(
            (PAGINATION_DIR / "run-03-vcb-complete-segment" / "pagination_run.json").read_text(encoding="utf-8")
        )
        pages_dir = PAGINATION_DIR / "run-03-vcb-complete-segment" / "pages"
        for transition in run["transitions"]:
            match = sorted(pages_dir.glob(f"page_{transition['page']:04d}_*.raw.json"))
            self.assertTrue(match, f"missing page {transition['page']}")
            self.assertEqual(pager.page_hash(match[0].read_bytes()), transition["page_sha256"])
        self.assertEqual(summary["reconciliation"]["verdict"], "incomplete_cursor_failure")
        self.assertTrue(summary["reconciliation"]["session_start_boundary_confirmed"])
        self.assertTrue(summary["reconciliation"]["accumulator_closure"]["closes_exactly"])
        self.assertEqual(summary["volume_contract"]["market_scope"], "unknown")
        self.assertFalse(summary["volume_contract"]["liquidity_actionable"])

    def test_production_and_actionability_gates_are_unchanged(self):
        from price_basis_contract import qualify_price_basis, qualify_volume_basis
        import vci_volume_basis

        self.assertFalse(qualify_price_basis("adjusted", verified=False)["is_actionable"])
        self.assertEqual(qualify_volume_basis("raw_shares_traded", verified=False)["volume_basis"], "unknown")
        self.assertEqual(vci_volume_basis.declaration()["volume_basis"], "unknown")
        self.assertFalse(vci_volume_basis.declaration()["volume_basis_verified"])

    def test_no_live_request_is_needed_by_this_module(self):
        import inspect

        self.assertNotIn("import requests", inspect.getsource(pager))
        self.assertNotIn("requests.post", inspect.getsource(pager))


if __name__ == "__main__":
    unittest.main()
