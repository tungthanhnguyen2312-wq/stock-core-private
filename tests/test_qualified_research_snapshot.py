import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from qualified_research_snapshot import (
    SnapshotCollisionError, SnapshotIntegrityError, _canonical, retain, replay,
    snapshot_as_bundle, validate_snapshot,
)
from tests.test_qualified_research_delta import brief


def source_bundle(root: Path, briefs=None):
    root.mkdir(parents=True, exist_ok=True)
    briefs = briefs or {ticker: brief(ticker, "bank" if ticker == "VCB" else "corporate") for ticker in ("HPG", "VNM", "VCB")}
    bundle = {"tickers": {ticker: {"qualified_research_brief": payload} for ticker, payload in briefs.items()}}
    bundle_path = root / "analysis_bundle.json"
    bundle_path.write_bytes(_canonical(bundle))
    import hashlib
    manifest = {"schema_version": "1.1.0", "trusted_subset": {"bundle_filename": "analysis_bundle.json", "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest()}}
    manifest_path = root / "bundle_manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    return bundle_path, manifest_path


class QualifiedResearchSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.bundle, self.manifest = source_bundle(self.root)
        self.store = self.root / "snapshots"

    def tearDown(self):
        self.tmp.cleanup()

    def retained(self):
        return retain(self.bundle, self.manifest, self.store)

    def test_retention_is_content_addressed_deterministic_and_idempotent(self):
        first = self.retained()
        os.utime(self.bundle, None); os.utime(self.manifest, None)
        second = self.retained()
        self.assertEqual(first["status"], "snapshot_retained")
        self.assertEqual(second["status"], "snapshot_already_retained")
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertRegex(first["snapshot_id"], r"^qrs-[0-9a-f]{64}$")

    def test_manifest_is_last_and_validator_hash_binds_every_brief(self):
        result = self.retained(); directory = self.store / result["snapshot_id"]
        self.assertTrue((directory / "snapshot_manifest.json").is_file())
        validated = validate_snapshot(self.store, result["snapshot_id"])
        self.assertEqual(validated["captured_tickers"], ["HPG", "VCB", "VNM"])
        self.assertEqual([x["ticker"] for x in validated["briefs"]], ["HPG", "VCB", "VNM"])

    def test_tamper_and_path_traversal_are_rejected(self):
        result = self.retained(); path = self.store / result["snapshot_id"] / "HPG.qualified_research_brief.json"
        path.write_text('{"ticker":"HPG"}', encoding="utf-8")
        with self.assertRaises(SnapshotIntegrityError): validate_snapshot(self.store, result["snapshot_id"])
        with self.assertRaises(SnapshotIntegrityError): validate_snapshot(self.store, "../not-a-snapshot")

    def test_incomplete_existing_snapshot_is_collision_not_repaired(self):
        source = self.retained(); directory = self.store / source["snapshot_id"]
        (directory / "snapshot_manifest.json").unlink()
        with self.assertRaises(SnapshotCollisionError): self.retained()

    def test_missing_or_malformed_brief_fails_closed(self):
        bundle = json.loads(self.bundle.read_text()); del bundle["tickers"]["VNM"]["qualified_research_brief"]
        self.bundle.write_bytes(_canonical(bundle)); source_bundle_manifest = {"schema_version":"1.1.0","trusted_subset":{"bundle_filename":"analysis_bundle.json","bundle_sha256":__import__('hashlib').sha256(self.bundle.read_bytes()).hexdigest()}}
        self.manifest.write_bytes(_canonical(source_bundle_manifest))
        with self.assertRaisesRegex(SnapshotIntegrityError, "qualified_research_brief_missing:VNM"): self.retained()
        bundle["tickers"]["VNM"]["qualified_research_brief"] = {"ticker":"VNM"}; self.bundle.write_bytes(_canonical(bundle)); source_bundle_manifest["trusted_subset"]["bundle_sha256"] = __import__('hashlib').sha256(self.bundle.read_bytes()).hexdigest(); self.manifest.write_bytes(_canonical(source_bundle_manifest))
        with self.assertRaisesRegex(SnapshotIntegrityError, "brief_contract_invalid:VNM"): self.retained()

    def test_snapshot_preserves_zero_null_and_vcb_bank_not_applicable(self):
        payload = snapshot_as_bundle(self.store, self.retained()["snapshot_id"])
        self.assertEqual(payload["tickers"]["HPG"]["qualified_research_brief"]["qualified_facts"][0]["value"], 0)
        vcb = payload["tickers"]["VCB"]["qualified_research_brief"]
        self.assertEqual(vcb["entity_type"], "bank")
        self.assertEqual(vcb["quality"]["capital_structure"]["status"], "not_applicable")

    def test_replay_requires_explicit_valid_id_and_reuses_phase_5d(self):
        result = self.retained()
        with self.assertRaises(SnapshotIntegrityError): replay(self.store, "", self.bundle, self.manifest)
        replayed = replay(self.store, result["snapshot_id"], self.bundle, self.manifest)
        self.assertEqual(sorted(replayed["deltas"]), ["HPG", "VCB", "VNM"])
        self.assertTrue(all(x["comparison_status"] == "comparable" for x in replayed["deltas"].values()))
        self.assertTrue(all(not x["material_change_summary"]["material_change_detected"] for x in replayed["deltas"].values()))

    def test_changed_current_fixture_detects_phase_5d_delta_without_archive_write(self):
        result = self.retained(); changed = json.loads(self.bundle.read_text())
        changed["tickers"]["HPG"]["qualified_research_brief"]["qualified_facts"][0]["value"] = 9
        changed_bundle, changed_manifest = source_bundle(self.root / "changed", {ticker: payload["qualified_research_brief"] for ticker, payload in changed["tickers"].items()})
        replayed = replay(self.store, result["snapshot_id"], changed_bundle, changed_manifest)
        self.assertTrue(replayed["deltas"]["HPG"]["material_change_summary"]["material_change_detected"])
        self.assertIn("changed", [x["status"] for x in replayed["deltas"]["HPG"]["fact_changes"]])

    def test_source_manifest_must_bind_explicit_bundle(self):
        manifest = json.loads(self.manifest.read_text()); manifest["trusted_subset"]["bundle_sha256"] = "0" * 64; self.manifest.write_bytes(_canonical(manifest))
        with self.assertRaisesRegex(SnapshotIntegrityError, "source_manifest_bundle_hash_mismatch"): self.retained()
