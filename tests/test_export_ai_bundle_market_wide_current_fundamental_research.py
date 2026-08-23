"""Unit tests for attaching market_wide_current_fundamental_research to the AI bundle
(export_ai_bundle.py).

Verifies the evidence-bounded attachment contract:
- Opt-in flag --include-market-wide-current-fundamental-research attaches
  `market_wide_current_fundamental_research`; disabled by default, the retained artifact file is
  never even opened.
- An explicit --market-wide-current-fundamental-research-path is required; a missing path,
  nonexistent file, or a hash mismatch against the artifact's own recomputed content_identity()
  fails the whole attach step closed (no key on any ticker) rather than degrading partially.
- Per-ticker fields are reused verbatim -- never recalculated: an OFFICIAL_QUALIFIED ticker keeps
  its full metric/lineage detail, a PROVIDER_RESEARCH ticker keeps its disposition/blocked reason
  and allowed/forbidden-use list, and neither is ever upgraded to the other tier.
- A ticker absent from the artifact's universe altogether gets no key.
- is_actionable=False unconditionally.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import export_ai_bundle as bundle
from market_wide_current_fundamental_research import build_artifact, content_identity


def _frozen_p3f10() -> dict:
    rows = [
        {"ticker": "GAS", "disposition": "EVIDENCE_QUALIFIED", "sector": "corporate", "blocker": None,
         "raw_observation_state": "RAW_OBSERVED", "raw_observation_count": 500,
         "raw_statement_families": ["balance_sheet", "income_statement"], "raw_providers": ["VCI"],
         "reporting_periods": ["2024-Q4"]},
        {"ticker": "AAA", "disposition": "STATEMENT_SCOPE_UNKNOWN", "sector": "unknown",
         "blocker": "PROVIDER_OBSERVATION_SCOPE_CURRENCY_SCALE_NOT_INDEPENDENTLY_EVIDENCED",
         "raw_observation_state": "RAW_OBSERVED", "raw_observation_count": 200,
         "raw_statement_families": ["balance_sheet"], "raw_providers": ["VCI", "KBS"],
         "reporting_periods": ["2024-Q4"]},
        {"ticker": "BBB", "disposition": "SOURCE_MISSING", "sector": "unknown",
         "blocker": "MISSING_FINANCIAL_SOURCE_PAYLOAD", "raw_observation_state": "RAW_NOT_RETAINED",
         "raw_observation_count": 0, "raw_statement_families": [], "raw_providers": [], "reporting_periods": []},
    ]
    return {
        "artifact_identity": "p3f10_generic_fundamental_evidence_scaleout:FIXTUREHASH",
        "cohort_identity": {"identity": "cohort_empirically_active:FIXTURE", "member_count": 3,
                            "as_of_session": "2026-08-20"},
        "instrument_dispositions": rows,
    }


def _p3f13_current(p3f10_identity: str) -> dict:
    gas_readiness = {
        "issuer_identity": {"ticker": "GAS", "entity_class": "corporate"},
        "fundamental_research_readiness": "PARTIAL",
        "authoritative_periods_available": ["2023", "2024"],
        "metrics": [
            {"metric_id": "net_margin", "status": "EXACT_QUALIFIED", "value": 0.12,
             "blocked_reason": None, "periods_used": ["2024"], "evidence_lineage": [{"citation_id": "gas-1"}]},
            {"metric_id": "debt_to_equity", "status": "MISSING", "value": None,
             "blocked_reason": "MISSING_INPUTS:total_interest_bearing_debt", "periods_used": ["2024"],
             "evidence_lineage": []},
        ],
        "metric_family_states": {"profitability": "PROFITABILITY_AVAILABLE", "balance_sheet": "BALANCE_SHEET_BLOCKED"},
        "history_readiness": {"compatible_annual_period_count": 2},
        "evidence_completeness": {"positive_authoritative_fact_count": 5},
    }
    return {
        "artifact_identity": "p3f13_official_financial_evidence_scaleout:FIXTUREHASH",
        "cohort_identity": {"total_cohort_count": 3},
        "source_artifacts": {"p3f10": p3f10_identity},
        "newly_qualified_issuers": [],
        "acquisition_dispositions": [
            {"ticker": "AAA", "disposition": "NO_APPROVED_ROUTE_FOUND",
             "reason": "NO_APPROVED_OFFICIAL_SOURCE_ROUTE_IN_REGISTRY"},
        ],
        "refreshed_fundamental_readiness": {
            "issuer_research_readiness": [gas_readiness],
            "coverage_summary": {"metric_status_counts": {"EXACT_QUALIFIED": 1, "DERIVED_PROXY": 0,
                                                            "MISSING": 1, "NOT_APPLICABLE": 0}},
        },
    }


def _build_fixture_artifact() -> dict:
    p3f10 = _frozen_p3f10()
    p3f13 = _p3f13_current(p3f10["artifact_identity"])
    return build_artifact(p3f10_frozen=p3f10, p3f13_current=p3f13, requested_at="2026-08-23T00:00:00Z")


class AttachMarketWideCurrentFundamentalResearch(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = _build_fixture_artifact()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "market_wide_current_fundamental_research_artifact.json"
        self.path.write_text(json.dumps(self.artifact), encoding="utf-8")
        self.bundle_entries = {"GAS": {}, "AAA": {}, "BBB": {}, "ZZZ_OUTSIDE_UNIVERSE": {}}

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_disabled_by_default_leaves_bundle_untouched(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), False, str(self.path))
        for entry in result.values():
            self.assertNotIn("market_wide_current_fundamental_research", entry)

    def test_missing_path_leaves_bundle_untouched(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, None)
        for entry in result.values():
            self.assertNotIn("market_wide_current_fundamental_research", entry)

    def test_nonexistent_file_fails_closed(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(Path(self.tmpdir.name) / "absent.json"))
        for entry in result.values():
            self.assertNotIn("market_wide_current_fundamental_research", entry)

    def test_hash_mismatch_fails_closed_for_every_ticker(self) -> None:
        tampered = dict(self.artifact)
        tampered["records"] = dict(tampered["records"])
        tampered["records"]["GAS"] = {**tampered["records"]["GAS"], "fundamental_research_readiness": "READY"}
        tampered_path = Path(self.tmpdir.name) / "tampered.json"
        tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(tampered_path))
        for entry in result.values():
            self.assertNotIn("market_wide_current_fundamental_research", entry)

    def test_official_qualified_ticker_keeps_full_metric_detail(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(self.path))
        gas = result["GAS"]["market_wide_current_fundamental_research"]
        self.assertEqual(gas["authority_tier"], "OFFICIAL_QUALIFIED")
        self.assertEqual(gas["status"], "official_qualified")
        self.assertEqual(len(gas["metrics"]), 2)
        self.assertFalse(gas["is_actionable"])
        self.assertIn("coverage", gas)
        self.assertEqual(gas["coverage"]["issuers_with_official_facts"], 1)

    def test_provider_research_ticker_keeps_disposition_and_forbidden_uses_never_a_value(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(self.path))
        aaa = result["AAA"]["market_wide_current_fundamental_research"]
        self.assertEqual(aaa["authority_tier"], "PROVIDER_RESEARCH")
        self.assertEqual(aaa["status"], "provider_research")
        self.assertEqual(aaa["disposition"], "STATEMENT_SCOPE_UNKNOWN")
        self.assertIn("official_label", aaa["forbidden_uses"])
        self.assertNotIn("metrics", aaa)
        self.assertNotIn("value", aaa)
        self.assertFalse(aaa["is_actionable"])

    def test_blocked_no_source_ticker(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(self.path))
        bbb = result["BBB"]["market_wide_current_fundamental_research"]
        self.assertEqual(bbb["authority_tier"], "BLOCKED")
        self.assertEqual(bbb["status"], "blocked")
        self.assertEqual(bbb["allowed_uses"], [])

    def test_ticker_outside_universe_has_no_key(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(self.path))
        self.assertNotIn("market_wide_current_fundamental_research", result["ZZZ_OUTSIDE_UNIVERSE"])

    def test_no_recompute_deepcopy_not_shared_reference(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(self.path))
        result["GAS"]["market_wide_current_fundamental_research"]["metrics"][0]["value"] = 999999.0
        self.assertEqual(self.artifact["records"]["GAS"]["metrics"][0]["value"], 0.12)

    def test_never_upgrades_provider_tier_to_official(self) -> None:
        result = bundle.attach_market_wide_current_fundamental_research(
            copy.deepcopy(self.bundle_entries), True, str(self.path))
        self.assertNotEqual(result["AAA"]["market_wide_current_fundamental_research"]["authority_tier"],
                           "OFFICIAL_QUALIFIED")


if __name__ == "__main__":
    unittest.main()
