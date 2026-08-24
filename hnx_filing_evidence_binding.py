"""Offline, fail-closed binding of retained HNX filing PDFs to their parent disclosure."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hnx_disclosure_feed_parser import parse_disclosure_detail


CONTRACT_VERSION = "hnx_official_filing_evidence_binding_and_extraction/v1"
SOURCE_ID = "hnx"
METRICS = (
    "revenue", "parent_net_income", "total_assets", "total_liabilities",
    "parent_equity", "cash_and_equivalents", "operating_cash_flow",
    "capital_expenditure", "interest_bearing_debt", "interest_expense",
    "weighted_average_basic_shares",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(value: Mapping[str, Any]) -> str:
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def parent_binding(document: Mapping[str, Any], detail_bytes: bytes) -> dict[str, Any]:
    """Bind only an exact parent attachment and a parent-supplied ticker field.

    The disclosure parser intentionally reads the ``Box-Noidung`` disclosure content only.
    Tickers in HNX page chrome, search widgets, filenames, or provider data are not issuer
    evidence for the attached filing.
    """
    detail_sha = _sha(detail_bytes)
    if detail_sha != document.get("detail_sha256"):
        raise ValueError("DETAIL_SHA256_MISMATCH")
    parsed = parse_disclosure_detail(detail_bytes, url=str(document["detail_url"]))
    attachment_count = sum(url == document.get("filing_url") for url in parsed["attachment_urls"])
    ticker = parsed.get("ticker")
    one_to_one = attachment_count == 1
    ticker_explicit = isinstance(ticker, str) and bool(ticker.strip())
    qualified = one_to_one and ticker_explicit
    return {
        "document_id": document["document_id"],
        "document_sha256": document["document_sha256"],
        "parent_detail_url": document["detail_url"],
        "parent_detail_sha256": detail_sha,
        "parent_content_block_found": parsed["content_block_found"],
        "parent_attachment_url": document["filing_url"],
        "parent_attachment_exact_url_count": attachment_count,
        "attachment_one_to_one": one_to_one,
        "parent_ticker": ticker if ticker_explicit else None,
        "parent_ticker_citation": parsed["citations"].get("ticker"),
        "document_subject_identity_source": "OFFICIAL_PARENT_DISCLOSURE" if qualified else None,
        "binding_state": "QUALIFIED_OFFICIAL_PARENT_BINDING" if qualified else "OFFICIAL_PARENT_BINDING_UNPROVEN",
        "binding_reason": "EXACT_ATTACHMENT_AND_EXPLICIT_PARENT_TICKER" if qualified else (
            "PARENT_TICKER_MISSING" if one_to_one else "ATTACHMENT_RELATION_NOT_ONE_TO_ONE"),
        "reporting_period": document["reporting_period"],
        "reporting_period_source": "OFFICIAL_PARENT_DISCLOSURE_TITLE",
        "statement_scope": document["title_scope"],
        "statement_scope_source": "OFFICIAL_PARENT_DISCLOSURE_TITLE" if document["title_scope"] != "UNKNOWN" else "UNKNOWN",
        # Filenames are retained provenance but do not qualify a statement status by themselves.
        "audit_review_status": "UNKNOWN",
        "audit_review_status_source": "NO_EXACT_PARENT_OR_CITABLE_STATEMENT_EVIDENCE",
        "published_at": document["published_at"],
        "text_extraction_state": "NOT_ATTEMPTED_IDENTITY_BLOCKED" if not qualified else "PENDING_CITABLE_TEXT_REVIEW",
        "ocr_state": "NOT_QUEUED_IDENTITY_BLOCKED" if not qualified else "PENDING_EXISTING_GOVERNED_HANDOFF",
        "canonical_facts": [],
    }


def build(*, retained_artifact: Mapping[str, Any], raw_root: Path, baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Replay retained parent/PDF provenance without network, OCR, or store mutation."""
    bindings: list[dict[str, Any]] = []
    for document in sorted(retained_artifact.get("documents") or [], key=lambda row: row["document_sha256"]):
        filing = raw_root / "raw" / "filings" / (str(document["document_sha256"]) + ".pdf")
        if not filing.is_file() or _sha(filing.read_bytes()) != document["document_sha256"]:
            raise ValueError("FILING_SHA256_MISMATCH")
        detail = raw_root / "raw" / "details" / (str(document["detail_sha256"]) + ".html")
        bindings.append(parent_binding(document, detail.read_bytes()))

    before_after = baseline["before_after_comparison"]
    bindings = sorted(bindings, key=lambda row: row["document_sha256"])
    qualified = [row for row in bindings if row["binding_state"] == "QUALIFIED_OFFICIAL_PARENT_BINDING"]
    period_qualified = [row for row in bindings if row["reporting_period"]]
    scope_qualified = [row for row in bindings if row["statement_scope"] in {"separate", "consolidated"}]
    coverage = {
        "retained_hnx_filings": len(bindings),
        "official_parent_bindings": len(qualified),
        "ticker_resolved_filings": len(qualified),
        "ticker_unresolved_filings": len(bindings) - len(qualified),
        "period_qualified": len(period_qualified),
        "scope_qualified": len(scope_qualified),
        "audit_review_status_qualified": 0,
        "text_native_filings": 0,
        "ocr_citable_filings": 0,
        "content_blocked_filings": len(bindings) - len(qualified),
        "canonical_observations_before": before_after["canonical_exact_qualified_facts"]["after"],
        "canonical_observations_after": before_after["canonical_exact_qualified_facts"]["after"],
        "canonical_tickers_before": before_after["metadata_qualified_issuers"]["after"],
        "canonical_tickers_after": before_after["metadata_qualified_issuers"]["after"],
    }
    outcome = "HNX_FILING_CANONICAL_DATA_UNLOCKED" if qualified else "OFFICIAL_PARENT_BINDING_UNPROVEN"
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "source_artifacts": {
            "retained_hnx_scaleout": retained_artifact["artifact_identity"],
            "retained_hnx_scaleout_sha256": retained_artifact["artifact_sha256"],
            "canonical_baseline": baseline["artifact_identity"],
        },
        "bindings": bindings,
        "coverage": coverage,
        "canonical_fact_readiness": {metric: {"new_ready": 0, "reason": "OFFICIAL_PARENT_BINDING_UNPROVEN"} for metric in METRICS},
        "provider_reconciliation": {"exact_matches": 0, "conflicts": 0, "state": "NOT_ATTEMPTED_NO_QUALIFIED_OFFICIAL_FACT"},
        "identity_contract_result": outcome,
        "extraction_result": "NOT_STARTED_IDENTITY_BLOCKED" if not qualified else "PENDING_CITATION_QUALIFICATION",
        "authority_result": "UNCHANGED_NO_CANONICAL_OBSERVATIONS",
        "lane_terminal_status": "OFFICIAL_PARENT_BINDING_UNPROVEN",
        "next_real_data_opportunity": "HNX parent disclosure metadata that explicitly binds the retained attachment to its issuer ticker",
        "missing_is_zero": False,
        "canonical_store_mutated": False,
        "network_used": False,
    }
    digest = _identity(artifact)
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = "hnx_official_filing_evidence_binding:" + digest
    return artifact


def replay(*, retained_artifact: Mapping[str, Any], raw_root: Path, baseline: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
    expected = build(retained_artifact=retained_artifact, raw_root=raw_root, baseline=baseline)
    if dict(artifact) != expected:
        raise ValueError("DETERMINISTIC_REPLAY_MISMATCH")
