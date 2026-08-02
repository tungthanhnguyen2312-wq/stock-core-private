import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from fundamental_quality import evaluate_fundamental_quality


def r(metric, value, period="2025", **extra):
    record={"canonical_metric":metric,"value":value,"quality_state":"available","statement_scope":"consolidated","period_identity":{"period":period,"period_type":"annual"},"currency":"VND","unit_scale":1,"source":"test","observation_ids":[f"obs-{metric}"],"evidence":{"citation_id":f"cit-{metric}","evidence_id":f"evi-{metric}"}}
    record.update(extra)
    return record


class FundamentalQualityTests(unittest.TestCase):
    def test_complete_corporate_is_deterministic_and_lineage_rich(self):
        records=[r("revenue",100),r("net_income",10),r("total_assets",50),r("shareholders_equity",25),r("operating_cash_flow",12),r("total_debt",20),r("cash_and_equivalents",5)]
        result=evaluate_fundamental_quality({"records":records},"corporate")
        self.assertEqual(result,evaluate_fundamental_quality({"records":records},"corporate"))
        # A 3-of-3 non-comparative criteria count is NOT a Piotroski F-Score: the standard
        # score is 0-9 and six of its criteria are year-over-year comparisons this module
        # never evaluates. score_or_value therefore stays None (nothing score-shaped is
        # presented as usable) and the raw count is reported separately, explicitly scoped.
        piotroski=result["models"]["piotroski_f_score"]
        self.assertIsNone(piotroski["score_or_value"])
        self.assertEqual(piotroski["result_state"],"partial")
        self.assertEqual(piotroski["component_results"]["non_comparative_criteria_met"],3)
        self.assertEqual(piotroski["component_results"]["non_comparative_criteria_evaluated"],3)
        self.assertIn("NOT reported here",piotroski["component_results"]["standard_piotroski_f_score_scale"])
        growth=result["models"]["growth_profitability"]
        self.assertEqual(growth["input_classification"],{"revenue":"qualified","net_income":"qualified"})
        self.assertEqual(growth["used_input_facts"]["revenue"]["citation_id"],"cit-revenue")
        self.assertNotIn("component_lineage",growth["used_input_facts"]["revenue"])
        self.assertEqual(result["models"]["bank_financial_quality"]["result_state"],"inapplicable")

    def test_bank_only_components_do_not_activate_corporate_models(self):
        records=[r("net_interest_income",20),r("net_income",10),r("customer_loans_net",200),r("customer_deposits",250),r("provision_for_credit_losses",-3),r("total_assets",500),r("total_equity",50)]
        result=evaluate_fundamental_quality({"records":records},"bank")
        bank=result["models"]["bank_financial_quality"]
        self.assertEqual(bank["result_state"],"available")
        self.assertIsNone(bank["score_or_value"])
        self.assertEqual(bank["component_results"]["loan_to_deposit_ratio"],0.8)
        self.assertEqual(bank["used_input_facts"]["customer_loans_net"]["citation_id"],"cit-customer_loans_net")
        self.assertEqual(result["models"]["financial_strength"]["result_state"],"inapplicable")
        self.assertIn("corporate_variant_not_qualified",result["models"]["financial_strength"]["warnings"][0])

    def test_missing_bank_input_fails_closed_with_classification(self):
        result=evaluate_fundamental_quality({"records":[r("net_interest_income",20),r("net_income",10)]},"bank")
        bank=result["models"]["bank_financial_quality"]
        self.assertEqual(bank["result_state"],"unavailable")
        self.assertIn("customer_loans_net",bank["missing_inputs"])
        self.assertEqual(bank["input_classification"]["customer_loans_net"],"missing")

    def test_never_mixes_periods_across_required_inputs(self):
        mixed={"records":[r("revenue",100,"2024"),r("revenue",120,"2025"),r("net_income",10,"2024")]}
        growth=evaluate_fundamental_quality(mixed,"corporate")["models"]["growth_profitability"]
        self.assertEqual(growth["result_state"],"available"); self.assertEqual(growth["score_or_value"],0.1)
        self.assertEqual({p["period"] for p in growth["input_periods"]},{"2024"})
        disjoint={"records":[r("revenue",100,"2025"),r("net_income",10,"2024")]}
        self.assertEqual(evaluate_fundamental_quality(disjoint,"corporate")["models"]["growth_profitability"]["result_state"],"unavailable")

    def test_isolated_pilot_uses_exporter_canonical_evaluator_entrypoint(self):
        from export_ai_bundle import evaluate_fundamental_quality as exporter_evaluator
        from fundamental_quality import evaluate_fundamental_quality as canonical_evaluator
        self.assertIs(exporter_evaluator, canonical_evaluator)

    def test_isolated_pilot_import_resolves_explicit_runtime_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            env=dict(os.environ, STOCK_LOOKUP_RUNTIME_ROOT=str(root))
            result=subprocess.run([sys.executable,"-c","from export_ai_bundle import runtime_path; print(runtime_path('financial_snapshot.parquet').resolve())"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=True)
            self.assertEqual(Path(result.stdout.strip()),root/"financial_snapshot.parquet")

    def test_derived_components_are_complete_sorted_and_deterministic(self):
        def component(metric, value):
            return {"canonical_metric":metric,"derivation_role":"required_component","value":value,"period_identity":{"period":"2025","period_type":"annual"},"statement_scope":"consolidated","currency":"VND","unit_scale":1,"source":"test","observation_ids":[f"obs-{metric}"],"citation_id":f"cit-{metric}","evidence_id":f"evi-{metric}"}
        debt=r("total_debt",20,derivation_status="derived",evidence={"components":[component("long_term_borrowings",15),component("short_term_borrowings",5)]})
        equity=r("shareholders_equity",25,derivation_status="derived",evidence={"components":[component("minority_interest_equity",2),component("total_equity",23)]})
        result=evaluate_fundamental_quality({"records":[debt,equity,r("cash_and_equivalents",5)]},"corporate")
        model=result["models"]["financial_strength"]
        self.assertEqual(model["result_state"],"available")
        lineage=model["used_input_facts"]["total_debt"]["component_lineage"]
        self.assertEqual([part["canonical_metric"] for part in lineage],["long_term_borrowings","short_term_borrowings"])
        self.assertEqual(set(lineage[0]),{"canonical_metric","derivation_role","value","period_identity","statement_scope","currency","unit_scale","source","observation_ids","citation_id","evidence_id"})
        self.assertEqual(result,evaluate_fundamental_quality({"records":[debt,equity,r("cash_and_equivalents",5)]},"corporate"))

    def test_conflicting_derived_component_lineage_fails_closed(self):
        def component(value):
            return {"canonical_metric":"short_term_borrowings","derivation_role":"required_component","value":value,"period_identity":{"period":"2025","period_type":"annual"},"statement_scope":"consolidated","currency":"VND","unit_scale":1,"source":"test","observation_ids":["obs-short-term"],"citation_id":"cit-short-term","evidence_id":"evi-short-term"}
        debt=r("total_debt",20,derivation_status="derived",evidence={"components":[component(5),component(15)]})
        model=evaluate_fundamental_quality({"records":[debt,r("shareholders_equity",25),r("cash_and_equivalents",5)]},"corporate")["models"]["financial_strength"]
        self.assertEqual(model["result_state"],"unavailable")
        self.assertEqual(model["missing_inputs"],["total_debt_lineage_unavailable"])
        self.assertEqual(model["input_classification"]["total_debt"],"incomparable")
        self.assertEqual(model["warnings"],["derived_component_identity_conflict"])

    def test_fail_closed_empty_and_incomparable(self):
        self.assertEqual(evaluate_fundamental_quality({"records":[]})["models"]["piotroski_f_score"]["result_state"],"unknown")
        record=r("revenue",1,quality_state="incomparable")
        result=evaluate_fundamental_quality({"records":[record]},"corporate")
        self.assertEqual(result["models"]["growth_profitability"]["result_state"],"unknown")


if __name__=="__main__":
    unittest.main()
