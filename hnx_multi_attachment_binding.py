"""Retained-only HNX parent-to-many attachment topology and fail-closed evidence gate."""
from __future__ import annotations

import hashlib
import html
import io
import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from hnx_disclosure_feed_parser import parse_disclosure_detail


CONTRACT_VERSION = "hnx_multi_attachment_binding_and_citable_extraction/v1"
_ATTACHMENT_BLOCK = re.compile(r'<div class="divLstFileAttach">(.*?)</div>\s*</div>', re.I | re.S)
_ANCHOR = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_METRICS = (
    "revenue", "parent_net_income", "total_assets", "total_liabilities", "parent_equity",
    "cash_and_equivalents", "operating_cash_flow", "capital_expenditure",
    "interest_bearing_debt", "interest_expense", "weighted_average_basic_shares",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(value: Mapping[str, Any]) -> str:
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def _attachment_type(title: str, filename: str) -> tuple[str, str]:
    value = (title + " " + filename).lower()
    if any(term in value for term in ("giaitrinh", "giatrinh", "giai trinh", "explanationsrelating", "explanations")):
        return "EXPLANATORY_LETTER", "UNKNOWN"
    if "congvan" in value or "cong van" in value:
        return "OTHER", "UNKNOWN"
    if any(term in value for term in ("financialstatements", "financialstatement", "financial statements", "bao cao tai chinh", "baocaotaichinh", "interimfinancial")):
        if any(term in value for term in ("consolidated", "hopnhat", "hop nhat")):
            return "CONSOLIDATED_FINANCIAL_STATEMENTS", "consolidated"
        if any(term in value for term in ("separate", "rieng")):
            return "SEPARATE_FINANCIAL_STATEMENTS", "separate"
        return "UNKNOWN", "UNKNOWN"
    if any(term in value for term in ("auditreport", "audit report", "reviewreport", "review report")):
        return "AUDITOR_REVIEW_REPORT", "UNKNOWN"
    return "UNKNOWN", "UNKNOWN"


def _is_statement_candidate(child: Mapping[str, Any]) -> bool:
    if child["attachment_type"] in {"CONSOLIDATED_FINANCIAL_STATEMENTS", "SEPARATE_FINANCIAL_STATEMENTS"}:
        return True
    value = (child["attachment_title"] + " " + child["attachment_filename"]).lower()
    return child["attachment_type"] == "UNKNOWN" and any(
        term in value for term in ("financialstatements", "financialstatement", "financial statements", "interimfinancial", "baocaotaichinh", "bao cao tai chinh")
    )


def parse_parent_attachments(*, parent: Mapping[str, Any], detail_bytes: bytes, retained_sha_by_url: Mapping[str, str]) -> dict[str, Any]:
    if _sha(detail_bytes) != parent["detail_sha256"]:
        raise ValueError("PARENT_DETAIL_SHA256_MISMATCH")
    parsed = parse_disclosure_detail(detail_bytes, url=str(parent["detail_url"]))
    source = detail_bytes.decode("utf-8", errors="replace")
    block = _ATTACHMENT_BLOCK.search(source)
    if block is None:
        raise ValueError("PARENT_ATTACHMENT_BLOCK_MISSING")
    anchors = _ANCHOR.findall(block.group(1))
    if not anchors:
        raise ValueError("PARENT_ATTACHMENT_LIST_EMPTY")
    ticker = parsed.get("ticker")
    ticker_explicit = isinstance(ticker, str) and bool(ticker.strip())
    attachments = []
    for index, (url, raw_title) in enumerate(anchors, 1):
        title = html.unescape(_TAG.sub(" ", raw_title)).strip()
        filename = Path(urlparse(url).path).name
        classification, scope = _attachment_type(title, filename)
        sha = retained_sha_by_url.get(url)
        attachments.append({
            "attachment_index": index,
            "attachment_title": title,
            "attachment_filename": filename,
            "attachment_url": url,
            "attachment_sha256": sha,
            "bytes_retained": sha is not None,
            "attachment_type": classification,
            "attachment_scope": scope,
            "identity_source": "OFFICIAL_PARENT_DISCLOSURE" if ticker_explicit else None,
            "ticker": ticker if ticker_explicit else None,
            "identity_state": "QUALIFIED_OFFICIAL_PARENT_ATTACHMENT" if ticker_explicit else "MULTI_ATTACHMENT_BINDING_UNPROVEN",
            "unit_scale_state": "NOT_EVALUATED_NOT_RETAINED" if sha is None else "PENDING_TEXT_SCAN",
            "canonical_facts": [],
        })
    return {
        "parent_filing_id": parent["detail_sha256"],
        "parent_detail_url": parent["detail_url"],
        "parent_detail_sha256": parent["detail_sha256"],
        "parent_issuer_name": None,
        "parent_ticker": ticker if ticker_explicit else None,
        "parent_ticker_citation": parsed["citations"].get("ticker"),
        "published_at": parent["published_at"],
        "attachments": attachments,
    }


def _text_state(path: Path, expected_sha: str) -> str:
    if _sha(path.read_bytes()) != expected_sha:
        raise ValueError("ATTACHMENT_SHA256_MISMATCH")
    try:
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(path.read_bytes())).pages
        text = [page.extract_text() or "" for page in pages]
    except Exception:
        return "UNKNOWN"
    if not any(value.strip() for value in text):
        return "IMAGE_ONLY_OR_SCANNED"
    if all(value.strip() for value in text):
        return "TEXT_NATIVE"
    return "MIXED"


def build(*, retained_artifact: Mapping[str, Any], raw_root: Path, baseline: Mapping[str, Any]) -> dict[str, Any]:
    retained_sha_by_url = {row["filing_url"]: row["document_sha256"] for row in retained_artifact["documents"]}
    parents = []
    for parent in sorted(retained_artifact["documents"], key=lambda row: row["detail_sha256"]):
        detail_path = raw_root / "raw" / "details" / (parent["detail_sha256"] + ".html")
        parents.append(parse_parent_attachments(parent=parent, detail_bytes=detail_path.read_bytes(), retained_sha_by_url=retained_sha_by_url))
    attachments = [child for parent in parents for child in parent["attachments"]]
    for child in attachments:
        if child["attachment_sha256"] is None:
            continue
        path = raw_root / "raw" / "filings" / (child["attachment_sha256"] + ".pdf")
        child["text_state"] = _text_state(path, child["attachment_sha256"])
        child["unit_scale_state"] = "UNIT_SCALE_UNRESOLVED"
        child["ocr_state"] = "NO_OPERATIONAL_GOVERNED_OCR_EXECUTOR"
    for child in attachments:
        if child["attachment_sha256"] is None:
            child["text_state"] = "UNKNOWN_NOT_RETAINED"
            child["ocr_state"] = "NOT_ELIGIBLE_BYTES_NOT_RETAINED"
    before_after = baseline["before_after_comparison"]
    count = lambda predicate: sum(1 for child in attachments if predicate(child))
    coverage = {
        "parent_disclosures": len(parents),
        "total_attachments": len(attachments),
        "attachments_per_parent": {parent["parent_filing_id"]: len(parent["attachments"]) for parent in parents},
        "official_parent_ticker_bindings": count(lambda child: child["ticker"] is not None),
        "financial_statement_attachments": count(_is_statement_candidate),
        "consolidated_attachments": count(lambda child: child["attachment_type"] == "CONSOLIDATED_FINANCIAL_STATEMENTS"),
        "separate_attachments": count(lambda child: child["attachment_type"] == "SEPARATE_FINANCIAL_STATEMENTS"),
        "auditor_report_attachments": count(lambda child: child["attachment_type"] == "AUDITOR_REVIEW_REPORT"),
        "explanatory_letter_attachments": count(lambda child: child["attachment_type"] == "EXPLANATORY_LETTER"),
        "other_attachments": count(lambda child: child["attachment_type"] == "OTHER"),
        "ambiguous_attachments": count(lambda child: child["attachment_type"] == "UNKNOWN" and not _is_statement_candidate(child)),
        "ticker_resolved_attachments": count(lambda child: child["ticker"] is not None),
        "ticker_unresolved_attachments": count(lambda child: child["ticker"] is None),
        "text_native_attachments": count(lambda child: child["text_state"] == "TEXT_NATIVE"),
        "scanned_attachments": count(lambda child: child["text_state"] == "IMAGE_ONLY_OR_SCANNED"),
        "mixed_attachments": count(lambda child: child["text_state"] == "MIXED"),
        "unit_scale_qualified": 0,
        "unit_scale_unresolved": count(lambda child: child["unit_scale_state"] == "UNIT_SCALE_UNRESOLVED"),
        "ocr_citable_attachments": 0,
        "content_blocked_attachments": count(lambda child: child["attachment_sha256"] is not None),
        "canonical_observations_before": before_after["canonical_exact_qualified_facts"]["after"],
        "canonical_observations_after": before_after["canonical_exact_qualified_facts"]["after"],
        "canonical_tickers_before": before_after["metadata_qualified_issuers"]["after"],
        "canonical_tickers_after": before_after["metadata_qualified_issuers"]["after"],
    }
    artifact = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION,
        "source_artifacts": {"retained_hnx_scaleout": retained_artifact["artifact_identity"], "canonical_baseline": baseline["artifact_identity"]},
        "parents": parents, "coverage": coverage,
        "canonical_fact_readiness": {metric: {"new_ready": 0, "reason": "MULTI_ATTACHMENT_BINDING_UNPROVEN"} for metric in _METRICS},
        "provider_reconciliation": {"exact_matches": 0, "scale_normalized_matches": 0, "possible_scale_matches": 0, "conflicts": 0, "not_comparable": 0, "state": "NOT_ATTEMPTED_NO_OFFICIAL_IDENTITY_OR_UNIT"},
        "identity_contract_result": "MULTI_ATTACHMENT_BINDING_UNPROVEN",
        "unit_scale_contract_result": "UNIT_SCALE_UNRESOLVED_FOR_8_RETAINED_SCANNED_PDFS",
        "extraction_result": "CONTENT_BLOCKED_SCANNED_NO_OPERATIONAL_GOVERNED_OCR",
        "authority_result": "UNCHANGED_NO_CANONICAL_OBSERVATIONS",
        "lane_terminal_status": "MULTI_ATTACHMENT_BINDING_UNPROVEN",
        "next_real_data_opportunity": "Retained or newly authorized HNX parent metadata explicitly identifying the issuer ticker for each parent disclosure",
        "network_used": False, "canonical_store_mutated": False, "missing_is_zero": False,
    }
    digest = _identity(artifact)
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = "hnx_multi_attachment_binding:" + digest
    return artifact


def replay(*, retained_artifact: Mapping[str, Any], raw_root: Path, baseline: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
    if dict(artifact) != build(retained_artifact=retained_artifact, raw_root=raw_root, baseline=baseline):
        raise ValueError("DETERMINISTIC_REPLAY_MISMATCH")
