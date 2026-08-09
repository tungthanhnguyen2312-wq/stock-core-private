import unittest
from qualified_research_brief import build
class T(unittest.TestCase):
 def test_compact_deterministic_and_bound(self):
  e={"entity_type":"bank","historical_decision_analysis":{"data_periods_used":["2024"],"eligibility":{"status":"eligible"},"provenance":{"qualified_fact_references":[{"value":0,"canonical_metric":"x"}]},"quality_assessment":{"capital":{"status":"not_applicable"}},"risks":[],"catalysts":[],"scenarios":{"bear":{},"base":{},"bull":{}},"invalidation_conditions":["x"],"historical_conclusion":{"status":"historically_mixed"},"missing_evidence":[]},"portfolio_risk_analysis":{"liquidity":{"status":"blocked"},"portfolio_considerations":{"actual_portfolio_fit":{"status":"blocked_input"}},"allocation_eligibility":{"eligible":False}}};a=build("VCB",e);self.assertEqual(a,build("VCB",e));self.assertFalse(a["is_actionable"]);self.assertEqual(a["qualified_facts"][0]["value"],0);self.assertEqual(a["quality"]["capital"]["status"],"not_applicable")
