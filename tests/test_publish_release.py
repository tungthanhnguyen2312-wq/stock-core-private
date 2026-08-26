"""The release publisher's boundary: what it publishes, what it refuses, what it restores.

These tests build a real exact-session release on disk -- one that the Consumer's own
`verify_exact_session_bundle` accepts -- and drive `tools/publish_release.py` against a real
git repository with a local bare remote. Nothing here stubs the validator or the hashes,
because the whole point of the publisher is that those two things gate the promotion.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import publish_release as release  # noqa: E402

WORKSPACE = ROOT.parent
CONSUMER_ROOT = WORKSPACE / "ai-core-private"
SESSION = "2026-07-30"
GENERATED_AT = "2026-07-30T10:00:00+00:00"
PRODUCER_CONTRACT = "stocklookup-producer/2026.08.03"
TRUSTED_SUBSET_SCHEMA = "1.1.0"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(body)
    return _sha256_bytes(body)


def build_release(root: Path, *, session: str = SESSION, generated_at: str = GENERATED_AT,
                  sidecar_session: str | None = None,
                  corrupt_after_manifest: str | None = None) -> dict[str, str]:
    """Write a complete, self-consistent exact-session release into `root`.

    `sidecar_session` lets a test bind the taxonomy sidecar to a different session than the
    manifest proof; `corrupt_after_manifest` rewrites one artifact after the manifest has
    recorded its hash, which is exactly the shape of a mid-flight tamper.
    """
    root.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema_version": "1.1.0",
        "generated_at": generated_at,
        "reference_session_date": session,
        "tickers_requested": ["HPG", "VNINDEX"],
        "price_basis": "unknown", "price_basis_verified": False,
        "volume_basis": "unknown", "volume_basis_verified": False, "is_actionable": False,
        "tickers": {
            "HPG": {"snapshot": {"date": session},
                    "financial_distress_evidence": {"status": "available", "score": 1.5}},
            "VNINDEX": {"snapshot": None},
        },
    }
    bundle_sha = _write_json(root / "analysis_bundle.json", bundle)
    focus_sha = _write_json(root / "focus_extract.json", {
        "schema_version": "1.1.0", "generated_at": generated_at,
        "reference_session_date": session, "tickers_requested": ["HPG", "VNINDEX"]})
    sidecar_payload = {
        "schema_version": "1.0.0", "generated_at": generated_at,
        "session_identity": sidecar_session or session,
        "records_fingerprint": "fingerprint-" + (sidecar_session or session),
        "input_fingerprint": "inputs", "records": [], "taxonomy_counts": {},
    }
    sidecar_sha = _write_json(root / "statement_taxonomy_sidecar.json", sidecar_payload)

    required = [
        {"file": "analysis_bundle.json", "sha256": bundle_sha},
        {"file": "focus_extract.json", "sha256": focus_sha},
        {"file": "statement_taxonomy_sidecar.json", "sha256": sidecar_sha},
    ]
    manifest = {
        "schema_version": TRUSTED_SUBSET_SCHEMA,
        "producer_contract_version": PRODUCER_CONTRACT,
        "generated_at": generated_at,
        "statement_taxonomy_sidecar": {
            "present": True,
            "records_fingerprint": sidecar_payload["records_fingerprint"],
            "input_fingerprint": "inputs",
            "session_identity": sidecar_payload["session_identity"],
            "authority_level": "generated_evidence",
        },
        "trusted_subset": {
            "schema_version": TRUSTED_SUBSET_SCHEMA,
            "producer_contract_version": PRODUCER_CONTRACT,
            "tickers": ["HPG"],
            "unproven_tickers": [{"ticker": "VNINDEX", "observed_session_identity": None,
                                  "reason": "snapshot_missing"}],
            "bundle_ticker_set": ["HPG", "VNINDEX"],
            "trust_state": "untrusted_basis",
            "session_identity": session,
            "generated_at": generated_at,
            "bundle_filename": "analysis_bundle.json",
            "bundle_sha256": bundle_sha,
            "bundle_reference_session_date": session,
            "bundle_generated_at": generated_at,
            "required_artifacts": required,
            "expected_artifact_filenames": sorted(
                ["analysis_bundle.json", "bundle_manifest.json",
                 "focus_extract.json", "statement_taxonomy_sidecar.json"]),
            "per_ticker": {"HPG": {"session_identity": session,
                                   "required_current_fields_qualified": True, "warnings": []}},
            "price_basis": {"state": "unknown", "verified": False},
            "volume_basis": {"state": "unknown", "verified": False},
        },
    }
    manifest_sha = _write_json(root / "bundle_manifest.json", manifest)
    if corrupt_after_manifest:
        (root / corrupt_after_manifest).write_bytes(
            (root / corrupt_after_manifest).read_bytes() + b"\n// tampered\n")
    return {"analysis_bundle.json": bundle_sha, "focus_extract.json": focus_sha,
            "statement_taxonomy_sidecar.json": sidecar_sha, "bundle_manifest.json": manifest_sha}


def rehash_manifest(root: Path) -> dict[str, str]:
    """Re-point the manifest at whatever the artifacts on disk now hash to."""
    manifest = json.loads((root / "bundle_manifest.json").read_text(encoding="utf-8"))
    proof = manifest["trusted_subset"]
    for item in proof["required_artifacts"]:
        item["sha256"] = _sha256_bytes((root / item["file"]).read_bytes())
    proof["bundle_sha256"] = _sha256_bytes((root / "analysis_bundle.json").read_bytes())
    manifest_sha = _write_json(root / "bundle_manifest.json", manifest)
    hashes = {item["file"]: item["sha256"] for item in proof["required_artifacts"]}
    hashes["bundle_manifest.json"] = manifest_sha
    return hashes


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=True)
    return (result.stdout or "").strip()


def build_destination(base: Path) -> tuple[Path, Path]:
    """A real git worktree on `main` with a local bare remote, plus pre-existing drift."""
    remote = base / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True,
                   capture_output=True)
    work = base / "web"
    work.mkdir()
    git(work, "init", "-b", "main")
    git(work, "config", "user.email", "release-test@example.invalid")
    git(work, "config", "user.name", "release test")
    git(work, "remote", "add", "origin", str(remote))
    # A previous release plus the kind of unrelated generated artifacts that were the
    # original problem: they are tracked, they get modified, and they must survive.
    build_release(work, session="2026-07-29", generated_at="2026-07-29T10:00:00+00:00")
    for name in ("screen_snapshot.csv", "analysis_latest.json", "market_breadth.csv"):
        (work / name).write_text("previous\n", encoding="utf-8")
    (work / "data").mkdir()
    (work / "data" / "candle_signals.json").write_text("previous\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-m", "baseline")
    git(work, "push", "origin", "main")
    for name in ("screen_snapshot.csv", "analysis_latest.json", "market_breadth.csv",
                 "data/candle_signals.json"):
        (work / name).write_text("locally modified\n", encoding="utf-8")
    return work, remote


class ReleaseFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.source = self.base / "runtime"
        self.incoming = build_release(self.source)
        self.destination, self.remote = build_destination(self.base)
        self._orig_identity_env = os.environ.get("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE")
        os.environ["STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE"] = str(self.destination.resolve())
        self.addCleanup(self._restore_identity_env)
        self.addCleanup(self._tmp.cleanup)

    def _restore_identity_env(self) -> None:
        if self._orig_identity_env is None:
            os.environ.pop("STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE", None)
        else:
            os.environ["STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE"] = self._orig_identity_env

    def publisher(self, **kwargs) -> release.ReleasePublisher:
        kwargs.setdefault("live", True)
        kwargs.setdefault("consumer_root", CONSUMER_ROOT)
        kwargs.setdefault("rollback_root", self.base / "rollback")
        return release.ReleasePublisher(self.source, self.destination, **kwargs)

    def drift_state(self) -> dict[str, str]:
        return {name: (self.destination / name).read_text(encoding="utf-8")
                for name in ("screen_snapshot.csv", "analysis_latest.json",
                             "market_breadth.csv", "data/candle_signals.json")}


class AllowlistedPublicationTests(ReleaseFixture):
    def test_publishes_exactly_the_allowlist_and_verifies_it(self) -> None:
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["outcome"], "published")
        self.assertEqual(payload["live_sha256"], self.incoming)
        self.assertEqual(sorted(payload["git"]["staged"]), sorted(release.RELEASE_ALLOWLIST))
        head = git(self.destination, "rev-parse", "HEAD")
        self.assertEqual(git(self.destination, "ls-remote", "origin", "refs/heads/main").split()[0], head)
        committed = git(self.destination, "show", "--name-only", "--format=", head).split()
        self.assertEqual(sorted(committed), sorted(release.RELEASE_ALLOWLIST))

    def test_dry_run_touches_nothing_and_reports_the_plan(self) -> None:
        before = self.destination_snapshot()
        code, payload = release.run_publication(self.publisher(live=False))
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["outcome"], "dry_run_ok")
        plan = payload["plan"]
        self.assertEqual(plan["files_to_publish"], list(release.RELEASE_ALLOWLIST))
        self.assertEqual(plan["incoming_sha256"], self.incoming)
        self.assertEqual(plan["session_identity"], SESSION)
        self.assertIn("screen_snapshot.csv", plan["explicitly_excluded"])
        self.assertTrue(plan["rollback_source"])
        self.assertEqual(self.destination_snapshot(), before)
        self.assertEqual(git(self.destination, "rev-list", "--count", "HEAD"), "1")

    def destination_snapshot(self) -> dict[str, str]:
        return {p.name: release.sha256_file(p)
                for p in sorted(self.destination.rglob("*")) if p.is_file() and ".git" not in p.parts}


class UnrelatedDriftTests(ReleaseFixture):
    def test_unrelated_modified_artifacts_are_neither_copied_nor_committed(self) -> None:
        drift_before = self.drift_state()
        # The source also carries the same unrelated artifacts, with different content: a
        # directory-copy publisher would overwrite the destination's versions with these.
        for name in ("screen_snapshot.csv", "analysis_latest.json", "market_breadth.csv"):
            (self.source / name).write_text("SOURCE VERSION - must never be published\n", encoding="utf-8")
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 0, payload)
        self.assertEqual(self.drift_state(), drift_before)
        head = git(self.destination, "rev-parse", "HEAD")
        committed = git(self.destination, "show", "--name-only", "--format=", head).split()
        for name in ("screen_snapshot.csv", "analysis_latest.json", "market_breadth.csv",
                     "data/candle_signals.json"):
            self.assertNotIn(name, committed)
        self.assertIn("screen_snapshot.csv", payload["excluded"])
        still_dirty = git(self.destination, "status", "--porcelain")
        self.assertIn("screen_snapshot.csv", still_dirty)

    def test_line_ending_translation_would_be_caught_before_the_commit(self) -> None:
        """An artifact git would rewrite on its way into the index must not be published."""
        git(self.destination, "config", "core.autocrlf", "true")
        # CRLF on disk, which core.autocrlf normalises to LF in the index: the published
        # bytes would then differ from the manifest that describes them.
        body = (self.source / "focus_extract.json").read_bytes().replace(b"\n", b"\r\n")
        (self.source / "focus_extract.json").write_bytes(body)
        rehash_manifest(self.source)
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 1, payload)
        self.assertEqual(payload["failed_gate"], "git_content_normalization")
        self.assertIn("focus_extract.json", payload["failure_detail"])
        self.assertTrue(payload["rollback"]["performed"])
        self.assertEqual(git(self.destination, "rev-list", "--count", "HEAD"), "1")

    def test_an_unrelated_file_staged_by_someone_else_stops_the_publication(self) -> None:
        git(self.destination, "add", "--", "screen_snapshot.csv")
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "git_index_not_clean")
        self.assertIn("screen_snapshot.csv", payload["failure_detail"])


class RefusalTests(ReleaseFixture):
    def test_missing_required_artifact_is_refused_before_anything_is_staged(self) -> None:
        (self.source / "focus_extract.json").unlink()
        before = git(self.destination, "rev-parse", "HEAD")
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "required_artifact_missing")
        self.assertIn("focus_extract.json", payload["failure_detail"])
        self.assertEqual(git(self.destination, "rev-parse", "HEAD"), before)

    def test_manifest_hash_mismatch_is_refused(self) -> None:
        build_release(self.source, corrupt_after_manifest="focus_extract.json")
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "manifest_hash_mismatch")
        self.assertIn("focus_extract.json", payload["failure_detail"])

    def test_a_sidecar_from_another_session_is_refused(self) -> None:
        build_release(self.source, sidecar_session="2026-07-28")
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "session_mismatch")
        self.assertIn("statement_taxonomy_sidecar", payload["failure_detail"])

    def test_a_manifest_widening_the_trusted_set_is_refused(self) -> None:
        manifest = json.loads((self.source / "bundle_manifest.json").read_text(encoding="utf-8"))
        manifest["trusted_subset"]["expected_artifact_filenames"].append("screen_snapshot.csv")
        (self.source / "bundle_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "unexpected_release_file")
        self.assertIn("screen_snapshot.csv", payload["failure_detail"])

    def test_a_bundle_body_from_another_session_is_refused_by_the_consumer_validator(self) -> None:
        bundle = json.loads((self.source / "analysis_bundle.json").read_text(encoding="utf-8"))
        bundle["tickers"]["HPG"]["snapshot"]["date"] = "2026-07-29"
        body = json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")
        (self.source / "analysis_bundle.json").write_bytes(body)
        manifest = json.loads((self.source / "bundle_manifest.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(body).hexdigest()
        manifest["trusted_subset"]["bundle_sha256"] = digest
        for item in manifest["trusted_subset"]["required_artifacts"]:
            if item["file"] == "analysis_bundle.json":
                item["sha256"] = digest
        (self.source / "bundle_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = release.run_publication(self.publisher())
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "consumer_exact_session_validation")
        self.assertIn("bundle_ticker_session_mismatch", payload["failure_detail"])


class InterruptedPromotionTests(ReleaseFixture):
    def test_a_promotion_that_dies_halfway_restores_the_complete_previous_set(self) -> None:
        previous = {name: release.sha256_file(self.destination / name)
                    for name in release.RELEASE_ALLOWLIST}
        drift_before = self.drift_state()
        publisher = self.publisher()
        real_replace = os.replace
        moved: list[str] = []

        def dying_replace(src, dst):
            if len(moved) >= 2:
                raise OSError("simulated interruption during promotion")
            moved.append(str(dst))
            return real_replace(src, dst)

        publisher.promote = _promote_with(publisher, dying_replace)
        code, payload = release.run_publication(publisher)
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "promote_release")
        self.assertTrue(payload["rollback"]["performed"])
        self.assertEqual(payload["rollback"]["verification_failed"], [])
        self.assertEqual({name: release.sha256_file(self.destination / name)
                          for name in release.RELEASE_ALLOWLIST}, previous)
        self.assertEqual(self.drift_state(), drift_before)
        self.assertEqual(git(self.destination, "rev-list", "--count", "HEAD"), "1")


def _promote_with(publisher: release.ReleasePublisher, replace):
    """Rebind promote() onto an injectable os.replace without patching the module globally."""
    def promote() -> list[str]:
        staging = publisher.staging_dir
        promoted: list[str] = []
        try:
            for name in release.RELEASE_ALLOWLIST:
                replace(staging / name, publisher.destination / name)
                promoted.append(name)
        except OSError as exc:
            publisher.promoted = promoted
            raise release.ReleaseError("promote_release", f"promotion interrupted: {exc}") from exc
        publisher.promoted = promoted
        return promoted
    return promote


class PostPublishRollbackTests(ReleaseFixture):
    def test_a_failure_after_promotion_restores_and_exits_nonzero(self) -> None:
        previous = {name: release.sha256_file(self.destination / name)
                    for name in release.RELEASE_ALLOWLIST}
        publisher = self.publisher()
        original = publisher.verify_destination

        def failing_verify(incoming):
            original(incoming)
            raise release.ReleaseError("post_publish_smoke", "simulated post-publication check failure")

        publisher.verify_destination = failing_verify
        code, payload = release.run_publication(publisher)
        self.assertEqual(code, 1)
        self.assertEqual(payload["failed_gate"], "post_publish_smoke")
        self.assertTrue(payload["rollback"]["performed"])
        self.assertEqual(sorted(payload["rollback"]["restored"]), sorted(release.RELEASE_ALLOWLIST))
        self.assertEqual({name: release.sha256_file(self.destination / name)
                          for name in release.RELEASE_ALLOWLIST}, previous)
        self.assertEqual(git(self.destination, "rev-list", "--count", "HEAD"), "1")

    def test_the_rollback_copy_is_written_and_hash_verified(self) -> None:
        publisher = self.publisher()
        code, payload = release.run_publication(publisher)
        self.assertEqual(code, 0, payload)
        rollback = Path(payload["rollback"])
        self.assertTrue(rollback.is_dir())
        saved = json.loads((rollback / "rollback_manifest.json").read_text(encoding="utf-8"))
        for name, digest in saved["sha256"].items():
            self.assertEqual(release.sha256_file(rollback / name), digest)
        self.assertEqual(saved["sha256"], payload["previous_sha256"])


class IdempotenceTests(ReleaseFixture):
    def test_republishing_the_same_release_changes_nothing(self) -> None:
        code, first = release.run_publication(self.publisher())
        self.assertEqual(code, 0, first)
        head = git(self.destination, "rev-parse", "HEAD")
        mtimes = {name: (self.destination / name).stat().st_mtime_ns
                  for name in release.RELEASE_ALLOWLIST}
        code, second = release.run_publication(self.publisher())
        self.assertEqual(code, 0, second)
        self.assertEqual(second["outcome"], "already_current")
        self.assertEqual(second["live_sha256"], self.incoming)
        self.assertFalse(second["git"]["committed"])
        self.assertEqual(git(self.destination, "rev-parse", "HEAD"), head)
        self.assertEqual({name: (self.destination / name).stat().st_mtime_ns
                          for name in release.RELEASE_ALLOWLIST}, mtimes)
        self.assertIsNone(second["rollback"])


if __name__ == "__main__":
    unittest.main()
