"""Producer serialization boundary for the retained C2 correlation context."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from correlation_concentration_guard import content_identity
from export_ai_bundle import (
    attach_correlation_concentration_guard,
    load_correlation_concentration_guard_artifact,
)


ROOT = Path(__file__).resolve().parents[1]
C2_PATH = ROOT / "operations-review" / "correlation-concentration-guard-v1-20260829" / "artifact.json"
CONSUMER_ROOT = ROOT.parent / "ai-core-private"


@unittest.skipUnless(C2_PATH.exists(), "retained C2 evidence is unavailable")
class CorrelationConcentrationGuardBundleSerializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifact = json.loads(C2_PATH.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp_dir.name) / "c2.json"
        self.path.write_text(json.dumps(self.artifact, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _bundle(self) -> dict:
        return {"schema_version": "1.0.0", "tickers": {"BSR": {}, "GAS": {}}}

    def test_disabled_or_incomplete_opt_in_preserves_legacy_bundle_bytes(self) -> None:
        original = self._bundle()
        for kwargs in (
            {"include": False, "artifact_path": str(self.path), "lookback": 20},
            {"include": True, "artifact_path": None, "lookback": 20},
            {"include": True, "artifact_path": str(self.path), "lookback": None},
        ):
            candidate = copy.deepcopy(original)
            self.assertEqual(original, attach_correlation_concentration_guard(candidate, **kwargs))

    def test_verified_artifact_is_attached_once_verbatim_at_top_level(self) -> None:
        bundle = self._bundle()
        attach_correlation_concentration_guard(
            bundle, include=True, artifact_path=str(self.path), lookback=20,
        )
        attached = bundle["correlation_concentration_guard"]
        self.assertEqual(self.artifact, attached)
        self.assertNotIn("correlation_concentration_guard", bundle["tickers"]["BSR"])
        self.assertEqual(0, attached["validation"]["recommendation_mutation_count"])
        pair = next(row for row in attached["pairwise_correlation_context"]
                    if {row["ticker_i"], row["ticker_j"]} == {"BSR", "GAS"})
        self.assertEqual(0.8235585903592545, pair["correlation"])

    def test_mismatched_or_unsupported_lookback_fails_closed(self) -> None:
        self.assertIsNone(load_correlation_concentration_guard_artifact(self.path, lookback=60))
        self.assertIsNone(load_correlation_concentration_guard_artifact(self.path, lookback=21))
        bundle = self._bundle()
        attach_correlation_concentration_guard(
            bundle, include=True, artifact_path=str(self.path), lookback=60,
        )
        self.assertNotIn("correlation_concentration_guard", bundle)

    def test_tampered_identity_fails_closed_and_attachment_is_deterministic(self) -> None:
        tampered = copy.deepcopy(self.artifact)
        tampered["guard_context"]["status"] = "FORGED"
        bad_path = Path(self.tmp_dir.name) / "tampered.json"
        bad_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")
        self.assertIsNone(load_correlation_concentration_guard_artifact(bad_path, lookback=20))
        first, second = self._bundle(), self._bundle()
        for bundle in (first, second):
            attach_correlation_concentration_guard(
                bundle, include=True, artifact_path=str(self.path), lookback=20,
            )
        self.assertEqual(first, second)

    def test_partial_readiness_payload_is_preserved_without_zero_filling(self) -> None:
        partial = copy.deepcopy(self.artifact)
        partial["pairwise_correlation_context"][0].update({
            "status": "PAIRWISE_INSUFFICIENT_OR_PARTIAL", "correlation": None,
            "return_observations": None,
        })
        partial["guard_context"]["status"] = "PARTIAL_PAIRWISE_VIEW"
        partial["validation"].update({
            "pairwise_ready_count": 779, "pairwise_insufficient_or_unavailable_count": 1,
        })
        partial.pop("artifact_sha256"); partial.pop("artifact_identity")
        partial.update(content_identity(partial))
        partial_path = Path(self.tmp_dir.name) / "partial.json"
        partial_path.write_text(json.dumps(partial, sort_keys=True), encoding="utf-8")
        bundle = self._bundle()
        attach_correlation_concentration_guard(
            bundle, include=True, artifact_path=str(partial_path), lookback=20,
        )
        row = bundle["correlation_concentration_guard"]["pairwise_correlation_context"][0]
        self.assertEqual("PAIRWISE_INSUFFICIENT_OR_PARTIAL", row["status"])
        self.assertIsNone(row["correlation"])
        self.assertIsNone(row["return_observations"])

    @unittest.skipUnless(CONSUMER_ROOT.exists(), "Consumer repository is unavailable")
    def test_actual_consumer_adapter_parses_the_serialized_top_level_artifact(self) -> None:
        sys.path.insert(0, str(CONSUMER_ROOT))
        try:
            from builders.correlation_concentration_consumer_context import (  # noqa: PLC0415
                parse_correlation_concentration_context,
            )
            bundle = self._bundle()
            attach_correlation_concentration_guard(
                bundle, include=True, artifact_path=str(self.path), lookback=20,
            )
            upstream = self.artifact["upstream_recommendation_context"]["BSR"]
            parsed = parse_correlation_concentration_context(
                bundle["correlation_concentration_guard"], ticker="BSR",
                recommendation_label=upstream["recommendation_label"],
                recommendation_readiness=upstream["recommendation_readiness"],
            )
            self.assertEqual("CORRELATION_CONCENTRATION_READY", parsed["status"])
            self.assertEqual(20, parsed["context"]["selected_lookback_sessions"])
        finally:
            sys.path.remove(str(CONSUMER_ROOT))


if __name__ == "__main__":
    unittest.main()
