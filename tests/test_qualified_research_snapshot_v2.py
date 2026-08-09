import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qualified_research_snapshot_v2 import PRODUCTION_UNIVERSE, build

class SnapshotV2Tests(unittest.TestCase):
 def test_explicit_universe_and_deterministic_identity(self):
  bundle={"tickers":{"POW":{"ticker_capability_matrix":{"research":{"qualified_research_brief":{"status":"available"}}}}}}
  a=build(bundle,source_identity={"bundle":"served"}); b=build(bundle,source_identity={"bundle":"served"})
  self.assertEqual(a,b);self.assertEqual([x["ticker"] for x in a["tickers"]],list(PRODUCTION_UNIVERSE));self.assertNotIn("VCB",PRODUCTION_UNIVERSE)
  self.assertEqual(next(x for x in a["tickers"] if x["ticker"]=="POW")["research_status"],"available")
 def test_absent_production_ticker_is_explicit_unknown(self):
  row=next(x for x in build({"tickers":{}},source_identity={})["tickers"] if x["ticker"]=="QNS")
  self.assertEqual(row["research_status"],"unknown")
if __name__=='__main__': unittest.main()
