"""Explicit offline location proofs. Storage location adds no historical authority.

Proofs are pinned by their native SHA in an operator-controlled catalog/reference.
There is no directory substitution, downloader, scheduler or retirement operation.
"""
from __future__ import annotations

import json
import os
import ctypes
import shutil
from pathlib import Path

from tools import vault_snapshot as vault

SCHEMA = "stocklookup_storage_location/v1"
MAX_BYTES = 64 * 1024 * 1024


def immutable_candidate(path):
    path = Path(path)
    vault.require(not path.is_symlink() and path.suffix.lower() not in {
        ".db", ".sqlite", ".sqlite3", ".lock", ".tmp", ".partial"}
        and not path.name.lower().endswith(("-wal", "-shm", "-journal"))
        and not any(part.lower() in {"accumulators", "journals", "caches", "cache", ".git", "data"}
                    for part in path.parts), "MUTABLE_OR_UNQUALIFIED_STORAGE_CANDIDATE")


def qualify_volume(path, expected, *, observer=None):
    observer = observer or vault.native_volume
    try:
        vault.require(Path(path).exists() and expected.get("healthy") is True
                      and observer(Path(path)) == expected, "ARCHIVE_VOLUME_UNAVAILABLE_OR_WRONG")
    except OSError as exc:
        raise vault.Refused("ARCHIVE_VOLUME_UNAVAILABLE_OR_WRONG") from exc


def capacity_admission(profile, *, staging_bytes, writer_bytes, observer=None,
                       usage=shutil.disk_usage, writable=None):
    """Independent system/workload reserves; no disk substitution or writer admission."""
    vault.require(type(staging_bytes) is int and staging_bytes >= 0
                  and type(writer_bytes) is int and writer_bytes >= 0, "capacity request invalid")
    vault.require(profile["system"]["volume"]["id"] != profile["workload"]["volume"]["id"],
                  "system and workload volumes must be distinct")
    rows = {}
    for role in ("system", "workload"):
        spec = profile[role]
        path = Path(spec["path"])
        qualify_volume(path, spec["volume"], observer=observer)
        reserve = spec["reserve_bytes"]
        vault.require(type(reserve) is int and reserve >= (25 if role == "system" else 140) * 1024**3,
                      "capacity reserve below foundation floor")
        required = reserve + (staging_bytes + writer_bytes if role == "workload" else 0)
        free = usage(path).free
        vault.require(free >= required, "INSUFFICIENT_CAPACITY:" + role)
        vault.require((writable or writable_directory)(path), "WORKLOAD_NOT_WRITABLE:" + role)
        rows[role] = dict(free_bytes=free, required_bytes=required)
    return rows


def writable_directory(path):
    """Request directory create rights without creating a file or changing ACLs."""
    if os.name != "nt":
        return os.access(path, os.W_OK | os.X_OK)
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(Path(path).resolve()), 0x0006, 7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        return False
    kernel.CloseHandle(handle)
    return True


def _read_proof(reference):
    path = Path(reference["path"])
    vault.require(path.stat().st_size <= 1024 * 1024, "storage proof too large")
    raw = path.read_bytes()
    vault.require(vault.digest(raw) == reference["sha256"], "INVALID_STORAGE_PROOF")
    proof = json.loads(raw)
    vault.require(proof.get("schema") == SCHEMA, "INVALID_STORAGE_PROOF_SCHEMA")
    return proof


def verify_location(reference, *, original_path, artifact_identity, session,
                    observer=None):
    """Verify the pinned registration and current bytes, never infer a new identity."""
    proof = _read_proof(reference)
    vault.require(proof["original_path"] == str(original_path)
                  and proof["artifact_identity"] == artifact_identity and proof["session"] == session,
                  "STORAGE_ORIGINAL_IDENTITY_MISMATCH")
    target = Path(proof["location"])
    qualify_volume(target, proof["volume"], observer=observer)
    with vault.locked_file(target):
        before = vault.fingerprint(target)
        vault.require(before == proof["location_fingerprint"] and target.stat().st_size == proof["bytes"]
                      and vault.sha(target) == proof["sha256"]
                      and vault.fingerprint(target) == before, "STORAGE_CONTENT_OR_FINGERPRINT_CHANGED")
        qualify_volume(target, proof["volume"], observer=observer)
    return target, proof


def register_copy(original, location, receipt_path, *, artifact_identity, session,
                  expected_volume, provenance, observer=None, max_bytes=MAX_BYTES,
                  t0_reference=None):
    """Register an already copied immutable file while original provenance is observable.

    T0 qualification is granted only after the existing original seal verifier passes.
    Registration never rewrites the original, index, manifest or write receipt.
    """
    original, location = Path(original), Path(location)
    immutable_candidate(original)
    immutable_candidate(location)
    vault.require(original.is_absolute() and location.is_absolute() and original != location,
                  "explicit distinct original/location required")
    vault.require(artifact_identity and session and provenance, "original provenance required")
    vault.require(original.stat().st_size <= max_bytes, "registration byte budget exceeded")
    qualify_volume(location, expected_volume, observer=observer)
    with vault.locked_file(original), vault.locked_file(location):
        original_fp, location_fp = vault.fingerprint(original), vault.fingerprint(location)
        digest = vault.sha(original)
        vault.require(vault.sha(location) == digest, "copy content differs")
        t0 = None
        if t0_reference is not None:
            import prospective_t0_seal_index as seals
            bindings = seals.load_verified(t0_reference, expected_snapshot_identity=artifact_identity, session=session)
            vault.require(bindings is not None, "original T0 provenance unqualified")
            index_path = Path(t0_reference["path"])
            vault.require(original == index_path.parent / "prospective_decision_snapshot.json",
                          "T0 original path mismatch")
            receipt = index_path.parent / "prospective_t0_snapshot_write_receipt.json"
            t0 = dict(reference=dict(t0_reference), index_sha256=vault.sha(index_path),
                      receipt_sha256=vault.sha(receipt), original_fingerprint=seals.fingerprint(original))
        vault.require(vault.fingerprint(original) == original_fp and vault.fingerprint(location) == location_fp,
                      "registration source changed")
        proof = dict(schema=SCHEMA, original_path=str(original), artifact_identity=artifact_identity,
                     session=session, provenance=provenance, location=str(location), volume=expected_volume,
                     bytes=original_fp["size"], sha256=digest, original_fingerprint=original_fp,
                     location_fingerprint=location_fp, t0=t0, authority_effect="NONE")
        raw = vault.canonical(proof)
        vault.publish(Path(receipt_path), raw)
    return dict(path=str(receipt_path), sha256=vault.digest(raw))


def restore_registered(entry, vault_root, staging_root, receipt_path, *, expected_archive_volume,
                       expected_hot_volume, observer=None, max_bytes=MAX_BYTES):
    """Explicit staged copy from an exact pinned Vault V1 manifest; no production writes.

    Returns a storage-only proof. T0 needs separate original qualification; restore
    bytes alone cannot manufacture an original native fingerprint or T0 authority.
    """
    archive, stage = Path(vault_root), Path(staging_root)
    qualify_volume(archive, expected_archive_volume, observer=observer)
    qualify_volume(stage, expected_hot_volume, observer=observer)
    locator = entry["vault"]
    vault.require(locator["volume_id"] == expected_archive_volume["id"], "catalog volume mismatch")
    manifest = vault.read_manifest(vault.safe_path(archive, locator["manifest_path"]), locator["manifest_sha256"])
    vault.require(manifest["volumes"]["destination"] == expected_archive_volume
                  and manifest["plan_sha256"] == locator["snapshot_identity"]
                  and manifest["session_identity"] == entry["session_identity"], "archive manifest binding invalid")
    matches = [r for r in manifest["files"] if r["relative_path"] == entry["relative_path"]
               and r["vault_path"] == locator["object_path"]]
    vault.require(len(matches) == 1, "archive exact path missing/ambiguous")
    row = matches[0]
    immutable_candidate(row["relative_path"])
    vault.require(row["sha256"] == entry["sha256"] == locator["object_sha256"]
                  and row["size"] == entry["original_size"] <= max_bytes, "archive bytes/budget mismatch")
    source = vault.safe_path(archive, row["vault_path"])
    target = vault.safe_path(stage, entry["relative_path"])
    vault.require(not target.exists(), "restore destination already exists")
    original = str(Path(manifest["source_root"]) / entry["relative_path"])
    t0 = None
    if entry.get("archive_location"):
        registered, original_proof = verify_location(entry["archive_location"], original_path=original,
            artifact_identity=entry["artifact_identity"], session=entry["session_identity"], observer=observer)
        vault.require(registered.resolve() == source.resolve() and original_proof["sha256"] == row["sha256"],
                      "archive original registration mismatch")
        t0 = original_proof.get("t0")
    with vault.locked_file(source):
        vault.require(vault.sha(source) == row["sha256"], "archive object corrupt")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive destination; no replacement, symlinks or transparent fallback.
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        vault.require(vault.sha(target) == row["sha256"], "restore content differs")
        qualify_volume(stage, expected_hot_volume, observer=observer)
        qualify_volume(archive, expected_archive_volume, observer=observer)
    proof = dict(schema=SCHEMA, original_path=original, artifact_identity=entry["artifact_identity"],
                 session=entry["session_identity"], provenance=dict(locator), location=str(target),
                 volume=expected_hot_volume, bytes=row["size"], sha256=row["sha256"],
                 original_fingerprint=row["source_fingerprint"], location_fingerprint=vault.fingerprint(target),
                 t0=t0, authority_effect="NONE")
    raw = vault.canonical(proof)
    vault.publish(Path(receipt_path), raw)
    return dict(path=str(receipt_path), sha256=vault.digest(raw))
