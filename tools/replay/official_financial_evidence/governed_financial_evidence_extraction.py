"""Phase 2 / P2-D: Governed Financial Evidence Extraction & Citation Binding.

Extracts verified financial statement line items from persisted OCR sidecars
using generic financial statement template recognition (financial_statement_template_recognizer.py),
binding each observation to its immutable document SHA-256 and verified citation lineage.
No authoritative financial values or ticker-specific extraction recipes are hardcoded in source code;
statement structure, unit/scale, period column semantics, and line items are recognized generically.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import unicodedata

from annual_financial_ocr_materialization import (
    parse_accounting_integer,
    verified_debt_extraction,
    verified_extraction,
)
from financial_statement_template_recognizer import (
    CANONICAL_NET_INCOME_SEMANTIC,
    CONTRACT_VERSION as TEMPLATE_CONTRACT_VERSION,
    ExtractedStatementFact,
    extract_generic_financial_statement_facts,
)

SCHEMA_VERSION = "1.1.0"
CONTRACT_VERSION = "governed_financial_evidence_extraction/v2"


def _normalize_text(s: str) -> str:
    """Normalize unicode and strip combining marks for tolerant anchor lookup."""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def compute_citation_id(
    *,
    ticker: str,
    metric: str,
    reporting_period: str,
    document_sha256: str,
    source_page: int,
    raw_value: str,
) -> str:
    """Compute deterministic citation ID bound to document and source page."""
    payload = f"citation|{ticker.upper()}|{metric}|{reporting_period}|{document_sha256}|{source_page}|{raw_value}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_governed_issuer_citations(
    *,
    qualification: Mapping[str, Any],
    sidecar: Mapping[str, Any],
    verified_at: str | None = None,
    metric_specs: Sequence[Mapping[str, Any]] | None = None,
    debt_specs: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Extract verified citations for an issuer from its qualification and persisted OCR sidecar.

    In Phase 2-D, extraction uses generic template recognition by default (metric_specs=None),
    deriving all statement structures, units, column layouts, and canonical facts without ticker recipes.
    """
    ticker = str(qualification.get("ticker", "")).upper().strip()
    period = str(qualification.get("reporting_period", "")).strip()
    doc_sha = str(qualification.get("document_sha256", "")).strip()
    evidence_id = str(qualification.get("evidence_id", "")).strip()
    scope = str(qualification.get("statement_scope", "consolidated")).strip()
    pub_at = qualification.get("published_at")
    obs_at = str(qualification.get("observed_at", ""))
    v_at = verified_at or obs_at

    if sidecar.get("document_sha256") != doc_sha:
        raise ValueError(
            f"Sidecar SHA-256 mismatch for {ticker}: expected {doc_sha}, got {sidecar.get('document_sha256')}"
        )

    # 1. Pure Generic Template Recognition Mode (Phase 2-D Primary Path)
    if metric_specs is None:
        facts = extract_generic_financial_statement_facts(
            sidecar=sidecar,
            reporting_period=period,
            qualification_record=qualification,
            verified_at=v_at,
        )

        citations: list[dict[str, Any]] = []
        for fact in facts:
            cit_id = compute_citation_id(
                ticker=ticker,
                metric=fact.canonical_metric,
                reporting_period=period,
                document_sha256=doc_sha,
                source_page=fact.page,
                raw_value=fact.raw_value,
            )

            cit_text = (
                f"{fact.source_label}: {fact.raw_value} ({fact.unit_label})"
                if fact.unit_label != "VND"
                else f"{fact.source_label}: {fact.raw_value}"
            )

            citations.append({
                "ticker": ticker,
                "metric": fact.canonical_metric,
                "reporting_period": period,
                "value": fact.normalized_value,
                "currency": fact.currency,
                "unit_scale": fact.unit_scale,
                "statement_scope": scope,
                "citation_id": cit_id,
                "evidence_id": evidence_id,
                "published_at": pub_at,
                "verified_at": v_at,
                "document_sha256": doc_sha,
                "source_page": fact.page,
                "line_item_code": fact.line_item_code,
                "citation": cit_text,
                "period_column_evidence": fact.period_column_evidence,
                "unit_evidence": fact.unit_evidence,
                "extraction": fact.extraction_details,
            })

        return citations

    # 2. Legacy / Explicit Spec Compatibility Mode
    pages_by_num = {int(p["page"]): p["text"] for p in sidecar.get("pages", [])}
    citations = []

    for spec in metric_specs:
        metric = str(spec["metric"])
        page = int(spec["page"])
        label_anchor = str(spec["ocr_label"])
        line_code = spec.get("line_item_code")
        source_label = str(spec.get("source_label") or label_anchor)
        unit = str(spec.get("unit", "VND"))
        unit_scale = int(spec.get("unit_scale", 1))
        currency = str(spec.get("currency", "VND"))
        statement = str(spec["statement"])

        if page not in pages_by_num:
            raise ValueError(f"Page {page} not found in sidecar for {ticker}")

        # Scan line
        matched_line = ""
        raw_val = ""
        for line in pages_by_num[page].splitlines():
            l_norm = _normalize_text(line)
            if _normalize_text(label_anchor) in l_norm:
                if line_code and line_code not in line.split():
                    if not re.search(rf"\b{line_code}\b", line):
                        continue
                tokens = re.findall(r"\(?[0-9]{1,3}(?:[.,][0-9]{3})+\)?", line)
                if tokens:
                    matched_line = line.strip()
                    raw_val = tokens[0]
                    break

        if not raw_val:
            raise ValueError(f"Could not locate line item anchor '{label_anchor}' in page text")

        extraction = verified_extraction(
            sidecar,
            page=page,
            raw_label=matched_line,
            raw_value=raw_val,
            source_raw_label=source_label,
            unit=unit,
            statement=statement,
            visual_source_page_verified=True,
        )

        cit_id = compute_citation_id(
            ticker=ticker,
            metric=metric,
            reporting_period=period,
            document_sha256=doc_sha,
            source_page=page,
            raw_value=raw_val,
        )

        citations.append({
            "ticker": ticker,
            "metric": metric,
            "reporting_period": period,
            "value": extraction["normalized_value"],
            "currency": currency,
            "unit_scale": unit_scale,
            "statement_scope": scope,
            "citation_id": cit_id,
            "evidence_id": evidence_id,
            "published_at": pub_at,
            "verified_at": v_at,
            "document_sha256": doc_sha,
            "source_page": page,
            "line_item_code": line_code,
            "citation": f"{source_label}: {raw_val} ({unit})" if unit != "VND" else f"{source_label}: {raw_val}",
            "extraction": extraction,
        })

    return citations
