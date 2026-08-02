from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from price_basis_events import project_price_test_events


def event(**overrides):
    result = {
        "canonical_event_id": "official-1", "ticker": "HPG", "exchange": "HOSE", "event_type": "bonus_share", "ex_date": "2024-01-04",
        "entitlement_ratio": {"ratio_float": 0.2}, "ratio_basis": "new_shares_per_existing_share", "provider": "VCI", "provider_version": "4.0.4",
        "provider_event_id": "vci-1", "official_source_id": "hose-notice-1", "retrieved_at": "2026-08-02T00:00:00Z",
        "source_field_identities": {"ex_date": "notice.ex_date", "ratio": "notice.ratio"},
        "evidence": {"citation_id": "citation-1", "document_sha256": "hash-1", "source_url": "https://official.example/1"},
        "qualified_for_share_transition": False,
    }
    result.update(overrides)
    return result


class PriceBasisEventProjectionTests(unittest.TestCase):
    def test_price_test_can_be_qualified_without_share_transition_completion(self):
        projected = project_price_test_events([event()])
        self.assertEqual(len(projected["accepted"]), 1)
        self.assertTrue(projected["accepted"][0]["qualified_for_price_basis_test"])
        self.assertFalse(projected["accepted"][0]["qualified_for_share_transition"])

    def test_ambiguous_ex_date_or_ratio_is_excluded(self):
        projected = project_price_test_events([event(ex_date=None), event(provider_event_id="vci-2", entitlement_ratio={})])
        self.assertEqual([item["reason"] for item in projected["excluded"]],
                         ["qualified_ex_date_or_ratio_missing", "qualified_ex_date_or_ratio_missing"])

    def test_duplicate_conflicting_provider_identity_is_excluded(self):
        projected = project_price_test_events([event(), event(ex_date="2024-01-05")])
        self.assertEqual(projected["accepted"], [])
        self.assertEqual(projected["excluded"][0]["reason"], "duplicate_identity_conflicting_payload")

    def test_provider_lineage_is_optional_metadata(self):
        projected = project_price_test_events([event(provider_version=None, provider_event_id=None, provider=None)])
        self.assertEqual(len(projected["accepted"]), 1)

    def test_record_date_cannot_substitute_for_ex_date(self):
        projected = project_price_test_events([event(ex_date=None, record_date="2024-01-04")])
        self.assertEqual(projected["excluded"][0]["reason"], "qualified_ex_date_or_ratio_missing")

    def test_missing_explicit_ratio_basis_is_rejected(self):
        self.assertEqual(project_price_test_events([event(ratio_basis=None)])["excluded"][0]["reason"], "qualified_ex_date_or_ratio_missing")
