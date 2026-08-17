from __future__ import annotations

import copy
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import canonical_universe_tiers as tiers


def candidate(symbol: str, instrument_class: str | None, *, listing: str | None = "UNKNOWN",
              exchange: str | None = None) -> dict:
    selected = {}
    if instrument_class is not None:
        selected["instrument_class"] = {"value": instrument_class}
    if listing is not None:
        selected["listing_status"] = {"value": listing}
    if exchange is not None:
        selected["exchange"] = {"value": exchange}
    return {
        "candidate_id": f"candidate:{symbol}",
        "provider_identities": [f"dnse:symbol:{symbol.casefold()}"],
        "selected_fields": selected,
    }


def c1_artifact(*candidates: dict) -> dict:
    payload = {"schema_version": "1.0.0", "canonical_instrument_candidates": list(candidates)}
    content_hash = tiers._hash(payload)
    return {**payload, "content_hash": content_hash,
            "artifact_id": f"canonical-instrument-reconciliation:{content_hash}"}


def built(*candidates: dict, **kwargs) -> dict:
    return tiers.build_universe_tier_artifact(
        c1_artifact(*candidates), as_of_session="2026-08-07", generated_at="2026-08-16T00:00:00+07:00", **kwargs,
    )


def snapshot(artifact: dict, tier: str, scope: str | None = None) -> dict:
    return next(item for item in artifact["snapshots"] if item["universe_tier"] == tier and item["tier_scope"] == scope)


class CanonicalUniverseTierTests(unittest.TestCase):
    def test_unknown_listing_status_never_becomes_active(self):
        artifact = built(candidate("EQ", "EQUITY"))
        active = snapshot(artifact, tiers.ACTIVE_UNIVERSE)["memberships"][0]
        self.assertEqual(tiers.UNKNOWN, active["state"])
        self.assertEqual("listing_status_unknown", active["reason_code"])

    def test_one_candidate_can_have_different_states_across_tiers(self):
        artifact = built(candidate("EQ", "EQUITY"))
        listed = snapshot(artifact, tiers.LISTED_EQUITY_CANDIDATE)["memberships"][0]
        active = snapshot(artifact, tiers.ACTIVE_UNIVERSE)["memberships"][0]
        self.assertEqual(tiers.INCLUDED, listed["state"])
        self.assertEqual(tiers.UNKNOWN, active["state"])

    def test_unknown_and_not_applicable_are_not_excluded(self):
        artifact = built(candidate("UNKNOWN", "UNKNOWN_SECURITY_GROUP"), candidate("INDEX", "INDEX"))
        rows = snapshot(artifact, tiers.LISTED_EQUITY_CANDIDATE)["memberships"]
        states = {row["instrument_candidate_id"]: row["state"] for row in rows}
        self.assertEqual(tiers.UNKNOWN, states["candidate:UNKNOWN"])
        self.assertEqual(tiers.NOT_APPLICABLE, states["candidate:INDEX"])
        self.assertNotIn(tiers.EXCLUDED, states.values())

    def test_explicit_non_equity_classes_get_class_specific_exclusion_reasons(self):
        # Aligned with dnse_instrument_universe.INSTRUMENT_CLASSES -- each known non-equity class
        # gets its own reason code instead of a single undifferentiated "not equity" bucket.
        artifact = built(candidate("ETF1", "ETF"), candidate("WAR1", "WARRANT"), candidate("RGT1", "RIGHT"),
                         candidate("BND1", "BOND"), candidate("DRV1", "DERIVATIVE"))
        rows = {row["instrument_candidate_id"]: row for row in snapshot(artifact, tiers.LISTED_EQUITY_CANDIDATE)["memberships"]}
        expected = {"candidate:ETF1": "instrument_type_etf", "candidate:WAR1": "instrument_type_warrant",
                    "candidate:RGT1": "instrument_type_right", "candidate:BND1": "instrument_type_bond",
                    "candidate:DRV1": "instrument_type_derivative"}
        for candidate_id, reason_code in expected.items():
            self.assertEqual((tiers.EXCLUDED, reason_code), (rows[candidate_id]["state"], rows[candidate_id]["reason_code"]))

    def test_unmapped_non_equity_class_falls_back_to_generic_reason(self):
        # A class string outside both the known equity/unknown/index buckets and the class-specific
        # table above must still fail closed to the generic catch-all, never be silently dropped.
        artifact = built(candidate("WEIRD", "SOME_FUTURE_CLASS"))
        row = snapshot(artifact, tiers.LISTED_EQUITY_CANDIDATE)["memberships"][0]
        self.assertEqual((tiers.EXCLUDED, "instrument_type_not_equity"), (row["state"], row["reason_code"]))

    def test_index_or_synthetic_is_not_applicable_and_marked_reserved_unqualified(self):
        artifact = built(candidate("SYN", "SYNTHETIC"))
        row = snapshot(artifact, tiers.LISTED_EQUITY_CANDIDATE)["memberships"][0]
        self.assertEqual((tiers.NOT_APPLICABLE, "index_or_synthetic_reserved_unqualified"), (row["state"], row["reason_code"]))
        self.assertEqual("unqualified", row["quality_status"])

    def test_exchange_field_absence_is_unknown_when_listing_is_otherwise_active(self):
        artifact = built(candidate("EQ", "EQUITY", listing="ACTIVE", exchange=None))
        active = snapshot(artifact, tiers.ACTIVE_UNIVERSE)["memberships"][0]
        self.assertEqual((tiers.UNKNOWN, "exchange_unknown"), (active["state"], active["reason_code"]))

    def test_membership_rows_carry_first_class_instrument_class_and_exchange(self):
        artifact = built(candidate("EQ", "EQUITY", listing="ACTIVE", exchange="HOSE"),
                         candidate("BND1", "BOND", exchange="HOSE"))
        rows = {row["instrument_candidate_id"]: row for row in snapshot(artifact, tiers.LISTED_EQUITY_CANDIDATE)["memberships"]}
        self.assertEqual({"instrument_class": "EQUITY", "exchange": "HOSE"},
                         {"instrument_class": rows["candidate:EQ"]["instrument_class"], "exchange": rows["candidate:EQ"]["exchange"]})
        self.assertEqual({"instrument_class": "BOND", "exchange": "HOSE"},
                         {"instrument_class": rows["candidate:BND1"]["instrument_class"], "exchange": rows["candidate:BND1"]["exchange"]})
        active = snapshot(artifact, tiers.ACTIVE_UNIVERSE)["memberships"]
        for row in active:
            self.assertIn("instrument_class", row)
            self.assertIn("exchange", row)

    def test_ledger_events_carry_first_class_instrument_class_and_exchange(self):
        artifact = built(candidate("BND1", "BOND", exchange="HOSE"))
        event = next(item for item in artifact["ledger_events"] if item["tier"] == tiers.LISTED_EQUITY_CANDIDATE)
        self.assertEqual("BOND", event["instrument_class"])
        self.assertEqual("HOSE", event["exchange"])

    def test_strategy_eligibility_requires_a_nonempty_tier_scope(self):
        with self.assertRaisesRegex(tiers.CanonicalUniverseTierError, "requires_tier_scope"):
            built(candidate("EQ", "EQUITY"), strategy_by_scope={"": {}})

    def test_strategy_and_feature_are_siblings_not_a_false_dependency(self):
        base = candidate("EQ", "EQUITY", listing="ACTIVE", exchange="HOSE")
        identity = "provider-identity-set:" + tiers._hash(["dnse:symbol:eq"])
        coverage = {identity: {"price_present": True, "stale": False, "price_basis_qualified": True, "volume_basis_qualified": True}}
        artifact = built(base, coverage_by_identity=coverage, feature_by_identity={identity: {"qualified": False}},
                         strategy_by_scope={"momentum/v1": {identity: {"qualified": True}}})
        self.assertEqual(tiers.EXCLUDED, snapshot(artifact, tiers.FEATURE_QUALIFIED_UNIVERSE)["memberships"][0]["state"])
        strategy = snapshot(artifact, tiers.STRATEGY_ELIGIBLE_UNIVERSE, "momentum/v1")["memberships"][0]
        self.assertEqual(tiers.INCLUDED, strategy["state"])

    def test_transition_history_is_append_only_and_continuity_survives_candidate_id_change(self):
        first = built(candidate("EQ", "EQUITY"))
        changed = candidate("EQ", "EQUITY", listing="ACTIVE", exchange="HOSE")
        changed["candidate_id"] = "candidate:EQ-after-c1-rule-change"
        second = tiers.build_universe_tier_artifact(
            c1_artifact(changed), as_of_session="2026-08-08", generated_at="2026-08-16T01:00:00+07:00",
            prior_ledger_artifact=first,
        )
        self.assertGreater(len(second["ledger_events"]), len(first["ledger_events"]))
        first_keys = {event["ledger_event_id"] for event in first["ledger_events"]}
        self.assertTrue(first_keys.issubset({event["ledger_event_id"] for event in second["ledger_events"]}))
        self.assertEqual(
            snapshot(first, tiers.ACTIVE_UNIVERSE)["memberships"][0]["instrument_identity_key"],
            snapshot(second, tiers.ACTIVE_UNIVERSE)["memberships"][0]["instrument_identity_key"],
        )

    def test_unchanged_rerun_is_deterministic_and_does_not_duplicate_ledger_events(self):
        first = built(candidate("EQ", "EQUITY"))
        second = tiers.build_universe_tier_artifact(
            c1_artifact(candidate("EQ", "EQUITY")), as_of_session="2026-08-07",
            generated_at="2026-08-16T00:00:00+07:00", prior_ledger_artifact=first,
        )
        self.assertEqual(first, second)

    def test_denominator_is_anchored_to_master_for_every_snapshot(self):
        artifact = built(candidate("EQ", "EQUITY"), candidate("UNKNOWN", "UNKNOWN_SECURITY_GROUP"), candidate("IDX", "INDEX"))
        for item in artifact["snapshots"]:
            self.assertEqual(3, item["total_count"])
            self.assertEqual(item["total_count"], item["included_count"] + item["excluded_count"] + item["unknown_count"] + item["not_applicable_count"])

    def test_tier_version_session_scope_identity_is_explicit_and_comparability_is_fail_closed(self):
        artifact = built(candidate("EQ", "EQUITY"), strategy_by_scope={"lane/a": {}})
        active = snapshot(artifact, tiers.ACTIVE_UNIVERSE)
        strategy = snapshot(artifact, tiers.STRATEGY_ELIGIBLE_UNIVERSE, "lane/a")
        for item in (active, strategy):
            for key in ("universe_tier", "universe_version", "source_c1_artifact_id", "as_of_session", "generated_at"):
                self.assertIn(key, item)
        self.assertFalse(tiers.snapshots_comparable(active, strategy))
        self.assertTrue(tiers.snapshots_comparable(active, copy.deepcopy(active)))

    def test_arbitrary_legacy_ticker_list_cannot_masquerade_as_c1(self):
        with self.assertRaisesRegex(tiers.CanonicalUniverseTierError, "c1_artifact_not_a_mapping"):
            tiers.build_universe_tier_artifact(["HPG", "VNM"], as_of_session="2026-08-07", generated_at="x")

    def test_core_never_opens_network_or_database_and_adapter_writes_only_explicit_output(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network prohibited")), \
             patch.object(sqlite3, "connect", side_effect=AssertionError("database prohibited")):
            artifact = built(candidate("EQ", "EQUITY"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = tiers.write_artifact(root, artifact)
            self.assertTrue(Path(written["path"]).is_file())
            self.assertIn("data\\canonical_universe_tiers\\artifacts", written["path"])

    def test_prior_ledger_must_be_a_canonical_artifact(self):
        with self.assertRaisesRegex(tiers.CanonicalUniverseTierError, "prior_ledger_not_a_canonical"):
            built(candidate("EQ", "EQUITY"), prior_ledger_artifact={"ledger_events": []})


if __name__ == "__main__":
    unittest.main()
