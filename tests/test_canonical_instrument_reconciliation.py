from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path

import canonical_instrument_reconciliation as reconciliation


def dnse(symbol: str, **overrides):
    record = {"symbol": symbol, "provider_identity": f"dnse:symbol:{symbol.casefold()}", "exchange_raw": "STO",
              "instrument_class": "EQUITY", "listing_status": "unknown_not_provided_by_dataset",
              "name": "DNSE Name", "discovered_at": "2026-08-11T10:00:00+07:00",
              "raw_record_json": json.dumps({"symbol": symbol, "marketId": "STO"})}
    record.update(overrides)
    return record


def vci(symbol: str, **overrides):
    record = {"symbol": symbol, "provider_identity": f"vci:symbol:{symbol.casefold()}", "exchange": "HOSE",
              "instrument_type": "STOCK", "fetched_at": "2026-08-11T10:00:00+07:00",
              "raw_record": {"symbol": symbol, "exchange": "HOSE"}}
    record.update(overrides)
    return record


def company_profile(symbol: str, **overrides):
    record = {"source_name": "FIREANT", "fetched_at": "2026-08-11T10:00:00+07:00",
              "qualified_fields": {"symbol": symbol, "organ_name": "Profile Name", "exchange": "HOSE",
                                    "instrument_type": "STOCK"}}
    record.update(overrides)
    return record


class CanonicalInstrumentReconciliationTests(unittest.TestCase):
    def test_exact_symbol_is_provisional_not_authoritative_match(self):
        result = reconciliation.reconcile({"DNSE": [dnse("HPG")], "VCI": [vci("HPG")]})
        link = result["instrument_identity_links"][0]
        self.assertEqual(reconciliation.PROVISIONAL_MATCH, link["resolution_state"])
        self.assertNotEqual(reconciliation.QUALIFIED_MATCH, link["resolution_state"])
        self.assertEqual(["dnse:symbol:hpg", "vci:symbol:hpg"], link["provider_identities"])

    def test_dnse_only_instrument_is_retained(self):
        result = reconciliation.reconcile({"DNSE": [dnse("ONLY")], "VCI": []})
        self.assertEqual(1, len(result["canonical_instrument_candidates"]))
        self.assertEqual(reconciliation.UNRESOLVED, result["canonical_instrument_candidates"][0]["resolution_state"])

    def test_unknown_security_group_remains_unknown(self):
        result = reconciliation.reconcile({"DNSE": [dnse("CW1", instrument_class="UNKNOWN_SECURITY_GROUP")], "VCI": []})
        fields = result["canonical_instrument_field_observations"]
        observed = next(row for row in fields if row["field"] == "instrument_class")
        self.assertEqual("UNKNOWN_SECURITY_GROUP", observed["raw_value"])

    def test_missing_listing_status_never_becomes_active(self):
        result = reconciliation.reconcile({"DNSE": [dnse("HPG")], "VCI": [vci("HPG")]})
        selected = result["canonical_instrument_candidates"][0]["selected_fields"]["listing_status"]
        self.assertEqual(reconciliation.LISTING_UNKNOWN, selected["value"])

    def test_legacy_delisted_marker_remains_raw_unqualified_listing_observation(self):
        result = reconciliation.reconcile({"DNSE": [], "LEGACY": [{"ticker": "OLD", "listing_status": "DELISTED"}]})
        candidate = result["canonical_instrument_candidates"][0]
        listing = next(row for row in result["canonical_instrument_field_observations"] if row["field"] == "listing_status")
        self.assertEqual("DELISTED", listing["raw_value"])
        self.assertEqual("unavailable_or_unqualified", listing["semantic_status"])
        self.assertEqual(reconciliation.LISTING_UNKNOWN, candidate["selected_fields"]["listing_status"]["value"])

    def test_missing_in_one_source_is_absence_not_conflict(self):
        result = reconciliation.reconcile({"DNSE": [dnse("HPG")], "VCI": []})
        self.assertEqual([], result["canonical_instrument_conflicts"])

    def test_true_disagreement_creates_explicit_conflict(self):
        result = reconciliation.reconcile({"DNSE": [dnse("HPG", name="Alpha")], "VCI": [vci("HPG", organ_name="Beta")]})
        self.assertEqual(1, len(result["canonical_instrument_conflicts"]))
        self.assertEqual("name", result["canonical_instrument_conflicts"][0]["field"])
        self.assertEqual(reconciliation.CONFLICT, result["canonical_instrument_candidates"][0]["resolution_state"])

    def test_raw_provider_observations_are_preserved(self):
        raw = {"symbol": "HPG", "marketId": "STO", "opaque": {"retained": True}}
        result = reconciliation.reconcile({"DNSE": [dnse("HPG", raw_record_json=json.dumps(raw))], "VCI": []})
        self.assertEqual(raw, result["provider_instrument_identities"][0]["raw_record"])

    def test_unsupported_exchange_mapping_stays_unknown(self):
        result = reconciliation.reconcile({"DNSE": [dnse("HPG", exchange_raw="STO")], "VCI": []})
        exchange = next(row for row in result["canonical_instrument_field_observations"] if row["field"] == "exchange")
        self.assertEqual("STO", exchange["raw_value"])
        self.assertIsNone(exchange["normalized_value"])
        self.assertEqual("provider_raw_only_mapping_unknown", exchange["semantic_status"])

    def test_company_profile_instrument_class_uses_nested_qualified_fields(self):
        result = reconciliation.reconcile({"COMPANY_PROFILE": [company_profile("HPG")]})
        observed = next(row for row in result["canonical_instrument_field_observations"] if row["field"] == "instrument_class")
        self.assertEqual("STOCK", observed["raw_value"])
        self.assertEqual("provider_raw_only_mapping_unknown", observed["semantic_status"])

    def test_company_profile_never_reads_a_top_level_instrument_type(self):
        # A COMPANY_PROFILE record's every field lives under qualified_fields (see name/exchange
        # in the same function); a stray top-level instrument_type must never leak through.
        record = company_profile("HPG")
        record["instrument_type"] = "SHOULD_NOT_BE_READ"
        del record["qualified_fields"]["instrument_type"]
        result = reconciliation.reconcile({"COMPANY_PROFILE": [record]})
        observed = next(row for row in result["canonical_instrument_field_observations"] if row["field"] == "instrument_class")
        self.assertIsNone(observed["raw_value"])
        self.assertEqual("missing", observed["semantic_status"])

    def test_rerun_has_identical_logical_identities_and_content_hash(self):
        source = {"DNSE": [dnse("HPG"), dnse("VNM")], "VCI": [vci("HPG")]}
        first = reconciliation.reconcile(source)
        second = reconciliation.reconcile({"VCI": [vci("HPG")], "DNSE": [dnse("VNM"), dnse("HPG")]})
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(first["artifact_id"], second["artifact_id"])

    def test_output_does_not_write_vn_stock_db(self):
        result = reconciliation.reconcile({"DNSE": [dnse("HPG")], "VCI": []})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "vn_stock.db"
            db.write_bytes(b"legacy-db-bytes")
            reconciliation.write_artifact(root, result)
            self.assertEqual(b"legacy-db-bytes", db.read_bytes())
            self.assertTrue((root / reconciliation.STORE_RELATIVE / f"{result['content_hash']}.json").is_file())

    def test_builder_fails_closed_for_missing_required_retained_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-dnse.json"
            with self.assertRaisesRegex(reconciliation.CanonicalInstrumentReconciliationError, "required_retained_input_missing:dnse"):
                reconciliation.build_from_retained_files(dnse_input=missing, output_root=tmp)

    def test_builder_accepts_a_dnse_only_retained_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "dnse.json"
            source.write_text(json.dumps({"records": [dnse("HPG")]}), encoding="utf-8")
            built = reconciliation.build_from_retained_files(dnse_input=source, output_root=root)
            self.assertEqual(reconciliation.UNRESOLVED, built["result"]["canonical_instrument_candidates"][0]["resolution_state"])
            self.assertTrue(Path(built["artifact"]["path"]).is_file())

    def test_reconciliation_requires_no_network_access(self):
        original = socket.create_connection
        try:
            socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called"))
            result = reconciliation.reconcile({"DNSE": [dnse("HPG")], "VCI": [vci("HPG")]})
        finally:
            socket.create_connection = original
        self.assertEqual(2, len(result["provider_instrument_identities"]))


if __name__ == "__main__":
    unittest.main()
