from __future__ import annotations
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from field_temporal_contract import stable_id
import current_common_shares_official_evidence_acquisition as c
import tools.derive_current_common_shares_official_evidence_acquisition as runner
class Tests(unittest.TestCase):
 def test_exact_cohort_manifest_and_identity(self):
  a=runner.build(); self.assertEqual(['GAS','HPG','NVL','PAN','POW','PVD','QNS','SSI','VCB','VNM','VRE'],a['cohort']); p=dict(a);d=p.pop('artifact_sha256');i=p.pop('artifact_identity');self.assertEqual(d,stable_id(p));self.assertEqual('current_common_shares_official_evidence_acquisition:'+d,i)
 def test_planned_and_executed_cases_remain_distinct(self):
  rows={r['ticker']:r for r in runner.build()['symbol_results']}; self.assertEqual(c.ACTION_UNRESOLVED,rows['SSI']['result']);self.assertEqual(c.ACTION_UNRESOLVED,rows['VCB']['result']);self.assertEqual(8442964520,rows['HPG']['current_common_shares']);self.assertFalse(rows['HPG']['covered_through_valuation_date'])
 def test_all_denominators_fail_closed(self):
  a=runner.build();self.assertEqual(0,a['summary']['qualified_for_valuation_date']);self.assertTrue(all(not r['eligible'] for r in a['denominator_eligibility']))
if __name__=='__main__': unittest.main()
