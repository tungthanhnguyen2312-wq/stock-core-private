import json
import unittest
from pathlib import Path

from fundamental_research_readiness import (
    MetricStatus,
    build_fundamental_research_artifact,
    evaluate_issuer_fundamental_research,
)


def fact(metric, value, period="2025", *, currency="VND", scope="consolidated", state="QUALIFIED", positive=True, pit=True):
    return {
        "canonical_metric": metric, "value": value, "reporting_period": period,
        "statement_scope": scope, "currency": currency, "unit_scale": 1,
        "qualification_state": state, "is_positive_authority": positive,
        "source_lineage": {"citation_id": f"citation-{metric}-{period}", "evidence_id": f"evidence-{metric}-{period}",
                           "document_sha256": f"hash-{metric}-{period}", "source_page": 1,
                           "authority_tier": "test_promoted", "reconciliation_status": "EXACT_MATCH"},
        "temporal_envelope": {"field_id": f"fact-{metric}-{period}", "pit_eligible": pit,
                              "pit_status": "QUALIFIED" if pit else "LOOKAHEAD_VIOLATION"},
    }


def issuer(ticker, entity_class, facts):
    return {"issuer_identity": {"ticker": ticker, "entity_type": entity_class}, "facts": facts}


def metric(result, metric_id, period="2025"):
    return next(row for row in result["metrics"] if row["metric_id"] == metric_id and (not row["periods_used"] or period in row["periods_used"]))


class FundamentalResearchReadinessTests(unittest.TestCase):
    def test_deterministic_authoritative_calculation_and_lineage(self):
        source = issuer("CORP", "corporate", [
            fact("net_income", 10, "2024"), fact("net_income", 15), fact("revenue", 100, "2024"), fact("revenue", 120),
            fact("operating_cash_flow", 12, "2024"), fact("operating_cash_flow", 18),
            fact("total_assets", 100, "2024"), fact("total_assets", 140),
            fact("shareholders_equity", 50, "2024"), fact("shareholders_equity", 70),
            fact("total_interest_bearing_debt", 21), fact("cash_and_equivalents", 4),
        ])
        first = evaluate_issuer_fundamental_research(source)
        second = evaluate_issuer_fundamental_research(source)
        self.assertEqual(first, second)
        growth = metric(first, "revenue_growth_yoy")
        self.assertEqual(growth["status"], MetricStatus.EXACT_QUALIFIED)
        self.assertAlmostEqual(growth["value"], 0.2)
        self.assertEqual(len(growth["input_fact_ids"]), 2)
        self.assertTrue(all(item["citation_id"] for item in growth["evidence_lineage"]))
        roe = metric(first, "return_on_equity")
        self.assertEqual(roe["method"], "AVERAGE_DENOMINATOR=(ending_balance+prior_ending_balance)/2")
        self.assertEqual(roe["status"], MetricStatus.EXACT_QUALIFIED)
        self.assertAlmostEqual(roe["value"], 15 / 60)

    def test_ending_balance_is_visible_proxy(self):
        result = evaluate_issuer_fundamental_research(issuer("CORP", "corporate", [
            fact("net_income", 15), fact("total_assets", 140), fact("shareholders_equity", 70),
        ]))
        roe = metric(result, "return_on_equity")
        self.assertEqual(roe["status"], MetricStatus.DERIVED_PROXY)
        self.assertIn("ENDING_BALANCE_PROXY", roe["method"])
        self.assertIn("AVERAGE_DENOMINATOR_NOT_AVAILABLE", roe["warnings"][0])

    def test_bank_and_securities_gating_preserves_sector_identities(self):
        bank = evaluate_issuer_fundamental_research(issuer("BANK", "bank", [
            fact("net_profit_parent", 10), fact("total_assets", 200), fact("total_equity", 50),
            fact("customer_loans_net", 160), fact("customer_deposits", 200), fact("provision_for_credit_losses", 4),
        ]))
        self.assertAlmostEqual(metric(bank, "loan_to_deposit_ratio")["value"], 0.8)
        self.assertEqual(metric(bank, "debt_to_equity")["status"], MetricStatus.NOT_APPLICABLE)
        securities = evaluate_issuer_fundamental_research(issuer("SEC", "securities", [
            fact("profit_after_tax_parent", 10), fact("total_assets", 200), fact("total_equity", 50),
            fact("financial_assets_fvtpl", 90), fact("loans_balance", 40),
        ]))
        self.assertAlmostEqual(metric(securities, "fvtpl_assets_to_total_assets")["value"], 0.45)
        self.assertAlmostEqual(metric(securities, "margin_loans_to_total_assets")["value"], 0.2)
        self.assertEqual(metric(securities, "debt_to_equity")["status"], MetricStatus.NOT_APPLICABLE)

    def test_missing_conflict_and_dimension_mismatch_stay_non_positive(self):
        missing = evaluate_issuer_fundamental_research(issuer("CORP", "corporate", [fact("net_income", 10)]))
        self.assertEqual(metric(missing, "net_margin")["status"], MetricStatus.MISSING)
        conflict = evaluate_issuer_fundamental_research(issuer("CORP", "corporate", [
            fact("net_income", 10, state="CONFLICT"), fact("revenue", 100),
        ]))
        self.assertEqual(metric(conflict, "net_margin")["status"], MetricStatus.CONFLICT)
        mismatch = evaluate_issuer_fundamental_research(issuer("CORP", "corporate", [
            fact("net_income", 10), fact("revenue", 100, currency="USD"),
        ]))
        self.assertEqual(metric(mismatch, "net_margin")["status"], MetricStatus.BLOCKED)
        self.assertEqual(metric(mismatch, "net_margin")["blocked_reason"], "SCOPE_CURRENCY_OR_SCALE_MISMATCH")
        cross_period = evaluate_issuer_fundamental_research(issuer("CORP", "corporate", [
            fact("revenue", 100, "2024", currency="USD"), fact("revenue", 120, "2025"),
        ]))
        growth = metric(cross_period, "revenue_growth_yoy")
        self.assertEqual(growth["status"], MetricStatus.BLOCKED)
        self.assertEqual(growth["blocked_reason"], "SCOPE_CURRENCY_OR_SCALE_MISMATCH_ACROSS_PERIODS")

    def test_artifact_has_no_market_dependency_score_or_ranking_and_is_repeatable(self):
        panel = {"artifact_id": "p2:test", "content_hash": "p2hash", "entity_class_distribution": {"corporate": 1},
                 "issuers": [issuer("CORP", "corporate", [fact("net_income", 10), fact("revenue", 100)])]}
        first, second = build_fundamental_research_artifact(panel), build_fundamental_research_artifact(panel)
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertFalse(first["governance"]["price_liquidity_dependency"])
        self.assertFalse(first["governance"]["universal_composite_score_produced"])
        self.assertFalse(first["governance"]["cross_sectional_ranking_produced"])
        self.assertNotIn("composite_score", first["issuer_research_readiness"][0])
        self.assertTrue(first["lineage_completeness"]["positive_metrics_with_evidence_lineage"] > 0)

    def test_current_authoritative_p2_cohort_runs_without_price_or_liquidity_inputs(self):
        root = Path(__file__).resolve().parents[1]
        source = json.loads((root / "operations-review" / "p2-closeout-financial-fact-panel-20260820" / "p2_closeout_financial_panel_artifact.json").read_text(encoding="utf-8"))
        artifact = build_fundamental_research_artifact(source)
        self.assertEqual(artifact["cohort_identity"]["issuers"], ["GAS", "HPG", "NVL", "PAN", "POW", "PVD", "QNS", "SSI", "VCB", "VNM", "VRE"])
        self.assertEqual(artifact["coverage_summary"]["by_entity_class"]["bank"]["issuer_count"], 1)
        self.assertEqual(artifact["coverage_summary"]["by_entity_class"]["securities"]["issuer_count"], 1)


if __name__ == "__main__":
    unittest.main()
