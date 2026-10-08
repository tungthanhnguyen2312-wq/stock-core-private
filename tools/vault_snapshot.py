"""Opt-in offline snapshots. No acquisition, source writes, cleanup, or Daily integration."""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
from typing import Callable

CHUNK = 1024 * 1024
SCHEMA = "stocklookup_vault_snapshot/v1"
ELIGIBLE = {"IMMUTABLE_SESSION", "RAW_EVIDENCE", "T0"}


class Refused(ValueError):
    """An explicit proof is missing or contradicted; no completion is published."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def safe_path(root: Path, relative: str) -> Path:
    p = PurePosixPath(relative)
    require(bool(relative) and not p.is_absolute() and ".." not in p.parts
            and "\\" not in relative and ":" not in relative, "unsafe relative path")
    reserved = {"CON", "PRN", "AUX", "NUL", *["COM" + str(i) for i in range(1, 10)],
                *["LPT" + str(i) for i in range(1, 10)]}
    require(p.parts and all(not part.endswith((".", " ")) and part.split(".")[0].upper() not in reserved
                            for part in p.parts), "aliased/reserved path")
    root = root.absolute()
    target = root.joinpath(*p.parts)
    for node in [root, *root.parents, target, *target.parents]:
        require(not node.is_symlink() and not getattr(node, "is_junction", lambda: False)(),
                "symlink/junction path refused")
        if node.exists():
            require(not (getattr(node.stat(), "st_file_attributes", 0) & 0x400),
                    "reparse point refused")
    return target


def publish(path: Path, data: bytes):
    """Exclusive immutable publication; an interrupted staging file is never a receipt."""
    if path.exists():
        require(path.read_bytes() == data, "immutable destination conflict")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_name(path.name + ".publishing")
    with stage.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    # link is an exclusive same-volume publish, not a hardlink to the source.
    os.link(stage, path)
    stage.unlink()  # only tool-owned destination staging, never source evidence


@contextmanager
def locked_file(path: Path, *, writer=False):
    """Windows deny-write/delete source handle; exclusive destination writer handle."""
    if os.name == "nt":
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        handle = kernel.CreateFileW(str(path), 0xC0000000 if writer else 0x80000000,
                                    0 if writer else 1, None, 4 if writer else 3, 0x80, None)
        require(handle != ctypes.c_void_p(-1).value, "writer exclusivity unavailable")
        fd = msvcrt.open_osfhandle(handle, (os.O_RDWR if writer else os.O_RDONLY) | os.O_BINARY)
        with os.fdopen(fd, "r+b" if writer else "rb") as stream:
            yield stream
    else:
        import fcntl
        with path.open("a+b" if writer else "rb") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Refused("writer exclusivity unavailable") from exc
            yield stream


def fingerprint(path: Path) -> dict:
    st = path.stat()
    result = dict(size=st.st_size, mtime_ns=st.st_mtime_ns, device=st.st_dev,
                  inode=st.st_ino, links=st.st_nlink)
    if os.name == "nt":
        class Basic(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in
                        ("creation", "access", "write", "change")] + [("attrs", wintypes.DWORD)]

        class Standard(ctypes.Structure):
            _fields_ = [("allocation", ctypes.c_int64), ("end", ctypes.c_int64),
                        ("links", wintypes.DWORD), ("delete", ctypes.c_byte),
                        ("directory", ctypes.c_byte)]

        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                       ctypes.c_void_p, wintypes.DWORD]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
        with path.open("rb") as stream:
            handle = msvcrt.get_osfhandle(stream.fileno())
            basic, standard = Basic(), Standard()
            require(kernel.GetFileInformationByHandleEx(handle, 0, ctypes.byref(basic), ctypes.sizeof(basic))
                    and kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(standard), ctypes.sizeof(standard)),
                    "strong fingerprint/allocation unavailable")
        result.update(change=basic.change, physical_bytes=standard.allocation, links=standard.links)
    else:
        result.update(change=st.st_ctime_ns, physical_bytes=st.st_blocks * 512)
    return result


def native_volume(path: Path) -> dict:
    """Exact Windows mount GUID + label + health. Unknown/non-Windows refuses."""
    require(os.name == "nt", "native volume attestation is Windows-only")
    drive = path.absolute().drive
    require(len(drive) == 2 and drive[1] == ":" and drive[0].isalpha(), "local volume required")
    command = ("$v=Get-Volume -DriveLetter '" + drive[0] + "' -ErrorAction Stop; "
               "$v | Select-Object UniqueId,FileSystemLabel,HealthStatus,OperationalStatus "
               "| ConvertTo-Json -Compress")
    try:
        v = json.loads(subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                     check=True, capture_output=True, text=True, timeout=15).stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise Refused("volume missing or identity unavailable") from exc
    return dict(id=v["UniqueId"], label=v["FileSystemLabel"],
                healthy=v["HealthStatus"] == "Healthy" and v["OperationalStatus"] == "OK")


def verify_volumes(source: Path, vault: Path, expected: dict, observer: Callable):
    require(source.exists() and vault.exists(), "source or destination missing")
    observed = {"source": observer(source), "destination": observer(vault)}
    for side in observed:
        require(observed[side] == expected[side] and observed[side].get("healthy") is True,
                side + " volume wrong/unhealthy")
    require(observed["source"]["id"] != observed["destination"]["id"], "distinct volumes required")
    return observed


def read_manifest(path: Path, expected_sha: str) -> dict:
    raw = path.read_bytes()
    require(digest(raw) == expected_sha, "manifest tampered")
    m = json.loads(raw)
    require(m.get("schema") == SCHEMA and m.get("status") == "COMPLETE", "unverified manifest")
    return m


def boundary_plan(source: Path, boundary: Path, boundary_sha: str, max_bytes: int) -> tuple[dict, list, list]:
    raw = boundary.read_bytes()
    require(digest(raw) == boundary_sha, "boundary identity mismatch")
    b = json.loads(raw)
    require(b.get("schema") == "vault_completed_boundary/v1" and b.get("status") == "COMPLETE"
            and b.get("session_identity") and b.get("cutoff") and b.get("source_identity")
            and b.get("receipt_refs") and b.get("seal_refs"), "completed evidence boundary required")
    files, excluded, seen = [], [], set()
    for row in sorted(b.get("files", []), key=lambda r: r["relative_path"]):
        path = safe_path(source, row["relative_path"])
        key = str(path).casefold()
        require(key not in seen, "duplicate/case-colliding path")
        seen.add(key)
        if (row.get("family") not in ELIGIBLE or row.get("state") != "COMPLETE"
                or row.get("immutable") is not True or row.get("lock_dependent") is not False
                or any(part.lower() in {"tmp", "temp", "accumulators"} for part in PurePosixPath(row["relative_path"]).parts)
                or path.suffix.lower() in {".tmp", ".partial", ".publishing", ".lock", ".db", ".sqlite", ".sqlite3"}
                or path.name.lower().endswith(("-wal", "-shm", "-journal"))):
            excluded.append(dict(relative_path=row["relative_path"], reason="ineligible boundary/family"))
            continue
        require(path.is_file() and len(row.get("sha256", "")) == 64
                and all(c in "0123456789abcdef" for c in row["sha256"])
                and isinstance(row.get("size"), int) and row["size"] >= 0, "native content proof missing")
        require(path.stat().st_size == row["size"], "source size differs from boundary")
        files.append(row)
    require(files and sum(r["size"] for r in files) <= max_bytes, "empty plan or copy/read budget exceeded")
    qualified = {r["relative_path"]: r["sha256"] for r in files}
    for ref in b["receipt_refs"] + b["seal_refs"]:
        require(isinstance(ref, dict) and qualified.get(ref.get("relative_path")) == ref.get("sha256"),
                "receipt/seal closure must be included with native SHA")
        require(sha(safe_path(source, ref["relative_path"])) == ref["sha256"], "receipt/seal identity mismatch")
    return b, files, excluded


def snapshot(source: Path, vault: Path, boundary: Path, boundary_sha: str, expected: dict, *,
             previous: Path | None = None, previous_sha: str | None = None,
             max_bytes=64 * CHUNK, observer=native_volume, on_chunk=None) -> dict:
    source, vault = source.absolute(), vault.absolute()
    safe_path(source, ".vault-path-check")
    safe_path(vault, ".vault-path-check")
    require(not source.is_relative_to(vault) and not vault.is_relative_to(source), "overlapping roots")
    volumes = verify_volumes(source, vault, expected, observer)
    b, files, excluded = boundary_plan(source, boundary, boundary_sha, max_bytes)
    prior = None
    if previous is not None:
        require(previous_sha is not None and previous.absolute().is_relative_to(vault), "trusted prior SHA/path required")
        safe_path(vault, previous.absolute().relative_to(vault).as_posix())
        prior = read_manifest(previous, previous_sha)
        require(prior["volumes"] == volumes and prior["source_root"] == str(source), "prior source/destination mismatch")
    plan = dict(schema=SCHEMA, boundary_sha=boundary_sha, source_root=str(source), volumes=volumes,
                previous_sha=previous_sha, boundary=b)
    version = digest(canonical(plan))
    folder = safe_path(vault, "snapshots/" + version)
    vault.joinpath(".writer.lock").touch(exist_ok=True)
    with locked_file(vault / ".writer.lock", writer=True):
        manifest_path = folder / "manifest.json"
        if manifest_path.exists():
            # Compare against the immutable deterministic receipt, not a self-asserted digest.
            prepared = folder / "receipt.prepared.json"
            receipt = json.loads(prepared.read_bytes())
            m = read_manifest(manifest_path, receipt["manifest_sha256"])
            require(m["plan_sha256"] == version, "plan mismatch")
            require(m["volumes"] == volumes and m["source_root"] == str(source)
                    and m["boundary_sha256"] == boundary_sha, "manifest input binding mismatch")
            native_rows = [{k: value for k, value in row.items()
                            if k not in {"source_fingerprint", "vault_path", "vault_fingerprint"}}
                           for row in m["files"]]
            require(native_rows == files and m["excluded"] == excluded, "manifest boundary closure mismatch")
            for row in m["files"]:
                require(fingerprint(safe_path(source, row["relative_path"])) == row["source_fingerprint"]
                        and fingerprint(safe_path(vault, row["vault_path"])) == row["vault_fingerprint"],
                        "repeat source/vault fingerprint changed; use explicit new version")
            publish(folder / "receipt.json", canonical(receipt))
            return receipt
        folder.mkdir(parents=True, exist_ok=True)
        publish(folder / "plan.json", canonical(plan))
        prior_rows = {r["relative_path"]: r for r in prior["files"]} if prior else {}
        records, copied, reused = [], 0, 0
        for row in files:
            path = safe_path(source, row["relative_path"])
            with locked_file(path) as stream:
                require(stream.read(16) != b"SQLite format 3\x00", "SQLite requires separate Backup API")
                stream.seek(0)
                before = fingerprint(path)
                old = prior_rows.get(row["relative_path"])
                if old and old["sha256"] == row["sha256"] and old["source_fingerprint"] == before:
                    dest = safe_path(vault, old["vault_path"])
                    require(fingerprint(dest) == old["vault_fingerprint"], "prior vault object mutated")
                    records.append({**row, "source_fingerprint": before, "vault_path": old["vault_path"],
                                    "vault_fingerprint": old["vault_fingerprint"]})
                    reused += 1
                    continue
                rel = "snapshots/" + version + "/files/" + row["relative_path"]
                dest = safe_path(vault, rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                stage_root = folder / ".staging"
                stage_root.mkdir(exist_ok=True)
                stage_key = digest(row["relative_path"].encode())
                stage = stage_root / (stage_key + ".partial")
                stage_meta = stage_root / (stage_key + ".json")
                token = canonical(dict(plan=version, sha256=row["sha256"], fingerprint=before))
                if stage_meta.exists():
                    require(stage_meta.read_bytes() == token, "staged source mutated")
                else:
                    publish(stage_meta, token)
                h = hashlib.sha256()
                if stage.exists():
                    with stage.open("rb") as partial:
                        for chunk in iter(lambda: partial.read(CHUNK), b""):
                            require(stream.read(len(chunk)) == chunk, "resume prefix corrupt")
                            h.update(chunk)
                with stage.open("ab") as out:
                    for chunk in iter(lambda: stream.read(CHUNK), b""):
                        out.write(chunk)
                        out.flush()
                        h.update(chunk)
                        if on_chunk:
                            on_chunk(path, stage)
                    os.fsync(out.fileno())
                require(fingerprint(path) == before and h.hexdigest() == row["sha256"]
                        and stage.stat().st_size == row["size"], "source mutated or native hash mismatch")
                require(sha(stage) == row["sha256"], "staged verification failed")
                if dest.exists():
                    require(sha(dest) == row["sha256"], "completed object conflict")
                else:
                    os.rename(stage, dest)
                records.append({**row, "source_fingerprint": before, "vault_path": rel,
                                "vault_fingerprint": fingerprint(dest)})
                copied += 1
        require(digest(boundary.read_bytes()) == boundary_sha, "boundary changed during snapshot")
        verify_volumes(source, vault, expected, observer)
        for row in records:
            require(fingerprint(safe_path(source, row["relative_path"])) == row["source_fingerprint"],
                    "source mutated before manifest completion")
            require(fingerprint(safe_path(vault, row["vault_path"])) == row["vault_fingerprint"],
                    "vault object mutated before manifest completion")
        m = dict(schema=SCHEMA, status="COMPLETE", plan_sha256=version,
                 source_root=str(source), volumes=volumes, boundary_sha256=boundary_sha,
                 source_identity=b["source_identity"], session_identity=b["session_identity"],
                 cutoff=b["cutoff"], seal_refs=b["seal_refs"], receipt_refs=b["receipt_refs"],
                 previous_sha256=previous_sha, files=records, excluded=excluded)
        raw = canonical(m)
        receipt = dict(schema="vault_receipt/v1", snapshot_identity=version,
                       manifest_sha256=digest(raw), status="VERIFIED", authority_effect="NONE",
                       copied_files=copied, reused_files=reused)
        publish(folder / "receipt.prepared.json", canonical(receipt))
        publish(manifest_path, raw)
        publish(folder / "receipt.json", canonical(receipt))
        return receipt


def restore_verify(vault: Path, manifest: Path, manifest_sha: str, restored: Path,
                   expected_destination: dict, *, observer=native_volume, max_bytes=64 * CHUNK) -> dict:
    """Read-only exact-path verification of an explicit restore, never live reacquisition."""
    require(observer(vault) == expected_destination and expected_destination.get("healthy") is True,
            "archive unavailable/wrong volume")
    m = read_manifest(manifest, manifest_sha)
    require(m["volumes"]["destination"] == expected_destination, "manifest volume mismatch")
    require(sum(r["size"] for r in m["files"]) <= max_bytes, "restore read budget exceeded")
    for r in m["files"]:
        require(sha(safe_path(vault, r["vault_path"])) == r["sha256"]
                and sha(safe_path(restored, r["relative_path"])) == r["sha256"], "restore bytes differ")
    return dict(status="VERIFIED", files=len(m["files"]), source_identity=m["source_identity"],
                operational_fingerprint_compatibility="NOT_GRANTED", authority_effect="NONE")


def sqlite_backup(source: Path, vault: Path, relative: str, expected: dict, source_sha: str, *,
                  max_bytes=64 * CHUNK, observer=native_volume) -> dict:
    """Bounded closed-database backup. Live/uncertain WAL or writer state refuses."""
    safe_path(source.parent, source.name)
    safe_path(vault, ".vault-path-check")
    verify_volumes(source, vault, expected, observer)
    require(os.name == "nt", "enforced SQLite writer exclusivity currently Windows-only")
    require(source.is_file() and source.stat().st_size <= max_bytes, "database budget exceeded")
    require(not any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")),
            "unclear journal/writer exclusivity")
    dest = safe_path(vault, relative)
    require(not dest.exists() and not dest.with_suffix(dest.suffix + ".receipt.json").exists(),
            "backup version already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = dest.with_suffix(dest.suffix + ".partial")
    require(not stage.exists(), "interrupted SQLite stage requires explicit separate recovery")
    with locked_file(source):
        before = fingerprint(source)
        require(sha(source) == source_sha, "database identity mismatch")
        uri = source.absolute().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as origin, closing(sqlite3.connect(stage, timeout=0)) as target:
            require(origin.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "source DB corrupt")

            def progress(status, remaining, total):
                require(status not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED), "backup lock unavailable")
                require(total * origin.execute("PRAGMA page_size").fetchone()[0] <= max_bytes,
                        "backup page budget exceeded")

            origin.backup(target, pages=128, progress=progress, sleep=0)
            require(target.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "backup DB corrupt")
        require(fingerprint(source) == before and sha(source) == source_sha, "source DB changed")
        verify_volumes(source, vault, expected, observer)
        result = dict(schema="vault_sqlite_backup/v1", status="VERIFIED", source=str(source),
                      source_sha256=source_sha, backup_sha256=sha(stage), volumes=expected,
                      integrity_check="ok", byte_identical=sha(stage) == source_sha,
                      backup_api=True, authority_effect="NONE")
        os.rename(stage, dest)
        publish(dest.with_suffix(dest.suffix + ".receipt.json"), canonical(result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opt-in", action="store_true", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--volumes", type=Path, required=True, help="Exact expected GUID/label/healthy JSON")
    parser.add_argument("--max-bytes", type=int, default=64 * CHUNK)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--boundary", type=Path, required=True)
    snap.add_argument("--boundary-sha", required=True)
    snap.add_argument("--previous", type=Path)
    snap.add_argument("--previous-sha")
    db = sub.add_parser("sqlite")
    db.add_argument("--relative", required=True)
    db.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    expected = json.loads(args.volumes.read_text(encoding="utf-8"))
    require(args.vault.drive.upper() == "W:", "production CLI destination must be explicit W:")
    if args.command == "snapshot":
        result = snapshot(args.source, args.vault, args.boundary, args.boundary_sha, expected,
                          previous=args.previous, previous_sha=args.previous_sha, max_bytes=args.max_bytes)
    else:
        result = sqlite_backup(args.source, args.vault, args.relative, expected, args.source_sha,
                               max_bytes=args.max_bytes)
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
