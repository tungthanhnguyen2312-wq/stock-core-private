"""Retained-evidence quarantine: files that must never serve as a pristine historical baseline.

The tracked registry ``config/retained_evidence_quarantine.json`` names retained Level-2 files
whose content is known or suspected not to be what production originally wrote (see
RETAINED_EVIDENCE_INCIDENT_20260925: tests rebuilt the 2026-08-25 and 2026-09-04 Integrated
Decision folders into the repository's own ``operations-review``). The registry never deletes,
restores or rewrites anything; restoration or supersession is an owner decision recorded by
amending the registry.

Loaders that use retained artifacts as a *reference* -- retained regression comparison,
historical acceptance, replay of research posture from a retained Integrated Decision -- consult
it and refuse a quarantined path with ``RETAINED_EVIDENCE_QUARANTINED`` instead of silently
comparing against contaminated bytes. Ordinary Daily reads only the processed session and its
predecessor and never needs this module. The pytest retained-evidence tier
(``tests/_test_tiers.py``) refuses a test whose declared evidence is quarantined.

Paths are repository-relative POSIX paths under the retained-evidence root (the Producer
checkout). Matching is by resolved location, so a junction or symlink cannot launder a
quarantined file under another name.
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "config" / "retained_evidence_quarantine.json"
CONTRACT_VERSION = "retained_evidence_quarantine/v1"
REFUSAL_CODE = "RETAINED_EVIDENCE_QUARANTINED"

USE_RETAINED_REGRESSION_BASELINE = "RETAINED_REGRESSION_BASELINE"
USE_HISTORICAL_ACCEPTANCE_BASELINE = "HISTORICAL_ACCEPTANCE_BASELINE"
USE_IID_DEPENDENT_POSTURE_REPLAY = "IID_DEPENDENT_POSTURE_REPLAY"
EXCLUDED_USES = (
    USE_RETAINED_REGRESSION_BASELINE,
    USE_HISTORICAL_ACCEPTANCE_BASELINE,
    USE_IID_DEPENDENT_POSTURE_REPLAY,
)
CLASSIFICATIONS = (
    "CONTAMINATED_UNRECOVERABLE",
    "NON_PRISTINE_ORIGINAL_RECONSTRUCTABLE",
    "NON_PRISTINE_CONTENT_UNVERIFIED",
)

PIN_MATCH = "PINNED_BYTES_UNCHANGED"
PIN_DRIFTED = "PINNED_BYTES_CHANGED"
PIN_ABSENT = "ABSENT"


class QuarantineRegistryError(ValueError):
    """The tracked registry is missing or malformed. Never read as 'nothing is quarantined'."""


class QuarantinedRetainedEvidence(RuntimeError):
    """A caller asked to use a quarantined retained file as a pristine reference."""

    def __init__(self, relative_path: str, entry: Mapping[str, Any], use: str) -> None:
        self.code = REFUSAL_CODE
        self.relative_path = relative_path
        self.entry = dict(entry)
        self.use = use
        super().__init__(f"{REFUSAL_CODE}:{use}:{relative_path}:{entry.get('classification')}")


def _validate(payload: Any, source: Path) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("contract_version") != CONTRACT_VERSION:
        raise QuarantineRegistryError(f"RETAINED_EVIDENCE_QUARANTINE_REGISTRY_INVALID:contract_version:{source}")
    entries = payload.get("quarantined")
    if not isinstance(entries, list) or not entries:
        raise QuarantineRegistryError(f"RETAINED_EVIDENCE_QUARANTINE_REGISTRY_INVALID:quarantined:{source}")
    seen: set[str] = set()
    for entry in entries:
        path = entry.get("path") if isinstance(entry, Mapping) else None
        if not isinstance(path, str) or "\\" in path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise QuarantineRegistryError(f"RETAINED_EVIDENCE_QUARANTINE_REGISTRY_INVALID:path:{path!r}")
        if entry.get("classification") not in CLASSIFICATIONS:
            raise QuarantineRegistryError(f"RETAINED_EVIDENCE_QUARANTINE_REGISTRY_INVALID:classification:{path}")
        key = path.casefold()
        if key in seen:
            raise QuarantineRegistryError(f"RETAINED_EVIDENCE_QUARANTINE_REGISTRY_INVALID:duplicate:{path}")
        seen.add(key)
    sessions = payload.get("iid_posture_replay_excluded_sessions")
    if not isinstance(sessions, list) or not all(isinstance(s, str) for s in sessions):
        raise QuarantineRegistryError(f"RETAINED_EVIDENCE_QUARANTINE_REGISTRY_INVALID:sessions:{source}")
    return dict(payload)


@lru_cache(maxsize=4)
def _load_cached(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuarantineRegistryError(f"RETAINED_EVIDENCE_QUARANTINE_REGISTRY_INVALID:unreadable:{type(exc).__name__}:{path}") from exc
    return _validate(payload, path)


def load_registry(path: Path | None = None) -> dict[str, Any]:
    return _load_cached(str(Path(path) if path is not None else REGISTRY_PATH))


def _location_key(path: Path) -> str:
    return os.path.normcase(os.path.realpath(path))


def relative_evidence_path(path: Path, evidence_root: Path) -> str | None:
    """The repository-relative POSIX path of ``path`` under ``evidence_root``, by resolved
    location (junctions/symlinks resolved), or None when it lies outside the root."""
    root_key = _location_key(Path(evidence_root))
    target_key = _location_key(Path(path))
    try:
        common = os.path.commonpath([root_key, target_key])
    except ValueError:  # different drives
        return None
    if common != root_key or target_key == root_key:
        return None
    return PurePosixPath(*Path(os.path.relpath(target_key, root_key)).parts).as_posix()


def quarantine_entry(
    path: Path, *, evidence_root: Path, registry: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    registry = registry if registry is not None else load_registry()
    relative = relative_evidence_path(path, evidence_root)
    if relative is None:
        return None
    for entry in registry["quarantined"]:
        if entry["path"].casefold() == relative.casefold():
            return dict(entry)
    return None


def quarantined_entries_named_by(
    relative_path: str, registry: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Entries that a declared repository-relative evidence path names: the quarantined file
    itself, or the folder that directly holds it."""
    registry = registry if registry is not None else load_registry()
    wanted = PurePosixPath(relative_path).as_posix().rstrip("/").casefold()
    hits = []
    for entry in registry["quarantined"]:
        path = PurePosixPath(entry["path"])
        if wanted in (path.as_posix().casefold(), path.parent.as_posix().casefold()):
            hits.append(dict(entry))
    return hits


def require_unquarantined(
    path: Path, *, evidence_root: Path, use: str, registry: Mapping[str, Any] | None = None,
) -> Path:
    """Return ``path`` unchanged, or raise ``QuarantinedRetainedEvidence`` when it is quarantined."""
    if use not in EXCLUDED_USES:
        raise ValueError(f"UNKNOWN_RETAINED_EVIDENCE_USE:{use}")
    entry = quarantine_entry(path, evidence_root=evidence_root, registry=registry)
    if entry is not None:
        raise QuarantinedRetainedEvidence(entry["path"], entry, use)
    return path


def iid_posture_replay_excluded(session: str, registry: Mapping[str, Any] | None = None) -> bool:
    """True when posture replay that depends on this session's retained Integrated Decision is
    excluded (the IID is quarantined; raw session-bar facts of the session remain usable)."""
    registry = registry if registry is not None else load_registry()
    return session in registry["iid_posture_replay_excluded_sessions"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pins(evidence_root: Path, registry: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read-only: compare every quarantined file with the bytes observed at quarantine time.
    A drift means the file was written again; it stays quarantined either way."""
    registry = registry if registry is not None else load_registry()
    rows = []
    for entry in registry["quarantined"]:
        path = Path(evidence_root) / entry["path"]
        if not path.is_file():
            status, observed = PIN_ABSENT, None
        else:
            observed = _sha256(path)
            status = PIN_MATCH if observed == entry.get("observed_sha256") else PIN_DRIFTED
        rows.append({"path": entry["path"], "status": status, "sha256": observed})
    return rows
