"""Bounded exact-path offline qualification. No production mutation interface."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import tempfile

from tools import vault_snapshot as v
from tools.vault_retention import unique_allocation

PROTECTED = ("prospective-decision-retention-v1", "thesis-evidence-t0-v1", "prospective-pit-capture-v1",
             "prospective-calendar-evidence-v1", "official-corporate-event-raw-store",
             "tactical-reversal-prospective-shadow-collection-v1", "integrated-investment-decision-product-v1",
             "_stream", "_artifact_summary_cache", "_settled_cache", "seal", "receipt",
             "handoff", "run_manifest", "p3f9b_mva_exact_session_snapshot")


def protected(relative):
    lower = relative.casefold()
    return (lower.startswith(("config/", "data/", "dashboard-runtime/"))
            or any(token in lower for token in PROTECTED))


def plan(source: Path, vault: Path, proposal: dict, proposal_sha: str, manifest: Path,
         manifest_sha: str, expected: dict, *, observer=v.native_volume, max_bytes=64*v.CHUNK):
    """Verify only declared paths; never scan, delete, convert, or infer dependency closure."""
    v.require(v.digest(v.canonical(proposal)) == proposal_sha, "proposal tampered")
    v.require(proposal.get("schema") == "capacity_exact_path_proposal/v1", "proposal schema")
    v.require(isinstance(proposal.get("keep_sessions"), list) and len(proposal["keep_sessions"]) >= 3,
              "current and previous two sessions required")
    v.require(manifest.absolute().is_relative_to(vault.absolute()), "manifest outside vault")
    v.safe_path(vault, manifest.absolute().relative_to(vault.absolute()).as_posix())
    volumes = v.verify_volumes(source, vault, expected, observer)
    retained = v.read_manifest(manifest, manifest_sha)
    v.require(retained["volumes"] == volumes and retained["source_root"] == str(source.absolute()),
              "snapshot source/volume mismatch")
    coverage = {r["relative_path"]: r for r in retained["files"]}
    rows, allocations, seen, charged = [], [], set(), 0
    for candidate in sorted(proposal.get("candidates", []), key=lambda r: r["relative_path"]):
        rel = candidate["relative_path"]
        path = v.safe_path(source, rel)
        v.require(rel.casefold() not in seen, "duplicate candidate")
        seen.add(rel.casefold())
        group = candidate.get("group")
        reasons = []
        if group not in {"G1", "G2", "G3", "G5"}: reasons.append("GROUP_DEFERRED_OR_UNKNOWN")
        if protected(rel): reasons.append("PROTECTED_EVIDENCE")
        if candidate.get("session_identity") in proposal["keep_sessions"]: reasons.append("RECENT_SESSION")
        if not candidate.get("session_identity") or not candidate.get("artifact_identity"):
            reasons.append("IDENTITY_UNKNOWN")
        closure = candidate.get("reader_dependency_closure")
        if not isinstance(closure, dict) or closure.get("status") != "VERIFIED" or not closure.get("proof_sha256"):
            reasons.append("DEPENDENCY_CLOSURE_UNKNOWN")
        elif any(closure.get(k) != [] for k in ("runtime", "code", "manifest", "cross_session", "external")):
            reasons.append("ACTIVE_OR_UNKNOWN_DEPENDENCY")
        if not candidate.get("restore_procedure") or not candidate.get("restore_preconditions"):
            reasons.append("RESTORE_PREREQUISITES_UNKNOWN")
        # A declared immutable flag does not prove every future writer's lifecycle.
        if group == "G1": reasons.append("HARDLINK_WRITE_LIFECYCLE_UNPROVEN")
        row = dict(candidate, reasons=reasons, execute=False, deletion_authorized=False,
                   potential_allocation_bytes=0, eligible=False)
        covered = coverage.get(rel)
        if reasons or covered is None:
            if covered is None: reasons.append("VERIFIED_VAULT_COVERAGE_MISSING")
            rows.append(row)
            continue
        object_path = v.safe_path(vault, covered["vault_path"])
        v.require(path.is_file() and object_path.is_file(), "covered source/object missing")
        charged += covered["size"] * 2
        v.require(charged <= max_bytes, "dual verification byte ceiling")
        with ExitStack() as stack:
            stack.enter_context(v.locked_file(path))
            stack.enter_context(v.locked_file(object_path))
            before = v.fingerprint(path)
            object_before = v.fingerprint(object_path)
            v.require(before == covered["source_fingerprint"] and object_before == covered["vault_fingerprint"],
                      "snapshot fingerprint drift")
            v.require(v.sha(path) == v.sha(object_path) == covered["sha256"], "vault/source native bytes differ")
            v.require(v.fingerprint(path) == before and v.fingerprint(object_path) == object_before,
                      "concurrent mutation")
        second = candidate.get("second_copy")
        if second != "OWNER_ACCEPTED_SINGLE_COPY":
            reasons.append("SECOND_COPY_NOT_QUALIFIED")
        if before["links"] != 1: reasons.append("LINK_CLOSURE_REQUIRED")
        row.update(source_fingerprint=before, vault_fingerprint=object_before,
                   vault_manifest_sha256=manifest_sha, sha256=covered["sha256"],
                   eligible=not reasons,
                   potential_allocation_bytes=before["physical_bytes"] if not reasons else 0)
        allocations.append(dict(volume=volumes["source"]["id"], **before))
        rows.append(row)
    v.require(v.verify_volumes(source, vault, expected, observer) == volumes, "volume changed")
    v.require(v.sha(manifest) == manifest_sha, "manifest changed")
    return dict(schema="capacity_offline_plan/v1", proposal_sha256=proposal_sha,
                vault_manifest_sha256=manifest_sha, candidates=rows,
                physical_accounting=unique_allocation(allocations), dual_hash_input_bytes=charged,
                potential_allocation_bytes=sum(r["potential_allocation_bytes"] for r in rows),
                reclaimed_bytes=0, production_apply_implemented=False, authority_effect="NONE")


def rehearsal(payload: bytes):
    """Apply/undo/restore mechanics only in a tool-created temporary tree, never caller paths.

    This is not qualification of any production writer or archival action.
    """
    v.require(isinstance(payload, bytes) and len(payload) <= v.CHUNK, "synthetic ceiling")
    with tempfile.TemporaryDirectory(prefix="capacity-synthetic-") as folder:
        root = Path(folder)
        canonical, alias, cold = (root / name for name in ("canonical", "alias", "vault"))
        canonical.write_bytes(payload)
        alias.write_bytes(payload)
        old = v.fingerprint(alias)
        staged = root / "link-stage"
        os.link(canonical, staged)
        os.replace(staged, alias)
        linked = canonical.stat().st_ino == alias.stat().st_ino
        consumers = canonical.read_bytes() == alias.read_bytes() == payload
        # Reversible split uses a fresh inode, never writes through the linked alias.
        split = root / "split-stage"
        shutil.copyfile(canonical, split)
        os.utime(split, ns=(old["mtime_ns"], old["mtime_ns"]))
        os.replace(split, alias)
        independent = canonical.stat().st_ino != alias.stat().st_ino
        shutil.copyfile(alias, cold)
        expected_sha = v.sha(cold)
        alias.unlink()  # isolated synthetic file only
        shutil.copyfile(cold, root / "restore-stage")
        v.require(v.sha(root / "restore-stage") == expected_sha, "restore corruption")
        os.replace(root / "restore-stage", alias)
        return dict(linked=linked, independent_consumer_read=consumers, undo_independent=independent,
                    restored=alias.read_bytes() == payload, production_mutation=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha", required=True)
    parser.add_argument("--volumes", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=64*v.CHUNK)
    args = parser.parse_args()
    v.require(args.vault.absolute().drive.upper() == "W:", "explicit W destination required")
    result = plan(args.source, args.vault, json.loads(args.proposal.read_bytes()), args.proposal_sha,
                  args.manifest, args.manifest_sha, json.loads(args.volumes.read_bytes()), max_bytes=args.max_bytes)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
