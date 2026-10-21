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


def prepare_financial_intake_candidate(candidate: Mapping[str, Any], *, document: Mapping[str, Any],
        retained_bytes: bytes, value_parser: Callable[[Any], int],
        period_resolver: Callable[..., Mapping[str, Any]],
        route_admission: Mapping[str, Any] | None = None, cutoff: str | None = None) -> dict[str, Any]:
    """Pure intake over previously reviewed rows, not official source activation.

    Existing value and period owners are injected explicitly to preserve dependency
    direction. The cohort gate is evaluated unchanged. A semantic candidate never
    claims official fact admission or makes an overlay/ratio available by itself.
    """
    from stocklookup_core.evidence.financial_row_identity import resolve_reported_row_identity
    row, doc = dict(candidate), dict(document)
    # A caller cannot write the qualification output. The guard below owns it.
    row.pop("native_numeric_literal_proven", None)
    schema, semantic, citation, knowledge = [], [], [], []
    digest = sha256(retained_bytes).hexdigest()
    if digest != doc.get("sha256") or digest != row.get("document_sha256"):
        citation.append("ORIGINAL_DOCUMENT_HASH_MISMATCH")
    if not doc.get("ticker") or row.get("ticker") != doc.get("ticker"):
        schema.append("DOCUMENT_ISSUER_MISMATCH")
    identity = resolve_reported_row_identity(str(row.get("statement_family") or ""),
        str(row.get("line_code") or ""), str(row.get("raw_row_label") or ""))
    label_only_candidate = str(row.get("line_code") or "") == "" and identity["accounting_identity"] != "UNKNOWN" and not identity["blockers"]
    required_fields = ["statement_family", "raw_row_label", "native_period_label", "statement_scope", "unit_scale"]
    if row.get("statement_family") != "eps_note" and not label_only_candidate:
        required_fields += ["line_code", "currency"]
    elif identity["accounting_identity"] not in {"SHARE_COUNT_NOTE", "EPS_DENOMINATOR_SHARES", "EPS_OPENING_SHARES", "EPS_RESTATED_DIVIDEND_IMPACT"} and row.get("statement_family") != "eps_note":
        required_fields += ["currency"]
    for key in required_fields:
        if row.get(key) in (None, ""):
            schema.append(key.upper() + "_MISSING")
    page = row.get("source_page")
    page_count = doc.get("page_count")
    def valid_page(value):
        return type(value) is int and type(page_count) is int and 1 <= value <= page_count
    if type(page_count) is not int or page_count < 1:
        citation.append("SOURCE_DOCUMENT_PAGE_COUNT_REQUIRED")
    if not valid_page(page):
        citation.append("SOURCE_PAGE_OUT_OF_RANGE_OR_MISSING")
    original_span = row.get("source_span")
    span = original_span if isinstance(original_span, Mapping) else {}
    if (not isinstance(span, Mapping) or span.get("document_sha256") != digest
            or not span.get("citation_id") or not span.get("text")):
        citation.append("EXACT_CITATION_NOT_DOCUMENT_BOUND")
    if not valid_page(span.get("source_page")) or span.get("source_page") != page:
        citation.append("REVIEW_SPAN_PAGE_NOT_BOUND")
    if str(row.get("raw_row_label") or "") not in str(span.get("text") or ""):
        citation.append("ROW_LABEL_NOT_IN_REVIEW_SPAN")
    semantic.extend(identity["blockers"])
    if row.get("canonical_metric") is not None and row["canonical_metric"] != identity["canonical_metric"]:
        semantic.append("CANONICAL_METRIC_IDENTITY_CONFLICT")
    scope = row.get("statement_scope")
    if scope not in {"consolidated", "standalone"} or scope != doc.get("statement_scope"):
        semantic.append("STATEMENT_SCOPE_NOT_BOUND")
    scale = row.get("unit_scale")
    if type(scale) is not int or scale <= 0:
        semantic.append("UNIT_SCALE_NOT_EXPLICIT")
    quantity = identity["accounting_identity"] in {"EPS_DENOMINATOR_SHARES", "EPS_OPENING_SHARES", "EPS_RESTATED_DIVIDEND_IMPACT", "SHARE_COUNT_NOTE"}
    per_share = identity["accounting_identity"] == "REPORTED_BASIC_EPS"
    unsupported_special_scale = (quantity or per_share) and (scale != 1 or doc.get("unit_scale") != 1)
    if unsupported_special_scale:
        # A statement's monetary scale cannot establish shares or VND/share.
        # Mixed-unit documents require an independently qualified row-unit adapter.
        semantic.append("EPS_OR_SHARE_MIXED_UNIT_SCALE_NOT_SUPPORTED")
    if quantity and (row.get("unit") != "shares" or row.get("currency") is not None):
        semantic.append("EPS_SHARE_QUANTITY_UNIT_NOT_PROVEN")
    if (not quantity and row.get("currency") != doc.get("currency")) or scale != doc.get("unit_scale"):
        semantic.append("DOCUMENT_CURRENCY_SCALE_MISMATCH")
    raw = row.get("raw_value_text")
    value = row.get("reviewed_integer_value")
    try:
        if raw is not None:
            parsed = value_parser(raw)
            if value is not None and parsed != value:
                raise ValueError("TRANSCRIPTION_VALUE_MISMATCH")
            if str(raw) not in str(span.get("text")):
                citation.append("NUMERIC_LITERAL_NOT_IN_REVIEW_SPAN")
            value = parsed
        if type(value) is not int:
            raise ValueError("EXACT_INTEGER_REQUIRED")
        normalized = value * scale if type(scale) is int and scale > 0 and not unsupported_special_scale else None
    except (ValueError, TypeError):
        normalized = None
        semantic.append("ACCOUNTING_INTEGER_INVALID_OR_CONFLICTING")
    period = dict(period_resolver(str(row.get("native_period_label") or ""),
        statement_family=str(row.get("statement_family") or ""),
        explicit_start=row.get("period_start"), explicit_end=row.get("period_end")))
    semantic.extend(period["blockers"])
    if row.get("reporting_period") is not None and row["reporting_period"] != period.get("reporting_period"):
        semantic.append("REPORTED_PERIOD_IDENTITY_CONFLICT")
    if (row.get("period_start") or row.get("period_end")) and not row.get("period_bounds_evidence"):
        semantic.append("COVERED_DATE_ENDPOINT_PROOF_MISSING")
    bounds_proof = row.get("period_bounds_evidence")
    if bounds_proof and (not isinstance(bounds_proof, Mapping) or bounds_proof.get("document_sha256") != digest
                         or not valid_page(bounds_proof.get("source_page")) or not bounds_proof.get("text")):
        semantic.append("COVERED_DATE_ENDPOINT_PROOF_UNBOUND")
    elif isinstance(bounds_proof, Mapping):
        def endpoint_in_text(endpoint):
            try:
                parsed_date = datetime.fromisoformat(endpoint).date()
            except (TypeError, ValueError):
                return False
            text = " ".join(str(bounds_proof.get("text") or "").casefold().split())
            months = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
            day, month, year = parsed_date.day, parsed_date.month, parsed_date.year
            month_name = months[month - 1]
            patterns = (re.escape(endpoint), rf"0?{day}\s+{month_name}\s+{year}",
                        rf"{month_name}\s+0?{day},?\s+{year}",
                        rf"0?{day}[/.-]0?{month}[/.-]{year}",
                        rf"ng[àa]y\s+0?{day}\s+th[áa]ng\s+0?{month}\s+n[ăa]m\s+{year}")
            return any(re.search(r"(?<!\d)(?:" + pattern + r")(?!\d)", text) for pattern in patterns)
        if any(not endpoint_in_text(row[key]) for key in ("period_start", "period_end") if row.get(key)):
            semantic.append("COVERED_DATE_ENDPOINT_NOT_IN_PROOF_TEXT")
    if row.get("reported_column_kind") and row["reported_column_kind"] != period.get("period_semantic_state"):
        semantic.append("QUARTER_CUMULATIVE_OR_INSTANT_MISMATCH")
    assurance = doc.get("audit_or_review_status", "unknown")
    doc_class = doc.get("document_class")
    if doc_class not in {"quarterly_financial_statements", "reviewed_interim_financial_statements", "audited_annual_financial_statements", "unreviewed_financial_statements"}:
        semantic.append("FINANCIAL_DOCUMENT_CLASS_NOT_SUPPORTED")
    expected_assurance = {"reviewed_interim_financial_statements": "reviewed", "audited_annual_financial_statements": "audited"}.get(doc_class)
    if expected_assurance and assurance != expected_assurance:
        semantic.append("DECLARED_DOCUMENT_CLASS_ASSURANCE_CONFLICT")
    if assurance not in {"audited", "reviewed", "unreviewed", "unknown"}:
        semantic.append("ASSURANCE_IDENTITY_UNKNOWN")
    if row.get("audit_or_review_status") not in (None, assurance):
        semantic.append("ASSURANCE_IDENTITY_CONFLICT")
    def instant(raw_time):
        try:
            result = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            return result if result.utcoffset() is not None else None
        except (TypeError, ValueError):
            return None
    observed, known, published, limit = (instant(doc.get("observed_at")), instant(row.get("knowledge_available_at")),
                                       instant(doc.get("published_at")), instant(cutoff))
    if observed is None or known is None:
        knowledge.append("EXACT_OBSERVATION_KNOWLEDGE_TIMESTAMP_UNKNOWN")
    elif known < observed:
        knowledge.append("KNOWLEDGE_PRECEDES_OBSERVATION")
    if cutoff is not None and limit is None:
        knowledge.append("CUTOFF_TIMESTAMP_INVALID")
    if limit and known and known > limit:
        knowledge.append("AFTER_KNOWLEDGE_CUTOFF")
    if published and known and published > known:
        knowledge.append("PUBLICATION_AFTER_KNOWLEDGE")
    acquisition_claimed_as_publication = doc.get("publication_time_basis") == "acquisition"
    if acquisition_claimed_as_publication:
        published = None
    publication_blockers = [] if published else ["SOURCE_PUBLICATION_TIMESTAMP_UNKNOWN_NO_HISTORICAL_PIT"]
    if acquisition_claimed_as_publication:
        publication_blockers.append("ACQUISITION_TIME_IS_NOT_PUBLICATION")
    layer = row.get("numeric_evidence_layer")
    binding = row.get("literal_byte_binding") if isinstance(row.get("literal_byte_binding"), Mapping) else {}
    token_in_source = isinstance(raw, str) and raw.encode("utf-8") in retained_bytes
    def native_bytes_bound() -> bool:
        start, end = binding.get("byte_start"), binding.get("byte_end")
        return (isinstance(raw, str) and binding.get("document_sha256") == digest and binding.get("source_page") == page
                and type(start) is int and type(end) is int and 0 <= start < end <= len(retained_bytes)
                and retained_bytes[start:end] == raw.encode("utf-8"))
    if layer in {"ocr_text", "reviewed_visual_integer", "unknown"}:
        # Parser success and a copied raw token never promote OCR or a visual read.
        judged_layer, native_literal_proven = layer, False
    elif layer == "native_text":
        if native_bytes_bound() and normalized is not None and not citation:
            judged_layer, native_literal_proven = "native_text", True
        else:
            judged_layer, native_literal_proven = "unknown", False
            citation.append("NATIVE_LITERAL_NOT_BOUND_TO_SOURCE_BYTES")
    elif layer not in (None, ""):
        judged_layer, native_literal_proven = "unknown", False
        semantic.append("NUMERIC_EVIDENCE_LAYER_UNKNOWN")
    elif raw is None and type(value) is int:
        judged_layer, native_literal_proven = "reviewed_visual_integer", False
    elif raw is not None and token_in_source and normalized is not None and not citation:
        # Old native literals remain native when the original bytes still contain the token.
        judged_layer, native_literal_proven = "native_text", True
    else:
        judged_layer, native_literal_proven = "unknown", False
    canonical = {**row, "canonical_metric": identity["canonical_metric"], "accounting_identity": identity["accounting_identity"],
                 "reporting_period": period.get("reporting_period"), "period_semantic_state": period["period_semantic_state"],
                 "value": normalized, "normalized_value": normalized, "source_unit_scale": scale, "unit_scale": 1,
                 "already_normalized": normalized is not None, "audit_or_review_status": assurance,
                 "qualification_state": "CANDIDATE_ONLY",
                 "publication_date": None if acquisition_claimed_as_publication else doc.get("published_at"),
                 "numeric_evidence_layer": judged_layer}
    canonical["value_unit"] = "shares" if quantity else (str(row.get("currency")) + "/share" if identity["accounting_identity"] == "REPORTED_BASIC_EPS" else row.get("currency"))
    # This preserves the existing gate, including TICKER_NOT_IN_APPROVED_COHORT.
    legacy = validate_fact({**row, "canonical_metric": identity["canonical_metric"],
        "issuer_identity": doc.get("issuer_identity"), "reporting_period": period.get("reporting_period"),
        "periodicity": row.get("periodicity"), "audit_or_review_status": assurance,
        "citation": {"page": page, "text": span.get("text") if isinstance(span, Mapping) else None}})
    route = dict(route_admission or {})
    route_bound = all(route.get(key) == doc.get(field) for key, field in
        (("source_id", "source_id"), ("url", "source_url"), ("document_type", "document_class")))
    source_blockers = list(legacy.get("blockers") or [])
    from stocklookup_core.evidence.financial_metadata_envelope import qualify_document_metadata, METADATA_QUALIFIED
    metadata_input = doc.get("metadata_candidate")
    metadata = qualify_document_metadata(metadata_input) if isinstance(metadata_input, Mapping) else None
    if metadata is None or metadata.get("qualification_status") != METADATA_QUALIFIED:
        source_blockers.append("EXPLICIT_DOCUMENT_METADATA_NOT_QUALIFIED")
    elif metadata["document"]["document_sha256"] != digest:
        source_blockers.append("DOCUMENT_METADATA_HASH_MISMATCH")
    else:
        claims = metadata.get("metadata_claims") or {}
        expected = {"reporting_period": period.get("reporting_period"), "statement_scope": scope,
                    "currency": row.get("currency"), "unit_scale": scale, "periodicity": row.get("periodicity")}
        if metadata.get("issuer_identity") != str(row.get("ticker") or "").upper():
            source_blockers.append("DOCUMENT_METADATA_ISSUER_MISMATCH")
        if any((claims.get(key) or {}).get("value") != value for key, value in expected.items()):
            source_blockers.append("DOCUMENT_METADATA_DIMENSION_MISMATCH")
    if route.get("decision") != "admitted" or not route_bound:
        source_blockers.append("REGISTRY_SOURCE_ROUTE_NOT_ADMITTED")
    valuation_blocks = ["OFFICIAL_FACT_ADMISSION_NOT_ESTABLISHED", "NO_ANNUALIZATION_OR_TTM", "CURRENT_SHARES_NOT_ESTABLISHED"]
    if identity["accounting_identity"] == "TOTAL_EQUITY_INCLUDING_NCI":
        valuation_blocks.append("TOTAL_EQUITY_IS_NOT_PARENT_BOOK_EQUITY")
    if identity["accounting_identity"] == "PARENT_PROFIT_AFTER_TAX":
        valuation_blocks.append("PARENT_PROFIT_IS_NOT_TOTAL_NET_INCOME")
    if "LOANS_AND_FINANCE_LEASES" in identity["accounting_identity"]:
        valuation_blocks.append("LEASE_INCLUSIVE_LOANS_ARE_NOT_PURE_BORROWINGS")
    if "LEASE_CONTENT_UNKNOWN" in identity["accounting_identity"]:
        valuation_blocks.append("LOAN_LEASE_CONTENT_UNKNOWN_NO_DEBT_TOTAL")
    if quantity:
        valuation_blocks.append("EPS_SHARE_BASIS_IS_NOT_CURRENT_OUTSTANDING_SHARES")
    if identity["accounting_identity"] == "EPS_ORDINARY_SHAREHOLDER_PROFIT":
        valuation_blocks.append("EPS_NUMERATOR_IS_NOT_PARENT_OR_TOTAL_PROFIT")
    if identity["accounting_identity"] == "SHARE_COUNT_NOTE":
        valuation_blocks.append("SHARE_NOTE_IS_NOT_OUTSTANDING_SHARE_AUTHORITY")
    if identity["accounting_identity"] == "CHARTER_CAPITAL_AMOUNT":
        valuation_blocks.append("CHARTER_CAPITAL_IS_NOT_A_SHARE_COUNT")
    if str(row.get("ticker") or "").upper() in BANKS:
        valuation_blocks.append("BANK_OUTSIDE_INDUSTRIAL_EV_EBITDA")
    result = dict(contract_version="official_financial_intake_candidate/v1", candidate=canonical,
        schema_valid=not schema, semantic_valid=not (schema + semantic + citation),
        native_numeric_literal_proven=bool(native_literal_proven) and normalized is not None and not citation,
        numeric_evidence_layer=judged_layer,
        schema_blockers=sorted(set(schema)), semantic_blockers=sorted(set(semantic)),
        citation_blockers=sorted(set(citation)), source_admission_blockers=sorted(set(source_blockers)),
        knowledge_blockers=sorted(set(knowledge)), publication_blockers=publication_blockers,
        source_admission_eligible=not (schema + semantic + citation + source_blockers),
        knowledge_cutoff_eligible=not knowledge and limit is not None,
        existing_consumer_usable=False, official_fact_admitted=False, strict_valuation_eligible=False,
        valuation_blockers=valuation_blocks, period_identity=period,
        assurance_scope=doc.get("assurance_scope", "UNKNOWN"),
        document_metadata=metadata,
        cutoff=cutoff, source_document={key: doc.get(key) for key in ("ticker", "source_id", "source_url", "document_class", "observed_at", "published_at", "audit_or_review_status")},
        original_document_sha256=digest, authority_effect="NONE", is_actionable=False)
    result["candidate_identity"] = sha256(canonical_json(result).encode()).hexdigest()
    return result


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
