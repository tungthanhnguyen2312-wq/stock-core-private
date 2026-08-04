"""Audit every retained VCI evidence artifact for reachability, secrets and determinism.

Read-only. Reports; it does not delete. An artifact is removed only by a human who has
read the finding, and failure evidence is never removed to reduce a count.

    python tools/audit_vci_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vci_direct_basis_pilot as pilot  # noqa: E402

EVIDENCE_ROOTS = (
    ROOT / "operations-review" / "vci-direct-basis-pilot-20260804",
    ROOT / "operations-review" / "vci-intraday-pagination-20260804",
    ROOT / "operations-review" / "vci-volume-composition-20260804",
    ROOT / "operations-review" / "vci-contract-reconciliation-20260804",
)

SECRET_MARKERS = (
    "set-cookie", "authorization", "bearer ", "api-key", "apikey",
    "jsessionid", "x-auth-token", "proxy-authorization", "password", "secret",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_referenced() -> dict[str, set[str]]:
    """Every raw artifact name a ledger, manifest or observation points at."""
    referenced: dict[str, set[str]] = defaultdict(set)
    for root in EVIDENCE_ROOTS:
        if not root.exists():
            continue
        for ledger in root.rglob("*.json"):
            if ledger.match("*/raw/*") or ledger.match("*/pages/*"):
                continue
            try:
                text = ledger.read_text(encoding="utf-8")
                blob = json.loads(text)
            except (ValueError, UnicodeDecodeError):
                continue
            # Names appear as raw_artifact fields and as page_sha256 prefixes in filenames,
            # so match on the literal text of the ledger rather than a fixed schema.
            for artifact in (root.rglob("*.raw.json")):
                if artifact.name in text:
                    referenced[str(root)].add(artifact.name)
            for run in ("transitions",):
                if isinstance(blob, dict) and run in blob:
                    for entry in blob[run]:
                        digest = entry.get("page_sha256")
                        if digest:
                            referenced[str(root)].add(f"sha:{digest}")
    return referenced


def main() -> int:
    report: dict = {"roots": {}, "totals": {}}
    total_files = total_raw = unreferenced = secret_hits = duplicate_groups = 0
    by_digest: dict[str, list[str]] = defaultdict(list)
    referenced = collect_referenced()

    for root in EVIDENCE_ROOTS:
        if not root.exists():
            continue
        files = [p for p in root.rglob("*") if p.is_file()]
        raws = [p for p in files if p.name.endswith(".raw.json")]
        entry: dict = {
            "files": len(files),
            "raw_artifacts": len(raws),
            "raw_without_sha_in_name": [],
            "unreferenced_raw": [],
            "secret_findings": [],
        }
        for path in raws:
            digest = sha256(path)
            by_digest[digest].append(str(path.relative_to(ROOT)))
            # Every raw filename embeds the first 16 hex of its own content hash, so the
            # name is self-verifying and a silent edit cannot hide.
            if digest[:16] not in path.name:
                entry["raw_without_sha_in_name"].append(path.name)
            names = referenced.get(str(root), set())
            if path.name not in names and f"sha:{digest}" not in names:
                entry["unreferenced_raw"].append(path.name)
        for path in files:
            if path.suffix not in {".json", ".md", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            # Structural, not textual. A report that says "no authorization header was
            # sent" is prose about a secret, not a secret; what matters is a marker used
            # as a key with a value that is not the redaction sentinel.
            for marker in SECRET_MARKERS:
                pattern = "[\"']" + re.escape(marker.strip()) + "[\"']\\s*:\\s*(.{0,40})"
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    value = match.group(1).strip()
                    if pilot.REDACTED.lower() in value.lower() or value.startswith(("null", "{", "[")):
                        continue
                    entry["secret_findings"].append(
                        {"file": path.name, "marker": marker, "value_preview": value[:24]}
                    )
        report["roots"][root.name] = entry
        total_files += entry["files"]
        total_raw += entry["raw_artifacts"]
        unreferenced += len(entry["unreferenced_raw"])
        secret_hits += len(entry["secret_findings"])

    # Identical bytes under two names would be an accidental duplicate. Identical bytes are
    # legitimate only when each copy has its own evidentiary role (e.g. the same provider
    # response observed at two different retrieval times).
    duplicates = {d: paths for d, paths in by_digest.items() if len(paths) > 1}
    duplicate_groups = len(duplicates)

    report["totals"] = {
        "files": total_files,
        "raw_artifacts": total_raw,
        "unreferenced_raw_artifacts": unreferenced,
        "secret_findings": secret_hits,
        "byte_identical_groups": duplicate_groups,
        "byte_identical_detail": duplicates,
        "all_raw_names_self_verifying": all(
            not e["raw_without_sha_in_name"] for e in report["roots"].values()
        ),
    }
    print(json.dumps(report["totals"], indent=1))
    for name, entry in report["roots"].items():
        print(f"  {name}: files={entry['files']} raw={entry['raw_artifacts']} "
              f"unreferenced={len(entry['unreferenced_raw'])} secrets={len(entry['secret_findings'])}")
        for item in entry["unreferenced_raw"][:5]:
            print(f"     unreferenced: {item}")
    out = ROOT / "operations-review" / "vci-volume-composition-20260804" / "evidence_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
