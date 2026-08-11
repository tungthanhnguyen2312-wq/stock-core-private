"""trusted_subset_contract.py — post-copy verification that a publisher never commits a
member of the exact-session trusted subset out of sync with its manifest.

Why this exists: the trusted subset (analysis_bundle.json, bundle_manifest.json,
focus_extract.json, statement_taxonomy_sidecar.json) is owned as one hash-verified,
atomically-published unit by tools/publish_release.py — see
docs/exact_session_bundle_contract.md. publish_dashboard.py independently copies
analysis_bundle.json as part of its own, unrelated screener-data whitelist. If
publish_dashboard.py ever runs --live without tools/publish_release.py having placed a
matching bundle_manifest.json first (a missed step, a race, or someone invoking it
directly), the destination ends up with a NEW analysis_bundle.json sitting next to the OLD
manifest that still names the OLD file's hash — a mixed release. This is exactly what
happened in commit fbaf1fe (2026-08-05): bundle_manifest.json's trusted_subset still
pointed at the 2026-08-03 bundle while analysis_bundle.json had been replaced with the
2026-08-04 one, and 7 of 9 tests/release-smoke.test.js assertions failed in CI as a direct,
mechanical result.

This module is the defense-in-depth half of the fix: publish_dashboard.py calls it on the
post-copy WEB_ROOT, right before its own git add/commit/push, and refuses to commit if any
present trusted-subset member disagrees with the manifest. The other half — making
sync_and_publish.bat invoke tools/publish_release.py for the full trusted subset before
publish_dashboard.py runs at all — is what keeps this gate from firing in normal operation;
this module is what stops publish_dashboard.py from ever repeating the mistake even if
invoked out of that sequence.

Deliberately dependency-light (stdlib only, no cross-repo import) so both copies of
publish_dashboard.py (stock-core-private and the dashboard worktree) can use it directly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

#: The exact-session release set tools/publish_release.py owns. Static and matching
#: RELEASE_ALLOWLIST there on purpose — this module does not invent its own list.
TRUSTED_SUBSET_ARTIFACTS = ("analysis_bundle.json", "bundle_manifest.json",
                            "focus_extract.json", "statement_taxonomy_sidecar.json")
#: bundle_manifest.json cannot hash itself — same rule as tools/publish_release.py.
SELF_UNHASHABLE = "bundle_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class TrustedSubsetReport:
    ready: bool
    checked: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def render(self) -> list[str]:
        lines = [
            f"TRUSTED_SUBSET_CHECKED={','.join(self.checked) if self.checked else '(none present)'}",
            f"TRUSTED_SUBSET_READY={'YES' if self.ready else 'NO'}",
        ]
        if not self.ready:
            lines.append("TRUSTED_SUBSET_MISMATCH:")
            lines.extend(f"  {p}" for p in self.problems)
        return lines


def verify_trusted_subset(root: Path | str, *, scope: Iterable[str] = TRUSTED_SUBSET_ARTIFACTS) -> TrustedSubsetReport:
    """Verify the trusted-subset artifacts named in `scope` hash to exactly what
    root/bundle_manifest.json's trusted_subset proof declares for them.

    `scope` is which members of the trusted subset THIS caller is responsible for.
    publish_dashboard.py passes ``scope=("analysis_bundle.json",)`` — the only trusted-
    subset member it ever copies — so an unrelated stale/undeclared sibling (e.g. a
    statement_taxonomy_sidecar.json left over from a prior session, which
    tools/publish_release.py's own manifest may legitimately exclude via
    `statement_taxonomy_sidecar.present: false` when a session mismatch makes the export
    ignore it) never blocks an otherwise-unrelated screener-data commit that has nothing
    to do with it. A general caller auditing the whole release (the default `scope`) still
    catches that same file as an undeclared intruder — that is tools/publish_release.py's
    own concern, not a false negative here.

    When the manifest declares its own release set (`expected_artifact_filenames`), every
    declared name within `scope` MUST exist — a missing declared artifact is exactly as
    much a mixed/incomplete release as a hash mismatch. A manifest from an older/partial
    schema with no declared set still gets *some* protection: whichever in-scope
    trusted-subset artifacts merely happen to be present are hash-checked, never silently
    skipped. If bundle_manifest.json itself is absent, there is nothing to verify against
    and the check passes vacuously (a root with no trusted subset at all is not this
    contract's concern — see release_session_contract.py for whether a release session can
    be resolved at all).
    """
    root = Path(root)
    scope_set = set(scope)
    manifest_path = root / "bundle_manifest.json"
    if not manifest_path.is_file():
        return TrustedSubsetReport(ready=True, checked=[], problems=[])

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return TrustedSubsetReport(ready=False, checked=[SELF_UNHASHABLE],
                                    problems=[f"bundle_manifest.json is not readable JSON: {exc}"])
    if not isinstance(manifest, Mapping):
        return TrustedSubsetReport(ready=False, checked=[SELF_UNHASHABLE],
                                    problems=["bundle_manifest.json does not contain a JSON object"])

    proof = manifest.get("trusted_subset")
    if not isinstance(proof, Mapping):
        return TrustedSubsetReport(ready=False, checked=[SELF_UNHASHABLE],
                                    problems=["bundle_manifest.json carries no trusted_subset proof"])

    declared_hashes = {str(item.get("file")): str(item.get("sha256"))
                       for item in (proof.get("required_artifacts") or [])
                       if isinstance(item, Mapping)}
    expected_names = {str(name) for name in (proof.get("expected_artifact_filenames") or [])}

    names_to_check = sorted(expected_names & scope_set) if expected_names else \
        [name for name in TRUSTED_SUBSET_ARTIFACTS if name in scope_set and (root / name).is_file()]

    checked: list[str] = []
    problems: list[str] = []
    for name in names_to_check:
        path = root / name
        checked.append(name)
        if not path.is_file():
            problems.append(f"{name} is declared in the manifest's trusted subset but missing from {root}")
            continue
        if name == SELF_UNHASHABLE:
            continue
        expected_hash = declared_hashes.get(name)
        if expected_hash is None:
            problems.append(f"{name} is present but not declared in trusted_subset.required_artifacts")
            continue
        actual = sha256_file(path)
        if actual != expected_hash:
            problems.append(f"{name} sha256={actual} does not match manifest-declared {expected_hash}")

    # An undeclared trusted-namespace file sitting next to a declared release set is also
    # a defect (mirrors tools/publish_release.py::verify_no_undeclared_trusted_artifact) —
    # only meaningful once the manifest has declared what the set should be, and only for
    # names within this caller's own scope.
    if expected_names:
        for name in TRUSTED_SUBSET_ARTIFACTS:
            if name not in scope_set or name in expected_names or name in checked:
                continue
            if (root / name).is_file():
                checked.append(name)
                problems.append(f"{name} is present but not declared in "
                                 "trusted_subset.expected_artifact_filenames")

    return TrustedSubsetReport(ready=not problems, checked=checked, problems=problems)
