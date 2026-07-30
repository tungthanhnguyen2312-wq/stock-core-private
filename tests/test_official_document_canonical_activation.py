import unittest
from official_document_canonical_activation import activate, conflicts, replay, SOURCE_TYPE

class OfficialActivationTests(unittest.TestCase):
 def row(self,**more): return {'metric':'profit_after_tax_total','raw_label':'PAT','raw_value':'10','period':'FY2024','scope':'consolidated','unit':'VND','sign':'positive','page':12,'document_sha256':'h','ocr_citation_id':'c','qualification':'qualified_direct_ocr'}|more
 def test_direct_authority_provenance_and_replay(self):
  a=activate('SSI',[self.row()]);r=a['records'][0];self.assertEqual(r['source'],SOURCE_TYPE);self.assertEqual(r['official_document_source']['document_sha256'],'h');self.assertEqual(replay(a),a)
 def test_source_separation_and_conflict(self):
  a=activate('PAN',[self.row()])['records'][0];provider={**a,'record_id':'provider','source':'provider_observation','official_document_source':a['official_document_source'],'value':11};self.assertEqual(conflicts([a,provider])[0]['state'],'incomparable_source_values')
 def test_partial_activation_rejects_unqualified(self):
  a=activate('SSI',[self.row(),self.row(metric='shares',qualification='unqualified_unit')]);self.assertEqual(len(a['records']),1);self.assertEqual(a['rejected'][0]['reason'],'official_observation_unqualified')
 def test_share_identity_separation(self):
  a=activate('PAN',[self.row(metric='period_end_shares_outstanding',unit='shares'),self.row(metric='weighted_average_basic_shares_outstanding',unit='shares')]);self.assertEqual({x['canonical_metric'] for x in a['records']},{'period_end_shares_outstanding','weighted_average_basic_shares_outstanding'})
if __name__=='__main__': unittest.main()
