"""Retention-layer tests: dedup, new-version detection, hash verification,
distinct failure classes, quarantine, and the qualification-state boundary."""

import tempfile
import unittest
from pathlib import Path

from acquisition_landing_contract import (
    QUALIFICATION_STATE_UNKNOWN,
    AcquisitionOutcome,
    AcquisitionSpec,
    FetchError,
    HashConflictError,
    ProtectedRootWriteError,
)
from acquisition_landing_isolation import default_protected_roots
from acquisition_landing_retention import blob_path, blobs_dir, retain

VALID_PDF = b"%PDF-1.4\n%fake-fixture-pdf-body\n%%EOF"


def make_spec(locator="https://issuer.invalid/report.pdf"):
    return AcquisitionSpec(
        domain="official-financial-filings-v1",
        source_locator=locator,
        source_authority_class="issuer_ir",
        issuer_identity="TEST",
        document_type="annual_report",
    )


class RetentionTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name)
        self.landing_root = self.workspace_root / "data-landing" / "official-financial-filings-v1"
        self.protected_roots = default_protected_roots(self.workspace_root)

    def tearDown(self):
        self.tmp.cleanup()

    def _retain(self, spec, **kwargs):
        run_id = kwargs.pop("run_id", "r1")
        observed_at = kwargs.pop("observed_at", "2026-01-01T00:00:00Z")
        return retain(
            self.landing_root,
            spec,
            run_id=run_id,
            observed_at=observed_at,
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            **kwargs,
        )


class DedupTests(RetentionTestCase):
    def test_identical_document_acquired_twice_creates_one_blob(self):
        spec = make_spec()
        first = self._retain(spec, data=VALID_PDF)
        second = self._retain(spec, data=VALID_PDF)

        self.assertEqual(first.outcome, AcquisitionOutcome.ACQUIRED)
        self.assertEqual(second.outcome, AcquisitionOutcome.ALREADY_PRESENT_IDENTICAL)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(len(list(blobs_dir(self.landing_root).glob("*.pdf"))), 1)


class NewVersionTests(RetentionTestCase):
    def test_same_locator_different_bytes_creates_new_version(self):
        spec = make_spec()
        v1 = self._retain(spec, data=VALID_PDF)
        v2_bytes = VALID_PDF + b"\n% a real amendment changed these bytes\n"
        v2 = self._retain(spec, data=v2_bytes, known_latest_hash_for_logical_identity=v1.sha256)

        self.assertEqual(v2.outcome, AcquisitionOutcome.ACQUIRED)
        self.assertNotEqual(v1.sha256, v2.sha256)
        self.assertEqual(v2.supersedes_sha256, v1.sha256)
        self.assertEqual(len(list(blobs_dir(self.landing_root).glob("*.pdf"))), 2, "prior version must remain retained")


class HashVerificationTests(RetentionTestCase):
    def test_existing_blob_hash_is_verified_before_reuse(self):
        spec = make_spec()
        first = self._retain(spec, data=VALID_PDF)

        # Simulate external corruption of the already-retained blob, then
        # prove a subsequent "identical" retain attempt does not silently
        # trust it - it re-hashes the actual bytes on disk and fails loudly.
        target = blob_path(self.landing_root, first.sha256, ".pdf")
        target.write_bytes(VALID_PDF + b"CORRUPTED")

        with self.assertRaises(HashConflictError):
            self._retain(spec, data=VALID_PDF)

    def test_declared_source_hash_mismatch_is_quarantined_not_trusted(self):
        spec = make_spec()
        record = self._retain(spec, data=VALID_PDF, declared_sha256="0" * 64)
        self.assertEqual(record.outcome, AcquisitionOutcome.QUARANTINED)
        self.assertIn("declared_sha256_mismatch", record.outcome_reason)
        self.assertEqual(len(list(blobs_dir(self.landing_root).glob("*.pdf"))), 0)


class FailureClassificationTests(RetentionTestCase):
    def test_retryable_and_permanent_failures_remain_distinct(self):
        retryable = self._retain(make_spec("https://issuer.invalid/a.pdf"), fetch_error=FetchError(category="retryable", detail="timeout"))
        permanent = self._retain(make_spec("https://issuer.invalid/b.pdf"), fetch_error=FetchError(category="permanent", detail="404 not found"))

        self.assertEqual(retryable.outcome, AcquisitionOutcome.FAILED_RETRYABLE)
        self.assertEqual(permanent.outcome, AcquisitionOutcome.FAILED_PERMANENT)
        self.assertNotEqual(retryable.outcome, permanent.outcome)
        self.assertIsNone(retryable.sha256)
        self.assertIsNone(permanent.sha256)

    def test_missing_document_never_becomes_a_successful_empty_record(self):
        with self.assertRaises(ValueError):
            self._retain(make_spec())


class QuarantineIntegrationTests(RetentionTestCase):
    def test_malformed_document_goes_to_quarantine(self):
        record = self._retain(make_spec(), data=b"this is not a pdf at all")
        self.assertEqual(record.outcome, AcquisitionOutcome.QUARANTINED)
        self.assertEqual(record.outcome_reason, "not_a_pdf_header")

    def test_zero_byte_document_goes_to_quarantine(self):
        record = self._retain(make_spec(), data=b"")
        self.assertEqual(record.outcome, AcquisitionOutcome.QUARANTINED)
        self.assertEqual(record.outcome_reason, "empty_document")

    def test_quarantine_never_becomes_qualified_evidence_automatically(self):
        spec = make_spec()
        first = self._retain(spec, data=b"not a pdf")
        self.assertEqual(first.outcome, AcquisitionOutcome.QUARANTINED)

        # Re-attempting the same bad bytes must independently fail
        # validation again - quarantine is never consulted as if it were
        # the content-addressed store, so nothing is promoted by side effect.
        second = self._retain(spec, data=b"not a pdf")
        self.assertEqual(second.outcome, AcquisitionOutcome.QUARANTINED)
        self.assertEqual(len(list(blobs_dir(self.landing_root).glob("*"))), 0)


class QualificationBoundaryTests(RetentionTestCase):
    def test_every_outcome_carries_unknown_qualification_state(self):
        acquired = self._retain(make_spec("https://issuer.invalid/a.pdf"), data=VALID_PDF)
        quarantined = self._retain(make_spec("https://issuer.invalid/b.pdf"), data=b"bad")
        failed = self._retain(make_spec("https://issuer.invalid/c.pdf"), fetch_error=FetchError(category="retryable", detail="timeout"))

        for record in (acquired, quarantined, failed):
            self.assertEqual(record.qualification_state, QUALIFICATION_STATE_UNKNOWN)


class ProtectedRootIntegrationTests(RetentionTestCase):
    def test_retain_refuses_to_write_under_a_protected_root(self):
        protected_target = self.workspace_root / "dashboard-runtime" / "data-landing" / "official-financial-filings-v1"
        with self.assertRaises(ProtectedRootWriteError):
            retain(
                protected_target,
                make_spec(),
                run_id="r1",
                observed_at="2026-01-01T00:00:00Z",
                allowed_root=protected_target,
                protected_roots=self.protected_roots,
                data=VALID_PDF,
            )


if __name__ == "__main__":
    unittest.main()
