"""Tests for P3-F3 Operational Current Valuation Input Scale-Out."""
from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_valuation_input_authority as authority
import p3f_current_market_valuation as p3f_val
import tools.run_p3f3_operational_valuation_input_scaleout as scaleout

COHORT_TICKERS = ["GAS", "HPG", "NVL", "PAN", "POW", "PVD", "QNS", "SSI", "VCB", "VNM", "VRE"]


class TestP3F3CohortAndSession(unittest.TestCase):
    def test_cohort_derivation_programmatic_and_exact(self):
        cohort = scaleout.load_cohort()
        self.assertEqual(11, len(cohort))
        tickers = [r["issuer_identity"]["ticker"] for r in cohort]
        self.assertEqual(COHORT_TICKERS, tickers)

    def test_execution_session_resolution_is_data_driven(self):
        # 14:00 intraday on 2026-08-20 resolves prior day 2026-08-19
        session = scaleout.resolve_execution_session("2026-08-20T14:00:00+07:00")
        self.assertEqual("2026-08-19", session["valuation_session"])
        self.assertEqual("QUALIFIED", session["status"])

        # 16:00 after close on 2026-08-19 resolves 2026-08-19
        session_after_close = scaleout.resolve_execution_session("2026-08-19T16:00:00+07:00")
        self.assertEqual("2026-08-19", session_after_close["valuation_session"])


class TestP3F3ZeroTickerSpecificProductionBranches(unittest.TestCase):
    def test_zero_ticker_specific_production_branches_in_scaleout_runner(self):
        source = inspect.getsource(scaleout)
        for ticker in COHORT_TICKERS:
            self.assertNotIn(f'== "{ticker}"', source)
            self.assertNotIn(f"== '{ticker}'", source)

    def test_zero_ticker_specific_production_branches_in_authority_module(self):
        source = inspect.getsource(authority)
        for ticker in COHORT_TICKERS:
            self.assertNotIn(f'== "{ticker}"', source)
            self.assertNotIn(f"== '{ticker}'", source)

    def test_zero_ticker_specific_production_branches_in_valuation_module(self):
        source = inspect.getsource(p3f_val)
        for ticker in COHORT_TICKERS:
            self.assertNotIn(f'== "{ticker}"', source)
            self.assertNotIn(f"== '{ticker}'", source)


class TestP3F3QualificationAndValuationRerun(unittest.TestCase):
    def test_price_qualification_across_cohort(self):
        # Mock observations for a canonical instrument
        inst = authority.canonical_instrument("GAS")
        evidence = {
            "status": "OBSERVED",
            "provider": "DNSE",
            "endpoint": "/price/ohlc",
            "provider_symbol": "GAS",
            "observations": [{"session": "2026-08-19", "close": 83.7}],
            "retrieved_at": "2026-08-20T07:00:00Z",
            "payload_identity": "payload-gas",
            "provenance": {},
        }
        price = authority.qualify_current_market_price(inst, evidence, requested_at="2026-08-20T14:00:00+07:00")
        self.assertEqual(authority.PRICE_READY, price["status"])
        self.assertEqual(83700.0, price["value"])
        self.assertEqual("2026-08-19", price["session"])
        self.assertEqual("NOT_PROMOTED", price["raw_as_traded"])
        self.assertFalse(price["historical_pit_eligible"])

    def test_share_coverage_fails_closed_when_stale(self):
        inst = authority.canonical_instrument("HPG")
        # Evidence through 2026-07-30 is stale for valuation date 2026-08-19
        stale_share = {
            "canonical_ticker": "HPG",
            "identity": authority.COMMON_OUTSTANDING,
            "value": 8442964520,
            "effective_date": "2026-07-02",
            "coverage_through": "2026-07-30",
            "qualification_state": "QUALIFIED",
            "payload_identity": "share-hpg",
        }
        shares = authority.qualify_current_share_basis(inst, [stale_share], valuation_date="2026-08-19")
        self.assertEqual(authority.SHARE_BLOCKED, shares["status"])
        self.assertEqual("STALE_OR_MISSING", shares["qualification_state"])
        self.assertIn("CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN", shares["reason_codes"])

    def test_valuation_rerun_with_blocked_share_basis(self):
        issuer = {
            "issuer_identity": {"ticker": "HPG", "entity_type": "corporate"},
            "facts": [
                {"canonical_metric": "net_income", "value": 11985000000000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-03-31"},
                {"canonical_metric": "shareholders_equity", "value": 114647000000000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-03-31"},
                {"canonical_metric": "revenue", "value": 140552000000000, "qualification_state": "QUALIFIED", "reporting_period": "2024", "observed_at": "2025-03-31"},
            ],
        }
        resolved = {
            "price": {"status": "PRICE_READY", "value": 21200.0, "session": "2026-08-19", "reason_codes": []},
            "shares": {"status": "SHARE_BLOCKED", "value": None, "reason_codes": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN"]},
            "market_cap_readiness": "MARKET_CAP_BLOCKED",
            "market_cap": None,
            "blocker_codes": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN"],
        }
        result = p3f_val.evaluate_issuer_from_resolved_inputs(issuer, resolved)
        self.assertIsNone(result["market_cap"])
        self.assertEqual("VALUATION_BLOCKED", result["methods"]["P/E"]["status"])
        self.assertEqual("VALUATION_BLOCKED", result["methods"]["P/B"]["status"])
        self.assertEqual("VALUATION_BLOCKED", result["methods"]["P/S"]["status"])
        self.assertIn("CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN", result["methods"]["P/E"]["blockers"])


class TestP3F3ArtifactDeterminism(unittest.TestCase):
    def test_artifact_schema_and_verdict(self):
        artifact_path = scaleout.DEFAULT_OUTPUT_DIR / "p3f3_operational_valuation_input_scaleout_artifact.json"
        self.assertTrue(artifact_path.exists())
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual("P3F3_OPERATIONAL_VALUATION_INPUT_SCALEOUT", data["artifact_type"])
        self.assertEqual("P3F3_OPERATIONAL_VALUATION_INPUT_SCALEOUT_PARTIAL", data["verdict"])
        self.assertEqual(11, data["frozen_cohort"]["size"])
        self.assertEqual(11, data["authority_coverage_before_after"]["post_scaleout_p3f3"]["PRICE_READY"])
        self.assertEqual(0, data["authority_coverage_before_after"]["post_scaleout_p3f3"]["PRICE_BLOCKED"])
        self.assertEqual(0, data["authority_coverage_before_after"]["post_scaleout_p3f3"]["SHARE_READY"])
        self.assertEqual(11, data["authority_coverage_before_after"]["post_scaleout_p3f3"]["SHARE_BLOCKED"])
        self.assertEqual(0, data["authority_coverage_before_after"]["post_scaleout_p3f3"]["BOTH_READY"])


if __name__ == "__main__":
    unittest.main()
