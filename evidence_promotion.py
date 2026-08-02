"""Approved evidence write boundary (P0.2). See docs/DECISIONS.md, 2026-08-02,
"Approved evidence write boundary".

This module is the sole writer authorized to append records into
<runtime_root>/data/official-evidence/manifest.json and its *_citations.jsonl
sidecars. It never rewrites, deletes, or reorders an existing record; a
correction is expressed with `supersedes_citation_ids` on a new row, exactly
as semantic_evidence_bridge.py's loaders already expect. It never touches
vn_stock.db, analysis_bundle.json, bundle_manifest.json, or focus_extract.json.

Every promotion is two-phase:
  1. build_manifest_record() / build_cash_dividend_citation() / build_non_cash_event_citation()
     are pure and I/O-free (safe to call in a dry run); they verify the referenced evidence
     document's live hash but perform no writes.
  2. promote() is the only function that writes. It is idempotent (rows are deduped by
     evidence_id / citation_id) and defaults to dry_run=True so a caller must opt in to a
     real write.

Precedent for citing evidence retained outside <runtime_root>/data/official-evidence/ via
archive_document_path already exists in production manifest.json (the VCB annual-report
record points at operations-review/evidence/...); this module formalizes that pattern
rather than introducing a new one.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import semantic_evidence_bridge as bridge

MANIFEST_RELATIVE = bridge.MANIFEST_RELATIVE
CASH_DIVIDEND_RELATIVE = bridge.CASH_DIVIDEND_RELATIVE
NON_CASH_EVENT_RELATIVE = bridge.NON_CASH_EVENT_RELATIVE
QUALIFICATION_CITATIONS_RELATIVE = bridge.CITATIONS_RELATIVE
MANIFEST_SCHEMA_VERSION = bridge.MANIFEST_SCHEMA_VERSION
VERSION = "1.0.0"


def _sha256_file(path: Path) -> str:
    return bridge._sha256_file(path)


def _hash(value: Any) -> str:
    return bridge._hash(value)


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": MANIFEST_SCHEMA_VERSION, "records": []}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported manifest schema_version {manifest.get('schema_version')!r}")
    if not isinstance(manifest.get("records"), list):
        raise ValueError("manifest.records must be a list")
    return manifest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_manifest_record(*, evidence_id: str, archive_document_path: Path, sha256: str,
                           filename: str, **fields: Any) -> dict[str, Any]:
    """Pure. Verifies the referenced document exists and hashes to `sha256` before returning
    the record. Raises ValueError on any mismatch. `filename` is required (not just
    `archive_document_path`) because semantic_evidence_bridge._load_manifest() silently
    drops any record where `filename` is falsy, before it ever checks the path or hash --
    an easy way to produce a manifest entry that looks written but is invisible to every
    loader. Performs no write."""
    if not filename:
        raise ValueError("filename is required: semantic_evidence_bridge._load_manifest() silently discards records without it")
    archive_document_path = Path(archive_document_path)
    if not archive_document_path.is_file():
        raise ValueError(f"evidence file not found: {archive_document_path}")
    live = _sha256_file(archive_document_path)
    if live != sha256:
        raise ValueError(f"hash mismatch for {archive_document_path}: expected {sha256}, got {live}")
    return {
        "evidence_id": evidence_id,
        "archive_document_path": str(archive_document_path),
        "sha256": sha256,
        "filename": filename,
        "qualification_state": "qualified",
        "is_actionable": False,
        "warnings": [],
        **fields,
    }


def build_cash_dividend_citation(*, ticker: str, resolution_number: str, declaration_date: str,
                                  cash_amount: float, currency: str, evidence_id: str,
                                  record_date: str | None = None, payment_date: str | None = None,
                                  event_status: str = "completed", citation: str | None = None,
                                  verified_at: str | None = None,
                                  supersedes_citation_ids: list[str] | None = None) -> dict[str, Any]:
    """Pure. citation_id is computed exactly as
    semantic_evidence_bridge.load_verified_cash_dividends() re-derives it, so the row is
    accepted deterministically instead of being rejected as citation_id_not_deterministic."""
    event_type = "cash_dividend"
    citation_id = _hash({
        "ticker": ticker, "event_type": event_type, "resolution_number": resolution_number,
        "declaration_date": declaration_date, "cash_amount": cash_amount,
        "payment_date": payment_date, "event_status": event_status, "evidence_id": evidence_id,
    })
    return {
        "citation_id": citation_id, "ticker": ticker, "event_type": event_type,
        "resolution_number": resolution_number, "declaration_date": declaration_date,
        "cash_amount": cash_amount, "currency": currency, "evidence_id": evidence_id,
        "record_date": record_date, "payment_date": payment_date, "event_status": event_status,
        "citation": citation, "verified_at": verified_at,
        "supersedes_citation_ids": supersedes_citation_ids or [],
    }


def promote(runtime_root: Path, *, manifest_records: list[dict[str, Any]] = (),
            citation_relative: Path | None = None, citation_records: list[dict[str, Any]] = (),
            dry_run: bool = True) -> dict[str, Any]:
    """The sole writer. Appends `manifest_records` (deduped by evidence_id) to
    <runtime_root>/data/official-evidence/manifest.json and `citation_records` (deduped by
    citation_id) to <runtime_root>/<citation_relative>.

    Idempotent: re-running with identical inputs reports added=0 for both and writes nothing.
    Never removes, edits, or reorders an existing record. dry_run defaults to True: the
    returned diff is computed and reported but nothing is written unless dry_run=False.
    """
    runtime_root = Path(runtime_root)
    manifest_path = runtime_root / MANIFEST_RELATIVE
    manifest = _read_manifest(manifest_path)
    existing_evidence_ids = {r.get("evidence_id") for r in manifest["records"]}
    new_manifest_records = [r for r in manifest_records if r.get("evidence_id") not in existing_evidence_ids]

    citation_path = (runtime_root / citation_relative) if citation_relative is not None else None
    existing_citation_ids: set[str] = set()
    new_citation_records: list[dict[str, Any]] = []
    if citation_path is not None:
        existing_citation_ids = {r.get("citation_id") for r in _read_jsonl(citation_path)}
        new_citation_records = [r for r in citation_records if r.get("citation_id") not in existing_citation_ids]

    result = {
        "status": "dry_run" if dry_run else "promoted",
        "version": VERSION,
        "manifest_path": str(manifest_path),
        "manifest_added": len(new_manifest_records),
        "manifest_skipped_existing": len(manifest_records) - len(new_manifest_records),
        "citation_path": str(citation_path) if citation_path else None,
        "citation_added": len(new_citation_records),
        "citation_skipped_existing": len(citation_records) - len(new_citation_records) if citation_path else 0,
        "new_manifest_evidence_ids": [r["evidence_id"] for r in new_manifest_records],
        "new_citation_ids": [r["citation_id"] for r in new_citation_records],
    }
    if dry_run:
        return result

    if new_manifest_records:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest["records"] = manifest["records"] + new_manifest_records
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    if citation_path is not None and new_citation_records:
        citation_path.parent.mkdir(parents=True, exist_ok=True)
        with citation_path.open("a", encoding="utf-8") as handle:
            for record in new_citation_records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    return result
