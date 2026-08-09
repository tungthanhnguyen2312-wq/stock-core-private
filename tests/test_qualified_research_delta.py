import copy
import unittest

from qualified_research_delta import attach, compare


def brief(ticker="HPG", entity_type="corporate"):
    return {
        "schema_version": "1.0.0", "ticker": ticker, "entity_type": entity_type,
        "analysis_mode": "historical_only_qualified_data", "historical_only": True, "is_actionable": False,
        "identity": {"periods": ["2024"], "eligibility": {"status": "eligible"}},
        "qualified_facts": [{"canonical_metric": "net_income", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "source": "official", "citation_id": "citation-1", "value": 0}],
        "quality": {"earnings_cash_conversion": {"dimension": "earnings_cash_conversion", "status": "available", "supporting_facts": [{"metric": "cash", "value": 0}], "warnings": []},
                    "capital_structure": {"dimension": "capital_structure", "status": "not_applicable", "supporting_facts": [], "warnings": []}},
        "risks": {"phase_4b": [{"risk_id": "historical_conditions_can_change", "fact": {"available_dimensions": ["earnings_cash_conversion"]}}], "phase_4c": {"aggregate_posture": "limited"}},
        "catalysts": [], "scenarios": {name: {"status": "available", "required_conditions": [name], "key_dependencies": [], "invalidation_conditions": [], "missing_evidence": [], "supporting_facts": []} for name in ("bear", "base", "bull")},
        "invalidation_conditions": ["A later qualified fact conflicts with the cited historical inputs."],
        "historical_conclusion": {"status": "historically_mixed", "missing_evidence": []}, "missing_evidence": [],
        "portfolio_risk_boundary": {"liquidity": {"status": "blocked", "reason_codes": ["PRICE_BASIS_UNQUALIFIED"]}, "portfolio_context": {"status": "blocked_input"}, "allocation": {"status": "allocation_blocked"}},
    }


class QualifiedResearchDeltaTests(unittest.TestCase):
    def test_identical_briefs_have_no_material_change_and_are_deterministic(self):
        before = brief()
        first, second = compare(before, copy.deepcopy(before)), compare(copy.deepcopy(before), before)
        self.assertEqual(first, second)
        self.assertEqual(first["comparison_status"], "comparable")
        self.assertFalse(first["material_change_summary"]["material_change_detected"])
        self.assertEqual(first["fact_changes"][0]["status"], "unchanged")
        self.assertEqual(first["portfolio_gate_changes"]["liquidity"]["status"], "unchanged")

    def test_fact_semantics_preserve_zero_null_availability_and_provenance(self):
        previous, current = brief(), brief()
        current["qualified_facts"][0]["value"] = 5
        current["qualified_facts"].append({"canonical_metric": "cash", "reporting_period": "2024", "statement_scope": "consolidated", "currency": "VND", "unit_scale": 1, "source": "official", "citation_id": "citation-2", "value": None})
        result = compare(previous, current)
        changed = [item for item in result["fact_changes"] if item["status"] == "changed"][0]
        unavailable = [item for item in result["fact_changes"] if item["status"] == "added"][0]
        self.assertEqual(changed["previous"]["value"], 0)
        self.assertEqual(changed["current"]["citation_id"], "citation-1")
        self.assertIsNone(unavailable["current"]["value"])
        current["qualified_facts"][1]["value"] = 1
        self.assertEqual([item for item in compare(previous, current)["fact_changes"] if item["semantic_identity"].get("canonical_metric") == "cash"][0]["status"], "added")

    def test_matched_null_can_become_available_or_unavailable_without_removal(self):
        previous, current = brief(), brief()
        previous["qualified_facts"][0]["value"] = None
        current["qualified_facts"][0]["value"] = None
        self.assertEqual(compare(previous, current)["fact_changes"][0]["status"], "unchanged")
        current["qualified_facts"][0]["value"] = 7
        self.assertEqual(compare(previous, current)["fact_changes"][0]["status"], "became_available")
        self.assertEqual(compare(current, previous)["fact_changes"][0]["status"], "became_unavailable")

    def test_quality_direction_requires_controlled_availability_transition(self):
        previous, current = brief(), brief()
        previous["quality"]["earnings_cash_conversion"]["status"] = "unavailable"
        item = [x for x in compare(previous, current)["quality_changes"] if x["dimension"] == "earnings_cash_conversion"][0]
        self.assertEqual((item["status"], item["direction"]), ("status_changed", "improved"))
        previous["quality"]["capital_structure"]["status"] = "available"
        item = [x for x in compare(previous, current)["quality_changes"] if x["dimension"] == "capital_structure"][0]
        self.assertEqual(item["direction"], "not_comparable")

    def test_new_risk_and_missing_evidence_disappearance_are_not_resolved(self):
        previous, current = brief(), brief()
        current["risks"]["phase_4b"] = []
        current["missing_evidence"] = ["earnings_cash_conversion"]
        result = compare(previous, current)
        self.assertEqual(result["risk_changes"][0]["status"], "no_longer_supported_due_to_unavailable_evidence")
        current = brief(); current["risks"]["phase_4b"].append({"risk_id": "new_risk"})
        self.assertIn("newly_identified", [x["status"] for x in compare(previous, current)["risk_changes"]])

    def test_eligibility_fundamental_risk_and_catalyst_changes_are_producer_structured(self):
        previous, current = brief(), brief()
        current["identity"]["eligibility"]["status"] = "blocked"
        current["risks"]["phase_4c"] = {"aggregate_posture": "elevated"}
        current["catalysts"] = [{"status": "available", "condition": "Qualified later evidence is available."}]
        result = compare(previous, current)
        self.assertEqual(result["eligibility_change"]["status"], "changed")
        self.assertEqual(result["fundamental_risk_change"]["status"], "changed")
        self.assertEqual(result["catalyst_changes"][0]["status"], "newly_supported")
        self.assertIn("eligibility", result["material_change_summary"]["change_categories"])

    def test_structural_scenario_and_invalidation_changes_are_not_prose_diffs(self):
        previous, current = brief(), brief()
        current["scenarios"]["bear"]["required_conditions"].append("new qualified condition")
        current["scenarios"]["bear"]["thesis"] = "unrelated prose change"
        current["invalidation_conditions"] = [{"condition_id": "net-income-zero", "trigger": {"canonical_metric": "net_income", "operator": "equals", "value": 0}}]
        result = compare(previous, current)
        self.assertEqual(result["scenario_changes"]["bear"]["changed_fields"], ["required_conditions"])
        invalidation = [x for x in result["invalidation_changes"] if x["condition_id"] == "net-income-zero"][0]
        self.assertEqual(invalidation["trigger_evaluation"], "triggered")

    def test_qualitative_invalidation_remains_unavailable(self):
        result = compare(brief(), brief())
        self.assertEqual(result["invalidation_changes"][0]["trigger_evaluation"], "unavailable")

    def test_conclusion_ticker_mismatch_and_bank_applicability_fail_closed(self):
        previous, current = brief(), brief()
        current["historical_conclusion"]["status"] = "insufficient_evidence"
        self.assertTrue(compare(previous, current)["historical_conclusion"]["changed"])
        self.assertEqual(compare(brief("HPG"), brief("VCB", "bank"))["comparison_status"], "incomparable")
        bank_before, bank_current = brief("VCB", "bank"), brief("VCB", "bank")
        bank_before["quality"]["capital_structure"]["status"] = "not_applicable"
        self.assertEqual([x for x in compare(bank_before, bank_current)["quality_changes"] if x["dimension"] == "capital_structure"][0]["direction"], "unchanged")

    def test_missing_or_ambiguous_provenance_is_partial_or_blocked_without_fact_inference(self):
        previous, current = brief(), brief()
        current["qualified_facts"][0].pop("source")
        current["qualified_facts"][0].pop("citation_id")
        self.assertEqual(compare(previous, current)["comparison_status"], "partially_comparable")
        current = brief(); current["qualified_facts"].append(copy.deepcopy(current["qualified_facts"][0]))
        self.assertEqual(compare(previous, current)["comparison_status"], "blocked")

    def test_attach_requires_explicit_snapshot_and_keeps_pilot_archetypes(self):
        entries = {ticker: {"qualified_research_brief": brief(ticker, "bank" if ticker == "VCB" else "corporate")} for ticker in ("HPG", "VNM", "VCB")}
        previous = {"tickers": {ticker: {"qualified_research_brief": copy.deepcopy(entry["qualified_research_brief"])} for ticker, entry in entries.items()}}
        attach(entries, previous, True)
        self.assertEqual(sorted(entries), ["HPG", "VCB", "VNM"])
        self.assertEqual(entries["VCB"]["qualified_research_delta"]["comparison_status"], "comparable")
