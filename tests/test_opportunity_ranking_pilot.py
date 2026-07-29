import unittest
from opportunity_ranking_pilot import build_snapshot,digest
class T(unittest.TestCase):
 def data(self):return {k:{"cutoff":"2025-03-01","axes":{a:{"state":"available"} for a in ("quality","valuation","technical","relative_strength","catalyst","downside","data_confidence")},"scenarios":{"bear":{},"base":{},"bull":{}},"invalidation":"x"} for k in ("HPG","VNM","VCB")}
 def test_sector_cutoff_determinism_and_no_recommendation(self):
  x=self.data();x["VCB"]["axes"]["valuation"]["ev_ebitda"]=1;r=build_snapshot(x,"2025-03-01");self.assertNotIn("ev_ebitda",r["tickers"][2]["axes"]["valuation"]);self.assertEqual(digest(r),digest(build_snapshot(x,"2025-03-01")));self.assertEqual(r["recommendations_emitted"],0)
 def test_missing_cutoff_partial(self):
  x=self.data();x["VNM"]["cutoff"]="late";self.assertEqual(build_snapshot(x,"2025-03-01")["comparability"],"partial_comparability")
if __name__=="__main__":unittest.main()