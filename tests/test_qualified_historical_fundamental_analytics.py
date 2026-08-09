import copy
import json
import unittest

from qualified_historical_fundamental_analytics import (
    adapt_official_annual_facts, build, build_comparative_matrix, merge_official_annual_facts,
)


def fact(metric, value, period="2024", *, ticker="HPG", currency="VND", scope="consolidated", period_type="annual"):
    return {
        "canonical_metric": metric, "value": value, "quality_state": "available",
        "period_identity": {"period": period, "period_type": period_type}, "statement_scope": scope,
        "currency": currency, "unit_scale": 1, "observation_ids": [f"{ticker}-{period}-{metric}"],
        "evidence": {"evidence_id": f"e-{ticker}-{period}-{metric}", "citation_id": f"c-{ticker}-{period}-{metric}"},
    }


def source(*, ticker="HPG", currency="VND", income=10, ocf=12, cash=30, debt=20, equity=100, period="2024"):
    values = {"net_income": income, "operating_cash_flow": ocf, "cash_and_equivalents": cash,
              "total_interest_bearing_debt": debt, "shareholders_equity": equity}
    return {"status": "available", "records": [fact(name, value, period, ticker=ticker, currency=currency)
                                                    for name, value in values.items()]}


class QualifiedHistoricalFundamentalAnalyticsTests(unittest.TestCase):
    def test_five_ticker_cohort_is_deterministic_and_currency_safe(self):
        inputs = {
            "HPG": source(ticker="HPG", debt=100, cash=30, equity=200, income=20, ocf=30),
            "VNM": source(ticker="VNM", debt=100, cash=150, equity=100),
            "PAN": source(ticker="PAN", debt=20, cash=30, equity=100),
            "PVD": source(ticker="PVD", currency="USD", debt=120, cash=80, equity=200, income=25, ocf=35),
            "NVL": source(ticker="NVL", debt=60, cash=4, equity=47, income=-4, ocf=-6),
        }
        analyses = {ticker: build(ticker, value) for ticker, value in inputs.items()}
        self.assertEqual(analyses, {ticker: build(ticker, copy.deepcopy(value)) for ticker, value in inputs.items()})
        self.assertEqual(analyses["PVD"]["currency"], "USD")
        self.assertEqual(analyses["PVD"]["metrics"]["net_debt"]["value"], 40)
        self.assertEqual(analyses["NVL"]["historical_conclusion"]["code"], "historically_loss_and_cashflow_stressed")
        matrix = build_comparative_matrix(analyses)
        self.assertTrue(matrix["ranking_prohibited"])
        self.assertTrue(matrix["fx_conversion_prohibited"])
        self.assertNotIn('"net_debt":', json.dumps(matrix))

    def test_incomplete_or_wrong_scope_fails_closed(self):
        data = source()
        data["records"][-1]["statement_scope"] = "standalone"
        result = build("HPG", data)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("complete_qualified_annual_metric_set_missing", result["blocking_reasons"])

    def test_nonpositive_income_and_zero_denominator_are_explicit(self):
        result = build("NVL", source(income=-4, ocf=-6, equity=0))
        self.assertEqual(result["metrics"]["operating_cash_flow_to_net_income"]["status"], "not_applicable")
        self.assertEqual(result["metrics"]["debt_to_equity"]["status"], "unavailable")
        self.assertEqual(result["metrics"]["net_debt_to_equity"]["status"], "unavailable")

    def test_trend_requires_two_qualified_annual_periods(self):
        data = source()
        one = build("HPG", data)
        self.assertEqual(one["trend_status"], "insufficient_history")
        data["records"] += [fact(name, value, "2023") for name, value in {
            "net_income": 8, "operating_cash_flow": 10, "cash_and_equivalents": 20,
            "total_interest_bearing_debt": 25, "shareholders_equity": 90,
        }.items()]
        two = build("HPG", data)
        self.assertEqual(two["trend_status"], "available")
        self.assertEqual(two["trend"]["periods"], ["2023", "2024"])

    def test_official_projection_adapter_preserves_authority_without_inference(self):
        official = [{
            "canonical_metric": "total_interest_bearing_debt", "status": "official_reported",
            "period_type": "annual", "reporting_period": "2024", "statement_scope": "consolidated",
            "currency": "USD", "scale": "units", "value": 120, "provider": "official_issuer_filing",
            "evidence_id": "e", "citation_id": "c", "source_observation_ids": ["o"],
        }]
        adapted = adapt_official_annual_facts(official)
        self.assertEqual(adapted[0]["quality_state"], "available")
        self.assertEqual(adapted[0]["currency"], "USD")
        merged = merge_official_annual_facts({"status": "available", "records": [
            fact("total_interest_bearing_debt", 999), fact("net_income", 10),
        ]}, official)
        debt = [row for row in merged["records"] if row["canonical_metric"] == "total_interest_bearing_debt"]
        self.assertEqual([row["value"] for row in debt], [120])


if __name__ == "__main__":
    unittest.main()
