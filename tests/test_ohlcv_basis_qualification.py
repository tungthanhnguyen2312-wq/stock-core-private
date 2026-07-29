import json,sqlite3,tempfile,unittest
from pathlib import Path
from ohlcv_basis_qualification import OHLCVBasisError,qualify,validate_forward
class BasisTests(unittest.TestCase):
 def fixture(self,d):
  db=Path(d)/"db.sqlite";c=sqlite3.connect(db);c.execute("create table ohlcv(ticker text,date text,close real,source text)");c.executemany("insert into ohlcv values(?,?,?,?)",[("HPG","2024-12-31",19830,"VCI"),("VCB","2024-12-31",60560,"VCI"),("AAA","2024-01-01",10,"KBS")]);c.commit();c.close();p=Path(d)/"c.jsonl";rows=[{"provider":"VCI","source_table":"ohlcv","price_field":"close","ticker":"HPG","trading_date":"2024-12-31","value":19830,"adjustment_status":"raw_as_quoted_no_adjustment_applied","citation_id":"a"},{"provider":"VCI","source_table":"ohlcv","price_field":"close","ticker":"VCB","trading_date":"2024-12-31","value":60560,"adjustment_status":"raw_as_quoted_no_adjustment_applied","citation_id":"b"}];p.write_text("\n".join(json.dumps(x) for x in rows));return db,p
 def test_provider_separation_and_unknown_volume(self):
  with tempfile.TemporaryDirectory() as d:
   r=qualify(*self.fixture(d));self.assertTrue(r["providers"]["VCI"]["price_basis_verified"]);self.assertEqual(r["providers"]["KBS"]["price_basis"],"unknown");self.assertEqual(r["providers"]["VCI"]["volume_basis"],"unknown")
 def test_conflict_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   db,p=self.fixture(d);p.write_text(p.read_text()+"\n"+json.dumps({"provider":"VCI","source_table":"ohlcv","price_field":"close","ticker":"HPG","trading_date":"2024-12-31","value":19830,"adjustment_status":"adjusted","citation_id":"c"}));self.assertRaises(OHLCVBasisError,qualify,db,p)
 def test_forward_rejects_unknown_and_mixing(self):
  self.assertRaises(OHLCBasisError if False else OHLCVBasisError,validate_forward,{"provider":"VCI"})
  self.assertRaises(OHLCVBasisError,validate_forward,{"provider":"VCI","price_basis":"raw_as_quoted_no_adjustment_applied","price_basis_verified":True,"volume_basis":"unknown","volume_basis_verified":False,"basis_evidence_id":"x"})
if __name__=="__main__":unittest.main()