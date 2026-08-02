# ==========================================================================
# Focused tests for entity_type_classifier.py. Pure unit tests -- no I/O, no
# dashboard-runtime access. Item vocabularies below are the real, distinctive
# balance-sheet item_ids observed in data_bctc/*_balance_sheet_quarter.parquet.
# Run: `python -m unittest tests.test_entity_type_classifier` from the repo root.
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from entity_type_classifier import classify  # noqa: E402

_CORPORATE = {"current_assets", "current_liabilities", "short_term_borrowings", "inventories",
              "total_assets", "owners_equity", "undistributed_earnings"}
_BANK = {"loans_and_advances_to_customers", "deposits_from_customers", "balances_with_the_sbv",
         "placements_with_and_loans_to_other_credit_institutions", "total_assets"}
# A broker files the corporate current/non-current split *and* client-asset lines.
_SECURITIES = _CORPORATE | {"available_for_sale_financial_assets_afs",
                             "customerss_deposits_for_securities_trading"}


class EntityTypeClassifierTests(unittest.TestCase):
    def test_corporate_template_is_classified_corporate(self):
        result = classify(_CORPORATE)
        self.assertEqual(result["entity_type"], "corporate")
        self.assertEqual(result["confidence_basis"], "corporate_statement_template_observed")

    def test_credit_institution_is_never_called_corporate_and_subtype_is_not_guessed(self):
        result = classify(_BANK)
        self.assertEqual(result["entity_type"], "unknown")
        self.assertIn("bank_vs_finance_company_not_decidable", result["confidence_basis"])

    def test_securities_broker_is_not_classified_corporate(self):
        """Regression guard for a real false positive: the broker template carries
        current_assets/current_liabilities/short_term_borrowings, so corporate markers
        alone let SSI through. Validating against the 15 hand-curated profiles caught it."""
        result = classify(_SECURITIES)
        self.assertEqual(result["entity_type"], "unknown")
        self.assertIn("securities_broker_template", result["confidence_basis"])
        self.assertGreater(result["securities_marker_hits"], 0)

    def test_securities_markers_win_over_corporate_markers(self):
        self.assertGreaterEqual(classify(_SECURITIES)["corporate_marker_hits"], 3,
                                 "the broker template really does carry corporate markers")
        self.assertEqual(classify(_SECURITIES)["entity_type"], "unknown")

    def test_any_single_credit_institution_marker_disqualifies_corporate(self):
        mixed = _CORPORATE | {"balances_with_the_sbv"}
        self.assertEqual(classify(mixed)["entity_type"], "unknown")

    def test_too_few_corporate_markers_stays_unknown(self):
        self.assertEqual(classify({"current_assets", "total_assets"})["entity_type"], "unknown")
        self.assertEqual(classify(set())["entity_type"], "unknown")

    def test_never_asserts_a_subtype_it_cannot_prove(self):
        for vocabulary in (_CORPORATE, _BANK, _SECURITIES, set()):
            self.assertIn(classify(vocabulary)["entity_type"], {"corporate", "unknown"},
                           "only corporate is ever asserted; subtypes stay hand-curated")

    def test_result_carries_the_evidence_for_the_call(self):
        result = classify(_CORPORATE)
        self.assertTrue(result["matched_markers"]["corporate"])
        self.assertEqual(result["matched_markers"]["credit_institution"], [])
        self.assertTrue(result["classifier_version"])


if __name__ == "__main__":
    unittest.main()
