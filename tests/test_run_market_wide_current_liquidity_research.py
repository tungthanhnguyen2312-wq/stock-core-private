"""Tests for tools/run_market_wide_current_liquidity_research.py's consolidate() step.

Regression coverage for a fixed hash-scope defect: build_artifact() stamps
artifact_sha256/artifact_identity before consolidate() adds resolved_completed_session and
universe.source_snapshot_identity, so the originally recorded hash on the retained 2026-08-23
checkpoint covered a strict subset of its own persisted payload (confirmed by recomputing
market_wide_current_liquidity_research.content_identity() against the file on disk). consolidate()
now re-stamps identity over the complete final dict; these tests assert that contract and that it
does not silently degrade back into a no-op (a hash that ignored the post-hoc fields would still
"match" a tampered copy of them).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from market_wide_current_liquidity_research import content_identity
from tools.run_market_wide_current_liquidity_research import consolidate


def _trade() -> dict:
    return {"ok": True, "body": {"trades": [
        {"boardId": "G1", "time": "2026-08-21 14:59:00", "matchPrice": 1, "matchQtty": 1,
         "avgPrice": 1, "totalVolumeTraded": 10, "grossTradeAmount": 1},
    ]}}


def _ohlc() -> dict:
    return {"ok": True, "body": {"t": [1787328000], "v": [100]}}


class ConsolidateIdentityCompletenessTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshot_path = self.root / "snapshot.json"
        self.snapshot_path.write_text(
            json.dumps({"snapshot_identity": "test_snapshot:abc123", "records": ["AAA"]}),
            encoding="utf-8",
        )
        self.out = self.root / "out"
        (self.out / "batches").mkdir(parents=True)
        (self.out / "batches" / "batch-000.json").write_text(
            json.dumps({
                "snapshot_identity": "test_snapshot:abc123", "session": "2026-08-21",
                "symbols": ["AAA"], "trades": {"AAA": _trade()}, "ohlc": {"AAA": _ohlc()},
            }),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _consolidated_artifact(self) -> dict:
        consolidate(self.snapshot_path, self.out, "2026-08-21")
        return json.loads(
            (self.out / "market_wide_current_liquidity_research_artifact.json").read_text(encoding="utf-8")
        )

    def test_recorded_hash_covers_the_complete_persisted_payload(self) -> None:
        artifact = self._consolidated_artifact()
        self.assertEqual("2026-08-21", artifact["resolved_completed_session"])
        self.assertEqual("test_snapshot:abc123", artifact["universe"]["source_snapshot_identity"])
        recomputed = content_identity(artifact)
        self.assertEqual(recomputed["artifact_sha256"], artifact["artifact_sha256"])
        self.assertEqual(recomputed["artifact_identity"], artifact["artifact_identity"])

    def test_hash_actually_depends_on_the_post_hoc_fields(self) -> None:
        artifact = self._consolidated_artifact()
        tampered = dict(artifact)
        tampered["resolved_completed_session"] = "2026-08-22"
        recomputed = content_identity(tampered)
        self.assertNotEqual(recomputed["artifact_sha256"], artifact["artifact_sha256"])

    def test_retained_2026_08_23_checkpoint_now_self_verifies(self) -> None:
        """The actual retained checkpoint this milestone integrates -- not a synthetic
        fixture -- must reproduce its own recorded hash after the consolidate() fix."""
        path = (
            Path(__file__).resolve().parents[1] / "operations-review"
            / "market-wide-current-liquidity-research-v1-20260823-resumable"
            / "market_wide_current_liquidity_research_artifact.json"
        )
        if not path.exists():
            self.skipTest("retained checkpoint artifact not present in this environment")
        artifact = json.loads(path.read_text(encoding="utf-8"))
        recomputed = content_identity(artifact)
        self.assertEqual(recomputed["artifact_sha256"], artifact["artifact_sha256"])


if __name__ == "__main__":
    unittest.main()
