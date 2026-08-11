"""current_state_relative_valuation.py: current DNSE price x official-evidence
current shares against qualified historical financial denominators.

Covers: the price/share adapters in isolation (real JSONL-shaped fixtures, no
mocking of the parsing logic itself), the full metric-computation formulas with
synthetic qualified inputs (mocking only the two external resolvers), every
fail-closed path, the historical-comparability logic, and one real-evidence
integration test against the actual runtime root that locks in today's real,
evidenced blocker so a future change cannot silently "fix" it without a human
noticing.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_state_relative_valuation as m  # noqa: E402
from share_transition_bridge import resolve_share_transition  # noqa: E402

RUNTIME_ROOT = ROOT.parent / "dashboard-runtime"
REAL_SHARE_BASIS_PATH = RUNTIME_ROOT / m._SHARE_BASIS_RELATIVE


def _financial_record(metric: str, value, *, period="2024", scope="consolidated",
                      period_type="annual", quality_state="available") -> dict:
    return {
        "canonical_metric": metric, "value": value, "quality_state": quality_state,
        "statement_scope": scope, "period_identity": {"period": period, "period_type": period_type},
    }


def _qualified_financial(**overrides) -> dict:
    base = {
        "net_income": _financial_record("net_income", 12_000_000_000_000),
        "shareholders_equity": _financial_record("shareholders_equity", 114_000_000_000_000),
        "revenue": _financial_record("revenue", 138_000_000_000_000),
        "ebitda": _financial_record("ebitda", 22_000_000_000_000),
        "total_debt": _financial_record("total_debt", 83_000_000_000_000),
        "cash_and_equivalents": _financial_record("cash_and_equivalents", 6_800_000_000_000),
    }
    base.update(overrides)
    return base


def _qualified_price(*, value_vnd=22_000_000, as_of_session="2026-08-07") -> dict:
    return {
        "qualified": True, "as_of_session": as_of_session, "status": m.DNSE_PRICE_STATUS_QUALIFIED,
        "coverage": {"status": "complete"}, "eligibility": {"eligible_for_current_state_price_analytics": True},
        "price_basis": "ADJUSTED_CONFIRMED", "price_basis_contract_version": "v1", "source": "DNSE",
        "analysis_time_semantics": m.AS_OF_SEMANTICS, "pit_backtest_eligible": False,
        "provenance": {}, "warnings": [], "raw_close": value_vnd / m.PRICE_UNIT_TO_VND,
        "price_unit": m.PRICE_UNIT, "value_vnd": value_vnd,
    }


def _not_qualified_price(*, as_of_session=None, status="NOT_QUALIFIED_FOR_DNSE_PRICE_ANALYTICS") -> dict:
    return {
        "qualified": False, "as_of_session": as_of_session, "status": status,
        "coverage": {"status": "not_qualified"}, "eligibility": {"eligible_for_current_state_price_analytics": False},
        "price_basis": None, "price_basis_contract_version": None, "source": "DNSE",
        "analysis_time_semantics": None, "pit_backtest_eligible": None, "provenance": {}, "warnings": [],
        "raw_close": None, "price_unit": m.PRICE_UNIT, "value_vnd": None,
    }


def _qualified_shares(*, value=8_442_964_520, target_date="2026-08-07") -> dict:
    bridge = resolve_share_transition(
        {"value": 7_675_465_852, "effective_date": "2024-12-31", "unit": "shares",
         "share_class": "common_outstanding", "identity_scope": "issuer", "qualification": "qualified",
         "source_hash": "opening-hash", "citation_id": "opening-citation"},
        [{"event_id": "e1", "action_type": "stock_dividend", "lifecycle": "completed",
          "effective_date": "2026-07-02", "opening_shares": None, "resulting_shares": value,
          "resulting_identity_type": "common_outstanding_shares", "unit": "shares",
          "identity_scope": "issuer", "ratio": 0.0999937567, "qualification": "qualified",
          "source_hash": "event-hash", "citation_id": "event-citation"}],
        target_date=target_date, coverage_through=target_date,
    )
    return {"bridge_result": bridge, "opening_identity": {"value": 7_675_465_852, "effective_date": "2024-12-31"},
            "opening_identity_diagnostic": None, "coverage_through": target_date,
            "raw_event_citation_count": 1, "mapped_event_count": 1, "target_date": target_date}


def _not_qualified_shares(*, target_date="2026-08-07", coverage_through="2026-07-30") -> dict:
    bridge = resolve_share_transition(
        {"value": 7_675_465_852, "effective_date": "2024-12-31", "unit": "shares",
         "share_class": "common_outstanding", "identity_scope": "issuer", "qualification": "qualified",
         "source_hash": "opening-hash", "citation_id": "opening-citation"},
        [{"event_id": "e1", "action_type": "stock_dividend", "lifecycle": "completed",
          "effective_date": "2026-07-02", "opening_shares": None, "resulting_shares": 8_442_964_520,
          "resulting_identity_type": "common_outstanding_shares", "unit": "shares",
          "identity_scope": "issuer", "ratio": 0.0999937567, "qualification": "qualified",
          "source_hash": "event-hash", "citation_id": "event-citation"}],
        target_date=target_date, coverage_through=coverage_through,
    )
    return {"bridge_result": bridge, "opening_identity": {"value": 7_675_465_852, "effective_date": "2024-12-31"},
            "opening_identity_diagnostic": None, "coverage_through": coverage_through,
            "raw_event_citation_count": 1, "mapped_event_count": 1, "target_date": target_date}


def _blocked_shares(*, target_date="2026-08-07") -> dict:
    bridge = resolve_share_transition({}, [], target_date=target_date, coverage_through=target_date)
    return {"bridge_result": bridge, "opening_identity": None,
            "opening_identity_diagnostic": {"reason": "official_evidence_share_basis_unverifiable",
                                            "detail": "evidence_missing_or_hash_mismatch", "note": "..."},
            "coverage_through": target_date, "raw_event_citation_count": 0, "mapped_event_count": 0,
            "target_date": target_date}


class EventRowMappingTests(unittest.TestCase):
    """_map_event_row_to_bridge_event: real JSONL-shaped rows, no mocking."""

    def _row(self, **overrides) -> dict:
        row = {
            "ticker": "HPG", "identity_type": "current_shares_outstanding_after_event",
            "event_id": "b7a97e12", "effective_date": "2026-07-02", "event_type": "stock_dividend",
            "value": 8442964520, "citation_id": "984a47fe", "source_content_hashes": ["cb41c96e"],
            "share_class": "common_outstanding", "unit": "shares",
        }
        row.update(overrides)
        return row

    def test_valid_row_maps_completely(self):
        mapped = m._map_event_row_to_bridge_event(self._row())
        self.assertEqual("b7a97e12", mapped["event_id"])
        self.assertEqual("stock_dividend", mapped["action_type"])
        self.assertEqual("completed", mapped["lifecycle"])
        self.assertEqual(8442964520, mapped["resulting_shares"])
        self.assertEqual("common_outstanding_shares", mapped["resulting_identity_type"])
        self.assertEqual("cb41c96e", mapped["source_hash"])
        self.assertIsNone(mapped["opening_shares"])

    def test_missing_required_field_returns_none(self):
        row = self._row()
        del row["citation_id"]
        self.assertIsNone(m._map_event_row_to_bridge_event(row))

    def test_non_positive_value_returns_none(self):
        self.assertIsNone(m._map_event_row_to_bridge_event(self._row(value=0)))
        self.assertIsNone(m._map_event_row_to_bridge_event(self._row(value=-5)))

    def test_empty_source_hashes_returns_none(self):
        self.assertIsNone(m._map_event_row_to_bridge_event(self._row(source_content_hashes=[])))

    def test_wrong_share_class_yields_no_resulting_identity_type(self):
        mapped = m._map_event_row_to_bridge_event(self._row(share_class="issued"))
        self.assertIsNotNone(mapped)
        self.assertIsNone(mapped["resulting_identity_type"])


class CoverageThroughTests(unittest.TestCase):
    def test_uses_latest_corroborated_on(self):
        rows = [{"corroborated_on": "2026-07-30"}, {"corroborated_on": "2026-06-01"}]
        self.assertEqual("2026-07-30", m._resolve_coverage_through(rows, "2024-12-31"))

    def test_falls_back_to_opening_when_no_corroboration(self):
        self.assertEqual("2024-12-31", m._resolve_coverage_through([{}], "2024-12-31"))

    def test_ignores_malformed_corroborated_on(self):
        rows = [{"corroborated_on": None}, {"corroborated_on": 12345}]
        self.assertEqual("2024-12-31", m._resolve_coverage_through(rows, "2024-12-31"))


class LoadShareBasisEventRowsTests(unittest.TestCase):
    """_load_share_basis_event_rows against a real temp JSONL file."""

    def test_reads_only_matching_ticker_and_identity_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / m._SHARE_BASIS_RELATIVE
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {"ticker": "HPG", "identity_type": "current_shares_outstanding_after_event", "value": 1},
                {"ticker": "HPG", "identity_type": "period_end_shares_outstanding", "value": 2},
                {"ticker": "VNM", "identity_type": "current_shares_outstanding_after_event", "value": 3},
                "not even an object",
                "",
            ]
            path.write_text("\n".join(json.dumps(r) if not isinstance(r, str) or r else r for r in rows),
                             encoding="utf-8")
            result = m._load_share_basis_event_rows(root, "HPG")
            self.assertEqual(1, len(result))
            self.assertEqual(1, result[0]["value"])

    def test_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], m._load_share_basis_event_rows(Path(tmp), "HPG"))


class EvaluateFormulaTests(unittest.TestCase):
    """Full metric computation with synthetic, fully-qualified price/shares/financial
    inputs -- proves the formulas are correct, not just that the fail-closed paths work."""

    def _evaluate(self, financial=None):
        with patch("current_state_relative_valuation.price_basis_capability.current_state_eligibility",
                   return_value={"eligible_for_current_state_price_analytics": True, "status": "QUALIFIED"}), \
             patch("current_state_relative_valuation.resolve_current_price", return_value=_qualified_price()), \
             patch("current_state_relative_valuation.resolve_current_shares", return_value=_qualified_shares()):
            return m.evaluate_current_state_relative_valuation(
                "HPG", runtime_root=RUNTIME_ROOT, financial=financial or _qualified_financial(),
                entity_type="corporate", reference_session_date="2026-08-07",
            )

    def test_market_cap_is_price_times_current_shares(self):
        result = self._evaluate()
        expected = 22_000_000 * 8_442_964_520
        self.assertEqual("available", result["methods"]["market_cap"]["state"])
        self.assertEqual(expected, result["methods"]["market_cap"]["observed_value"])
        self.assertEqual("2026-08-07", result["methods"]["market_cap"]["price_as_of_session"])
        self.assertEqual("2026-08-07", result["methods"]["market_cap"]["share_effective_date"])

    def test_pe_pb_ps_use_market_cap_over_denominator(self):
        result = self._evaluate()
        market_cap = 22_000_000 * 8_442_964_520
        self.assertAlmostEqual(market_cap / 12_000_000_000_000, result["methods"]["pe"]["observed_value"])
        self.assertAlmostEqual(market_cap / 114_000_000_000_000, result["methods"]["pb"]["observed_value"])
        self.assertAlmostEqual(market_cap / 138_000_000_000_000, result["methods"]["ps"]["observed_value"])
        for name in ("pe", "pb", "ps"):
            self.assertFalse(result["methods"][name]["is_actionable"])
            self.assertEqual(m.AS_OF_SEMANTICS, result["methods"][name]["as_of_semantics"])
            self.assertFalse(result["methods"][name]["historical_only"])

    def test_enterprise_value_and_ev_multiples(self):
        result = self._evaluate()
        market_cap = 22_000_000 * 8_442_964_520
        ev = market_cap + 83_000_000_000_000 - 6_800_000_000_000
        self.assertAlmostEqual(ev, result["methods"]["enterprise_value"]["observed_value"])
        self.assertAlmostEqual(ev / 138_000_000_000_000, result["methods"]["ev_sales"]["observed_value"])
        self.assertAlmostEqual(ev / 22_000_000_000_000, result["methods"]["ev_ebitda"]["observed_value"])

    def test_overall_status_available_when_any_method_available(self):
        self.assertEqual(m.STATUS_QUALIFIED, self._evaluate()["status"])

    def test_bank_entity_type_makes_ev_methods_inapplicable(self):
        with patch("current_state_relative_valuation.price_basis_capability.current_state_eligibility",
                   return_value={"eligible_for_current_state_price_analytics": True}), \
             patch("current_state_relative_valuation.resolve_current_price", return_value=_qualified_price()), \
             patch("current_state_relative_valuation.resolve_current_shares", return_value=_qualified_shares()):
            result = m.evaluate_current_state_relative_valuation(
                "SOME_BANK", runtime_root=RUNTIME_ROOT, financial=_qualified_financial(), entity_type="bank",
            )
        for name in m._EV_METHODS:
            self.assertEqual("inapplicable", result["methods"][name]["state"])
        self.assertEqual("available", result["methods"]["pe"]["state"])

    def test_missing_denominator_yields_unavailable_not_a_crash(self):
        financial = _qualified_financial()
        del financial["shareholders_equity"]
        result = self._evaluate(financial)
        self.assertEqual("unavailable", result["methods"]["pb"]["state"])
        self.assertIn("required_input_missing", result["methods"]["pb"]["missing_inputs"])

    def test_negative_denominator_is_incomparable_not_unavailable(self):
        financial = _qualified_financial(net_income=_financial_record("net_income", -1))
        result = self._evaluate(financial)
        self.assertEqual("incomparable", result["methods"]["pe"]["state"])

    def test_price_not_qualified_blocks_every_method(self):
        with patch("current_state_relative_valuation.price_basis_capability.current_state_eligibility",
                   return_value={"eligible_for_current_state_price_analytics": True}), \
             patch("current_state_relative_valuation.resolve_current_price", return_value=_not_qualified_price()):
            result = m.evaluate_current_state_relative_valuation(
                "HPG", runtime_root=RUNTIME_ROOT, financial=_qualified_financial(), entity_type="corporate",
            )
        self.assertEqual(m.STATUS_NOT_QUALIFIED, result["status"])
        self.assertIsNone(result["current_shares"])
        for name in m.METHODS:
            self.assertEqual("unavailable", result["methods"][name]["state"])
            self.assertIn("qualified_current_price", result["methods"][name]["missing_inputs"])

    def test_shares_not_qualified_for_session_blocks_every_method_but_price_is_shown(self):
        with patch("current_state_relative_valuation.price_basis_capability.current_state_eligibility",
                   return_value={"eligible_for_current_state_price_analytics": True}), \
             patch("current_state_relative_valuation.resolve_current_price", return_value=_qualified_price()), \
             patch("current_state_relative_valuation.resolve_current_shares", return_value=_not_qualified_shares()):
            result = m.evaluate_current_state_relative_valuation(
                "HPG", runtime_root=RUNTIME_ROOT, financial=_qualified_financial(), entity_type="corporate",
            )
        self.assertEqual(m.STATUS_NOT_QUALIFIED, result["status"])
        self.assertTrue(result["current_price"]["qualified"])
        self.assertEqual("latest_historical_only", result["current_shares"]["bridge_result"]["status"])
        for name in m.METHODS:
            self.assertIn("qualified_current_shares_outstanding_for_session", result["methods"][name]["missing_inputs"])
            self.assertIsNone(result["methods"][name]["observed_value"])

    def test_ineligible_ticker_never_calls_price_or_shares_resolvers(self):
        with patch("current_state_relative_valuation.price_basis_capability.current_state_eligibility",
                   return_value={"eligible_for_current_state_price_analytics": False, "status": "NOT_QUALIFIED_FOR_DNSE_PRICE_ANALYTICS"}), \
             patch("current_state_relative_valuation.resolve_current_price") as price_fn, \
             patch("current_state_relative_valuation.resolve_current_shares") as shares_fn:
            result = m.evaluate_current_state_relative_valuation(
                "VNM", runtime_root=RUNTIME_ROOT, financial=_qualified_financial(),
            )
        price_fn.assert_not_called()
        shares_fn.assert_not_called()
        self.assertEqual(m.STATUS_NOT_QUALIFIED, result["status"])
        self.assertIsNone(result["current_price"])

    def test_deterministic_repeated_evaluation(self):
        first = self._evaluate()
        second = self._evaluate()
        self.assertEqual(first, second)

    def test_every_available_method_never_actionable(self):
        result = self._evaluate()
        for method in result["methods"].values():
            self.assertIs(False, method["is_actionable"])
        self.assertIs(False, result["is_actionable"])

    def test_historical_comparison_wired_end_to_end(self):
        historical = {"methods": {"pe": {
            "state": "available", "observed_multiple": 10.55, "denominator_identity": "net_income",
            "statement_scope": "consolidated", "historical_only": True, "price_as_of_date": "2024-12-31",
        }}}
        with patch("current_state_relative_valuation.price_basis_capability.current_state_eligibility",
                   return_value={"eligible_for_current_state_price_analytics": True}), \
             patch("current_state_relative_valuation.resolve_current_price", return_value=_qualified_price()), \
             patch("current_state_relative_valuation.resolve_current_shares", return_value=_qualified_shares()):
            result = m.evaluate_current_state_relative_valuation(
                "HPG", runtime_root=RUNTIME_ROOT, financial=_qualified_financial(), entity_type="corporate",
                historical_relative_valuation=historical,
            )
        self.assertEqual("comparable", result["historical_comparison"]["status"])
        self.assertEqual("comparable", result["historical_comparison"]["comparisons"]["pe"]["status"])

    def test_historical_comparison_defaults_to_incomparable_without_historical_input(self):
        result = self._evaluate()
        self.assertEqual("incomparable", result["historical_comparison"]["status"])


class HistoricalComparabilityTests(unittest.TestCase):
    def _current_pe(self, **overrides):
        base = {"state": "available", "observed_value": 12.0, "denominator_identity": "net_income",
                "statement_scope": "consolidated", "price_as_of_session": "2026-08-07"}
        base.update(overrides)
        return {"pe": base}

    def _historical_pe(self, **overrides):
        base = {"state": "available", "observed_multiple": 10.55, "denominator_identity": "net_income",
                "statement_scope": "consolidated", "historical_only": True, "price_as_of_date": "2024-12-31"}
        base.update(overrides)
        return {"methods": {"pe": base}}

    def test_comparable_when_compatible(self):
        result = m.evaluate_historical_comparability(self._current_pe(), self._historical_pe())
        self.assertEqual("comparable", result["status"])
        self.assertEqual("comparable", result["comparisons"]["pe"]["status"])
        self.assertAlmostEqual((12.0 / 10.55) - 1.0, result["comparisons"]["pe"]["multiple_change_pct"])

    def test_incomparable_when_historical_unavailable(self):
        historical = self._historical_pe(state="unavailable", observed_multiple=None)
        result = m.evaluate_historical_comparability(self._current_pe(), historical)
        self.assertEqual("incomparable", result["status"])
        self.assertIn("historical_checkpoint_unavailable", result["comparisons"]["pe"]["reasons"])

    def test_incomparable_when_denominator_identity_differs(self):
        historical = self._historical_pe(denominator_identity="shareholders_equity")
        result = m.evaluate_historical_comparability(self._current_pe(), historical)
        self.assertEqual("incomparable", result["comparisons"]["pe"]["status"])
        self.assertIn("denominator_identity_mismatch", result["comparisons"]["pe"]["reasons"])

    def test_incomparable_when_historical_not_marked_historical_only(self):
        historical = self._historical_pe(historical_only=False)
        result = m.evaluate_historical_comparability(self._current_pe(), historical)
        self.assertIn("historical_checkpoint_not_marked_historical_only", result["comparisons"]["pe"]["reasons"])

    def test_incomparable_when_current_unavailable(self):
        current = self._current_pe(state="unavailable", observed_value=None)
        result = m.evaluate_historical_comparability(current, self._historical_pe())
        self.assertIn("current_metric_unavailable", result["comparisons"]["pe"]["reasons"])

    def test_no_target_price_or_recommendation_keys_anywhere(self):
        # Structural check, not a substring ban: the comparison's own disclaimer text
        # legitimately contains words like "buy/sell" and "cheap/expensive" precisely
        # to negate them, so a naive substring ban would false-positive on the
        # disclaimer itself. What must never appear is an actual conclusion field.
        result = m.evaluate_historical_comparability(self._current_pe(), self._historical_pe())
        for banned_key in ("target_price", "recommendation", "rating", "expected_return", "position_size"):
            self.assertNotIn(banned_key, json.dumps(result))

    def test_none_historical_bundle_is_incomparable_not_a_crash(self):
        result = m.evaluate_historical_comparability(self._current_pe(), None)
        self.assertEqual("incomparable", result["status"])


class RealEvidenceIntegrationTests(unittest.TestCase):
    """Against the actual dashboard-runtime evidence -- proves today's real,
    evidenced state, not a synthetic stand-in. Skips cleanly if the runtime root
    or its share-basis evidence file is not present (e.g. a bare checkout)."""

    def setUp(self):
        if not REAL_SHARE_BASIS_PATH.exists():
            self.skipTest("real dashboard-runtime share_basis_citations.jsonl not present")

    def test_hpg_current_price_is_qualified_and_scaled_to_vnd(self):
        price = m.resolve_current_price("HPG", runtime_root=RUNTIME_ROOT, reference_session_date="2026-08-07")
        self.assertTrue(price["qualified"])
        self.assertEqual("2026-08-07", price["as_of_session"])
        self.assertEqual(22_000.0, price["value_vnd"])
        self.assertEqual(22.0, price["raw_close"])

    def test_hpg_current_shares_preserve_stale_coverage_after_manifest_registration(self):
        shares = m.resolve_current_shares(RUNTIME_ROOT, "HPG", "2026-08-07")
        self.assertEqual("latest_historical_only", shares["bridge_result"]["status"])
        self.assertFalse(shares["bridge_result"]["current_shares"]["qualified"])
        self.assertEqual("coverage_through_target_not_proven", shares["bridge_result"]["current_shares"]["reason"])
        self.assertEqual("qualified", shares["opening_identity"]["qualification"])
        self.assertIsNone(shares["opening_identity_diagnostic"])
        # The registered opening identity and one retained event remain insufficient to
        # infer coverage beyond the independently evidenced 2026-07-30 observation.
        self.assertEqual(1, shares["raw_event_citation_count"])
        self.assertEqual(1, shares["mapped_event_count"])

    def test_hpg_full_lane_is_not_qualified_today_for_an_evidenced_reason(self):
        from export_ai_bundle import load_financial_canonical, _financial_input
        canonical = load_financial_canonical(["HPG"])
        financial = _financial_input(canonical.get("HPG"))
        result = m.evaluate_current_state_relative_valuation(
            "HPG", runtime_root=RUNTIME_ROOT, financial=financial, entity_type="corporate",
            reference_session_date="2026-08-07",
        )
        self.assertEqual(m.STATUS_NOT_QUALIFIED, result["status"])
        self.assertTrue(result["current_price"]["qualified"])
        for method in result["methods"].values():
            self.assertIn("qualified_current_shares_outstanding_for_session", method["missing_inputs"])
            self.assertIsNone(method["observed_value"])
            self.assertFalse(method["is_actionable"])


if __name__ == "__main__":
    unittest.main()
