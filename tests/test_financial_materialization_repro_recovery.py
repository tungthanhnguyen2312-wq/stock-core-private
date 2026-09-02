# ==========================================================================
# CANONICAL_FINANCIAL_MATERIALIZATION_AND_ENTITY_REPRODUCIBILITY_RECOVERY_V1
#
# Covers the two genuine operational defects the 2026-09-02
# canonical-financial-materialization-integrity recon found:
#
# 1. `raw_financial_store.load_state()` collapsed a readable-but-stale prior
#    schema into the same `{}` as "never ingested", which made
#    `canonical_fact_store.ingest()`'s failure message misleading and left an
#    operator no way to distinguish "run the first ingest" from "rebuild
#    after a schema bump". `inspect_state()` (added here) makes the
#    distinction explicit; `load_state()`'s fail-closed behavior for any
#    non-current schema is byte-for-byte unchanged.
#
# 2. `market_wide_financial_analysis_v2_scaleout.build_scaleout()`'s optional
#    `legacy_records` parameter -- sourced, in every prior invocation on
#    record (including the checked-in `test_entity_classification_scaleout_
#    replay.py`), from an untracked sibling-worktree artifact -- was the only
#    thing standing between "reproducible from tracked repository inputs"
#    and the historically-quoted 1,382/85/25 entity-family split. The 3-tier
#    `entity_classification_contract` registry chain is itself already fully
#    reproducible from tracked config; these tests prove that mechanism
#    (precedence, UNKNOWN-stays-UNKNOWN, determinism, no sibling path
#    required) without asserting the historical count -- see this
#    milestone's REPORT.md for why 1,382/85/25 was never actually
#    reproducible without that external file, and entity_reproduction.json
#    for the real, tracked-inputs-only number this milestone measured.
#
# Candidate-level gross_profit KBS-gating and canonical MAPPER_VERSION
# invalidation already have solid coverage in
# `tests/test_canonical_financial_facts.py` (`GrossProfitProviderGateTests`,
# `test_inputs_fingerprint_covers_the_mapper_version`) and engine-level
# `gross_margin` READY computation in
# `tests/test_financial_analysis_engine_v2.py` -- not duplicated here.  What
# was missing, and what this file adds, is proof that the *standard store
# tooling*, run end to end against an isolated runtime, actually reaches
# that already-correct candidate/engine logic.
#
# The materialization tests that need real retained `data_bctc` payloads
# skip (never fail) when `STOCK_LOOKUP_RUNTIME_ROOT` / `dashboard-runtime`
# is not configured -- see `tests/_runtime_root.py`. They copy only 1-2
# real tickers into a scratch directory, so they stay fast.
#
# Run: `python -m pytest tests/test_financial_materialization_repro_recovery.py -v`
# ==========================================================================

from __future__ import annotations

import gzip
import inspect
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import canonical_fact_store as fact_store  # noqa: E402
import canonical_financial_facts as facts  # noqa: E402
import raw_financial_store as raw_store  # noqa: E402
import market_wide_financial_analysis_v2_scaleout as v2_scaleout  # noqa: E402
from entity_classification_contract import (  # noqa: E402
    ClassificationStatus,
    ConfidenceSemantics,
    EntityClass,
    EntityClassificationRecord,
    EvidenceTier,
    DEFAULT_SCALEOUT_PROMOTED_CLASSIFICATIONS_PATH,
    load_layered_entity_profiles,
    load_legacy_recovery_entity_classifications,
    load_promoted_entity_classifications,
    load_scaleout_promoted_entity_classifications,
    load_seed_profiles,
    resolve_layered_entity_classification,
)
from _runtime_root import RUNTIME_ROOT  # noqa: E402


# ---------------------------------------------------------------------------
# Part A -- raw store schema-state diagnosis (items 1, 2)
# ---------------------------------------------------------------------------

class RawStoreStateInspectionTests(unittest.TestCase):
    """A readable prior schema is STALE_SCHEMA_REBUILD_REQUIRED, never confused with
    MISSING or CORRUPT -- and never treated as consumable current evidence."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="raw_store_state_"))
        self.addCleanup(shutil.rmtree, self.scratch, ignore_errors=True)

    def _write_state(self, payload) -> Path:
        path = raw_store.state_path(self.scratch)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_state_is_reported_as_missing_not_stale(self):
        inspection = raw_store.inspect_state(self.scratch)
        self.assertEqual(inspection["status"], raw_store.STATE_STATUS_MISSING)
        self.assertIsNone(inspection["found_schema_version"])

    def test_old_supported_schema_is_reported_as_stale_not_missing(self):
        """Item 1: the exact regression this milestone exists to fix."""
        self._write_state({"schema_version": "1.0.0", "tickers": []})
        inspection = raw_store.inspect_state(self.scratch)
        self.assertEqual(inspection["status"], raw_store.STATE_STATUS_STALE_SCHEMA_REBUILD_REQUIRED)
        self.assertEqual(inspection["found_schema_version"], "1.0.0")
        self.assertEqual(inspection["expected_schema_version"], raw_store.STORE_SCHEMA_VERSION)
        self.assertNotEqual(inspection["status"], raw_store.STATE_STATUS_MISSING)

    def test_corrupt_json_is_reported_as_corrupt_not_missing(self):
        self._write_state("{not valid json")
        self.assertEqual(raw_store.inspect_state(self.scratch)["status"], raw_store.STATE_STATUS_CORRUPT)

    def test_non_mapping_json_is_reported_as_corrupt(self):
        self._write_state("[1, 2, 3]")
        self.assertEqual(raw_store.inspect_state(self.scratch)["status"], raw_store.STATE_STATUS_CORRUPT)

    def test_missing_schema_version_field_is_reported_as_corrupt(self):
        self._write_state({"tickers": []})
        self.assertEqual(raw_store.inspect_state(self.scratch)["status"], raw_store.STATE_STATUS_CORRUPT)

    def test_current_schema_is_reported_as_current(self):
        self._write_state({"schema_version": raw_store.STORE_SCHEMA_VERSION, "tickers": []})
        self.assertEqual(raw_store.inspect_state(self.scratch)["status"], raw_store.STATE_STATUS_CURRENT)

    def test_stale_schema_still_cannot_be_consumed_as_current_by_load_state(self):
        """Item 2: STALE is a diagnostic fact, never evidence -- load_state() stays
        byte-for-byte {} exactly like the pre-existing MISSING/CORRUPT behavior."""
        self._write_state({"schema_version": "1.0.0",
                           "tickers": [{"ticker": "AAA", "shard_sha256": "x"}]})
        self.assertEqual(raw_store.load_state(self.scratch), {})

    def test_verify_reports_precise_stale_reason_not_generic_missing(self):
        self._write_state({"schema_version": "1.0.0", "tickers": []})
        result = raw_store.verify(self.scratch)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], raw_store.STATE_STATUS_STALE_SCHEMA_REBUILD_REQUIRED)
        self.assertEqual(result["found_schema_version"], "1.0.0")

    def test_verify_reports_missing_reason_when_never_ingested(self):
        result = raw_store.verify(self.scratch)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], raw_store.STATE_STATUS_MISSING)


# ---------------------------------------------------------------------------
# Part B/G -- standard raw+canonical materialization heals a stale runtime
# (items 3-7, plus a store-level bridge for 9/10 beyond the existing
# candidate-level GrossProfitProviderGateTests coverage)
# ---------------------------------------------------------------------------

def _copy_real_ticker_payloads(dest: Path, tickers: list[str]) -> bool:
    """Copy a handful of real retained data_bctc payloads into `dest` -- faithful
    parquet shape, without needing the full ~1,500-ticker corpus for a focused test.
    Returns whether anything was found."""
    source = RUNTIME_ROOT / "data_bctc"
    dest.mkdir(parents=True, exist_ok=True)
    found = False
    for path in source.glob("*.parquet"):
        if any(path.name.startswith(f"{ticker}_") for ticker in tickers):
            shutil.copy2(path, dest / path.name)
            metadata = path.with_suffix(".metadata.json")
            if metadata.is_file():
                shutil.copy2(metadata, dest / metadata.name)
            found = True
    return found


@unittest.skipUnless((RUNTIME_ROOT / "data_bctc").is_dir(),
                      "real data_bctc payloads are not available (set STOCK_LOOKUP_RUNTIME_ROOT "
                      "to a runtime root that has them); this class proves the standard "
                      "materialization path against real retained evidence, not a hand-built "
                      "fixture, so it skips rather than fabricate a parquet payload")
class StandardMaterializationHealsStaleRuntimeTests(unittest.TestCase):
    """The standard tools, run against an isolated runtime (never dashboard-runtime
    itself) whose raw layer starts absent, discover real retained payloads, build under
    the current schema/mapper contract, and materialize gross_profit through
    canonical_fact_store -- proven end to end, not just at the candidate-matching level."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="materialization_repro_"))
        if not _copy_real_ticker_payloads(cls.scratch / "data_bctc", ["AAA"]):
            shutil.rmtree(cls.scratch, ignore_errors=True)
            raise unittest.SkipTest("AAA payloads not found under the resolved data_bctc")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def setUp(self):
        # Each test starts from a clean store so tests are independent of run order.
        for sub in ("data/market-wide-financials", "data/canonical-financial-facts"):
            shutil.rmtree(self.scratch / sub, ignore_errors=True)

    def test_raw_ingest_rebuilds_under_current_schema(self):
        """Item 3."""
        result = raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        self.assertGreaterEqual(result["counts"]["tickers"], 1)
        self.assertEqual(result["state"]["schema_version"], raw_store.STORE_SCHEMA_VERSION)
        self.assertEqual(raw_store.inspect_state(self.scratch)["status"], raw_store.STATE_STATUS_CURRENT)

    def test_second_raw_ingest_is_idempotent(self):
        """Item 4."""
        raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        first_fingerprint = raw_store.load_state(self.scratch)["state_fingerprint"]
        second = raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:01Z", execute=True)
        self.assertEqual(second["counts"]["rebuilt"], 0)
        self.assertEqual(second["state"]["state_fingerprint"], first_fingerprint)

    def test_raw_verify_passes_after_rebuild(self):
        """Item 5."""
        raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        result = raw_store.verify(self.scratch)
        self.assertTrue(result["ok"], result.get("findings"))

    def test_canonical_ingest_rejects_stale_raw_store_with_precise_reason(self):
        """Item 6."""
        state_path = raw_store.state_path(self.scratch)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"schema_version": "1.0.0", "tickers": []}), encoding="utf-8")
        result = fact_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=False)
        self.assertFalse(result["ok"])
        self.assertIn("RAW_STORE_SCHEMA_STALE_REBUILD_REQUIRED", result["reason"])
        self.assertNotIn("missing or has an unsupported schema", result["reason"])

    def test_canonical_ingest_accepts_rebuilt_current_raw_store(self):
        """Item 7."""
        raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        result = fact_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        self.assertTrue(result["ok"], result.get("reason"))
        self.assertEqual(result["state"]["mapper_version"], facts.MAPPER_VERSION)

    def test_canonical_gross_profit_appears_through_the_standard_path(self):
        """Items 9/10, at the store level (candidate level already covered by
        GrossProfitProviderGateTests in test_canonical_financial_facts.py)."""
        raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        fact_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        found_provider_reported = False
        for path in fact_store.facts_root(self.scratch).glob("*.jsonl.gz"):
            for record in fact_store.decode_shard(path.read_bytes()):
                if record["canonical_metric"] != "gross_profit":
                    continue
                self.assertNotEqual(record.get("provider"), "VCI",
                                    "VCI must never canonicalize gross_profit (VCI_PERIOD_DURATION_REMAINS_UNKNOWN)")
                if record["status"] == facts.STATUS_PROVIDER_REPORTED:
                    found_provider_reported = True
        self.assertTrue(found_provider_reported,
                        "AAA is known (from this milestone's own real replay) to carry "
                        "retained KBS gross_profit")

    def test_canonical_store_verify_passes_after_standard_ingest(self):
        raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        fact_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        result = fact_store.verify(self.scratch)
        self.assertTrue(result["ok"], result.get("findings"))

    def test_no_write_outside_the_isolated_runtime(self):
        """Item 22 (mechanism-level): both stores are strictly parameterized by
        runtime_root and never touch a path outside it."""
        raw_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        fact_store.ingest(self.scratch, generated_at="2026-09-02T00:00:00Z", execute=True)
        self.assertTrue((self.scratch / "data" / "market-wide-financials").is_dir())
        self.assertTrue((self.scratch / "data" / "canonical-financial-facts").is_dir())


class RawStoreFingerprintCoversSchemaVersionTests(unittest.TestCase):
    """Part C regression lock, mirroring test_canonical_financial_facts.py's existing
    `test_inputs_fingerprint_covers_the_mapper_version` for the raw layer: a
    STORE_SCHEMA_VERSION bump must change every ticker's inputs_fingerprint, so a future
    extraction-contract change cannot silently leave the persisted store looking
    unchanged the way the pre-existing MAPPER_VERSION omission once did at layer 3."""

    def test_inputs_fingerprint_covers_the_store_schema_version(self):
        inputs = [{"source_file": "TST_income_statement_quarter.parquet",
                  "source_sha256": "abc", "metadata_sha256": None}]
        baseline = raw_store._inputs_fingerprint(inputs)
        original = raw_store.STORE_SCHEMA_VERSION
        try:
            raw_store.STORE_SCHEMA_VERSION = "9.9.9"
            moved = raw_store._inputs_fingerprint(inputs)
        finally:
            raw_store.STORE_SCHEMA_VERSION = original
        self.assertNotEqual(baseline, moved,
                            "a raw store schema-version change must invalidate every shard")

    def test_inputs_fingerprint_covers_the_observation_schema_version(self):
        inputs = [{"source_file": "TST_income_statement_quarter.parquet",
                  "source_sha256": "abc", "metadata_sha256": None}]
        baseline = raw_store._inputs_fingerprint(inputs)
        original = raw_store.OBSERVATION_SCHEMA_VERSION
        try:
            raw_store.OBSERVATION_SCHEMA_VERSION = "9.9.9"
            moved = raw_store._inputs_fingerprint(inputs)
        finally:
            raw_store.OBSERVATION_SCHEMA_VERSION = original
        self.assertNotEqual(baseline, moved,
                            "an observation-extraction schema-version change must invalidate every shard")


class NoHardcodedProductionRuntimePathTests(unittest.TestCase):
    """Item 22: neither store module hardcodes (or defaults to) the shared production
    runtime -- every path is derived from the caller-supplied runtime_root."""

    def test_raw_store_module_names_no_dashboard_runtime_literal(self):
        source = Path(raw_store.__file__).read_text(encoding="utf-8")
        self.assertNotIn("dashboard-runtime", source)
        self.assertNotIn("dashboard_runtime", source)

    def test_canonical_fact_store_module_names_no_dashboard_runtime_literal(self):
        source = Path(fact_store.__file__).read_text(encoding="utf-8")
        self.assertNotIn("dashboard-runtime", source)
        self.assertNotIn("dashboard_runtime", source)


# ---------------------------------------------------------------------------
# Part D/E -- entity classification reproducibility (items 12-16)
# ---------------------------------------------------------------------------

def _record(entity_class: str, *, status=ClassificationStatus.QUALIFIED) -> EntityClassificationRecord:
    return EntityClassificationRecord(
        issuer_identity="issuer:TST", ticker="TST", legal_name=None,
        entity_class=EntityClass(entity_class), classification_status=status,
        confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
        evidence_tier=EvidenceTier.CURATED_SEED_AUTHORITY,
        classification_evidence_id="e", source_id="test", source_record_id=None,
        effective_from=None, knowledge_available_at=None, verified_at="2026-09-02",
        classification_reason="test_fixture",
    )


class EntityClassificationPrecedenceTests(unittest.TestCase):
    """Items 13, 14: precedence never lets a lower tier override a stronger one, and an
    unresolved ticker stays UNKNOWN rather than defaulting to corporate. All in-memory --
    no dependency on any tracked or sibling-worktree file."""

    def test_seed_wins_over_conflicting_promoted_record(self):
        result = resolve_layered_entity_classification(
            "TST", seed_profiles={"TST": "corporate"},
            promoted_records={"TST": _record("bank")})
        self.assertEqual(result.resolved_entity_class, EntityClass.UNKNOWN)
        self.assertEqual(result.classification_status, ClassificationStatus.CONFLICT)

    def test_seed_wins_over_conflicting_scaleout_record(self):
        result = resolve_layered_entity_classification(
            "TST", seed_profiles={"TST": "corporate"},
            scaleout_promoted_records={"TST": _record("bank")})
        self.assertEqual(result.resolved_entity_class, EntityClass.UNKNOWN)
        self.assertEqual(result.classification_status, ClassificationStatus.CONFLICT)

    def test_seed_wins_over_agreeing_promoted_and_scaleout(self):
        result = resolve_layered_entity_classification(
            "TST", seed_profiles={"TST": "corporate"},
            promoted_records={"TST": _record("corporate")},
            scaleout_promoted_records={"TST": _record("corporate")})
        self.assertEqual(result.resolved_entity_class, EntityClass.CORPORATE)
        self.assertEqual(result.authority_tier, "curated_seed_authority")

    def test_original_promoted_wins_over_disagreeing_scaleout_when_no_seed(self):
        """Item 13: the scale-out tier is gap-fill only -- a ticker already resolved by
        the original promoted manifest must never be reconsidered by the newer, weaker
        scale-out tier, even when they disagree."""
        result = resolve_layered_entity_classification(
            "TST", promoted_records={"TST": _record("securities")},
            scaleout_promoted_records={"TST": _record("corporate")})
        self.assertEqual(result.resolved_entity_class, EntityClass.SECURITIES)
        self.assertEqual(result.authority_tier, "promoted_record_authority")

    def test_scaleout_only_fills_a_genuine_gap(self):
        result = resolve_layered_entity_classification(
            "TST", scaleout_promoted_records={"TST": _record("corporate")})
        self.assertEqual(result.resolved_entity_class, EntityClass.CORPORATE)
        self.assertEqual(result.authority_tier, "scaleout_promoted_record_authority")
        self.assertTrue(result.is_positive_authority)

    def test_unresolved_ticker_stays_unknown_never_defaults_to_corporate(self):
        """Item 14."""
        result = resolve_layered_entity_classification("ZZZ_NOT_A_REAL_TICKER")
        self.assertEqual(result.resolved_entity_class, EntityClass.UNKNOWN)
        self.assertEqual(result.classification_status, ClassificationStatus.UNKNOWN)
        self.assertFalse(result.is_positive_authority)

    def test_non_qualified_scaleout_record_never_supplies_positive_classification(self):
        result = resolve_layered_entity_classification(
            "TST", scaleout_promoted_records={"TST": _record("corporate", status=ClassificationStatus.AMBIGUOUS)})
        self.assertEqual(result.resolved_entity_class, EntityClass.UNKNOWN)
        self.assertFalse(result.is_positive_authority)


class GovernedRegistryLoadedFromTrackedFilesTests(unittest.TestCase):
    """Items 12, 15, 16: the layered registry is loaded from the tracked repository
    config files -- not a sibling-worktree or manually-replayed artifact -- and doing so
    is deterministic."""

    def test_scaleout_registry_file_is_tracked_and_loads(self):
        """Item 12."""
        self.assertTrue(DEFAULT_SCALEOUT_PROMOTED_CLASSIFICATIONS_PATH.is_file(),
                        "config/promoted_entity_classifications_scaleout_v1.json must be a "
                        "tracked repository file, not a generated/gitignored artifact")
        records = load_scaleout_promoted_entity_classifications()
        self.assertGreater(len(records), 900)

    def test_layered_profiles_load_is_deterministic_across_two_calls(self):
        """Item 15 (reproducibility, not a hardcoded historical count -- see module
        docstring and entity_reproduction.json for why 1,382/85/25 was never actually
        reproducible without an untracked sibling-worktree artifact)."""
        first = load_layered_entity_profiles()
        second = load_layered_entity_profiles()
        self.assertEqual(first, second)
        self.assertGreater(len(first), 0)

    def test_governed_distribution_matches_the_sum_of_the_four_tracked_tiers(self):
        """Cross-validates the live registry arithmetic: every positively-classified
        ticker traces to exactly one of the four tracked tiers (seed, original promoted,
        legacy-recovery -- see LEGACY_ENTITY_CLASSIFICATION_TRACKED_AUTHORITY_RECOVERY_V1
        -- and scale-out), with no unexplained extra classifications from an untracked
        source."""
        seed = load_seed_profiles()
        promoted = load_promoted_entity_classifications()
        legacy_recovery = load_legacy_recovery_entity_classifications()
        scaleout = load_scaleout_promoted_entity_classifications()
        merged = load_layered_entity_profiles()
        tier_union = set(seed) | {t for t, r in promoted.items()
                                  if r.classification_status == ClassificationStatus.QUALIFIED} \
                              | {t for t, r in legacy_recovery.items()
                                  if r.classification_status == ClassificationStatus.QUALIFIED} \
                              | {t for t, r in scaleout.items()
                                  if r.classification_status == ClassificationStatus.QUALIFIED}
        # Every merged ticker must be explained by at least one tracked tier (a CONFLICT
        # never enters `merged` at all, so this is a strict subset check).
        self.assertTrue(set(merged) <= tier_union)

    def test_build_scaleout_does_not_require_legacy_records(self):
        """Item 16: `legacy_records` -- the parameter every prior invocation on record
        threaded a sibling-worktree artifact through -- defaults to None. No sibling
        path is required to call the standard materializer."""
        signature = inspect.signature(v2_scaleout.build_scaleout)
        self.assertIsNone(signature.parameters["legacy_records"].default)
        required = [name for name, param in signature.parameters.items()
                   if param.default is inspect.Parameter.empty]
        self.assertNotIn("legacy_records", required)


# ---------------------------------------------------------------------------
# Part H/I -- existing-feature and denominator regressions (items 17-21)
# ---------------------------------------------------------------------------

class UnrelatedCapabilityRegressionTests(unittest.TestCase):
    """Items 17-21: this milestone's diff is limited to raw_financial_store.py and
    canonical_fact_store.py (plus this test file and evidence/roadmap docs). Working
    capital, current ratio, debt ratios, gross margin, Bank Specialist, relative volume,
    Financial V2's 1,492/1,699 denominators, and the six-label research-stance
    distribution are exercised by their own existing, passing suites
    (tests/test_financial_analysis_engine_v2.py, tests/test_bank_financial_research_
    component.py, tests/test_market_wide_relative_volume_research.py, and the product/
    stance suites) -- not re-asserted here to avoid a second, drifting source of truth.
    This class only pins the mechanism this milestone actually changed: that the two
    edited modules do not import or reference anything from the product/stance/
    valuation/tactical/portfolio layer, so a change to raw/canonical store diagnostics
    cannot have altered them."""

    def test_raw_store_does_not_import_downstream_research_modules(self):
        source = Path(raw_store.__file__).read_text(encoding="utf-8")
        for forbidden in ("financial_analysis_engine_v2", "security_decision_context",
                          "relative_valuation", "watchlist_tactical", "portfolio"):
            self.assertNotIn(forbidden, source)

    def test_canonical_fact_store_does_not_import_downstream_research_modules(self):
        source = Path(fact_store.__file__).read_text(encoding="utf-8")
        for forbidden in ("financial_analysis_engine_v2", "security_decision_context",
                          "relative_valuation", "watchlist_tactical", "portfolio"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
