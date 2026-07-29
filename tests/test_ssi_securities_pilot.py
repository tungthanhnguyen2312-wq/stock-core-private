import unittest
from ssi_securities_pilot import evaluate
from intrinsic_valuation import evaluate_intrinsic_valuation
from relative_valuation import evaluate_relative_valuation

class SSISecuritiesPilotTests(unittest.TestCase):
    def test_missing_retained_annual_facts_fail_closed_and_deterministic(self):
        first=evaluate([]); second=evaluate([])
        self.assertEqual(first,second); self.assertEqual(first["state"],"unavailable")
        self.assertTrue(all(x["blocker_code"]=="ssi_fy2024_qualified_annual_provider_identity_missing" for x in first["metrics"].values()))
    def test_only_cited_consolidated_annual_provider_identity_promotes(self):
        row={"metric":"brokerage_revenue","provider":"KBS","reporting_period":"2024","reporting_frequency":"annual","statement_scope":"consolidated","unit":"VND","value":12,"observation_id":"obs","citation_id":"cite","raw_item_id":"revenue_from_brokerage_services", "method":"income_statement"}
        result=evaluate([row]); self.assertEqual(result["metrics"]["brokerage_revenue"]["state"],"available")
        self.assertEqual(result["metrics"]["brokerage_revenue"]["lineage"][0]["observation_id"],"obs")
        self.assertEqual(evaluate([{**row,"statement_scope":"unknown"}])["state"],"unavailable")
        self.assertEqual(evaluate([{**row,"method":"balance_sheet"}])["state"],"unavailable")
    def test_financial_sector_gates_block_corporate_models(self):
        intrinsic=evaluate_intrinsic_valuation({"entity_type":"securities","financial":{}})
        self.assertEqual(intrinsic["methods"]["fcff_dcf"]["state"],"inapplicable")
        self.assertEqual(intrinsic["methods"]["net_net"]["state"],"inapplicable")
        relative=evaluate_relative_valuation({"entity_type":"securities"})
        self.assertEqual(relative["methods"]["ev_ebitda"]["state"],"inapplicable")
        self.assertEqual(relative["methods"]["ev_sales"]["state"],"inapplicable")

if __name__ == "__main__": unittest.main()