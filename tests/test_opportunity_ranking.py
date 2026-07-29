import unittest
from opportunity_ranking import evaluate_opportunity, rank_opportunities
from scenario_analysis import evaluate_scenario_analysis


def fact(metric="net_income"):
    return {"value": 1, "period_identity": {"period": "2024", "period_type": "annual"}, "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "source": "test", "observation_ids": ["obs-" + metric], "citation_id": "cit-" + metric, "evidence_id": "evi-" + metric}


def entry(*, bank=False, stale=False, conflicting=False):
    used = fact()
    if conflicting:
        used.update({"citation_id": None, "evidence_id": None, "component_lineage": [{"canonical_metric": "debt", "derivation_role": "required_component", "value": 1, "period_identity": {"period": "2024", "period_type": "annual"}, "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "source": "test", "observation_ids": ["obs"], "citation_id": "cit", "evidence_id": "evi"}, {"canonical_metric": "debt", "derivation_role": "required_component", "value": 1, "period_identity": {"period": "2024", "period_type": "annual"}, "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "source": "test", "observation_ids": ["obs"], "citation_id": "cit", "evidence_id": "evi"}]})
    quality = {"bank_financial_quality" if bank else "financial_strength": {"result_state": "available", "used_input_facts": {"net_income": used}}}
    if bank: quality["financial_strength"] = {"result_state": "inapplicable"}
    return {"fundamental_quality": {"models": quality}, "relative_valuation": {"methods": {"pb": {"state": "available", "is_actionable": True, "provenance": {"citation_id": "pb-cit"}}, "ev_ebitda": {"state": "inapplicable" if bank else "unavailable", "is_actionable": False}}}, "freshness": {"daily_prices": {"is_actionable": not stale}, "technical_signals": {"is_actionable": not stale}}, "analysis_readiness": {"domains": {"market_technical": {"state": "ready" if not stale else "degraded"}}}, "ta_signal": {"above_sma50": True}, "corporate_intelligence": {}}


class OpportunityRankingTests(unittest.TestCase):
    def test_explicit_dimensions_are_deterministic_and_partial_without_catalyst(self):
        source = entry(); first = evaluate_opportunity(source, ticker="HPG", entity_type="corporate")
        self.assertEqual(first, evaluate_opportunity(source, ticker="HPG", entity_type="corporate"))
        self.assertEqual(first["state"], "partial")
        self.assertEqual(first["dimensions"]["financial_quality"]["state"], "available")
        self.assertEqual(first["dimensions"]["catalyst_evidence"]["state"], "unknown")
        self.assertEqual(first["inferences"], []); self.assertEqual(first["hypotheses"], [])

    def test_conflicting_lineage_and_stale_technical_fail_closed(self):
        conflict = evaluate_opportunity(entry(conflicting=True), ticker="HPG", entity_type="corporate")
        self.assertEqual(conflict["dimensions"]["financial_quality"]["state"], "incomparable")
        stale = evaluate_opportunity(entry(stale=True), ticker="VNM", entity_type="corporate")
        self.assertEqual(stale["dimensions"]["technical_current_market_readiness"]["state"], "unavailable")
        self.assertEqual(stale["dimensions"]["downside_invalidation"]["state"], "unknown")

    def test_bank_sector_gating_rejects_corporate_ev_and_preserves_bank_quality(self):
        valid = evaluate_opportunity(entry(bank=True), ticker="VCB", entity_type="bank")
        self.assertEqual(valid["dimensions"]["financial_quality"]["state"], "available")
        broken = entry(bank=True); broken["relative_valuation"]["methods"]["ev_ebitda"] = {"state": "available", "is_actionable": True}
        self.assertEqual(evaluate_opportunity(broken, ticker="VCB", entity_type="bank")["dimensions"]["valuation"]["state"], "incomparable")

    def test_ranking_tie_breaks_by_ticker_without_magic_score(self):
        ranked = rank_opportunities({"VNM": entry(), "HPG": entry()})
        self.assertEqual([row["ticker"] for row in ranked["ordered_tickers"]], ["HPG", "VNM"])
        self.assertEqual(ranked["ranking_kind"], "evidence_availability_ordering_only")
        self.assertFalse(ranked["is_actionable"])

    def test_scenarios_keep_fact_warning_inference_hypothesis_classes_separate(self):
        opportunity = evaluate_opportunity(entry(), ticker="HPG", entity_type="corporate")
        scenario = evaluate_scenario_analysis({"freshness": entry()["freshness"], "readiness": entry()["analysis_readiness"]["domains"], "technical": {"above_sma50": True}, "opportunity": opportunity}, "2026-07-29T00:00:00Z")
        self.assertEqual(scenario["scenarios"]["bull"]["state"], "available")
        self.assertIn("catalysts", scenario["scenarios"]["base"])
        self.assertIn("downside", scenario["scenarios"]["bear"])
        self.assertIn("time_horizon", scenario["scenarios"]["bull"])
        self.assertTrue(all(not isinstance(item, str) for item in scenario["evidence_inventory"]["facts"]))

if __name__ == "__main__": unittest.main()
