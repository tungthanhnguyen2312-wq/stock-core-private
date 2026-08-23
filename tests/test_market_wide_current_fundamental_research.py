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
        self.assertFalse(boundary["new_evidence_acquired"])

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
        self.assertFalse(boundary["new_evidence_acquired"])
        self.assertFalse(boundary["new_source_route_approved"])
        for ticker, record in self.artifact["records"].items():
            self.assertNotIn("target_price", record)
            self.assertNotIn("recommendation", record)
            self.assertNotIn("ranking", record)


if __name__ == "__main__":
    unittest.main()
