"""export_ai_bundle.py's current_state_market_risk attach layer: the opt-in
wiring on top of dnse_current_state_market_risk.py (math/gates tested in
tests/test_dnse_current_state_market_risk.py). Covers exactly what changes at
this layer: the flag threading itself, per-ticker fail-closed behaviour
across a multi-ticker bundle, the bundle-common status/is_actionable/
convenience fields this layer adds, and that nothing else on a ticker's
entry is ever touched.
"""
from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnse_current_state_market_risk as market_risk_module  # noqa: E402
import dnse_current_state_price_analytics as price_analytics_module  # noqa: E402
import dnse_index_return_series_capability as index_capability_module  # noqa: E402
from export_ai_bundle import (  # noqa: E402
    attach_current_state_market_risk,
    build_current_state_market_risk_for_ticker_safe,
)

RUNTIME_ROOT = ROOT.parent / "dashboard-runtime"
REAL_EVIDENCE_PRESENT = (
    market_risk_module.DEFAULT_STOCK_EVIDENCE_PATH.exists()
    and market_risk_module.DEFAULT_BENCHMARK_EVIDENCE_PATH.exists()
)


def _qualified_result(ticker: str = "HPG") -> dict:
    return {
        "schema_version": "1.0.0", "ticker": ticker, "benchmark": "VNINDEX",
        "source_scope": {"stock_source": "DNSE", "benchmark_source": "DNSE",
                         "same_source_no_fallback_mixing": True, "reason": None},
        "stock_price_contract": {"price_basis": "ADJUSTED_CONFIRMED",
                                 "price_basis_contract_version": "v1", "qualification_scope": "x"},
        "benchmark_return_contract": {"index_level_unit": "index_points", "source_contract_version": "v1"},
        "analysis_time_semantics": market_risk_module.ANALYSIS_TIME_SEMANTICS,
        "pit_backtest_eligible": False,
        "input_gates": {"stock_qualified": True, "stock_reason": None,
                        "benchmark_qualified": True, "benchmark_reason": None,
                        "source_scope_ok": True, "source_scope_reason": None},
        "aligned_sessions": {"aligned_pairs": [], "stock_return_count": 18, "benchmark_return_count": 18,
                             "paired_return_count": 18, "dropped_stock_sessions": [], "dropped_benchmark_sessions": []},
        "paired_return_count": 18,
        "beta": {"value": 0.81, "sample_adequacy": "MATHEMATICALLY_COMPUTABLE", "reason": None},
        "correlation": {"value": 0.57, "sample_adequacy": "MATHEMATICALLY_COMPUTABLE", "reason": None},
        "coverage": {"status": "complete", "paired_return_count": 18, "minimum_required": 2,
                    "sample_adequacy": "MATHEMATICALLY_COMPUTABLE", "reason": None},
        "qualification_status": "CURRENT_STATE_BETA_CORRELATION_QUALIFIED",
        "warnings": list(market_risk_module.STANDING_WARNINGS),
        "provenance": {"stock_provenance": {}, "benchmark_provenance": {},
                      "contract_module": "dnse_current_state_market_risk.py", "contract_version": "1.0.0"},
    }


def _not_qualified_result(ticker: str) -> dict:
    result = _qualified_result(ticker)
    result["qualification_status"] = "CURRENT_STATE_BETA_CORRELATION_NOT_QUALIFIED"
    result["beta"] = {"value": None, "sample_adequacy": None, "reason": "stock_ticker_not_qualified_for_dnse_current_state_price_analytics"}
    result["correlation"] = {"value": None, "sample_adequacy": None, "reason": "stock_ticker_not_qualified_for_dnse_current_state_price_analytics"}
    result["aligned_sessions"] = {"aligned_pairs": [], "stock_return_count": 0, "benchmark_return_count": 0,
                                  "paired_return_count": 0, "dropped_stock_sessions": [], "dropped_benchmark_sessions": []}
    result["paired_return_count"] = 0
    result["coverage"] = {"status": "not_qualified", "reason": "stock_ticker_not_qualified_for_dnse_current_state_price_analytics"}
    return result


class DisabledByDefaultTests(unittest.TestCase):
    def test_disabled_by_default_attaches_no_key_at_all(self):
        entries = {"HPG": {}, "VNM": {}}
        attach_current_state_market_risk(entries, RUNTIME_ROOT, False)
        self.assertNotIn("current_state_market_risk", entries["HPG"])
        self.assertNotIn("current_state_market_risk", entries["VNM"])


class MockedAttachLayerTests(unittest.TestCase):
    """Exercises the attach layer's own logic (status/is_actionable derivation,
    per-ticker fail-closed behaviour, isolation) without depending on the real
    retained evidence files or the real runtime root -- the underlying math
    contract is separately, thoroughly tested in
    tests/test_dnse_current_state_market_risk.py."""

    def test_qualified_ticker_gets_status_available_and_is_actionable_false(self):
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   return_value=_qualified_result("HPG")):
            result = build_current_state_market_risk_for_ticker_safe("HPG", RUNTIME_ROOT)
        self.assertEqual("available", result["status"])
        self.assertIs(False, result["is_actionable"])
        self.assertIs(False, result["pit_backtest_eligible"])

    def test_not_qualified_ticker_gets_status_not_qualified_never_a_fabricated_value(self):
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   return_value=_not_qualified_result("VNM")):
            result = build_current_state_market_risk_for_ticker_safe("VNM", RUNTIME_ROOT)
        self.assertEqual("not_qualified", result["status"])
        self.assertIsNone(result["beta"]["value"])
        self.assertIsNone(result["correlation"]["value"])
        self.assertIs(False, result["is_actionable"])

    def test_top_level_convenience_fields_are_copies_not_recomputed(self):
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   return_value=_qualified_result("HPG")):
            result = build_current_state_market_risk_for_ticker_safe("HPG", RUNTIME_ROOT)
        self.assertEqual(18, result["stock_return_count"])
        self.assertEqual(18, result["benchmark_return_count"])
        self.assertEqual([], result["dropped_stock_sessions"])
        self.assertEqual([], result["dropped_benchmark_sessions"])
        self.assertEqual("MATHEMATICALLY_COMPUTABLE", result["sample_adequacy"])
        self.assertEqual(18, result["paired_return_count"])

    def test_build_failure_returns_none_without_raising(self):
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   side_effect=RuntimeError("boom")):
            result = build_current_state_market_risk_for_ticker_safe("HPG", RUNTIME_ROOT)
        self.assertIsNone(result)

    def test_one_tickers_build_failure_does_not_break_the_bundle_or_other_tickers(self):
        def flaky(ticker, benchmark_id, *, runtime_root):
            if ticker == "BROKEN":
                raise RuntimeError("boom")
            return _qualified_result(ticker)

        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   side_effect=flaky):
            entries = {"HPG": {}, "BROKEN": {}}
            attach_current_state_market_risk(entries, RUNTIME_ROOT, True)
        self.assertIn("current_state_market_risk", entries["HPG"])
        self.assertNotIn("current_state_market_risk", entries["BROKEN"])

    def test_attaching_touches_no_other_key_on_the_entry(self):
        entry = {"ticker_capability_matrix": {"research": {"research_eligible": True}},
                 "snapshot": {"date": "2026-08-07"}}
        before = json.loads(json.dumps(entry))
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   return_value=_qualified_result("HPG")):
            entries = {"HPG": entry}
            attach_current_state_market_risk(entries, RUNTIME_ROOT, True)
        after = {k: v for k, v in entries["HPG"].items() if k != "current_state_market_risk"}
        self.assertEqual(before, after)

    def test_deterministic_serialization_across_repeated_attach_calls(self):
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   return_value=_qualified_result("HPG")):
            first = {"HPG": {}}
            attach_current_state_market_risk(first, RUNTIME_ROOT, True)
            second = {"HPG": {}}
            attach_current_state_market_risk(second, RUNTIME_ROOT, True)
        self.assertEqual(json.dumps(first, sort_keys=True, default=str),
                         json.dumps(second, sort_keys=True, default=str))

    def test_no_secret_or_credential_like_value_in_the_attached_entry(self):
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   return_value=_qualified_result("HPG")):
            entries = {"HPG": {}}
            attach_current_state_market_risk(entries, RUNTIME_ROOT, True)
        dumped = json.dumps(entries["HPG"]["current_state_market_risk"], default=str).lower()
        for forbidden in ("token", "secret", "signature", "authorization", "x-api-key", "cookie",
                          "api_key", "api_secret", "bearer"):
            self.assertNotIn(forbidden, dumped)

    def test_no_volume_field_anywhere_in_the_attached_entry(self):
        with patch("export_ai_bundle.build_current_state_market_risk_from_retained_evidence",
                   return_value=_qualified_result("HPG")):
            entries = {"HPG": {}}
            attach_current_state_market_risk(entries, RUNTIME_ROOT, True)
        self.assertNotIn("volume", json.dumps(entries["HPG"]["current_state_market_risk"], default=str).lower())


class NoMetricRecomputationTests(unittest.TestCase):
    """Step 13 item 14: the attach layer must be pure composition -- it must
    never contain its own beta/covariance/variance arithmetic."""

    def test_attach_layer_source_contains_no_formula_arithmetic(self):
        import export_ai_bundle
        source = inspect.getsource(export_ai_bundle.build_current_state_market_risk_for_ticker_safe) + \
            inspect.getsource(export_ai_bundle.attach_current_state_market_risk)
        for forbidden in ("sqrt(", "covariance", " variance", "cov =", "corr =", "beta_val", "** 2"):
            self.assertNotIn(forbidden, source)

    def test_attach_layer_calls_the_authoritative_module_not_a_local_reimplementation(self):
        import export_ai_bundle
        source = inspect.getsource(export_ai_bundle.build_current_state_market_risk_for_ticker_safe)
        self.assertIn("build_current_state_market_risk_from_retained_evidence", source)


class VcbNeverEntersProductionUniverseTests(unittest.TestCase):
    def test_vcb_not_in_default_tickers(self):
        import export_ai_bundle
        self.assertNotIn("VCB", export_ai_bundle.DEFAULT_TICKERS)
        self.assertIn("HPG", export_ai_bundle.DEFAULT_TICKERS)


class NoNetworkRequiredForBundleBuildTests(unittest.TestCase):
    """Step 13 item 17: static proof that building a bundle with this flag
    enabled cannot reach the network or read secrets.env -- the entire import
    chain (attach layer -> dnse_current_state_market_risk.py -> its two
    upstream capability modules) imports neither a DNSE network client nor a
    generic HTTP library."""

    def test_no_network_or_credential_module_anywhere_on_the_import_chain(self):
        source_paths = [
            Path(market_risk_module.__file__),
            Path(price_analytics_module.__file__),
            Path(index_capability_module.__file__),
        ]
        forbidden_imports = ("dnse_access", "dnse_market_data", "requests", "urllib.request",
                             "httpx", "socket")
        for path in source_paths:
            text = path.read_text(encoding="utf-8")
            for forbidden in forbidden_imports:
                self.assertNotIn(f"import {forbidden}", text,
                                 f"{path.name} unexpectedly imports {forbidden}")


@unittest.skipUnless(REAL_EVIDENCE_PRESENT, "real retained HPG/VNINDEX evidence not present")
class RealHpgVnindexBundleTests(unittest.TestCase):
    """Steps 5 & 11: the real bundle-attachment result for the actual
    production universe, against the real retained evidence and the real
    runtime root."""

    def test_hpg_available_with_real_beta_and_correlation(self):
        entries = {"HPG": {}}
        attach_current_state_market_risk(entries, RUNTIME_ROOT, True)
        result = entries["HPG"]["current_state_market_risk"]
        self.assertEqual("available", result["status"])
        self.assertAlmostEqual(0.8093285134496059, result["beta"]["value"], places=9)
        self.assertAlmostEqual(0.5664164065437041, result["correlation"]["value"], places=9)
        self.assertEqual(18, result["paired_return_count"])
        self.assertEqual("MATHEMATICALLY_COMPUTABLE", result["sample_adequacy"])
        self.assertIs(False, result["pit_backtest_eligible"])
        self.assertIs(False, result["is_actionable"])

    def test_every_other_production_ticker_fails_closed_not_qualified(self):
        from export_ai_bundle import DEFAULT_TICKERS
        entries = {tk: {} for tk in DEFAULT_TICKERS}
        attach_current_state_market_risk(entries, RUNTIME_ROOT, True)
        for ticker in DEFAULT_TICKERS:
            if ticker == "HPG":
                continue
            result = entries[ticker]["current_state_market_risk"]
            self.assertEqual("not_qualified", result["status"], ticker)
            self.assertIsNone(result["beta"]["value"], ticker)
            self.assertIsNone(result["correlation"]["value"], ticker)

    def test_full_default_universe_attach_is_byte_identical_across_two_runs(self):
        from export_ai_bundle import DEFAULT_TICKERS
        first = {tk: {} for tk in DEFAULT_TICKERS}
        attach_current_state_market_risk(first, RUNTIME_ROOT, True)
        second = {tk: {} for tk in DEFAULT_TICKERS}
        attach_current_state_market_risk(second, RUNTIME_ROOT, True)
        self.assertEqual(json.dumps(first, sort_keys=True, default=str),
                         json.dumps(second, sort_keys=True, default=str))


if __name__ == "__main__":
    unittest.main()
