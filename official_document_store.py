"""Immutable, content-addressed store for official corporate-action documents (pillar B).

WHAT THIS IS
    The retention layer between the source registry and event extraction. Every document is
    stored under its own SHA-256, and every fact later extracted cites that hash, so
    extraction is re-runnable against retained bytes without re-fetching anything.

IMMUTABILITY IS ENFORCED, NOT REQUESTED
    * A document's bytes are written once. Writing different bytes to an existing content
      path raises `HashConflict` rather than overwriting.
    * A manifest record is never edited. A corrected or superseded document is a **new**
      record carrying `supersedes_document_id`, and the superseded record keeps its own
      identity and content forever.
    * Nothing is ever deleted. There is no delete function in this module, deliberately.

    `docs/DECISIONS.md` records the same rule for the evidence manifest ("Nothing is ever
    edited, reordered, or deleted; a correction is a new row"). This store applies it to the
    document bytes themselves.

RETAINED DOCUMENTS ARE FIRST-CLASS INPUTS
    The repository already holds official documents acquired under the 2026-07-30 allowlist,
    including two HPG corporate-action notices. `adopt_retained_document` registers those
    bytes into this store by hash without issuing a request, which is what lets the bounded
    vertical slice prove the whole pipeline offline. Adoption re-hashes the file at adoption
    time; it never trusts a hash recorded elsewhere.

WHAT THIS MODULE DOES NOT DO
    It does not fetch. Acquisition stays in `official_document_acquisition.py`, which already
    implements bounded retries, response validation and hash-addressed retention against an
    allowlist. This module owns identity, metadata, immutability and supersession.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from atomic_io import atomic_write_file, atomic_write_json

VERSION = "1.0.0"

STORE_RELATIVE = Path("data") / "official-corporate-actions"
DOCUMENTS_RELATIVE = STORE_RELATIVE / "documents"
MANIFEST_FILENAME = "document_manifest.json"

#: Document classes this store recognises. A class outside the set is refused rather than
#: stored as "other", because the event extractor dispatches on it.
DOCUMENT_TYPES = (
    "corporate_action_notice",
    "ex_right_notice",
    "listing_change_notice",
    "last_registration_date_notice",
    "agm_document_or_resolution",
    "corporate_governance_report",
    "annual_report",
    "audited_annual_financial_statements",
    "reviewed_interim_financial_statements",
    "amendment_or_supersession_notice",
)

RETRIEVAL_RETAINED = "retained"
RETRIEVAL_ADOPTED = "adopted_from_retained_evidence"

PARSER_READY = "ready_for_direct_citations"
PARSER_NEEDS_OCR = "needs_ocr"
PARSER_MALFORMED = "malformed_document"
PARSER_UNKNOWN = "not_assessed"

_MIME_BY_SUFFIX = {".pdf": "application/pdf", ".html": "text/html", ".htm": "text/html"}


class HashConflict(ValueError):
    """Different bytes were offered for a content path that already exists."""


class UnsupportedDocument(ValueError):
    """The document type or media type is outside what this store accepts."""


def store_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / STORE_RELATIVE


def documents_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / DOCUMENTS_RELATIVE


def manifest_path(runtime_root: Path | str) -> Path:
    return store_root(runtime_root) / MANIFEST_FILENAME


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_id(ticker: str, source_url: str, content_sha256: str) -> str:
    """Stable identity: the same bytes from the same URL for the same issuer are one document."""
    return hashlib.sha256(
        f"{str(ticker).upper()}|{source_url}|{content_sha256}".encode("utf-8")).hexdigest()


def detect_media_type(filename: str, prefix: bytes) -> str:
    """Media type from the magic bytes, cross-checked against the suffix."""
    suffix = Path(filename).suffix.lower()
    declared = _MIME_BY_SUFFIX.get(suffix)
    if prefix.startswith(b"%PDF"):
        sniffed = "application/pdf"
    elif b"<html" in prefix[:2048].lower() or b"<!doctype html" in prefix[:2048].lower():
        sniffed = "text/html"
    else:
        sniffed = None
    if sniffed is None:
        raise UnsupportedDocument(
            f"{filename}: bytes are neither PDF nor HTML; refusing to retain an unknown format")
    if declared is not None and declared != sniffed:
        raise UnsupportedDocument(
            f"{filename}: suffix declares {declared} but the bytes are {sniffed}")
    return sniffed


def assess_parser_state(path: Path | str, media_type: str) -> str:
    """Whether text can be read directly, OCR is needed, or the document is malformed."""
    if media_type == "text/html":
        return PARSER_READY
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        has_text = any((page.extract_text() or "").strip() for page in reader.pages)
        return PARSER_READY if has_text else PARSER_NEEDS_OCR
    except Exception:  # noqa: BLE001 - an unreadable PDF is a recorded state, not a crash
        return PARSER_MALFORMED


def load_manifest(runtime_root: Path | str) -> dict[str, Any]:
    path = manifest_path(runtime_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": VERSION, "records": []}
    if not isinstance(payload, Mapping) or payload.get("schema_version") != VERSION:
        return {"schema_version": VERSION, "records": []}
    records = payload.get("records")
    return {"schema_version": VERSION,
            "records": [dict(record) for record in records] if isinstance(records, list) else []}


def manifest_index(runtime_root: Path | str) -> dict[str, dict[str, Any]]:
    return {str(record["document_id"]): record
            for record in load_manifest(runtime_root)["records"]
            if record.get("document_id")}


def content_path(runtime_root: Path | str, ticker: str, document_type: str,
                 content_sha256: str, media_type: str) -> Path:
    suffix = ".pdf" if media_type == "application/pdf" else ".html"
    return (documents_root(runtime_root) / str(ticker).upper() / str(document_type)
            / f"{content_sha256}{suffix}")


def _write_manifest(runtime_root: Path | str, records: Iterable[Mapping[str, Any]]) -> None:
    ordered = sorted((dict(record) for record in records),
                     key=lambda record: (str(record.get("ticker") or ""),
                                         str(record.get("document_type") or ""),
                                         str(record.get("content_sha256") or "")))
    atomic_write_json(manifest_path(runtime_root),
                      {"schema_version": VERSION, "records": ordered})


def adopt_retained_document(runtime_root: Path | str, source_path: Path | str, *,
                            ticker: str, document_type: str, source_url: str,
                            source_authority: str, observed_at: str,
                            published_at: str | None = None,
                            supersedes_document_id: str | None = None,
                            execute: bool = False) -> dict[str, Any]:
    """Register already-retained official bytes into the store, without any network request.

    The hash is recomputed from the file at adoption time. A hash recorded in some other
    manifest is metadata about a past retrieval, not evidence about the bytes on disk now.
    """
    source_path = Path(source_path)
    if not source_path.is_file():
        raise UnsupportedDocument(f"retained document not found: {source_path}")
    if str(document_type) not in DOCUMENT_TYPES:
        raise UnsupportedDocument(f"unsupported document_type: {document_type!r}")

    payload = source_path.read_bytes()
    media_type = detect_media_type(source_path.name, payload[:4096])
    content_sha256 = sha256_bytes(payload)
    identity = document_id(ticker, source_url, content_sha256)

    existing = manifest_index(runtime_root)
    target = content_path(runtime_root, ticker, document_type, content_sha256, media_type)
    if target.exists() and sha256_file(target) != content_sha256:
        raise HashConflict(f"{target} already holds different bytes")

    if identity in existing:
        return {"state": "already_retained", "document_id": identity,
                "content_sha256": content_sha256, "record": existing[identity]}

    parser_state = assess_parser_state(source_path, media_type)
    record = {
        "document_id": identity,
        "ticker": str(ticker).upper(),
        "source_authority": str(source_authority),
        "source_url": str(source_url),
        "document_type": str(document_type),
        "media_type": media_type,
        "content_sha256": content_sha256,
        "content_length": len(payload),
        "relative_path": target.relative_to(Path(runtime_root)).as_posix(),
        "published_at": published_at,
        "observed_at": str(observed_at),
        "retrieval_status": RETRIEVAL_ADOPTED,
        "parser_status": parser_state,
        "supersedes_document_id": supersedes_document_id,
        "adopted_from": str(source_path),
        "store_version": VERSION,
    }
    if execute:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            atomic_write_file(target, payload)
        _write_manifest(runtime_root, [*load_manifest(runtime_root)["records"], record])
    return {"state": "retained" if execute else "planned", "document_id": identity,
            "content_sha256": content_sha256, "record": record}


def read_document(runtime_root: Path | str, document_id_value: str) -> bytes:
    """Retained bytes for one document, verified against the recorded hash before returning."""
    record = manifest_index(runtime_root).get(str(document_id_value))
    if record is None:
        raise KeyError(f"unknown document_id: {document_id_value}")
    path = Path(runtime_root) / str(record["relative_path"])
    payload = path.read_bytes()
    actual = sha256_bytes(payload)
    if actual != record["content_sha256"]:
        raise HashConflict(
            f"{path} hashes to {actual}, the manifest records {record['content_sha256']}")
    return payload


def verify(runtime_root: Path | str) -> dict[str, Any]:
    """Every retained document re-hashed against its manifest record. Never writes."""
    findings: list[dict[str, Any]] = []
    checked = 0
    for record in load_manifest(runtime_root)["records"]:
        path = Path(runtime_root) / str(record.get("relative_path") or "")
        if not path.is_file():
            findings.append({"document_id": record.get("document_id"),
                             "finding": "document_missing", "path": str(path)})
            continue
        actual = sha256_file(path)
        if actual != record.get("content_sha256"):
            findings.append({"document_id": record.get("document_id"),
                             "finding": "content_sha256_mismatch",
                             "recorded": record.get("content_sha256"), "actual": actual})
            continue
        checked += 1
    return {"ok": not findings, "checked": checked, "findings": findings}
