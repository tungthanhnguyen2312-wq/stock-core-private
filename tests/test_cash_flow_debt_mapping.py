import unittest

from cash_flow_debt_mapping import canonicalize_items


def item(code, value, statement="cash_flow", **extra):
    return {"provider":"VCI", "vnstock_version":"4.0.4", "source_method":statement, "parameters":{"period":"year"}, "statement_type":statement, "raw_item_code":code, "raw_label":code, "reporting_frequency":"annual", "period":"2025", "statement_scope":"unknown", "value":value, "currency":None, "scale":None, "retrieved_at":"t", **extra}


class CashFlowDebtMappingTests(unittest.TestCase):
    def records(self, rows, entity="corporate"):
        return canonicalize_items(rows, entity_type=entity)["records"]

    def test_direct_cfo_cfi_cff_and_capex_not_aggregate_cfi(self):
        rows=self.records([item("net_cash_inflows_outflows_from_operating_activities",1),item("net_cash_inflows_outflows_from_investing_activities",-2),item("net_cash_inflows_outflows_from_financing_activities",3),item("purchases_of_fixed_assets_and_other_long_term_assets",-4)])
        self.assertEqual({r["canonical_metric"] for r in rows},{"operating_cash_flow","investing_cash_flow","financing_cash_flow","capital_expenditure"})
        self.assertEqual(next(r for r in rows if r["canonical_metric"]=="capital_expenditure")["value"],-4)

    def test_debt_components_derive_total_with_provenance(self):
        rows=self.records([item("short_term_borrowings",10,"balance_sheet"),item("long_term_borrowings",-2,"balance_sheet")])
        total=next(r for r in rows if r["canonical_metric"]=="total_interest_bearing_debt")
        self.assertEqual(total["value"],8); self.assertEqual(len(total["provenance"]["components"]),2)

    def test_interest_is_not_finance_cost_and_attributable_is_explicit(self):
        rows=self.records([item("financial_expenses",9,"income_statement"),item("interest_expenses",2,"income_statement"),item("attributable_to_parent_company",0,"income_statement")])
        self.assertEqual({r["canonical_metric"] for r in rows},{"interest_expense","net_income_attributable_to_parent"})
        self.assertEqual(next(r for r in rows if r["canonical_metric"]=="net_income_attributable_to_parent")["value"],0)

    def test_provider_period_scope_and_cumulative_guards(self):
        quarter=item("net_cash_inflows_outflows_from_operating_activities",-1,reporting_frequency="quarterly",period="2025-Q4",cumulative_state="unknown")
        annual=item("net_cash_inflows_outflows_from_operating_activities",5)
        rows=self.records([quarter,annual]); self.assertEqual({r["period"] for r in rows},{"2025-Q4","2025"})
        self.assertIn("quarterly_cumulative_semantics_unknown",next(r for r in rows if r["period"]=="2025-Q4")["warnings"])
        self.assertEqual(canonicalize_items([{**annual,"provider":"KBS"}],entity_type="corporate")["status"],"unavailable")

    def test_conflicts_null_malformed_and_repeated_output(self):
        null=item("cash_and_cash_equivalents",None,"balance_sheet"); zero=item("cash_and_cash_equivalents",0,"balance_sheet")
        self.assertEqual(self.records([null,zero])[0]["qualification_state"],"contradictory")
        self.assertEqual(canonicalize_items([item("cash_and_cash_equivalents","bad","balance_sheet")],entity_type="corporate")["status"],"malformed")
        one=canonicalize_items([item("cash_and_cash_equivalents",-3,"balance_sheet")],entity_type="corporate")
        self.assertEqual(one,canonicalize_items([item("cash_and_cash_equivalents",-3,"balance_sheet")],entity_type="corporate"))

    def test_bank_specific_mapping_and_legacy_empty(self):
        rows=self.records([item("net_cash_from_operating_activities",7),item("interest_and_similar_expenses",-1,"income_statement")],"bank")
        self.assertEqual({r["canonical_metric"] for r in rows},{"operating_cash_flow","interest_expense"})
        self.assertEqual(canonicalize_items([],entity_type="corporate"),{"status":"unavailable","records":[]})


if __name__ == "__main__": unittest.main()
