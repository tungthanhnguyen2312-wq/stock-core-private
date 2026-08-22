from __future__ import annotations

import unittest

import market_capability_taxonomy as taxonomy


# The owner-specified field list, transcribed independently of SEMANTIC_FIELDS so this test
# actually validates the module against the milestone spec rather than against itself.
_REQUIRED_FIELDS = {
    "PRICE": {"OPEN_KVND", "HIGH_KVND", "LOW_KVND", "CLOSE_KVND",
              "OPEN_VND", "HIGH_VND", "LOW_VND", "CLOSE_VND"},
    "VOLUME": {"MATCHED_VOLUME_SHARES", "PUT_THROUGH_VOLUME_SHARES", "TOTAL_VOLUME_SHARES"},
    "TRADED_VALUE": {"MATCHED_TRADED_VALUE_VND", "PUT_THROUGH_TRADED_VALUE_VND", "TOTAL_TRADED_VALUE_VND"},
    "FOREIGN": {"FOREIGN_BUY_VOLUME", "FOREIGN_SELL_VOLUME", "FOREIGN_NET_VOLUME",
                "FOREIGN_BUY_VALUE", "FOREIGN_SELL_VALUE", "FOREIGN_NET_VALUE",
                "FOREIGN_ROOM_MAX", "FOREIGN_ROOM_OWNED", "FOREIGN_ROOM_AVAILABLE"},
    "PROPRIETARY": {"PROPRIETARY_BUY_VOLUME", "PROPRIETARY_SELL_VOLUME", "PROPRIETARY_NET_VOLUME",
                    "PROPRIETARY_BUY_VALUE", "PROPRIETARY_SELL_VALUE", "PROPRIETARY_NET_VALUE"},
    "MICROSTRUCTURE": {"ACTIVE_BUY_ORDER_COUNT", "ACTIVE_SELL_ORDER_COUNT",
                       "ACTIVE_BUY_VOLUME", "ACTIVE_SELL_VOLUME", "ACTIVE_NET_VOLUME"},
    "REFERENCE": {"SYMBOL", "EXCHANGE", "LISTED_SHARES", "OUTSTANDING_SHARES", "FREE_FLOAT"},
}


class SchemaCompletenessTests(unittest.TestCase):
    def test_every_owner_specified_field_is_declared(self):
        for family, fields in _REQUIRED_FIELDS.items():
            with self.subTest(family=family):
                self.assertTrue(fields.issubset(set(taxonomy.SEMANTIC_FIELDS[family])))

    def test_proprietary_and_microstructure_families_are_declared(self):
        self.assertEqual(6, len(taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_PROPRIETARY]))
        self.assertTrue(5 <= len(taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_MICROSTRUCTURE]))

    def test_family_of_resolves_every_declared_identity(self):
        for identity in taxonomy.ALL_SEMANTIC_IDENTITIES:
            self.assertIsNotNone(taxonomy.family_of(identity))

    def test_family_of_unknown_identity_is_none(self):
        self.assertIsNone(taxonomy.family_of("NOT_A_REAL_FIELD"))


class SingleAndMultiSourceTests(unittest.TestCase):
    def test_one_source_only_capability_is_representable(self):
        # DNSE's OHLC endpoint has no put-through figure; only FHSC documents one.
        self.assertTrue(taxonomy.is_single_source_capability("PUT_THROUGH_VOLUME_SHARES"))
        self.assertEqual(("FHSC",), taxonomy.source_candidates("PUT_THROUGH_VOLUME_SHARES"))
        record = taxonomy.capability("PUT_THROUGH_VOLUME_SHARES", "FHSC")
        self.assertNotEqual(taxonomy.MISSING, record["usability_state"])

    def test_multi_source_capability_is_representable(self):
        sources = taxonomy.source_candidates("OPEN_KVND")
        self.assertEqual({"DNSE", "FHSC"}, set(sources))

    def test_overlap_is_supported_but_not_mandatory(self):
        # Must not raise: at least one source per multi-source identity stands on its own.
        taxonomy.assert_overlap_not_mandatory()
        dnse_only = taxonomy.capability("OPEN_KVND", "DNSE")
        self.assertEqual(taxonomy.RESEARCH_USABLE, dnse_only["usability_state"])
        # FHSC's own weaker verdict does not drag DNSE's down, and vice versa.
        fhsc_only = taxonomy.capability("OPEN_KVND", "FHSC")
        self.assertEqual(taxonomy.SEMANTIC_UNRESOLVED, fhsc_only["usability_state"])


class MissingDimensionIsolationTests(unittest.TestCase):
    def test_missing_family_does_not_affect_unrelated_family(self):
        proprietary_dnse = [r for r in taxonomy.capabilities_for_family(taxonomy.FAMILY_PROPRIETARY) if r["source"] == "DNSE"]
        self.assertTrue(all(r["usability_state"] == taxonomy.MISSING for r in proprietary_dnse))
        price_dnse = taxonomy.capability("CLOSE_KVND", "DNSE")
        self.assertEqual(taxonomy.RESEARCH_USABLE, price_dnse["usability_state"])

    def test_unresolved_room_fields_do_not_affect_flow_fields(self):
        room = taxonomy.capability("FOREIGN_ROOM_AVAILABLE", "DNSE")
        self.assertEqual(taxonomy.SEMANTIC_UNRESOLVED, room["usability_state"])
        flow = taxonomy.capability("FOREIGN_NET_VOLUME", "DNSE")
        self.assertEqual(taxonomy.RESEARCH_USABLE, flow["usability_state"])

    def test_traded_value_missing_does_not_affect_volume(self):
        for identity in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_TRADED_VALUE]:
            self.assertEqual(taxonomy.MISSING, taxonomy.capability(identity, "DNSE")["usability_state"])
        matched = taxonomy.capability("MATCHED_VOLUME_SHARES", "DNSE")
        self.assertNotEqual(taxonomy.MISSING, matched["usability_state"])


class NoAuthorityPromotionTests(unittest.TestCase):
    def test_registry_is_fail_closed(self):
        taxonomy.assert_registry_fail_closed()

    def test_every_record_has_none_authority_effect(self):
        for record in taxonomy.CAPABILITY_REGISTRY:
            self.assertEqual("NONE", record["authority_effect"])

    def test_snapshot_reports_no_liquidity_or_raw_as_traded_authority(self):
        snap = taxonomy.snapshot()
        self.assertFalse(snap["liquidity_actionable"])
        self.assertFalse(snap["raw_as_traded_actionable"])


class FailClosedLookupTests(unittest.TestCase):
    def test_unknown_identity_raises(self):
        with self.assertRaises(taxonomy.CapabilityRegistryError):
            taxonomy.capabilities_for("NOT_A_FIELD")

    def test_unknown_source_raises(self):
        with self.assertRaises(taxonomy.CapabilityRegistryError):
            taxonomy.capability("OPEN_KVND", "NOT_A_SOURCE")

    def test_no_record_for_source_raises_rather_than_defaulting(self):
        with self.assertRaises(taxonomy.CapabilityRegistryError):
            taxonomy.capability("OPEN_KVND", "OFFICIAL")

    def test_unknown_family_raises(self):
        with self.assertRaises(taxonomy.CapabilityRegistryError):
            taxonomy.capabilities_for_family("NOT_A_FAMILY")


class DerivedVndRecordTests(unittest.TestCase):
    def test_vnd_record_points_back_to_its_kvnd_source(self):
        derived = taxonomy.capability("CLOSE_VND", "DERIVED_CANONICAL")
        self.assertEqual("CLOSE_KVND", derived["derived_from"])
        self.assertIsNone(derived["provider_native_representation"])

    def test_kvnd_record_points_forward_to_its_vnd_canonical(self):
        native = taxonomy.capability("CLOSE_KVND", "DNSE")
        self.assertEqual(
            "CLOSE_VND", native["canonical_representation"]["derived_identity"],
        )


class SnapshotTests(unittest.TestCase):
    def test_snapshot_record_count_matches_registry(self):
        snap = taxonomy.snapshot()
        self.assertEqual(len(taxonomy.CAPABILITY_REGISTRY), snap["record_count"])
        self.assertEqual(
            snap["record_count"], sum(snap["record_count_by_usability_state"].values())
        )

    def test_snapshot_is_deterministic(self):
        self.assertEqual(taxonomy.snapshot(), taxonomy.snapshot())


if __name__ == "__main__":
    unittest.main()
