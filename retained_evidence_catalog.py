"""Location metadata for retained identities; never an evidence authority or downloader."""
from __future__ import annotations

import json
from pathlib import Path

from tools.vault_snapshot import Refused, safe_path, sha

SCHEMA = "retained_evidence_cold_catalog/v1"
STATES = {"PRESENT_ON_C", "ARCHIVED_COLD", "NEVER_RETAINED", "UNKNOWN_OR_CONFLICTED"}


class EvidenceIntegrityError(Refused):
    pass


class ArchiveRestoreRequired(EvidenceIntegrityError):
    def __init__(self, entry):
        self.entry = entry.copy()
        self.locator = entry["vault"].copy()
        super().__init__("RESTORE_REQUIRED:" + entry["relative_path"] + ":" + json.dumps(self.locator, sort_keys=True))


def load(root: Path) -> list[dict]:
    path = safe_path(root, "config/retained_evidence_cold_catalog.json")
    if not path.exists():
        return []  # Legacy/test roots have no activated catalog.
    try:
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict) or value.get("schema") != SCHEMA or not isinstance(value.get("entries"), list):
            raise ValueError("schema")
        seen = set()
        for entry in value["entries"]:
            if not isinstance(entry, dict):
                raise ValueError("entry object required")
            rel = entry["relative_path"]
            safe_path(root, rel)
            if rel.casefold() in seen or entry["state"] not in STATES:
                raise ValueError("duplicate/conflicted state")
            seen.add(rel.casefold())
            if not all(isinstance(entry.get(k), str) and entry[k] for k in
                       ("session_identity", "artifact_identity", "artifact_role")):
                raise ValueError("identity required")
            if entry["state"] in {"PRESENT_ON_C", "ARCHIVED_COLD"}:
                if (type(entry.get("original_size")) is not int or entry["original_size"] < 0
                        or not _hash(entry.get("sha256")) or not entry.get("source_seal_provenance")):
                    raise ValueError("native provenance required")
            if entry["state"] == "ARCHIVED_COLD":
                vault = entry["vault"]
                safe_path(root, vault["manifest_path"])
                safe_path(root, vault["object_path"])
                if (not all(vault.get(k) for k in ("snapshot_identity", "manifest_path", "object_path", "volume_id"))
                        or not _hash(vault.get("manifest_sha256")) or not _hash(vault.get("object_sha256"))
                        or vault["object_sha256"] != entry["sha256"]
                        or not entry.get("restore_procedure") or not entry.get("restore_preconditions")):
                    raise ValueError("qualified restore locator required")
        return value["entries"]
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise EvidenceIntegrityError("UNKNOWN_OR_CONFLICTED:catalog invalid") from exc


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def resolve(root: Path, relative_path: str, *, session_identity: str | None = None) -> str:
    path = safe_path(root, relative_path)
    entries = load(root)
    entry = next((r for r in entries if r["relative_path"].casefold() == relative_path.casefold()), None)
    if entry is None:
        return "PRESENT_ON_C" if path.is_file() else "NEVER_RETAINED"
    if session_identity is not None and entry["session_identity"] != session_identity:
        raise EvidenceIntegrityError("UNKNOWN_OR_CONFLICTED:session identity mismatch")
    state = entry["state"]
    if state == "UNKNOWN_OR_CONFLICTED" or (state == "NEVER_RETAINED" and path.exists()):
        raise EvidenceIntegrityError("UNKNOWN_OR_CONFLICTED:" + relative_path)
    if state == "PRESENT_ON_C":
        if not path.is_file():
            raise EvidenceIntegrityError("LOCAL_EVIDENCE_MISSING:" + relative_path)
        if path.stat().st_size != entry["original_size"] or sha(path) != entry["sha256"]:
            raise EvidenceIntegrityError("LOCAL_EVIDENCE_CORRUPT:" + relative_path)
    if state == "ARCHIVED_COLD":
        # Even if a file was manually restored, require an explicit verified local event.
        raise ArchiveRestoreRequired(entry)
    return state


def guard_path(root: Path, path: Path, *, session_identity: str | None = None):
    try:
        relative = path.absolute().relative_to(root.absolute()).as_posix()
    except ValueError as exc:
        raise EvidenceIntegrityError("UNKNOWN_OR_CONFLICTED:path outside catalog root") from exc
    return resolve(root, relative, session_identity=session_identity)


def guard_registered_snapshots(root: Path, session: str, roles):
    """Check registered canonical identities independently of the selected attempt path."""
    for entry in load(root):
        if entry["session_identity"] == session and entry["artifact_role"] in roles:
            resolve(root, entry["relative_path"], session_identity=session)


def guard_acquisition(root: Path, session: str):
    """Session-wide check prevents a fresh attempt root from evading a registered cold path."""
    guard_registered_snapshots(root, session, {"exact_session_snapshot", "dnse_only_exact_session_snapshot"})
    registry = safe_path(root, "config/daily_research_session_input_registry.json")
    if registry.exists():
        try:
            completed = json.loads(registry.read_bytes()).get("completed_sessions", {}).get(session, {})
        except (ValueError, TypeError, AttributeError) as exc:
            raise EvidenceIntegrityError("UNKNOWN_OR_CONFLICTED:completion registry invalid") from exc
        if completed.get("status") == "COMPLETED_RETAINED_EVIDENCE":
            raise EvidenceIntegrityError("COMPLETED_SESSION_EVIDENCE_MISSING:" + session)
