"""Generated statement-taxonomy sidecar: determinism, reconciliation and authority order."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import statement_taxonomy_sidecar as sidecar  # noqa: E402

CORPORATE_ITEMS = ["current_assets", "current_liabilities", "short_term_borrowings", "inventories"]
BANK_ITEMS = ["deposits_from_customers", "balances_with_the_sbv",
              "placements_with_and_loans_to_other_credit_institutions"]
BROKER_ITEMS = ["customerss_deposits_for_securities_trading", "collateral_financial_assets"]
AMBIGUOUS_ITEMS = ["loans_and_advances_to_customers"]


def _payload(root: Path, ticker: str, items: list[str], periods=("2025-Q3", "2025-Q4"),
             source="VCI", populate=True) -> Path:
    data = {"item_id": items, "source": [source] * len(items)}
    for period in periods:
        data[period] = [1.0 if populate else None] * len(items)
    frame = pd.DataFrame(data)
    directory = root / "data_bctc"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ticker}_balance_sheet_quarter.parquet"
    frame.to_parquet(path)
    return path


class SidecarBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        _payload(self.root, "AAA", CORPORATE_ITEMS)
        _payload(self.root, "BBB", BANK_ITEMS)
        _payload(self.root, "CCC", BROKER_ITEMS)
        _payload(self.root, "DDD", AMBIGUOUS_ITEMS)
        _payload(self.root, "EEE", ["something_unmapped"])
        # No reporting-period columns at all: the exact BIO condition in production.
        frame = pd.DataFrame({"item_id": CORPORATE_ITEMS, "source": ["VCI"] * 4})
        frame.to_parquet(self.root / "data_bctc" / "ZZZ_balance_sheet_quarter.parquet")

    def _build(self, **kwargs):
        params = {"generated_at": "2026-08-03T00:00:00+00:00", "session_identity": "2026-07-30"}
        params.update(kwargs)
        return sidecar.build_sidecar(self.root, **params)

    def test_every_input_is_reconciled_exactly_once(self):
        payload = self._build()
        reconciliation = payload["reconciliation"]
        self.assertEqual(reconciliation["input_payloads"], 6)
        self.assertEqual(reconciliation["classified_records"], 5)
        self.assertEqual(reconciliation["omitted_records"], 1)
        self.assertTrue(reconciliation["inputs_fully_accounted"])
        self.assertTrue(reconciliation["taxonomy_counts_sum_to_records"])

    def test_omission_carries_an_explicit_reason(self):
        omitted = self._build()["omitted"]
        self.assertEqual([row["ticker"] for row in omitted], ["ZZZ"])
        self.assertEqual(omitted[0]["omission_reason"], "payload_has_no_reporting_period_columns")
        self.assertTrue(omitted[0]["source_sha256"])

    def test_taxonomies_are_evidence_based_and_unknown_never_becomes_corporate(self):
        index = sidecar.taxonomy_index(self._build())
        self.assertEqual(index["AAA"], "corporate_vas")
        self.assertEqual(index["BBB"], "credit_institution")
        self.assertEqual(index["CCC"], "securities_company")
        self.assertEqual(index["DDD"], "financial_specialized_ambiguous")
        self.assertEqual(index["EEE"], "unknown")

    def test_records_carry_the_full_required_provenance(self):
        record = sidecar.sidecar_provenance(self._build(), "BBB")
        for key in ("record_id", "ticker", "statement_taxonomy", "source", "source_file",
                    "source_sha256", "statement_scope", "classifier_version",
                    "periods_evaluated", "first_observed_period", "last_observed_period",
                    "matched_positive_markers", "matched_exclusion_markers",
                    "ambiguity_status", "abstention_reason", "authority_level"):
            self.assertIn(key, record)
        self.assertEqual(record["authority_level"], "generated_evidence")
        self.assertNotIn("entity_type", record)
        self.assertNotIn("issuer_entity_type", record)
        self.assertEqual(record["first_observed_period"], "2025-Q3")
        self.assertEqual(record["last_observed_period"], "2025-Q4")
        self.assertTrue(record["matched_exclusion_markers"]["credit_institution_exclusive"])

    def test_rebuild_on_unchanged_inputs_is_byte_stable(self):
        first = self._build()
        second = self._build(generated_at="2099-01-01T00:00:00+00:00", session_identity="2099-01-01")
        self.assertEqual(first["records_fingerprint"], second["records_fingerprint"])
        self.assertEqual(first["input_fingerprint"], second["input_fingerprint"])
        self.assertEqual(json.dumps(first["records"], sort_keys=True),
                         json.dumps(second["records"], sort_keys=True))

    def test_changed_input_changes_both_fingerprint_and_record_identity(self):
        first = self._build()
        before = sidecar.sidecar_provenance(first, "AAA")["record_id"]
        _payload(self.root, "AAA", CORPORATE_ITEMS, periods=("2025-Q3", "2025-Q4", "2026-Q1"))
        second = self._build()
        self.assertNotEqual(first["input_fingerprint"], second["input_fingerprint"])
        self.assertNotEqual(first["records_fingerprint"], second["records_fingerprint"])
        self.assertNotEqual(before, sidecar.sidecar_provenance(second, "AAA")["record_id"])

    def test_load_fails_closed_on_absent_or_wrong_schema(self):
        self.assertIsNone(sidecar.load_sidecar(self.root))
        sidecar.sidecar_path(self.root).write_text(json.dumps({"schema_version": "0.9.0", "records": []}),
                                                    encoding="utf-8")
        self.assertIsNone(sidecar.load_sidecar(self.root))
        sidecar.sidecar_path(self.root).write_text("{not json", encoding="utf-8")
        self.assertIsNone(sidecar.load_sidecar(self.root))

    def test_resolve_taxonomy_of_an_unknown_ticker_is_none_not_a_default(self):
        self.assertIsNone(sidecar.resolve_taxonomy(self._build(), "NOPE"))
        self.assertIsNone(sidecar.resolve_taxonomy(None, "AAA"))


class AuthorityOrderTests(unittest.TestCase):
    def test_manual_profile_always_overrides_generated_taxonomy(self):
        resolved = sidecar.resolve_entity_authority("corporate", "credit_institution")
        self.assertEqual(resolved["entity_type"], "corporate")
        self.assertEqual(resolved["authority"], "manual_profile")

    def test_generated_financial_taxonomy_withholds_without_naming_an_entity_type(self):
        for taxonomy in ("credit_institution", "securities_company", "financial_specialized_ambiguous"):
            resolved = sidecar.resolve_entity_authority(None, taxonomy)
            self.assertIsNone(resolved["entity_type"])
            self.assertEqual(resolved["authority"], "generated_taxonomy")

    def test_corporate_template_never_resolves_an_entity_type(self):
        resolved = sidecar.resolve_entity_authority(None, "corporate_vas")
        self.assertIsNone(resolved["entity_type"])
        self.assertEqual(resolved["authority"], "unknown")

    def test_unknown_taxonomy_never_defaults_to_corporate(self):
        for taxonomy in (None, "", "unknown", "unresolved"):
            resolved = sidecar.resolve_entity_authority(None, taxonomy)
            self.assertIsNone(resolved["entity_type"])
            self.assertEqual(resolved["authority"], "unknown")

    def test_blank_manual_profile_is_not_an_authority(self):
        for manual in ("", "  ", None, "unknown"):
            self.assertNotEqual(sidecar.resolve_entity_authority(manual, "corporate_vas")["authority"],
                                "manual_profile")


if __name__ == "__main__":
    unittest.main()
