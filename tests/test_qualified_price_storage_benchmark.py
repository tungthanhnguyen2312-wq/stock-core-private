import sqlite3,tempfile,unittest
from pathlib import Path
from qualified_price_storage_benchmark import BASIS,export_vci_price,_equal
class PriceBenchmarkTests(unittest.TestCase):
 def test_vci_only_export_and_determinism(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/"x.db";c=sqlite3.connect(db);c.execute("create table ohlcv(ticker text,date text,open real,high real,low real,close real,volume integer,source text)");c.executemany("insert into ohlcv values(?,?,?,?,?,?,?,?)",[("VNM","2024-01-01",1,2,0.5,1.5,9,"VCI"),("AAA","2024-01-01",1,2,0.5,1.5,9,"KBS")]);c.commit();c.close();a=export_vci_price(db,Path(d)/"a.parquet");b=export_vci_price(db,Path(d)/"b.parquet");self.assertEqual(a["rows"],1);self.assertEqual(a["kbs_rows_excluded"],1);self.assertEqual(a["parquet_hash"],b["parquet_hash"]);self.assertIn("price_basis",a["schema"])
 def test_parity_precision_and_nulls(self):
  self.assertEqual(_equal([{"x":1.0,"n":None}],[{"x":1.0000000001,"n":None}]),(True,1.000000082740371e-10));self.assertFalse(_equal([{"x":None}],[{"x":1}])[0])
if __name__=="__main__":unittest.main()