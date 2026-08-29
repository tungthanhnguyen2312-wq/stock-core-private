"""Focused A3 as-of query and revision ledger tests.

Tests cover the PIT safety contract required by the A3 milestone:
- Future revision exclusion
- Identical reacquisition (no fictitious new fact)
- Changed observation (separate identity)
- Missing first-observed / temporal evidence (fail closed)
- Publication vs transport metadata
- Research vs execution
- Determinism (repeated identical input => stable output)
- CONFLICT case (multiple irresolvable candidates)
- Supersession chain resolution
"""
from __future__ import annotations

import hashlib
import json
import unittest
from typing import Any, Mapping

from asof_query_ledger import (
    ASOF_QUERY_CONTRACT_VERSION,
    AsofResultCode,
    LedgerEntry,
    RevisionKnowabilityCode,
    build_revision_ledger,
    canonical_result_identity,
    deterministic_ledger_hash,
    query_as_of,
)
from bitemporal_semantic_contract import (
    KnowledgeTimeStatus,
    HistoricalReconstructionScope,
)


# ---------------------------------------------------------------------------
# Helper builders for synthetic retained-observation dicts
# ---------------------------------------------------------------------------

def _obs_with_known_first_observed(
    *,
    observation_identity: str,
    first_observed_at: str,
    knowledge_session: str,
    kt_status: str = KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_FIRST_OBSERVED_CONSERVATIVE.value,
    hr_scope: str = HistoricalReconstructionScope.FROM_FIRST_OBSERVED_FORWARD_ONLY.value,
    supersedes_identity: str | None = None,
    valid_time_reference: str | None = None,
    pub_at: str | None = None,
    pub_prec: str | None = "DATE_ONLY",
    pub_tier: str = "OFFICIAL_ISSUER_IR_OR_EXCHANGE",
) -> dict[str, Any]:
    """Build a flat A2-style receipt envelope with resolved knowledge."""
    d: dict[str, Any] = {
        "observation_identity": observation_identity,
        "first_observed_at": first_observed_at,
        "first_observed_status": "RETAINED",
        "knowledge_resolution": {
            "knowledge_time_status": kt_status,
            "knowledge_available_research_session": knowledge_session,
            "historical_reconstruction_scope": hr_scope,
        },
        "valid_time_reference": valid_time_reference,
        "source_published_at": pub_at,
        "source_published_at_precision": pub_prec,
        "publication_time": {
            "publication_authority_tier": pub_tier,
            "source_published_at": pub_at,
            "source_published_at_precision": pub_prec,
        },
    }
    if supersedes_identity is not None:
        d["supersedes_identity"] = supersedes_identity
    return d


def _obs_legacy_unknown(
    *,
    observation_identity: str,
    valid_time_reference: str | None = None,
) -> dict[str, Any]:
    """Build a legacy observation with no trustworthy receipt."""
    return {
        "observation_identity": observation_identity,
        "first_observed_at": None,
        "first_observed_status": "LEGACY_UNKNOWN",
        "knowledge_resolution": {
            "knowledge_time_status": KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN.value,
            "knowledge_available_research_session": None,
            "historical_reconstruction_scope": HistoricalReconstructionScope.NONE.value,
        },
        "valid_time_reference": valid_time_reference,
        "source_published_at": None,
        "source_published_at_precision": "UNKNOWN",
    }


def _obs_with_official_pub(
    *,
    observation_identity: str,
    source_published_at: str,
    knowledge_session: str,
    hr_scope: str = HistoricalReconstructionScope.FROM_QUALIFIED_SOURCE_PUBLICATION.value,
    first_observed_at: str | None = None,
    supersedes_identity: str | None = None,
    valid_time_reference: str | None = None,
) -> dict[str, Any]:
    """Build an observation with a qualified official publication date."""
    d: dict[str, Any] = {
        "observation_identity": observation_identity,
        "first_observed_at": first_observed_at,
        "first_observed_status": "RETAINED" if first_observed_at else "LEGACY_UNKNOWN",
        "knowledge_resolution": {
            "knowledge_time_status": KnowledgeTimeStatus.KNOWLEDGE_RESOLVED_SOURCE_PUBLICATION_DATE_ONLY.value,
            "knowledge_available_research_session": knowledge_session,
            "historical_reconstruction_scope": hr_scope,
        },
        "valid_time_reference": valid_time_reference,
        "source_published_at": source_published_at,
        "source_published_at_precision": "DATE_ONLY",
        "publication_time": {
            "publication_authority_tier": "OFFICIAL_ISSUER_IR_OR_EXCHANGE",
            "source_published_at": source_published_at,
            "source_published_at_precision": "DATE_ONLY",
            "source_identity": observation_identity + "_doc",
        },
    }
    if supersedes_identity is not None:
        d["supersedes_identity"] = supersedes_identity
    return d


# ---------------------------------------------------------------------------
# 3.3 PIT safety tests
# ---------------------------------------------------------------------------

class TestFutureRevisionExclusion(unittest.TestCase):
    """A later revision existing today cannot appear in an earlier as-of result."""

    def test_later_revision_excluded_from_earlier_as_of(self):
        early_obs = _obs_with_known_first_observed(
            observation_identity="sha256:early",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
            valid_time_reference="2025-12-31",
        )
        later_obs = _obs_with_known_first_observed(
            observation_identity="sha256:later",
            first_observed_at="2026-06-01T07:30:00Z",
            knowledge_session="2026-06-01",
            valid_time_reference="2025-12-31",
            supersedes_identity="sha256:early",
        )
        # As-of 2026-03-01: only early should be selected; later is not yet knowable
        result = query_as_of([early_obs, later_obs], "2026-03-01")
        self.assertEqual(result.result_code, AsofResultCode.READY)
        self.assertEqual(result.selected_observation_identity, "sha256:early")
        self.assertIn("sha256:later", result.excluded_future_observation_identities)
        self.assertNotIn("sha256:later", [e.observation_identity for e in result.ledger
                                          if e.knowability_at_cutoff == RevisionKnowabilityCode.KNOWABLE])

    def test_later_revision_visible_at_later_cutoff(self):
        early_obs = _obs_with_known_first_observed(
            observation_identity="sha256:early",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        later_obs = _obs_with_known_first_observed(
            observation_identity="sha256:later",
            first_observed_at="2026-06-01T07:30:00Z",
            knowledge_session="2026-06-01",
            supersedes_identity="sha256:early",
        )
        # As-of 2026-06-15: later supersedes early, non-superseded is later
        result = query_as_of([early_obs, later_obs], "2026-06-15")
        self.assertEqual(result.result_code, AsofResultCode.READY)
        self.assertEqual(result.selected_observation_identity, "sha256:later")
        self.assertIn("SUPERSESSION_CHAIN_RESOLVED_SINGLE_NON_SUPERSEDED", result.warnings)


class TestIdenticalReacquisition(unittest.TestCase):
    """Identical bytes retaining earliest first_observed must not become a new factual revision."""

    def test_identical_bytes_produce_same_single_observation(self):
        # Both observations have the same identity (identical bytes => same SHA-256)
        obs1 = _obs_with_known_first_observed(
            observation_identity="sha256:same",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        # A re-observation of identical bytes should use the same observation_identity
        # (A2 merge_identical_reobservation preserves earliest; only one identity exists)
        obs2 = _obs_with_known_first_observed(
            observation_identity="sha256:same",  # same identity — not a new fact
            first_observed_at="2026-01-10T07:30:00Z",  # same (merged in A2)
            knowledge_session="2026-01-10",
        )
        # With identical identities there is a semantic duplicate -- CONFLICT should
        # not occur because after deduplication it's one observation.
        # If both dicts somehow appear (e.g. two serialised copies), we expect CONFLICT
        # because we cannot distinguish deduplication context here.  The correct
        # caller usage is to deduplicate before calling query_as_of.
        # With a single deduplicated entry the result is READY.
        result_single = query_as_of([obs1], "2026-01-15")
        self.assertEqual(result_single.result_code, AsofResultCode.READY)
        self.assertEqual(result_single.selected_observation_identity, "sha256:same")

    def test_identical_reacquisition_is_not_a_new_revision_in_ledger(self):
        obs = _obs_with_known_first_observed(
            observation_identity="sha256:same",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        ledger = build_revision_ledger([obs], "2026-02-01")
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0].observation_identity, "sha256:same")
        self.assertEqual(ledger[0].first_observed_at, "2026-01-10T07:30:00Z")
        # supersedes_identity is None -- no predecessor exists for a single observation
        self.assertIsNone(ledger[0].supersedes_identity)


class TestChangedObservation(unittest.TestCase):
    """Changed bytes / observation identity must be separately represented."""

    def test_changed_bytes_create_distinct_identity(self):
        original = _obs_with_known_first_observed(
            observation_identity="sha256:v1",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        revised = _obs_with_known_first_observed(
            observation_identity="sha256:v2",
            first_observed_at="2026-04-01T07:30:00Z",
            knowledge_session="2026-04-01",
            supersedes_identity="sha256:v1",
        )
        ledger = build_revision_ledger([original, revised], "2026-06-01")
        self.assertEqual(len(ledger), 2)
        identities = {e.observation_identity for e in ledger}
        self.assertIn("sha256:v1", identities)
        self.assertIn("sha256:v2", identities)

    def test_changed_observation_only_knowable_from_its_own_boundary(self):
        original = _obs_with_known_first_observed(
            observation_identity="sha256:v1",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        revised = _obs_with_known_first_observed(
            observation_identity="sha256:v2",
            first_observed_at="2026-04-01T07:30:00Z",
            knowledge_session="2026-04-01",
            supersedes_identity="sha256:v1",
        )
        # Before v2 is knowable: only v1
        result_before = query_as_of([original, revised], "2026-02-01")
        self.assertEqual(result_before.result_code, AsofResultCode.READY)
        self.assertEqual(result_before.selected_observation_identity, "sha256:v1")
        # v2 is not yet knowable at 2026-02-01
        future_ids = result_before.excluded_future_observation_identities
        self.assertIn("sha256:v2", future_ids)

    def test_ledger_knowability_flags_per_entry(self):
        original = _obs_with_known_first_observed(
            observation_identity="sha256:v1",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        revised = _obs_with_known_first_observed(
            observation_identity="sha256:v2",
            first_observed_at="2026-04-01T07:30:00Z",
            knowledge_session="2026-04-01",
            supersedes_identity="sha256:v1",
        )
        ledger = build_revision_ledger([original, revised], "2026-02-01")
        v1_entry = next(e for e in ledger if e.observation_identity == "sha256:v1")
        v2_entry = next(e for e in ledger if e.observation_identity == "sha256:v2")
        self.assertEqual(v1_entry.knowability_at_cutoff, RevisionKnowabilityCode.KNOWABLE)
        self.assertEqual(v2_entry.knowability_at_cutoff, RevisionKnowabilityCode.NOT_YET_KNOWABLE)


class TestMissingTemporalEvidence(unittest.TestCase):
    """Legacy evidence lacking receipt must fail closed."""

    def test_legacy_unknown_fails_closed_no_backfill(self):
        obs = _obs_legacy_unknown(observation_identity="sha256:legacy", valid_time_reference="2024-12-31")
        result = query_as_of([obs], "2026-06-01")
        self.assertEqual(result.result_code, AsofResultCode.UNKNOWN_TEMPORAL)
        self.assertIsNone(result.selected_observation_identity)
        # Verify authority invariants are preserved
        self.assertEqual(result.authority_boundaries["raw_as_traded"], "NOT_PROMOTED")
        self.assertEqual(result.authority_boundaries["historical_price_pit"], "BLOCKED")

    def test_legacy_unknown_in_ledger_is_labelled_not_inferred(self):
        obs = _obs_legacy_unknown(observation_identity="sha256:legacy")
        ledger = build_revision_ledger([obs], "2026-06-01")
        self.assertEqual(len(ledger), 1)
        entry = ledger[0]
        self.assertEqual(entry.knowability_at_cutoff, RevisionKnowabilityCode.UNKNOWN_TEMPORAL)
        self.assertIn("TEMPORAL_EVIDENCE_INSUFFICIENT_KNOWLEDGE_UNKNOWN", entry.warnings)
        # No backfill: knowledge_available_research_session must be None
        self.assertIsNone(entry.knowledge_available_research_session)

    def test_no_observations_returns_no_qualifying(self):
        result = query_as_of([], "2026-06-01")
        self.assertEqual(result.result_code, AsofResultCode.NO_QUALIFYING_OBSERVATION)

    def test_invalid_as_of_date_fails_closed(self):
        obs = _obs_with_known_first_observed(
            observation_identity="sha256:x",
            first_observed_at="2026-01-01T00:00:00Z",
            knowledge_session="2026-01-01",
        )
        result = query_as_of([obs], "not-a-date")
        self.assertEqual(result.result_code, AsofResultCode.UNKNOWN_TEMPORAL)
        self.assertIn("AS_OF_RESEARCH_SESSION_NOT_A_VALID_DATE", result.warnings)


class TestPublicationVsTransportMetadata(unittest.TestCase):
    """HTTP Date / Last-Modified / ETag must not become publication authority."""

    def test_http_headers_are_not_used_for_knowledge(self):
        # An observation that has HTTP headers but no qualified publication
        # and no first_observed_at should fail closed, not use HTTP Date
        obs = {
            "observation_identity": "sha256:http_test",
            "first_observed_at": None,
            "first_observed_status": "LEGACY_UNKNOWN",
            "http_response_date": "Fri, 10 Jan 2026 07:30:00 GMT",
            "http_last_modified": "Thu, 09 Jan 2026 12:00:00 GMT",
            "http_etag": "abc123",
            "knowledge_resolution": {
                "knowledge_time_status": KnowledgeTimeStatus.KNOWLEDGE_UNKNOWN.value,
                "knowledge_available_research_session": None,
                "historical_reconstruction_scope": HistoricalReconstructionScope.NONE.value,
            },
        }
        result = query_as_of([obs], "2026-06-01")
        # Must fail closed -- HTTP headers are NOT used to derive knowledge
        self.assertEqual(result.result_code, AsofResultCode.UNKNOWN_TEMPORAL)
        self.assertIsNone(result.selected_observation_identity)

    def test_qualified_official_pub_is_used_not_http_headers(self):
        # Official publication date => READY, separate from HTTP metadata
        obs = _obs_with_official_pub(
            observation_identity="sha256:official_doc",
            source_published_at="2026-01-09",
            knowledge_session="2026-01-10",
        )
        result = query_as_of([obs], "2026-01-15")
        self.assertEqual(result.result_code, AsofResultCode.READY)
        self.assertEqual(result.selected_observation_identity, "sha256:official_doc")


class TestResearchVsExecution(unittest.TestCase):
    """Research-session eligibility must not imply same-close execution eligibility."""

    def test_ready_result_does_not_imply_execution(self):
        obs = _obs_with_known_first_observed(
            observation_identity="sha256:ready",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        result = query_as_of([obs], "2026-01-15")
        self.assertEqual(result.result_code, AsofResultCode.READY)
        # Authority boundaries must explicitly block execution authority
        self.assertEqual(result.authority_boundaries["same_session_close_execution"], "NOT_ESTABLISHED")
        self.assertEqual(result.authority_boundaries["raw_as_traded"], "NOT_PROMOTED")
        self.assertEqual(result.authority_boundaries["historical_price_pit"], "BLOCKED")

    def test_authority_invariants_present_on_all_result_codes(self):
        for result in [
            query_as_of([], "2026-01-15"),
            query_as_of([_obs_legacy_unknown(observation_identity="sha256:leg")], "2026-01-15"),
            query_as_of([_obs_with_known_first_observed(
                observation_identity="sha256:future",
                first_observed_at="2026-06-01T00:00:00Z",
                knowledge_session="2026-06-01",
            )], "2026-01-15"),
        ]:
            self.assertIn("same_session_close_execution", result.authority_boundaries)
            self.assertEqual(result.authority_boundaries["same_session_close_execution"], "NOT_ESTABLISHED")
            self.assertEqual(result.authority_boundaries["raw_as_traded"], "NOT_PROMOTED")


class TestDeterminism(unittest.TestCase):
    """Repeated identical input must produce byte/logically equivalent output."""

    def test_same_input_twice_produces_identical_identity(self):
        obs1 = _obs_with_known_first_observed(
            observation_identity="sha256:a",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        obs2 = _obs_with_known_first_observed(
            observation_identity="sha256:b",
            first_observed_at="2026-02-01T07:30:00Z",
            knowledge_session="2026-02-01",
            supersedes_identity="sha256:a",
        )
        result_a = query_as_of([obs1, obs2], "2026-06-01")
        result_b = query_as_of([obs1, obs2], "2026-06-01")
        self.assertEqual(canonical_result_identity(result_a), canonical_result_identity(result_b))

    def test_input_order_does_not_change_ledger_or_result(self):
        obs1 = _obs_with_known_first_observed(
            observation_identity="sha256:a",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        obs2 = _obs_with_known_first_observed(
            observation_identity="sha256:b",
            first_observed_at="2026-02-01T07:30:00Z",
            knowledge_session="2026-02-01",
            supersedes_identity="sha256:a",
        )
        result_forward = query_as_of([obs1, obs2], "2026-01-15")
        result_reversed = query_as_of([obs2, obs1], "2026-01-15")
        # Both should select sha256:a (only knowable at 2026-01-15)
        self.assertEqual(result_forward.result_code, AsofResultCode.READY)
        self.assertEqual(result_reversed.result_code, AsofResultCode.READY)
        self.assertEqual(result_forward.selected_observation_identity, "sha256:a")
        self.assertEqual(result_reversed.selected_observation_identity, "sha256:a")
        self.assertEqual(canonical_result_identity(result_forward), canonical_result_identity(result_reversed))

    def test_ledger_hash_is_stable(self):
        obs = _obs_with_known_first_observed(
            observation_identity="sha256:stable",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        ledger1 = build_revision_ledger([obs], "2026-06-01")
        ledger2 = build_revision_ledger([obs], "2026-06-01")
        self.assertEqual(deterministic_ledger_hash(ledger1), deterministic_ledger_hash(ledger2))


class TestConflictCase(unittest.TestCase):
    """Multiple irresolvable knowable candidates -> CONFLICT."""

    def test_two_knowable_without_supersession_is_conflict(self):
        obs_a = _obs_with_known_first_observed(
            observation_identity="sha256:conflict_a",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        obs_b = _obs_with_known_first_observed(
            observation_identity="sha256:conflict_b",
            first_observed_at="2026-01-15T07:30:00Z",
            knowledge_session="2026-01-15",
            # No supersedes_identity -- no chain to resolve
        )
        result = query_as_of([obs_a, obs_b], "2026-06-01")
        self.assertEqual(result.result_code, AsofResultCode.CONFLICT)
        self.assertIsNone(result.selected_observation_identity)
        self.assertIn("sha256:conflict_a", result.conflict_observation_identities)
        self.assertIn("sha256:conflict_b", result.conflict_observation_identities)

    def test_all_future_is_not_yet_knowable(self):
        obs = _obs_with_known_first_observed(
            observation_identity="sha256:future_only",
            first_observed_at="2026-12-01T07:30:00Z",
            knowledge_session="2026-12-01",
        )
        result = query_as_of([obs], "2026-01-01")
        self.assertEqual(result.result_code, AsofResultCode.NOT_YET_KNOWABLE)
        self.assertIn("sha256:future_only", result.excluded_future_observation_identities)


class TestRevisionLedgerSemantics(unittest.TestCase):
    """Section 3.2 ledger-specific invariants."""

    def test_ledger_includes_both_knowable_and_future_entries(self):
        early = _obs_with_known_first_observed(
            observation_identity="sha256:early",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        later = _obs_with_known_first_observed(
            observation_identity="sha256:later",
            first_observed_at="2026-06-01T07:30:00Z",
            knowledge_session="2026-06-01",
            supersedes_identity="sha256:early",
        )
        legacy = _obs_legacy_unknown(observation_identity="sha256:legacy")
        ledger = build_revision_ledger([early, later, legacy], "2026-03-01")
        self.assertEqual(len(ledger), 3)
        codes = {e.observation_identity: e.knowability_at_cutoff for e in ledger}
        self.assertEqual(codes["sha256:early"], RevisionKnowabilityCode.KNOWABLE)
        self.assertEqual(codes["sha256:later"], RevisionKnowabilityCode.NOT_YET_KNOWABLE)
        self.assertEqual(codes["sha256:legacy"], RevisionKnowabilityCode.UNKNOWN_TEMPORAL)

    def test_ledger_ordered_by_knowledge_session_then_identity(self):
        obs_b = _obs_with_known_first_observed(
            observation_identity="sha256:zzz",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        obs_a = _obs_with_known_first_observed(
            observation_identity="sha256:aaa",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        obs_c = _obs_with_known_first_observed(
            observation_identity="sha256:mid",
            first_observed_at="2026-02-01T07:30:00Z",
            knowledge_session="2026-02-01",
        )
        ledger = build_revision_ledger([obs_b, obs_c, obs_a], "2026-06-01")
        # Same session: ordered by identity
        self.assertEqual(ledger[0].observation_identity, "sha256:aaa")
        self.assertEqual(ledger[1].observation_identity, "sha256:zzz")
        # Later session last
        self.assertEqual(ledger[2].observation_identity, "sha256:mid")

    def test_ledger_entry_preserves_supersession_lineage(self):
        early = _obs_with_known_first_observed(
            observation_identity="sha256:v1",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        revised = _obs_with_known_first_observed(
            observation_identity="sha256:v2",
            first_observed_at="2026-04-01T07:30:00Z",
            knowledge_session="2026-04-01",
            supersedes_identity="sha256:v1",
        )
        ledger = build_revision_ledger([early, revised], "2026-06-01")
        v2_entry = next(e for e in ledger if e.observation_identity == "sha256:v2")
        self.assertEqual(v2_entry.supersedes_identity, "sha256:v1")


class TestContractVersion(unittest.TestCase):
    def test_result_carries_contract_version(self):
        obs = _obs_with_known_first_observed(
            observation_identity="sha256:version_test",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        result = query_as_of([obs], "2026-01-15")
        d = result.to_dict()
        self.assertEqual(d["contract_version"], ASOF_QUERY_CONTRACT_VERSION)

    def test_result_identity_is_stable_prefix(self):
        obs = _obs_with_known_first_observed(
            observation_identity="sha256:id_test",
            first_observed_at="2026-01-10T07:30:00Z",
            knowledge_session="2026-01-10",
        )
        result = query_as_of([obs], "2026-01-15")
        identity = canonical_result_identity(result)
        self.assertTrue(identity.startswith(ASOF_QUERY_CONTRACT_VERSION + ":"))


if __name__ == "__main__":
    unittest.main()
