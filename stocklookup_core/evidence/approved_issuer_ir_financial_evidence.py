"""Bounded official-financial-document acquisition for the approved issuer-IR cohort.

The module deliberately treats an issuer IR page as a *finite index*, not an archive
to crawl.  A document can become a panel fact only when the document itself supplies
every accounting dimension and a page/table citation.  It never reads provider data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urljoin, urlsplit

import requests


VERSION = "approved_issuer_ir_official_financial_evidence_cohort/v1"
APPROVED_ROUTES = {
    "ABS": "https://bitagco.com/", "ABW": "https://abs.vn/", "ACB": "https://www.acb.com.vn/",
    "MBB": "https://www.mbbank.com.vn/", "MWG": "https://mwg.vn/", "TCB": "https://techcombank.com/",
    "AAA": "https://anphatbioplastics.com/", "AAT": "https://tiensonaus.com/", "BID": "https://bidv.com.vn/vn/quan-he-nha-dau-tu",
}
BANKS = frozenset({"ACB", "MBB", "TCB", "BID"})
MAX_DOCUMENTS_PER_ISSUER = 2
MAX_NEW_DOCUMENTS = 18
FINANCIAL_TERMS = ("báo cáo tài chính", "bao cao tai chinh", "financial statement", "bctc", "annual report", "báo cáo thường niên")
REQUIRED_METADATA = ("issuer_identity", "reporting_period", "periodicity", "statement_scope", "currency", "unit_scale", "audit_or_review_status", "statement_family")
CORPORATE_METRICS = frozenset({"revenue", "net_income", "shareholders_equity", "total_assets", "cash_and_equivalents", "short_term_borrowings", "long_term_borrowings", "total_interest_bearing_debt", "operating_cash_flow"})
BANK_METRICS = frozenset({"net_profit_parent", "total_equity", "total_assets", "customer_loans_net", "customer_deposits", "provision_for_credit_losses"})


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.href = None; self.parts: list[str] = []; self.links: list[tuple[str, str]] = []
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a": self.href, self.parts = dict(attrs).get("href"), []
    def handle_data(self, data: str) -> None:
        if self.href is not None: self.parts.append(data)
    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.href:
            self.links.append((self.href, " ".join(" ".join(self.parts).split())))
            self.href, self.parts = None, []


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def same_approved_host(index_url: str, target_url: str) -> bool:
    source, target = urlsplit(index_url).hostname, urlsplit(target_url).hostname
    return bool(source and target and source.lower().removeprefix("www.") == target.lower().removeprefix("www."))


def document_links(index_url: str, raw: bytes) -> list[str]:
    parser = _Links(); parser.feed(raw.decode("utf-8", errors="replace"))
    links: list[str] = []
    for href, label in parser.links:
        target = urljoin(index_url, href)
        haystack = f"{label} {target}".casefold()
        if same_approved_host(index_url, target) and (target.casefold().split("?")[0].endswith(".pdf") or any(t in haystack for t in FINANCIAL_TERMS)):
            if target not in links: links.append(target)
    return links[:MAX_DOCUMENTS_PER_ISSUER]


def fetch(url: str) -> tuple[int, Mapping[str, str], bytes, str]:
    response = requests.get(url, timeout=(5, 15), headers={"User-Agent": "StockLookupOfficialEvidence/1.1"}, allow_redirects=True)
    return response.status_code, dict(response.headers), response.content, response.url


def _route_failure(status: int, payload: bytes) -> str:
    if status == 404: return "OFFICIAL_ROUTE_404"
    if status in {401, 403}: return "ACCESS_BLOCKED"
    if not payload or status == 0 or status >= 500: return "OFFICIAL_ROUTE_UNAVAILABLE"
    return "OTHER_PRECISE_REASON"


def is_financial_document(url: str, headers: Mapping[str, str], payload: bytes) -> bool:
    """A category/detail HTML page is a resolver, never silently a filing document."""
    content_type = str(headers.get("Content-Type") or "").casefold()
    return urlsplit(url).path.casefold().endswith(".pdf") and "pdf" in content_type and payload.startswith(b"%PDF")


def validate_fact(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one already-extracted exact line; extraction is intentionally separate."""
    row, blockers = dict(candidate), []
    ticker = str(row.get("ticker") or "").upper()
    if ticker not in APPROVED_ROUTES: blockers.append("TICKER_NOT_IN_APPROVED_COHORT")
    metric = str(row.get("canonical_metric") or "")
    allowed = BANK_METRICS if ticker in BANKS else CORPORATE_METRICS
    if metric not in allowed: blockers.append("BANK_TAXONOMY_VIOLATION" if ticker in BANKS else "CANONICAL_METRIC_NOT_ALLOWED")
    for key in REQUIRED_METADATA:
        if row.get(key) in (None, ""): blockers.append(f"{key.upper()}_MISSING")
    if not isinstance(row.get("unit_scale"), int) or int(row.get("unit_scale", 0)) <= 0: blockers.append("UNIT_SCALE_NOT_EXPLICIT")
    if not re.fullmatch(r"\(?[0-9]{1,3}(?:[,.][0-9]{3})*\)?|[0-9]+", str(row.get("raw_value_text") or "")): blockers.append("NUMERIC_TEXT_AMBIGUOUS")
    if not isinstance(row.get("citation"), Mapping) or not row["citation"].get("page") or not row["citation"].get("text"): blockers.append("CITATION_REQUIRED")
    if len(str(row.get("document_sha256") or "")) != 64: blockers.append("DOCUMENT_HASH_REQUIRED")
    if blockers: return {"qualification_status": "REJECTED", "blockers": sorted(set(blockers)), "candidate": row}
    raw = str(row["raw_value_text"]).strip(); negative = raw.startswith("(")
    value = int(raw.strip("()").replace(",", "").replace(".", "")) * (-1 if negative else 1)
    normalized = value * int(row["unit_scale"])
    return {"qualification_status": "QUALIFIED", "fact": {**row, "ticker": ticker, "value": normalized, "normalized_vnd_value": normalized if row["currency"] == "VND" else None, "provider": "official_issuer_ir"}}


def classify_conflict(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> str:
    """Keep competing source identities; this never selects or overwrites a winner."""
    if existing.get("ticker") != incoming.get("ticker") or existing.get("canonical_metric") != incoming.get("canonical_metric"):
        return "NOT_COMPARABLE"
    if existing.get("reporting_period") != incoming.get("reporting_period"): return "PERIOD_DIFFERENCE"
    if existing.get("statement_scope") != incoming.get("statement_scope"): return "SCOPE_DIFFERENCE"
    if (existing.get("currency"), existing.get("unit_scale")) != (incoming.get("currency"), incoming.get("unit_scale")): return "UNIT_SCALE_DIFFERENCE"
    if existing.get("value") == incoming.get("value"): return "EXACT_MATCH"
    return "TRUE_CONFLICT"


def acquire(*, output_root: Path, fetcher: Callable[[str], tuple[int, Mapping[str, str], bytes, str]] = fetch,
            now: Callable[[], str] | None = None) -> dict[str, Any]:
    """Run exactly one foreground index pass and at most two direct documents per issuer."""
    now = now or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    output_root.mkdir(parents=True, exist_ok=True); evidence = output_root / "evidence"; evidence.mkdir(exist_ok=True)
    documents: list[dict[str, Any]] = []; resolution_pages: list[dict[str, Any]] = []; dispositions: list[dict[str, Any]] = []; request_log: list[dict[str, Any]] = []; newly_retained_documents = 0
    for ticker, index_url in APPROVED_ROUTES.items():
        try: status, headers, raw, final = fetcher(index_url)
        except (requests.RequestException, OSError): status, headers, raw, final = 0, {}, b"", index_url
        request_log.append({"ticker": ticker, "kind": "index", "url": index_url, "status": status, "final_url": final})
        if not (200 <= status < 300 and raw and same_approved_host(index_url, final)):
            dispositions.append({"ticker": ticker, "disposition": _route_failure(status, raw), "documents": 0}); continue
        targets = document_links(final, raw)
        if not targets:
            dispositions.append({"ticker": ticker, "disposition": "PERIOD_NOT_FOUND", "documents": 0}); continue
        retained = 0
        for target in targets:
            if newly_retained_documents >= MAX_NEW_DOCUMENTS: raise RuntimeError("DOCUMENT_BUDGET_EXCEEDED")
            try: dstatus, dheaders, body, dfinal = fetcher(target)
            except (requests.RequestException, OSError): dstatus, dheaders, body, dfinal = 0, {}, b"", target
            request_log.append({"ticker": ticker, "kind": "document", "url": target, "status": dstatus, "final_url": dfinal})
            if not (200 <= dstatus < 300 and body and same_approved_host(index_url, dfinal)):
                continue
            digest = sha256(body).hexdigest(); path = evidence / f"{ticker}_{digest}.bin"
            previously_retained = path.exists()
            if not previously_retained: path.write_bytes(body)
            record = {"ticker": ticker, "document_id": f"issuer-ir:{ticker}:{digest}", "official_url": dfinal, "retrieved_at": now(), "content_type": dheaders.get("Content-Type", "unknown"), "sha256": digest, "relative_path": str(path.relative_to(output_root)).replace("\\", "/"), "bytes": len(body), "retention_status": "DUPLICATE_DOCUMENT_NO_OP" if previously_retained else "NEWLY_RETAINED"}
            if is_financial_document(dfinal, dheaders, body):
                documents.append({**record, "metadata_status": "DOCUMENT_METADATA_BLOCKED", "metadata_blockers": ["DOCUMENT_TEXT_EXTRACTION_AND_EXPLICIT_SEMANTICS_REQUIRED"]}); retained += 1; newly_retained_documents += int(not previously_retained)
            else:
                resolution_pages.append({**record, "classification": "INDEX_OR_NON_FINANCIAL_DOCUMENT"})
        dispositions.append({"ticker": ticker, "disposition": "OFFICIAL_DOCUMENT_FOUND" if retained else "DOCUMENT_NOT_FINANCIAL_STATEMENT", "documents": retained})
    artifact = {"schema_version": VERSION, "approved_tickers": list(APPROVED_ROUTES), "excluded_tickers": ["ABT"], "document_budget": {"per_issuer": MAX_DOCUMENTS_PER_ISSUER, "ceiling": MAX_NEW_DOCUMENTS, "actual": newly_retained_documents}, "request_log": request_log, "documents": documents, "resolution_pages": resolution_pages, "route_dispositions": dispositions, "qualified_facts": [], "rejected_facts": [], "authority": {"provider_used": False, "canonical_store_mutated": False, "runtime_database_mutated": False, "value_strategy_activated": False, "recommendation_or_ranking_produced": False}}
    artifact["artifact_sha256"] = sha256(canonical_json(artifact).encode()).hexdigest(); artifact["artifact_identity"] = f"approved_issuer_ir_official_financial_evidence:{artifact['artifact_sha256']}"
    (output_root / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


def reclassify_retained_artifact(path: Path) -> dict[str, Any]:
    """Recover an older run that retained index HTML as if it were a filing, without network I/O."""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    documents, resolvers = [], list(artifact.get("resolution_pages") or [])
    for record in artifact.get("documents") or []:
        raw_path = path.parent / str(record["relative_path"])
        raw = raw_path.read_bytes()
        headers = {"Content-Type": str(record.get("content_type") or "")}
        if is_financial_document(str(record["official_url"]), headers, raw): documents.append(record)
        else: resolvers.append({k: v for k, v in record.items() if k not in {"metadata_status", "metadata_blockers"}} | {"classification": "INDEX_OR_NON_FINANCIAL_DOCUMENT"})
    artifact["documents"], artifact["resolution_pages"] = documents, resolvers
    artifact["document_budget"]["actual"] = len(documents)
    for row in artifact["route_dispositions"]:
        count = sum(1 for document in documents if document["ticker"] == row["ticker"])
        if row["disposition"] in {"OFFICIAL_DOCUMENT_FOUND", "DOCUMENT_NOT_FINANCIAL_STATEMENT"}:
            row["documents"], row["disposition"] = count, "OFFICIAL_DOCUMENT_FOUND" if count else "DOCUMENT_NOT_FINANCIAL_STATEMENT"
    artifact.pop("artifact_sha256", None); artifact.pop("artifact_identity", None)
    artifact["artifact_sha256"] = sha256(canonical_json(artifact).encode()).hexdigest(); artifact["artifact_identity"] = f"approved_issuer_ir_official_financial_evidence:{artifact['artifact_sha256']}"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


def summarize_existing_artifact(path: Path, coverage_report: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Produce the nine-issuer inventory from retained acquisition results only."""
    artifact = json.loads(path.read_text(encoding="utf-8")); docs = artifact.get("documents") or []
    resolvers = artifact.get("resolution_pages") or []; disposition = {r["ticker"]: r for r in artifact["route_dispositions"]}
    inventory = []
    for ticker, route in APPROVED_ROUTES.items():
        entity_type = "bank" if ticker in BANKS else "securities" if ticker == "ABW" else "corporate"
        required = sorted(BANK_METRICS if ticker in BANKS else CORPORATE_METRICS)
        ticker_docs = [d for d in docs if d["ticker"] == ticker]
        inventory.append({"ticker": ticker, "official_issuer_route": route, "entity_type": entity_type, "retained_financial_documents": ticker_docs, "retained_resolution_pages": len([p for p in resolvers if p["ticker"] == ticker]), "existing_qualified_canonical_facts": [], "current_valuation_relevant_facts": [], "missing_required_facts": required, "route_disposition": disposition[ticker]["disposition"]})
    report = {"schema_version": VERSION, "artifact_identity": artifact["artifact_identity"], "inventory": inventory, "qualified_documents": [d for d in docs if d.get("metadata_status") == "DOCUMENT_METADATA_QUALIFIED"], "new_qualified_facts_by_ticker": {}, "rejected_facts": artifact["rejected_facts"], "conflict_dispositions": [], "official_panel_consumption": {"qualified_fact_count": 0, "status": "NO_OP_NO_DOCUMENT_QUALIFIED_FACTS"}, "aaa_effect": "REMAINS_FINANCIAL_FACT_MISSING_PROVIDER_DESCRIPTIVE_NO_PAGE_BOUND_FACT", "bank_validation": {"bank_tickers": sorted(BANKS), "industrial_ev_metrics_forced": False, "bank_specific_facts_qualified": 0}, "authority": artifact["authority"]}
    if coverage_report:
        report["financial_inventory"] = coverage_report.get("identity_inventory_summary")
        report["valuation"] = {"research_usable": coverage_report.get("valuation_metric_research_usable_counts"), "ready": coverage_report.get("valuation_metric_ready_counts"), "value": coverage_report.get("value_strategy_readiness")}
    output = path.parent / "cohort_report.json"; output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
