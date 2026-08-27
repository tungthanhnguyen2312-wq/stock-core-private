"""Generic local TSV-OCR table evidence for image-only official financial filings.

This module deliberately keeps source-image evidence separate from OCR-derived text.
It accepts only exact, positioned value cells selected by a visible two-period table
header and the standard financial-statement line-code taxonomy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

import fitz

from annual_financial_ocr_materialization import DEFAULT_ENGINE, parse_accounting_integer, sha256_file
from official_financial_structural_table import match_geometry_table_row


CONTRACT_VERSION = "official_financial_ocr_table_evidence/v1"
OCR_CONFIG = {"dpi": 240, "colorspace": "gray", "language": "vie+eng", "psm": 6, "format": "tsv"}
STANDARD_FACT_RULES = (
    ("cash_and_equivalents", "balance_sheet", "110"),
    ("total_assets", "balance_sheet", "270"),
    ("shareholders_equity", "balance_sheet", "400"),
    ("revenue", "income_statement", "10"),
    # Consolidated parent-attributable earnings, never line 60 total profit.
    ("net_income", "income_statement", "61"),
    ("operating_cash_flow", "cash_flow", "20"),
)
DEBT_COMPONENT_RULES = (
    ("short_term_borrowings", "balance_sheet", "320"),
    ("long_term_borrowings_or_finance_leases", "balance_sheet", "338"),
)
_FAMILY_ANCHORS = {
    "balance_sheet": (("bang can", "ke toan"),),
    "income_statement": (("bao cao ket qua", "kinh doanh"),),
    "cash_flow": (("bao cao luu chuyen", "tien"),),
}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    import unicodedata
    return " ".join("".join(ch for ch in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(ch)).split())


def _parse_tsv(raw: bytes, *, page_number: int, image_sha256: str) -> list[dict[str, Any]]:
    rows = raw.decode("utf-8", errors="replace").splitlines()
    if not rows or rows[0].split("\t")[:12] != ["level", "page_num", "block_num", "par_num", "line_num", "word_num", "left", "top", "width", "height", "conf", "text"]:
        raise ValueError("OCR_TSV_SCHEMA_INVALID")
    tokens = []
    for raw_order, row in enumerate(rows[1:]):
        parts = row.split("\t")
        if len(parts) < 12 or not parts[11].strip():
            continue
        try:
            x, top, width, height = (float(parts[index]) for index in (6, 7, 8, 9))
            confidence = float(parts[10])
        except ValueError as exc:
            raise ValueError("OCR_TSV_POSITION_INVALID") from exc
        text = parts[11].strip()
        token = {
            "text": text, "x0": x, "x1": x + width, "top": top, "bottom": top + height,
            "bbox": {"left": x, "top": top, "width": width, "height": height, "coordinate_system": "rendered_image_pixels_top_left"},
            "confidence": confidence, "raw_token_order": raw_order,
            "tsv_hierarchy": {key: int(parts[index]) for key, index in (("level", 0), ("page_num", 1), ("block_num", 2), ("par_num", 3), ("line_num", 4), ("word_num", 5))},
            "provenance": "OCR_TSV_POSITIONED_TOKEN",
            "token_id": _hash({"page": page_number, "image_sha256": image_sha256, "raw_token_order": raw_order, "text": text, "bbox": [x, top, width, height]}),
        }
        tokens.append(token)
    return tokens


def materialize_tsv_pages(record: Mapping[str, Any], *, evidence_root: Path, pages: Sequence[int], engine: Path = DEFAULT_ENGINE) -> dict[str, Any]:
    """Render fixed image-only pages once and preserve raw positioned TSV tokens."""
    root = Path(evidence_root)
    source = (root / str(record["relative_path"])).resolve()
    if not source.is_file() or sha256_file(source) != str(record["sha256"]):
        raise ValueError("RETAINED_SOURCE_HASH_MISMATCH")
    engine = Path(engine)
    version = subprocess.run([str(engine), "--version"], capture_output=True, check=True, text=True).stdout.splitlines()[0]
    document = fitz.open(source)
    materialized_pages = []
    try:
        for number in pages:
            if number < 1 or number > document.page_count:
                raise ValueError("PAGE_OUT_OF_RANGE")
            page = document[number - 1]
            if page.get_text("text").strip():
                materialized_pages.append({"page_number": number, "route": "NATIVE_TEXT_AVAILABLE_USE_NATIVE_PATH"})
                continue
            pixmap = page.get_pixmap(matrix=fitz.Matrix(OCR_CONFIG["dpi"] / 72.0, OCR_CONFIG["dpi"] / 72.0), colorspace=fitz.csGRAY, alpha=False)
            image_bytes = pixmap.tobytes("png")
            image_sha256 = hashlib.sha256(image_bytes).hexdigest()
            result = subprocess.run([str(engine), "stdin", "stdout", "-l", OCR_CONFIG["language"], "--psm", str(OCR_CONFIG["psm"]), "tsv"], input=image_bytes, capture_output=True, check=True)
            tokens = _parse_tsv(result.stdout, page_number=number, image_sha256=image_sha256)
            materialized_pages.append({
                "page_number": number, "route": "IMAGE_ONLY_TSV_OCR", "positioned_token_provenance": "OCR_TSV_POSITIONED_TOKEN", "source_image_evidence": {"document_sha256": record["sha256"], "source_page": number, "rendered_image_sha256": image_sha256, "rendered_width": pixmap.width, "rendered_height": pixmap.height, "source_page_rotation": page.rotation},
                "ocr_derived_text_evidence": {"engine_version": version, "config": OCR_CONFIG, "tokens": tokens, "token_count": len(tokens)},
            })
    finally:
        document.close()
    return {"contract_version": CONTRACT_VERSION, "document_id": record["document_id"], "document_sha256": record["sha256"], "ocr_config": OCR_CONFIG, "pages": materialized_pages, "materialization_id": _hash({"document_sha256": record["sha256"], "pages": materialized_pages})}


def _statement_family(tokens: Sequence[Mapping[str, Any]]) -> str | None:
    text = _normalize(" ".join(str(token["text"]) for token in sorted(tokens, key=lambda token: int(token["raw_token_order"]))))
    matches = [family for family, alternatives in _FAMILY_ANCHORS.items() if any(all(anchor in text for anchor in option) for option in alternatives)]
    return matches[0] if len(matches) == 1 else None


def qualify_table_facts(materialization: Mapping[str, Any], *, ticker: str, reporting_period: str, currency: str = "VND", unit_scale: int = 1) -> dict[str, Any]:
    """Produce qualified and blocked candidates; no panel mutation occurs here."""
    qualified: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    pages_by_family: dict[str, list[dict[str, Any]]] = {}
    for raw_page in materialization.get("pages") or []:
        payload = raw_page.get("ocr_derived_text_evidence") or {}
        tokens = payload.get("tokens") or []
        family = _statement_family(tokens)
        if family:
            pages_by_family.setdefault(family, []).append({"page_number": raw_page["page_number"], "document_sha256": materialization["document_sha256"], "statement_family": family, "positioned_token_provenance": raw_page.get("positioned_token_provenance"), "positioned_tokens": tokens, "source_image_evidence": raw_page.get("source_image_evidence")})
    def attempt(metric: str, family: str, code: str) -> dict[str, Any] | None:
        matches = [match_geometry_table_row(page, line_code=code, target_period=reporting_period) for page in pages_by_family.get(family, [])]
        matches = [match for match in matches if match is not None]
        if len(matches) != 1:
            blocked.append({"canonical_metric": metric, "line_code": code, "statement_family": family, "state": "BLOCKED", "reason": "ROW_NOT_UNIQUE_OR_NOT_GEOMETRICALLY_RESOLVED", "match_count": len(matches)})
            return None
        match = matches[0]
        try:
            value = parse_accounting_integer(match["current_raw"])[0] * unit_scale
        except ValueError:
            blocked.append({"canonical_metric": metric, "line_code": code, "statement_family": family, "state": "BLOCKED", "reason": "OCR_NUMERIC_AMBIGUITY", "raw_value": match["current_raw"]})
            return None
        return {"canonical_metric": metric, "value": value, "currency": currency, "unit_scale": unit_scale, "reporting_period": reporting_period, "statement_family": family, "qualification_state": "QUALIFIED", "reason_codes": ["OFFICIAL_EVIDENCE_QUALIFIED", "IMAGE_ONLY_TSV_OCR_GEOMETRY", "EXACT_LINE_CODE"], "source_lineage": {"document_sha256": materialization["document_sha256"], "source_page": match["page"], "line_code": code, "row_object": match["row_object"], "source_image_evidence": next(page["source_image_evidence"] for page in pages_by_family[family] if page["page_number"] == match["page"]), "ocr_derived_text_evidence": {"materialization_id": materialization["materialization_id"], "current_raw": match["current_raw"], "comparative_raw": match["comparative_raw"]}}}
    for rule in STANDARD_FACT_RULES:
        fact = attempt(*rule)
        if fact:
            qualified.append(fact)
    components = [attempt(name, family, code) for name, family, code in DEBT_COMPONENT_RULES]
    if all(components):
        short, long = components
        qualified.append({
            "canonical_metric": "total_interest_bearing_debt", "value": short["value"] + long["value"],
            "currency": currency, "unit_scale": unit_scale, "reporting_period": reporting_period,
            "statement_family": "balance_sheet", "qualification_state": "QUALIFIED",
            "reason_codes": ["OFFICIAL_EVIDENCE_QUALIFIED", "IMAGE_ONLY_TSV_OCR_GEOMETRY", "EXPLICIT_DEBT_COMPONENT_SUM"],
            "debt_components": components,
            "source_lineage": {"document_sha256": materialization["document_sha256"], "source_pages": [short["source_lineage"]["source_page"], long["source_lineage"]["source_page"]]},
        })
    else:
        blocked.append({"canonical_metric": "total_interest_bearing_debt", "state": "BLOCKED", "reason": "DEBT_COMPONENT_INCOMPLETE"})
    return {"contract_version": CONTRACT_VERSION, "ticker": ticker, "document_sha256": materialization["document_sha256"], "reporting_period": reporting_period, "qualified_facts": qualified, "blocked_candidates": blocked, "candidate_count": len(qualified) + len(blocked)}


def panel_facts_from_qualified_ocr(
    qualification: Mapping[str, Any], *, entity_type: str, statement_scope: str,
    audit_or_review_status: str, knowledge_available_at: str, observed_at: str,
) -> list[dict[str, Any]]:
    """Adapt already-qualified OCR geometry facts to the existing P3-F13 ingress shape.

    This function is deliberately document-generic: issuer, period, source hash and
    exact row evidence come only from ``qualification``.  It never re-parses or
    repairs OCR text, and refuses incomplete metadata before an ingress candidate
    can be constructed.
    """
    if statement_scope != "consolidated" or audit_or_review_status != "audited":
        raise ValueError("OCR_DOCUMENT_METADATA_NOT_QUALIFIED")
    ticker = str(qualification.get("ticker") or "").upper()
    document_sha = str(qualification.get("document_sha256") or "")
    period = str(qualification.get("reporting_period") or "")
    if not ticker or not document_sha or not period:
        raise ValueError("OCR_QUALIFICATION_IDENTITY_MISSING")
    output: list[dict[str, Any]] = []
    instantaneous = {"cash_and_equivalents", "total_assets", "shareholders_equity", "total_interest_bearing_debt"}
    for fact in qualification.get("qualified_facts") or []:
        if fact.get("qualification_state") != "QUALIFIED":
            continue
        lineage = dict(fact.get("source_lineage") or {})
        row = dict(lineage.get("row_object") or {})
        source_image = dict(lineage.get("source_image_evidence") or {})
        ocr = dict(lineage.get("ocr_derived_text_evidence") or {})
        if not row or not source_image or not ocr or source_image.get("document_sha256") != document_sha:
            raise ValueError("OCR_ROW_EVIDENCE_INCOMPLETE")
        citation_id = _hash({"contract": CONTRACT_VERSION, "document_sha256": document_sha,
                             "page": lineage.get("source_page"), "statement_family": fact.get("statement_family"),
                             "line_code": lineage.get("line_code"), "row_object": row,
                             "rendered_image_sha256": source_image.get("rendered_image_sha256"),
                             "materialization_id": ocr.get("materialization_id")})
        metric = str(fact["canonical_metric"])
        output.append({
            "issuer_identity": ticker, "entity_type": entity_type, "applicability_state": "APPLICABLE",
            "authority_tier": "promoted_corporate_evidence", "canonical_metric": metric,
            "value": fact["value"], "currency": fact["currency"], "unit_scale": fact["unit_scale"],
            "reporting_period": period, "period_type": "annual", "period_start": f"{period}-01-01",
            "period_end": f"{period}-12-31", "statement_scope": statement_scope,
            "statement_family": fact["statement_family"],
            "temporal_nature": "instant" if metric in instantaneous else "duration",
            "qualification_state": "QUALIFIED", "is_positive_authority": True,
            "knowledge_available_at": knowledge_available_at, "observed_at": observed_at,
            "temporal_envelope": {"as_of": period, "domain": "financial_statement",
                "field_id": f"ocr-tsv:{document_sha}:{metric}:{period}", "field_name": metric,
                "freshness_status": "historical", "knowledge_available_at": knowledge_available_at,
                "observed_at": observed_at, "pit_eligible": True, "pit_status": "QUALIFIED",
                "quality_status": "qualified", "value": fact["value"]},
            "reason_codes": list(fact.get("reason_codes") or []),
            "source_lineage": {"provider": "official_issuer_ir", "authority_tier": "promoted_corporate_evidence",
                "document_sha256": document_sha, "citation_id": citation_id, "evidence_id": citation_id,
                "source_page": lineage.get("source_page"), "line_code": lineage.get("line_code"),
                "row_object": row, "source_image_evidence": source_image,
                "ocr_derived_text_evidence": ocr, "extraction_method": "image_only_tsv_ocr_geometry"},
        })
    return output
