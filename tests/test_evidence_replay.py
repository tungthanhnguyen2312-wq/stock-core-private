import json,tempfile,unittest
from pathlib import Path
from evidence_replay import replay

def fixture(root):
 e=root/'data'/'official-evidence';e.mkdir(parents=True);(e/'x.pdf').write_bytes(b'x');h='2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881';(e/'manifest.json').write_text(json.dumps({'records':[{'evidence_id':'e','filename':'x.pdf','sha256':h,'qualification_state':'qualified'}]}));(root/'data'/'financial-observations').mkdir(parents=True);(root/'data'/'financial-observations'/'observations.jsonl').write_text('');
 for n in ['qualification_citations.jsonl','market_price_citations.jsonl','ebitda_component_citations.jsonl']:(e/n).write_text('')
 rows=[{'ticker':'HPG','reporting_period':'2024','identity_type':'period_end_shares_outstanding','citation_id':'h','evidence_id':'e'},{'ticker':'VNM','reporting_period':'2024','identity_type':'period_end_shares_outstanding','citation_id':'v','evidence_id':'e'},{'ticker':'VCB','reporting_period':'2024','identity_type':'weighted_average_basic_shares_outstanding','citation_id':'b','evidence_id':'e'}];(e/'share_basis_citations.jsonl').write_text('\n'.join(json.dumps(x) for x in rows))
class T(unittest.TestCase):
 def test_idempotent_and_coexist(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);fixture(r);a=replay(r,r/'x.db');b=replay(r,r/'x.db');self.assertEqual(a['items'],b['items']);self.assertTrue(b['parity_pass'])
 def test_dangling_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);fixture(r);p=r/'data'/'official-evidence'/'share_basis_citations.jsonl';p.write_text(json.dumps({'ticker':'VCB','reporting_period':'2024','identity_type':'bad','citation_id':'x','evidence_id':'no'}));
   with self.assertRaises(ValueError):replay(r,r/'x.db')
class ReplayContractRegression(unittest.TestCase):
 def test_market_price_and_statement_type_identity(self):
  import sqlite3
  from evidence_replay import init,validate
  with tempfile.TemporaryDirectory() as d:
   c=sqlite3.connect(Path(d)/'x.db');init(c)
   rows=[('manifest','e','{}'),('observations','a','{}'),('observations','b','{}'),('market_price','m',json.dumps({'citation_id':'m'})),('qualification','q1',json.dumps({'ticker':'HPG','reporting_period':'2024','raw_item_id':'minority_interests','raw_statement_type':'balance_sheet','citation_id':'q1','evidence_id':'e','observation_id':'a'})),('qualification','q2',json.dumps({'ticker':'HPG','reporting_period':'2024','raw_item_id':'minority_interests','raw_statement_type':'income_statement','citation_id':'q2','evidence_id':'e','observation_id':'b'}))]
   for k,i,x in rows:c.execute('insert into replay_items values(?,?,?,?)',(k,i,'h',x))
   self.assertEqual(validate(c),[]);c.close()

if __name__=='__main__':unittest.main()