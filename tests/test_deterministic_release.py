"""Two explicit determinism modes for the supported release artifacts.

The previous closeout claimed both "byte-identical with pinned evaluation time" and
"generated_at differs by session". Both are true, of different modes, and neither is a
property of the exporter in general. These tests pin the difference down:

NORMAL PRODUCTION MODE  (no --evaluation-at)
    `generated_at` is wall-clock, so the artifacts are NOT byte-identical between two
    builds. The business content must still be identical for unchanged inputs, and the
    session identity must move consistently across bundle body, manifest and proof.

REPRODUCIBILITY MODE  (--evaluation-at pinned)
    Evaluation time and generated/session time are the same value in this exporter --
    `generated_at = reference_at.isoformat(...)` -- so pinning the evaluation time pins the
    timestamps too, and the supported artifact set must be byte-identical.

Both modes run the real `export_ai_bundle.py` against the real runtime root into isolated
`--output-dir` shadows. Nothing here writes to the production artifact set.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _runtime_root import RUNTIME_ROOT, require_runtime_path  # noqa: E402

#: The artifacts a release publishes and therefore the only ones a determinism claim covers.
#: `observability_events.jsonl` is an append-only run log, not a release artifact.
RELEASE_ARTIFACTS = ("analysis_bundle.json", "focus_extract.json", "bundle_manifest.json")
PINNED_EVALUATION_AT = "2026-08-03T00:00:00+00:00"
TICKERS = "HPG,VNM,SSI"

#: Keys whose values are identity/time/hash metadata rather than business content. Normal
#: production mode is allowed to move these between builds; nothing else may move.
#: `valuation_date` is the intrinsic-valuation methods' echo of the evaluation instant, not
#: the reporting period they valued (that is `financial_period`), so it belongs here.
IDENTITY_KEYS = frozenset({
    "generated_at", "bundle_generated_at", "reference_at", "reference_time",
    "source_generated_at", "downstream_generated_at", "upstream_generated_at",
    "evaluated_at", "valuation_date", "mtime", "mtime_iso", "sha256", "bundle_sha256",
    "age_days", "age_hours", "age_sessions", "days_since", "seconds_since",
})


def scrub_identity(value):
    """Recursively drop identity/time/hash fields so business content can be compared."""
    if isinstance(value, dict):
        return {k: scrub_identity(v) for k, v in value.items() if k not in IDENTITY_KEYS}
    if isinstance(value, list):
        return [scrub_identity(item) for item in value]
    return value


def run_export(output_dir: Path, *, evaluation_at: str | None) -> None:
    command = [sys.executable, str(ROOT / "export_ai_bundle.py"),
               "--tickers", TICKERS,
               "--include-fundamental-quality-evidence",
               "--include-analysis-lane-eligibility",
               "--output-dir", str(output_dir)]
    if evaluation_at:
        command += ["--evaluation-at", evaluation_at]
    env = {**os.environ, "STOCK_LOOKUP_RUNTIME_ROOT": str(RUNTIME_ROOT), "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        raise unittest.SkipTest(
            "export_ai_bundle.py could not produce a shadow export in this environment "
            f"(exit {result.returncode}): {(result.stderr or result.stdout or '').strip()[-600:]}")


class DeterministicGenerationTests(unittest.TestCase):
    """Each test runs two real shadow exports; they are slow by nature, not by accident."""

    @classmethod
    def setUpClass(cls) -> None:
        require_runtime_path("vn_stock.db")
        require_runtime_path("screen_snapshot_live.csv")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _two_exports(self, label: str, *, evaluation_at: str | None) -> tuple[Path, Path]:
        first, second = self.base / f"{label}-a", self.base / f"{label}-b"
        for target in (first, second):
            target.mkdir(parents=True, exist_ok=True)
            run_export(target, evaluation_at=evaluation_at)
            for name in RELEASE_ARTIFACTS:
                if not (target / name).is_file():
                    raise unittest.SkipTest(f"shadow export produced no {name}")
        return first, second

    # ------------------------------------------------------------ reproducibility mode
    def test_pinned_evaluation_time_yields_byte_identical_artifacts(self) -> None:
        first, second = self._two_exports("pinned", evaluation_at=PINNED_EVALUATION_AT)
        for name in RELEASE_ARTIFACTS:
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(),
                             f"{name} is not byte-identical under a pinned evaluation time")

    def test_pinned_evaluation_time_also_pins_every_generated_timestamp(self) -> None:
        """The claim is about all bytes, including the timestamp and identity fields."""
        first, _ = self._two_exports("pinned", evaluation_at=PINNED_EVALUATION_AT)
        bundle = json.loads((first / "analysis_bundle.json").read_text(encoding="utf-8"))
        manifest = json.loads((first / "bundle_manifest.json").read_text(encoding="utf-8"))
        focus = json.loads((first / "focus_extract.json").read_text(encoding="utf-8"))
        proof = manifest["trusted_subset"]
        self.assertEqual(bundle["generated_at"], PINNED_EVALUATION_AT)
        self.assertEqual(focus["generated_at"], PINNED_EVALUATION_AT)
        self.assertEqual(manifest["generated_at"], PINNED_EVALUATION_AT)
        self.assertEqual(proof["generated_at"], PINNED_EVALUATION_AT)
        self.assertEqual(proof["bundle_generated_at"], PINNED_EVALUATION_AT)

    # ------------------------------------------------------------ normal production mode
    def test_wall_clock_mode_moves_identity_but_not_business_content(self) -> None:
        first, second = self._two_exports("wallclock", evaluation_at=None)
        first_bundle = json.loads((first / "analysis_bundle.json").read_text(encoding="utf-8"))
        second_bundle = json.loads((second / "analysis_bundle.json").read_text(encoding="utf-8"))
        # Identity moves...
        self.assertNotEqual(first_bundle["generated_at"], second_bundle["generated_at"],
                            "two wall-clock builds produced the same generated_at; "
                            "this test cannot distinguish the modes")
        self.assertNotEqual((first / "analysis_bundle.json").read_bytes(),
                            (second / "analysis_bundle.json").read_bytes())
        # ...business content does not.
        self.assertEqual(scrub_identity(first_bundle), scrub_identity(second_bundle),
                         "wall-clock builds disagree on business content for unchanged inputs")
        for name in ("focus_extract.json", "bundle_manifest.json"):
            self.assertEqual(
                scrub_identity(json.loads((first / name).read_text(encoding="utf-8"))),
                scrub_identity(json.loads((second / name).read_text(encoding="utf-8"))),
                f"{name} disagrees on business content between two wall-clock builds")

    def test_wall_clock_mode_moves_manifest_and_session_identity_consistently(self) -> None:
        first, second = self._two_exports("wallclock", evaluation_at=None)
        import hashlib
        for target in (first, second):
            bundle_path = target / "analysis_bundle.json"
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            manifest = json.loads((target / "bundle_manifest.json").read_text(encoding="utf-8"))
            proof = manifest["trusted_subset"]
            generated_at = bundle["generated_at"]
            # One timestamp, echoed everywhere the Consumer checks it.
            self.assertEqual(manifest["generated_at"], generated_at)
            self.assertEqual(proof["generated_at"], generated_at)
            self.assertEqual(proof["bundle_generated_at"], generated_at)
            self.assertEqual(json.loads((target / "focus_extract.json").read_text(encoding="utf-8"))["generated_at"],
                             generated_at)
            # The proof's bundle hash tracks the body it was built from, so a changed
            # timestamp changes the exact-session identity rather than silently keeping it.
            self.assertEqual(proof["bundle_sha256"],
                             hashlib.sha256(bundle_path.read_bytes()).hexdigest())
            self.assertEqual(proof["bundle_reference_session_date"], bundle["reference_session_date"])
        first_manifest = json.loads((first / "bundle_manifest.json").read_text(encoding="utf-8"))
        second_manifest = json.loads((second / "bundle_manifest.json").read_text(encoding="utf-8"))
        self.assertNotEqual(first_manifest["trusted_subset"]["bundle_sha256"],
                            second_manifest["trusted_subset"]["bundle_sha256"])
        # The trading session the release is about is a property of the data, not the clock.
        self.assertEqual(first_manifest["trusted_subset"]["session_identity"],
                         second_manifest["trusted_subset"]["session_identity"])


class TaxonomySidecarDeterminismTests(unittest.TestCase):
    def test_sidecar_is_byte_identical_when_its_timestamps_are_pinned(self) -> None:
        require_runtime_path("data_bctc")
        from statement_taxonomy_sidecar import build_sidecar
        first = build_sidecar(RUNTIME_ROOT, generated_at=PINNED_EVALUATION_AT,
                              session_identity="2026-07-30")
        second = build_sidecar(RUNTIME_ROOT, generated_at=PINNED_EVALUATION_AT,
                               session_identity="2026-07-30")
        self.assertEqual(json.dumps(first, ensure_ascii=False, sort_keys=True),
                         json.dumps(second, ensure_ascii=False, sort_keys=True))
        self.assertEqual(first["records_fingerprint"], second["records_fingerprint"])

    def test_sidecar_records_fingerprint_ignores_the_clock(self) -> None:
        require_runtime_path("data_bctc")
        from statement_taxonomy_sidecar import build_sidecar
        early = build_sidecar(RUNTIME_ROOT, generated_at="2026-01-01T00:00:00+00:00",
                              session_identity="2026-07-30")
        late = build_sidecar(RUNTIME_ROOT, generated_at="2026-12-31T23:59:59+00:00",
                             session_identity="2026-07-30")
        self.assertEqual(early["records_fingerprint"], late["records_fingerprint"])
        self.assertNotEqual(early["generated_at"], late["generated_at"])


if __name__ == "__main__":
    unittest.main()
