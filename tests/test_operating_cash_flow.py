"""Phase 3 tests for reported, YTD, standalone-quarter and TTM OCF."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bctc_processor as processor  # noqa: E402


def _ocf_rows(
    values: dict[str, float],
    *,
    basis: str = "quarter",
    source: str = "TEST",
    normalized_unit: str = "VND",
) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "ticker": "PAN",
            "period": period,
            "item_id": "operating_cash_flow",
            "value": value,
            "ocf_basis": basis,
            "mapping_priority": 130,
            "mapping_confidence": 1.0,
            "source": source,
            "statement_scope": "consolidated",
            "audit_status": "audited",
            "raw_unit": "VND",
            "normalized_unit": normalized_unit,
            "effective_unit_multiplier": 1.0,
            "unit_status": "normalized",
        }
        for period, value in values.items()
    ])


class OperatingCashFlowPhase3Tests(unittest.TestCase):
    def test_pan_ocf_raw_data_detection(self):
        diagnostic = processor.diagnose_ocf_raw(ROOT / "data_bctc" / "PAN_cash_flow_quarter.csv")
        self.assertGreater(diagnostic["cash_flow_raw_row_count"], 0)
        self.assertEqual(diagnostic["candidate_item_ids"], ["operating_cash_flow"])
        self.assertEqual(diagnostic["selected_row"]["period"], "2025-Q4")
        self.assertEqual(diagnostic["selected_row"]["value"], -2_885_506_210_000)
        self.assertEqual(diagnostic["selected_row"]["basis"], "ytd")

    def test_pan_latest_null_period_is_skipped(self):
        selected = processor.select_latest_non_null_reported_value([
            {"period": "2025-Q4", "operating_cash_flow": -20.0},
            {"period": "2026-Q1", "operating_cash_flow": None},
        ])
        self.assertEqual(selected["period"], "2025-Q4")
        self.assertEqual(selected["operating_cash_flow"], -20.0)

    def test_reported_ocf_not_overwritten_by_null_ttm(self):
        result = processor.build_ocf_period_metrics(_ocf_rows({"2025-Q4": -20.0}, basis="ytd"))
        row = result.iloc[0]
        self.assertTrue(pd.isna(row["operating_cash_flow_ttm"]))
        self.assertEqual(row["operating_cash_flow_ttm_status"], "insufficient_periods")
        self.assertEqual(row["operating_cash_flow_reported"], -20.0)
        self.assertEqual(row["operating_cash_flow"], -20.0)
        self.assertEqual(row["operating_cash_flow_basis"], "ytd")

    def test_ocf_ytd_not_mislabeled_as_quarter(self):
        result = processor.build_ocf_period_metrics(_ocf_rows({"2025-Q2": 120.0}, basis="ytd"))
        row = result.iloc[0]
        self.assertEqual(row["operating_cash_flow_ytd"], 120.0)
        self.assertTrue(pd.isna(row["operating_cash_flow_quarter"]))
        self.assertEqual(row["operating_cash_flow_quarter_status"], "insufficient_periods")
        self.assertEqual(row["operating_cash_flow_basis"], "ytd")

    def test_ocf_ttm_requires_four_comparable_periods(self):
        three = processor.build_ocf_period_metrics(_ocf_rows({
            "2025-Q2": 2.0, "2025-Q3": 3.0, "2025-Q4": 4.0,
        }))
        self.assertTrue(three["operating_cash_flow_ttm"].isna().all())

        four = processor.build_ocf_period_metrics(_ocf_rows({
            "2025-Q1": 1.0, "2025-Q2": 2.0, "2025-Q3": 3.0, "2025-Q4": 4.0,
        }))
        q4 = four[four["period"] == "2025-Q4"].iloc[0]
        self.assertEqual(q4["operating_cash_flow_ttm"], 10.0)
        self.assertEqual(q4["operating_cash_flow_ttm_status"], "derived")
        self.assertEqual(q4["operating_cash_flow"], 10.0)
        self.assertEqual(q4["operating_cash_flow_basis"], "ttm")

    def test_ocf_unit_normalization(self):
        normalized = processor.normalize_ocf_unit(2.5, "million VND")
        self.assertEqual(normalized["value"], 2_500_000.0)
        self.assertEqual(normalized["normalized_unit"], "VND")
        self.assertEqual(normalized["unit_multiplier"], 1_000_000.0)

    def test_ocf_sign_is_preserved(self):
        normalized = processor.normalize_ocf_unit(-2.5, "billion VND")
        self.assertEqual(normalized["value"], -2_500_000_000.0)


if __name__ == "__main__":
    unittest.main()
