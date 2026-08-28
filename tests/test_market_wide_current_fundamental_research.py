"""Tests for market_wide_current_fundamental_research.py.

Two layers: synthetic-fixture unit tests for build_artifact()'s join/authority-tier logic
(isolated from the real retained corpus, fast, deterministic), and one live-integration test
that calls execute() against the actual retained P3-F10/P3-F13 evidence and pins the real,
independently-known coverage numbers (523 candidates, 13 official, 510 official-route-blocked,
3 source-missing, 94 exact metrics, 22 proxies, 49 missing).
"""
from __future__ import annotations

import inspect
import unittest
from copy import deepcopy

from market_wide_current_fundamental_research import (
    BLOCKED_TIER,
    OFFICIAL_TIER,
    PROVIDER_TIER,
    build_artifact,
    content_identity,
    execute,
)


def _frozen_p3f10(rows: list[dict]) -> dict:
    return {
        "artifact_identity": "p3f10_generic_fundamental_evidence_scaleout:FAKEHASH",
        "cohort_identity": {"identity": "cohort_empirically_active:FAKE", "member_count": len(rows),
                            "as_of_session": "2026-08-20"},
        "instrument_dispositions": rows,
    }


def _row(ticker: str, *, disposition: str, sector: str = "unknown", raw_observed: bool = True,
        blocker: str | None = "PROVIDER_OBSERVATION_SCOPE_CURRENCY_SCALE_NOT_INDEPENDENTLY_EVIDENCED") -> dict:
    return {
        "ticker": ticker, "disposition": disposition, "sector": sector, "blocker": blocker,
        "raw_observation_state": "RAW_OBSERVED" if raw_observed else "RAW_NOT_RETAINED",
        "raw_observation_count": 100 if raw_observed else 0,
        "raw_statement_families": ["balance_sheet"] if raw_observed else [],
        "raw_providers": ["VCI"] if raw_observed else [],
        "reporting_periods": ["2024-Q4"] if raw_observed else [],
    }


def _issuer_readiness(ticker: str, entity_class: str, readiness: str) -> dict:
    metric = {"metric_id": "net_margin", "status": "EXACT_QUALIFIED" if readiness != "BLOCKED" else "MISSING",
              "blocked_reason": None if readiness != "BLOCKED" else "MISSING_INPUTS:net_income",
              "periods_used": ["2024"]}
    return {
        "issuer_identity": {"ticker": ticker, "entity_class": entity_class},
        "fundamental_research_readiness": readiness,
        "authoritative_periods_available": ["2024"],
        "metrics": [metric],
        "metric_family_states": {"profitability": f"PROFITABILITY_{'AVAILABLE' if readiness != 'BLOCKED' else 'BLOCKED'}"},
        "history_readiness": {"compatible_annual_period_count": 1},
        "evidence_completeness": {"positive_authoritative_fact_count": 1},
    }


def _p3f13_current(*, cohort_size: int, official: list[dict], newly_qualified: list[str],
                   acquisition: list[dict], p3f10_identity: str) -> dict:
    return {
        "artifact_identity": "p3f13_official_financial_evidence_scaleout:FAKEHASH",
        "cohort_identity": {"total_cohort_count": cohort_size},
        "source_artifacts": {"p3f10": p3f10_identity},
        "newly_qualified_issuers": newly_qualified,
        "acquisition_dispositions": acquisition,
        "refreshed_fundamental_readiness": {
            "issuer_research_readiness": official,
            "coverage_summary": {"metric_status_counts": {
                "EXACT_QUALIFIED": sum(1 for o in official if o["fundamental_research_readiness"] != "BLOCKED"),
                "DERIVED_PROXY": 0,
                "MISSING": sum(1 for o in official if o["fundamental_research_readiness"] == "BLOCKED"),
                "NOT_APPLICABLE": 0,
            }},
        },
    }


class BuildArtifactJoinLogic(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            _row("AAA", disposition="STATEMENT_SCOPE_UNKNOWN"),
            _row("BBB", disposition="SOURCE_MISSING", raw_observed=False, blocker="MISSING_FINANCIAL_SOURCE_PAYLOAD"),
            _row("GAS", disposition="EVIDENCE_QUALIFIED", sector="corporate", blocker=None),
            _row("PNJ", disposition="STATEMENT_SCOPE_UNKNOWN", sector="unknown"),
        ]
        self.p3f10_frozen = _frozen_p3f10(self.rows)
        self.official = [
            _issuer_readiness("GAS", "corporate", "PARTIAL"),
            _issuer_readiness("PNJ", "corporate", "BLOCKED"),
        ]
        self.p3f13_current = _p3f13_current(
            cohort_size=4, official=self.official, newly_qualified=["PNJ"],
            acquisition=[{"ticker": "AAA", "disposition": "NO_APPROVED_ROUTE_FOUND",
                          "reason": "NO_APPROVED_OFFICIAL_SOURCE_ROUTE_IN_REGISTRY"}],
            p3f10_identity=self.p3f10_frozen["artifact_identity"],
        )

    def test_cohort_size_and_tier_split(self) -> None:
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        self.assertEqual(artifact["coverage"]["candidate_count"], 4)
        self.assertEqual(artifact["coverage"]["issuers_with_official_facts"], 2)
        self.assertEqual(artifact["records"]["GAS"]["authority_tier"], OFFICIAL_TIER)
        self.assertEqual(artifact["records"]["AAA"]["authority_tier"], PROVIDER_TIER)
        self.assertEqual(artifact["records"]["BBB"]["authority_tier"], BLOCKED_TIER)

    def test_opportunity_research_attachment_is_separate_and_opt_in(self) -> None:
        artifact = build_artifact(
            p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t",
            opportunity_research_by_ticker={"AAA": {"research_priority": "BUCKET_ONLY"}},
        )
        self.assertEqual(artifact["records"]["AAA"]["opportunity_research"], {"research_priority": "BUCKET_ONLY"})
        self.assertNotIn("opportunity_research", artifact["records"]["BBB"])
        self.assertEqual(artifact["opportunity_research_coverage"]["attached_ticker_count"], 1)
        self.assertFalse(artifact["opportunity_research_coverage"]["provider_facts_flattened_into_official_facts"])

    def test_promoted_ticker_uses_official_record_not_stale_frozen_disposition(self) -> None:
        """PNJ was STATEMENT_SCOPE_UNKNOWN in the frozen P3-F10 checkpoint but is officially
        qualified in the current P3-F13 refresh -- the join must prefer the current truth and
        record the supersession, never silently keep serving the stale disposition."""
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        record = artifact["records"]["PNJ"]
        self.assertEqual(record["authority_tier"], OFFICIAL_TIER)
        self.assertEqual(record["sector"], "corporate")
        self.assertEqual(record["supersedes_frozen_p3f10_disposition"], "STATEMENT_SCOPE_UNKNOWN")

    def test_issuers_with_usable_deterministic_metrics_excludes_blocked_official_issuer(self) -> None:
        """An issuer can have official facts (evidence retained) without a single usable
        deterministic metric (every ratio blocked on a missing input) -- the two coverage
        numbers must never be conflated into one."""
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        self.assertEqual(artifact["coverage"]["issuers_with_official_facts"], 2)
        self.assertEqual(artifact["coverage"]["issuers_with_usable_deterministic_metrics"], 1)

    def test_official_tier_never_carries_provider_blocked_reason(self) -> None:
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        for ticker in ("GAS", "PNJ"):
            self.assertNotIn("provider_tier_blocked_reason", artifact["records"][ticker])

    def test_provider_tier_forbidden_uses_present_and_no_value_computed(self) -> None:
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        aaa = artifact["records"]["AAA"]
        self.assertIn("official_label", aaa["forbidden_uses"])
        self.assertEqual(aaa["scope_currency_scale_status"], "UNKNOWN_FAIL_CLOSED")
        self.assertNotIn("value", aaa)
        self.assertNotIn("metrics", aaa)

    def test_provider_series_trend_requires_same_provider_consecutive_reported_facts(self) -> None:
        self.rows[0]["reporting_periods"] = ["2025-Q4", "2026-Q1"]
        facts = {
            "AAA": [
                {"canonical_metric": "total_assets", "status": "provider_reported", "provider": "VCI", "statement_family": "balance_sheet", "period_end": "2025-12-31", "statement_scope": "consolidated",
                 "reporting_period": "2025-Q4", "value": 100, "fact_id": "old",
                 "source_observation_ids": ["old-observation"], "source_sha256": "same-sha"},
                {"canonical_metric": "total_assets", "status": "provider_reported", "provider": "VCI", "statement_family": "balance_sheet", "period_end": "2026-03-31", "statement_scope": "consolidated",
                 "reporting_period": "2026-Q1", "value": 125, "fact_id": "new",
                 "source_observation_ids": ["new-observation"], "source_sha256": "same-sha"},
                {"canonical_metric": "net_income", "status": "provider_reported", "provider": "KBS",
                 "reporting_period": "2026-Q1", "value": 1, "fact_id": "orphan", "source_observation_ids": []},
            ]
        }
        artifact = build_artifact(
            p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current,
            requested_at="t", provider_series_by_ticker=facts,
        )
        trends = artifact["records"]["AAA"]["provider_series_trends"]
        assets = trends["metrics"]["assets_direction"]
        self.assertEqual(assets["status"], "AVAILABLE")
        self.assertEqual(assets["provider"], "VCI")
        self.assertEqual(assets["periods"], ["2025-Q4", "2026-Q1"])
        self.assertEqual(assets["direction"], "INCREASED")
        self.assertEqual(assets["authority_tier"], PROVIDER_TIER)
        self.assertNotIn("value", assets)
        self.assertEqual(trends["metrics"]["earnings_growth"]["blocked_reason"], "NO_SAME_PROVIDER_CONSECUTIVE_QUARTER_PAIR")

    def test_provider_series_growth_fails_closed_for_nonpositive_base(self) -> None:
        self.rows[0]["reporting_periods"] = ["2025-Q4", "2026-Q1"]
        facts = {"AAA": [
            {"canonical_metric": "operating_cash_flow", "status": "provider_reported", "provider": "VCI", "statement_family": "cash_flow", "period_start": "2025-10-01", "period_end": "2025-12-31", "cumulative_state": "period_only", "statement_scope": "consolidated", "source_sha256": "same",
             "reporting_period": "2025-Q4", "value": -1, "fact_id": "old", "source_observation_ids": []},
            {"canonical_metric": "operating_cash_flow", "status": "provider_reported", "provider": "VCI", "statement_family": "cash_flow", "period_start": "2026-01-01", "period_end": "2026-03-31", "cumulative_state": "period_only", "statement_scope": "consolidated", "source_sha256": "same",
             "reporting_period": "2026-Q1", "value": 2, "fact_id": "new", "source_observation_ids": []},
        ]}
        artifact = build_artifact(
            p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current,
            requested_at="t", provider_series_by_ticker=facts,
        )
        cashflow = artifact["records"]["AAA"]["provider_series_trends"]["metrics"]["operating_cash_flow_direction"]
        self.assertEqual(cashflow["status"], "AVAILABLE")

    def test_kbs_income_statement_period_schema_recovers_direct_qoq_and_yoy_only(self) -> None:
        self.rows[0]["reporting_periods"] = ["2025-Q1", "2025-Q2", "2026-Q1", "2026-Q2"]
        facts = {"AAA": [
            {"canonical_metric": "revenue", "status": "provider_reported", "provider": "KBS",
             "statement_family": "income_statement", "statement_scope": "consolidated", "source_sha256": "same",
             "reporting_period": period, "value": value, "fact_id": f"r-{period}", "source_observation_ids": [f"r-{period}"]}
            for period, value in (("2025-Q1", 10), ("2025-Q2", 20), ("2026-Q1", 15), ("2026-Q2", 30))
        ] + [
            {"canonical_metric": "net_income", "status": "provider_reported", "provider": "VCI",
             "statement_family": "income_statement", "statement_scope": "consolidated", "source_sha256": "same",
             "reporting_period": period, "value": value, "fact_id": f"n-{period}", "source_observation_ids": [f"n-{period}"]}
            for period, value in (("2025-Q1", 2), ("2025-Q2", 3), ("2026-Q1", 4), ("2026-Q2", 5))
        ]}
        artifact = build_artifact(
            p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current,
            requested_at="t", provider_series_by_ticker=facts,
        )
        revenue = artifact["records"]["AAA"]["provider_series_trends"]["metrics"]["revenue_growth"]
        self.assertEqual(revenue["status"], "AVAILABLE")
        self.assertEqual(revenue["provider"], "KBS")
        self.assertEqual(revenue["period_basis"][0]["duration_basis"], "SINGLE_QUARTER")
        self.assertEqual(revenue["comparisons"]["qoq"]["periods"], ["2026-Q1", "2026-Q2"])
        self.assertEqual(revenue["comparisons"]["yoy"]["periods"], ["2025-Q2", "2026-Q2"])
        self.assertEqual(revenue["comparisons"]["yoy"]["status"], "AVAILABLE")
        earnings = artifact["records"]["AAA"]["provider_series_trends"]["metrics"]["earnings_growth"]
        self.assertEqual(earnings["status"], "BLOCKED")
        self.assertEqual(earnings["blocked_reason"], "PERIOD_FLOW_DURATION_BASIS_UNEVIDENCED")

    def test_blocked_no_source_tier_has_no_allowed_uses(self) -> None:
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        self.assertEqual(artifact["records"]["BBB"]["allowed_uses"], [])

    def test_cross_repository_identity_guard_fails_closed_on_mismatch(self) -> None:
        tampered = deepcopy(self.p3f13_current)
        tampered["source_artifacts"]["p3f10"] = "wrong-identity"
        with self.assertRaises(ValueError):
            build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=tampered, requested_at="t")

    def test_cohort_size_mismatch_fails_closed(self) -> None:
        tampered = deepcopy(self.p3f13_current)
        tampered["cohort_identity"]["total_cohort_count"] = 999
        with self.assertRaises(ValueError):
            build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=tampered, requested_at="t")

    def test_no_valuation_ranking_or_recommendation_authority(self) -> None:
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        boundary = artifact["authority_boundary"]
        self.assertFalse(boundary["authority_promoted"])
        self.assertFalse(boundary["valuation_or_ranking_or_recommendation_produced"])
        self.assertTrue(boundary["new_evidence_acquired"])

    def test_content_identity_self_verifies(self) -> None:
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        identity = content_identity(artifact)
        self.assertEqual(identity["artifact_sha256"], artifact["artifact_sha256"])
        self.assertEqual(identity["artifact_identity"], artifact["artifact_identity"])

    def test_deterministic_given_same_inputs(self) -> None:
        first = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        second = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        self.assertEqual(first, second)

    def test_no_ticker_specific_branch_in_source(self) -> None:
        import market_wide_current_fundamental_research as module
        source = inspect.getsource(module)
        self.assertNotIn("if ticker ==", source)
        artifact = build_artifact(p3f10_frozen=self.p3f10_frozen, p3f13_current=self.p3f13_current, requested_at="t")
        self.assertEqual(artifact["ticker_specific_branch_audit"]["status"], "PASS")


class LiveIntegration(unittest.TestCase):
    """Exercises the real retained P3-F10/P3-F13 corpus, matching the convention already used by
    tests/test_p3f13_official_financial_evidence_scaleout.py (execute() fresh in setUp)."""

    def setUp(self) -> None:
        self.artifact = execute()

    def test_real_cohort_and_tier_counts(self) -> None:
        coverage = self.artifact["coverage"]
        self.assertEqual(coverage["candidate_count"], 523)
        self.assertEqual(coverage["issuers_with_official_facts"], 13)
        self.assertEqual(coverage["provider_research_tier_count"], 507)
        self.assertEqual(coverage["blocked_no_source_count"], 3)
        self.assertEqual(13 + 507 + 3, coverage["candidate_count"])

    def test_real_metric_counts_match_p3f13(self) -> None:
        coverage = self.artifact["coverage"]
        self.assertEqual(coverage["exact_qualified_metrics"], 94)
        self.assertEqual(coverage["derived_proxy_metrics"], 22)
        self.assertEqual(coverage["missing_or_blocked_metrics"], 49)

    def test_real_provider_series_trends_are_explicitly_bounded(self) -> None:
        coverage = self.artifact["coverage"]
        self.assertGreater(coverage["provider_research_usable_for_series_trends_count"], 0)
        self.assertLessEqual(coverage["provider_research_usable_for_series_trends_count"], 507)
        for record in self.artifact["records"].values():
            if record["authority_tier"] != PROVIDER_TIER:
                continue
            for metric in record["provider_series_trends"]["metrics"].values():
                self.assertEqual(metric["authority_tier"], PROVIDER_TIER)
                self.assertIn(metric["status"], {"AVAILABLE", "BLOCKED"})
                self.assertNotIn("value", metric)
                self.assertIsNotNone(metric["blocked_reason"] if metric["status"] == "BLOCKED" else metric["provider"])

    def test_real_period_basis_recovers_only_kbs_income_statement_growth(self) -> None:
        available = [
            metric for record in self.artifact["records"].values()
            if record["authority_tier"] == PROVIDER_TIER
            for metric in record["provider_series_trends"]["metrics"].values()
            if metric["status"] == "AVAILABLE"
        ]
        self.assertEqual({metric["metric_id"] for metric in available}, {
            "revenue_growth", "earnings_growth", "assets_direction", "equity_direction", "operating_cash_flow_direction",
        })
        self.assertEqual(self.artifact["coverage"]["provider_research_usable_for_series_trends_count"], 494)
        self.assertEqual(len(available), 1205)
        contract = self.artifact["provider_financial_period_basis_contract"]
        self.assertEqual(contract["metric_family_classification"]["revenue"], "PERIOD_FLOW")
        self.assertEqual(contract["income_statement_provider_semantics"]["KBS"]["period_basis"]["Q2"], "SINGLE_QUARTER")
        self.assertEqual(contract["income_statement_provider_semantics"]["VCI"]["period_basis"]["Q2"], "UNKNOWN")
        self.assertEqual(contract["metric_family_classification"]["total_assets"], "POINT_IN_TIME_STOCK")

    def test_pnj_and_fpt_are_official_and_supersede_frozen_disposition(self) -> None:
        for ticker in ("PNJ", "FPT"):
            record = self.artifact["records"][ticker]
            self.assertEqual(record["authority_tier"], OFFICIAL_TIER)
            self.assertEqual(record.get("supersedes_frozen_p3f10_disposition"), "STATEMENT_SCOPE_UNKNOWN")

    def test_bank_and_securities_not_applicable_metrics_preserved(self) -> None:
        vcb = self.artifact["records"]["VCB"]
        reasons = {m["blocked_reason"] for m in vcb["blocked_metrics"] if m["status"] == "NOT_APPLICABLE"}
        self.assertTrue(any("BANK" in reason for reason in reasons))

    def test_sector_coverage_reconciles_to_candidate_count(self) -> None:
        broad = self.artifact["sector_coverage"]["broad_sector_distribution_all_candidates"]
        self.assertEqual(sum(broad.values()), self.artifact["coverage"]["candidate_count"])

    def test_retained_entity_class_scaleout_is_evidence_backed_and_fail_closed(self) -> None:
        coverage = self.artifact["entity_class_scaleout_coverage"]
        self.assertEqual(coverage["before_entity_class_distribution"], {
            "bank": 28, "corporate": 13, "finance_company": 1,
            "insurance": 6, "securities": 33, "unknown": 442,
        })
        self.assertEqual(coverage["after_entity_class_distribution"], {
            "bank": 28, "corporate": 452, "finance_company": 1,
            "insurance": 7, "securities": 33, "unknown": 2,
        })
        self.assertEqual(coverage["resolved_unknown_count"], 440)
        self.assertEqual(coverage["conflicting_count"], 0)
        self.assertEqual({ticker for ticker, record in self.artifact["records"].items()
                          if record["entity_class"] == "unknown"}, {"F88", "OGC"})
        for ticker in ("F88", "OGC"):
            provenance = self.artifact["records"][ticker]["entity_class_provenance"]
            self.assertEqual(provenance["classification_status"], "UNKNOWN")
            self.assertEqual(provenance["source_observations"][0]["reason"],
                             "AMBIGUOUS_FINANCIAL_SERVICES_PROVIDER_INDUSTRY")

    def test_entity_class_applicability_never_blocks_provider_series_only_by_class(self) -> None:
        record = self.artifact["records"]["ABB"]
        self.assertEqual(record["entity_class"], "bank")
        self.assertEqual(record["entity_class_applicability"]["sector_metric_applicability"]["ebitda"]["applicability"],
                         "NOT_APPLICABLE")
        self.assertEqual(record["entity_class_applicability"]["provider_series_trend_policy"]["status"],
                         "PERMITTED_PROVIDER_RESEARCH_DESCRIPTIVE_ONLY")

    def test_trajectory_context_is_descriptive_and_coverage_explicit(self) -> None:
        coverage = self.artifact["fundamental_trajectory_context_coverage"]
        self.assertEqual(coverage["issuers_with_any_trajectory_context"], 507)
        self.assertEqual(coverage["issuers_with_income_trajectory"], 83)
        self.assertEqual(coverage["issuers_with_balance_sheet_trajectory"], 494)
        self.assertEqual(coverage["issuers_with_ocf_trajectory"], 66)
        self.assertEqual(coverage["issuers_with_multi_dimensional_trajectory"], 133)
        self.assertEqual(coverage["acceleration_available_count"], 0)
        self.assertEqual(sum(coverage["revenue_earnings_alignment"].values()), 523)
        self.assertEqual(coverage["revenue_earnings_alignment"]["BOTH_EXPANDING"], 22)

    def test_trajectory_context_preserves_provider_official_boundary(self) -> None:
        provider = self.artifact["records"]["AAA"]["fundamental_trajectory_context"]
        official = self.artifact["records"]["VCB"]["fundamental_trajectory_context"]
        self.assertEqual(provider["authority_tier"], PROVIDER_TIER)
        self.assertEqual(provider["trajectory_status"], "AVAILABLE")
        self.assertIsNone(provider["official_metric_context"])
        self.assertEqual(official["authority_tier"], OFFICIAL_TIER)
        self.assertEqual(official["trajectory_status"], "OFFICIAL_METRIC_CONTEXT_ONLY")
        self.assertIsNone(official["revenue_direction"])
        self.assertNotIn("score", provider)
        self.assertNotIn("recommendation", provider)

    def test_content_identity_is_self_consistent(self) -> None:
        identity = content_identity(self.artifact)
        self.assertEqual(identity["artifact_sha256"], self.artifact["artifact_sha256"])

    def test_no_valuation_ranking_recommendation_authority(self) -> None:
        """Governance disclosure keys/lists legitimately *name* forbidden concepts (e.g. the
        authority_boundary key "valuation_or_ranking_or_recommendation_produced", or
        "buy_sell_recommendation" inside non_authorized_downstream_uses) as things this artifact
        must never produce -- that is the opposite of producing them, so this checks the actual
        booleans/values, not a fragile whole-artifact substring scan."""
        boundary = self.artifact["authority_boundary"]
        self.assertFalse(boundary["valuation_or_ranking_or_recommendation_produced"])
        self.assertFalse(boundary["authority_promoted"])
        self.assertTrue(boundary["new_evidence_acquired"])
        self.assertFalse(boundary["new_source_route_approved"])
        for ticker, record in self.artifact["records"].items():
            self.assertNotIn("target_price", record)
            self.assertNotIn("recommendation", record)
            self.assertNotIn("ranking", record)


if __name__ == "__main__":
    unittest.main()
