import unittest
from ssi_securities_pilot import evaluate
from official_document_canonical_activation import activate
class SSIOfficialSourceTests(unittest.TestCase):
 def official(self,metric='brokerage_revenue',unit='VND'):
  row={'metric':metric,'raw_label':'x','raw_value':'10','period':'FY2024','scope':'consolidated','unit':unit,'sign':'positive','page':1,'document_sha256':'h','ocr_citation_id':'c','qualification':'qualified_direct_ocr'}
  return activate('SSI',[row])['records'][0]
 def test_official_source_consumption_and_provenance(self):
  r=evaluate([self.official()])['metrics']['brokerage_revenue'];self.assertEqual(r['state'],'available');self.assertEqual(r['lineage'][0]['source_type'],'official_document_observation');self.assertEqual(r['lineage'][0]['document_sha256'],'h')
 def test_partial_and_missing_sector_identity(self):
  r=evaluate([self.official('financial_assets_fvtpl')]);self.assertEqual(r['metrics']['proprietary_trading_assets']['state'],'available');self.assertEqual(r['metrics']['margin_lending_balance']['state'],'unavailable')
if __name__=='__main__':unittest.main()
