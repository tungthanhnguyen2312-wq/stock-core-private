"""P0.3 -- generate a git-trackable, tamper-evident hash manifest for an
untracked directory tree that is too large (binary evidence, shadow database
snapshots) to bring into git history directly.

Records, for every file under `root`: relative path, SHA-256, byte size, and
mtime. Writes nothing but the manifest itself; never moves, deletes, or
modifies a source file. Deterministic: re-running against an unchanged tree
produces a byte-identical manifest (rows sorted by relative path).

Usage: python tools/hash_manifest.py <root> <output.json> [--label TEXT]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0.0"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, *, label: str | None = None) -> dict:
    root = root.resolve()
    entries = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        entries.append({
            "path": rel,
            "sha256": _sha256_file(path),
            "byte_size": size,
            "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
        total_bytes += size
    return {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "root_description": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "entries": entries,
    }


def verify_manifest(root: Path, manifest: dict) -> list[dict]:
    """Returns a list of discrepancies: missing files, hash mismatches, and
    files present on disk but absent from the manifest. Empty list means the
    tree matches the manifest exactly."""
    root = root.resolve()
    issues = []
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    manifest_paths = set()
    for entry in manifest["entries"]:
        manifest_paths.add(entry["path"])
        full = root / entry["path"]
        if not full.is_file():
            issues.append({"path": entry["path"], "reason": "missing_on_disk"})
            continue
        live_hash = _sha256_file(full)
        if live_hash != entry["sha256"]:
            issues.append({"path": entry["path"], "reason": "hash_mismatch", "expected": entry["sha256"], "live": live_hash})
    for extra in on_disk - manifest_paths:
        issues.append({"path": extra, "reason": "present_on_disk_not_in_manifest"})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label", default=None)
    parser.add_argument("--verify", action="store_true", help="verify `output` against `root` instead of generating")
    args = parser.parse_args()

    if args.verify:
        manifest = json.loads(args.output.read_text(encoding="utf-8"))
        issues = verify_manifest(args.root, manifest)
        print(json.dumps({"issues": issues, "ok": not issues}, indent=1))
        return 1 if issues else 0

    manifest = build_manifest(args.root, label=args.label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=1, sort_keys=False), encoding="utf-8")
    print(f"wrote {args.output}: {manifest['file_count']} files, {manifest['total_bytes']} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
