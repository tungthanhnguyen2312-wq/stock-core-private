import unittest
from corporate_action_evidence_registry import promote_official_stock_dividend,shadow_share_factor
from vcb_adjustment_ledger import build_shadow_ledger
class Tests(unittest.TestCase):
 def test_multiplier_only_lineage_is_deterministic(self):
  p={"ticker":"VCB","provider_event_id":"6708f3f70ec61045ab800869","exercise_ratio":.495,"record_date":"2025-03-13"};o={"ticker":"VCB","provider_event_id":"6708f3f70ec61045ab800869","ratio":.495,"approval_date":"2025-01-15","record_date":"2025-03-13","issuance_date":"2025-05-09","listing_date":"2025-05-09","completion_date":"2025-05-09","lifecycle":"completed","source_hash":"8a79e8b0ca1381cd1cac12a82818f382052e55a323e9386ebbd54a7f93e712ef","citation_id":"vsdc-182319","citation":"VSDC notice"};e=promote_official_stock_dividend(p,o);f=shadow_share_factor(e);a=build_shadow_ledger(e,f);self.assertEqual(a,build_shadow_ledger(e,f));self.assertFalse(a["price_factor_applied"]);self.assertEqual(a["share_basis_status"],"multiplier_only")
 def test_unqualified_application_rejected(self):
  with self.assertRaises(ValueError):build_shadow_ledger({}, {})
if __name__=="__main__":unittest.main()