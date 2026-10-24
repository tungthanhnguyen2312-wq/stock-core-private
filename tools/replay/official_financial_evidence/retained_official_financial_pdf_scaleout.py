"""Inventory and retained-only replay of official financial PDF evidence.

This is deliberately an adapter around ``official_financial_pdf_page_evidence``.
It discovers local PDF bytes by signature, deduplicates SHA-256 first, and does
not acquire, OCR, or create another fact store.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from official_financial_pdf_page_evidence import build_artifact as build_page_evidence_artifact


VERSION = "retained_official_financial_pdf_scaleout/v1"
FINANCIAL_CLASSES = {"audited_annual_financial_statements", "annual_report", "reviewed_interim_financial_statements"}
NON_FINANCIAL_PATH_TERMS = ("corporate_action", "daily_trading", "trading_statistics", "visual-check", "agm_document")


def _stable(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def discover_pdf_bytes(operations_root: Path) -> dict[str, list[Path]]:
    """Return every retained PDF signature grouped by immutable byte hash."""
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(operations_root.rglob("*")):
        if path.is_file() and path.suffix.casefold() in {".pdf", ".bin"} and _is_pdf(path):
            grouped[hashlib.sha256(path.read_bytes()).hexdigest()].append(path)
    return dict(grouped)


def _manifest_documents(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    governed = root / "governed-official-evidence-v1"
    manifest = governed / "official_document_acquisition_manifest.json"
    if manifest.is_file():
        for record in json.loads(manifest.read_text(encoding="utf-8")).get("records", []):
            item = dict(record)
            item["_path"] = governed / str(item["relative_path"])
            result[str(item["sha256"])] = item
    cohort = root / "approved-issuer-ir-official-financial-evidence-cohort-v1-20260827" / "artifact.json"
    if cohort.is_file():
        for record in json.loads(cohort.read_text(encoding="utf-8")).get("documents", []):
            item = dict(record)
            item["document_class"] = "audited_annual_financial_statements"
            item["canonical_url"] = item.get("official_url")
            item["observed_at"] = item.get("retrieved_at")
            item["_path"] = cohort.parent / str(item["relative_path"])
            result[str(item["sha256"])] = item
    return result


def _text_status(path: Path) -> tuple[int | None, str]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        # A source labelled needs_ocr remains image-only by its retained acquisition
        # disposition.  Otherwise a bounded first/last-page check is sufficient for
        # eligibility; full native text is rechecked by the extractor before facts.
        probes = sorted({0, len(reader.pages) // 2, len(reader.pages) - 1})
        return len(reader.pages), "TEXT_AVAILABLE" if any((reader.pages[i].extract_text() or "").strip() for i in probes) else "TEXT_NOT_DETECTED_BOUNDARY"
    except Exception:
        return None, "PDF_UNREADABLE"


def _path_classification(paths: Sequence[Path]) -> str:
    names = " ".join(str(path).casefold() for path in paths)
    if any(term in names for term in NON_FINANCIAL_PATH_TERMS):
        return "NOT_FINANCIAL_STATEMENT"
    if any(term in names for term in ("financial_statements", "annual_report", "annual-financial", "official-evidence")):
        return "METADATA_INSUFFICIENT"
    return "OTHER_EXPLICIT_REASON"


def _layout(entity_type: str, state: str) -> str:
    if state == "IMAGE_ONLY":
        return "SCANNED_IMAGE_ONLY"
    if entity_type == "bank":
        return "BANK_STATEMENT"
    if entity_type == "securities":
        return "SECURITIES_COMPANY_STATEMENT"
    return "GENERAL_CORPORATE_STANDARD" if entity_type == "corporate" else "OTHER_STRUCTURED_TEXT"


def build_artifact(*, operations_root: Path, entity_type_by_ticker: Mapping[str, str] = {}, replay_hashes: Sequence[str] | None = None) -> dict[str, Any]:
    """Create a complete SHA-deduplicated retained-PDF inventory and replay ledger."""
    sources = discover_pdf_bytes(operations_root)
    manifest = _manifest_documents(operations_root)
    inventory: list[dict[str, Any]] = []
    targets: list[tuple[dict[str, Any], Path]] = []
    for digest, paths in sorted(sources.items()):
        record = manifest.get(digest)
        page_count, text_status = _text_status(paths[0])
        if record:
            document_class = str(record.get("document_class") or "unknown")
            if document_class not in FINANCIAL_CLASSES:
                state = "NOT_FINANCIAL_STATEMENT"
            elif str(record.get("extraction_status")) == "needs_ocr" or text_status == "TEXT_NOT_DETECTED_BOUNDARY":
                state = "IMAGE_ONLY"
            elif text_status == "TEXT_AVAILABLE":
                state = "ELIGIBLE_NATIVE_TEXT"
            else:
                state = "METADATA_INSUFFICIENT"
            ticker = str(record.get("ticker") or "").upper() or None
        else:
            state = _path_classification(paths)
            document_class, ticker = None, None
        entity_type = str(entity_type_by_ticker.get(ticker or "", "unknown"))
        public_record = {key: value for key, value in (record or {}).items() if key != "_path"}
        item = {"document_sha256": digest, "provenance_paths": [str(p) for p in paths], "duplicate_path_count": len(paths) - 1,
                "ticker": ticker, "document_class": document_class, "page_count": page_count, "text_layer_status": text_status,
                "classification": state, "layout_family": _layout(entity_type, state), "source_metadata": public_record or None}
        inventory.append(item)
        if state == "ELIGIBLE_NATIVE_TEXT" and record and (replay_hashes is None or digest in set(replay_hashes)):
            doc = {"document_id": record["document_id"], "ticker": ticker, "sha256": digest,
                   "official_url": record.get("final_url") or record.get("canonical_url"),
                   "retrieved_at": record.get("observed_at"), "entity_type": entity_type}
            targets.append((doc, Path(record["_path"])))

    replays = []
    for document, path in targets:
        extracted = build_page_evidence_artifact(document=document, path=path)
        replays.append({"document_sha256": document["sha256"], "ticker": document["ticker"], "artifact_identity": extracted["artifact_identity"],
                        "pages_processed": extracted["page_count"], "statement_tables_found": len(extracted["tables"]),
                        "candidate_rows": len(extracted["fact_candidates"]), "qualified_facts": len(extracted["p3f13_panel_facts"]),
                        "blocked_candidates": extracted["blocked_candidates"], "artifact": extracted})
    states = Counter(row["classification"] for row in inventory)
    output = {"schema_version": VERSION, "inventory": inventory, "replays": replays,
              "coverage": {"unique_pdf_documents": len(inventory), "retained_pdf_paths": sum(len(v) for v in sources.values()),
                           "duplicate_paths": sum(len(v) - 1 for v in sources.values()), "classification_counts": dict(sorted(states.items())),
                           "inventory_residual": 0, "pdfs_processed": len(replays), "pages_processed": sum(r["pages_processed"] for r in replays),
                           "statement_tables_found": sum(r["statement_tables_found"] for r in replays), "candidate_rows": sum(r["candidate_rows"] for r in replays),
                           "qualified_facts": sum(r["qualified_facts"] for r in replays), "blocked_candidates": sum(len(r["blocked_candidates"]) for r in replays)},
              "authority": {"network_used": False, "ocr_used": False, "provider_used": False, "production_db_mutated": False,
                            "value_or_recommendation_activated": False}}
    output["artifact_sha256"] = _stable(output); output["artifact_identity"] = f"retained_official_financial_pdf_scaleout:{output['artifact_sha256']}"
    return output
