# ==========================================================================
# Focused tests for statement_taxonomy_classifier.py. Pure unit tests -- no
# I/O, no dashboard-runtime access. Item vocabularies below are the real,
# distinctive balance-sheet item_ids observed in
# data_bctc/*_balance_sheet_quarter.parquet.
# Run: `python -m unittest tests.test_statement_taxonomy_classifier`
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from statement_taxonomy_classifier import (  # noqa: E402
    TAXONOMIES, classify_statement_taxonomy as classify,
)

_CORPORATE = {"current_assets", "current_liabilities", "short_term_borrowings", "inventories",
              "total_assets", "owners_equity", "undistributed_earnings"}
_CREDIT = {"loans_and_advances_to_customers", "deposits_from_customers", "balances_with_the_sbv",
           "placements_with_and_loans_to_other_credit_institutions", "total_assets"}
# BVH's real shape: one *shared* lending line and three corporate markers, with zero
# exclusive deposit-taking/SBV/interbank markers. An insurer holds loans too.
_INSURER_LIKE = _CORPORATE | {"loans_and_advances_to_customers"}
# A broker files the corporate current/non-current split *and* client-asset lines.
_SECURITIES = _CORPORATE | {"available_for_sale_financial_assets_afs",
                             "customerss_deposits_for_securities_trading"}


class StatementTaxonomyClassifierTests(unittest.TestCase):
    def test_corporate_template_is_observed(self):
        result = classify(_CORPORATE)
        self.assertEqual(result["statement_taxonomy"], "corporate_vas")
        self.assertEqual(result["classification_status"], "observed")
        self.assertIsNone(result["abstention_reason"])

    def test_credit_institution_template_is_observed_without_guessing_a_subtype(self):
        """The template cannot separate a bank from a finance company -- EVF files the same
        49/2014/TT-NHNN form as BID/MBB/TCB/VCB -- so the taxonomy stops at the family."""
        result = classify(_CREDIT)
        self.assertEqual(result["statement_taxonomy"], "credit_institution")
        self.assertEqual(result["classification_status"], "observed")

    def test_securities_broker_is_never_read_as_corporate(self):
        """Regression guard for a real false positive: the broker template carries
        current_assets/current_liabilities/short_term_borrowings too, so corporate markers
        alone let SSI through until client-asset markers were added as an exclusion."""
        result = classify(_SECURITIES)
        self.assertEqual(result["statement_taxonomy"], "securities_company")
        self.assertGreaterEqual(result["marker_hits"]["corporate"], 3,
                                 "the broker template really does carry corporate markers")
        self.assertGreater(result["marker_hits"]["securities"], 0)

    def test_two_specialized_families_abstain_rather_than_pick_one(self):
        result = classify(_CREDIT | _SECURITIES)
        self.assertEqual(result["statement_taxonomy"], "financial_specialized_ambiguous")
        self.assertEqual(result["classification_status"], "abstained")
        self.assertTrue(result["abstention_reason"])

    def test_shared_lending_line_alone_never_asserts_credit_institution(self):
        """Regression guard for a real overstatement: BVH (insurance) carries only
        `loans_and_advances_to_customers` -- a line an insurer reports too -- and was
        labelled `credit_institution` on that single shared marker. Exclusive
        deposit-taking/SBV/interbank evidence is now required."""
        result = classify(_INSURER_LIKE)
        self.assertNotEqual(result["statement_taxonomy"], "credit_institution")
        self.assertEqual(result["statement_taxonomy"], "financial_specialized_ambiguous")
        self.assertEqual(result["classification_status"], "abstained")
        self.assertEqual(result["marker_hits"]["credit_institution_exclusive"], 0)
        self.assertGreater(result["marker_hits"]["credit_institution_shared"], 0)

    def test_insurance_is_never_named_without_exclusive_evidence(self):
        self.assertNotEqual(classify(_INSURER_LIKE)["statement_taxonomy"], "insurance")

    def test_exclusive_credit_markers_do_assert_credit_institution(self):
        for marker in ("deposits_from_customers", "balances_with_the_sbv",
                        "placements_with_and_loans_to_other_credit_institutions"):
            result = classify({marker, "total_assets"})
            self.assertEqual(result["statement_taxonomy"], "credit_institution", marker)
            self.assertEqual(result["classification_status"], "observed", marker)

    def test_shared_financial_vocabulary_never_falls_back_to_corporate(self):
        """The insurer-like vocabulary clears the corporate marker threshold; it must still
        not be read as corporate_vas."""
        self.assertGreaterEqual(classify(_INSURER_LIKE)["marker_hits"]["corporate"], 3)
        self.assertNotEqual(classify(_INSURER_LIKE)["statement_taxonomy"], "corporate_vas")

    def test_insufficient_markers_abstain(self):
        for vocabulary in ({"current_assets", "total_assets"}, set()):
            result = classify(vocabulary)
            self.assertEqual(result["statement_taxonomy"], "unknown")
            self.assertEqual(result["classification_status"], "abstained")
            self.assertTrue(result["abstention_reason"])

    def test_never_emits_an_entity_type(self):
        """Statement vocabulary evidences which form was filed, not what the issuer is.
        Emitting an entity_type here would re-create the fail-open route this module was
        split apart to remove."""
        for vocabulary in (_CORPORATE, _CREDIT, _SECURITIES, set()):
            result = classify(vocabulary)
            self.assertNotIn("entity_type", result)
            self.assertIn(result["statement_taxonomy"], set(TAXONOMIES))

    def test_result_carries_provenance_fields_for_a_shadow_overlay(self):
        result = classify(_CORPORATE, ticker="HPG", source="VCI",
                           reporting_period="2025-Q4", statement_scope="consolidated")
        for field in ("ticker", "source", "reporting_period", "statement_scope",
                       "classifier_version", "matched_markers", "marker_hits"):
            self.assertIn(field, result)
        self.assertEqual(result["ticker"], "HPG")
        self.assertTrue(result["matched_markers"]["corporate"])
        self.assertEqual(result["matched_markers"]["credit_institution_exclusive"], [])
        self.assertEqual(result["matched_markers"]["credit_institution_shared"], [])

    def test_classification_is_deterministic(self):
        self.assertEqual(classify(_CORPORATE), classify(set(_CORPORATE)))


if __name__ == "__main__":
    unittest.main()
