"""Bounded governed-evidence recovery for the five historical research tickers.

This is deliberately a recovery contract, not a new filing framework.  It fixes the
only permitted legacy cohort and requires a fresh, hash-verified filing path; prior
served bundles and briefs have no input path here.  VNM is the first materialized
slice.  It writes a derived page sidecar under governed retained evidence and returns
promotion records for an explicitly supplied *temporary* evidence root.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import evidence_promotion as promotion
from annual_financial_ocr_materialization import (
    render_and_ocr,
    verified_extraction,
    verified_sum_extraction,
    write_materialization,
)


DEFAULT_EVIDENCE_ROOT = Path("operations-review") / "governed-official-evidence-v1"
MATERIALIZATION_ROOT = Path("derived") / "annual_financial_ocr_materialization_v1"
VERIFIED_AT = "2026-08-09T00:00:00Z"
LEGACY_TICKERS = ("HPG", "VNM", "PAN", "PVD", "NVL")
LEGACY_FILINGS = {
    "HPG": "304a93a65e1587f625e0045d6ec9bcfba6647d19df4034cfd8fc1ec7b62eeb64",
    "VNM": "4313d34c5d2131803e87c11bdd34ff3313d607e901dd37ea6e09f5600441a6ab",
    "PAN": "f1d6fb0dde557d9e098e13cc10ca0b0506e10e446f3ac6dc8122c4fa560df006",
    "PVD": "ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14",
    "NVL": "078fe614549d6f139b3cd3e9bdcd9f99a533b03c067c5018a989166cb2eab3d3",
}

# The anchors are exact OCR occurrences checked against pages 182--187 in the retained
# report.  The report labels all figures VND million; values are normalized to VND while
# `unit_scale` retains the displayed scale in every citation.
VNM_FACTS = (
    ("cash_and_equivalents", 2_225_944_000_000, 92, "Cash and cash equivalents", "2,225,944", "balance_sheet"),
    ("shareholders_equity", 37_165_930_000_000, 92, "Equity", "37,165,930", "balance_sheet"),
    ("net_income", 8_686_245_000_000, 93, "Net profit", "8,686,245", "income_statement"),
    ("operating_cash_flow", 9_770_587_000_000, 94, "Net cash generated from operating activities", "9,770,587", "cash_flow"),
)
VNM_DEBT_COMPONENTS = (
    {"page": 92, "label": "Borrowings", "raw_value": "9,115,435", "visual_source_page_verified": True},
    {"page": 92, "label": "Borrowings", "raw_value": "157,904", "visual_source_page_verified": True},
)


def _normalize_vnd_millions(extraction: Mapping[str, Any]) -> dict[str, Any]:
    """Retain displayed-unit provenance while normalizing a cited value to VND units."""
    result = dict(extraction)
    result["normalized_value"] = int(result["normalized_value"]) * 1_000_000
    if result.get("method") == "document_line_item_sum":
        result["components"] = [{**component, "value": int(component["value"]) * 1_000_000}
                                for component in result["components"]]
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _retained_records(evidence_root: Path) -> list[dict[str, Any]]:
    manifest = json.loads((Path(evidence_root) / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError("RETAINED_FILING_MANIFEST_MALFORMED")
    return [dict(record) for record in records if isinstance(record, Mapping)]


def retained_filing(evidence_root: Path, ticker: str) -> dict[str, Any]:
    """Return exactly the fixed retained filing for one approved legacy ticker."""
    ticker = str(ticker).upper()
    if ticker not in LEGACY_FILINGS:
        raise ValueError("LEGACY_TICKER_OUT_OF_SCOPE")
    matches = [record for record in _retained_records(evidence_root)
               if str(record.get("ticker") or "").upper() == ticker
               and record.get("sha256") == LEGACY_FILINGS[ticker]
               and record.get("acquisition_status") == "retained"
               and record.get("reporting_period") == "2024"]
    if len(matches) != 1:
        raise ValueError(f"RETAINED_FILING_AMBIGUOUS_OR_MISSING:{ticker}")
    record = matches[0]
    source = Path(evidence_root) / str(record.get("relative_path") or "")
    if not source.is_file() or _sha256_file(source) != record["sha256"]:
        raise ValueError(f"RETAINED_FILING_HASH_MISMATCH:{ticker}")
    return record


def recovery_contract(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """Verify the exact five-filing recovery boundary without materializing a fact."""
    root = Path(evidence_root)
    records = {ticker: retained_filing(root, ticker) for ticker in LEGACY_TICKERS}
    return {
        "contract": "legacy_qualified_cohort_recovery/v1",
        "tickers": list(LEGACY_TICKERS),
        "restoration_sources": "retained_official_filings_only",
        "comparison_outputs_permitted_as_evidence": False,
        "documents": {ticker: {"document_id": record["document_id"], "sha256": record["sha256"],
                                "relative_path": record["relative_path"]}
                      for ticker, record in records.items()},
        "is_actionable": False,
    }


def materialize_vnm(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """OCR only VNM FY2024 statement pages 92--94 and persist the hash-bound sidecar."""
    root = Path(evidence_root)
    record = retained_filing(root, "VNM")
    materialization = render_and_ocr(record, root=root, pages=(92, 93, 94), language="eng",
                                     psm={92: 6, 93: 6, 94: 6}, dpi=288)
    write_materialization(root / MATERIALIZATION_ROOT / "vnm-fy2024.json", materialization)
    return materialization


def build_vnm_promotion(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build VNM's five fresh citation records; this does not write an evidence root."""
    root = Path(evidence_root)
    record = retained_filing(root, "VNM")
    sidecar = root / MATERIALIZATION_ROOT / "vnm-fy2024.json"
    if not sidecar.is_file():
        raise ValueError("VNM_MATERIALIZATION_REQUIRED")
    materialization = json.loads(sidecar.read_text(encoding="utf-8"))
    if materialization.get("document_sha256") != record["sha256"]:
        raise ValueError("VNM_MATERIALIZATION_SOURCE_HASH_MISMATCH")
    evidence_id = promotion._hash({"ticker": "VNM", "document_sha256": record["sha256"],
                                   "document_id": record["document_id"]})
    manifest = promotion.build_manifest_record(
        evidence_id=evidence_id, archive_document_path=root / record["relative_path"], sha256=record["sha256"],
        filename=Path(record["relative_path"]).name, ticker="VNM",
        issuer="Vietnam Dairy Products Joint Stock Company", authority=record["source_authority"],
        authority_domain="vinamilk.com.vn", evidence_type="audited_consolidated_financial_statements",
        source_url=record["canonical_url"], document_title="Vinamilk FY2024 annual report consolidated financial statements",
        document_id=record["document_id"], document_class=record["document_class"], reporting_period="2024",
        published_at=record["published_at"], observed_at=record["observed_at"], statement_scope="consolidated",
        audit_status="audited", source_id="issuer_ir",
    )
    citations = []
    for metric, value, page, label, raw_value, statement in VNM_FACTS:
        extraction = verified_extraction(materialization, page=page, raw_label=label, raw_value=raw_value,
                                         unit="VND million", statement=statement,
                                         visual_source_page_verified=True)
        extraction = _normalize_vnd_millions(extraction)
        citations.append(promotion.build_financial_identity_citation(
            ticker="VNM", metric=metric, reporting_period="2024", value=value, evidence_id=evidence_id,
            currency="VND", unit_scale=1_000_000,
            citation=f"Issuer annual-report PDF page {page}; {label}; consolidated FY2024; displayed in VND million.",
            verified_at=VERIFIED_AT, extraction=extraction,
        ))
    debt = verified_sum_extraction(materialization, components=VNM_DEBT_COMPONENTS,
                                   unit="VND million", statement="balance_sheet")
    debt = _normalize_vnd_millions(debt)
    debt_value = debt["normalized_value"]
    citations.append(promotion.build_financial_identity_citation(
        ticker="VNM", metric="total_interest_bearing_debt", reporting_period="2024", value=debt_value,
        evidence_id=evidence_id, currency="VND", unit_scale=1_000_000,
        citation=("Issuer annual-report PDF page 92; current and non-current Borrowings components; "
                  "consolidated FY2024; displayed in VND million."),
        verified_at=VERIFIED_AT, extraction=debt,
    ))
    return [manifest], citations
