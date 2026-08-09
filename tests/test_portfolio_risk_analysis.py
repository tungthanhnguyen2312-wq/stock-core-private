import copy, json, unittest
from historical_decision_analysis import evaluate_historical_decision_analysis
from portfolio_risk_analysis import evaluate_portfolio_risk_analysis

def entry(ticker="HPG",entity="corporate",capex=True):
 r=lambda metric,value:{"canonical_metric":metric,"value":value,"quality_state":"available","period_identity":{"period":"2024"},"source":"x","observation_ids":[metric],"evidence":{"evidence_id":"e","citation_id":"c"}}
 records=[r("revenue",10),r("net_income",1)]+([r("capital_expenditure",-2)] if capex else [])
 models={"growth_profitability":{"result_state":"available"},"financial_strength":{"result_state":"available"},"dupont_roe":{"result_state":"partial"},"earnings_quality":{"result_state":"available"},"bank_financial_quality":{"result_state":"available"}}
 base={"entity_type":entity,"financial_canonical":{"status":"available","records":records},"fundamental_quality":{"models":models},"fundamental_quality_evidence":{"metrics":{"operating_cash_flow_less_net_income":{"qualification_status":"qualified","value":0}}},"historical_capital_structure":{"metrics":{"net_debt_to_equity":{"qualification_status":"qualified","value":0}}}}
 base["historical_decision_analysis"]=evaluate_historical_decision_analysis(ticker,base);return base
def basis(): return {"price_basis":"unknown","price_basis_verified":False,"volume_basis":"unknown","volume_basis_verified":False}
class T(unittest.TestCase):
 def test_deterministic_and_liquidity_blocked(self):
  x=entry();a=evaluate_portfolio_risk_analysis("HPG",x,basis());self.assertEqual(a,evaluate_portfolio_risk_analysis("HPG",copy.deepcopy(x),basis()));self.assertEqual(a["liquidity"]["status"],"blocked");self.assertEqual(a["liquidity"]["metrics"],{});self.assertIn("VOLUME_BASIS_UNQUALIFIED",a["liquidity"]["reason_codes"]);self.assertFalse(a["allocation_eligibility"]["eligible"])
 def test_archetypes_differ_and_bank_is_not_corporate(self):
  h=evaluate_portfolio_risk_analysis("HPG",entry("HPG"),basis());v=evaluate_portfolio_risk_analysis("VNM",entry("VNM",capex=False),basis());b=evaluate_portfolio_risk_analysis("VCB",entry("VCB","bank"),basis());self.assertNotEqual(set(h["fundamental_risk"]["dimensions"]),set(b["fundamental_risk"]["dimensions"]));self.assertEqual(b["fundamental_risk"]["dimensions"]["corporate_leverage"]["status"],"not_applicable");self.assertEqual(v["fundamental_risk"]["dimensions"]["capital_intensity"]["status"],"unavailable")
 def test_phase4b_block_and_no_advice(self):
  x=entry();x["historical_decision_analysis"]["eligibility"]["status"]="blocked";a=evaluate_portfolio_risk_analysis("HPG",x,basis());self.assertFalse(a["allocation_eligibility"]["research_ready"]);self.assertEqual(a["portfolio_considerations"]["actual_portfolio_fit"]["status"],"blocked_input");self.assertNotIn('"buy"',json.dumps(a).lower());self.assertNotIn("position_size",a)
if __name__=="__main__":unittest.main()
