"""Contract regressions for current financial momentum research context."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import current_financial_momentum_context as momentum
import current_official_market_universe as official
import export_ai_bundle as bundle
import polymorphic_current_strategy_classification as strategy
from market_wide_current_descriptive_research import content_identity as descriptive_identity
from market_wide_current_fundamental_research import content_identity as fundamental_identity


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "daily_research_session_input_registry.json"
FROZEN_20260821 = "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a"
FROZEN_20260824 = "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388"


def _signed_official(tickers: list[str]) -> dict:
    artifact = {
        "contract_version": "current_official_market_universe/v1",
        "records": {
            ticker: {
                "ticker": ticker, "stocklookup_candidate": True,
                "current_universe_status": official.OFFICIAL_CURRENT_EXCHANGE_SECURITY,
            }
            for ticker in tickers
        },
        "reconciliation": {"official_total_match": len(tickers)},
    }
    artifact.update(official._identity(artifact))
    return artifact


def _signed_fundamental(records: dict) -> dict:
    artifact = {"contract_version": "market_wide_current_fundamental_research/v1", "records": records}
    artifact.update(fundamental_identity(artifact))
    return artifact


def _signed_descriptive(records: dict) -> dict:
    artifact = {"contract_version": "market_wide_current_descriptive_research/v1", "session": "2026-08-24", "records": records}
    artifact.update(descriptive_identity(artifact))
    return artifact


def _official_metric(metric_id: str, value: float, periods: list[str], *, status="EXACT_QUALIFIED",
                     scope="consolidated", currency="VND", blocked_reason=None) -> dict:
    return {
        "metric_id": metric_id, "value": value, "status": status, "periods_used": periods,
        "statement_scope": scope, "currency": currency, "method": "YOY_GROWTH=(current-prior)/abs(prior)",
        "blocked_reason": blocked_reason, "warnings": [], "evidence_lineage": [{"canonical_metric": metric_id, "reporting_period": periods[-1]}],
    }


def _official_record(ticker: str, entity_class: str, metrics: list[dict]) -> dict:
    return {
        "ticker": ticker, "authority_tier": "OFFICIAL_QUALIFIED", "entity_class": entity_class,
        "fundamental_research_readiness": "PARTIAL", "metrics": metrics,
        "authoritative_periods_available": sorted({period for metric in metrics for period in metric.get("periods_used") or []}),
    }


def _provider_growth(fraction: float | None, *, status="AVAILABLE", comparison_type="QoQ",
                     periods=None, yoy=None, blocked_reason=None, provider="KBS") -> dict:
    periods = periods or ["2026-Q1", "2026-Q2"]
    metric = {
        "status": status, "growth_fraction": fraction, "comparison_type": comparison_type,
        "periods": periods, "provider": provider, "blocked_reason": blocked_reason,
        "lineage": [{"provider": provider, "periods": periods}],
        "method": "same_provider_comparable_quarter_provider_series_trend/v2",
        "comparisons": {},
    }
    if yoy is not None:
        metric["comparisons"]["yoy"] = yoy
    return metric


def _provider_record(ticker: str, entity_class: str, *, revenue=None, earnings=None, ocf=None) -> dict:
    metrics = {}
    if revenue is not None:
        metrics["revenue_growth"] = revenue
    if earnings is not None:
        metrics["earnings_growth"] = earnings
    if ocf is not None:
        metrics["operating_cash_flow_direction"] = ocf
    return {
        "ticker": ticker, "authority_tier": "PROVIDER_RESEARCH", "entity_class": entity_class,
        "provider_series_trends": {"metrics": metrics, "status": "AVAILABLE"},
        "fundamental_trajectory_context": {
            "trajectory_status": "AVAILABLE",
            "revenue_direction": "EXPANDING",
            "earnings_direction": "EXPANDING",
            "revenue_vs_earnings_alignment": {"status": "BOTH_EXPANDING"},
        },
    }


def _price_row(momentum: float) -> dict:
    return {
        "technical_features": {
            "status": "SHADOW_ONLY", "is_current_session": True,
            "values": {"return_1d": 0.01, "momentum_20d": momentum},
        },
        "trend_state": "ABOVE_MA20",
    }


class CurrentFinancialMomentumContextTests(unittest.TestCase):
    def _build(self, records: dict, tickers: list[str] | None = None, descriptive: dict | None = None) -> dict:
        tickers = tickers or sorted(records)
        return momentum.build_artifact(
            current_official_universe=_signed_official(tickers),
            current_fundamental=_signed_fundamental(records),
            current_descriptive=descriptive,
        )

    def test_official_fy_yoy_and_broad_improvement(self) -> None:
        artifact = self._build({
            "HPG": _official_record("HPG", "corporate", [
                _official_metric("revenue_growth_yoy", 0.16, ["2023", "2024"]),
                _official_metric("earnings_growth_yoy", 0.76, ["2023", "2024"]),
                _official_metric("net_margin", 0.05, ["2023"]),
                _official_metric("net_margin", 0.08, ["2024"]),
            ]),
        })
        row = artifact["records"]["HPG"]
        self.assertEqual(row["financial_momentum_state"], momentum.BROAD_IMPROVEMENT)
        self.assertEqual(row["components"]["revenue_growth"]["comparison_type"], "FY_YOY")
        self.assertEqual(row["evidence_tier"], "OFFICIAL_QUALIFIED")
        self.assertEqual(row["coverage_status"], momentum.COVERAGE_PARTIAL)

    def test_margin_deterioration_despite_revenue_and_earnings_growth_is_mixed(self) -> None:
        artifact = self._build({
            "PVD": _official_record("PVD", "corporate", [
                _official_metric("revenue_growth_yoy", 0.52, ["2023", "2024"]),
                _official_metric("earnings_growth_yoy", 0.21, ["2023", "2024"]),
                _official_metric("net_margin", 0.07, ["2023"]),
                _official_metric("net_margin", 0.05, ["2024"]),
            ]),
        })
        self.assertEqual(artifact["records"]["PVD"]["financial_momentum_state"], momentum.MIXED)
        self.assertEqual(artifact["records"]["PVD"]["state_rule"], "REVENUE_UP_EARNINGS_UP_MARGIN_DOWN")

    def test_quarter_versus_fy_mismatch_fails_closed(self) -> None:
        artifact = self._build({
            "AAA": _official_record("AAA", "corporate", [
                _official_metric("revenue_growth_yoy", 0.10, ["2023-Q4", "2024"]),
            ]),
        })
        self.assertEqual(artifact["records"]["AAA"]["components"]["revenue_growth"]["status"], "BLOCKED")
        self.assertEqual(artifact["records"]["AAA"]["components"]["revenue_growth"]["blocked_reason"], "OFFICIAL_GROWTH_PERIODS_NOT_FY_YOY_PAIR")

    def test_consolidated_standalone_mismatch_fails_closed(self) -> None:
        metrics = [
            _official_metric("net_margin", 0.10, ["2023"], scope="consolidated"),
            _official_metric("net_margin", 0.12, ["2024"], scope="standalone"),
        ]
        artifact = self._build({"AAA": _official_record("AAA", "corporate", metrics)})
        self.assertEqual(artifact["records"]["AAA"]["components"]["net_margin_change"]["status"], "UNAVAILABLE")

    def test_parent_versus_total_earnings_remain_distinct_for_banks(self) -> None:
        artifact = self._build({
            "VCB": _official_record("VCB", "bank", [
                _official_metric("earnings_growth_yoy", 0.12, ["2023", "2024"]),
                _official_metric("revenue_growth_yoy", 0.20, ["2023", "2024"]),
            ]),
            "ACB": _provider_record("ACB", "bank", earnings=_provider_growth(0.25)),
        }, tickers=["VCB", "ACB"])
        self.assertEqual(artifact["records"]["VCB"]["components"]["revenue_growth"]["status"], "NOT_APPLICABLE")
        self.assertEqual(artifact["records"]["VCB"]["components"]["earnings_growth"]["earnings_identity"], "net_profit_parent")
        self.assertEqual(artifact["records"]["VCB"]["financial_momentum_state"], momentum.EARNINGS_IMPROVING)
        self.assertEqual(artifact["records"]["ACB"]["components"]["earnings_growth"]["blocked_reason"],
                         "PROVIDER_NET_INCOME_IS_NOT_PARENT_ATTRIBUTABLE_EARNINGS")
        self.assertEqual(artifact["records"]["ACB"]["financial_momentum_state"], momentum.INSUFFICIENT_COMPARABLE_DATA)

    def test_official_and_provider_authority_stay_separated(self) -> None:
        artifact = self._build({
            "HPG": _official_record("HPG", "corporate", [_official_metric("revenue_growth_yoy", 0.1, ["2023", "2024"])]),
            "AAA": _provider_record("AAA", "corporate", revenue=_provider_growth(0.1, yoy={
                "status": "AVAILABLE", "growth_fraction": 0.2, "comparison_type": "YoY",
                "periods": ["2025-Q2", "2026-Q2"], "provider": "KBS", "lineage": [],
            })),
        })
        self.assertEqual(artifact["records"]["HPG"]["evidence_tier"], "OFFICIAL_QUALIFIED")
        self.assertEqual(artifact["records"]["AAA"]["evidence_tier"], "PROVIDER_RESEARCH")
        self.assertIsNone(artifact["records"]["AAA"]["components"]["revenue_growth"]["current_value"])
        self.assertEqual(artifact["records"]["AAA"]["components"]["revenue_growth"]["comparison_type"], "YoY")

    def test_positive_growth_and_yoy_preferred_over_qoq(self) -> None:
        artifact = self._build({
            "HPA": _provider_record("HPA", "corporate", revenue=_provider_growth(
                0.05, comparison_type="QoQ", yoy={
                    "status": "AVAILABLE", "growth_fraction": 0.10, "periods": ["2025-Q3", "2026-Q3"],
                    "provider": "KBS", "lineage": [{"fact_id": "a"}],
                },
            )),
        })
        row = artifact["records"]["HPA"]["components"]["revenue_growth"]
        self.assertEqual(row["comparison_type"], "YoY")
        self.assertEqual(row["change"], 0.10)
        self.assertEqual(row["direction"], "EXPANDING")

    def test_missing_yoy_does_not_relabel_qoq_as_yoy(self) -> None:
        artifact = self._build({
            "AAA": _provider_record("AAA", "corporate", revenue=_provider_growth(-0.2), earnings=_provider_growth(-0.3)),
        })
        row = artifact["records"]["AAA"]
        self.assertEqual(row["components"]["revenue_growth"]["comparison_type"], "QoQ")
        self.assertIn("YOY_COMPARABLE_ABSENT_QOQ_NOT_SUBSTITUTED_AS_YOY", row["components"]["revenue_growth"]["warnings"])
        self.assertEqual(row["financial_momentum_state"], momentum.DETERIORATING)
        self.assertEqual(row["coverage_status"], momentum.COVERAGE_PARTIAL)

    def test_negative_earnings_semantics(self) -> None:
        artifact = self._build({
            "ALV": _provider_record("ALV", "corporate", earnings=_provider_growth(
                None, status="BLOCKED", blocked_reason="GROWTH_BASE_NON_POSITIVE",
            )),
            "LOSS": _official_record("LOSS", "corporate", [_official_metric("net_margin", -0.02, ["2024"])]),
        }, tickers=["ALV", "LOSS"])
        self.assertEqual(artifact["records"]["ALV"]["financial_momentum_state"], momentum.LOSS_MAKING_OR_STRESSED)
        self.assertEqual(artifact["records"]["LOSS"]["financial_momentum_state"], momentum.LOSS_MAKING_OR_STRESSED)

    def test_missing_comparison_period_is_partial_or_insufficient_not_zero(self) -> None:
        artifact = self._build({
            "AAA": _provider_record("AAA", "corporate", revenue=_provider_growth(
                0.1, yoy={"status": "BLOCKED", "blocked_reason": "NO_SAME_PROVIDER_SAME_QUARTER_PRIOR_YEAR_PAIR",
                           "periods": [], "lineage": []},
            )),
            "BBB": _official_record("BBB", "corporate", []),
        }, tickers=["AAA", "BBB", "ZZZ"])
        self.assertIsNone(artifact["records"]["BBB"]["components"]["revenue_growth"]["change"])
        self.assertEqual(artifact["records"]["BBB"]["financial_momentum_state"], momentum.INSUFFICIENT_COMPARABLE_DATA)
        self.assertEqual(artifact["records"]["ZZZ"]["state_rule"], "NOT_IN_FUNDAMENTAL_COHORT")
        self.assertNotEqual(artifact["records"]["ZZZ"]["financial_momentum_state"], momentum.DETERIORATING)

    def test_one_missing_metric_does_not_globally_block_ticker(self) -> None:
        artifact = self._build({
            "HPG": _official_record("HPG", "corporate", [
                _official_metric("revenue_growth_yoy", 0.16, ["2023", "2024"]),
                _official_metric("earnings_growth_yoy", 0.76, ["2023", "2024"]),
            ]),
        })
        row = artifact["records"]["HPG"]
        self.assertEqual(row["components"]["net_margin_change"]["status"], "UNAVAILABLE")
        self.assertEqual(row["financial_momentum_state"], momentum.EARNINGS_IMPROVING)
        self.assertEqual(row["coverage_status"], momentum.COVERAGE_PARTIAL)

    def test_statement_scope_conflict_on_provider_yoy_fails_closed(self) -> None:
        artifact = self._build({
            "AAN": _provider_record("AAN", "corporate", earnings=_provider_growth(
                -0.5, yoy={"status": "BLOCKED", "blocked_reason": "STATEMENT_SCOPE_NOT_COMPARABLE",
                           "periods": ["2025-Q1", "2026-Q1"], "lineage": []},
            )),
        })
        self.assertEqual(artifact["records"]["AAN"]["components"]["earnings_growth"]["status"], "BLOCKED")
        self.assertEqual(artifact["records"]["AAN"]["components"]["earnings_growth"]["blocked_reason"], "STATEMENT_SCOPE_NOT_COMPARABLE")

    def test_price_contrast_does_not_become_a_forecast(self) -> None:
        records = {
            "HPG": _official_record("HPG", "corporate", [
                _official_metric("revenue_growth_yoy", 0.16, ["2023", "2024"]),
                _official_metric("earnings_growth_yoy", 0.76, ["2023", "2024"]),
                _official_metric("net_margin", 0.05, ["2023"]),
                _official_metric("net_margin", 0.08, ["2024"]),
            ]),
        }
        descriptive = _signed_descriptive({"HPG": _price_row(-0.2)})
        artifact = self._build(records, descriptive=descriptive)
        contrast = artifact["records"]["HPG"]["price_momentum_context"]
        self.assertEqual(contrast["contrast"], "FINANCIAL_IMPROVEMENT_WITHOUT_PRICE_MOMENTUM")
        self.assertTrue(contrast["financial_momentum_is_not_price_momentum"])

    def test_strategy_priority_and_entry_are_not_modified(self) -> None:
        fundamental_row = _provider_record("AAA", "corporate", revenue=_provider_growth(0.2), earnings=_provider_growth(0.3))
        before = strategy._fundamental_requirements(fundamental_row)
        artifact = self._build({"AAA": fundamental_row})
        after = strategy._fundamental_requirements(fundamental_row)
        self.assertEqual(before[0]["status"], after[0]["status"])
        self.assertEqual(before[1]["status"], "SATISFIED")
        self.assertEqual(artifact["blocked_outputs"]["strategy_eligibility"], "NOT_MODIFIED")
        self.assertEqual(artifact["blocked_outputs"]["research_priority"], "NOT_MODIFIED")
        self.assertEqual(artifact["blocked_outputs"]["entry_action"], "NOT_MODIFIED")
        self.assertTrue(artifact["records"]["AAA"]["does_not_enable_fundamental_improvement_strategy"])

    def test_no_forecast_target_valuation_or_probability_fields(self) -> None:
        artifact = self._build({
            "HPG": _official_record("HPG", "corporate", [_official_metric("revenue_growth_yoy", 0.1, ["2023", "2024"])]),
        })
        for row in artifact["records"].values():
            for forbidden in ("target_price", "forecast", "probability", "dcf", "recommendation"):
                self.assertNotIn(forbidden, row)
        self.assertFalse(artifact["authority_boundary"]["is_actionable"])
        self.assertTrue(artifact["authority_boundary"]["financial_momentum_is_not_forecast"])

    def test_replay_and_frozen_identities(self) -> None:
        artifact = self._build({
            "HPG": _official_record("HPG", "corporate", [_official_metric("revenue_growth_yoy", 0.1, ["2023", "2024"])]),
        })
        again = self._build({
            "HPG": _official_record("HPG", "corporate", [_official_metric("revenue_growth_yoy", 0.1, ["2023", "2024"])]),
        })
        self.assertEqual(artifact["artifact_identity"], again["artifact_identity"])
        momentum.replay(artifact)
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(registry["sessions"]["2026-08-21"]["valuation"]["artifact_identity"], FROZEN_20260821)
        self.assertEqual(registry["sessions"]["2026-08-24"]["valuation"]["artifact_identity"], FROZEN_20260824)


class ExportAttachmentTests(unittest.TestCase):
    def test_opt_in_attachment_is_default_off_and_preserves_decisions(self) -> None:
        records = {"HPG": _official_record("HPG", "corporate", [_official_metric("revenue_growth_yoy", 0.1, ["2023", "2024"])])}
        artifact = momentum.build_artifact(
            current_official_universe=_signed_official(["HPG"]),
            current_fundamental=_signed_fundamental(records),
        )
        entries = {"HPG": {"strategy_eligibility": "existing", "research_priority": "existing", "entry_action": "existing"}}
        untouched = copy.deepcopy(entries)
        self.assertEqual(bundle.attach_current_financial_momentum_context(entries, False, "missing.json"), untouched)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "momentum.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = bundle.attach_current_financial_momentum_context(entries, True, str(path))
            attached = result["HPG"]["current_financial_momentum_context"]
            self.assertFalse(attached["is_actionable"])
            self.assertEqual(attached["ticker_context"]["financial_momentum_state"], artifact["records"]["HPG"]["financial_momentum_state"])
            self.assertEqual(result["HPG"]["strategy_eligibility"], "existing")
            self.assertEqual(result["HPG"]["research_priority"], "existing")
            self.assertEqual(result["HPG"]["entry_action"], "existing")
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["coverage"]["universe_denominator"] = 0
            path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertNotIn(
                "current_financial_momentum_context",
                bundle.attach_current_financial_momentum_context({"HPG": {}}, True, str(path))["HPG"],
            )


if __name__ == "__main__":
    unittest.main()
