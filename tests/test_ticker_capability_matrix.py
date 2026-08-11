"""Focused P1.5 projection tests.  Pure contracts only; no runtime or network I/O."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from export_ai_bundle import attach_ticker_capability_matrix  # noqa: E402
from ticker_capability import build_ticker_capability_matrix  # noqa: E402


AUTHORITY = {
    "market_data_track": "OFFICIAL_PILLAR_B_LINEAGE_EXPANSION",
    "selected_source_id": None,
    "market_authority_reason": "NO_ACTIVE_QUALIFIED_RAW_PRICE_SOURCE",
    "raw_price_authority_after_selection": "PARTIAL",
    "generic_actionable_price_basis": "BLOCKED",
    "generic_actionable_volume_basis": "BLOCKED",
    "historical_valuation_unlock": "BLOCKED",
}


def _qualified_entry(entity_type: str = "corporate") -> dict:
    return {
        "entity_type": entity_type,
        "financial_canonical": {"status": "available", "reason_codes": []},
        "fundamental_quality": {"models": {"financial_strength": {"status": "available", "blocking_reasons": []}}},
        "historical_fundamental_brief": {"status": "available", "reason_codes": ["qualified_financial_facts"]},
        "historical_decision_analysis": {"eligibility": {"status": "eligible", "reason_codes": []}},
        "qualified_cohort_comparison": {"status": "available", "historical_only": True, "market_dependent": False,
                                          "is_actionable": False, "ranking_prohibited": True, "rows": []},
        "qualified_market_observations": {
            "status": "available", "descriptive_only": True, "is_actionable": False,
            "reason_codes": ["provider_scoped_only"],
        },
        "qualified_research_brief": {"ticker": "HPG", "historical_only": True, "is_actionable": False},
        "portfolio_risk_analysis": {
            "portfolio_considerations": {"actual_portfolio_fit": {"status": "blocked_input", "reason_codes": ["PORTFOLIO_CONTEXT_REQUIRED"]}},
            "allocation_eligibility": {"status": "allocation_blocked", "reason_codes": ["PORTFOLIO_CONTEXT_REQUIRED", "PRICE_BASIS_UNQUALIFIED"]},
        },
        "analysis_lane_eligibility": [{"lane": "quality_growth", "status": "eligible_for_analysis", "blocking_reasons": []}],
    }


class CapabilityMatrixTests(unittest.TestCase):
    def test_hpg_projection_preserves_descriptive_market_and_blocked_generic_gates(self) -> None:
        matrix = build_ticker_capability_matrix("HPG", _qualified_entry(), market_authority=AUTHORITY)
        self.assertEqual(matrix["fundamental_data"]["canonical_financial_facts"]["status"], "available")
        self.assertEqual(matrix["fundamental_data"]["historical_decision_analysis"]["status"], "available")
        self.assertEqual(matrix["fundamental_data"]["qualified_cohort_comparison"]["status"], "descriptive_only")
        self.assertEqual(matrix["market_descriptive"]["qualified_market_observations"]["status"], "descriptive_only")
        self.assertEqual(matrix["market_actionable"]["current_valuation"]["status"], "blocked")
        self.assertEqual(matrix["market_actionable"]["generic_liquidity"]["status"], "blocked")
        self.assertEqual(matrix["market_actionable"]["raw_as_traded_price"]["status"], "partial")
        self.assertFalse(matrix["is_actionable"])

    def test_vnm_projection_is_deterministic_and_reason_codes_survive(self) -> None:
        entry = _qualified_entry()
        entry["qualified_research_brief"]["ticker"] = "VNM"
        first = build_ticker_capability_matrix("VNM", entry, market_authority=AUTHORITY)
        second = build_ticker_capability_matrix("VNM", copy.deepcopy(entry), market_authority=copy.deepcopy(AUTHORITY))
        self.assertEqual(first, second)
        self.assertEqual(first["market_descriptive"]["provider_scoped_price_observations"]["reason_codes"], ["provider_scoped_only"])

    def test_known_unsupported_archetype_remains_not_applicable_not_unknown(self) -> None:
        entry = _qualified_entry("securities")
        entry["qualified_research_brief"]["ticker"] = "SSI"
        entry["analysis_lane_eligibility"] = [{
            "lane": "quality_growth", "status": "not_applicable",
            "blocking_reasons": ["entity_type_unsupported"],
        }]
        matrix = build_ticker_capability_matrix("SSI", entry, market_authority=AUTHORITY)
        self.assertEqual(matrix["identity"]["status"], "available")
        qualification = matrix["identity"]["analysis_archetype_qualification"]
        self.assertEqual(qualification["status"], "not_applicable")
        self.assertEqual(qualification["reason_codes"], ["entity_type_unsupported"])

    def test_unknown_entity_and_missing_optional_contracts_fail_closed(self) -> None:
        matrix = build_ticker_capability_matrix("PNJ", {"entity_type": "unknown"}, market_authority=AUTHORITY)
        self.assertEqual(matrix["identity"]["status"], "unknown")
        self.assertEqual(matrix["identity"]["reason_codes"], ["entity_type_unknown"])
        self.assertEqual(matrix["research"]["qualified_research_brief"]["status"], "unavailable")
        self.assertEqual(matrix["portfolio"]["portfolio_fit"]["status"], "unavailable")

    def test_attachment_retains_every_production_ticker_and_legacy_fields(self) -> None:
        tickers = ("POW", "SSI", "HPG", "EVF", "PAN", "PNJ", "FPT", "QNS", "VNM", "PVD", "NVL")
        entries = {ticker: {"entity_type": "unknown", "legacy": ticker} for ticker in tickers}
        result = attach_ticker_capability_matrix(entries)
        self.assertEqual(tuple(result), tickers)
        for ticker in tickers:
            self.assertEqual(result[ticker]["legacy"], ticker)
            self.assertEqual(result[ticker]["ticker_capability_matrix"]["ticker"], ticker)
            self.assertEqual(result[ticker]["ticker_capability_matrix"]["market_data_authority"]["market_data_track"], "OFFICIAL_PILLAR_B_LINEAGE_EXPANSION")


if __name__ == "__main__":
    unittest.main()
