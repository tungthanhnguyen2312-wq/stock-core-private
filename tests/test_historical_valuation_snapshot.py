import unittest
from historical_valuation_snapshot import build_snapshot,replay
class T(unittest.TestCase):
 def x(self,bank=False):return {"ticker":"VCB" if bank else "HPG","entity_type":"bank" if bank else "corporate","financial_period":"2024","publication_cutoff":"2025-03-01","price_date":"2025-03-02","price":10,"shares":100,"financial":{"net_income":20,"equity":50,"sales":100,"ebitda":25},"citations":["c"],"source_hashes":["h"]}
 def test_bank_gate_lineage_and_determinism(self):
  r=build_snapshot(self.x(True));self.assertEqual(r["methods"]["ev_sales"]["state"],"inapplicable");self.assertEqual(r,build_snapshot(self.x(True)))
 def test_cutoff_and_ordering(self):
  x=self.x();x["price_date"]="2025-02-28";self.assertRaises(ValueError,build_snapshot,x);a=build_snapshot(self.x());b=build_snapshot(dict(self.x(),ticker="HPG",price_date="2025-03-03"));self.assertEqual(replay([b,a]),[a,b])
if __name__=="__main__":unittest.main()