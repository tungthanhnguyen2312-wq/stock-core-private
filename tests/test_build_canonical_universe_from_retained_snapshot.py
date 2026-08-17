from __future__ import annotations

import json
import socket
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_canonical_universe_from_retained_snapshot import (  # noqa: E402
    RetainedSnapshotIntegrationError, build_from_retained_snapshot,
)
import dnse_instrument_universe as universe  # noqa: E402


def _raw_instrument(symbol: str, security_group_id: str, *, market_id: str = "STO") -> dict:
    """Shaped exactly like one row of a real DNSE /market/instruments response."""
    return {"symbol": symbol, "securityGroupId": security_group_id, "marketId": market_id,
            "name": f"{symbol} Co", "shortName": symbol, "symbolType": "STOCK", "listedDate": "",
            "indexName": None}


def _write_snapshot(tmp: Path, raw_records: list[dict], *, retrieved_at: str = "2026-08-12T10:51:45+07:00"):
    """Build a retained snapshot Parquet + manifest exactly as
    tools/discover_market_universe.py would, reusing the real production classifier
    (dnse_instrument_universe) end to end -- never a hand-rolled record shape."""
    normalized = [universe.normalize_instrument_record(raw, retrieved_at=retrieved_at, page=1) for raw in raw_records]
    discovery = universe._assemble_result(
        status="COMPLETE", records=normalized, pages_fetched=[{"page": 1, "ok": True}],
        malformed=[], duplicate_identities=[], declared_total=len(normalized),
        retrieved_at=retrieved_at, page_size=100,
    )
    manifest = universe.snapshot_manifest(discovery)
    frame = universe.build_snapshot_frame(normalized)
    snapshot_path = tmp / f"{manifest['snapshot_id']}.parquet"
    frame.to_parquet(snapshot_path, index=False)
    manifest_path = tmp / f"{manifest['snapshot_id']}.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return snapshot_path, manifest_path, manifest


class BuildCanonicalUniverseFromRetainedSnapshotTests(unittest.TestCase):
    def test_end_to_end_reproduces_exact_split_for_this_snapshot(self):
        raw = [_raw_instrument("EQ1", "ST"), _raw_instrument("EQ2", "ST"), _raw_instrument("EQ3", "ST"),
               _raw_instrument("UNK1", "XX"), _raw_instrument("UNK2", "FU")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, manifest_path, _ = _write_snapshot(root, raw)
            built = build_from_retained_snapshot(
                dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=manifest_path,
                output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00",
            )
            summary = built["result"]["reconciliation_summary"]
            self.assertEqual(5, summary["master_observed"]["total"])
            self.assertEqual(
                {"included": 3, "excluded": 0, "unknown": 2, "not_applicable": 0, "total": 5,
                 "excluded_by_reason": {}, "unknown_by_reason": {"instrument_type_unknown": 2}},
                summary["listed_equity_candidate"],
            )
            # Fail-closed by design: no listing-status/exchange evidence exists for this or any
            # other snapshot yet, so every instrument -- including the 3 EQUITY ones -- stays
            # ACTIVE_UNIVERSE=UNKNOWN. This is the expected result, not a bug to patch around.
            self.assertEqual(0, summary["active_universe"]["included"])
            self.assertEqual(5, summary["active_universe"]["unknown"])
            self.assertEqual(0, summary["active_universe"]["excluded"])

    def test_provenance_is_bound_to_the_exact_snapshot(self):
        raw = [_raw_instrument("EQ1", "ST")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, manifest_path, manifest = _write_snapshot(root, raw)
            built = build_from_retained_snapshot(
                dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=manifest_path,
                output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00",
            )
            provenance = built["result"]["source_snapshot_provenance"]
            self.assertEqual(str(snapshot_path), provenance["snapshot_path"])
            self.assertEqual(manifest["snapshot_id"], provenance["snapshot_id"])
            self.assertEqual(manifest["content_hash"], provenance["content_hash"])
            self.assertEqual(manifest["retrieved_at"], provenance["retrieved_at"])
            self.assertEqual(manifest["by_instrument_class"], provenance["by_instrument_class"])

    def test_row_count_mismatch_against_manifest_fails_closed(self):
        raw = [_raw_instrument("EQ1", "ST"), _raw_instrument("EQ2", "ST")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, manifest_path, manifest = _write_snapshot(root, raw)
            tampered = dict(manifest)
            tampered["discovered_count"] = 999
            manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(RetainedSnapshotIntegrationError,
                                        "snapshot_row_count_does_not_match_manifest"):
                build_from_retained_snapshot(
                    dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=manifest_path,
                    output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00",
                )

    def test_missing_manifest_fails_closed(self):
        raw = [_raw_instrument("EQ1", "ST")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, _manifest_path, _manifest = _write_snapshot(root, raw)
            missing_manifest = root / "missing.manifest.json"
            with self.assertRaisesRegex(RetainedSnapshotIntegrationError, "required_retained_input_missing"):
                build_from_retained_snapshot(
                    dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=missing_manifest,
                    output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00",
                )

    def test_non_dnse_instruments_manifest_is_rejected(self):
        raw = [_raw_instrument("EQ1", "ST")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, manifest_path, manifest = _write_snapshot(root, raw)
            wrong = dict(manifest)
            wrong["dataset"] = "trades"
            manifest_path.write_text(json.dumps(wrong), encoding="utf-8")
            with self.assertRaisesRegex(RetainedSnapshotIntegrationError,
                                        "snapshot_manifest_not_a_dnse_instruments_snapshot"):
                build_from_retained_snapshot(
                    dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=manifest_path,
                    output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00",
                )

    def test_rerun_is_deterministic_and_content_addressed(self):
        raw = [_raw_instrument("EQ1", "ST"), _raw_instrument("UNK1", "XX")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, manifest_path, _ = _write_snapshot(root, raw)
            kwargs = dict(dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=manifest_path,
                          output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00")
            first = build_from_retained_snapshot(**kwargs)
            second = build_from_retained_snapshot(**kwargs)
            self.assertEqual(first["result"]["content_hash"], second["result"]["content_hash"])
            self.assertEqual(first["result"]["artifact_id"], second["result"]["artifact_id"])
            self.assertTrue(first["artifact"]["written"])
            self.assertFalse(second["artifact"]["written"])
            self.assertTrue(Path(second["artifact"]["path"]).is_file())

    def test_no_hardcoded_universe_size_a_differently_sized_snapshot_scales_correctly(self):
        # This adapter must not assume 3,250/1,660/1,590 anywhere -- those are facts about one
        # specific retained snapshot under review, never a permanent architecture constant.
        raw = [_raw_instrument(f"EQ{i}", "ST") for i in range(7)] + [_raw_instrument("UNK1", "XX")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, manifest_path, _ = _write_snapshot(root, raw)
            built = build_from_retained_snapshot(
                dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=manifest_path,
                output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00",
            )
            summary = built["result"]["reconciliation_summary"]
            self.assertEqual(8, summary["master_observed"]["total"])
            self.assertEqual(7, summary["listed_equity_candidate"]["included"])
            self.assertEqual(1, summary["listed_equity_candidate"]["unknown"])

    def test_no_network_or_database_access(self):
        raw = [_raw_instrument("EQ1", "ST")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path, manifest_path, _ = _write_snapshot(root, raw)
            with patch.object(socket, "create_connection", side_effect=AssertionError("network prohibited")), \
                 patch.object(sqlite3, "connect", side_effect=AssertionError("database prohibited")):
                built = build_from_retained_snapshot(
                    dnse_universe_snapshot=snapshot_path, dnse_universe_manifest=manifest_path,
                    output_root=root, as_of_session="2026-08-17", generated_at="2026-08-17T13:00:00+07:00",
                )
            self.assertEqual(1, built["result"]["reconciliation_summary"]["master_observed"]["total"])


# operations-review/ is this workspace's local, machine-specific, non-git-tracked evidence
# directory (see AGENTS.md: "Put machine-specific procedures in local operator documentation").
# The retained real DNSE security-master snapshot this milestone reconciled against lives there,
# not in this repository, so this one test skips cleanly (never fails) wherever that exact evidence
# file is absent -- a fresh clone, CI, or a different operator's machine. It is a best-effort
# regression check for the exact snapshot this review already verified by hand, not a portability
# guarantee, and the synthetic tests above are the ones that must always run.
REAL_RETAINED_SNAPSHOT = Path(
    r"C:\Projects\StockLookup\operations-review\dnse-market-data-lake-v2-20260812\data\market_raw_lake"
    r"\universe\5c61b853c6f806e7120c56646b2af64e241aa26e70cccd37b9ddf1288258c4d4.parquet"
)
REAL_RETAINED_MANIFEST = REAL_RETAINED_SNAPSHOT.with_suffix("").with_suffix(".manifest.json")


class RealRetainedSnapshotReconciliationTest(unittest.TestCase):
    def test_3250_denominator_and_1660_1590_split_for_the_reviewed_snapshot(self):
        if not (REAL_RETAINED_SNAPSHOT.is_file() and REAL_RETAINED_MANIFEST.is_file()):
            self.skipTest(f"real retained snapshot not present on this machine: {REAL_RETAINED_SNAPSHOT}")
        with tempfile.TemporaryDirectory() as tmp:
            built = build_from_retained_snapshot(
                dnse_universe_snapshot=REAL_RETAINED_SNAPSHOT, dnse_universe_manifest=REAL_RETAINED_MANIFEST,
                output_root=Path(tmp), as_of_session="2026-08-12", generated_at="2026-08-17T13:00:00+07:00",
            )
            summary = built["result"]["reconciliation_summary"]
            self.assertEqual(3250, summary["master_observed"]["total"])
            self.assertEqual(
                {"included": 1660, "excluded": 0, "unknown": 1590, "not_applicable": 0, "total": 3250,
                 "excluded_by_reason": {}, "unknown_by_reason": {"instrument_type_unknown": 1590}},
                summary["listed_equity_candidate"],
            )
            self.assertEqual(0, summary["active_universe"]["included"])
            self.assertEqual(3250, summary["active_universe"]["unknown"])


if __name__ == "__main__":
    unittest.main()
