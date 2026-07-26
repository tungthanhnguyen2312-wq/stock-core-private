import unittest
from fundamental_quality import evaluate_fundamental_quality
def r(m,v):return {"canonical_metric":m,"value":v,"quality_state":"available","statement_scope":"consolidated","period_identity":{"period":"2025","period_type":"annual"}}
class T(unittest.TestCase):
 def test_complete_and_deterministic(self):
  x={"records":[r("revenue",100),r("net_income",10),r("total_assets",50),r("shareholders_equity",25),r("operating_cash_flow",12),r("total_debt",20),r("cash_and_equivalents",5)]};a=evaluate_fundamental_quality(x,"corporate");self.assertEqual(a,evaluate_fundamental_quality(x,"corporate"));self.assertEqual(a['models']['piotroski_f_score']['score_or_value'],3)
 def test_fail_closed(self):
  self.assertEqual(evaluate_fundamental_quality({"records":[r("revenue",0)]},"corporate")['models']['beneish_m_score']['result_state'],'unavailable');self.assertEqual(evaluate_fundamental_quality({"records":[r("revenue",1)]},"bank")['models']['piotroski_f_score']['result_state'],'inapplicable');self.assertEqual(evaluate_fundamental_quality({"records":[]})['models']['piotroski_f_score']['result_state'],'unknown')
if __name__=='__main__':unittest.main()
