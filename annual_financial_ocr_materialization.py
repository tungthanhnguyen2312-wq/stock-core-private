"""Bounded, page-preserving OCR materialization for retained annual filings.

This is intentionally a small adapter, not a general document platform.  It can
run local Tesseract on selected pages of an already hash-verified scan, and it
will only build citation metadata for values explicitly confirmed against that
source page.  The PDF remains the evidence authority.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from official_document_ocr_handoff import add_batch, citation_id, sha256_file


VERSION = "1.0.0"
CONTRACT = "annual_financial_ocr_materialization/v1"
DEFAULT_ENGINE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def engine_version(engine: Path = DEFAULT_ENGINE) -> str:
    """Return the first, stable Tesseract version line or fail closed."""
    result = subprocess.run([str(engine), "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False, timeout=15)
    first = result.stdout.decode("utf-8", "strict").splitlines()
    if result.returncode or not first or not first[0].startswith("tesseract "):
        raise ValueError("OCR_ENGINE_QUALIFICATION_FAILED")
    return first[0]


def parse_accounting_integer(raw: str) -> tuple[int, str]:
    """Parse a displayed integer without repairing ambiguous OCR characters."""
    text = str(raw).strip()
    negative = text.startswith("(") and text.endswith(")")
    body = text[1:-1] if negative else text
    if not re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})*|[0-9]+", body):
        raise ValueError("OCR_NUMERIC_AMBIGUITY")
    if "," in body and any(len(group) != 3 for group in body.split(",")[1:]):
        raise ValueError("OCR_NUMERIC_AMBIGUITY")
    return (-int(body.replace(",", "")) if negative else int(body.replace(",", "")),
            "negative" if negative else "positive")


def _normal(text: str) -> str:
    """Normalize benign label typography only; numeric text remains exact."""
    return " ".join(str(text).replace("\u2019", "'").casefold().split())


def materialization_id(*, document_sha256: str, page: int, engine: str, text_sha256: str) -> str:
    return _digest({"contract": CONTRACT, "document_sha256": document_sha256, "page": int(page),
                    "engine": engine, "text_sha256": text_sha256})


def render_and_ocr(record: Mapping[str, Any], *, root: Path, pages: Sequence[int],
                   engine: Path = DEFAULT_ENGINE, dpi: int = 216) -> dict[str, Any]:
    """OCR only the selected one-indexed pages, preserving each page boundary.

    PyMuPDF is loaded only when executing the local adapter.  It is used solely
    to rasterise an immutable source page in memory; no image or PDF is written.
    """
    try:
        import fitz  # Existing local renderer; deliberately no network service.
    except ImportError as error:  # pragma: no cover - environment-specific
        raise ValueError("OCR_RENDERER_UNAVAILABLE") from error
    source = Path(root) / str(record["relative_path"])
    if not source.is_file() or sha256_file(source) != record["sha256"]:
        raise ValueError("source_hash_mismatch")
    requested = sorted({int(page) for page in pages})
    if not requested or requested[0] < 1:
        raise ValueError("OCR_PAGE_INVALID")
    version = engine_version(engine)
    document = fitz.open(source)
    if requested[-1] > len(document):
        raise ValueError("STATEMENT_PAGE_NOT_FOUND")
    output: list[tuple[int, bytes, bytes]] = []
    for page in requested:
        pixmap = document[page - 1].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72),
                                                colorspace=fitz.csGRAY, alpha=False)
        result = subprocess.run([str(engine), "stdin", "stdout", "-l", "eng", "--psm", "6"],
                                input=pixmap.tobytes("png"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=90)
        output.append((page, result.stdout, result.stderr))
    checkpoint = add_batch({}, record, output)
    materialized = []
    for row in checkpoint["pages"]:
        materialized.append({**row, "ocr_engine": version, "render_dpi": dpi,
                             "materialization_id": materialization_id(
                                 document_sha256=row["document_sha256"], page=row["page"], engine=version,
                                 text_sha256=row["text_sha256"]), "contract": CONTRACT})
    return {"schema_version": VERSION, "contract": CONTRACT, "document_id": record["document_id"],
            "document_sha256": record["sha256"], "ticker": record["ticker"], "ocr_engine": version,
            "source_page_count": len(document), "pages_processed": len(materialized), "pages": materialized}


def verified_extraction(materialization: Mapping[str, Any], *, page: int, raw_label: str, raw_value: str,
                        unit: str, visual_source_page_verified: bool, statement: str) -> dict[str, Any]:
    """Return identity-bound extraction metadata only after exact source-page verification."""
    if not visual_source_page_verified:
        raise ValueError("CITATION_VERIFICATION_FAILED")
    rows = [row for row in materialization.get("pages", []) if int(row.get("page", 0)) == int(page)]
    if len(rows) != 1 or rows[0].get("status") != "ocr_available":
        raise ValueError("OCR_EXTRACTION_FAILED")
    row = rows[0]
    value, sign = parse_accounting_integer(raw_value)
    if _normal(raw_label) not in _normal(row.get("text", "")) or raw_value not in row.get("text", ""):
        raise ValueError("OCR_NUMERIC_AMBIGUITY")
    return {"method": "document_line_item", "source_pages": [int(page)], "raw_labels": [raw_label],
            "materialization": {"contract": CONTRACT, "document_sha256": materialization["document_sha256"],
                                "page": int(page), "page_citation_id": row.get("citation_id") or citation_id(
                                    row["document_id"], row["document_sha256"], int(page), row["text"]),
                                "text_sha256": row["text_sha256"], "materialization_id": row["materialization_id"],
                                "ocr_engine": row["ocr_engine"], "render_dpi": row["render_dpi"],
                                "verification": "source_page_visual"},
            "raw_values": [raw_value], "unit": unit, "statement": statement,
            "normalized_value": value, "sign": sign}


def verified_sum_extraction(materialization: Mapping[str, Any], *, components: Sequence[Mapping[str, Any]],
                            unit: str, statement: str) -> dict[str, Any]:
    """Build the existing approved debt-sum shape from independently verified rows."""
    if len(components) < 2:
        raise ValueError("REQUIRED_DEBT_COMPONENT_MISSING")
    rows = []
    for component in components:
        rows.append(verified_extraction(materialization, page=int(component["page"]), raw_label=str(component["label"]),
                                        raw_value=str(component["raw_value"]), unit=unit,
                                        visual_source_page_verified=bool(component.get("visual_source_page_verified")),
                                        statement=statement))
    values = [item["normalized_value"] for item in rows]
    return {"method": "document_line_item_sum", "source_pages": sorted({item["source_pages"][0] for item in rows}),
            "raw_labels": [item["raw_labels"][0] for item in rows],
            "components": [{"label": item["raw_labels"][0], "value": item["normalized_value"]} for item in rows],
            "materialization": {"contract": CONTRACT, "components": [item["materialization"] for item in rows],
                                "verification": "source_page_visual"},
            "raw_values": [item["raw_values"][0] for item in rows], "unit": unit, "statement": statement,
            "normalized_value": sum(values), "sign": "negative" if sum(values) < 0 else "positive"}


def write_materialization(path: Path, materialization: Mapping[str, Any]) -> None:
    """Persist a deterministic derived sidecar; never write or replace the source PDF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical(materialization) + "\n", encoding="utf-8")
