from __future__ import annotations
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from field_temporal_contract import stable_id
import provider_reported_current_valuation_proxy as p
import tools.derive_provider_reported_current_valuation_proxy as runner
class Tests(unittest.TestCase):
 def test_real_retained_proxy_preserves_identity_and_counts(self):
  a=runner.build();self.assertEqual(11,len(a['corpus_results']));self.assertEqual(9,a['broader_retained_universe_denominators']['proxy_market_cap_produced']);self.assertEqual(1683,a['broader_retained_universe_denominators']['candidate_universe']);h=next(x for x in a['corpus_results'] if x['ticker']=='HPG');self.assertEqual('issued_shares',h['provider_issued_shares']['semantic_identity']);self.assertFalse(h['provider_issued_shares']['common_outstanding_equivalence'])
 def test_corporate_action_and_sector_gates_fail_closed(self):
  rows={x['ticker']:x for x in runner.build()['corpus_results']};self.assertIsNone(rows['SSI']['provider_issued_share_market_cap_proxy']['value']);self.assertIsNone(rows['VCB']['provider_issued_share_market_cap_proxy']['value']);self.assertFalse(rows['SSI']['metrics']['ev_sales_provider_issued_share_proxy']['sector_applicable'])
 def test_identity_and_authority_are_explicit(self):
  a=runner.build();q=dict(a);d=q.pop('artifact_sha256');i=q.pop('artifact_identity');self.assertEqual(d,stable_id(q));self.assertEqual('provider_reported_current_valuation_proxy:'+d,i);self.assertTrue(all(x['authority']==p.AUTHORITY for x in a['corpus_results']))
if __name__=='__main__':unittest.main()
