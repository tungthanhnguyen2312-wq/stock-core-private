"""Offline source conservation for the Owner-approved retention reader transition.

The original manifest/pins stay unchanged. Only the exact archived reader supplies
historical bytes. Active execution always hashes active source; no digest spoofing
or historical receipt adoption is provided by this diagnostic.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools import qualify_e4_infrastructure as e4

READER = "prospective_decision_retention.py"
ARCHIVE = "tests/fixtures/retention_reader_v1.py.txt"
MANIFEST = "tests/fixtures/retention_reader_transition_v2.json"
STORAGE_MANIFEST = "tests/fixtures/storage_portability_source_transition_v1.json"


def _storage_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Conserve exact pre-storage sources without repinning either historical domain."""
    manifest = root / STORAGE_MANIFEST
    if not manifest.exists():
        return active  # Released pre-storage checkout compatibility.
    spec = json.loads(manifest.read_bytes())
    if spec.get("contract_version") != "storage_portability_source_transition/v1":
        raise ValueError("STORAGE_SOURCE_TRANSITION_INVALID")
    row = spec["sources"].get(relative)
    if row is None:
        return active
    expected_archive = "tests/fixtures/storage_portability_v1_sources/" + relative + ".txt"
    if row["archive"] != expected_archive:
        raise ValueError("STORAGE_SOURCE_ARCHIVE_PATH_INVALID")
    prior = (root / expected_archive).read_bytes().replace(b"\r\n", b"\n")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    expected = (json.loads((root / MANIFEST).read_bytes())["active_sha256_lf"]
                if relative == READER else pins[relative])
    if (row["prior_sha256_lf"] != expected or hashlib.sha256(prior).hexdigest() != expected
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]):
        raise ValueError("STORAGE_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def historical_bytes(root: Path, relative: str) -> bytes:
    """Verify both sides of the one-file boundary before supplying legacy bytes."""
    content = (root / relative).read_bytes().replace(b"\r\n", b"\n")
    content = _storage_prior_bytes(root, relative, content)
    if relative != READER:
        return content
    spec = json.loads((root / MANIFEST).read_bytes())
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    archive = (root / ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (spec["contract_version"] != "retention_reader_source_transition/v2" or
        spec["reader_path"] != READER or spec["legacy_archive"] != ARCHIVE or
        hashlib.sha256(archive).hexdigest() != pins[READER] or
        spec["legacy_sha256_lf"] != pins[READER] or
        hashlib.sha256(content).hexdigest() != spec["active_sha256_lf"] or
        spec["reader_version"] != "prospective_t0_origination_lineage/v2"):
        raise ValueError("RETENTION_READER_VERSION_BOUNDARY_INVALID")
    return archive


def legacy_source_identity(root: Path, *, version: str) -> dict:
    """Recompute the original closed hash domain; never return a historical constant."""
    if version not in {"v1", "v2"}:
        raise ValueError("E4_SOURCE_VERSION_UNSUPPORTED")
    digest = hashlib.sha256(b"e4_infrastructure_source/v2\0" if version == "v2" else b"")
    sources = list(e4.V1_SOURCES)
    if version == "v2":
        sources.extend((p, p) for p in e4.V2_SOURCES)
    for label, relative in sources:
        digest.update(label.encode() + b"\0" + hashlib.sha256(historical_bytes(root, relative)).digest())
    return {"source_version": version, "code_digest": digest.hexdigest(), "verification_scope": "HISTORICAL_SOURCE_ONLY"}


def active_reader_identity(root: Path) -> dict:
    historical_bytes(root, READER)
    spec = json.loads((root / MANIFEST).read_bytes())
    active = e4.source_identity(root, version="v1")
    return {"reader_version": spec["reader_version"], "execution_code_digest": active["code_digest"],
            "source_version": "retention_reader_source/v2", "legacy_receipt_adoption": False,
            "cache_policy": "EXACT_EXECUTION_AND_VERIFIER_DIGEST_REQUIRED_NO_CROSS_VERSION_ADOPTION"}
