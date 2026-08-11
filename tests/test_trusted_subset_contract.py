"""Focused coverage for trusted_subset_contract.py.

publish_dashboard.py copies analysis_bundle.json independently of the other three members
of the exact-session trusted subset (bundle_manifest.json, focus_extract.json,
statement_taxonomy_sidecar.json) that tools/publish_release.py owns as one hash-verified
unit. Commit fbaf1fe (2026-08-05) is the real-world proof of what happens without this
gate: publish_dashboard.py replaced analysis_bundle.json with a fresh 2026-08-04 copy while
bundle_manifest.json still declared the 2026-08-03 file's hash — a mixed release that
failed 7 of 9 tests/release-smoke.test.js assertions in CI and left GitHub Pages on the
previous deployment. These tests pin down the fix: a hard, deterministic refusal before any
git mutation, scoped so a publisher only answers for the trusted-subset member it actually
copies.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import trusted_subset_contract as tsc  # noqa: E402


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(root: Path, name: str, content: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(content, encoding="utf-8")


def _manifest(*, required: dict[str, str], expected: list[str]) -> str:
    return json.dumps({
        "schema_version": "1.1.0",
        "trusted_subset": {
            "session_identity": "2026-08-04",
            "required_artifacts": [{"file": name, "sha256": sha} for name, sha in required.items()],
            "expected_artifact_filenames": expected,
        },
    })


class NoManifestPassesVacuouslyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_no_bundle_manifest_json_is_not_this_contracts_concern(self):
        _write(self.root, "analysis_bundle.json", '{"reference_session_date": "2026-08-04"}')
        report = tsc.verify_trusted_subset(self.root)
        self.assertTrue(report.ready)
        self.assertEqual(report.checked, [])


class ExactSessionCompleteReleaseTests(unittest.TestCase):
    """Scenario: exact-session complete release passes."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.bundle_content = '{"reference_session_date": "2026-08-04", "tickers": {}}'
        self.focus_content = '{"reference_session_date": "2026-08-04"}'
        self.sidecar_content = '{"session_identity": "2026-08-04"}'
        _write(self.root, "analysis_bundle.json", self.bundle_content)
        _write(self.root, "focus_extract.json", self.focus_content)
        _write(self.root, "statement_taxonomy_sidecar.json", self.sidecar_content)
        required = {
            "analysis_bundle.json": _sha256_text(self.bundle_content),
            "focus_extract.json": _sha256_text(self.focus_content),
            "statement_taxonomy_sidecar.json": _sha256_text(self.sidecar_content),
        }
        expected = ["analysis_bundle.json", "bundle_manifest.json", "focus_extract.json",
                    "statement_taxonomy_sidecar.json"]
        _write(self.root, "bundle_manifest.json", _manifest(required=required, expected=expected))

    def test_complete_matching_release_is_ready(self):
        report = tsc.verify_trusted_subset(self.root)
        self.assertTrue(report.ready, report.problems)
        self.assertEqual(report.problems, [])
        self.assertIn("analysis_bundle.json", report.checked)
        self.assertIn("bundle_manifest.json", report.checked)


class MixedReleaseReproductionTests(unittest.TestCase):
    """Reproduces the exact real-world defect: analysis_bundle.json replaced without its
    matching manifest (commit fbaf1fe, 2026-08-05)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        old_bundle = '{"reference_session_date": "2026-08-03"}'
        required = {"analysis_bundle.json": _sha256_text(old_bundle)}
        expected = ["analysis_bundle.json", "bundle_manifest.json"]
        _write(self.root, "bundle_manifest.json", _manifest(required=required, expected=expected))
        # A publish_dashboard.py --live run replaces analysis_bundle.json with a fresh
        # session's bytes, but bundle_manifest.json (tools/publish_release.py's domain) was
        # never re-published to match — the manifest still names the OLD file's hash.
        new_bundle = '{"reference_session_date": "2026-08-04"}'
        _write(self.root, "analysis_bundle.json", new_bundle)

    def test_replacing_analysis_bundle_without_its_manifest_fails(self):
        report = tsc.verify_trusted_subset(self.root)
        self.assertFalse(report.ready)
        self.assertTrue(any("analysis_bundle.json" in p and "does not match" in p for p in report.problems))

    def test_manifest_hash_mismatch_is_reported_with_both_hashes(self):
        report = tsc.verify_trusted_subset(self.root)
        problem = next(p for p in report.problems if "analysis_bundle.json" in p)
        self.assertIn("sha256=", problem)
        self.assertIn("manifest-declared", problem)

    def test_scoped_to_analysis_bundle_still_catches_it(self):
        """publish_dashboard.py's own narrow scope must still catch the one artifact it is
        actually responsible for."""
        report = tsc.verify_trusted_subset(self.root, scope=("analysis_bundle.json",))
        self.assertFalse(report.ready)


class MissingTrustedArtifactTests(unittest.TestCase):
    """Scenario: missing trusted artifact fails."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        bundle_content = '{"reference_session_date": "2026-08-04"}'
        _write(self.root, "analysis_bundle.json", bundle_content)
        required = {"analysis_bundle.json": _sha256_text(bundle_content),
                    "focus_extract.json": "deadbeef"}
        # focus_extract.json is declared expected but was never written to disk.
        expected = ["analysis_bundle.json", "bundle_manifest.json", "focus_extract.json"]
        _write(self.root, "bundle_manifest.json", _manifest(required=required, expected=expected))

    def test_missing_declared_artifact_fails(self):
        report = tsc.verify_trusted_subset(self.root)
        self.assertFalse(report.ready)
        self.assertTrue(any("focus_extract.json" in p and "missing from" in p for p in report.problems))

    def test_missing_artifact_outside_scope_does_not_block_a_narrower_caller(self):
        """publish_dashboard.py only ever copies analysis_bundle.json — a missing
        focus_extract.json (tools/publish_release.py's job to deliver) must not block its
        unrelated screener-data commit."""
        report = tsc.verify_trusted_subset(self.root, scope=("analysis_bundle.json",))
        self.assertTrue(report.ready, report.problems)


class UndeclaredIntruderTests(unittest.TestCase):
    """A trusted-subset-named file present but absent from the manifest's own declared set
    (e.g. a stale sidecar from a prior session that this session's export correctly
    excluded) is an intruder for a full audit, but must not leak into a narrower caller's
    verdict — this is precisely the real dashboard-runtime state discovered while building
    this fix: statement_taxonomy_sidecar.present:false with the file still on disk."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        bundle_content = '{"reference_session_date": "2026-08-04"}'
        _write(self.root, "analysis_bundle.json", bundle_content)
        _write(self.root, "statement_taxonomy_sidecar.json", '{"session_identity": "2026-08-01"}')
        required = {"analysis_bundle.json": _sha256_text(bundle_content)}
        expected = ["analysis_bundle.json", "bundle_manifest.json"]  # sidecar deliberately absent
        _write(self.root, "bundle_manifest.json", _manifest(required=required, expected=expected))

    def test_full_audit_flags_the_undeclared_sidecar(self):
        report = tsc.verify_trusted_subset(self.root)
        self.assertFalse(report.ready)
        self.assertTrue(any("statement_taxonomy_sidecar.json" in p and "not declared" in p
                            for p in report.problems))

    def test_analysis_bundle_scoped_caller_is_unaffected(self):
        report = tsc.verify_trusted_subset(self.root, scope=("analysis_bundle.json",))
        self.assertTrue(report.ready, report.problems)


class MalformedManifestTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_manifest_present_but_not_json_fails(self):
        _write(self.root, "bundle_manifest.json", "{not valid json")
        report = tsc.verify_trusted_subset(self.root)
        self.assertFalse(report.ready)
        self.assertTrue(any("not readable JSON" in p for p in report.problems))

    def test_manifest_with_no_trusted_subset_proof_fails(self):
        _write(self.root, "bundle_manifest.json", json.dumps({"schema_version": "1.1.0"}))
        report = tsc.verify_trusted_subset(self.root)
        self.assertFalse(report.ready)
        self.assertTrue(any("no trusted_subset proof" in p for p in report.problems))


class DeterministicOrderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tsc_test_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        bundle_content = '{"reference_session_date": "2026-08-04"}'
        _write(self.root, "analysis_bundle.json", bundle_content)
        required = {"analysis_bundle.json": "wronghash"}
        expected = ["analysis_bundle.json", "bundle_manifest.json"]
        _write(self.root, "bundle_manifest.json", _manifest(required=required, expected=expected))

    def test_repeated_calls_are_byte_identical(self):
        first = tsc.verify_trusted_subset(self.root).render()
        second = tsc.verify_trusted_subset(self.root).render()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
