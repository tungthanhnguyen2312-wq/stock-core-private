"""Generic local TSV-OCR table evidence for image-only official financial filings.

This module deliberately keeps source-image evidence separate from OCR-derived text.
It accepts only exact, positioned value cells selected by a visible two-period table
header and the standard financial-statement line-code taxonomy.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence

import fitz
from PIL import Image

from annual_financial_ocr_materialization import DEFAULT_ENGINE, parse_accounting_integer, sha256_file
from official_financial_structural_table import match_geometry_ambiguous_line_code_cell, match_geometry_table_row


CONTRACT_VERSION = "official_financial_ocr_table_evidence/v1"
OCR_CONFIG = {"dpi": 240, "colorspace": "gray", "language": "vie+eng", "psm": 6, "format": "tsv"}
# A single, field-scoped secondary mode.  This is never available to values or
# labels and is intentionally not a retry policy.
CELL_CODE_READ_CONTRACT = "ocr_cell_code_read/v1"
CELL_CODE_READ_CONFIG = {
    "base_render": {"dpi": 240, "colorspace": "gray"}, "upscale_factor": 4,
    "resample": "lanczos", "language": "eng", "psm": 8,
    "tesseract_variables": {"tessedit_char_whitelist": "0123456789"},
}
_VALID_LINE_CODE_RE = re.compile(r"^[0-9]{1,3}$")
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
DEBT_COMPONENT_LABEL_TERMS = {
    # Geometry reconstruction can place wrapped OCR label fragments on nearby
    # physical baselines; require each identity-bearing term independently.
    "short_term_borrowings": ("vay", "ngan", "han"),
    "long_term_borrowings_or_finance_leases": ("vay", "dai", "han"),
}
_FAMILY_ANCHORS = {
    "balance_sheet": (("bang can", "ke toan"), ("balance", "sheet")),
    "income_statement": (("bao cao ket qua", "kinh doanh"), ("income", "statement")),
    "cash_flow": (("bao cao luu chuyen", "tien"), ("cash", "flow")),
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


def _render_image_bytes(source: Path, page_number: int) -> tuple[bytes, dict[str, Any]]:
    """Re-render the immutable source page under the primary render contract."""
    document = fitz.open(source)
    try:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("PAGE_OUT_OF_RANGE")
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(OCR_CONFIG["dpi"] / 72.0, OCR_CONFIG["dpi"] / 72.0), colorspace=fitz.csGRAY, alpha=False)
        image_bytes = pixmap.tobytes("png")
        return image_bytes, {"rendered_image_sha256": hashlib.sha256(image_bytes).hexdigest(), "rendered_width": pixmap.width,
                             "rendered_height": pixmap.height, "source_page_rotation": page.rotation}
    finally:
        document.close()


def materialize_tsv_pages(record: Mapping[str, Any], *, evidence_root: Path, pages: Sequence[int], engine: Path = DEFAULT_ENGINE) -> dict[str, Any]:
    """Render fixed image-only pages once and preserve raw positioned TSV tokens."""
    root = Path(evidence_root)
    source = (root / str(record["relative_path"])).resolve()
    if not source.is_file() or sha256_file(source) != str(record["sha256"]):
        raise ValueError("RETAINED_SOURCE_HASH_MISMATCH")
    engine = Path(engine)
    version = subprocess.run([str(engine), "--version"], capture_output=True, check=True, text=True).stdout.splitlines()[0]
    materialized_pages = []
    document = fitz.open(source)
    try:
        native_text_pages = {number: bool(document[number - 1].get_text("text").strip()) for number in pages if 1 <= number <= document.page_count}
    finally:
        document.close()
    for number in pages:
        if number not in native_text_pages:
            raise ValueError("PAGE_OUT_OF_RANGE")
        if native_text_pages[number]:
            materialized_pages.append({"page_number": number, "route": "NATIVE_TEXT_AVAILABLE_USE_NATIVE_PATH"})
            continue
        image_bytes, render = _render_image_bytes(source, number)
        image_sha256 = render["rendered_image_sha256"]
        result = subprocess.run([str(engine), "stdin", "stdout", "-l", OCR_CONFIG["language"], "--psm", str(OCR_CONFIG["psm"]), "tsv"], input=image_bytes, capture_output=True, check=True)
        tokens = _parse_tsv(result.stdout, page_number=number, image_sha256=image_sha256)
        materialized_pages.append({
            "page_number": number, "route": "IMAGE_ONLY_TSV_OCR", "positioned_token_provenance": "OCR_TSV_POSITIONED_TOKEN", "source_image_evidence": {"document_sha256": record["sha256"], "source_page": number, **render},
            "ocr_derived_text_evidence": {"engine_version": version, "config": OCR_CONFIG, "tokens": tokens, "token_count": len(tokens)},
        })
    return {"contract_version": CONTRACT_VERSION, "document_id": record["document_id"], "document_sha256": record["sha256"], "ocr_config": OCR_CONFIG, "pages": materialized_pages, "materialization_id": _hash({"document_sha256": record["sha256"], "pages": materialized_pages})}


def _statement_family(tokens: Sequence[Mapping[str, Any]]) -> str | None:
    text = _normalize(" ".join(str(token["text"]) for token in sorted(tokens, key=lambda token: int(token["raw_token_order"]))))
    matches = [family for family, alternatives in _FAMILY_ANCHORS.items() if any(all(anchor in text for anchor in option) for option in alternatives)]
    return matches[0] if len(matches) == 1 else None


def _pages_by_statement_family(materialization: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    pages: dict[str, list[dict[str, Any]]] = {}
    for raw_page in materialization.get("pages") or []:
        payload = raw_page.get("ocr_derived_text_evidence") or {}
        tokens = payload.get("tokens") or []
        family = _statement_family(tokens)
        if family:
            pages.setdefault(family, []).append({"page_number": raw_page["page_number"], "document_sha256": materialization["document_sha256"],
                "statement_family": family, "positioned_token_provenance": raw_page.get("positioned_token_provenance"),
                "positioned_tokens": tokens, "source_image_evidence": raw_page.get("source_image_evidence"),
                "primary_ocr_evidence": {"engine_version": payload.get("engine_version"), "config": payload.get("config")}})
    return pages


def _code_crop_bbox(locator: Mapping[str, Any], source_image: Mapping[str, Any]) -> dict[str, int]:
    """Derive a code-cell crop only from the code band and its physical row."""
    bands = locator["row_object"]["column_bands"]["bands"]
    row = locator["code_row_bbox"]
    width = int(source_image["rendered_width"])
    height = int(source_image["rendered_height"])
    left = max(0, min(width, math.floor(float(bands["line_code"]["x0"]))))
    right = max(left + 1, min(width, math.ceil(float(bands["line_code"]["x1"]))))
    top = max(0, min(height, math.floor(float(row["top"]))))
    bottom = max(top + 1, min(height, math.ceil(float(row["bottom"]))))
    if left >= right or top >= bottom:
        raise ValueError("LINE_CODE_CROP_BOUNDS_INVALID")
    return {"left": left, "top": top, "right": right, "bottom": bottom,
            "coordinate_system": "base_rendered_image_pixels_top_left"}


def assess_secondary_line_code_raw(expected_line_code: str, raw_output: str) -> tuple[str, str]:
    """Accept only the exact raw, field-scoped ASCII line code; never repair it."""
    field_raw = str(raw_output).strip()
    exact_ascii_code = bool(_VALID_LINE_CODE_RE.fullmatch(field_raw)) and field_raw.isascii()
    if not exact_ascii_code:
        return field_raw, "SECONDARY_CODE_NOT_EXACT"
    if field_raw != expected_line_code:
        return field_raw, "CONFLICTING_PRIMARY_SECONDARY_CODE"
    return field_raw, "QUALIFIED_BY_SECONDARY_RAW_CODE"


def _run_secondary_line_code_read(
    locator: Mapping[str, Any], *, expected_line_code: str, source: Path,
    source_image: Mapping[str, Any], primary_ocr_evidence: Mapping[str, Any], materialization_id: str, engine: Path,
) -> dict[str, Any]:
    """Run the one fixed, field-scoped secondary OCR read for one malformed cell."""
    image_bytes, render = _render_image_bytes(source, int(locator["page"]))
    if render["rendered_image_sha256"] != source_image.get("rendered_image_sha256"):
        raise ValueError("PRIMARY_RENDER_IDENTITY_MISMATCH")
    crop_bbox = _code_crop_bbox(locator, source_image)
    with Image.open(BytesIO(image_bytes)) as image:
        crop = image.crop((crop_bbox["left"], crop_bbox["top"], crop_bbox["right"], crop_bbox["bottom"]))
        crop_buffer = BytesIO()
        crop.save(crop_buffer, format="PNG")
        crop_bytes = crop_buffer.getvalue()
        enlarged = crop.resize((crop.width * CELL_CODE_READ_CONFIG["upscale_factor"], crop.height * CELL_CODE_READ_CONFIG["upscale_factor"]), Image.Resampling.LANCZOS)
        enlarged_buffer = BytesIO()
        enlarged.save(enlarged_buffer, format="PNG")
        secondary_input = enlarged_buffer.getvalue()
    command = [str(engine), "stdin", "stdout", "-l", CELL_CODE_READ_CONFIG["language"], "--psm", str(CELL_CODE_READ_CONFIG["psm"])]
    for key, value in CELL_CODE_READ_CONFIG["tesseract_variables"].items():
        command.extend(["-c", f"{key}={value}"])
    result = subprocess.run(command, input=secondary_input, capture_output=True, check=True)
    raw_output = result.stdout.decode("utf-8", errors="replace")
    field_raw, disposition = assess_secondary_line_code_raw(expected_line_code, raw_output)
    primary = {"raw_token": locator["observed_line_code_raw"], "bbox": locator["code_cell_bbox"],
               "base_render_identity": dict(source_image), "full_page_ocr": dict(primary_ocr_evidence),
               "materialization_id": materialization_id}
    return {
        "contract_version": CELL_CODE_READ_CONTRACT, "expected_line_code": expected_line_code,
        "primary_evidence": primary, "row_identity": locator["row_object"],
        "code_band_bbox": dict(locator["row_object"]["column_bands"]["bands"]["line_code"]), "crop_bbox": crop_bbox,
        "crop_image_sha256": hashlib.sha256(crop_bytes).hexdigest(), "secondary_input_sha256": hashlib.sha256(secondary_input).hexdigest(),
        "secondary_ocr": {"engine": Path(engine).name, "config": CELL_CODE_READ_CONFIG, "raw_output": raw_output,
                           "field_raw": field_raw, "run_count": 1},
        "competing_code_candidate_count": 1, "disposition": disposition,
    }


def resolve_ambiguous_debt_line_code_cells(
    materialization: Mapping[str, Any], *, record: Mapping[str, Any], evidence_root: Path,
    reporting_period: str, engine: Path = DEFAULT_ENGINE,
) -> dict[str, Any]:
    """Resolve at most one malformed line-code cell per declared debt component.

    Exact primary codes stay authoritative.  For a malformed code, all candidate
    rows are located before one fixed crop read is permitted; no output can be used
    to adjust the crop, OCR configuration, or requested code.
    """
    root = Path(evidence_root)
    source = (root / str(record["relative_path"])).resolve()
    if not source.is_file() or sha256_file(source) != str(record["sha256"]) or str(record["sha256"]) != str(materialization["document_sha256"]):
        raise ValueError("RETAINED_SOURCE_HASH_MISMATCH")
    pages_by_family = _pages_by_statement_family(materialization)
    cells = []
    for metric, family, code in DEBT_COMPONENT_RULES:
        primary_matches = [match_geometry_table_row(page, line_code=code, target_period=reporting_period) for page in pages_by_family.get(family, [])]
        primary_matches = [match for match in primary_matches if match is not None]
        if len(primary_matches) == 1:
            cells.append({"canonical_metric": metric, "expected_line_code": code, "state": "PRIMARY_EXACT", "match": primary_matches[0], "secondary_run_count": 0})
            continue
        locators = [match_geometry_ambiguous_line_code_cell(page, target_period=reporting_period, required_label_terms=DEBT_COMPONENT_LABEL_TERMS[metric]) for page in pages_by_family.get(family, [])]
        locators = [item for item in locators if item is not None]
        if len(locators) != 1:
            cells.append({"canonical_metric": metric, "expected_line_code": code, "state": "BLOCKED", "reason": "AMBIGUOUS_CODE_CELL_ROW_NOT_UNIQUE", "primary_match_count": len(primary_matches), "secondary_run_count": 0})
            continue
        page = next(item for item in pages_by_family[family] if int(item["page_number"]) == int(locators[0]["page"]))
        cell = _run_secondary_line_code_read(locators[0], expected_line_code=code, source=source,
                                             source_image=page["source_image_evidence"], primary_ocr_evidence=page["primary_ocr_evidence"],
                                             materialization_id=str(materialization["materialization_id"]), engine=Path(engine))
        entry = {"canonical_metric": metric, "expected_line_code": code, "primary_match_count": len(primary_matches),
                 "secondary_run_count": 1, "cell_evidence": cell}
        if cell["disposition"] == "QUALIFIED_BY_SECONDARY_RAW_CODE":
            match = dict(locators[0])
            row_object = dict(match["row_object"])
            row_object["line_code"] = code
            match["row_object"] = row_object
            entry.update({"state": "QUALIFIED", "match": match})
        else:
            entry.update({"state": "BLOCKED", "reason": cell["disposition"]})
        cells.append(entry)
    return {"contract_version": CELL_CODE_READ_CONTRACT, "document_sha256": materialization["document_sha256"],
            "materialization_id": materialization["materialization_id"], "cells": cells,
            "resolution_id": _hash({"document_sha256": materialization["document_sha256"], "materialization_id": materialization["materialization_id"], "cells": cells})}


def qualify_table_facts(materialization: Mapping[str, Any], *, ticker: str, reporting_period: str, currency: str = "VND", unit_scale: int = 1,
                        line_code_cell_resolution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Produce qualified and blocked candidates; no panel mutation occurs here."""
    qualified: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    pages_by_family = _pages_by_statement_family(materialization)
    resolved_cells = {str(item.get("canonical_metric")): item for item in (line_code_cell_resolution or {}).get("cells", [])}
    def attempt(metric: str, family: str, code: str) -> dict[str, Any] | None:
        matches = [match_geometry_table_row(page, line_code=code, target_period=reporting_period) for page in pages_by_family.get(family, [])]
        matches = [match for match in matches if match is not None]
        cell_resolution = resolved_cells.get(metric)
        cell_evidence = None
        if len(matches) == 1:
            match = matches[0]
        elif cell_resolution and cell_resolution.get("state") == "QUALIFIED":
            match = cell_resolution["match"]
            cell_evidence = cell_resolution.get("cell_evidence")
        else:
            blocked.append({"canonical_metric": metric, "line_code": code, "statement_family": family, "state": "BLOCKED", "reason": "ROW_NOT_UNIQUE_OR_NOT_GEOMETRICALLY_RESOLVED", "match_count": len(matches)})
            return None
        try:
            value = parse_accounting_integer(match["current_raw"])[0] * unit_scale
        except ValueError:
            blocked.append({"canonical_metric": metric, "line_code": code, "statement_family": family, "state": "BLOCKED", "reason": "OCR_NUMERIC_AMBIGUITY", "raw_value": match["current_raw"]})
            return None
        reason_codes = ["OFFICIAL_EVIDENCE_QUALIFIED", "IMAGE_ONLY_TSV_OCR_GEOMETRY", "EXACT_LINE_CODE"]
        if cell_evidence:
            reason_codes[-1] = "CELL_LEVEL_EXACT_LINE_CODE"
        lineage = {"document_sha256": materialization["document_sha256"], "source_page": match["page"], "line_code": code,
                   "row_object": match["row_object"], "source_image_evidence": next(page["source_image_evidence"] for page in pages_by_family[family] if page["page_number"] == match["page"]),
                   "ocr_derived_text_evidence": {"materialization_id": materialization["materialization_id"], "current_raw": match["current_raw"], "comparative_raw": match["comparative_raw"]}}
        if cell_evidence:
            lineage["line_code_cell_evidence"] = cell_evidence
        return {"canonical_metric": metric, "value": value, "currency": currency, "unit_scale": unit_scale, "reporting_period": reporting_period, "statement_family": family, "qualification_state": "QUALIFIED", "reason_codes": reason_codes, "source_lineage": lineage}
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
            "source_lineage": {"document_sha256": materialization["document_sha256"], "source_page": short["source_lineage"]["source_page"],
                "source_pages": [short["source_lineage"]["source_page"], long["source_lineage"]["source_page"]],
                "row_object": short["source_lineage"]["row_object"], "source_image_evidence": short["source_lineage"]["source_image_evidence"],
                "ocr_derived_text_evidence": short["source_lineage"]["ocr_derived_text_evidence"], "debt_component_lineages": [short["source_lineage"], long["source_lineage"]]},
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
