import unittest
import pandas as pd
from financial_canonicalization import canonicalize_financial_rows, derive_ttm
class FinancialCanonicalizationTests(unittest.TestCase):
    def rows(self): return pd.DataFrame([{"ticker":"AAA","period":"2025-Q1","period_type":"quarter","period_calendar_end":"2025-03-31","revenue":1,"net_profit":-2,"cash":0,"statement_currency":"VND","statement_scale":1,"statement_scope":"consolidated"},{"ticker":"AAA","period":"2025-Q2","period_type":"quarter","period_calendar_end":"2025-06-30","revenue":2,"net_profit":None,"cash":0,"statement_currency":"VND","statement_scale":1,"statement_scope":"consolidated"},{"ticker":"AAA","period":"2025-Q3","period_type":"quarter","period_calendar_end":"2025-09-30","revenue":3,"net_profit":4,"cash":0,"statement_currency":"VND","statement_scale":1,"statement_scope":"consolidated"},{"ticker":"AAA","period":"2025-Q4","period_type":"quarter","period_calendar_end":"2025-12-31","revenue":4,"net_profit":5,"cash":0,"statement_currency":"VND","statement_scale":1,"statement_scope":"consolidated"}])
    def test_period_identity_null_zero_negative_and_determinism(self):
        one=canonicalize_financial_rows(self.rows(),"AAA"); two=canonicalize_financial_rows(self.rows(),"AAA"); self.assertEqual(one,two)
        values={(r['canonical_metric'],r['period_identity']['period']):r['value'] for r in one['records']}; self.assertEqual(values['cash_and_equivalents','2025-Q1'],0); self.assertEqual(values['net_income','2025-Q1'],-2); self.assertIsNone(values['net_income','2025-Q2'])
    def test_ttm_requires_four_compatible_quarters(self):
        records=canonicalize_financial_rows(self.rows(),"AAA")['records']; ttm=derive_ttm(records,'revenue','consolidated'); self.assertEqual(ttm['value'],10); self.assertEqual(ttm['period_identity']['period_type'],'ttm')
        incomplete=canonicalize_financial_rows(self.rows().iloc[:3],"AAA")['records']; self.assertEqual(derive_ttm(incomplete,'revenue','consolidated')['quality_state'],'unavailable')
    def test_scope_duplicate_conflict_and_malformed(self):
        frame=self.rows().iloc[:1].copy(); duplicate=frame.copy(); duplicate.loc[0,'revenue']=9; merged=pd.concat([frame,duplicate],ignore_index=True); result=canonicalize_financial_rows(merged,"AAA"); self.assertTrue(any(r['quality_state']=='incomparable' for r in result['records'] if r['canonical_metric']=='revenue'))
        bad=frame.copy(); bad.loc[0,'period']='bad'; self.assertEqual(canonicalize_financial_rows(bad,'AAA')['invalid_periods'][0]['reason'],'period_malformed')
        separate=frame.copy(); separate.loc[0,'statement_scope']='separate'; both=canonicalize_financial_rows(pd.concat([frame,separate],ignore_index=True),'AAA'); self.assertEqual({r['statement_scope'] for r in both['records'] if r['canonical_metric']=='revenue'},{'consolidated','separate'})
if __name__=='__main__': unittest.main()
