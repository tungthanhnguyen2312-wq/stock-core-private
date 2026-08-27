"""Native-text, page/table-bound evidence for retained official financial PDFs.

This is an extraction boundary, not a document acquirer or a fact store.  It uses
the existing generic statement-template recognizer and refuses OCR/provider fallback.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from annual_financial_ocr_materialization import parse_accounting_integer
from financial_statement_template_recognizer import extract_generic_financial_statement_facts
import official_financial_structural_table


VERSION = "official_financial_pdf_page_evidence/v2"
EXTRACTION_METHOD = "pypdf_native_text"
POSITIONED_TEXT_METHOD = "pypdf_visitor_text_origin_v1"
CORPORATE_METRICS = ("total_assets", "shareholders_equity", "cash_and_equivalents", "total_interest_bearing_debt", "revenue", "net_income", "operating_cash_flow")


def _hash(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _positioned_page_tokens(page: Any) -> tuple[str, list[dict[str, Any]]]:
    """Return native visitor-text chunks with their deterministic PDF text origins.

    pypdf exposes the text matrix origin for every emitted text chunk.  Its public
    callback does not expose glyph outlines, so ``x1`` is deliberately a bounded,
    conservative width estimate; geometry consumers use x0/top for alignment and
    retain the estimate's provenance instead of pretending it is a glyph box.
    """
    chunks: list[dict[str, Any]] = []

    def visitor(text: str, _cm: Any, tm: Any, _font: Any, font_size: Any) -> None:
        value = str(text).strip()
        x0, top = float(tm[4]), float(tm[5])
        if not value or (x0 == 0.0 and top == 0.0):
            return
        size = max(1.0, float(font_size or 1.0))
        chunks.append({
            "text": value, "x0": round(x0, 4),
            "x1": round(x0 + max(1, len(value)) * size * 0.55, 4),
            "top": round(top, 4), "bottom": round(top + size, 4),
            "font_size": round(size, 4), "raw_token_order": len(chunks),
            "bbox_method": "pypdf_text_origin_conservative_width",
        })

    text = page.extract_text(visitor_text=visitor) or ""
    return text, chunks


def _load_pages(path: Path, expected_sha256: str) -> tuple[str, list[tuple[str, list[dict[str, Any]]]], str]:
    raw = path.read_bytes(); actual = _hash(raw)
    if actual != expected_sha256:
        raise ValueError("DOCUMENT_HASH_MISMATCH")
    try:
        import pypdf
    except ImportError as exc:  # pragma: no cover
        raise ValueError("PDF_TEXT_EXTRACTOR_UNAVAILABLE") from exc
    reader = pypdf.PdfReader(path)
    return actual, [_positioned_page_tokens(page) for page in reader.pages], f"pypdf {pypdf.__version__}"


def page_evidence(*, document: Mapping[str, Any], path: Path) -> list[dict[str, Any]]:
    digest, pages, engine = _load_pages(path, str(document["sha256"]))
    rows = []
    for number, (text, positioned_tokens) in enumerate(pages, 1):
        text_hash = _hash(text)
        identity = _hash(_json({"contract": VERSION, "document_sha256": digest, "page": number, "text_sha256": text_hash, "method": EXTRACTION_METHOD}))
        rows.append({"page_evidence_id": identity, "document_identity": document["document_id"], "document_sha256": digest,
                     "ticker": str(document["ticker"]).upper(), "official_url": document["official_url"], "page_number": number,
                     "page_label": None, "page_text_hash": text_hash, "page_text": text, "extraction_method": EXTRACTION_METHOD,
                     "parser_identity": engine, "positioned_text_method": POSITIONED_TEXT_METHOD,
                     "positioned_tokens": positioned_tokens,
                     "status": "TEXT_AVAILABLE" if text.strip() else "TEXT_EMPTY"})
    return rows


def _claim(value: Any, page: int | None, text: str | None, status: str = "EXPLICIT") -> dict[str, Any]:
    return {"value": value, "source_page": page, "source_text": text, "qualification_status": status}


def document_metadata(pages: list[Mapping[str, Any]], ticker: str) -> dict[str, Any]:
    """Extract only literal document claims; unknown is retained rather than repaired."""
    text_by_page = {int(row["page_number"]): str(row["page_text"]) for row in pages}
    def first(needle: str) -> tuple[int | None, str | None]:
        for page, text in text_by_page.items():
            pos = text.casefold().find(needle.casefold())
            if pos >= 0: return page, text[pos:pos + max(180, len(needle))]
        return None, None
    def match(pattern: str, *, minimum_page: int = 1) -> tuple[str | None, int | None, str | None]:
        for page, text in text_by_page.items():
            if page < minimum_page: continue
            found = re.search(pattern, text, flags=re.IGNORECASE)
            if found: return found.group(1).strip(), page, found.group(0)
        return None, None, None
    issuer_candidates = []
    for page, text in text_by_page.items():
        for found in re.finditer(r"(Công ty Cổ phần.*?)(?=\s+BÁO CÁO|\s*\n|\s*\(|$)", text, flags=re.IGNORECASE):
            score = int(f"mã chứng khoán là {ticker}".casefold() in text.casefold()) * 2 + int("báo cáo tài chính" in text.casefold())
            issuer_candidates.append((-score, page, found.group(1).strip(), found.group(0)))
    issuer = issuer_page = issuer_text = None
    if issuer_candidates:
        _, issuer_page, issuer, issuer_text = sorted(issuer_candidates)[0]
        words = issuer.split()
        if len(words) % 2 == 0 and words[:len(words)//2] == words[len(words)//2:]:
            issuer = " ".join(words[:len(words)//2])
    stated_ticker, ticker_page, ticker_text = match(r"mã chứng khoán là\s+([A-Z]{3,5})", minimum_page=int(issuer_page or 1))
    period, period_page, period_text = match(r"năm tài chính kết thúc ngày 31 tháng 12 năm\s+(20\d{2})", minimum_page=int(issuer_page or 1))
    scope_page, scope_text = first("báo cáo tài chính hợp nhất")
    audit_page, audit_text = first("báo cáo kiểm toán độc lập")
    currency_page, currency_text = first("Đơn vị tính: VND")
    # Front-matter tables of contents are not the accounting statement.  Prefer the
    # document body at/after the issuer-identifying statement page whenever available.
    def first_after(needle: str, current: tuple[int | None, str | None]) -> tuple[int | None, str | None]:
        for page, text in text_by_page.items():
            if issuer_page and page < issuer_page: continue
            pos = text.casefold().find(needle.casefold())
            if pos >= 0: return page, text[pos:pos + max(180, len(needle))]
        return current
    scope_page, scope_text = first_after("báo cáo tài chính hợp nhất", (scope_page, scope_text))
    audit_page, audit_text = first_after("báo cáo kiểm toán độc lập", (audit_page, audit_text))
    currency_page, currency_text = first_after("Đơn vị tính: VND", (currency_page, currency_text))
    # These labels are generic; the ticker lookup above is merely an optional corroborating
    # document field and never controls table extraction or canonical mapping.
    claims = {
        "issuer_identity": _claim(issuer, issuer_page, issuer_text) if issuer_page else _claim(None, None, None, "UNKNOWN"),
        "ticker": _claim(stated_ticker, ticker_page, ticker_text) if ticker_page else _claim(None, None, None, "UNKNOWN"),
        "reporting_period": _claim(period, period_page, period_text) if period_page else _claim(None, None, None, "UNKNOWN"),
        "periodicity": _claim("annual", period_page, period_text) if period_page else _claim(None, None, None, "UNKNOWN"),
        "statement_scope": _claim("consolidated", scope_page, scope_text) if scope_page else _claim(None, None, None, "UNKNOWN"),
        "audit_or_review_status": _claim("audited", audit_page, audit_text) if audit_page else _claim(None, None, None, "UNKNOWN"),
        "currency": _claim("VND", currency_page, currency_text) if currency_page else _claim(None, None, None, "UNKNOWN"),
        "unit_scale": _claim(1, currency_page, currency_text) if currency_page else _claim(None, None, None, "UNKNOWN"),
    }
    # Do not accept a caller-supplied ticker as proof: a retained PDF must state it itself.
    claims["issuer_ticker_match"] = _claim(str(ticker).upper(), ticker_page, ticker_text) if stated_ticker == str(ticker).upper() else _claim(None, ticker_page, ticker_text, "CONFLICT_OR_UNKNOWN")
    return {"contract": VERSION, "metadata_claims": claims, "qualification_status": "DOCUMENT_METADATA_QUALIFIED" if all(c["value"] is not None for k, c in claims.items() if k != "issuer_ticker_match") else "DOCUMENT_METADATA_BLOCKED"}


def _fragment(page: Mapping[str, Any], kind: str) -> dict[str, Any] | None:
    text = str(page["page_text"]); upper = text.upper(); number = int(page["page_number"])
    code = {"balance_sheet": "B01-DN/HN", "income_statement": "B02-DN/HN", "cash_flow": "B03-DN/HN"}[kind]
    if code not in upper: return None
    units = [i for i in range(len(text)) if text.startswith("Đơn vị tính:", i)]
    if kind == "balance_sheet":
        start = units[-1] if units else 0; body = f"{code}\nBẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT\n" + text[start:]
    elif len(units) >= 2:
        if kind == "income_statement": start, end = units[0], units[1]; heading = "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT"
        else: start, end = units[1], len(text); heading = "BÁO CÁO LƯU CHUYỂN TIỀN TỆ HỢP NHẤT"
        body = f"{code}\n{heading}\n" + text[start:end]
    else:
        body = text
    start = text.find(body.split("\n")[-1]) if body else 0
    return {"table_id": _hash(_json({"document": page["document_sha256"], "page": number, "type": kind, "text": body})), "table_type": kind, "page_number": number, "detected_heading": code, "column_labels": ["current", "comparative"], "unit_context": "explicit_on_table_or_statement_page" if "Đơn vị tính:" in body else "not_on_fragment", "source_span": {"start": max(0, start), "end": len(text)}, "text": body}


def discover_tables(pages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    tables = [table for page in pages for kind in ("balance_sheet", "income_statement", "cash_flow") if (table := _fragment(page, kind))]
    return sorted(tables, key=lambda row: (row["page_number"], row["table_type"]))


def _sidecar(document: Mapping[str, Any], tables: list[Mapping[str, Any]], table_type: str) -> dict[str, Any]:
    selected = [t for t in tables if t["table_type"] == table_type]
    return {"document_id": document["document_id"], "document_sha256": document["sha256"], "pages": [
        {"page": t["page_number"], "text": t["text"], "status": "text_available", "text_sha256": _hash(t["text"]),
         "citation_id": _hash(_json({"document": document["sha256"], "page": t["page_number"], "table": t["table_id"]})),
         "materialization_id": t["table_id"], "extraction_engine": EXTRACTION_METHOD} for t in selected]}


def _row_source_span(page_text: str, raw_value: str, extracted_label: str) -> dict[str, Any]:
    """Return native-PDF coordinates when a literal row value survives extraction.

    A derived row (for example, short plus long debt) has no single literal
    value on the page.  Such a row keeps its extracted label but deliberately
    records null coordinates instead of inventing an offset.
    """
    position = page_text.find(raw_value)
    if position < 0:
        return {"start": None, "end": None, "text": extracted_label,
                "coordinate_status": "UNAVAILABLE_FOR_DERIVED_OR_WRAPPED_ROW"}
    start = page_text.rfind("\n", 0, position) + 1
    end = page_text.find("\n", position)
    if end < 0:
        end = len(page_text)
    return {"start": start, "end": end, "text": page_text[start:end],
            "coordinate_status": "NATIVE_TEXT_LINE"}


def extract_candidates(*, document: Mapping[str, Any], pages: list[Mapping[str, Any]], metadata: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tables = discover_tables(pages); rejected: list[dict[str, Any]] = []
    if str(document.get("entity_type", "corporate")) != "corporate":
        return [], [{"state": "NOT_APPLICABLE", "reason": "ENTITY_LAYOUT_NOT_SUPPORTED_BY_CORPORATE_TEMPLATE",
                     "entity_type": document.get("entity_type")}]
    if not tables:
        # The exact-form Circular-200 table fragmenter found nothing on this corporate
        # document (no literal B01/B02/B03-DN/HN code on any page).  Dispatch to the
        # structural fallback recognizer instead of blocking on REPORTING_PERIOD_UNPROVEN
        # below -- that check is specific to document_metadata()'s Vietnamese-only claims
        # and is never reached here.  AAA and every other exact-form-eligible document
        # always has tables != [] at this point, so this branch never fires for them.
        return official_financial_structural_table.build_structural_candidates(document=document, pages=pages)
    claims = metadata["metadata_claims"]
    reporting_period = str(claims["reporting_period"]["value"] or "")
    if not re.fullmatch(r"20\d{2}", reporting_period):
        return [], [{"state": "OFFICIAL_FACT_CANDIDATE_BLOCKED", "reason": "REPORTING_PERIOD_UNPROVEN"}]
    family_metrics = {"balance_sheet": ("total_assets", "shareholders_equity", "cash_and_equivalents", "total_interest_bearing_debt"), "income_statement": ("revenue", "net_income"), "cash_flow": ("operating_cash_flow",)}
    extracted = []
    for family, metrics in family_metrics.items():
        try:
            extracted.extend(extract_generic_financial_statement_facts(sidecar=_sidecar(document, tables, family), reporting_period=reporting_period, required_metrics=metrics))
        except ValueError as exc:
            rejected.append({"table_type": family, "state": "CANONICAL_IDENTITY_AMBIGUOUS", "reason": str(exc)})
    candidates = []
    table_by_page_type = {(t["page_number"], t["table_type"]): t for t in tables}
    for fact in extracted:
        table = table_by_page_type[(fact.page, fact.statement_type)]
        raw = fact.raw_value
        value, _ = parse_accounting_integer(raw)
        normalized = value * fact.unit_scale
        source_page = next(p for p in pages if p["page_number"] == fact.page)
        candidates.append({"ticker": document["ticker"], "canonical_metric": fact.canonical_metric, "canonical_mapping_state": "CANONICAL_IDENTITY_EXACT", "raw_row_label": fact.ocr_matched_label, "raw_numeric_text": raw, "parsed_numeric_value": value, "normalized_value": normalized, "currency": fact.currency, "unit_scale": fact.unit_scale, "fiscal_period": reporting_period, "statement_scope": claims["statement_scope"]["value"], "audit_or_review_status": claims["audit_or_review_status"]["value"], "document_sha256": document["sha256"], "official_url": document["official_url"], "page_number": fact.page, "statement_family": fact.statement_type, "table_id": table["table_id"], "table_heading": table["detected_heading"], "period_column_label": fact.period_column_evidence["current_period_label"], "source_span": _row_source_span(str(source_page["page_text"]), raw, fact.ocr_matched_label), "extraction_method": EXTRACTION_METHOD, "qualification_status": "OFFICIAL_FACT_QUALIFIED" if metadata["qualification_status"] == "DOCUMENT_METADATA_QUALIFIED" else "OFFICIAL_FACT_CANDIDATE_BLOCKED"})
    return candidates, rejected


def build_artifact(*, document: Mapping[str, Any], path: Path) -> dict[str, Any]:
    pages = page_evidence(document=document, path=path); metadata = document_metadata(pages, str(document["ticker"])); tables = discover_tables(pages)
    candidates, rejected = extract_candidates(document=document, pages=pages, metadata=metadata)
    panel_facts = []
    for candidate in candidates:
        if candidate["qualification_status"] != "OFFICIAL_FACT_QUALIFIED": continue
        period = candidate["fiscal_period"]
        instant = candidate["canonical_metric"] in {"total_assets", "shareholders_equity", "cash_and_equivalents", "total_interest_bearing_debt"}
        knowledge_available_at = document["retrieved_at"]
        panel_facts.append({"issuer_identity": candidate["ticker"], "entity_type": "corporate", "applicability_state": "APPLICABLE", "authority_tier": "promoted_corporate_evidence", "canonical_metric": candidate["canonical_metric"], "value": candidate["normalized_value"], "currency": candidate["currency"], "unit_scale": candidate["unit_scale"], "reporting_period": period, "period_type": "annual", "period_start": f"{period}-01-01", "period_end": f"{period}-12-31", "statement_scope": candidate["statement_scope"], "statement_family": candidate["statement_family"], "temporal_nature": "instant" if instant else "duration", "qualification_state": "QUALIFIED", "is_positive_authority": True, "knowledge_available_at": knowledge_available_at, "observed_at": knowledge_available_at, "reason_codes": ["OFFICIAL_DOCUMENT_PAGE_TABLE_CITED"], "reconciliation_status": "NOT_COMPARED_TO_PROVIDER", "temporal_envelope": {"as_of": period, "domain": "financial_statement", "field_id": f"pdf-page:{candidate['document_sha256']}:{candidate['canonical_metric']}:{period}", "field_name": candidate["canonical_metric"], "freshness_status": "historical", "knowledge_available_at": knowledge_available_at, "observed_at": knowledge_available_at, "pit_eligible": True, "pit_status": "QUALIFIED", "quality_status": "qualified", "value": candidate["normalized_value"]}, "source_lineage": {"provider": "official_issuer_ir", "authority_tier": "promoted_corporate_evidence", "document_sha256": candidate["document_sha256"], "citation_id": candidate["table_id"], "evidence_id": candidate["table_id"], "source_page": candidate["page_number"], "source_span": candidate["source_span"], "table_heading": candidate["table_heading"], "period_column_label": candidate["period_column_label"], "extraction_method": candidate["extraction_method"], "reconciliation_status": "NOT_COMPARED_TO_PROVIDER"}})
    output = {"schema_version": VERSION, "document": {k: document[k] for k in ("document_id", "ticker", "sha256", "official_url", "retrieved_at")}, "page_count": len(pages), "text_layer_status": "USABLE_NATIVE_TEXT" if any(p["status"] == "TEXT_AVAILABLE" for p in pages) else "IMAGE_ONLY_OR_SCANNED", "page_evidence": pages, "document_metadata": metadata, "tables": tables, "fact_candidates": candidates, "p3f13_panel_facts": panel_facts, "blocked_candidates": rejected, "authority": {"network_used": False, "provider_used": False, "production_db_mutated": False, "value_or_recommendation_activated": False}}
    if not tables and str(document.get("entity_type", "corporate")) == "corporate":
        # Additive only: the exact-form document_metadata claims above stay exactly what
        # the Vietnamese-only function found (usually DOCUMENT_METADATA_BLOCKED for this
        # branch) -- this key never redefines that meaning, it just makes the separate
        # structural-fallback evidence that actually gated `candidates` visible too.
        output["structural_document_metadata"] = {
            "recognizer_identity": official_financial_structural_table.VERSION,
            "layout_family": official_financial_structural_table.recognize_layout_family(pages),
            "identity_claims": official_financial_structural_table.structural_document_identity_claims(pages, str(document["ticker"])),
        }
    output["artifact_sha256"] = _hash(_json(output)); output["artifact_identity"] = f"official_financial_pdf_page_evidence:{output['artifact_sha256']}"
    return output
