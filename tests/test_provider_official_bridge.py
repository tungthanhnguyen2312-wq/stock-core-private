import unittest
from provider_official_bridge import *
class BridgeTests(unittest.TestCase):
 def snapshot(self):return provider_snapshot(provider='VCI',method='income_statement',version='4.0.4',parameters={'period':'year'},retrieved_at='2026-07-30T00:00:00Z',raw_payload=[{'x':1}])
 def rows(self):
  p=provider_observation(self.snapshot(),identity='profit_after_tax_total',period='2024',scope='consolidated',unit='VND',sign='positive',raw_item_id='net_profit_loss_after_tax',raw_label='PAT',value=10)
  o={'identity':'profit_after_tax_total','reporting_period':'2024','statement_scope':'consolidated','unit':'VND','sign':'positive','raw_value':10,'raw_item_id':'net_profit_loss_after_tax','citation_id':'c','document_sha256':'h'}
  return p,o
 def test_exact_match_and_deterministic_replay(self):
  p,o=self.rows();a=exact_links([p],[o]);self.assertEqual(a,exact_links([p],[o]));self.assertEqual(replay(a),a);self.assertEqual(canonical_promotions(a['links'])[0]['canonical_identity'],'profit_after_tax_total')
 def test_partial_bridge_and_identity_separation(self):
  p,o=self.rows();shares=provider_observation(self.snapshot(),identity='period_end_shares_outstanding',period='2024',scope='consolidated',unit='shares',sign='positive',raw_item_id='shares',raw_label='shares',value=20);a=exact_links([p,shares],[o]);self.assertEqual(len(a['links']),1);self.assertEqual(a['rejected'][0]['reason'],'official_identity_missing')
 def test_drift_and_unit_rejection(self):
  p,o=self.rows();drift={**p,'raw_value':11};unit={**p,'unit':'shares'};a=exact_links([drift,unit],[o]);self.assertEqual(len(a['links']),0);self.assertTrue(all(x['reason']=='exact_compatibility_failed' for x in a['rejected']))
if __name__=='__main__':unittest.main()