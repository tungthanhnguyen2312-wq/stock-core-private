from datetime import datetime, timezone
import unittest
from freshness_history import evaluate_analysis_readiness
REF = datetime(2026, 7, 26, 12, tzinfo=timezone.utc)
def envelope(status="current", actionable=True): return {"freshness_status": status, "is_actionable": actionable, "as_of_date": "2026-07-25", "generated_at": "2026-07-25T00:00:00+00:00"}
def corporate(status="available", actionable=True, event_cap=False):
    core = {name: {"status": status, "freshness": envelope(actionable=actionable)} for name in ("company_profile", "company_subsidiaries", "ownership_structure", "major_shareholders")}
    core["corporate_events"] = {"status": "partial" if event_cap else status, "coverage_status": "partial_unqualified_50_row_cap" if event_cap else "complete", "freshness": envelope(actionable=actionable)}
    return core
class AnalysisReadinessTests(unittest.TestCase):
    def test_ready_and_repeatable(self):
        freshness = {"daily_prices": envelope(), "technical_signals": envelope(), "financial_statements": envelope()}
        one = evaluate_analysis_readiness(freshness=freshness, corporate_intelligence=corporate(), reference_at=REF); two = evaluate_analysis_readiness(freshness=freshness, corporate_intelligence=corporate(), reference_at=REF)
        self.assertEqual(one, two); self.assertEqual(one["domains"]["combined_ai_analysis"]["state"], "ready")
    def test_historical_and_stale_are_degraded_not_ready(self):
        result = evaluate_analysis_readiness(freshness={"daily_prices": envelope("stale", False), "technical_signals": envelope(), "financial_statements": envelope("historical", False)}, corporate_intelligence=corporate(), reference_at=REF)
        self.assertEqual(result["domains"]["market_technical"]["state"], "degraded"); self.assertEqual(result["domains"]["fundamental"]["state"], "degraded")
    def test_missing_partial_and_incomplete_fail_closed(self):
        result = evaluate_analysis_readiness(freshness={"daily_prices": envelope(), "technical_signals": envelope(), "financial_statements": envelope()}, corporate_intelligence=corporate(event_cap=True), reference_at=REF)
        self.assertEqual(result["domains"]["corporate_events"]["state"], "degraded"); self.assertFalse(result["domains"]["corporate_events"]["is_actionable"])
        missing = evaluate_analysis_readiness(freshness={}, corporate_intelligence=None, reference_at=REF); self.assertEqual(missing["domains"]["market_technical"]["state"], "unknown")
        blocked = evaluate_analysis_readiness(freshness={"daily_prices": envelope(), "technical_signals": envelope(), "financial_statements": envelope()}, corporate_intelligence=corporate(status="partial", actionable=False), reference_at=REF); self.assertEqual(blocked["domains"]["corporate_intelligence"]["state"], "blocked")
    def test_null_and_zero_are_untouched(self):
        source = {"nullable": None, "zero": 0}; evaluate_analysis_readiness(freshness={"daily_prices": envelope(), "technical_signals": envelope(), "financial_statements": envelope()}, corporate_intelligence=corporate(), reference_at=REF); self.assertEqual(source, {"nullable": None, "zero": 0})
if __name__ == "__main__": unittest.main()
