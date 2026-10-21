"""Offline source conservation for Owner-approved source transitions.

The original manifest/pins stay unchanged. Historical bytes come only from the exact
archived source after both sides have been read and hashed. Active execution always
hashes active source; no digest spoofing or historical receipt adoption is provided.
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
VALUATION_MANIFEST = "tests/fixtures/evidence_valuation_orchestration_source_transition_v1.json"
VALUATION_CONTRACT = "evidence_valuation_orchestration_source_transition/v1"
VALUATION_BASE = "de90c6b94c7bb2377bedd7e2a1c809498d22926a"
VALUATION_SOURCES = (
    "canonical_daily_operation.py",
    "canonical_post_close_pipeline.py",
)
THESIS_MANIFEST = "tests/fixtures/thesis_evidence_production_source_transition_v1.json"
THESIS_CONTRACT = "thesis_evidence_production_source_transition/v1"
THESIS_BASE = "de90c6b94c7bb2377bedd7e2a1c809498d22926a"
THESIS_SOURCE = "stocklookup_core/research/thesis_evidence_production.py"
THESIS_ARCHIVE = "tests/fixtures/thesis_evidence_v1_sources/thesis_evidence_production.py.txt"
THESIS_SCOPE = "EXACT_ONE_FILE_OWNER_APPROVED_NOT_A_GENERAL_TRANSITION"
_THESIS_FIELDS = frozenset({
    "contract_version", "workstream", "base_commit", "source_path", "archive",
    "prior_sha256_lf", "active_sha256_lf", "historical_e4_v2_digest", "active_e4_v2_digest",
    "rejected_mixed_digest", "exception_scope", "release_authority", "compatibility",
})
FINANCIAL_RESEARCH_MANIFEST = "tests/fixtures/financial_research_source_transition_v1.json"


def _financial_research_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Same conservation rule as the storage transition, for the divergence pipeline leg."""
    manifest = root / FINANCIAL_RESEARCH_MANIFEST
    if not manifest.exists():
        return active
    spec = json.loads(manifest.read_bytes())
    if spec.get("contract_version") != "financial_research_source_transition/v1":
        raise ValueError("FINANCIAL_RESEARCH_SOURCE_TRANSITION_INVALID")
    row = spec["sources"].get(relative)
    if row is None:
        return active
    expected_archive = "tests/fixtures/financial_research_v1_sources/" + relative + ".txt"
    if row["archive"] != expected_archive:
        raise ValueError("FINANCIAL_RESEARCH_SOURCE_ARCHIVE_PATH_INVALID")
    prior = (root / expected_archive).read_bytes().replace(b"\r\n", b"\n")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    # E2/E3-pinned files must reproduce their pin; E4 V2-only files bind to the archived
    # prior-release bytes (their own digest test then reproduces the historical code digest).
    expected = pins.get(relative, row["prior_sha256_lf"])
    if (row["prior_sha256_lf"] != expected or hashlib.sha256(prior).hexdigest() != expected
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]):
        raise ValueError("FINANCIAL_RESEARCH_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


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


def _valuation_orchestration_prior_bytes(root: Path, relative: str) -> bytes:
    """Return archived origin/main bytes for the two approved orchestration sources.

    The closed set is the code constant above. A manifest that names any other
    file, or omits either approved file, is refused. Both the archive and the
    live file are hashed on every call.
    """
    if relative not in VALUATION_SOURCES:
        raise ValueError("VALUATION_SOURCE_TRANSITION_SCOPE_INVALID")
    manifest = root / VALUATION_MANIFEST
    if not manifest.is_file():
        raise ValueError("VALUATION_SOURCE_TRANSITION_INVALID")
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    admitted = spec.get("admitted_sources")
    if (spec.get("contract_version") != VALUATION_CONTRACT or spec.get("base_commit") != VALUATION_BASE
            or spec.get("exception_scope") != "EXACT_TWO_FILE_OWNER_APPROVED_NOT_A_GENERAL_TRANSITION"
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or not isinstance(admitted, list)
            or admitted != list(VALUATION_SOURCES) or list(sources) != list(VALUATION_SOURCES)):
        raise ValueError("VALUATION_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    expected_archive = "tests/fixtures/evidence_valuation_v1_sources/" + relative + ".txt"
    if not isinstance(row, dict) or row.get("archive") != expected_archive:
        raise ValueError("VALUATION_SOURCE_ARCHIVE_PATH_INVALID")
    if row.get("base_commit") != VALUATION_BASE:
        raise ValueError("VALUATION_SOURCE_TRANSITION_BASE_INVALID")
    active = (root / relative).read_bytes().replace(b"\r\n", b"\n")
    prior = (root / expected_archive).read_bytes().replace(b"\r\n", b"\n")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    prior_sha = hashlib.sha256(prior).hexdigest()
    active_sha = hashlib.sha256(active).hexdigest()
    if (row.get("prior_sha256_lf") != pins[relative] or prior_sha != pins[relative]
            or row.get("active_sha256_lf") != active_sha or active_sha == prior_sha):
        raise ValueError("VALUATION_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _thesis_production_prior_bytes(root: Path, relative: str) -> bytes:
    """Return archived origin/main bytes for the one approved Thesis source.

    The admitted path is the code constant above. A manifest that names another
    file, adds a field, or omits this file is refused. The archive and the live
    file are hashed on every call.
    """
    if relative != THESIS_SOURCE:
        raise ValueError("THESIS_SOURCE_TRANSITION_SCOPE_INVALID")
    manifest = root / THESIS_MANIFEST
    if not manifest.is_file():
        raise ValueError("THESIS_SOURCE_TRANSITION_INVALID")
    spec = json.loads(manifest.read_bytes())
    if set(spec) != _THESIS_FIELDS:
        raise ValueError("THESIS_SOURCE_TRANSITION_SCOPE_INVALID")
    if (spec.get("contract_version") != THESIS_CONTRACT or spec.get("base_commit") != THESIS_BASE
            or spec.get("exception_scope") != THESIS_SCOPE or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("source_path") != THESIS_SOURCE or spec.get("archive") != THESIS_ARCHIVE):
        raise ValueError("THESIS_SOURCE_TRANSITION_SCOPE_INVALID")
    active = (root / THESIS_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    prior = (root / THESIS_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    prior_sha = hashlib.sha256(prior).hexdigest()
    active_sha = hashlib.sha256(active).hexdigest()
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    pinned = pins.get(THESIS_SOURCE)
    if (spec.get("prior_sha256_lf") != prior_sha or spec.get("active_sha256_lf") != active_sha
            or active_sha == prior_sha or (pinned is not None and pinned != prior_sha)):
        raise ValueError("THESIS_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def historical_bytes(root: Path, relative: str) -> bytes:
    """Verify both sides of an approved boundary before supplying legacy bytes."""
    content = (root / relative).read_bytes().replace(b"\r\n", b"\n")
    content = _storage_prior_bytes(root, relative, content)
    if relative in VALUATION_SOURCES:
        return _valuation_orchestration_prior_bytes(root, relative)
    if relative == THESIS_SOURCE:
        return _thesis_production_prior_bytes(root, relative)
    content = _financial_research_prior_bytes(root, relative, content)
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


def active_valuation_orchestration_identity(root: Path) -> dict:
    """Attest the live orchestration sources without adopting their historical digest."""
    spec = json.loads((root / VALUATION_MANIFEST).read_bytes())
    execution = e4.source_identity(root, version="v1")
    execution_paths = {row["path"] for row in execution["sources"].values()}
    if set(VALUATION_SOURCES) & execution_paths:
        raise ValueError("VALUATION_SOURCE_EXECUTION_DOMAIN_INVALID")
    rows = {}
    for relative in VALUATION_SOURCES:
        historical = historical_bytes(root, relative)
        active = (root / relative).read_bytes().replace(b"\r\n", b"\n")
        historical_sha = hashlib.sha256(historical).hexdigest()
        active_sha = hashlib.sha256(active).hexdigest()
        declared = spec["sources"][relative]
        if (historical_sha != declared["prior_sha256_lf"] or active_sha != declared["active_sha256_lf"]
                or active_sha == historical_sha):
            raise ValueError("VALUATION_SOURCE_TRANSITION_BINDING_INVALID")
        rows[relative] = {"historical_sha256_lf": historical_sha, "active_sha256_lf": active_sha}
    return {
        "contract_version": VALUATION_CONTRACT,
        "base_commit": VALUATION_BASE,
        "sources": rows,
        "execution_code_digest": execution["code_digest"],
        "execution_source_version": execution["source_version"],
        "historical_receipt_adoption": False,
        "cache_policy": "EXACT_ACTIVE_BYTES_REQUIRED_NO_HISTORICAL_RECEIPT_ADOPTION",
        "release_authority": "NOT_GRANTED",
    }


def active_thesis_evidence_identity(root: Path) -> dict:
    """Attest the live Thesis source without adopting its historical or mixed digest."""
    spec = json.loads((root / THESIS_MANIFEST).read_bytes())
    historical_file = historical_bytes(root, THESIS_SOURCE)
    active_file = (root / THESIS_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    historical_sha = hashlib.sha256(historical_file).hexdigest()
    active_sha = hashlib.sha256(active_file).hexdigest()
    if (historical_sha != spec["prior_sha256_lf"] or active_sha != spec["active_sha256_lf"]
            or active_sha == historical_sha):
        raise ValueError("THESIS_SOURCE_TRANSITION_BINDING_INVALID")
    execution = e4.source_identity(root, version="v2")
    historical = legacy_source_identity(root, version="v2")
    if THESIS_SOURCE not in {row["path"] for row in execution["sources"].values()}:
        raise ValueError("THESIS_SOURCE_EXECUTION_DOMAIN_INVALID")
    if historical["code_digest"] != spec["historical_e4_v2_digest"]:
        raise ValueError("THESIS_SOURCE_HISTORICAL_DIGEST_MISMATCH")
    if execution["code_digest"] != spec["active_e4_v2_digest"] or execution["code_digest"] == historical["code_digest"]:
        raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
    if spec["rejected_mixed_digest"] in {execution["code_digest"], historical["code_digest"]}:
        raise ValueError("THESIS_SOURCE_MIXED_DIGEST_REJECTED")
    historical_receipt = {
        "source_version": "v2", "contract_version": "e4_infrastructure_source/v2",
        "code_digest": historical["code_digest"], "input_digest": "historical-receipt",
    }
    mixed_receipt = {**historical_receipt, "code_digest": spec["rejected_mixed_digest"]}
    if (e4.candidate_reuse_eligible(historical_receipt, execution, input_digest="historical-receipt")
            or e4.candidate_reuse_eligible(mixed_receipt, execution, input_digest="historical-receipt")):
        raise ValueError("THESIS_SOURCE_HISTORICAL_RECEIPT_ADOPTED")
    return {
        "contract_version": THESIS_CONTRACT,
        "base_commit": THESIS_BASE,
        "source_path": THESIS_SOURCE,
        "historical_sha256_lf": historical_sha,
        "active_sha256_lf": active_sha,
        "historical_e4_v2_digest": historical["code_digest"],
        "active_e4_v2_digest": execution["code_digest"],
        "historical_receipt_adoption": False,
        "cache_policy": "EXACT_ACTIVE_BYTES_REQUIRED_NO_HISTORICAL_RECEIPT_ADOPTION",
        "release_authority": "NOT_GRANTED",
    }


def active_reader_identity(root: Path) -> dict:
    historical_bytes(root, READER)
    spec = json.loads((root / MANIFEST).read_bytes())
    active = e4.source_identity(root, version="v1")
    return {"reader_version": spec["reader_version"], "execution_code_digest": active["code_digest"],
            "source_version": "retention_reader_source/v2", "legacy_receipt_adoption": False,
            "cache_policy": "EXACT_EXECUTION_AND_VERIFIER_DIGEST_REQUIRED_NO_CROSS_VERSION_ADOPTION"}
