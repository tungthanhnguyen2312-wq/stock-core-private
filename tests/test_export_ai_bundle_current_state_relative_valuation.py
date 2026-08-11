"""export_ai_bundle.py's current_state_relative_valuation attach layer: the opt-in
wiring on top of current_state_relative_valuation.py (math/gates tested in
tests/test_current_state_relative_valuation.py). Covers exactly what changes at this
layer: flag threading, per-ticker fail-closed behaviour across a multi-ticker bundle,
the bundle-common status/is_actionable fields this layer adds, that the ticker's own
relative_valuation entry is threaded through for the historical-comparability check,
and that nothing else on a ticker's entry is ever touched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_state_relative_valuation as valuation_module  # noqa: E402
from export_ai_bundle import (  # noqa: E402
    attach_current_state_relative_valuation,
    build_current_state_relative_valuation_for_ticker_safe,
)

RUNTIME_ROOT = ROOT.parent / "dashboard-runtime"


def _qualified_result(ticker: str = "HPG") -> dict:
    return {
        "schema_version": "1.0.0", "ticker": ticker, "source": "DNSE",
        "as_of_semantics": valuation_module.AS_OF_SEMANTICS, "formula_version": valuation_module.FORMULA_VERSION,
        "eligibility": {"eligible_for_current_state_price_analytics": True},
        "current_price": {"qualified": True, "as_of_session": "2026-08-07", "value_vnd": 22000.0},
        "current_shares": {"bridge_result": {"status": "current_qualified",
                                             "current_shares": {"value": 8442964520, "qualified": True}}},
        "methods": {
            "market_cap": {"method": "market_cap", "state": "available", "observed_value": 1.857e14, "is_actionable": False},
            "pe": {"method": "pe", "state": "available", "observed_value": 15.0, "is_actionable": False},
            "pb": {"method": "pb", "state": "unavailable", "is_actionable": False},
            "ps": {"method": "ps", "state": "unavailable", "is_actionable": False},
            "enterprise_value": {"method": "enterprise_value", "state": "unavailable", "is_actionable": False},
            "ev_sales": {"method": "ev_sales", "state": "unavailable", "is_actionable": False},
            "ev_ebitda": {"method": "ev_ebitda", "state": "unavailable", "is_actionable": False},
        },
        "historical_comparison": {"status": "incomparable", "reasons": ["historical_checkpoint_unavailable"], "comparisons": {}},
        "warnings": [], "limitations": [],
        "status": valuation_module.STATUS_QUALIFIED,
    }


def _not_qualified_result(ticker: str) -> dict:
    result = _qualified_result(ticker)
    result["status"] = valuation_module.STATUS_NOT_QUALIFIED
    result["current_price"] = {"qualified": False, "as_of_session": None, "value_vnd": None}
    result["current_shares"] = None
    for method in result["methods"].values():
        method["state"] = "unavailable"
        method["observed_value"] = None
    return result


class DisabledByDefaultTests(unittest.TestCase):
    def test_disabled_by_default_attaches_no_key_at_all(self):
        entries = {"HPG": {"relative_valuation": {"methods": {}}}, "VNM": {}}
        attach_current_state_relative_valuation(entries, RUNTIME_ROOT, False, {})
        self.assertNotIn("current_state_relative_valuation", entries["HPG"])
        self.assertNotIn("current_state_relative_valuation", entries["VNM"])


class MockedAttachLayerTests(unittest.TestCase):
    """Exercises the attach layer's own logic without depending on the real retained
    evidence files or the real runtime root -- the underlying qualification/formula
    contract is separately, thoroughly tested in
    tests/test_current_state_relative_valuation.py."""

    def test_qualified_ticker_gets_status_available_and_is_actionable_false(self):
        with patch("export_ai_bundle.evaluate_current_state_relative_valuation",
                   return_value=_qualified_result("HPG")):
            result = build_current_state_relative_valuation_for_ticker_safe("HPG", RUNTIME_ROOT, {"HPG": {}}, None)
        self.assertEqual("available", result["status"])
        self.assertIs(False, result["is_actionable"])

    def test_not_qualified_ticker_gets_status_not_qualified_never_a_fabricated_value(self):
        with patch("export_ai_bundle.evaluate_current_state_relative_valuation",
                   return_value=_not_qualified_result("VNM")):
            result = build_current_state_relative_valuation_for_ticker_safe("VNM", RUNTIME_ROOT, {"VNM": {}}, None)
        self.assertEqual("not_qualified", result["status"])
        for method in result["methods"].values():
            self.assertIsNone(method["observed_value"])
        self.assertIs(False, result["is_actionable"])

    def test_build_failure_returns_none_without_raising(self):
        with patch("export_ai_bundle.evaluate_current_state_relative_valuation", side_effect=RuntimeError("boom")):
            result = build_current_state_relative_valuation_for_ticker_safe("HPG", RUNTIME_ROOT, {"HPG": {}}, None)
        self.assertIsNone(result)

    def test_relative_valuation_entry_is_threaded_through_as_historical_input(self):
        historical = {"methods": {"pe": {"state": "available", "observed_multiple": 10.55}}}
        with patch("export_ai_bundle.evaluate_current_state_relative_valuation") as evaluate_fn:
            evaluate_fn.return_value = _qualified_result("HPG")
            build_current_state_relative_valuation_for_ticker_safe("HPG", RUNTIME_ROOT, {"HPG": {}}, historical)
        self.assertEqual(historical, evaluate_fn.call_args.kwargs.get("historical_relative_valuation"))

    def test_attach_only_touches_the_new_key_per_ticker(self):
        entries = {
            "HPG": {"relative_valuation": {"methods": {}}, "snapshot": {"unchanged": True}},
            "VNM": {"relative_valuation": {"methods": {}}, "snapshot": {"unchanged": True}},
        }
        with patch("export_ai_bundle.evaluate_current_state_relative_valuation",
                   side_effect=lambda ticker, **kw: _qualified_result(ticker) if ticker == "HPG" else _not_qualified_result(ticker)):
            attach_current_state_relative_valuation(entries, RUNTIME_ROOT, True, {"HPG": {}, "VNM": {}})
        self.assertEqual({"unchanged": True}, entries["HPG"]["snapshot"])
        self.assertEqual({"unchanged": True}, entries["VNM"]["snapshot"])
        self.assertEqual("available", entries["HPG"]["current_state_relative_valuation"]["status"])
        self.assertEqual("not_qualified", entries["VNM"]["current_state_relative_valuation"]["status"])

    def test_ticker_whose_build_fails_gets_no_key_others_unaffected(self):
        entries = {"HPG": {}, "VNM": {}}
        with patch("export_ai_bundle.evaluate_current_state_relative_valuation",
                   side_effect=lambda ticker, **kw: (_ for _ in ()).throw(RuntimeError()) if ticker == "HPG" else _not_qualified_result(ticker)):
            attach_current_state_relative_valuation(entries, RUNTIME_ROOT, True, {"HPG": {}, "VNM": {}})
        self.assertNotIn("current_state_relative_valuation", entries["HPG"])
        self.assertIn("current_state_relative_valuation", entries["VNM"])


class RealEvidenceIntegrationTests(unittest.TestCase):
    """One real, non-mocked call against the actual dashboard-runtime evidence --
    locks in today's true, evidenced state end-to-end through the attach layer."""

    def setUp(self):
        if not RUNTIME_ROOT.exists():
            self.skipTest("dashboard-runtime runtime root not present")

    def test_real_hpg_attach_reflects_the_real_blocker(self):
        from export_ai_bundle import load_financial_canonical
        canonical = load_financial_canonical(["HPG"])
        result = build_current_state_relative_valuation_for_ticker_safe(
            "HPG", RUNTIME_ROOT, canonical, {"methods": {}}, "2026-08-07",
        )
        self.assertIsNotNone(result)
        self.assertEqual("not_qualified", result["status"])
        self.assertTrue(result["current_price"]["qualified"])
        self.assertEqual("blocked", result["current_shares"]["bridge_result"]["status"])
        self.assertIs(False, result["is_actionable"])


if __name__ == "__main__":
    unittest.main()
