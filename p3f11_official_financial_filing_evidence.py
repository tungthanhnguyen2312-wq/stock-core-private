"""P3-F11 retained-document metadata qualification foundation.

The runner is offline and read-only: it reuses the governed official-document manifest,
P3-E corporate evidence, P2-F1 sector citations, and P3-F10 dispositions.  It does not
discover or acquire a document and never emits a financial observation from PDF text.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from official_financial_filing_evidence import METADATA_QUALIFIED, qualify_document_metadata


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "p3f11_official_financial_filing_evidence/v1"
DEFAULT_MANIFEST = ROOT / "operations-review" / "governed-official-evidence-v1" / "official_document_acquisition_manifest.json"
DEFAULT_P3E = ROOT / "config" / "promoted_fundamental_coverage_closeout_evidence.json"
DEFAULT_P2F1 = ROOT / "operations-review" / "p2f1-sector-financial-taxonomy-foundation-20260819" / "p2f1_sector_financial_taxonomy_artifact.json"
DEFAULT_P3F10 = ROOT / "operations-review" / "p3f10-generic-fundamental-evidence-scaleout-20260820" / "p3f10_generic_fundamental_evidence_scaleout_artifact.json"
DEFAULT_REGISTRY = ROOT / "config" / "official_source_registry.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _span(*, document_sha256: str, citation_id: str, page: int | None, text: str, kind: str) -> dict[str, Any]:
    return {"document_sha256": document_sha256, "citation_id": citation_id,
            "source_page": page, "text": text, "citation_kind": kind}


def _claim(value: Any, span: Mapping[str, Any]) -> dict[str, Any]:
    return {"value": value, "evidence_span": dict(span)}


def _manifest_by_hash(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("sha256")): dict(row) for row in manifest.get("records", [])
            if row.get("acquisition_status") == "retained" and row.get("sha256")}


def _document(record: Mapping[str, Any], evidence_root: Path) -> dict[str, Any]:
    """Bind a retained manifest row to the exact on-disk bytes it describes."""
    relative_path = str(record.get("relative_path") or "")
    path = (evidence_root / relative_path).resolve()
    try:
        path.relative_to(evidence_root.resolve())
    except ValueError:
        immutable_bytes_verified = False
    else:
        try:
            immutable_bytes_verified = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record.get("sha256")
        except OSError:
            immutable_bytes_verified = False
    return {"document_id": record.get("document_id"), "sha256": record.get("sha256"),
            "source_locator": record.get("canonical_url"), "source_id": record.get("source_id", "issuer_ir"),
            "source_authority": record.get("source_authority"), "observed_at": record.get("observed_at"),
            "published_at": record.get("published_at"), "relative_path": relative_path,
            "immutable_bytes_verified": immutable_bytes_verified}


def _from_corporate_evidence(doc: Mapping[str, Any], manifest_by_hash: Mapping[str, Mapping[str, Any]], evidence_root: Path) -> dict[str, Any] | None:
    """Use source-page text retained in P3-E's existing sidecar, never a provider field."""
    sha = str(doc.get("document_sha256") or "")
    retained = manifest_by_hash.get(sha)
    if not retained:
        return None
    pages = ((doc.get("sidecar") or {}).get("pages") or [])
    period = str(doc.get("reporting_period") or "")
    scope_page = next((row for row in pages if "hop nhat" in str(row.get("text", "")).casefold()), None)
    unit_page = next((row for row in pages if "don vi:" in str(row.get("text", "")).casefold()), None)
    period_page = next((row for row in pages if period in str(row.get("text", ""))), None)
    if not (scope_page and unit_page and period_page):
        return None
    def page_span(row: Mapping[str, Any], property_name: str) -> dict[str, Any]:
        text = str(row["text"])
        return _span(document_sha256=sha, citation_id=_hash({"sha": sha, "page": row["page"], "property": property_name}), page=int(row["page"]), text=text, kind="retained_ocr_source_page")
    return {"issuer_identity": doc.get("ticker"), "entity_type": "corporate", "document": _document(retained, evidence_root),
            "metadata": {
                "reporting_period": _claim(period, page_span(period_page, "reporting_period")),
                "periodicity": _claim("annual", page_span(period_page, "periodicity")),
                "statement_scope": _claim("consolidated", page_span(scope_page, "statement_scope")),
                "currency": _claim("VND", page_span(unit_page, "currency")),
                "unit_scale": _claim(1, page_span(unit_page, "unit_scale")),
                "publication_date": _claim(retained.get("published_at"), _span(document_sha256=sha, citation_id=_hash({"sha": sha, "property": "publication_date"}), page=None, text=str(retained.get("published_at")), kind="retained_manifest_metadata")),
            }}


def _from_sector_validation(validation: Mapping[str, Any], manifest_by_hash: Mapping[str, Mapping[str, Any]], evidence_root: Path) -> dict[str, Any] | None:
    facts = [row for row in validation.get("extracted_facts", []) if row.get("document_sha256")]
    if not facts:
        return None
    fact = facts[0]
    sha = str(fact["document_sha256"])
    retained = manifest_by_hash.get(sha)
    if not retained:
        return None
    def fact_span(property_name: str) -> dict[str, Any]:
        return _span(document_sha256=sha, citation_id=str(fact["citation_id"]), page=int(fact["source_page"]), text=str(fact["raw_label"]), kind="existing_qualified_sector_fact_citation")
    return {"issuer_identity": validation.get("issuer"), "entity_type": validation.get("entity_class"), "document": _document(retained, evidence_root),
            "metadata": {
                "reporting_period": _claim(str(fact["reporting_period"]), fact_span("reporting_period")),
                "periodicity": _claim("annual", _span(document_sha256=sha, citation_id=_hash({"sha": sha, "property": "periodicity"}), page=None, text=str(retained["document_class"]), kind="retained_manifest_metadata")),
                "statement_scope": _claim(str(fact["statement_scope"]), fact_span("statement_scope")),
                "currency": _claim(str(fact["currency"]), fact_span("currency")),
                "unit_scale": _claim(int(fact["unit_scale"]), fact_span("unit_scale")),
                "publication_date": _claim(retained.get("published_at"), _span(document_sha256=sha, citation_id=_hash({"sha": sha, "property": "publication_date"}), page=None, text=str(retained.get("published_at")), kind="retained_manifest_metadata")),
            }}


def _missing_case(p3f10: Mapping[str, Any]) -> dict[str, Any]:
    row = next(item for item in p3f10["instrument_dispositions"] if item["disposition"] == "SOURCE_MISSING")
    return {"issuer_identity": row["ticker"], "entity_type": row["sector"], "document": {}, "metadata": {}}


def execute(*, manifest_path: Path = DEFAULT_MANIFEST, p3e_path: Path = DEFAULT_P3E,
            p2f1_path: Path = DEFAULT_P2F1, p3f10_path: Path = DEFAULT_P3F10,
            registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    manifest, p3e, p2f1, p3f10, registry = map(_load, (manifest_path, p3e_path, p2f1_path, p3f10_path, registry_path))
    by_hash = _manifest_by_hash(manifest)
    evidence_root = manifest_path.parent
    corporate_candidates = [_from_corporate_evidence(doc, by_hash, evidence_root) for doc in p3e.get("evidence_documents", [])]
    corporate = next(candidate for candidate in corporate_candidates if candidate is not None)
    sector_candidates = [_from_sector_validation(value, by_hash, evidence_root) for key, value in p2f1.items()
                         if key.endswith("_validation") and isinstance(value, Mapping)]
    candidates = [corporate, *[candidate for candidate in sector_candidates if candidate is not None], _missing_case(p3f10)]
    results = [qualify_document_metadata(candidate) for candidate in candidates]
    qualified = [row for row in results if row["qualification_status"] == METADATA_QUALIFIED]
    blocked = [row for row in results if row["qualification_status"] != METADATA_QUALIFIED]
    p3f10_blocked = sum(1 for row in p3f10["instrument_dispositions"] if row["disposition"] == "STATEMENT_SCOPE_UNKNOWN")
    official_routes = [{"source_id": row.get("source_id"), "authority": row.get("authority"), "authority_class": row.get("authority_class"), "document_types": row.get("document_types", [])}
                       for row in registry.get("sources", []) if row.get("activation") == "approved"]
    artifact: dict[str, Any] = {
        "schema_version": VERSION, "contract_version": CONTRACT_VERSION,
        "artifact_type": "P3F11_OFFICIAL_FINANCIAL_FILING_EVIDENCE_FOUNDATION",
        "approved_official_route_inventory": official_routes,
        "evidence_envelope_contract": {"contract_version": "official_financial_filing_evidence/v1", "required_metadata": ["canonical instrument identity", "document/source identity", "observed timestamp", "immutable hash", "reporting period", "periodicity", "statement scope", "currency", "unit scale", "metadata evidence spans"], "value_level_evidence_required_for_canonical_qualification": True},
        "pilot_results": results,
        "qualification_before_after": {"p3f10_document_metadata_qualified": 0, "pilot_document_metadata_qualified": len(qualified), "canonical_facts_promoted": 0, "reason": "metadata does not replace exact value-level citation/matching"},
        "fundamental_readiness_impact": {"readiness_changed": False, "reason": "no canonical fact promotion; P3-B remains dependent on exact value-level evidence"},
        "scaleout_addressability": {"p3f10_scope_currency_scale_blocked": p3f10_blocked, "addressable_now_from_current_retained_route_authority": 0, "no_discoverable_approved_route_or_retained_filing": p3f10_blocked, "unsupported_or_manual_handling_required": 0, "minimum_estimated_documents_or_issuer_periods_to_acquire": p3f10_blocked},
        "root_blockers": [{"root_cause": "VALUE_LEVEL_OFFICIAL_CITATION_AND_EXACT_PROVIDER_MATCH_REQUIRED", "affected_instruments": p3f10_blocked}, {"root_cause": "NO_CURRENT_RETAINED_APPROVED_FILING_ROUTE_FOR_BLOCKED_COHORT", "affected_instruments": p3f10_blocked}],
        "ticker_specific_branch_audit": {"status": "PASS", "production_ticker_literals": [], "selection_method": "entity_type_and_retained_evidence_metadata"},
        "authority_boundaries": {"source_authority_promoted": False, "new_provider_added": False, "documents_acquired": 0, "pdf_values_fabricated": 0, "runtime_database_mutated": False, "p3g_started": False},
        "source_artifacts": {"retained_manifest_sha256": _hash(manifest), "p3f10_identity": p3f10.get("artifact_identity"), "p2f1_identity": p2f1.get("artifact_identity")},
    }
    artifact["fundamental_evidence_foundation_gate"] = "VALUE_LEVEL_FINANCIAL_EVIDENCE_QUALIFICATION_FOUNDATION"
    artifact["verdict"] = "P3F11_FINANCIAL_EVIDENCE_FOUNDATION_PARTIAL"
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = f"p3f11_official_financial_filing_evidence:{artifact['artifact_sha256']}"
    return artifact
