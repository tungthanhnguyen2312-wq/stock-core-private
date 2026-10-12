"""Bounded SSI FY2024 issuer-financial identity materialization.

This module uses one already-retained, hash-verified SSI issuer PDF.  It does
not acquire documents, call providers, write a runtime, or apply corporate
debt semantics to a securities issuer.  The existing financial-identity
contract admits the direct current-liabilities line; other SSI financial
metrics remain governed by the separate securities-sector semantics contract.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import evidence_promotion as promotion
from annual_financial_ocr_materialization import render_and_ocr, verified_extraction, write_materialization


DEFAULT_EVIDENCE_ROOT = Path("operations-review") / "governed-official-evidence-v1"
MATERIALIZATION_ROOT = Path("derived") / "annual_financial_ocr_materialization_v1"
SSI_FY2024_SHA256 = "38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74"
VERIFIED_AT = "2026-08-11T00:00:00+07:00"
CURRENT_LIABILITIES = 46_599_438_522_989


def _record(evidence_root: Path) -> dict[str, Any]:
    manifest = json.loads((Path(evidence_root) / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    records = [dict(row) for row in manifest.get("records") or [] if isinstance(row, Mapping)
               and row.get("ticker") == "SSI" and row.get("sha256") == SSI_FY2024_SHA256]
    if len(records) != 1 or records[0].get("acquisition_status") != "retained":
        raise ValueError("SSI_RETAINED_SOURCE_NOT_QUALIFIED")
    return records[0]


def materialize_ssi_current_liabilities(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """OCR only page 10, the cited FY2024 consolidated-liabilities source page."""
    root = Path(evidence_root)
    record = _record(root)
    materialization = render_and_ocr(record, root=root, pages=(10,), language="eng", psm={10: 6}, dpi=288)
    write_materialization(root / MATERIALIZATION_ROOT / "ssi-fy2024-current-liabilities.json", materialization)
    return materialization


def build_ssi_promotion(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the one direct, contract-supported SSI financial-identity promotion."""
    root = Path(evidence_root)
    record = _record(root)
    sidecar = root / MATERIALIZATION_ROOT / "ssi-fy2024-current-liabilities.json"
    if not sidecar.is_file():
        raise ValueError("SSI_MATERIALIZATION_REQUIRED")
    materialization = json.loads(sidecar.read_text(encoding="utf-8"))
    if materialization.get("document_sha256") != record["sha256"] or materialization.get("document_id") != record["document_id"]:
        raise ValueError("SSI_SIDECAR_DOCUMENT_MISMATCH")
    evidence_id = promotion._hash({"ticker": "SSI", "document_sha256": record["sha256"],
                                   "document_id": record["document_id"]})
    manifest = promotion.build_manifest_record(
        evidence_id=evidence_id, archive_document_path=root / record["relative_path"], sha256=record["sha256"],
        filename=Path(record["relative_path"]).name, ticker="SSI", issuer="SSI Securities Corporation",
        authority=record["source_authority"], authority_domain="ssi.com.vn",
        evidence_type="audited_consolidated_financial_statements", source_url=record["canonical_url"],
        document_title="SSI audited consolidated financial statements FY2024", document_id=record["document_id"],
        document_class=record["document_class"], reporting_period="2024", published_at=record["published_at"],
        observed_at=record["observed_at"], statement_scope="consolidated", audit_status="audited",
        source_id=record.get("source_id", "issuer_ir"),
    )
    extraction = verified_extraction(
        materialization, page=10, raw_label="Current liabilities", raw_value="46,599,438,522,989",
        source_raw_label="Current liabilities", source_raw_value="46,599,438,522,989", unit="VND",
        statement="balance_sheet", visual_source_page_verified=True,
    )
    citation = promotion.build_financial_identity_citation(
        ticker="SSI", metric="current_liabilities", reporting_period="2024", value=CURRENT_LIABILITIES,
        evidence_id=evidence_id, currency="VND", citation=(
            "Issuer PDF page 10; Current liabilities; consolidated FY2024 statement of financial position."),
        verified_at=VERIFIED_AT, extraction=extraction,
    )
    return [manifest], [citation]
