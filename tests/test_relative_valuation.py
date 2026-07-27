import unittest
from relative_valuation import evaluate_relative_valuation

def r(metric, value, period="2025", scope="consolidated", kind="annual"):
 return {"canonical_metric":metric,"value":value,"quality_state":"available","statement_scope":scope,"period_identity":{"period":period,"period_type":kind}}
def inputs(**overrides):
 value={"entity_type":"corporate","current_price":{"value":10,"as_of_date":"2026-01-01","source":"price","is_actionable":True,"financial_period":"2025"},"share_count_weighted_average_basic":{"value":10,"semantics":"weighted_average_basic","source":"shares"},"share_count_period_end":{"value":10,"semantics":"period_end","source":"shares"},"financial":{"net_income":r("net_income",20),"shareholders_equity":r("shareholders_equity",50),"revenue":r("revenue",100),"ebitda":r("ebitda",25),"total_debt":r("total_debt",10),"cash_and_equivalents":r("cash_and_equivalents",2)},"market_cap":{"value":100,"semantics":"qualified_market_cap","as_of_date":"2026-01-01","source":"cap"}}
 value.update(overrides);return value
class T(unittest.TestCase):
 def test_qualified_and_deterministic(self):
  a=evaluate_relative_valuation(inputs(),"2026-01-02T00:00:00+00:00");self.assertEqual(a,evaluate_relative_valuation(inputs(),"2026-01-02T00:00:00+00:00"));self.assertEqual(a["methods"]["pe"]["observed_multiple"],5);self.assertEqual(a["methods"]["pb"]["observed_multiple"],2);self.assertEqual(a["methods"]["ps"]["observed_multiple"],1)
 def test_negative_zero_null_scope_and_period_fail_closed(self):
  x=inputs();x["financial"]["net_income"]=r("net_income",-1);self.assertEqual(evaluate_relative_valuation(x)["methods"]["pe"]["state"],"incomparable")
  x=inputs();x["financial"]["revenue"]=r("revenue",0);self.assertEqual(evaluate_relative_valuation(x)["methods"]["ps"]["state"],"unavailable")
  x=inputs();x["financial"]["shareholders_equity"]=r("shareholders_equity",None);self.assertEqual(evaluate_relative_valuation(x)["methods"]["pb"]["state"],"unavailable")
  x=inputs();x["financial"]["revenue"]=r("revenue",10,scope="unknown");self.assertEqual(evaluate_relative_valuation(x)["methods"]["ps"]["state"],"unavailable")
  x=inputs();x["current_price"]["financial_period"]="2025-Q1";self.assertEqual(evaluate_relative_valuation(x)["methods"]["pb"]["state"],"unavailable")
 def test_ev_direct_peer_and_sector_guards(self):
  x=inputs();del x["financial"]["cash_and_equivalents"];self.assertEqual(evaluate_relative_valuation(x)["methods"]["ev_sales"]["state"],"unavailable")
  x=inputs(entity_type="bank");self.assertEqual(evaluate_relative_valuation(x)["methods"]["ev_sales"]["state"],"inapplicable")
  x=inputs(direct_multiples={"pe":{"value":-2,"as_of_date":"2026-01-01","source":"provider","multiple_semantics":"pe","is_actionable":True}});self.assertEqual(evaluate_relative_valuation(x)["methods"]["pe"]["state"],"incomparable")
  x=inputs(historical={"pe":[1,2,3,100]},historical_universe={"deterministic":True});self.assertEqual(evaluate_relative_valuation(x)["methods"]["pe"]["reference_range"]["high"],3)
  x=inputs(historical={"pe":[1,2]},historical_universe={"deterministic":True});self.assertIsNone(evaluate_relative_valuation(x)["methods"]["pe"]["reference_range"])
 def test_stale_unknown_share_and_no_target_price(self):
  x=inputs();x["current_price"]["is_actionable"]=False;self.assertFalse(evaluate_relative_valuation(x)["methods"]["pe"]["is_actionable"])
  x=inputs();x["share_count_weighted_average_basic"]["semantics"]="unknown";self.assertEqual(evaluate_relative_valuation(x)["methods"]["pe"]["state"],"unavailable")
  self.assertIsNone(evaluate_relative_valuation(inputs())["methods"]["pe"]["implied_value_range"])
if __name__=="__main__":unittest.main()
