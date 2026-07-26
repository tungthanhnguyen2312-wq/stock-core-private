import unittest

import pandas as pd

from financial_identity import qualify_capital_structure_observation, qualify_statement_identity


class FinancialIdentityTests(unittest.TestCase):
    def test_scope_is_unknown_while_frequency_is_qualified_by_invocation(self):
        frame = pd.DataFrame(columns=["item", "item_id", "2026-Q1", "2025-Q4"])
        result = qualify_statement_identity(frame, ticker="HPG", provider="KBS", library_version="4.0.4", method="income_statement", parameters={"period":"quarter"}, observed_at="2026-07-26T00:00:00+00:00")
        self.assertEqual(result["reporting_frequency"], "quarterly")
        self.assertEqual(result["statement_scope"], "unknown")
        self.assertEqual(result["parameters"], {"period":"quarter"})

    def test_conflicting_scope_cannot_be_created_from_frequency(self):
        frame = pd.DataFrame(columns=["item", "item_id", "2025-Năm"])
        result = qualify_statement_identity(frame, ticker="PAN", provider="VCI", library_version="4.0.4", method="income_statement", parameters={"period":"quarter"}, observed_at="t")
        self.assertEqual(result["reporting_frequency"], "unknown")
        self.assertEqual(result["statement_scope_quality_state"], "unqualified")

    def test_unknown_share_basis_and_same_response_timestamp_alignment(self):
        result = qualify_capital_structure_observation({"symbol":"VCB", "issue_share":100, "market_cap":0}, ticker="VCB", provider="VCI", library_version="4.0.4", method="overview", parameters={}, observed_at="2026-07-26T00:00:00+00:00")
        self.assertEqual(result["outstanding_shares"]["value"], 100)
        self.assertEqual(result["outstanding_shares"]["share_basis_state"], "unknown")
        self.assertIsNone(result["outstanding_shares"]["as_of_date"])
        self.assertEqual(result["market_cap"]["value"], 0)
        self.assertEqual(result["timestamp_alignment"]["state"], "aligned_observation_time")

    def test_missing_dates_and_values_remain_missing(self):
        result = qualify_capital_structure_observation({"organ_code":"PAN", "issue_share":None, "market_cap":None}, ticker="PAN", provider="VCI", library_version="4.0.4", method="overview", parameters={}, observed_at="t")
        self.assertIsNone(result["outstanding_shares"]["value"])
        self.assertIsNone(result["market_cap"]["value"])
        self.assertEqual(result["timestamp_alignment"]["state"], "partial")

    def test_financial_sector_uses_the_same_identity_contract(self):
        frame = pd.DataFrame(columns=["item", "item_id", "2025"])
        result = qualify_statement_identity(frame, ticker="VCB", provider="VCI", library_version="4.0.4", method="income_statement", parameters={"period":"year"}, observed_at="t")
        self.assertEqual(result["reporting_frequency"], "annual")
        self.assertEqual(result["statement_scope"], "unknown")

    def test_repeated_output_is_identical(self):
        kwargs = dict(ticker="HPG", provider="VCI", library_version="4.0.4", method="overview", parameters={}, observed_at="t")
        self.assertEqual(qualify_capital_structure_observation({"symbol":"HPG", "issue_share":5, "market_cap":7}, **kwargs), qualify_capital_structure_observation({"symbol":"HPG", "issue_share":5, "market_cap":7}, **kwargs))


if __name__ == "__main__":
    unittest.main()
