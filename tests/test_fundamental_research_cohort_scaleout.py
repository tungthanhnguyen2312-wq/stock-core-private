"""MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1.

Real end-to-end proof (mirrors tests/test_financial_fact_coverage_recovery.py's own
``test_widening_cohort_is_byte_identical_for_the_narrow_subset`` convention) plus a few
synthetic-fixture unit tests for the pure classification/sampling helpers.
"""
from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path

import financial_fact_coverage_recovery as ffcr
import fundamental_cross_sectional_scoring as fcss
import fundamental_research_cohort_scaleout as scaleout
import market_wide_historical_fundamentals_scaleout as mwhfs
import p3f10_fundamental_evidence_scaleout as p3f10mod
import p3f13_official_financial_evidence_scaleout as p3f13mod

ROOT = Path(__file__).resolve().parents[1]
AS_OF_SESSION = "2026-08-30"
REQUESTED_AT = "2026-08-30T00:00:00+07:00"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class RealWideCohortTest(unittest.TestCase):
    """Builds the wide cohort once against real retained evidence and exercises it. Skips
    cleanly (rather than failing) if the large gitignored retained-evidence stores this
    milestone reads are not present on this machine -- see fundamental_research_cohort_scaleout.py
    module docstring for why that data is not git-tracked."""

    @classmethod
    def setUpClass(cls):
        required = (
            p3f10mod.DEFAULT_RAW_STATE, p3f10mod.DEFAULT_CANONICAL_STATE, p3f10mod.DEFAULT_P3E,
            p3f13mod.DEFAULT_MANIFEST, p3f13mod.DEFAULT_RAW_OBS_DIR,
            ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
            / "current_official_market_universe_artifact.json",
        )
        missing = [str(p) for p in required if not Path(p).exists()]
        if missing:
            raise unittest.SkipTest(f"retained evidence not locally available: {missing[:2]}")

        official = _read(ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
                          / "current_official_market_universe_artifact.json")
        cls.official_tickers = ffcr.official_research_universe_tickers(official)
        raw_state = _read(p3f10mod.DEFAULT_RAW_STATE)
        canonical_state = _read(p3f10mod.DEFAULT_CANONICAL_STATE)
        p3e = _read(p3f10mod.DEFAULT_P3E)
        registry = _read(p3f10mod.DEFAULT_REGISTRY)
        manifest = _read(p3f13mod.DEFAULT_MANIFEST)

        cls.narrow_historical = mwhfs.execute(cohort_selector="LEGACY_HISTORICAL_FROZEN_523_V1")
        cls.narrow_cross_sectional = scaleout.build_wide_fundamental_cross_sectional_artifact(
            wide_historical_fundamentals=cls.narrow_historical)
        cls.narrow_tickers = sorted(cls.narrow_cross_sectional["records"])

        cls.wide_historical = scaleout.build_wide_historical_fundamentals_artifact(
            official_tickers=cls.official_tickers, raw_state=raw_state, canonical_state=canonical_state,
            p3e=p3e, registry=registry, manifest_records=manifest.get("records", []),
            evidence_root=p3f13mod.DEFAULT_EVIDENCE_ROOT, raw_obs_dir=p3f13mod.DEFAULT_RAW_OBS_DIR,
            as_of_session=AS_OF_SESSION, requested_at=REQUESTED_AT,
        )
        cls.wide_cross_sectional = scaleout.build_wide_fundamental_cross_sectional_artifact(
            wide_historical_fundamentals=cls.wide_historical)
        cls.reconciliation = scaleout.build_root_cause_reconciliation(
            universe_raw_denominator=len(official.get("records") or {}),
            universe_candidate_count=sum(1 for r in (official.get("records") or {}).values() if r.get("stocklookup_candidate")),
            official_tickers=cls.official_tickers, narrow_cohort_tickers=cls.narrow_tickers,
            wide_historical_fundamentals=cls.wide_historical, wide_cross_sectional=cls.wide_cross_sectional,
        )

    # -- 1. full governed denominator evaluated -----------------------------------------
    def test_full_governed_denominator_evaluated(self):
        manifest_tickers = {row["ticker"] for row in self.wide_historical["manifest"]}
        self.assertEqual(manifest_tickers, set(self.official_tickers))
        self.assertEqual(self.wide_cross_sectional["denominator"], len(self.official_tickers))
        self.assertTrue(self.reconciliation["residual_zero"])
        self.assertEqual(self.reconciliation["residual_official_tickers_missing_from_wide_manifest"], [])

    # -- 2. qualified excluded name becomes eligible once the generic ceiling is removed --
    def test_qualified_excluded_name_becomes_eligible(self):
        narrow_set = set(self.narrow_tickers)
        manifest_by_ticker = {row["ticker"]: row for row in self.wide_historical["manifest"]}
        newly_eligible = sorted(
            t for t, row in manifest_by_ticker.items()
            if t not in narrow_set and row["terminal_disposition"] == "OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE"
            and any(a["axis_status"] == "READY_RESEARCH_ONLY" for a in self.wide_cross_sectional["records"][t]["axes"].values())
        )
        self.assertGreater(len(newly_eligible), 0, "expected at least one previously-excluded, now research-ready ticker")
        example = newly_eligible[0]
        self.assertNotIn(example, self.narrow_cross_sectional["records"])
        self.assertIn(example, self.wide_cross_sectional["records"])
        record = self.wide_cross_sectional["records"][example]
        self.assertEqual(record["entity_class"], "corporate")
        self.assertGreater(manifest_by_ticker[example]["canonical_fact_count"], 0)

    # -- unqualified name remains unavailable --------------------------------------------
    def test_unqualified_name_remains_unavailable(self):
        manifest_by_ticker = {row["ticker"]: row for row in self.wide_historical["manifest"]}
        no_evidence = [t for t, row in manifest_by_ticker.items() if row["terminal_disposition"] == "NO_ELIGIBLE_PROVIDER_FACTS"]
        self.assertGreater(len(no_evidence), 0)
        example = sorted(no_evidence)[0]
        self.assertEqual(manifest_by_ticker[example]["canonical_fact_count"], 0)
        axes = self.wide_cross_sectional["records"][example]["axes"]
        self.assertTrue(all(a["axis_status"] == "INSUFFICIENT_INPUTS" for a in axes.values()),
                        "a ticker with zero retained facts must never show a fabricated READY_RESEARCH_ONLY axis")

    # -- stale/unusable evidence (fact-count zero) remains unavailable, never fabricated --
    def test_missing_required_facts_remain_fail_closed(self):
        """This layer's contract has no separate 'staleness' gate distinct from fact presence
        (freshness/staleness is a different, upstream evidence-tier concern -- see
        market_wide_current_fundamental_research.py); here 'unusable retained evidence' means
        zero classified facts, and it must fail closed to INSUFFICIENT_INPUTS on every axis,
        never a fabricated value."""
        for record in self.wide_cross_sectional["records"].values():
            confidence = record["data_confidence"]
            if confidence["status"] == "INSUFFICIENT_INPUTS":
                for axis in record["axes"].values():
                    if axis["axis_status"] == "READY_RESEARCH_ONLY":
                        self.fail("a record with INSUFFICIENT_INPUTS data_confidence must not carry a READY_RESEARCH_ONLY axis")

    # -- unsupported security remains NOT_APPLICABLE-equivalent ---------------------------
    def test_unsupported_security_remains_not_applicable(self):
        manifest_by_ticker = {row["ticker"]: row for row in self.wide_historical["manifest"]}
        non_corporate = [t for t, row in manifest_by_ticker.items() if row["entity_type"] not in ("corporate", "unknown")]
        self.assertGreater(len(non_corporate), 0)
        for ticker in non_corporate[:25]:
            self.assertEqual(manifest_by_ticker[ticker]["terminal_disposition"], "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE")
            axes = self.wide_cross_sectional["records"][ticker]["axes"]
            self.assertTrue(all(a["axis_status"] != "READY_RESEARCH_ONLY" for a in axes.values()),
                            f"{ticker} ({manifest_by_ticker[ticker]['entity_type']}) must not receive a fabricated corporate axis score")

    # -- no ticker allowlist ---------------------------------------------------------------
    def test_no_ticker_allowlist_in_scaleout_module(self):
        source = Path(ROOT / "fundamental_research_cohort_scaleout.py").read_text(encoding="utf-8")
        for pattern in ('ticker == "', "ticker == '", 'if ticker in {"', "if ticker in ('", "TICKER_ALLOWLIST"):
            self.assertNotIn(pattern, source, f"found ticker-specific branch pattern: {pattern}")

    # -- deterministic ordering / identity --------------------------------------------------
    def test_deterministic_ordering_and_cohort_identity(self):
        rebuild = scaleout.build_wide_fundamental_cross_sectional_artifact(wide_historical_fundamentals=self.wide_historical)
        self.assertEqual(rebuild, self.wide_cross_sectional)
        self.assertEqual(rebuild["artifact_sha256"], self.wide_cross_sectional["artifact_sha256"])
        self.assertEqual(list(self.wide_cross_sectional["records"]), sorted(self.wide_cross_sectional["records"]))

        samples_a = scaleout.sample_newly_admitted_lineage(
            wide_cross_sectional=self.wide_cross_sectional, wide_historical_fundamentals=self.wide_historical,
            narrow_tickers=self.narrow_tickers, limit=12)
        samples_b = scaleout.sample_newly_admitted_lineage(
            wide_cross_sectional=self.wide_cross_sectional, wide_historical_fundamentals=self.wide_historical,
            narrow_tickers=self.narrow_tickers, limit=12)
        self.assertEqual(samples_a, samples_b)

    # -- provenance retained -----------------------------------------------------------------
    def test_provenance_retained_in_lineage_sample(self):
        samples = scaleout.sample_newly_admitted_lineage(
            wide_cross_sectional=self.wide_cross_sectional, wide_historical_fundamentals=self.wide_historical,
            narrow_tickers=self.narrow_tickers, limit=5)
        manifest_by_ticker = {row["ticker"]: row for row in self.wide_historical["manifest"]}
        self.assertEqual(len(samples), 5)
        for sample in samples:
            manifest_row = manifest_by_ticker[sample["ticker"]]
            self.assertEqual(sample["entity_class"], manifest_row["entity_type"])
            self.assertEqual(sample["terminal_disposition"], manifest_row["terminal_disposition"])
            self.assertEqual(sample["canonical_fact_count"], manifest_row["canonical_fact_count"])

    # -- same scoring semantics preserved: narrow subset is byte-identical -------------------
    def test_same_scoring_semantics_preserved_for_narrow_subset(self):
        diff = scaleout.build_narrow_vs_wide_lineage_diff(
            narrow_historical_fundamentals=self.narrow_historical, wide_historical_fundamentals=self.wide_historical,
            narrow_tickers=self.narrow_tickers,
        )
        self.assertTrue(diff["narrow_subset_facts_byte_identical"], diff["mismatched_tickers"][:5])
        self.assertEqual(diff["narrow_tickers_missing_from_wide"], [])

    def test_axis_formula_and_feature_set_unchanged(self):
        self.assertEqual(scaleout.AXES, tuple(fcss.AXES))
        source = inspect.getsource(scaleout.build_wide_fundamental_cross_sectional_artifact)
        self.assertIn("fcss.build_artifact(base=", source, "wrapper must delegate to the unmodified engine, not reimplement it")
        for record in self.wide_cross_sectional["records"].values():
            for axis in record["axes"].values():
                if axis["axis_status"] == "READY_RESEARCH_ONLY":
                    self.assertEqual(axis["method"], "AVAILABLE_FEATURE_PERCENTILE_MEAN/v1")

    def test_root_cause_finding_is_reconciled_not_asserted(self):
        universe = self.reconciliation["universe"]
        self.assertEqual(universe["applicable_official_research_universe"], len(self.official_tickers))
        overall = self.reconciliation["terminal_disposition_distribution"]["overall"]
        self.assertEqual(sum(overall.values()), self.reconciliation["wide_cohort_size"])
        newly_admitted = self.reconciliation["newly_admitted_tickers"]
        self.assertEqual(newly_admitted["count"], self.reconciliation["wide_cohort_size"] - len(self.narrow_tickers))
        self.assertEqual(sum(newly_admitted["terminal_disposition_distribution"].values()), newly_admitted["count"])

    def test_legacy_historical_reproduction_requires_an_explicit_selector(self):
        """The frozen cohort remains reproducible, but cannot be the implicit default."""
        with self.assertRaisesRegex(ValueError, "LEGACY_HISTORICAL_COHORT_REQUIRES_EXPLICIT_SELECTOR"):
            mwhfs.execute()
        narrow_again = mwhfs.execute(cohort_selector="LEGACY_HISTORICAL_FROZEN_523_V1")
        self.assertEqual(narrow_again["operational_proxy"]["records"].keys(), self.narrow_historical["operational_proxy"]["records"].keys())
        self.assertEqual(len(narrow_again["operational_proxy"]["records"]), 523)


class SyntheticSamplingTest(unittest.TestCase):
    """Pure, small, synthetic fixtures for the sampling helpers -- no real data required."""

    @staticmethod
    def _wide_historical(manifest_rows):
        return {"manifest": manifest_rows}

    @staticmethod
    def _wide_cross_sectional(records):
        return {"records": records}

    def test_sample_sector_special_case_falls_back_across_entity_types(self):
        manifest = self._wide_historical([
            {"ticker": "BANKX", "entity_type": "bank", "terminal_disposition": "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE", "canonical_fact_count": 0},
            {"ticker": "INSY", "entity_type": "insurance", "terminal_disposition": "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE", "canonical_fact_count": 0},
        ])
        records = self._wide_cross_sectional({"BANKX": {"axes": {}}, "INSY": {"axes": {}}})
        # BANKX is already in the narrow cohort (no newly-admitted bank); INSY is newly admitted.
        result = scaleout.sample_sector_special_case(
            wide_cross_sectional=records, wide_historical_fundamentals=manifest,
            narrow_tickers=["BANKX"], entity_types=("bank", "insurance"),
        )
        self.assertEqual([r["ticker"] for r in result], ["INSY"])
        self.assertEqual(result[0]["expected_treatment"].split(" -- ")[0], "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE")

    def test_sample_still_unavailable_reports_missing_and_no_evidence(self):
        manifest = self._wide_historical([
            {"ticker": "OK1", "entity_type": "corporate", "terminal_disposition": "OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE", "canonical_fact_count": 10},
            {"ticker": "ZEROFACT", "entity_type": "corporate", "terminal_disposition": "NO_ELIGIBLE_PROVIDER_FACTS", "canonical_fact_count": 0},
        ])
        result = scaleout.sample_still_unavailable(
            official_tickers=["OK1", "ZEROFACT", "GHOST"], wide_historical_fundamentals=manifest,
            narrow_tickers=[], limit=5,
        )
        reasons = {row["ticker"]: row["reason"] for row in result}
        self.assertEqual(reasons.get("GHOST"), "NOT_IN_WIDE_MANIFEST_RESIDUAL")
        self.assertEqual(reasons.get("ZEROFACT"), "NO_ELIGIBLE_PROVIDER_FACTS")
        self.assertNotIn("OK1", reasons)

    def test_root_cause_reconciliation_on_tiny_synthetic_universe(self):
        manifest = self._wide_historical([
            {"ticker": "OLD1", "entity_type": "corporate", "terminal_disposition": "OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE", "canonical_fact_count": 5},
            {"ticker": "NEW1", "entity_type": "corporate", "terminal_disposition": "OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE", "canonical_fact_count": 5},
            {"ticker": "NEW2", "entity_type": "corporate", "terminal_disposition": "NO_ELIGIBLE_PROVIDER_FACTS", "canonical_fact_count": 0},
            {"ticker": "NEW3", "entity_type": "bank", "terminal_disposition": "ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE", "canonical_fact_count": 0},
        ])
        records = self._wide_cross_sectional({
            "OLD1": {"axes": {"A": {"axis_status": "READY_RESEARCH_ONLY"}}},
            "NEW1": {"axes": {"A": {"axis_status": "READY_RESEARCH_ONLY"}}},
            "NEW2": {"axes": {"A": {"axis_status": "INSUFFICIENT_INPUTS"}}},
            "NEW3": {"axes": {"A": {"axis_status": "INSUFFICIENT_INPUTS"}}},
        })
        report = scaleout.build_root_cause_reconciliation(
            universe_raw_denominator=10, universe_candidate_count=6,
            official_tickers=["OLD1", "NEW1", "NEW2", "NEW3"], narrow_cohort_tickers=["OLD1"],
            wide_historical_fundamentals=manifest, wide_cross_sectional=records,
        )
        self.assertTrue(report["residual_zero"])
        self.assertEqual(report["wide_cohort_size"], 4)
        self.assertEqual(report["narrow_cohort_size"], 1)
        self.assertEqual(report["newly_admitted_tickers"]["count"], 3)
        self.assertEqual(
            report["newly_admitted_tickers"]["terminal_disposition_distribution"],
            {"ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE": 1, "NO_ELIGIBLE_PROVIDER_FACTS": 1, "OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE": 1},
        )
        # Rerun on identical inputs must be byte-identical (determinism).
        report_again = scaleout.build_root_cause_reconciliation(
            universe_raw_denominator=10, universe_candidate_count=6,
            official_tickers=["OLD1", "NEW1", "NEW2", "NEW3"], narrow_cohort_tickers=["OLD1"],
            wide_historical_fundamentals=manifest, wide_cross_sectional=records,
        )
        self.assertEqual(report, report_again)

    def test_content_identity_deterministic(self):
        payload = {"a": 1, "b": [1, 2, 3]}
        first = scaleout.content_identity(payload)
        second = scaleout.content_identity(payload)
        self.assertEqual(first, second)
        self.assertEqual(first["artifact_identity"], f"{scaleout.ARTIFACT_TYPE.lower()}:{first['artifact_sha256']}")


if __name__ == "__main__":
    unittest.main()
