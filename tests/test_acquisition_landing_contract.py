"""Contract-level tests: outcome vocabulary, FetchError classification, and
the "never build a silently-empty record" guarantee."""

import unittest

from acquisition_landing_contract import (
    QUALIFICATION_STATE_UNKNOWN,
    AcquisitionOutcome,
    AcquisitionSpec,
    FetchError,
    IncompleteObservationError,
    build_record,
)

SPEC = AcquisitionSpec(
    domain="test-domain",
    source_locator="https://example.invalid/doc.pdf",
    source_authority_class="issuer_ir",
)


class OutcomeVocabularyTests(unittest.TestCase):
    def test_seven_required_outcomes_exist(self):
        expected = {
            "ACQUIRED",
            "ALREADY_PRESENT_IDENTICAL",
            "QUARANTINED",
            "FAILED_RETRYABLE",
            "FAILED_PERMANENT",
            "UNSUPPORTED",
            "BLOCKED_BY_POLICY",
        }
        self.assertEqual({o.value for o in AcquisitionOutcome}, expected)


class FetchErrorTests(unittest.TestCase):
    def test_rejects_unknown_category(self):
        with self.assertRaises(Exception):
            FetchError(category="not-a-real-category", detail="x")

    def test_category_outcome_mapping_is_distinct(self):
        mapping = {
            "retryable": AcquisitionOutcome.FAILED_RETRYABLE,
            "permanent": AcquisitionOutcome.FAILED_PERMANENT,
            "unsupported": AcquisitionOutcome.UNSUPPORTED,
            "blocked_by_policy": AcquisitionOutcome.BLOCKED_BY_POLICY,
        }
        seen = set()
        for category, expected_outcome in mapping.items():
            err = FetchError(category=category, detail="detail")
            self.assertEqual(err.outcome(), expected_outcome)
            seen.add(err.outcome())
        self.assertEqual(len(seen), 4, "each fetch-error category must map to a distinct outcome")


class BuildRecordGuaranteeTests(unittest.TestCase):
    def test_success_without_sha256_is_rejected(self):
        with self.assertRaises(IncompleteObservationError):
            build_record(
                run_id="r1",
                spec=SPEC,
                observed_at="2026-01-01T00:00:00Z",
                outcome=AcquisitionOutcome.ACQUIRED,
                sha256=None,
            )

    def test_failure_without_reason_is_rejected(self):
        with self.assertRaises(IncompleteObservationError):
            build_record(
                run_id="r1",
                spec=SPEC,
                observed_at="2026-01-01T00:00:00Z",
                outcome=AcquisitionOutcome.FAILED_PERMANENT,
                outcome_reason=None,
            )

    def test_every_record_carries_unknown_qualification_state(self):
        record = build_record(
            run_id="r1",
            spec=SPEC,
            observed_at="2026-01-01T00:00:00Z",
            outcome=AcquisitionOutcome.ACQUIRED,
            sha256="a" * 64,
            storage_locator="raw/blobs/a.pdf",
        )
        self.assertEqual(record.qualification_state, QUALIFICATION_STATE_UNKNOWN)

    def test_record_serializes_outcome_as_plain_string(self):
        record = build_record(
            run_id="r1",
            spec=SPEC,
            observed_at="2026-01-01T00:00:00Z",
            outcome=AcquisitionOutcome.ACQUIRED,
            sha256="a" * 64,
            storage_locator="raw/blobs/a.pdf",
        )
        payload = record.to_dict()
        self.assertEqual(payload["outcome"], "ACQUIRED")
        self.assertIsInstance(payload["outcome"], str)


if __name__ == "__main__":
    unittest.main()
