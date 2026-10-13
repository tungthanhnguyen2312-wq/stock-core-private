"""Bounded FPT FY2025 audited-consolidated financial-evidence promotion."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import evidence_promotion as promotion
from annual_financial_ocr_materialization import (
    render_and_ocr,
    verified_debt_extraction,
    verified_extraction,
    write_materialization,
)


DEFAULT_EVIDENCE_ROOT = Path("operations-review") / "governed-official-evidence-v1"
MATERIALIZATION_ROOT = Path("derived") / "annual_financial_ocr_materialization_v1"
FPT_FY2025_DOCUMENT_ID = "7c7ec0a1e76045bbb655f46f807165962516f3b16833a005a57af59a0e6bce32"
FPT_FY2025_SHA256 = "630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4"
VERIFIED_AT = "2026-08-11T00:00:00Z"

# Each tuple keeps the exact OCR anchor separate from the issuer's displayed label.  The former
# is a deterministic locator; the latter is the source-facing citation label.
FPT_FACTS = (
    ("cash_and_equivalents", 10_522_105_729_992, 8,
     "Ti\u00e9n va cac khoan tuong dwong ti\u00e9n", "10.522.105.729.992",
     "Ti\u1ec1n v\u00e0 c\u00e1c kho\u1ea3n t\u01b0\u01a1ng \u0111\u01b0\u01a1ng ti\u1ec1n", "10.522.105.729.992", "balance_sheet"),
    ("shareholders_equity", 43_748_040_747_539, 11,
     "VON CHU SO H\u1eeeU", "43.748.040.747.539",
     "V\u1ed0N CH\u1ee6 S\u1ede H\u1eeeU", "43.748.040.747.539", "balance_sheet"),
    ("net_income", 11_232_339_450_734, 12,
     "Loi nhuan sau thu\u00e9 TNDN", "11.232.339.450.734",
     "L\u1ee3i nhu\u1eadn sau thu\u1ebf TNDN", "11.232.339.450.734", "income_statement"),
    ("operating_cash_flow", 10_136_043_915_911, 13,
     "Luu chuy\u00e9n ti\u00e9n thuan tir hoat d\u00e9ng kinh doanh", "10.136.043.915.911",
     "L\u01b0u chuy\u1ec3n ti\u1ec1n thu\u1ea7n t\u1eeb ho\u1ea1t \u0111\u1ed9ng kinh doanh", "10.136.043.915.911", "cash_flow"),
)
FPT_DEBT = (
    {"page": 10, "component_type": "short_term_borrowings", "reporting_period": "2025",
     "label": "Vay v\u00e0 n\u1ee3 thu\u00ea t\u00e0i ch\u00ednh ng\u1eafn h\u1ea1n",
     "ocr_label": "Vay v\u00e0 n\u1ee3 thu\u00ea t\u00e0i ch\u00ednh ng\u1eafn h\u1ea1n",
     "raw_value": "19.169.697.497.955", "ocr_raw_value": "19.169.697.497.955",
     "visual_source_page_verified": True},
    {"page": 10, "component_type": "long_term_borrowings_or_finance_leases", "reporting_period": "2025",
     "label": "Vay v\u00e0 n\u1ee3 thu\u00ea t\u00e0i ch\u00ednh d\u00e0i h\u1ea1n",
     "ocr_label": "Vay va no\u2019 thu\u00e9 tai chinh dai han",
     "raw_value": "1.903.789.988.184", "ocr_raw_value": "1.903.789.988.184",
     "visual_source_page_verified": True},
)


def _record(evidence_root: Path) -> dict[str, Any]:
    manifest = json.loads((Path(evidence_root) / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    records = [dict(row) for row in manifest.get("records") or [] if isinstance(row, Mapping)
               and row.get("ticker") == "FPT" and row.get("document_id") == FPT_FY2025_DOCUMENT_ID]
    if len(records) != 1 or records[0].get("acquisition_status") != "retained" or records[0].get("sha256") != FPT_FY2025_SHA256:
        raise ValueError("FPT_FY2025_RETAINED_SOURCE_NOT_QUALIFIED")
    return records[0]


def materialize_fpt_fy2025(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """OCR only the five visually checked annual-statement pages and retain their sidecar."""
    root = Path(evidence_root)
    record = _record(root)
    materialization = render_and_ocr(record, root=root, pages=(8, 10, 11, 12, 13), language="vie+eng", psm=6, dpi=240)
    write_materialization(root / MATERIALIZATION_ROOT / "fpt-fy2025.json", materialization)
    return materialization


def build_fpt_fy2025_promotion(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the five fixed FPT FY2025 records without mutating a runtime root."""
    root = Path(evidence_root)
    record = _record(root)
    sidecar = root / MATERIALIZATION_ROOT / "fpt-fy2025.json"
    if not sidecar.is_file():
        raise ValueError("FPT_FY2025_MATERIALIZATION_REQUIRED")
    materialization = json.loads(sidecar.read_text(encoding="utf-8"))
    if materialization.get("document_id") != record["document_id"] or materialization.get("document_sha256") != record["sha256"]:
        raise ValueError("FPT_FY2025_SIDECAR_DOCUMENT_MISMATCH")
    evidence_id = promotion._hash({"ticker": "FPT", "document_sha256": record["sha256"], "document_id": record["document_id"]})
    manifest = promotion.build_manifest_record(
        evidence_id=evidence_id, archive_document_path=root / record["relative_path"], sha256=record["sha256"],
        filename=Path(record["relative_path"]).name, ticker="FPT", issuer="FPT Corporation",
        authority=record["source_authority"], authority_domain="fpt.com",
        evidence_type="audited_consolidated_financial_statements", source_url=record["canonical_url"],
        document_title="FPT audited consolidated financial statements FY2025", document_id=record["document_id"],
        document_class=record["document_class"], reporting_period="2025", published_at=record["published_at"],
        observed_at=record["observed_at"], statement_scope="consolidated", audit_status="audited", source_id=record["source_id"],
    )
    citations = []
    for metric, value, page, ocr_label, ocr_value, source_label, source_value, statement in FPT_FACTS:
        extraction = verified_extraction(
            materialization, page=page, raw_label=ocr_label, raw_value=ocr_value,
            source_raw_label=source_label, source_raw_value=source_value, unit="VND", statement=statement,
            visual_source_page_verified=True,
        )
        citations.append(promotion.build_financial_identity_citation(
            ticker="FPT", metric=metric, reporting_period="2025", value=value, evidence_id=evidence_id, currency="VND",
            citation=f"Issuer PDF page {page}; {source_label}; audited consolidated FY2025.",
            verified_at=VERIFIED_AT, extraction=extraction,
        ))
    debt = verified_debt_extraction(materialization, components=FPT_DEBT, unit="VND", statement="balance_sheet", reporting_period="2025")
    citations.append(promotion.build_financial_identity_citation(
        ticker="FPT", metric="total_interest_bearing_debt", reporting_period="2025", value=debt["normalized_value"],
        evidence_id=evidence_id, currency="VND",
        citation="Issuer PDF page 10; explicit short- and long-term borrowing/finance-lease components; audited consolidated FY2025.",
        verified_at=VERIFIED_AT, extraction=debt,
    ))
    return [manifest], citations


def promote_fpt_fy2025(runtime_root: Path, *, evidence_root: Path = DEFAULT_EVIDENCE_ROOT, dry_run: bool = True) -> dict[str, Any]:
    manifest, citations = build_fpt_fy2025_promotion(evidence_root)
    return promotion.promote(Path(runtime_root), manifest_records=manifest,
                             citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                             citation_records=citations, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT"))
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--materialize", action="store_true")
    parser.add_argument("--promote", action="store_true", help="append through evidence_promotion; default is dry run")
    args = parser.parse_args(argv)
    if args.runtime_root is None:
        parser.error("--runtime-root or STOCK_LOOKUP_RUNTIME_ROOT is required")
    if args.materialize:
        materialize_fpt_fy2025(args.evidence_root)
    print(json.dumps(promote_fpt_fy2025(args.runtime_root, evidence_root=args.evidence_root, dry_run=not args.promote), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
