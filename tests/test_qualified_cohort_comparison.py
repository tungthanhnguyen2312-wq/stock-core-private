import copy
import json
import unittest

from qualified_cohort_comparison import QUALIFIED_COHORT, build


def metric(value=None, *, status="available", reasons=None):
    return {"status": status, "value": value, "applicability": "applicable" if status == "available" else "not_applicable",
            "reason_codes": reasons or [], "source_fact_identities": [{"canonical_metric": "x", "reporting_period": "2024", "currency": "USD" if value == 0.19 else "VND", "citation_id": "c"}]}


def analysis(ticker, *, income=1, ocf=1, conversion=1.0, debt_equity=0.5, cash_debt=0.3, net_debt_equity=0.2):
    earnings = ["profitable"] if income > 0 else ["loss_making"]
    ocf_state = ["operating_cash_flow_positive"] if ocf > 0 else ["operating_cash_flow_negative"]
    risks = []
    if income < 0: risks.append({"predicate": "loss_making_period"})
    if ocf < 0: risks.append({"predicate": "negative_operating_cash_flow"})
    if debt_equity > 0: risks.append({"predicate": "net_debt_position"})
    return {"status": "available", "analysis_period": "2024", "currency": "USD" if ticker == "PVD" else "VND",
            "qualified_annual_periods": ["2024"], "trend_status": "insufficient_history",
            "metrics": {"earnings_state": metric(income, reasons=earnings), "operating_cash_flow_state": metric(ocf, reasons=ocf_state),
                        "operating_cash_flow_to_net_income": metric(conversion) if income > 0 else metric(status="not_applicable", reasons=["net_income_nonpositive_ratio_interpretation_not_applicable"]),
                        "debt_to_equity": metric(debt_equity), "cash_to_debt": metric(cash_debt),
                        "net_debt_to_equity": metric(net_debt_equity), "net_debt": metric(100, reasons=["net_debt_position"])},
            "risk_predicates": risks, "strength_predicates": [{"predicate": "positive_earnings"}] if income > 0 else [],
            "historical_conclusion": {"code": "historically_loss_and_cashflow_stressed" if income < 0 and ocf < 0 else "historically_mixed"}}


class QualifiedCohortComparisonTests(unittest.TestCase):
    def setUp(self):
        self.analyses = {
            "HPG": analysis("HPG", conversion=.55, debt_equity=.73, cash_debt=.08, net_debt_equity=.67),
            "VNM": analysis("VNM", conversion=1.03, debt_equity=.29, cash_debt=.24, net_debt_equity=.22),
            "PAN": analysis("PAN", ocf=-1, conversion=-1.49, debt_equity=1.32, cash_debt=.25, net_debt_equity=.99),
            "PVD": analysis("PVD", conversion=1.49, debt_equity=.19, cash_debt=.72, net_debt_equity=.05),
            "NVL": analysis("NVL", income=-1, ocf=-1, debt_equity=1.30, cash_debt=.07, net_debt_equity=1.20),
        }

    def test_fixed_cohort_is_deterministic_and_descriptive(self):
        first = build(self.analyses)
        self.assertEqual(first, build(copy.deepcopy(self.analyses)))
        self.assertEqual(first["cohort_tickers"], list(QUALIFIED_COHORT))
        self.assertEqual(first["cross_sectional_comparison"], "available")
        self.assertEqual(first["multi_period_trend"], "insufficient_history")
        self.assertTrue(first["ranking_prohibited"])
        self.assertTrue(first["fx_conversion_prohibited"])
        self.assertNotIn('"net_debt":', json.dumps(first))

    def test_sub_conclusions_differentiate_pan_and_nvl_without_recommendation(self):
        rows = {row["ticker"]: row for row in build(self.analyses)["rows"]}
        self.assertEqual(rows["PAN"]["sub_conclusions"]["earnings_quality"]["code"], "negative_or_zero_cash_conversion")
        self.assertEqual(rows["PAN"]["sub_conclusions"]["historical_stress"]["code"], "cash_flow_stress")
        self.assertEqual(rows["NVL"]["sub_conclusions"]["earnings_quality"]["code"], "cash_conversion_not_applicable_or_unavailable")
        self.assertEqual(rows["NVL"]["sub_conclusions"]["historical_stress"]["code"], "combined_earnings_and_cash_flow_stress")
        self.assertEqual(rows["PVD"]["comparative_positions"]["debt_to_equity"]["code"], "lowest_observed_in_qualified_cohort")
        self.assertEqual(rows["PVD"]["sub_conclusions"]["funding_structure"]["code"], "lowest_observed_in_qualified_cohort")

    def test_incomplete_or_missing_metric_fails_closed(self):
        incomplete = dict(self.analyses); incomplete.pop("NVL")
        self.assertEqual(build(incomplete)["status"], "unavailable")
        missing_metric = copy.deepcopy(self.analyses); missing_metric["PVD"]["metrics"].pop("debt_to_equity")
        row = next(row for row in build(missing_metric)["rows"] if row["ticker"] == "PVD")
        self.assertEqual(row["comparative_positions"]["debt_to_equity"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
