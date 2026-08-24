"""official_issuer_disclosure_registry projects retained evidence; it computes none of its own."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import official_issuer_disclosure_registry as reg  # noqa: E402


class ProjectDisclosureRecord(unittest.TestCase):
    def test_metadata_only_without_detail(self):
        manifest_record = {
            "document_id": "D1", "ticker": "HPG", "source_authority": "HOSE",
            "source_url": "https://www.hsx.vn/x.html", "document_type": "corporate_action_notice",
            "published_at": "2026-08-01", "observed_at": "2026-08-24T00:00:00Z",
            "content_sha256": "abc", "relative_path": "documents/HPG/x.html",
            "parser_status": "ready_for_direct_citations", "supersedes_document_id": None,
        }
        record = reg.project_disclosure_record(manifest_record=manifest_record, source_id="hose")
        self.assertEqual(record["qualification"], reg.QUALIFICATION_METADATA_ONLY)
        self.assertEqual(record["exchange"], "HOSE")
        self.assertEqual(record["disclosure_type"], "CORPORATE_ACTION")
        self.assertEqual(record["amendment_status"], "ORIGINAL")
        self.assertEqual(record["filing_id"], "D1")

    def test_structured_with_complete_detail(self):
        manifest_record = {
            "document_id": "D2", "ticker": "MULTI", "source_authority": "HNX",
            "source_url": "https://www.hnx.vn/x.html", "document_type": "insider_transaction_notice",
            "published_at": None, "observed_at": "2026-08-24T00:00:00Z", "content_sha256": "def",
            "relative_path": "documents/MULTI/x.html", "parser_status": "ready_for_direct_citations",
            "supersedes_document_id": None,
        }
        detail = {"ticker": "AIG", "title": "T", "published_at_raw": "15:40 22/08/2026",
                  "fields": {"actor_individual_name": "X"}, "extraction_complete": True}
        record = reg.project_disclosure_record(manifest_record=manifest_record, source_id="hnx",
                                               detail=detail, observation_state="REGISTERED_SELL")
        self.assertEqual(record["ticker"], "AIG")  # detail's page-observed ticker wins over the store placeholder
        self.assertEqual(record["qualification"], reg.QUALIFICATION_STRUCTURED)
        self.assertEqual(record["disclosure_type"], "INSIDER_TRANSACTION")
        self.assertEqual(record["observation_state"], "REGISTERED_SELL")

    def test_amendment_status_from_supersedes(self):
        manifest_record = {"document_id": "D3", "ticker": "HPG", "source_authority": "HOSE",
                           "source_url": "u", "document_type": "amendment_or_supersession_notice",
                           "supersedes_document_id": "D1", "content_sha256": "x",
                           "relative_path": "p", "parser_status": "ready_for_direct_citations"}
        record = reg.project_disclosure_record(manifest_record=manifest_record, source_id="hose")
        self.assertEqual(record["amendment_status"], "AMENDMENT")
        self.assertEqual(record["supersedes"], "D1")


class DetectConflicts(unittest.TestCase):
    def test_no_conflict_on_empty_batch(self):
        self.assertEqual(reg.detect_conflicts([], {}), [])

    def test_registration_then_result_is_lifecycle_not_conflict(self):
        """A registration and its own later result notice are *expected* to disagree in state
        (that is the announcement -> registration -> execution lifecycle, kept as separate
        facts per the milestone spec) -- this must never be reported as CONFLICTING_EVIDENCE."""
        records = [
            {"filing_id": "A", "ticker": "VNF", "published_at": "2026-08-22", "amendment_status": "ORIGINAL"},
            {"filing_id": "B", "ticker": "VNF", "published_at": "2026-08-22", "amendment_status": "ORIGINAL"},
        ]
        observations = {
            "A": {"actor_name": "X", "state": "REGISTERED_BUY"},
            "B": {"actor_name": "X", "state": "NOT_EXECUTED"},
        }
        self.assertEqual(reg.detect_conflicts(records, observations), [])

    def test_two_registrations_same_actor_same_day_disagreeing_is_flagged(self):
        records = [
            {"filing_id": "A", "ticker": "HPG", "published_at": "2026-08-22", "amendment_status": "ORIGINAL"},
            {"filing_id": "B", "ticker": "HPG", "published_at": "2026-08-22", "amendment_status": "ORIGINAL"},
        ]
        observations = {
            "A": {"actor_name": "X", "state": "REGISTERED_BUY"},
            "B": {"actor_name": "X", "state": "REGISTERED_SELL"},
        }
        conflicts = reg.detect_conflicts(records, observations)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["resolution"], "CONFLICTING_EVIDENCE")
        self.assertEqual(conflicts[0]["stage"], "registration")

    def test_amendment_linked_records_never_flagged(self):
        records = [
            {"filing_id": "A", "ticker": "HPG", "published_at": "2026-08-22", "amendment_status": "ORIGINAL"},
            {"filing_id": "B", "ticker": "HPG", "published_at": "2026-08-22", "amendment_status": "AMENDMENT"},
        ]
        observations = {"A": {"actor_name": "X", "state": "REGISTERED_BUY"},
                        "B": {"actor_name": "X", "state": "REGISTERED_SELL"}}
        self.assertEqual(reg.detect_conflicts(records, observations), [])


class CoverageReport(unittest.TestCase):
    def test_denominators_are_exact_not_estimated(self):
        report = reg.coverage_report(
            universe_count=1683, source_visible_issuers=5, disclosure_records=[{"ticker": "A"}, {"ticker": "B"}],
            insider_observations=[{"state": "REGISTERED_BUY"}, {"state": "NOT_EXECUTED"}],
            major_holder_observations=[{"state": "CEASED_MAJOR_HOLDER"}],
            audit_evaluations=[{"qualification": "EXTRACTED"}, {"qualification": "NOT_IDENTIFIED"}],
            unavailable=1, source_rejected=0, parse_blocked=0, semantic_blocked=0)
        self.assertEqual(report["UNIVERSE_COUNT"], 1683)
        self.assertEqual(report["DISCLOSURES_RETAINED"], 2)
        self.assertEqual(report["INSIDER_REGISTRATION_EVENTS"], 1)
        self.assertEqual(report["INSIDER_EXECUTION_EVENTS"], 1)
        self.assertEqual(report["MAJOR_HOLDER_EVENTS"], 1)
        self.assertEqual(report["AUDIT_OPINION_QUALIFIED"], 1)
        self.assertEqual(report["AUDIT_DOCUMENTS"], 2)


if __name__ == "__main__":
    unittest.main()
