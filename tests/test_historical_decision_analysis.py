import copy
import json
import unittest

from export_ai_bundle import attach_historical_decision_analysis
from historical_decision_analysis import evaluate_historical_decision_analysis


def record(metric, value, period="2024", *, state="available"):
    return {
        "canonical_metric": metric, "value": value, "quality_state": state,
        "period_identity": {"period": period, "period_type": "annual"},
        "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1,
        "source": "financial_observation_store", "observation_ids": [f"obs-{metric}"],
        "evidence": {"evidence_id": f"evidence-{metric}", "citation_id": f"citation-{metric}"},
    }


def entry(ticker="HPG", entity_type="corporate"):
    models = {
        "growth_profitability": {"result_state": "available", "score_or_value": 0.12, "input_periods": [{"period": "2024"}]},
        "financial_strength": {"result_state": "available", "score_or_value": 2.0, "input_periods": [{"period": "2024"}]},
        "dupont_roe": {"result_state": "partial", "score_or_value": None, "input_periods": [{"period": "2024"}]},
        "earnings_quality": {"result_state": "available", "score_or_value": 3.0, "input_periods": [{"period": "2024"}]},
        "bank_financial_quality": {"result_state": "available", "score_or_value": None, "input_periods": [{"period": "2024"}]},
    }
    return {
        "entity_type": entity_type,
        "financial_canonical": {"status": "available", "records": [record("revenue", 100), record("net_income", 10)]},
        "fundamental_quality": {"schema_version": "1.0.0", "models": models},
        "fundamental_quality_evidence": {"status": "available", "metrics": {
            "operating_cash_flow_less_net_income": {"qualification_status": "qualified", "value": 5},
        }},
        "historical_capital_structure": {"status": "available", "metrics": {
            "net_debt_to_equity": {"qualification_status": "qualified", "value": 0.2},
            "cash_to_debt": {"qualification_status": "qualified", "value": 0.5},
        }},
    }


class HistoricalDecisionAnalysisTests(unittest.TestCase):
    def test_hpg_deterministic_structured_historical_result(self):
        source = entry("HPG")
        first = evaluate_historical_decision_analysis("HPG", source)
        second = evaluate_historical_decision_analysis("HPG", copy.deepcopy(source))
        self.assertEqual(first, second)
        self.assertEqual(first["eligibility"]["status"], "eligible")
        self.assertEqual(first["analysis_mode"], "historical_only_qualified_data")
        self.assertTrue(first["historical_only"])
        self.assertFalse(first["market_dependent"])
        self.assertFalse(first["is_actionable"])
        self.assertEqual(set(first["scenarios"]), {"bear", "base", "bull"})
        self.assertTrue(first["invalidation_conditions"])
        self.assertTrue(first["provenance"]["qualified_fact_references"])

    def test_vnm_positive_result_and_missing_optional_capital_evidence(self):
        source = entry("VNM")
        source["historical_capital_structure"] = {"status": "unavailable", "blocking_reasons": ["capital_inputs_missing"]}
        result = evaluate_historical_decision_analysis("VNM", source)
        self.assertEqual(result["eligibility"]["status"], "eligible")
        self.assertEqual(result["quality_assessment"]["capital_structure"]["status"], "unavailable")
        self.assertIn("capital_structure", result["scenarios"]["base"]["missing_evidence"])
        self.assertEqual(result["historical_conclusion"]["status"], "historically_mixed")

    def test_vcb_uses_bank_applicability_not_corporate_capital_ratios(self):
        result = evaluate_historical_decision_analysis("VCB", entry("VCB", "bank"))
        self.assertEqual(result["eligibility"]["status"], "eligible")
        self.assertEqual(result["quality_assessment"]["bank_financial_quality"]["status"], "available")
        self.assertEqual(result["quality_assessment"]["capital_structure"]["status"], "not_applicable")
        self.assertNotIn("profitability_and_resilience", result["quality_assessment"])

    def test_missing_or_unqualified_canonical_data_fails_closed(self):
        source = entry("HPG")
        source["financial_canonical"] = {"status": "available", "records": [record("revenue", 100, state="unknown")]}
        result = evaluate_historical_decision_analysis("HPG", source)
        self.assertEqual(result["eligibility"]["status"], "insufficient_evidence")
        self.assertEqual(result["historical_conclusion"]["status"], "insufficient_evidence")
        self.assertEqual(result["scenarios"]["base"]["status"], "unavailable")

    def test_zero_is_a_qualified_fact_but_null_is_not(self):
        source = entry("HPG")
        source["financial_canonical"]["records"] = [record("net_income", 0), record("revenue", None)]
        result = evaluate_historical_decision_analysis("HPG", source)
        self.assertEqual(result["eligibility"]["qualified_fact_count"], 1)
        self.assertEqual(result["provenance"]["qualified_fact_references"][0]["value"], 0)

    def test_catalyst_is_explicitly_unavailable_when_no_dimension_is_qualified(self):
        source = entry("HPG")
        source["fundamental_quality"] = {"models": {}}
        source["fundamental_quality_evidence"] = {"status": "unavailable", "metrics": {}}
        source["historical_capital_structure"] = {"status": "unavailable"}
        result = evaluate_historical_decision_analysis("HPG", source)
        self.assertEqual(result["eligibility"]["status"], "partially_eligible")
        self.assertEqual(result["catalysts"][0]["status"], "unavailable")
        self.assertEqual(result["historical_conclusion"]["status"], "insufficient_evidence")

    def test_export_attachment_is_pilot_only_and_additive(self):
        entries = {"HPG": entry("HPG"), "ABC": entry("ABC")}
        attached = attach_historical_decision_analysis(entries, True)
        self.assertIn("historical_decision_analysis", attached["HPG"])
        self.assertNotIn("historical_decision_analysis", attached["ABC"])
        self.assertEqual(attach_historical_decision_analysis({"HPG": entry("HPG")}, False)["HPG"].keys(), entry("HPG").keys())

    def test_prohibited_market_outputs_are_not_emitted(self):
        result = evaluate_historical_decision_analysis("HPG", entry("HPG"))
        payload = json.dumps(result, sort_keys=True).lower()
        for forbidden in ('"buy"', '"sell"', '"hold"', "target price", "portfolio weight", "position sizing"):
            self.assertNotIn(forbidden, payload)
        self.assertNotIn("target_price", result)
        self.assertNotIn("current_valuation", result)
        self.assertNotIn("ranking", result)


if __name__ == "__main__":
    unittest.main()
