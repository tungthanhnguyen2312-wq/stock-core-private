import unittest
from official_document_canonical_activation import activate
from official_document_downstream_shadow import build,replay
class ShadowTests(unittest.TestCase):
 def row(self,m):return {'metric':m,'raw_label':m,'raw_value':'10','period':'FY2024','scope':'consolidated','unit':'number_of_shares' if 'shares' in m else 'VND','sign':'positive','page':1,'document_sha256':'h','ocr_citation_id':'c','qualification':'qualified_direct_ocr'}
 def artifact(self):return {'activations':{'PAN':activate('PAN',[self.row('period_end_shares_outstanding')]),'SSI':activate('SSI',[self.row('brokerage_revenue'),self.row('financial_assets_fvtpl')])}}
 def test_official_provenance_and_replay(self):
  x=build(self.artifact());r=x['SSI']['outputs']['securities.brokerage_revenue'];self.assertEqual(r['state'],'available');self.assertEqual(r['input_lineage'][0]['source_type'],'official_document_observation');self.assertEqual(replay(x),x)
 def test_sector_and_partial_gates(self):
  x=build(self.artifact());self.assertEqual(x['SSI']['outputs']['relative.ev_sales']['state'],'inapplicable');self.assertEqual(x['SSI']['outputs']['securities.margin_lending_balance']['state'],'unavailable');self.assertEqual(x['PAN']['outputs']['share_basis.0']['state'],'available')
 def test_missing_input_behavior(self):
  x=build(self.artifact());self.assertEqual(x['PAN']['outputs']['intrinsic.fcff_dcf']['state'],'unavailable');self.assertTrue(x['PAN']['outputs']['intrinsic.fcff_dcf']['missing_inputs'])
if __name__=='__main__':unittest.main()
