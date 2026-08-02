import sqlite3, tempfile, unittest
from pathlib import Path
from tools.discover_official_price_events import discover, official_locator_results, select_candidates

class DiscoveryTests(unittest.TestCase):
 def test_selection_deduplicates_overlaps(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.db'; c=sqlite3.connect(p); c.execute('create table corporate_event_records(ticker,provider_event_id,event_code,exright_date,exercise_ratio)'); c.executemany('insert into corporate_event_records values(?,?,?,?,?)',[('HPG','b','ISS','2024-01-02',.2),('HPG','a','ISS','2024-01-02',.1),('VNM','c','DIV','2024-01-03',.2)]); c.commit(); c.close()
   r=select_candidates(p,as_of='2024-12-31'); self.assertEqual([x['provider_event_id'] for x in r['accepted']],['b']); self.assertEqual(r['excluded'][0]['reason'],'overlapping_candidate_action')
 def test_only_official_locator_urls_survive(self):
  c={'ticker':'HPG','candidate_ex_date':'2024-01-02'}; rows=official_locator_results(c,'https://news.example/a https://www.hoaphat.com.vn/a.pdf',discovered_at='t'); self.assertEqual(rows[0]['authority'],'hoaphat.com.vn')
 def test_search_is_locator_not_evidence(self):
  c={'ticker':'HPG','candidate_ex_date':'2024-01-02'}; r=discover([c],search=lambda _: 'https://www.hoaphat.com.vn/a.pdf',discovered_at='t'); self.assertNotIn('qualified_for_price_basis_test',r['locators'][0])

if __name__=='__main__': unittest.main()
