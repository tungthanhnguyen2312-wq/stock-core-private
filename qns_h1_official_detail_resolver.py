"""QNS-only detail-page resolver for the retained 2026 semi-annual statement.

The official financial index is not refreshed. The detail page is discovery
evidence: it may name one first-party PDF and it never supplies a fact.
A retained PDF whose URL and SHA256 already match is not downloaded again.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

MILESTONE_ID = "QNS_2026_H1_OFFICIAL_DETAIL_RESOLVER_AND_FINANCIAL_EVIDENCE_V1"
DETAIL_URL = "https://www.qns.com.vn/qns-cong-bo-bao-cao-tai-chinh-ban-nien-nam-2026"
CONSOLIDATED_TITLE = "Báo cáo tài chính hợp nhất bán niên năm 2026"
ADMITTED_HOSTS = frozenset({"qns.com.vn", "www.qns.com.vn"})
RETAINED_PDF_URL = "https://www.qns.com.vn/upload/product/2026q2-bctc-hop-nhat-sau-kt-1786788334.pdf"
RETAINED_PDF_SHA256 = "5a06a40f34a6d9b30233926f9c9d909d684744de2bf2ad0956edd367d5f7b068"
PARENT_INDEX = {
    "url": "https://www.qns.com.vn/bao-cao-tai-chinh",
    "sha256": "8921d8e7148425222e8b953941f51783fe8595731e537556dbb49c84fa067d0a",
    "literal_href": "/qns-cong-bo-bao-cao-tai-chinh-ban-nien-nam-2026",
    "literal_title": "QNS công bố báo cáo tài chính bán niên năm 2026",
    "refreshed_by_this_milestone": False,
}
PRIORITY_METRICS = (
    "revenue", "net_income", "attributable_net_income", "cash_and_equivalents",
    "total_assets", "shareholders_equity", "operating_cash_flow",
    "short_term_borrowings", "long_term_borrowings_or_finance_leases",
    "total_interest_bearing_debt",
)
STORAGE_CEILING_BYTES = 50 * 1024 * 1024


def declared_budget() -> dict[str, Any]:
    """The budget is fixed before any HTTP call."""
    return {
        "issuer": "QNS",
        "detail_page_requests_max": 1,
        "pdf_requests_max": 1,
        "total_requests_including_redirects_retries_max": 5,
        "concurrency": 1,
        "retained_storage_ceiling_bytes": STORAGE_CEILING_BYTES,
        "pagination": False,
        "generic_search": False,
        "index_refresh": False,
        "further_discovery_layers": False,
    }


def _collapse(value: str) -> str:
    return " ".join(value.split())


class _PdfAnchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, _collapse(" ".join(self._parts))))
            self._href, self._parts = None, []


def pdf_anchors(page_url: str, html: bytes) -> list[dict[str, str]]:
    parser = _PdfAnchors()
    parser.feed(html.decode("utf-8", errors="replace"))
    found: list[dict[str, str]] = []
    for href, label in parser.links:
        target = urljoin(page_url, href)
        if urlsplit(target).path.casefold().endswith(".pdf"):
            found.append({"url": target, "literal_anchor_text": label})
    return found


def select_statement(page_url: str, html: bytes) -> dict[str, Any]:
    """Choose the one literal consolidated semi-annual anchor, or stop."""
    anchors = pdf_anchors(page_url, html)
    matches = [item for item in anchors if item["literal_anchor_text"] == CONSOLIDATED_TITLE]
    if len(matches) != 1:
        return {
            "state": "DETAIL_PAGE_HAS_NO_OFFICIAL_PDF",
            "pdf_anchors": anchors,
            "selected_locator": None,
            "html_is_financial_evidence": False,
        }
    selected = matches[0]["url"]
    host = (urlsplit(selected).hostname or "").casefold()
    if host not in ADMITTED_HOSTS:
        return {
            "state": "OWNER_ROUTE_DECISION_REQUIRED",
            "pdf_anchors": anchors,
            "selected_locator": selected,
            "host": host,
            "html_is_financial_evidence": False,
        }
    return {
        "state": "PDF_LOCATOR_ON_ADMITTED_QNS_HOST",
        "pdf_anchors": anchors,
        "selected_locator": selected,
        "host": host,
        "html_is_financial_evidence": False,
    }


def classify_representation(materialization: Mapping[str, Any]) -> str:
    pages = list(materialization.get("pages") or [])
    if any(page.get("route") == "NATIVE_TEXT_AVAILABLE_USE_NATIVE_PATH" for page in pages):
        return "NATIVE_TEXT_USABLE"
    ocr_pages = [page for page in pages if page.get("ocr_derived_text_evidence")]
    native_failures = [page.get("native_failure_evidence") or {} for page in ocr_pages]
    if ocr_pages and native_failures and all(item.get("candidate_count") == 0 for item in native_failures):
        return "OCR_REQUIRED"
    if not ocr_pages:
        return "SOURCE_DAMAGED"
    return "SOURCE_DAMAGED"


def attempt_priority_facts(materialization: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse the canonical qualifier. This does not repair tokens or headers."""
    from official_financial_ocr_table_evidence import (
        qualify_table_facts, resolve_scoped_statement_scope_evidence, resolve_scoped_unit_evidence,
    )
    qualified = qualify_table_facts(
        materialization, ticker="QNS", reporting_period="2026-H1", include_earnings_quality_components=True,
        scoped_unit_evidence=resolve_scoped_unit_evidence(materialization),
        scoped_statement_scope_evidence=resolve_scoped_statement_scope_evidence(materialization),
    )
    by_metric = {fact["canonical_metric"]: fact for fact in qualified["qualified_facts"]}
    blocked = {item["canonical_metric"]: item["reason"] for item in qualified["blocked_candidates"]}
    rows = []
    for metric in PRIORITY_METRICS:
        if metric in by_metric:
            fact = by_metric[metric]
            rows.append({
                "canonical_metric": metric, "state": "QUALIFIED", "value": fact["value"],
                "currency": fact["currency"], "unit_scale": fact["unit_scale"],
                "source_page": fact["source_lineage"]["source_page"],
                "line_code": fact["source_lineage"]["row_object"]["line_code"],
            })
        else:
            rows.append({"canonical_metric": metric, "state": "BLOCKED", "reason": blocked.get(metric, "NOT_ATTEMPTED")})
    components = [fact["canonical_metric"] for fact in qualified["qualified_facts"]
                  if fact["canonical_metric"] in {"provision_charge_or_reversal_adjustment", "investment_property_disposal_result"}]
    return {"facts": rows, "earnings_components": components, "normalization": "SOURCE_FAITHFUL_NORMALIZATION_NOT_YET_PROVABLE"}


def terminal_disposition(selection_state: str, qualified_metrics: list[str]) -> str:
    if selection_state == "DETAIL_PAGE_HAS_NO_OFFICIAL_PDF":
        return "QNS_2026_H1_DETAIL_HAS_NO_PDF"
    if selection_state == "OWNER_ROUTE_DECISION_REQUIRED":
        return "QNS_2026_H1_ROUTE_BLOCKED"
    if qualified_metrics:
        return "QNS_2026_H1_CURRENT_OFFICIAL_EVIDENCE_READY"
    return "QNS_2026_H1_DOCUMENT_RETAINED_FACTS_BLOCKED"


def bind_retained_pdf(selected_url: str, pdf_path: Path) -> dict[str, Any]:
    if selected_url != RETAINED_PDF_URL or not pdf_path.is_file():
        return {"state": "PDF_NOT_THE_RETAINED_STATEMENT", "sha256": None, "request_required": True}
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if digest != RETAINED_PDF_SHA256:
        return {"state": "RETAINED_BYTES_HASH_MISMATCH", "sha256": digest, "request_required": True}
    return {"state": "CACHED_VALID_NO_PDF_REQUEST", "sha256": digest, "request_required": False,
            "bytes": pdf_path.stat().st_size}


def build_report(*, detail: Mapping[str, Any], selection: Mapping[str, Any], pdf_binding: Mapping[str, Any],
                 representation: str, attempt: Mapping[str, Any], requests_used: int) -> dict[str, Any]:
    qualified = [row["canonical_metric"] for row in attempt["facts"] if row["state"] == "QUALIFIED"]
    return {
        "milestone_id": MILESTONE_ID,
        "budget": declared_budget(),
        "budget_declared_before_http": True,
        "detail_page": {
            "classification": "DETAIL_PAGE_RESOLVER",
            "authority_effect": "DISCOVERY_ONLY_NOT_FINANCIAL_EVIDENCE",
            "original_url": DETAIL_URL,
            "final_url": detail.get("final_url"),
            "retrieved_at": detail.get("retrieved_at"),
            "sha256": detail.get("sha256"),
            "content_type": detail.get("content_type"),
            "parent_index": PARENT_INDEX,
        },
        "selection": {key: selection[key] for key in ("state", "selected_locator", "pdf_anchors") if key in selection},
        "pdf_binding": dict(pdf_binding),
        "representation": representation,
        "ocr_rerun": False,
        "normalization": attempt["normalization"],
        "facts": attempt["facts"],
        "earnings_components": attempt["earnings_components"],
        "requests_used": requests_used,
        "terminal_disposition": terminal_disposition(str(selection["state"]), qualified),
    }
