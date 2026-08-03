# ==========================================================================
# Tests for the market-wide canonical financial normalization pillar:
#   raw_financial_observations.py  -- pure extraction, no allowlist
#   raw_financial_store.py         -- incremental, byte-deterministic shards
#   financial_entity_applicability -- archetype + EBITDA/EV-EBITDA applicability
#   market_wide_financial_coverage -- deterministic coverage statistics
#
# Synthetic in-memory frames and a tmp runtime root for everything structural.
# The two production-data assertions at the bottom skip when the runtime store
# has not been generated.
# Run: `python -m unittest tests.test_market_wide_financial_ingest`
# ==========================================================================

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import financial_entity_applicability as applicability  # noqa: E402
import market_wide_financial_coverage as coverage  # noqa: E402
import raw_financial_observations as observations  # noqa: E402
import raw_financial_store as store  # noqa: E402
from _runtime_root import runtime_path  # noqa: E402


def _frame(rows, columns=None):
    import pandas as pd
    return pd.DataFrame(rows, columns=columns)


def _income_frame():
    """Mirrors the real HPG income-statement shape: repeated `revenue`, duplicate period."""
    return _frame([
        {"ticker": "HPG", "report_type": "income_statement", "source": "VCI",
         "scraped_at": "2026-07-30T00:00:00", "item": "Doanh thu bán hàng",
         "item_id": "revenue", "2026-Q1": 100.0, "2025-Q4_1": 90.0, "2025-Q4": 95.0},
        {"ticker": "HPG", "report_type": "income_statement", "source": "VCI",
         "scraped_at": "2026-07-30T00:00:00", "item": "Doanh thu thuần",
         "item_id": "revenue", "2026-Q1": 98.0, "2025-Q4_1": 88.0, "2025-Q4": 93.0},
        {"ticker": "HPG", "report_type": "income_statement", "source": "VCI",
         "scraped_at": "2026-07-30T00:00:00", "item": "Một chỉ tiêu lạ",
         "item_id": "an_item_no_allowlist_knows", "2026-Q1": 7.0,
         "2025-Q4_1": None, "2025-Q4": None},
        {"ticker": "HPG", "report_type": "income_statement", "source": "VCI",
         "scraped_at": "2026-07-30T00:00:00", "item": "Rỗng",
         "item_id": "always_empty", "2026-Q1": None, "2025-Q4_1": None, "2025-Q4": None},
    ])


def _extract(frame=None, **overrides):
    kwargs = {"ticker": "HPG", "statement_family": "income_statement",
              "reporting_frequency": "quarter", "source_file": "HPG_income_statement_quarter.parquet",
              "source_sha256": "a" * 64}
    kwargs.update(overrides)
    return observations.extract_payload(frame if frame is not None else _income_frame(), **kwargs)


class PayloadIdentityTests(unittest.TestCase):
    def test_payload_name_parses_ticker_family_and_frequency(self):
        self.assertEqual(
            observations.parse_payload_name("HPG_balance_sheet_quarter"),
            {"ticker": "HPG", "statement_family": "balance_sheet", "reporting_frequency": "quarter"})

    def test_payload_name_without_frequency_raises_rather_than_being_dropped(self):
        # `BIO_balance_sheet.parquet` really exists in the runtime; it must surface as an
        # explicit accounting failure, never be silently skipped.
        with self.assertRaises(observations.PayloadNameError):
            observations.parse_payload_name("BIO_balance_sheet")

    def test_period_columns_normalize_across_writer_variants(self):
        self.assertEqual(observations.normalize_period_column("2026-Q1"),
                         {"reporting_period": "2026-Q1", "period_type": "quarterly",
                          "variant_suffix": None})
        self.assertEqual(observations.normalize_period_column("2025-Q4_1")["reporting_period"],
                         "2025-Q4")
        self.assertEqual(observations.normalize_period_column("2025Q4")["reporting_period"],
                         "2025-Q4")
        self.assertEqual(observations.normalize_period_column("2024"),
                         {"reporting_period": "2024", "period_type": "annual",
                          "variant_suffix": None})
        self.assertEqual(observations.normalize_period_column("2024_1")["reporting_period"], "2024")

    def test_non_period_columns_are_not_periods(self):
        for column in ("ticker", "item", "item_id", "source", "scraped_at", "item_en"):
            self.assertIsNone(observations.normalize_period_column(column))


class ExtractionTests(unittest.TestCase):
    def test_retains_items_no_allowlist_would_know(self):
        extracted = _extract()
        retained = {row["raw_item_id"] for row in extracted["observations"]}
        self.assertIn("an_item_no_allowlist_knows", retained)
        self.assertEqual(extracted["retention_policy"], "all_raw_items")

    def test_repeated_item_id_is_flagged_and_ordinally_disambiguated(self):
        extracted = _extract()
        revenue = [row for row in extracted["observations"]
                   if row["raw_item_id"] == "revenue" and row["reporting_period"] == "2026-Q1"]
        self.assertEqual(len(revenue), 2)
        self.assertEqual(sorted(row["item_id_occurrence"] for row in revenue), [1, 2])
        self.assertNotEqual(revenue[0]["row_ordinal"], revenue[1]["row_ordinal"])
        for row in revenue:
            self.assertIn("ambiguous_raw_item_id", row["warnings"])
        self.assertEqual(extracted["repeated_raw_item_ids"], ["revenue"])

    def test_unrepeated_item_id_is_not_flagged_ambiguous(self):
        row = next(row for row in _extract()["observations"]
                   if row["raw_item_id"] == "an_item_no_allowlist_knows")
        self.assertNotIn("ambiguous_raw_item_id", row["warnings"])

    def test_duplicate_period_column_is_kept_separately_never_collapsed(self):
        extracted = _extract()
        q4 = [row for row in extracted["observations"] if row["reporting_period"] == "2025-Q4"]
        self.assertEqual(sorted({row["period_variant_index"] for row in q4}), [0, 1])
        variant = [row for row in q4 if row["period_variant_index"] == 1]
        self.assertTrue(variant)
        for row in variant:
            self.assertIn("duplicate_period_column", row["warnings"])
            self.assertEqual(row["period_column"], "2025-Q4_1")
        self.assertEqual(extracted["duplicate_period_columns"], ["2025-Q4"])

    def test_primary_period_column_carries_no_duplicate_warning(self):
        primary = [row for row in _extract()["observations"]
                   if row["reporting_period"] == "2026-Q1"]
        self.assertTrue(primary)
        for row in primary:
            self.assertNotIn("duplicate_period_column", row["warnings"])

    def test_missing_cells_produce_no_observation_and_empty_rows_are_accounted(self):
        extracted = _extract()
        self.assertEqual([entry["raw_item_id"] for entry in extracted["rows_without_values"]],
                         ["always_empty"])
        self.assertEqual(extracted["reconciliation"]["input_rows"], 4)
        self.assertEqual(extracted["reconciliation"]["rows_without_values"], 1)
        self.assertTrue(extracted["reconciliation"]["rows_fully_accounted"])
        self.assertTrue(extracted["reconciliation"]["columns_fully_accounted"])
        self.assertTrue(extracted["reconciliation"]["observation_ids_unique"])

    def test_scope_currency_and_scale_stay_unknown_and_nothing_is_qualified(self):
        for row in _extract()["observations"]:
            self.assertEqual(row["statement_scope"], "unknown")
            self.assertIsNone(row["raw_currency"])
            self.assertIsNone(row["raw_scale"])
            self.assertEqual(row["qualification_state"], "retained_raw")
            self.assertIn("statement_scope_unknown", row["warnings"])
            self.assertIn("currency_and_scale_unknown", row["warnings"])

    def test_english_label_absence_is_recorded_not_invented(self):
        row = _extract()["observations"][0]
        self.assertIsNone(row["raw_label_en"])
        self.assertIn("raw_label_en_absent", row["warnings"])

    def test_extraction_is_deterministic_and_value_sensitive(self):
        first = _extract()["observations"]
        second = _extract()["observations"]
        self.assertEqual([row["observation_id"] for row in first],
                         [row["observation_id"] for row in second])

        changed = _income_frame()
        changed.loc[0, "2026-Q1"] = 101.0
        moved = _extract(changed)["observations"]
        by_identity = {row["identity_key"]: row["observation_id"] for row in first}
        differing = [row for row in moved
                     if by_identity.get(row["identity_key"]) not in (None, row["observation_id"])]
        self.assertEqual(len(differing), 1)
        # the identity is stable across a value revision; only the observation id moves
        self.assertIn(differing[0]["identity_key"], by_identity)

    def test_non_finite_and_non_numeric_cells_are_reported_not_stored(self):
        frame = _frame([
            {"ticker": "X", "report_type": "income_statement", "source": "KBS",
             "scraped_at": "t", "item": "a", "item_id": "x", "2025-Q4": float("inf")},
            {"ticker": "X", "report_type": "income_statement", "source": "KBS",
             "scraped_at": "t", "item": "b", "item_id": "y", "2025-Q4": "not-a-number"},
        ])
        extracted = _extract(frame, ticker="X")
        self.assertEqual(extracted["observations"], [])
        self.assertEqual({entry["reason"] for entry in extracted["malformed_values"]},
                         {"value_not_finite", "value_not_numeric"})


class ShardTests(unittest.TestCase):
    def test_shard_bytes_are_deterministic_and_clock_independent(self):
        rows = _extract()["observations"]
        self.assertEqual(store.encode_shard(rows), store.encode_shard(rows))
        # mtime=0 is what makes the gzip container itself reproducible
        self.assertEqual(gzip.decompress(store.encode_shard(rows)).decode("utf-8"),
                         observations.observation_lines(rows))

    def test_shard_roundtrips(self):
        rows = _extract()["observations"]
        self.assertEqual(store.decode_shard(store.encode_shard(rows)), rows)


class IngestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "data_bctc").mkdir(parents=True)
        _income_frame().to_parquet(
            self.root / "data_bctc" / "HPG_income_statement_quarter.parquet", index=False)
        self.addCleanup(self._tmp.cleanup)

    def _ingest(self, **kwargs):
        return store.ingest(self.root, generated_at="2026-08-03T00:00:00+00:00", **kwargs)

    def test_dry_run_writes_nothing_but_computes_the_full_plan(self):
        result = self._ingest(execute=False)
        self.assertEqual(result["counts"]["rebuilt"], 1)
        self.assertFalse(store.state_path(self.root).exists())
        self.assertFalse(store.shard_path(self.root, "HPG").exists())

    def test_second_run_over_unchanged_inputs_rebuilds_nothing(self):
        first = self._ingest(execute=True)
        self.assertEqual(first["counts"]["rebuilt"], 1)
        second = self._ingest(execute=True)
        self.assertEqual(second["counts"]["rebuilt"], 0)
        self.assertEqual(second["counts"]["unchanged"], 1)
        self.assertEqual(first["state"]["state_fingerprint"],
                         second["state"]["state_fingerprint"])

    def test_state_fingerprint_excludes_generated_at(self):
        first = store.ingest(self.root, generated_at="2026-08-03T00:00:00+00:00", execute=True)
        second = store.ingest(self.root, generated_at="2027-01-01T00:00:00+00:00", execute=True)
        self.assertEqual(first["state"]["state_fingerprint"],
                         second["state"]["state_fingerprint"])

    def test_changed_payload_triggers_exactly_one_rebuild(self):
        self._ingest(execute=True)
        changed = _income_frame()
        changed.loc[0, "2026-Q1"] = 123.0
        changed.to_parquet(self.root / "data_bctc" / "HPG_income_statement_quarter.parquet",
                           index=False)
        result = self._ingest(execute=True)
        self.assertEqual(result["rebuilt"], ["HPG"])

    def test_a_change_to_the_extraction_schema_invalidates_existing_shards(self):
        self._ingest(execute=True)
        self.assertEqual(self._ingest(execute=True)["counts"]["rebuilt"], 0)
        with unittest.mock.patch.object(store, "OBSERVATION_SCHEMA_VERSION", "9.9.9"):
            self.assertEqual(self._ingest(execute=True)["rebuilt"], ["HPG"])

    def test_corrupted_shard_bytes_are_rebuilt_not_trusted(self):
        self._ingest(execute=True)
        store.shard_path(self.root, "HPG").write_bytes(b"corrupted")
        result = self._ingest(execute=True)
        self.assertEqual(result["rebuilt"], ["HPG"])

    def test_verify_reports_a_missing_shard(self):
        self._ingest(execute=True)
        store.shard_path(self.root, "HPG").unlink()
        result = store.verify(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual([finding["finding"] for finding in result["findings"]],
                         ["shard_missing"])

    def test_verify_passes_on_a_freshly_written_store(self):
        self._ingest(execute=True)
        self.assertTrue(store.verify(self.root)["ok"])

    def test_unparseable_payload_name_is_reported_never_dropped(self):
        _income_frame().to_parquet(self.root / "data_bctc" / "BIO_balance_sheet.parquet",
                                   index=False)
        result = self._ingest(execute=False)
        self.assertEqual([entry["source_file"] for entry in result["state"]["unparsed_payloads"]],
                         ["BIO_balance_sheet.parquet"])

    def test_orphaned_shard_is_reported_never_deleted(self):
        self._ingest(execute=True)
        orphan = store.shard_path(self.root, "ZZZ")
        orphan.write_bytes(store.encode_shard([]))
        result = self._ingest(execute=True)
        self.assertEqual(result["orphaned_shards"], ["ZZZ"])
        self.assertTrue(orphan.exists())


class IncomeStatementTaxonomyTests(unittest.TestCase):
    def test_credit_institution_markers_are_recognised(self):
        result = applicability.classify_income_statement(
            ["net_interest_income", "provision_for_credit_losses", "some_other_line"])
        self.assertEqual(result["template_family"], "credit_institution")

    def test_insurance_markers_resolve_what_the_balance_sheet_cannot(self):
        result = applicability.classify_income_statement(
            applicability.INSURANCE_INCOME_MARKERS)
        self.assertEqual(result["template_family"], "insurance")

    def test_a_corporate_income_statement_is_never_named_corporate(self):
        result = applicability.classify_income_statement(
            ["revenue", "cost_of_goods_sold", "gross_profit", "profit_before_tax"])
        self.assertIsNone(result["template_family"])

    def test_markers_of_two_templates_conflict_rather_than_picking_one(self):
        result = applicability.classify_income_statement(
            ["net_interest_income", "revenue_from_securities_custody_services"])
        self.assertEqual(result["template_family"], "financial_specialized_conflicted")


class ArchetypeTests(unittest.TestCase):
    def test_manual_profile_outranks_generated_evidence(self):
        resolved = applicability.resolve_archetype(
            "VCB", manual_entity_type="bank", balance_sheet_taxonomy="corporate_vas")
        self.assertEqual(resolved["issuer_entity_type"], "bank")
        self.assertEqual(resolved["authority"], "manual_profile")

    def test_corporate_template_never_grants_a_corporate_archetype(self):
        resolved = applicability.resolve_archetype("AAA", balance_sheet_taxonomy="corporate_vas")
        self.assertIsNone(resolved["issuer_entity_type"])
        self.assertIsNone(resolved["template_family"])
        self.assertEqual(resolved["authority"], "unknown")

    def test_no_evidence_never_defaults_to_corporate(self):
        resolved = applicability.resolve_archetype("ZZZ")
        self.assertIsNone(resolved["issuer_entity_type"])
        self.assertEqual(resolved["evidence_agreement"], "no_generated_evidence")

    def test_income_statement_disambiguates_an_ambiguous_balance_sheet(self):
        resolved = applicability.resolve_archetype(
            "BVH", balance_sheet_taxonomy="financial_specialized_ambiguous",
            income_statement_family="insurance")
        self.assertEqual(resolved["template_family"], "insurance")
        self.assertEqual(resolved["evidence_agreement"], "income_statement_disambiguates")

    def test_disagreeing_families_still_withhold_the_corporate_model(self):
        resolved = applicability.resolve_archetype(
            "XXX", balance_sheet_taxonomy="credit_institution",
            income_statement_family="securities_company")
        self.assertEqual(resolved["evidence_agreement"], "conflicting")
        self.assertEqual(resolved["template_family"], "financial_specialized_conflicted")
        verdict = applicability.metric_applicability(resolved, "ebitda")
        self.assertEqual(verdict["status"], "not_applicable")


class ApplicabilityTests(unittest.TestCase):
    def _status(self, metric="ebitda", **kwargs):
        resolved = applicability.resolve_archetype("T", **kwargs)
        return applicability.metric_applicability(resolved, metric)

    def test_manual_financial_filer_is_not_applicable_for_both_metrics(self):
        for entity_type in sorted(applicability.FINANCIAL_ENTITY_TYPES):
            for metric in applicability.CORPORATE_ONLY_METRICS:
                verdict = self._status(metric, manual_entity_type=entity_type)
                self.assertEqual(verdict["status"], "not_applicable", entity_type)

    def test_generated_financial_evidence_is_not_applicable_without_a_manual_profile(self):
        verdict = self._status(balance_sheet_taxonomy="credit_institution")
        self.assertEqual(verdict["status"], "not_applicable")
        self.assertEqual(verdict["authority"], "generated_statement_evidence")
        self.assertIn("net_interest_margin", verdict["substitute_metrics"])

    def test_ambiguous_specialized_evidence_still_withholds(self):
        verdict = self._status(balance_sheet_taxonomy="financial_specialized_ambiguous")
        self.assertEqual(verdict["status"], "not_applicable")

    def test_manual_corporate_is_applicable_subject_to_inputs(self):
        verdict = self._status(manual_entity_type="corporate")
        self.assertEqual(verdict["status"], "applicable_subject_to_inputs")

    def test_unresolved_archetype_is_insufficient_evidence_never_applicable(self):
        verdict = self._status(balance_sheet_taxonomy="corporate_vas")
        self.assertEqual(verdict["status"], "insufficient_evidence")

    def test_metrics_outside_the_corporate_earnings_model_are_unrestricted(self):
        verdict = self._status("total_assets", manual_entity_type="bank")
        self.assertEqual(verdict["status"], "applicable_subject_to_inputs")

    def test_not_applicable_always_names_substitutes(self):
        verdict = self._status(balance_sheet_taxonomy="securities_company")
        self.assertTrue(verdict["substitute_metrics"])


class CoverageTests(unittest.TestCase):
    def test_candidate_config_covers_both_provider_dialects(self):
        candidates = coverage.load_candidates(ROOT / coverage.CANDIDATES_RELATIVE)
        self.assertIn("depreciation_amortization", candidates)
        dialects = {entry["dialect"] for entry in candidates["depreciation_amortization"]}
        self.assertEqual(dialects, {"vci_a", "kbs_b"})
        ocf = {entry["dialect"] for entry in candidates["operating_cash_flow"]}
        self.assertEqual(ocf, {"vci_a", "kbs_b"})

    def test_every_ebitda_input_metric_has_candidates(self):
        candidates = coverage.load_candidates(ROOT / coverage.CANDIDATES_RELATIVE)
        for metric in coverage.EBITDA_INPUT_METRICS:
            self.assertIn(metric, candidates)

    def test_coverage_csv_header_is_stable(self):
        body = coverage.coverage_csv({"records": []})
        self.assertEqual(body.splitlines()[0], ",".join(coverage.CSV_COLUMNS))


class ProductionStoreTests(unittest.TestCase):
    """Assertions about the generated runtime store. Skipped when it is absent."""

    def _report(self):
        path = runtime_path("data", "market-wide-financials", "coverage_report.json")
        if not path.exists():
            raise unittest.SkipTest("market-wide store not generated in this runtime root")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_specialized_financial_filers_are_not_applicable_not_merely_unavailable(self):
        report = self._report()
        counts = report["metric_applicability"]["ebitda"]
        # The 2026-08-03 audit found only the 7 manually-profiled tickers excluded while the
        # generated taxonomy separately flagged ~76 more. Anything back near 7 is a regression.
        self.assertGreater(counts.get("not_applicable", 0), 50)
        self.assertEqual(report["metric_applicability"]["ebitda"],
                         report["metric_applicability"]["ev_ebitda"])

    def test_no_ticker_is_silently_granted_a_corporate_archetype(self):
        report = self._report()
        by_authority = report["archetype_coverage"]["by_authority"]
        manual = report["archetype_coverage"]["by_issuer_entity_type"]
        self.assertEqual(sum(count for key, count in manual.items() if key != "null"),
                         by_authority.get("manual_profile", 0))

    def test_every_active_universe_ticker_is_accounted_for(self):
        reconciliation = self._report()["reconciliation"]
        self.assertEqual(
            reconciliation["active_universe_tickers"],
            reconciliation["in_store_and_active_universe"]
            + reconciliation["in_active_universe_without_store_shard"])


if __name__ == "__main__":
    unittest.main()
