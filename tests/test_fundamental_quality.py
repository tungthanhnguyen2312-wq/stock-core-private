import unittest
from fundamental_quality import evaluate_fundamental_quality
def r(m,v,period="2025"):return {"canonical_metric":m,"value":v,"quality_state":"available","statement_scope":"consolidated","period_identity":{"period":period,"period_type":"annual"}}
class T(unittest.TestCase):
 def test_complete_and_deterministic(self):
  x={"records":[r("revenue",100),r("net_income",10),r("total_assets",50),r("shareholders_equity",25),r("operating_cash_flow",12),r("total_debt",20),r("cash_and_equivalents",5)]};a=evaluate_fundamental_quality(x,"corporate");self.assertEqual(a,evaluate_fundamental_quality(x,"corporate"));self.assertEqual(a['models']['piotroski_f_score']['score_or_value'],3)
 def test_fail_closed(self):
  self.assertEqual(evaluate_fundamental_quality({"records":[r("revenue",0)]},"corporate")['models']['beneish_m_score']['result_state'],'unavailable');self.assertEqual(evaluate_fundamental_quality({"records":[r("revenue",1)]},"bank")['models']['piotroski_f_score']['result_state'],'inapplicable');self.assertEqual(evaluate_fundamental_quality({"records":[]})['models']['piotroski_f_score']['result_state'],'unknown')
 def test_never_mixes_periods_across_required_inputs(self):
  # revenue exists for both 2024 and 2025, but net_income only for 2024 -- growth_profitability
  # must use the 2024 revenue (the only period common to every required input), never silently
  # pair 2024 net_income with a newer, unrelated 2025 revenue figure.
  mixed={"records":[r("revenue",100,"2024"),r("revenue",120,"2025"),r("net_income",10,"2024")]}
  growth=evaluate_fundamental_quality(mixed,"corporate")["models"]["growth_profitability"]
  self.assertEqual(growth["result_state"],"available");self.assertEqual(growth["score_or_value"],0.1)
  self.assertEqual({p["period"] for p in growth["input_periods"]},{"2024"})
  # no common period at all across required inputs -> unavailable, not a mismatched guess.
  disjoint={"records":[r("revenue",100,"2025"),r("net_income",10,"2024")]}
  self.assertEqual(evaluate_fundamental_quality(disjoint,"corporate")["models"]["growth_profitability"]["result_state"],"unavailable")
if __name__=='__main__':unittest.main()
