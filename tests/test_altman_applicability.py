# ==========================================================================
# Focused tests for altman_applicability.py. Pure unit tests -- no I/O.
# Industry labels are the real ICB-style values in vn_stock.db:metadata.industry.
# Run: `python -m unittest tests.test_altman_applicability`
# ==========================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from altman_applicability import (  # noqa: E402
    evaluate_altman_applicability, is_manufacturing_industry,
)

_MANUFACTURING = "Tài nguyên Cơ bản"          # HPG
_NON_MANUFACTURING = "Bất động sản"           # VIC


class AltmanApplicabilityTests(unittest.TestCase):
    def test_confirmed_non_financial_manufacturer_is_eligible(self):
        result = evaluate_altman_applicability("corporate", _MANUFACTURING)
        self.assertEqual(result["applicability"], "eligible")
        self.assertTrue(result["industry_qualified_manufacturing"])

    def test_financial_entity_types_are_not_applicable(self):
        for entity_type in ("bank", "securities", "insurance", "finance_company", "BANK"):
            result = evaluate_altman_applicability(entity_type, _MANUFACTURING)
            self.assertEqual(result["applicability"], "not_applicable", entity_type)

    def test_unknown_entity_type_is_insufficient_evidence_not_corporate(self):
        for entity_type in (None, "", "unknown", "  "):
            result = evaluate_altman_applicability(entity_type, _MANUFACTURING)
            self.assertEqual(result["applicability"], "insufficient_evidence", repr(entity_type))

    def test_non_manufacturing_corporate_is_insufficient_evidence(self):
        """Z' keeps the industry-sensitive X5 term and was estimated on manufacturers;
        entity_type == corporate alone would fail open across the whole universe."""
        for industry in (_NON_MANUFACTURING, "Bán lẻ", "Công nghệ Thông tin", "Du lịch và Giải trí"):
            result = evaluate_altman_applicability("corporate", industry)
            self.assertEqual(result["applicability"], "insufficient_evidence", industry)
            self.assertFalse(result["industry_qualified_manufacturing"], industry)

    def test_mixed_industry_labels_are_excluded_deliberately(self):
        for industry in ("Xây dựng và Vật liệu", "Hàng & Dịch vụ Công nghiệp", "Y tế"):
            self.assertFalse(is_manufacturing_industry(industry), industry)
            self.assertEqual(evaluate_altman_applicability("corporate", industry)["applicability"],
                              "insufficient_evidence", industry)

    def test_missing_industry_blocks_even_for_confirmed_corporate(self):
        for industry in (None, "", "   "):
            self.assertEqual(evaluate_altman_applicability("corporate", industry)["applicability"],
                              "insufficient_evidence", repr(industry))

    def test_industry_match_is_diacritic_and_case_insensitive(self):
        self.assertTrue(is_manufacturing_industry("Tài nguyên Cơ bản"))
        self.assertTrue(is_manufacturing_industry("Tai nguyen Co ban"))
        self.assertTrue(is_manufacturing_industry("  TAI NGUYEN CO BAN  "))

    def test_every_verdict_carries_a_reason(self):
        for entity_type, industry in (("corporate", _MANUFACTURING), ("bank", _MANUFACTURING),
                                       (None, _MANUFACTURING), ("corporate", _NON_MANUFACTURING)):
            self.assertTrue(evaluate_altman_applicability(entity_type, industry)["reason"])




class TaxonomyToAltmanBridgeTests(unittest.TestCase):
    """Altman must stay unavailable for every financial-specialized statement taxonomy,
    whichever route the entity type arrives by. The taxonomy itself never grants
    applicability -- it can only fail to support the corporate archetype."""

    #  observed taxonomy  ->  the entity_type a shadow overlay could legitimately propose
    _TAXONOMY_OVERLAY = {
        "corporate_vas": "corporate",
        "credit_institution": None,              # bank vs finance_company undecidable
        "securities_company": None,              # subtype not asserted from a template
        "financial_specialized_ambiguous": None,  # BVH-like: no exclusive evidence
        "unknown": None,
    }

    def test_no_financial_or_ambiguous_taxonomy_can_reach_eligible(self):
        for taxonomy, overlay in self._TAXONOMY_OVERLAY.items():
            if taxonomy == "corporate_vas":
                continue
            result = evaluate_altman_applicability(overlay, _MANUFACTURING)
            self.assertNotEqual(result["applicability"], "eligible", taxonomy)

    def test_only_the_corporate_taxonomy_can_reach_eligible_and_only_with_industry(self):
        self.assertEqual(
            evaluate_altman_applicability(self._TAXONOMY_OVERLAY["corporate_vas"], _MANUFACTURING)["applicability"],
            "eligible")
        self.assertEqual(
            evaluate_altman_applicability(self._TAXONOMY_OVERLAY["corporate_vas"], _NON_MANUFACTURING)["applicability"],
            "insufficient_evidence")

    def test_confirmed_financial_entity_types_stay_not_applicable(self):
        for entity_type in ("bank", "finance_company", "securities", "insurance"):
            self.assertEqual(evaluate_altman_applicability(entity_type, _MANUFACTURING)["applicability"],
                              "not_applicable", entity_type)

if __name__ == "__main__":
    unittest.main()
