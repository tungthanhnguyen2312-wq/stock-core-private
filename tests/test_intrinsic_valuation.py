import unittest
from intrinsic_valuation import evaluate_intrinsic_valuation as e
def r(m,v):return {"canonical_metric":m,"value":v,"quality_state":"available","statement_scope":"consolidated","period_identity":{"period":"2025","period_type":"annual"}}
def x():
 f={m:r(m,v) for m,v in {"operating_cash_flow":100,"capital_expenditure":20,"total_debt":10,"cash_and_equivalents":5,"current_assets":100,"receivables":10,"inventory":20,"total_liabilities":50}.items()};return {"financial":f,"share_count":{"value":10,"semantics":"basic"},"current_price_actionable":True,"fcff_assumptions":{"wacc":.1,"wacc_source":"x","terminal_growth":.03,"terminal_growth_source":"x","forecast_fcff":80,"forecast_fcff_source":"x"}}
class T(unittest.TestCase):
 def test_complete_deterministic(self):a=e(x(),"2026");self.assertEqual(a,e(x(),"2026"));self.assertEqual(a["methods"]["fcff_dcf"]["state"],"available");self.assertEqual(a["methods"]["net_net"]["per_share_value"],-1.5)
 def test_fail_closed(self):
  a=x();a["financial"]["capital_expenditure"]["statement_scope"]="unknown";self.assertEqual(e(a)["methods"]["fcff_dcf"]["state"],"unavailable")
  a=x();a["share_count"]["semantics"]="unknown";self.assertEqual(e(a)["methods"]["net_net"]["state"],"unavailable")
if __name__=="__main__":unittest.main()
