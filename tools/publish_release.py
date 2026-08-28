"""Publish one exact-session StockLookup release to the authoritative Dashboard checkout.

WHY THIS EXISTS
    `publish_dashboard.py` derives its git whitelist by scanning the HTML/JS for every
    referenced .csv/.json/.md. That whitelist is correct for "rebuild the dashboard data
    layer", but it is not a release boundary: every generated artifact already modified in
    the destination working tree falls inside it and gets swept into the release commit.
    A release is not "whatever is dirty"; it is an exact, named, hash-verified set.

WHAT THIS PUBLISHES
    Exactly RELEASE_ALLOWLIST and nothing else. The allowlist is static in this file AND
    cross-checked against the manifest's own `trusted_subset.expected_artifact_filenames`,
    so neither side can widen the release alone.

HOW IT PUBLISHES
    stage -> verify -> capture rollback -> promote -> verify -> git publish -> verify live.

    The filesystem step is "staged files plus atomic rename": every byte is written into a
    temporary release directory and hash-verified there, and only then is each file moved
    into the destination with os.replace. Nothing is ever written into the destination
    incrementally, and a failure at any point restores the complete previous set.

    For the served application the atomic unit is the git commit: GitHub Pages builds one
    deployment from one commit and swaps it in whole, so a reader sees either the previous
    release or this one, never a mixture.

MODES
    (default)   dry run. Reads, verifies, prints the exact plan. Writes nothing anywhere.
    --live      stage, promote, and (unless --no-git) commit and push the allowlist only.

EXIT CODES
    0 success (including an idempotent no-op republish)   1 a gate failed   2 bad invocation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json  # noqa: E402
from release_checkout_identity import (  # noqa: E402
    GITHUB_SOURCE_UPDATED,
    ReleaseIdentityError,
    assert_producer_publisher_file,
    assert_runtime_root_identity,
    assert_web_checkout_identity,
    publication_state_after_push,
)

WORKSPACE = ROOT.parent
DEFAULT_CONSUMER_ROOT = WORKSPACE / "ai-core-private"

#: The exact release set. Static on purpose: a release boundary that is computed from the
#: destination's contents is not a boundary. Every name here must also be declared by the
#: manifest being published, and the manifest may declare nothing outside this tuple.
RELEASE_ALLOWLIST = ("analysis_bundle.json", "bundle_manifest.json",
                     "focus_extract.json", "statement_taxonomy_sidecar.json")
#: bundle_manifest.json cannot hash itself, so it is the one allowlisted file with no entry
#: in `trusted_subset.required_artifacts`.
SELF_UNHASHABLE = "bundle_manifest.json"


class ReleaseError(RuntimeError):
    """A named publication gate refused to pass."""

    def __init__(self, gate: str, detail: str):
        super().__init__(f"{gate}: {detail}")
        self.gate = gate
        self.detail = detail


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def porcelain_paths(status_output: str) -> list[str]:
    """Repo-relative paths from `git status --porcelain` output.

    The two status columns are fixed-width and the path starts at column 3, so this must be
    handed the unstripped output. A rename reports "old -> new"; the new path is the one
    that exists in the worktree and therefore the one a release boundary cares about.
    """
    paths: list[str] = []
    for line in status_output.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        paths.append(entry.strip().strip('"'))
    return paths


def load_consumer_validator(consumer_root: Path) -> Callable[..., tuple[bool, str | None]]:
    """Return the Consumer's own `verify_exact_session_bundle`.

    Imported from `ai-core-private` rather than reimplemented: a publisher that carries its
    own copy of the exact-session rules can drift from the validator that actually gates
    the Consumer, and then a release passes here and is rejected downstream. The function
    resolves every artifact relative to the bundle it is handed, so it validates a staging
    directory exactly as it validates a runtime root.
    """
    builders = consumer_root / "builders"
    if not (builders / "build_ticker_context.py").is_file():
        raise ReleaseError("consumer_validator",
                           f"builders/build_ticker_context.py not found under {consumer_root}")
    inserted = False
    if str(consumer_root) not in sys.path:
        sys.path.insert(0, str(consumer_root))
        inserted = True
    try:
        from builders.build_ticker_context import verify_exact_session_bundle
    except Exception as exc:  # pragma: no cover - import failure is environmental
        raise ReleaseError("consumer_validator", f"cannot import the Consumer validator: {exc}") from exc
    finally:
        if inserted and sys.path and sys.path[0] == str(consumer_root):
            # Leave the Consumer package importable for the caller's process only if it was
            # already reachable; do not permanently reorder an embedder's sys.path.
            pass
    return verify_exact_session_bundle


class ReleasePublisher:
    def __init__(self, source: Path, destination: Path, *, live: bool = False,
                 rollback_root: Path | None = None, consumer_root: Path | None = None,
                 use_git: bool = True, verify_live_url: str | None = None,
                 verify_live_timeout: int = 600, commit_message: str | None = None,
                 runner: Callable[..., Any] = subprocess.run,
                 opener: Callable[[str], bytes] | None = None):
        self.source = source
        self.destination = destination
        self.live = live
        self.rollback_root = rollback_root or (source / "reports" / "release_rollback")
        self.consumer_root = consumer_root or DEFAULT_CONSUMER_ROOT
        self.use_git = use_git
        self.verify_live_url = verify_live_url.rstrip("/") if verify_live_url else None
        self.verify_live_timeout = verify_live_timeout
        self.commit_message = commit_message
        self.runner = runner
        self.opener = opener or self._http_get
        self.steps: list[dict[str, Any]] = []
        self.rollback_dir: Path | None = None
        self.staging_dir: Path | None = None
        self.promoted: list[str] = []
        self.started_at = _now()

    # ------------------------------------------------------------------ plumbing
    def _record(self, name: str, status: str, **detail: Any) -> dict[str, Any]:
        step = {"step": name, "status": status, "at": _now(), **detail}
        self.steps.append(step)
        note = detail.get("detail")
        print(f"[release] {name}: {status}" + (f" — {note}" if note else ""), flush=True)
        return step

    def _git(self, *args: str, check: bool = True, raw: bool = False) -> str:
        result = self.runner(["git", *args], cwd=str(self.destination), check=False,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        if check and result.returncode != 0:
            raise ReleaseError("git", f"git {' '.join(args)} failed: "
                                      f"{(result.stdout or '') + (result.stderr or '')}".strip())
        # `git status --porcelain` encodes the index/worktree state in the first two
        # columns, so its leading space is significant; stripping it silently corrupts the
        # path offset for the first line only. Callers that need those columns ask for raw.
        return (result.stdout or "") if raw else (result.stdout or "").strip()

    @staticmethod
    def _http_get(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - fixed https origin
            return response.read()

    def source_hashes(self) -> dict[str, str]:
        return {name: sha256_file(self.source / name) for name in RELEASE_ALLOWLIST}

    def destination_hashes(self) -> dict[str, str | None]:
        return {name: (sha256_file(self.destination / name)
                       if (self.destination / name).is_file() else None)
                for name in RELEASE_ALLOWLIST}

    def foreign_worktree_state(self) -> list[str]:
        """Every path the destination worktree reports as changed, outside the allowlist.

        Captured before and after promotion and compared: this is the mechanical proof that
        unrelated Dashboard drift was preserved rather than swept into the release.
        """
        if not self.use_git:
            return []
        return sorted(set(porcelain_paths(self._git("status", "--porcelain", raw=True)))
                      - set(RELEASE_ALLOWLIST))

    # ------------------------------------------------------------------ 1. release set
    def resolve_release(self) -> dict[str, Any]:
        """Read the manifest and prove the allowlist and the manifest agree exactly."""
        manifest_path = self.source / SELF_UNHASHABLE
        if not manifest_path.is_file():
            raise ReleaseError("release_manifest", f"{SELF_UNHASHABLE} is absent from {self.source}")
        try:
            manifest = _load_json(manifest_path)
        except (OSError, ValueError) as exc:
            raise ReleaseError("release_manifest", f"{SELF_UNHASHABLE} is not readable JSON: {exc}") from exc
        proof = manifest.get("trusted_subset") if isinstance(manifest, Mapping) else None
        if not isinstance(proof, Mapping):
            raise ReleaseError("release_manifest", f"{SELF_UNHASHABLE} carries no trusted_subset proof")

        missing = [name for name in RELEASE_ALLOWLIST if not (self.source / name).is_file()]
        if missing:
            raise ReleaseError("required_artifact_missing",
                               f"allowlisted release file(s) absent from the source: {', '.join(missing)}")

        declared = {str(item.get("file")): str(item.get("sha256"))
                    for item in (proof.get("required_artifacts") or [])
                    if isinstance(item, Mapping)}
        expected = {str(name) for name in (proof.get("expected_artifact_filenames") or [])}
        allow = set(RELEASE_ALLOWLIST)
        # Neither side may widen the release on its own.
        surplus = sorted(expected - allow)
        if surplus:
            raise ReleaseError("unexpected_release_file",
                               "the manifest presents artifact(s) outside the supported release "
                               f"allowlist as trusted: {', '.join(surplus)}")
        shortfall = sorted(allow - expected)
        if shortfall:
            raise ReleaseError("release_set_incomplete",
                               "the manifest does not declare allowlisted release file(s): "
                               f"{', '.join(shortfall)}")
        if set(declared) | {SELF_UNHASHABLE} != expected:
            raise ReleaseError("release_set_incomplete",
                               "trusted_subset.required_artifacts and expected_artifact_filenames disagree")

        self._record("resolve_release_set", "passed",
                     allowlist=list(RELEASE_ALLOWLIST),
                     session_identity=proof.get("session_identity"),
                     producer_contract_version=manifest.get("producer_contract_version"),
                     detail=f"{len(RELEASE_ALLOWLIST)} allowlisted files agreed by the manifest")
        return {"manifest": manifest, "proof": proof, "declared": declared}

    # ------------------------------------------------------------------ 2. stage
    def stage(self, staging_parent: Path | None = None) -> Path:
        """Copy exactly the allowlisted files into a fresh temporary release directory.

        One file at a time, by exact name. No directory copy, no glob, no rsync-style
        mirror: an unrelated modified artifact in the source cannot reach the staging
        directory because nothing ever enumerates the source directory.
        """
        parent = staging_parent or self.rollback_root.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="release-staging-", dir=str(parent)))
        for name in RELEASE_ALLOWLIST:
            shutil.copy2(self.source / name, staging / name)
        self.staging_dir = staging
        self._record("stage_release", "passed", staging_dir=str(staging),
                     staged=list(RELEASE_ALLOWLIST),
                     detail=f"staged {len(RELEASE_ALLOWLIST)} allowlisted files")
        return staging

    # ------------------------------------------------------------------ 3. verify staging
    def verify_staged_hashes(self, release: Mapping[str, Any]) -> dict[str, str]:
        staging = self.staging_dir
        if staging is None:
            raise ReleaseError("verify_staged_hashes", "nothing has been staged")
        declared = release["declared"]
        staged = {name: sha256_file(staging / name) for name in RELEASE_ALLOWLIST}
        mismatches = [f"{name}: staged {staged[name][:12]}… != manifest {expected[:12]}…"
                      for name, expected in sorted(declared.items())
                      if staged.get(name) != expected]
        if mismatches:
            raise ReleaseError("manifest_hash_mismatch", "; ".join(mismatches))
        # The manifest is verified by identity with the source it was read from, since it is
        # the document the other hashes are checked against.
        if staged[SELF_UNHASHABLE] != sha256_file(self.source / SELF_UNHASHABLE):
            raise ReleaseError("manifest_hash_mismatch", f"{SELF_UNHASHABLE} changed while staging")
        self._record("verify_staged_hashes", "passed", staged_sha256=staged,
                     detail="every staged artifact matches the manifest")
        return staged

    def verify_session_identity(self, release: Mapping[str, Any]) -> str:
        """The sidecar, the bundle body and the manifest proof must name one session."""
        staging = self.staging_dir
        assert staging is not None
        proof = release["proof"]
        manifest = release["manifest"]
        session = proof.get("session_identity")
        problems: list[str] = []
        try:
            bundle = _load_json(staging / "analysis_bundle.json")
            focus = _load_json(staging / "focus_extract.json")
            sidecar = _load_json(staging / "statement_taxonomy_sidecar.json")
        except (OSError, ValueError) as exc:
            raise ReleaseError("session_mismatch", f"a staged artifact is not readable JSON: {exc}") from exc

        if bundle.get("reference_session_date") != session:
            problems.append(f"analysis_bundle.reference_session_date={bundle.get('reference_session_date')!r}")
        if focus.get("reference_session_date") != session:
            problems.append(f"focus_extract.reference_session_date={focus.get('reference_session_date')!r}")
        if sidecar.get("session_identity") != session:
            problems.append(f"statement_taxonomy_sidecar.session_identity={sidecar.get('session_identity')!r}")
        declared_sidecar = manifest.get("statement_taxonomy_sidecar")
        if not isinstance(declared_sidecar, Mapping) or declared_sidecar.get("present") is not True:
            problems.append("the manifest does not declare a present taxonomy sidecar")
        elif declared_sidecar.get("records_fingerprint") != sidecar.get("records_fingerprint"):
            problems.append("statement_taxonomy_sidecar.records_fingerprint differs from the manifest")
        elif declared_sidecar.get("session_identity") != session:
            problems.append("the manifest's sidecar session identity differs from the proof")
        if problems:
            raise ReleaseError("session_mismatch",
                               f"expected session {session!r}; " + "; ".join(problems))
        self._record("verify_session_identity", "passed", session_identity=session,
                     sidecar_authority=(declared_sidecar or {}).get("authority_level"),
                     detail="bundle, focus extract, taxonomy sidecar and manifest name one session")
        return str(session)

    def verify_consumer_proof(self) -> None:
        """Run the Consumer's own exact-session validator over the staged set."""
        staging = self.staging_dir
        assert staging is not None
        verify = load_consumer_validator(self.consumer_root)
        bundle_path = staging / "analysis_bundle.json"
        payload = _load_json(bundle_path)
        manifest = _load_json(staging / SELF_UNHASHABLE)
        ok, reason = verify(bundle_path, payload, manifest)
        if not ok:
            raise ReleaseError("consumer_exact_session_validation",
                               f"the Consumer rejected the staged release: {reason}")
        self._record("consumer_exact_session_validation", "passed",
                     validator="ai-core-private/builders/build_ticker_context.verify_exact_session_bundle",
                     detail="staged release verifies as exact-session")

    def verify_no_undeclared_trusted_artifact(self, release: Mapping[str, Any]) -> None:
        """Refuse a source that presents an undeclared file as part of the trusted set.

        Scoped to the trusted-artifact namespace on purpose. Unrelated modified generated
        artifacts in the source (screen_snapshot.csv, data/*.js, ...) are not part of the
        release and are not an error here; they are simply never staged.
        """
        expected = {str(name) for name in (release["proof"].get("expected_artifact_filenames") or [])}
        intruders = sorted(name for name in RELEASE_ALLOWLIST
                           if (self.source / name).is_file() and name not in expected)
        if intruders:
            raise ReleaseError("unexpected_release_file",
                               f"trusted artifact(s) present but undeclared: {', '.join(intruders)}")
        self._record("verify_trusted_namespace", "passed",
                     detail="no undeclared file is presented as part of the trusted release set")

    # ------------------------------------------------------------------ 4. rollback point
    def capture_rollback_point(self) -> dict[str, str | None]:
        before = self.destination_hashes()
        if not self.live:
            self._record("rollback_point", "skipped", current_live_sha256=before,
                         detail="dry run writes nothing")
            return before
        target = self.rollback_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for name in RELEASE_ALLOWLIST:
            live = self.destination / name
            if not live.is_file():
                continue
            shutil.copy2(live, target / name)
            if sha256_file(target / name) != before[name]:
                raise ReleaseError("rollback_point", f"the rollback copy of {name} does not match the live file")
            saved.append(name)
        atomic_write_json(target / "rollback_manifest.json", {
            "captured_at": _now(), "destination": str(self.destination),
            "saved": saved, "sha256": {k: v for k, v in before.items() if v},
            "absent_before_release": [k for k, v in before.items() if v is None],
        })
        self.rollback_dir = target
        self._record("rollback_point", "passed", rollback_dir=str(target), saved=saved,
                     current_live_sha256=before,
                     detail=f"previous live set copied and hash-verified into {target.name}")
        return before

    def restore(self) -> dict[str, Any]:
        if self.rollback_dir is None:
            return {"performed": False, "reason": "no rollback point was captured"}
        restored, removed, failed = [], [], []
        for name in RELEASE_ALLOWLIST:
            saved = self.rollback_dir / name
            live = self.destination / name
            try:
                if saved.is_file():
                    shutil.copy2(saved, live)
                    if sha256_file(live) != sha256_file(saved):
                        failed.append(name)
                    else:
                        restored.append(name)
                elif live.is_file():
                    # Absent before this release: leaving the new file behind would present a
                    # partial promotion as a complete release.
                    live.unlink()
                    removed.append(name)
            except OSError as exc:
                failed.append(f"{name} ({exc})")
        return {"performed": True, "restored": restored, "removed": removed,
                "verification_failed": failed, "from": str(self.rollback_dir)}

    # ------------------------------------------------------------------ 5. promote
    def promote(self) -> list[str]:
        """Move each verified staged file into place with os.replace.

        Every byte has already been written and hash-verified in the staging directory, so
        this loop performs no content generation and no partial write: each file appears at
        its destination path whole or not at all.
        """
        staging = self.staging_dir
        assert staging is not None
        promoted: list[str] = []
        for name in RELEASE_ALLOWLIST:
            os.replace(staging / name, self.destination / name)
            promoted.append(name)
            self.promoted = promoted
        self._record("promote_release", "passed", promoted=promoted,
                     detail=f"{len(promoted)} files promoted by atomic rename")
        return promoted

    def verify_destination(self, incoming: Mapping[str, str]) -> dict[str, str | None]:
        landed = self.destination_hashes()
        mismatches = [f"{name}: live {str(landed.get(name))[:12]}… != incoming {incoming[name][:12]}…"
                      for name in RELEASE_ALLOWLIST if landed.get(name) != incoming[name]]
        if mismatches:
            raise ReleaseError("post_promotion_verification", "; ".join(mismatches))
        self._record("verify_destination", "passed", live_sha256=landed,
                     detail="the destination now holds exactly the incoming release")
        return landed

    def verify_drift_preserved(self, before: Iterable[str], after: Iterable[str]) -> None:
        before_set, after_set = set(before), set(after)
        lost = sorted(before_set - after_set)
        gained = sorted(after_set - before_set)
        if lost or gained:
            raise ReleaseError("unrelated_drift_disturbed",
                               f"working-tree changes outside the allowlist moved: lost={lost}, gained={gained}")
        self._record("verify_drift_preserved", "passed",
                     unrelated_modified_paths=sorted(after_set),
                     detail=f"{len(after_set)} unrelated modified path(s) left exactly as found")

    # ------------------------------------------------------------------ 6. git
    def _git_bytes(self, *args: str) -> bytes:
        result = self.runner(["git", *args], cwd=str(self.destination), check=False,
                             capture_output=True)
        if result.returncode != 0:
            raise ReleaseError("git", f"git {' '.join(args)} failed")
        return result.stdout if isinstance(result.stdout, bytes) else str(result.stdout).encode()

    def verify_committed_bytes(self, incoming: Mapping[str, str]) -> None:
        """What git is about to publish must be the bytes we hash-verified.

        A checkout configured with `core.autocrlf` rewrites line endings on its way into
        the index, which silently changes an artifact's sha256 and leaves the published
        manifest describing a file nobody can reproduce. Comparing the staged blob against
        the incoming hash catches that before the commit exists.
        """
        mismatches = []
        for name in RELEASE_ALLOWLIST:
            blob = hashlib.sha256(self._git_bytes("cat-file", "blob", f":{name}")).hexdigest()
            if blob != incoming[name]:
                mismatches.append(name)
        if mismatches:
            raise ReleaseError(
                "git_content_normalization",
                "git would publish different bytes than were verified for "
                f"{', '.join(mismatches)}; mark them `-text` in .gitattributes so no "
                "end-of-line translation is applied to a hash-verified artifact")
        self._record("verify_committed_bytes", "passed",
                     detail="the staged blobs are byte-identical to the verified release")

    def git_publish(self, branch: str, incoming: Mapping[str, str] | None = None) -> dict[str, Any]:
        """Stage, commit and push exactly the allowlist.

        `git add -- <four exact paths>` and then an assertion that the staged set is a
        subset of the allowlist. No `git add -A`, no `git add .`, no pathspec glob: a
        modified file outside the allowlist cannot enter the index through this function.
        """
        self._git("add", "--", *RELEASE_ALLOWLIST)
        staged = sorted(line for line in self._git("diff", "--cached", "--name-only").splitlines() if line.strip())
        escaped = sorted(set(staged) - set(RELEASE_ALLOWLIST))
        if escaped:
            self._git("reset", "--", *staged, check=False)
            raise ReleaseError("git_stage_exceeded_allowlist",
                               f"staging reached outside the allowlist: {', '.join(escaped)}")
        if incoming:
            self.verify_committed_bytes(incoming)
        if not staged:
            self._record("git_publish", "skipped", detail="the release is already committed on this branch")
            return {"committed": False, "staged": [], "head": self._git("rev-parse", "HEAD")}
        message = self.commit_message or (
            "Publish StockLookup analysis release\n\n"
            "Exact-session artifact set only; unrelated generated-artifact drift in this\n"
            "working tree is deliberately not part of this commit."
        )
        self._git("commit", "-m", message)
        head = self._git("rev-parse", "HEAD")
        self._git("push", "origin", f"HEAD:{branch}")
        remote = self._git("ls-remote", "origin", f"refs/heads/{branch}").split()
        remote_head = remote[0] if remote else ""
        if remote_head != head:
            raise ReleaseError("git_push_verification",
                               f"origin/{branch}={remote_head or '(none)'} does not match the pushed commit {head}")
        state = publication_state_after_push(local_validation_pass=True)
        self._record("git_publish", "passed", branch=branch, commit=head, staged=staged,
                     state=state,
                     detail=f"pushed {len(staged)} file(s) to origin/{branch} and verified the remote SHA; state={GITHUB_SOURCE_UPDATED} not PUBLISHED")
        return {"committed": True, "staged": staged, "head": head, "branch": branch, "state": state}

    def git_preflight(self) -> str:
        top = self._git("rev-parse", "--show-toplevel")
        if Path(top).resolve() != self.destination.resolve():
            raise ReleaseError("git_preflight", f"the destination is not a git root: {top}")
        branch = self._git("branch", "--show-current")
        if not branch:
            raise ReleaseError("git_preflight", "the destination is not on a named branch")
        origin_url = self._git("remote", "get-url", "origin")
        head = self._git("rev-parse", "HEAD")
        try:
            origin_main = self._git("rev-parse", "origin/main")
        except Exception:
            origin_main = ""
        try:
            assert_producer_publisher_file(Path(__file__), role="publish_release")
            assert_runtime_root_identity(self.source)
            assert_web_checkout_identity(
                self.destination,
                backend_dir=self.source,
                origin_url=origin_url,
                branch=branch,
                head=head,
                origin_main=origin_main or None,
                live=self.live,
                git_toplevel=Path(top),
            )
        except ReleaseIdentityError as exc:
            raise ReleaseError("release_identity", str(exc)) from exc
        conflicts = self._git("diff", "--name-only", "--diff-filter=U")
        if conflicts:
            raise ReleaseError("git_preflight", f"the destination worktree has conflicts: {conflicts}")
        # Refuse before anything is staged or promoted: an index carrying someone else's
        # work would end up inside the release commit no matter how narrow our own add is.
        pre_staged = sorted(line for line in self._git("diff", "--cached", "--name-only").splitlines()
                            if line.strip())
        foreign = sorted(set(pre_staged) - set(RELEASE_ALLOWLIST))
        if foreign:
            raise ReleaseError("git_index_not_clean",
                               f"the destination index already holds non-release file(s): {', '.join(foreign)}")
        self._git("fetch", "origin", branch)
        relation = self._git("rev-list", "--left-right", "--count", f"HEAD...origin/{branch}")
        ahead, behind = (int(part) for part in relation.split())
        if ahead and behind:
            raise ReleaseError("git_preflight", f"local and origin/{branch} have diverged; refusing to merge")
        if behind:
            raise ReleaseError(
                "git_preflight",
                f"HEAD != origin/{branch} before release mutation (behind {behind}); refusing to pull as part of live publish",
            )
        self._record("git_preflight", "passed", branch=branch, ahead=ahead, behind=behind,
                     head=self._git("rev-parse", "HEAD"),
                     detail=f"destination is on {branch}, HEAD matches origin/{branch}")
        return branch

    # ------------------------------------------------------------------ 7. live verification
    def verify_live_served(self, incoming: Mapping[str, str]) -> dict[str, Any]:
        """Fetch the published artifacts from the serving origin and compare hashes."""
        assert self.verify_live_url
        deadline = time.monotonic() + self.verify_live_timeout
        attempt, observed = 0, {}
        while True:
            attempt += 1
            observed = {}
            for name in RELEASE_ALLOWLIST:
                url = f"{self.verify_live_url}/{name}"
                try:
                    observed[name] = hashlib.sha256(self.opener(url)).hexdigest()
                except (urllib.error.URLError, OSError, TimeoutError) as exc:
                    observed[name] = f"unreachable: {exc}"
            if all(observed[name] == incoming[name] for name in RELEASE_ALLOWLIST):
                self._record("verify_live_served", "passed", url=self.verify_live_url,
                             attempts=attempt, served_sha256=observed,
                             detail="the serving origin returns exactly the published release")
                return {"verified": True, "served_sha256": observed, "attempts": attempt}
            if time.monotonic() >= deadline:
                self._record("verify_live_served", "failed", url=self.verify_live_url,
                             attempts=attempt, served_sha256=observed,
                             detail="the serving origin did not converge on the published release")
                return {"verified": False, "served_sha256": observed, "attempts": attempt}
            time.sleep(20)

    # ------------------------------------------------------------------ report
    def dry_run_report(self, release: Mapping[str, Any], incoming: Mapping[str, str],
                       current: Mapping[str, str | None], excluded: Iterable[str]) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "destination": str(self.destination),
            "files_to_publish": list(RELEASE_ALLOWLIST),
            "current_destination_sha256": dict(current),
            "incoming_sha256": dict(incoming),
            "unchanged": sorted(name for name in RELEASE_ALLOWLIST if current.get(name) == incoming[name]),
            "explicitly_excluded": sorted(excluded),
            "rollback_source": str(self.rollback_root),
            "session_identity": release["proof"].get("session_identity"),
            "git_branch": None,
        }

    def report(self, outcome: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "schema_version": "1.0.0",
            "command": "tools/publish_release.py",
            "mode": "live" if self.live else "dry_run",
            "outcome": outcome,
            "started_at": self.started_at,
            "ended_at": _now(),
            "allowlist": list(RELEASE_ALLOWLIST),
            "steps": self.steps,
            **payload,
        }
        return payload


def excluded_modified_files(destination: Path, runner: Callable[..., Any] = subprocess.run) -> list[str]:
    """Modified/untracked paths in the destination that this publisher deliberately skips."""
    result = runner(["git", "status", "--porcelain"], cwd=str(destination), check=False,
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return []
    return sorted(set(porcelain_paths(result.stdout or "")) - set(RELEASE_ALLOWLIST))


def run_publication(publisher: ReleasePublisher) -> tuple[int, dict[str, Any]]:
    branch: str | None = None
    try:
        release = publisher.resolve_release()
        publisher.verify_no_undeclared_trusted_artifact(release)
        if publisher.use_git:
            branch = publisher.git_preflight()
        drift_before = publisher.foreign_worktree_state()
        current = publisher.destination_hashes()
        publisher.stage()
        incoming = publisher.verify_staged_hashes(release)
        publisher.verify_session_identity(release)
        publisher.verify_consumer_proof()

        excluded = excluded_modified_files(publisher.destination, publisher.runner) if publisher.use_git else []
        if not publisher.live:
            plan = publisher.dry_run_report(release, incoming, current, excluded)
            plan["git_branch"] = branch
            publisher._record("dry_run_plan", "passed",
                              detail="verified only; nothing was copied, committed or pushed")
            return 0, publisher.report("dry_run_ok", {"plan": plan})

        if all(current.get(name) == incoming[name] for name in RELEASE_ALLOWLIST):
            publisher._record("idempotent_republish", "passed", live_sha256=current,
                              detail="the destination already holds this exact release; no file was rewritten")
            git_result = (publisher.git_publish(branch, incoming)
                          if publisher.use_git and branch else {"committed": False})
            # The destination already holding these bytes says nothing about what the
            # serving origin returns, so this check is not skipped on the idempotent path.
            served = publisher.verify_live_served(incoming) if publisher.verify_live_url else None
            if served is not None and not served["verified"]:
                raise ReleaseError("verify_live_served",
                                   "the serving origin did not converge on the published release")
            return 0, publisher.report("already_current", {
                "previous_sha256": dict(current), "live_sha256": dict(current),
                "excluded": excluded, "git": git_result, "served": served, "rollback": None})

        publisher.capture_rollback_point()
        publisher.promote()
        live = publisher.verify_destination(incoming)
        publisher.verify_drift_preserved(drift_before, publisher.foreign_worktree_state())
        git_result = (publisher.git_publish(branch, incoming)
                      if publisher.use_git and branch else {"committed": False})
        served = publisher.verify_live_served(incoming) if publisher.verify_live_url else None
        if served is not None and not served["verified"]:
            raise ReleaseError("verify_live_served",
                               "the serving origin did not converge on the published release")
        return 0, publisher.report("published", {
            "previous_sha256": dict(current), "live_sha256": dict(live),
            "excluded": excluded, "git": git_result, "served": served,
            "rollback": str(publisher.rollback_dir) if publisher.rollback_dir else None})
    except ReleaseError as exc:
        publisher._record(exc.gate, "failed", detail=exc.detail)
        rollback = publisher.restore() if publisher.live else {"performed": False,
                                                               "reason": "dry run changed nothing"}
        if rollback.get("performed"):
            print(f"[release] restored the previous artifact set from {rollback['from']}", file=sys.stderr)
            if rollback.get("verification_failed"):
                print(f"[release] RESTORE VERIFICATION FAILED for: {rollback['verification_failed']}",
                      file=sys.stderr)
        print(f"[release] FAILED at {exc.gate}: {exc.detail}", file=sys.stderr)
        return 1, publisher.report("failed", {"failed_gate": exc.gate, "failure_detail": exc.detail,
                                              "rollback": rollback})
    finally:
        if publisher.staging_dir and publisher.staging_dir.is_dir():
            shutil.rmtree(publisher.staging_dir, ignore_errors=True)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="Runtime root holding the generated release.")
    parser.add_argument("--destination", required=True,
                        help="Authoritative Dashboard checkout that is actually served.")
    parser.add_argument("--live", action="store_true", help="Promote, commit and push for real.")
    parser.add_argument("--no-git", action="store_true",
                        help="Filesystem promotion only; do not touch git in the destination.")
    parser.add_argument("--rollback-root", type=Path, default=None)
    parser.add_argument("--consumer-root", type=Path, default=None)
    parser.add_argument("--verify-live-url", default=None,
                        help="Base URL of the serving origin; published hashes are re-verified over HTTP.")
    parser.add_argument("--verify-live-timeout", type=int, default=600)
    parser.add_argument("--commit-message", default=None)
    parser.add_argument("--json-report", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    source = args.source.expanduser().resolve() if isinstance(args.source, Path) else Path(args.source).expanduser().resolve()
    destination = Path(args.destination).expanduser().resolve()
    for label, path in (("source", source), ("destination", destination)):
        if not path.is_dir():
            print(f"[release] {label} directory does not exist: {path}", file=sys.stderr)
            return 2
    if source == destination:
        print("[release] source and destination are the same directory; there is nothing to publish",
              file=sys.stderr)
        return 2

    publisher = ReleasePublisher(
        source, destination, live=args.live,
        rollback_root=args.rollback_root, consumer_root=args.consumer_root,
        use_git=not args.no_git, verify_live_url=args.verify_live_url,
        verify_live_timeout=args.verify_live_timeout, commit_message=args.commit_message,
    )
    print(f"[release] === publish_release {'LIVE' if args.live else 'DRY-RUN (read-only)'} ===")
    print(f"[release] source={source}")
    print(f"[release] destination={destination}")
    code, payload = run_publication(publisher)
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.json_report, payload)
        print(f"[release] report -> {args.json_report}")
    if payload.get("outcome") == "dry_run_ok":
        plan = payload["plan"]
        print("\n[release] --- publication plan ---")
        print(f"  source                : {plan['source']}")
        print(f"  destination           : {plan['destination']}")
        print(f"  git branch            : {plan['git_branch']}")
        print(f"  session identity      : {plan['session_identity']}")
        print(f"  rollback source       : {plan['rollback_source']}")
        print("  files to publish      :")
        for name in plan["files_to_publish"]:
            current = plan["current_destination_sha256"].get(name)
            print(f"    {name}")
            print(f"        current  : {current or '(absent)'}")
            print(f"        incoming : {plan['incoming_sha256'][name]}")
        print(f"  unchanged             : {', '.join(plan['unchanged']) or '(none)'}")
        print(f"  explicitly excluded   : {len(plan['explicitly_excluded'])} modified path(s) "
              "in the destination that this publisher will not touch")
        for name in plan["explicitly_excluded"]:
            print(f"    - {name}")
        print("\n[release] DRY RUN — nothing was copied, committed or pushed. Re-run with --live.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
