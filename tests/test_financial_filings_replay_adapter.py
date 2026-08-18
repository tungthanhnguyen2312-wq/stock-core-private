"""Financial-filings replay-adapter tests, including the real vertical-slice
proof: replaying the actual governed HPG/VNM/VCB corpus must preserve
source SHA-256 exactly. Read-only against the source; no network call."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from acquisition_landing_checkpoint import process_batch
from acquisition_landing_contract import AcquisitionOutcome
from acquisition_landing_isolation import default_protected_roots
from financial_filings_replay_adapter import (
    DEFAULT_TICKERS,
    default_governed_evidence_root,
    iter_replay_items,
    load_governed_records,
    select_records,
    utc_now_iso,
)

REAL_WORKSPACE_ROOT = Path(r"C:\Projects\StockLookup")
REAL_GOVERNED_EVIDENCE_ROOT = default_governed_evidence_root(REAL_WORKSPACE_ROOT)


def _skip_if_corpus_missing():
    manifest = REAL_GOVERNED_EVIDENCE_ROOT / "official_document_acquisition_manifest.json"
    if not manifest.exists():
        raise unittest.SkipTest(f"real governed evidence corpus not present at {manifest}")


class SelectRecordsTests(unittest.TestCase):
    def test_select_records_filters_by_ticker_case_insensitively(self):
        records = [{"ticker": "HPG"}, {"ticker": "vnm"}, {"ticker": "SSI"}]
        selected = select_records(records, tickers=("hpg", "VNM"))
        self.assertEqual({r["ticker"] for r in selected}, {"HPG", "vnm"})


class RealGovernedCorpusReplayTests(unittest.TestCase):
    """Uses the real, already-retained governed evidence corpus - no
    network call, read-only against the source."""

    def setUp(self):
        _skip_if_corpus_missing()
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name)
        self.landing_root = self.workspace_root / "data-landing" / "official-financial-filings-v1"
        self.protected_roots = default_protected_roots(self.workspace_root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_tickers_are_hpg_vnm_vcb(self):
        self.assertEqual(DEFAULT_TICKERS, ("HPG", "VNM", "VCB"))

    def test_real_governed_records_found_for_default_tickers(self):
        records = select_records(load_governed_records(REAL_GOVERNED_EVIDENCE_ROOT), DEFAULT_TICKERS)
        self.assertEqual(len(records), 5, "expected 3 HPG + 1 VNM + 1 VCB records in the real governed corpus")

    def test_replay_preserves_source_sha256_exactly(self):
        records = select_records(load_governed_records(REAL_GOVERNED_EVIDENCE_ROOT), DEFAULT_TICKERS)
        expected_hashes = {r["canonical_url"]: r["sha256"] for r in records}

        items = list(iter_replay_items(REAL_GOVERNED_EVIDENCE_ROOT, DEFAULT_TICKERS))
        report = process_batch(
            self.landing_root,
            items,
            run_id="vertical-slice-1",
            domain="official-financial-filings-v1",
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            extra_protected_paths=(REAL_GOVERNED_EVIDENCE_ROOT,),
            observed_at_fn=utc_now_iso,
        )

        self.assertEqual(report.attempted, 5)
        self.assertEqual(report.succeeded, 5)
        self.assertEqual(report.quarantined, 0)
        self.assertEqual(report.failed_permanent, 0)
        self.assertEqual(report.failed_retryable, 0)

        for record in report.records:
            self.assertEqual(record["outcome"], AcquisitionOutcome.ACQUIRED.value)
            expected = expected_hashes[record["source_locator"]]
            self.assertEqual(record["sha256"], expected, f"sha256 mismatch for {record['source_locator']}")

            retained_path = self.landing_root / record["storage_locator"]
            actual_bytes_hash = hashlib.sha256(retained_path.read_bytes()).hexdigest()
            self.assertEqual(actual_bytes_hash, expected)

    def test_source_governed_evidence_root_is_never_modified(self):
        manifest_path = REAL_GOVERNED_EVIDENCE_ROOT / "official_document_acquisition_manifest.json"
        before = manifest_path.read_bytes()

        items = list(iter_replay_items(REAL_GOVERNED_EVIDENCE_ROOT, DEFAULT_TICKERS))
        process_batch(
            self.landing_root,
            items,
            run_id="vertical-slice-read-only-check",
            domain="official-financial-filings-v1",
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            extra_protected_paths=(REAL_GOVERNED_EVIDENCE_ROOT,),
            observed_at_fn=utc_now_iso,
        )

        after = manifest_path.read_bytes()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
