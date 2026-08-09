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
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from official_document_ocr_handoff import add_batch, citation_id, sha256_file


VERSION = "1.0.0"
CONTRACT = "annual_financial_ocr_materialization/v1"
DEFAULT_ENGINE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
DEBT_COMPONENT_TYPES = frozenset({"short_term_borrowings", "long_term_borrowings_or_finance_leases"})


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
    if not re.fullmatch(r"[0-9]{1,3}(?:[,.][0-9]{3})*|[0-9]+", body):
        raise ValueError("OCR_NUMERIC_AMBIGUITY")
    separators = {char for char in body if char in ",."}
    if len(separators) > 1:
        raise ValueError("OCR_NUMERIC_AMBIGUITY")
    separator = next(iter(separators), None)
    if separator and any(len(group) != 3 for group in body.split(separator)[1:]):
        raise ValueError("OCR_NUMERIC_AMBIGUITY")
    normalized = body.replace(",", "").replace(".", "")
    return (-int(normalized) if negative else int(normalized),
            "negative" if negative else "positive")


def _normal(text: str) -> str:
    """Normalize benign label typography only; numeric text remains exact."""
    return " ".join(str(text).replace("\u2019", "'").casefold().split())


def _label_key(text: str) -> str:
    """Fold diacritics only for the finite borrowing-label vocabulary."""
    value = unicodedata.normalize("NFD", _normal(text)).replace("đ", "d")
    return "".join(char for char in value if unicodedata.category(char) != "Mn")


def materialization_id(*, document_sha256: str, page: int, engine: str, text_sha256: str) -> str:
    return _digest({"contract": CONTRACT, "document_sha256": document_sha256, "page": int(page),
                    "engine": engine, "text_sha256": text_sha256})


def render_and_ocr(record: Mapping[str, Any], *, root: Path, pages: Sequence[int],
                   engine: Path = DEFAULT_ENGINE, dpi: int = 216, language: str = "eng",
                   psm: int | Mapping[int, int] = 6) -> dict[str, Any]:
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
    if not re.fullmatch(r"[a-z+_]+", language):
        raise ValueError("OCR_LANGUAGE_INVALID")
    version = engine_version(engine)
    psm_for_page = ({int(page): int(value) for page, value in psm.items()} if isinstance(psm, Mapping)
                    else {page: int(psm) for page in requested})
    if any(value not in {3, 4, 6, 11, 12} for value in psm_for_page.values()):
        raise ValueError("OCR_LAYOUT_MODE_INVALID")
    document = fitz.open(source)
    if requested[-1] > len(document):
        raise ValueError("STATEMENT_PAGE_NOT_FOUND")
    output: list[tuple[int, bytes, bytes]] = []
    for page in requested:
        page_psm = psm_for_page.get(page, 6)
        pixmap = document[page - 1].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72),
                                                colorspace=fitz.csGRAY, alpha=False)
        result = subprocess.run([str(engine), "stdin", "stdout", "-l", language, "--psm", str(page_psm)],
                                input=pixmap.tobytes("png"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=90)
        output.append((page, result.stdout, result.stderr))
    checkpoint = add_batch({}, record, output)
    materialized = []
    for row in checkpoint["pages"]:
        page_psm = psm_for_page[int(row["page"])]
        engine_identity = f"{version} language={language} psm={page_psm}"
        materialized.append({**row, "ocr_engine": engine_identity, "ocr_language": language, "ocr_psm": page_psm,
                             "render_dpi": dpi,
                             "materialization_id": materialization_id(
                                 document_sha256=row["document_sha256"], page=row["page"], engine=engine_identity,
                                 text_sha256=row["text_sha256"]), "contract": CONTRACT})
    return {"schema_version": VERSION, "contract": CONTRACT, "document_id": record["document_id"],
            "document_sha256": record["sha256"], "ticker": record["ticker"], "ocr_engine": version,
            "ocr_language": language, "ocr_psm": {str(page): psm_for_page[page] for page in requested},
            "source_page_count": len(document), "pages_processed": len(materialized), "pages": materialized}


def extract_pdf_text(record: Mapping[str, Any], *, root: Path, pages: Sequence[int]) -> dict[str, Any]:
    """Materialize selected pages from a text-bearing retained PDF without OCR.

    The source hash, PDF page boundary, extraction-library version and extracted bytes
    are bound into the same sidecar identity as scan OCR.  An empty text layer is a
    terminal result for this route; callers must use ``render_and_ocr`` explicitly.
    """
    try:
        import pypdf
    except ImportError as error:  # pragma: no cover - environment-specific
        raise ValueError("PDF_TEXT_EXTRACTOR_UNAVAILABLE") from error
    source = Path(root) / str(record["relative_path"])
    if not source.is_file() or sha256_file(source) != record["sha256"]:
        raise ValueError("source_hash_mismatch")
    requested = sorted({int(page) for page in pages})
    if not requested or requested[0] < 1:
        raise ValueError("PDF_TEXT_PAGE_INVALID")
    reader = pypdf.PdfReader(source)
    if requested[-1] > len(reader.pages):
        raise ValueError("STATEMENT_PAGE_NOT_FOUND")
    version = f"pypdf {pypdf.__version__}"
    materialized = []
    for page in requested:
        text = reader.pages[page - 1].extract_text() or ""
        status = "text_available" if text.strip() else "text_empty_page"
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        row = {"document_id": record["document_id"], "document_sha256": record["sha256"], "page": page,
               "provenance": "pdf_text", "status": status, "text": text, "text_sha256": text_sha256,
               "extraction_engine": version, "extraction_method": "pdf_text", "contract": CONTRACT,
               "materialization_id": materialization_id(document_sha256=record["sha256"], page=page,
                                                          engine=version, text_sha256=text_sha256)}
        if status == "text_available":
            row["citation_id"] = hashlib.sha256(
                f"pdf_text|{record['document_id']}|{record['sha256']}|{page}|{text}".encode("utf-8")).hexdigest()
        materialized.append(row)
    return {"schema_version": VERSION, "contract": CONTRACT, "document_id": record["document_id"],
            "document_sha256": record["sha256"], "ticker": record["ticker"], "extraction_engine": version,
            "extraction_method": "pdf_text", "source_page_count": len(reader.pages),
            "pages_processed": len(materialized), "pages": materialized}


def verified_extraction(materialization: Mapping[str, Any], *, page: int, raw_label: str, raw_value: str,
                        unit: str, visual_source_page_verified: bool, statement: str,
                        source_raw_label: str | None = None,
                        source_raw_value: str | None = None) -> dict[str, Any]:
    """Return identity-bound extraction metadata only after exact source-page verification."""
    if not visual_source_page_verified:
        raise ValueError("CITATION_VERIFICATION_FAILED")
    rows = [row for row in materialization.get("pages", []) if int(row.get("page", 0)) == int(page)]
    if len(rows) != 1 or rows[0].get("status") not in {"ocr_available", "text_available"}:
        raise ValueError("DOCUMENT_TEXT_EXTRACTION_FAILED")
    row = rows[0]
    value, sign = parse_accounting_integer(raw_value)
    if _normal(raw_label) not in _normal(row.get("text", "")) or raw_value not in row.get("text", ""):
        raise ValueError("OCR_NUMERIC_AMBIGUITY")
    source_label = str(source_raw_label or raw_label)
    source_value = str(source_raw_value or raw_value)
    return {"method": "document_line_item", "source_pages": [int(page)], "raw_labels": [source_label],
            "materialization": {"contract": CONTRACT, "document_sha256": materialization["document_sha256"],
                                "page": int(page), "page_citation_id": row.get("citation_id") or citation_id(
                                    row["document_id"], row["document_sha256"], int(page), row["text"]),
                                "text_sha256": row["text_sha256"], "materialization_id": row["materialization_id"],
                                "verification": "source_page_visual",
                                **({"ocr_engine": row["ocr_engine"], "render_dpi": row["render_dpi"],
                                    "extraction_method": "ocr"} if row.get("status") == "ocr_available" else
                                   {"extraction_engine": row["extraction_engine"], "extraction_method": "pdf_text"})},
            "raw_values": [source_value], "ocr_anchors": {"label": raw_label, "value": raw_value},
            "unit": unit, "statement": statement,
            "normalized_value": value, "sign": sign}


def verified_sum_extraction(materialization: Mapping[str, Any], *, components: Sequence[Mapping[str, Any]],
                            unit: str, statement: str) -> dict[str, Any]:
    """Build the existing approved debt-sum shape from independently verified rows."""
    if len(components) < 2:
        raise ValueError("REQUIRED_DEBT_COMPONENT_MISSING")
    rows = []
    for component in components:
        rows.append(verified_extraction(materialization, page=int(component["page"]),
                                        raw_label=str(component.get("ocr_label") or component["label"]),
                                        raw_value=str(component.get("ocr_raw_value") or component["raw_value"]),
                                        source_raw_label=str(component.get("source_raw_label") or component["label"]),
                                        source_raw_value=str(component.get("source_raw_value") or component["raw_value"]), unit=unit,
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


def verified_debt_extraction(materialization: Mapping[str, Any], *, components: Sequence[Mapping[str, Any]],
                             unit: str, statement: str, reporting_period: str) -> dict[str, Any]:
    """Derive debt only from exactly labelled, same-period borrowing components.

    This is the existing two-line debt vocabulary made explicit: current borrowings
    plus non-current borrowings/finance leases.  Generic liabilities, duplicate
    components, cross-period rows and hand-entered totals are intentionally refused.
    """
    types = [str(component.get("component_type", "")) for component in components]
    if set(types) != DEBT_COMPONENT_TYPES or len(types) != len(DEBT_COMPONENT_TYPES):
        raise ValueError("REQUIRED_DEBT_COMPONENT_MISSING")
    if any(str(component.get("reporting_period", "")) != str(reporting_period) for component in components):
        raise ValueError("DEBT_COMPONENT_PERIOD_MISMATCH")
    labels = {str(component["component_type"]): _label_key(str(component.get("label", ""))) for component in components}
    short_label = labels["short_term_borrowings"]
    long_label = labels["long_term_borrowings_or_finance_leases"]
    short_qualified = (("short" in short_label and ("borrow" in short_label or "loan" in short_label))
                       or ("vay" in short_label and "han" in short_label and "dai" not in short_label))
    long_qualified = (("long" in long_label and ("borrow" in long_label or "loan" in long_label))
                      or "finance lease" in long_label or "lease liabilities" in long_label
                      or ("vay" in long_label and "dai" in long_label and "han" in long_label))
    if not (short_qualified and long_qualified):
        raise ValueError("DEBT_COMPONENT_LABEL_UNQUALIFIED")
    return verified_sum_extraction(materialization, components=components, unit=unit, statement=statement)


def write_materialization(path: Path, materialization: Mapping[str, Any]) -> None:
    """Persist a deterministic derived sidecar; never write or replace the source PDF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical(materialization) + "\n", encoding="utf-8")
