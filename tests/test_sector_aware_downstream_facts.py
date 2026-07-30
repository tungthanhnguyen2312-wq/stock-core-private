import unittest
from sector_aware_downstream_facts import export,replay
class ExportTests(unittest.TestCase):
 def shadow(self):
  l={'canonical_input':'brokerage_revenue','record_id':'r','value':10,'source_type':'official_document_observation','document_sha256':'h','citation_id':'c','period':{'period':'2024'},'scope':'consolidated','unit':'VND'}
  return {'input_source':'phase7c_official_document_canonical_activation_only','PAN':{'outputs':{'share_basis.0':{'state':'available','formula_version':'x','input_lineage':[dict(l,canonical_input='period_end_shares_outstanding',unit='shares')]}}},'SSI':{'outputs':{'securities.brokerage_revenue':{'state':'available','formula_version':'x','input_lineage':[l]},'securities.margin_lending_balance':{'state':'unavailable','formula_version':'x','missing_inputs':['missing'],'warnings':[],'input_lineage':[]},'relative.ev_sales':{'state':'inapplicable','formula_version':'x','missing_inputs':[],'warnings':['sector'],'input_lineage':[]}},'sector_applicability':{'corporate_debt':'inapplicable'}}}
 def test_schema_lineage_status_and_replay(self):
  x=export(self.shadow());self.assertEqual(replay(x),x);self.assertEqual(x['facts'][0]['official_document_source_type'],'official_document_observation');self.assertTrue(all('path' not in str(f) for f in x['facts']))
 def test_ticker_isolation_and_no_recomputation(self):
  x=export(self.shadow());self.assertEqual(sum(f['ticker']=='PAN' for f in x['facts']),1);self.assertEqual(next(f for f in x['facts'] if f['fact_identity']=='brokerage_revenue')['value'],10)
if __name__=='__main__':unittest.main()
