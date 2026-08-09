import unittest
from historical_scaleout import select,attach
def e(entity="corporate",ok=True):return {"entity_type":entity,"financial_canonical":{"status":"available" if ok else "missing","records":[{"quality_state":"available","value":0,"canonical_metric":"net_income"}] if ok else []}}
class T(unittest.TestCase):
 def test_selection_is_sorted_bounded_and_fail_closed(self):
  x={"ZZZ":e(),"AAA":e(),"UNK":e("unknown"),"BAD":e(ok=False),"HPG":e()};r=select(x,1);self.assertEqual([i["ticker"] for i in r if i["selected"]],["AAA"]);self.assertIn("entity_type_unknown_or_unsupported",next(i for i in r if i["ticker"]=="UNK")["reason_codes"])
 def test_attach_has_brief_and_does_not_select_by_name(self):
  x={"AAA":e(),"BBB":e("bank")};o=attach(x,{"price_basis_verified":False,"volume_basis_verified":False});self.assertEqual(o["selected_tickers"],["AAA","BBB"]);self.assertIn("historical_research_brief",x["AAA"]);self.assertFalse(x["AAA"]["portfolio_risk_analysis"]["is_actionable"])
if __name__=="__main__":unittest.main()
