"""Bounded FY2024 issuer-financial materialization for QNS and POW only.

This module never acquires a document, calls a provider, changes a database, or writes a
runtime.  QNS is inspected by native text only.  POW's four cited pages use the established,
page-preserving OCR contract; promotion requests are returned for an isolated review root and
remain subject to the existing sole writer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import evidence_promotion as promotion
from annual_financial_ocr_materialization import (
    extract_pdf_text,
    render_and_ocr,
    verified_debt_extraction,
    verified_extraction,
    write_materialization,
)


DEFAULT_EVIDENCE_ROOT = Path("operations-review") / "governed-official-evidence-v1"
MATERIALIZATION_ROOT = Path("derived") / "annual_financial_ocr_materialization_v1"
VERIFIED_AT = "2026-08-09T00:00:00Z"
QNS_SHA256 = "a43f5b274524e3c7f754e037ddf143793f8c26a41b826b74b53b56c380f3aa4a"
POW_SHA256 = "e2f6e74e1702d406473a427c0036a543c5d49c57e3b9a03469fa97d597a9e1a3"
QNS_REQUIRED_STATEMENT_HEADINGS = (
    "BẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT",
    "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT",
    "BÁO CÁO LƯU CHUYỂN TIỀN TỆ HỢP NHẤT",
)

# Every value below was checked on the original source page.  ``ocr_label``/``ocr_raw_value``
# are the exact deterministic OCR anchors, while ``source_raw_*`` preserves what the issuer
# actually displayed; an OCR spelling is never presented as a source label.
POW_FACTS = (
    ("cash_and_equivalents", 11_564_348_565_017, 9,
     "Tién va cdc khoan tuong duro’ng tién", "11.564.348.565.017",
     "Tiền và các khoản tương đương tiền", "11.564.348.565.017", "balance_sheet"),
    ("shareholders_equity", 34_680_634_910_666, 10,
     "Vén chi s& hiru", "34.680.634.910.666",
     "Vốn chủ sở hữu", "34.680.634.910.666", "balance_sheet"),
    ("net_income", 1_211_341_955_166, 11,
     "Loi nhuan sau thué thu nhap", "1.211.341.955.166",
     "Lợi nhuận sau thuế thu nhập doanh nghiệp", "1.211.341.955.166", "income_statement"),
    ("operating_cash_flow", 4_343_815_084_239, 12,
     "Luu chuyén tién thuan tir hoat déng", "4.343.815.084.239",
     "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "4.343.815.084.239", "cash_flow"),
)
POW_DEBT = (
    {"page": 10, "component_type": "short_term_borrowings", "reporting_period": "2024",
     "label": "Vay và nợ thuê tài chính ngắn hạn", "raw_value": "13.508.102.547.690",
     "ocr_label": "Vay va ng thué tai chinh ngan han", "ocr_raw_value": "13.508.102.547.690",
     "visual_source_page_verified": True},
    {"page": 10, "component_type": "long_term_borrowings_or_finance_leases", "reporting_period": "2024",
     "label": "Vay và nợ thuê tài chính dài hạn", "raw_value": "9.151.300.727.761",
     "ocr_label": "Vay va ng thué tai chinh dai han", "ocr_raw_value": "9.151.300.727.761",
     "visual_source_page_verified": True},
)


def _records(evidence_root: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads((Path(evidence_root) / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    return {str(row.get("ticker") or "").upper(): dict(row) for row in manifest.get("records") or [] if isinstance(row, Mapping)}


def _record(evidence_root: Path, ticker: str, sha256: str) -> dict[str, Any]:
    record = _records(evidence_root).get(ticker)
    if record is None or record.get("acquisition_status") != "retained" or record.get("sha256") != sha256:
        raise ValueError(f"RETAINED_SOURCE_NOT_QUALIFIED:{ticker}")
    return record


def inspect_qns(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """Native-text-only package check; QNS is never OCR'd by this milestone."""
    root = Path(evidence_root)
    record = _record(root, "QNS", QNS_SHA256)
    materialization = extract_pdf_text(record, root=root, pages=range(1, 76))
    text = "\n".join(str(row.get("text") or "") for row in materialization["pages"]).casefold()
    missing = [heading for heading in QNS_REQUIRED_STATEMENT_HEADINGS if heading.casefold() not in text]
    return {
        "ticker": "QNS", "document_sha256": record["sha256"], "extraction_method": "pdf_text",
        "source_page_count": materialization["source_page_count"], "statement_cover_page": 75,
        "state": "blocked" if missing else "ready", "reason": "AUDITED_CONSOLIDATED_STATEMENT_SECTION_MISSING" if missing else None,
        "missing_statement_sections": missing, "new_external_document_acquisition": 0,
    }


def materialize_pow(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """OCR only POW's four audited FY2024 statement pages and persist its sidecar."""
    root = Path(evidence_root)
    record = _record(root, "POW", POW_SHA256)
    materialization = render_and_ocr(record, root=root, pages=(9, 10, 11, 12), language="eng",
                                     psm={9: 6, 10: 6, 11: 6, 12: 11}, dpi=288)
    write_materialization(root / MATERIALIZATION_ROOT / "pow-fy2024.json", materialization)
    return materialization


def build_pow_promotion(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the five exact POW promotion records without touching a runtime root."""
    root = Path(evidence_root)
    record = _record(root, "POW", POW_SHA256)
    sidecar = root / MATERIALIZATION_ROOT / "pow-fy2024.json"
    if not sidecar.is_file():
        raise ValueError("POW_MATERIALIZATION_REQUIRED")
    materialization = json.loads(sidecar.read_text(encoding="utf-8"))
    evidence_id = promotion._hash({"ticker": "POW", "document_sha256": record["sha256"], "document_id": record["document_id"]})
    manifest = promotion.build_manifest_record(
        evidence_id=evidence_id, archive_document_path=root / record["relative_path"], sha256=record["sha256"],
        filename=Path(record["relative_path"]).name, ticker="POW", issuer="PetroVietnam Power Corporation - JSC",
        authority=record["source_authority"], authority_domain="pvpower.vn",
        evidence_type="audited_consolidated_financial_statements", source_url=record["canonical_url"],
        document_title="PV Power audited consolidated financial statements FY2024", document_id=record["document_id"],
        document_class=record["document_class"], reporting_period="2024", published_at=record["published_at"],
        observed_at=record["observed_at"], statement_scope="consolidated", audit_status="audited", source_id=record["source_id"],
    )
    citations = []
    for metric, value, page, ocr_label, ocr_value, source_label, source_value, statement in POW_FACTS:
        extraction = verified_extraction(
            materialization, page=page, raw_label=ocr_label, raw_value=ocr_value,
            source_raw_label=source_label, source_raw_value=source_value, unit="VND", statement=statement,
            visual_source_page_verified=True,
        )
        citations.append(promotion.build_financial_identity_citation(
            ticker="POW", metric=metric, reporting_period="2024", value=value, evidence_id=evidence_id,
            currency="VND", citation=f"Issuer PDF page {page}; {source_label}; audited consolidated FY2024.",
            verified_at=VERIFIED_AT, extraction=extraction,
        ))
    debt = verified_debt_extraction(materialization, components=POW_DEBT, unit="VND", statement="balance_sheet", reporting_period="2024")
    citations.append(promotion.build_financial_identity_citation(
        ticker="POW", metric="total_interest_bearing_debt", reporting_period="2024", value=debt["normalized_value"],
        evidence_id=evidence_id, currency="VND", citation="Issuer PDF page 10; exact short- and long-term borrowing/finance-lease components; audited consolidated FY2024.",
        verified_at=VERIFIED_AT, extraction=debt,
    ))
    return [manifest], citations
