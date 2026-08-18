"""Tests for Consumer pass-through and validation of canonical_financial_facts section."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONSUMER_ROOT = ROOT.parent / "ai-core-private"

#: The session the retained runtime is anchored to. The share and price legs of this
#: section are both session-relative, so the tests state the session explicitly.
SESSION = "2026-07-30"


from canonical_financial_bundle_section import attach  # noqa: E402

if CONSUMER_ROOT.is_dir():
    sys.path.insert(0, str(CONSUMER_ROOT))
    from builders.build_ticker_context import (  # noqa: E402
        canonical_financial_facts_contract,
        apply_bundle_canonical_financial_facts_contract,
    )
else:
    canonical_financial_facts_contract = None
    apply_bundle_canonical_financial_facts_contract = None


@unittest.skipUnless(CONSUMER_ROOT.is_dir(), "Consumer repository required")
class TestConsumerCanonicalFinancialFacts(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = ROOT.parent / "dashboard-runtime"

    def test_legacy_bundle_compatibility(self) -> None:
        """Legacy bundles without canonical_financial_facts return None without error."""
        legacy_bundle = {
            "schema_version": "1.0.0",
            "tickers": {
                "HPG": {"company_name": "Hoa Phat Group"}
            }
        }
        res = canonical_financial_facts_contract(legacy_bundle, "HPG")
        self.assertIsNone(res)

        context = {"ticker": "HPG", "provenance": []}
        updated = apply_bundle_canonical_financial_facts_contract(context, legacy_bundle)
        self.assertNotIn("canonical_financial_facts", updated)

    def test_malformed_status_fails_closed(self) -> None:
        """Malformed or corrupt canonical_financial_facts section fails closed."""
        malformed_bundle = {
            "schema_version": "1.0.0",
            "tickers": {
                "HPG": {
                    "canonical_financial_facts": {
                        "section_status": "malformed",
                        "facts": []
                    }
                }
            }
        }
        res = canonical_financial_facts_contract(malformed_bundle, "HPG")
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "malformed")
        self.assertFalse(res.get("is_actionable", True))

    def test_ebitda_ready_non_financial(self) -> None:
        """Case 1: EBITDA-ready non-financial company (AAH)."""
        bundle_entries = {"AAH": {"company_name": "Hop Lay Holdings"}}
        attached = attach(bundle_entries, self.runtime_root, include=True, session_date=SESSION)
        bundle = {"schema_version": "1.0.0", "tickers": attached}
        self.assertIn("canonical_financial_facts", attached["AAH"])
        sec = attached["AAH"]["canonical_financial_facts"]

        context = {"ticker": "AAH", "provenance": []}
        apply_bundle_canonical_financial_facts_contract(context, bundle)
        self.assertIn("canonical_financial_facts", context)
        c_sec = context["canonical_financial_facts"]

        # Verbatim preservation
        self.assertEqual(sec, c_sec)
        self.assertEqual(c_sec["ticker"], "AAH")
        self.assertIn("calculation_readiness", c_sec)
        self.assertIn("facts", c_sec)

        # EBITDA readiness check
        readiness_list = c_sec["calculation_readiness"]
        ebitda_ready = any(
            period.get("ebitda", {}).get("readiness") == "ready"
            for period in readiness_list
        )
        self.assertTrue(ebitda_ready, "AAH should have at least one EBITDA-ready period")

    def test_financial_institution_not_applicable(self) -> None:
        """Case 2: Financial institution (VCB) with EBITDA not_applicable."""
        bundle_entries = {"VCB": {"company_name": "Vietcombank"}}
        attached = attach(bundle_entries, self.runtime_root, include=True, session_date=SESSION)
        bundle = {"schema_version": "1.0.0", "tickers": attached}
        self.assertIn("canonical_financial_facts", attached["VCB"])
        sec = attached["VCB"]["canonical_financial_facts"]

        context = {"ticker": "VCB", "provenance": []}
        apply_bundle_canonical_financial_facts_contract(context, bundle)
        self.assertIn("canonical_financial_facts", context)
        c_sec = context["canonical_financial_facts"]

        self.assertEqual(sec, c_sec)
        readiness_list = c_sec["calculation_readiness"]
        self.assertTrue(len(readiness_list) > 0)
        first_period = readiness_list[0]
        self.assertEqual(first_period["ebitda"]["status"], "not_applicable")
        self.assertEqual(first_period["roe"]["readiness"], "ready")

    def test_conflicted_or_unavailable_case(self) -> None:
        """Case 3: Conflicted or unavailable canonical facts preserve status & withhold values."""
        bundle_entries = {"HPG": {"company_name": "Hoa Phat Group"}}
        attached = attach(bundle_entries, self.runtime_root, include=True, session_date=SESSION)
        bundle = {"schema_version": "1.0.0", "tickers": attached}
        sec = attached["HPG"]["canonical_financial_facts"]
        
        # Verify conflicted or unavailable fact presence in facts list
        facts_list = sec["facts"]
        conflicted_or_unavailable = [
            f for f in facts_list if f.get("status") in ("conflicted", "unavailable")
        ]
        self.assertTrue(len(conflicted_or_unavailable) > 0)
        for fact in conflicted_or_unavailable:
            self.assertIsNone(fact.get("value"))
            self.assertTrue(fact.get("value_withheld"))

        context = {"ticker": "HPG", "provenance": []}
        apply_bundle_canonical_financial_facts_contract(context, bundle)
        c_sec = context["canonical_financial_facts"]
        self.assertEqual(sec, c_sec)


if __name__ == "__main__":
    unittest.main()
