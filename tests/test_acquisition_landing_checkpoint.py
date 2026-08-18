"""Checkpoint/resume orchestration tests: interruption+resume, failure
isolation across a batch, and manifest-output determinism."""

import filecmp
import tempfile
import unittest
from pathlib import Path

from acquisition_landing_checkpoint import content_manifest_path, load_content_manifest, process_batch, run_report_path
from acquisition_landing_contract import AcquisitionOutcome, AcquisitionSpec
from acquisition_landing_isolation import default_protected_roots
from acquisition_landing_retention import blob_path, blobs_dir

VALID_PDF_A = b"%PDF-1.4\n%doc-a\n%%EOF"
VALID_PDF_B = b"%PDF-1.4\n%doc-b\n%%EOF"
VALID_PDF_C = b"%PDF-1.4\n%doc-c\n%%EOF"

FIXED_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def fixed_clock():
    return FIXED_TIMESTAMP


def make_items():
    spec_a = AcquisitionSpec(domain="d", source_locator="https://issuer.invalid/a.pdf", source_authority_class="issuer_ir")
    spec_b = AcquisitionSpec(domain="d", source_locator="https://issuer.invalid/b.pdf", source_authority_class="issuer_ir")
    spec_c = AcquisitionSpec(domain="d", source_locator="https://issuer.invalid/c.pdf", source_authority_class="issuer_ir")
    return [
        (spec_a, {"data": VALID_PDF_A}),
        (spec_b, {"data": VALID_PDF_B}),
        (spec_c, {"data": VALID_PDF_C}),
    ]


class CheckpointTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name)
        self.landing_root = self.workspace_root / "data-landing" / "official-financial-filings-v1"
        self.protected_roots = default_protected_roots(self.workspace_root)

    def tearDown(self):
        self.tmp.cleanup()


class InterruptionResumeTests(CheckpointTestCase):
    def test_interruption_and_resume_preserves_prior_completed_work(self):
        all_items = make_items()

        first_attempt = process_batch(
            self.landing_root,
            all_items[:2],  # simulate a run interrupted after 2 of 3 items
            run_id="interrupt-1",
            domain="d",
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            observed_at_fn=fixed_clock,
        )
        self.assertEqual(first_attempt.succeeded, 2)

        resumed = process_batch(
            self.landing_root,
            all_items,  # same run_id, full item list
            run_id="interrupt-1",
            domain="d",
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            observed_at_fn=fixed_clock,
            resume=True,
        )
        self.assertEqual(resumed.attempted, 3)
        self.assertEqual(resumed.skipped, 2, "the first two items must be recognized from checkpoint, not reprocessed")
        self.assertEqual(resumed.succeeded, 1, "only the third, genuinely new item is freshly acquired")

        manifest = load_content_manifest(self.landing_root)
        self.assertEqual(len(manifest["blobs"]), 3)
        self.assertEqual(len(list(blobs_dir(self.landing_root).glob("*.pdf"))), 3, "resume must not duplicate any blob")

    def test_rerun_after_interruption_produces_the_same_retained_corpus_as_one_uninterrupted_run(self):
        all_items = make_items()

        process_batch(
            self.landing_root, all_items[:1], run_id="same-run", domain="d",
            allowed_root=self.landing_root, protected_roots=self.protected_roots, observed_at_fn=fixed_clock,
        )
        process_batch(
            self.landing_root, all_items, run_id="same-run", domain="d",
            allowed_root=self.landing_root, protected_roots=self.protected_roots, observed_at_fn=fixed_clock,
        )
        interrupted_manifest = load_content_manifest(self.landing_root)

        uninterrupted_root = self.workspace_root / "data-landing-b" / "official-financial-filings-v1"
        process_batch(
            uninterrupted_root, all_items, run_id="same-run", domain="d",
            allowed_root=uninterrupted_root, protected_roots=default_protected_roots(self.workspace_root),
            observed_at_fn=fixed_clock,
        )
        uninterrupted_manifest = load_content_manifest(uninterrupted_root)

        self.assertEqual(
            {h: v["sha256"] for h, v in interrupted_manifest["blobs"].items()},
            {h: v["sha256"] for h, v in uninterrupted_manifest["blobs"].items()},
        )
        self.assertEqual(
            interrupted_manifest["latest_hash_by_logical_identity"],
            uninterrupted_manifest["latest_hash_by_logical_identity"],
        )


class FailureIsolationTests(CheckpointTestCase):
    def test_one_item_failure_does_not_abort_unrelated_successful_items(self):
        from acquisition_landing_identity import content_sha256

        items = make_items()
        good_1, bad, good_2 = items

        bad_sha = content_sha256(bad[1]["data"])
        corrupted_path = blob_path(self.landing_root, bad_sha, ".pdf")
        corrupted_path.parent.mkdir(parents=True, exist_ok=True)
        corrupted_path.write_bytes(b"already occupied by unrelated corrupted content")

        report = process_batch(
            self.landing_root,
            [good_1, bad, good_2],
            run_id="failure-isolation-1",
            domain="d",
            allowed_root=self.landing_root,
            protected_roots=self.protected_roots,
            observed_at_fn=fixed_clock,
        )

        self.assertEqual(report.attempted, 3)
        self.assertEqual(report.succeeded, 2)
        self.assertEqual(report.failed_permanent, 1)
        outcomes = [r["outcome"] for r in report.records]
        self.assertEqual(outcomes.count(AcquisitionOutcome.ACQUIRED.value), 2)
        self.assertEqual(outcomes.count(AcquisitionOutcome.FAILED_PERMANENT.value), 1)


class ManifestDeterminismTests(unittest.TestCase):
    def test_manifest_and_report_output_are_deterministic_for_equivalent_completed_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp)
            protected_roots = default_protected_roots(workspace_root)
            root_a = workspace_root / "run-a" / "official-financial-filings-v1"
            root_b = workspace_root / "run-b" / "official-financial-filings-v1"

            for root in (root_a, root_b):
                process_batch(
                    root, make_items(), run_id="deterministic-run", domain="d",
                    allowed_root=root, protected_roots=protected_roots, observed_at_fn=fixed_clock,
                )

            self.assertTrue(
                filecmp.cmp(content_manifest_path(root_a), content_manifest_path(root_b), shallow=False),
                "content_manifest.json must be byte-identical for two independent runs over equivalent input",
            )
            self.assertTrue(
                filecmp.cmp(
                    run_report_path(root_a, "deterministic-run"),
                    run_report_path(root_b, "deterministic-run"),
                    shallow=False,
                ),
                "run-report JSON must be byte-identical for two independent runs over equivalent input",
            )


if __name__ == "__main__":
    unittest.main()
