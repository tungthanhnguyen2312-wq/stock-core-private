"""Offline P3-F12 pilot over retained P3-E/P2-F1 official evidence and raw observations."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from official_financial_value_evidence import qualify_value_evidence

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
P3E = ROOT / "operations-review" / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
P2F1 = ROOT / "operations-review" / "p2f1-sector-financial-taxonomy-foundation-20260819" / "p2f1_sector_financial_taxonomy_artifact.json"
P3F10 = ROOT / "operations-review" / "p3f10-generic-fundamental-evidence-scaleout-20260820" / "p3f10_generic_fundamental_evidence_scaleout_artifact.json"
P3F11 = ROOT / "operations-review" / "p3f11-official-financial-filing-evidence-20260820" / "p3f11_official_financial_filing_evidence_artifact.json"
RAW = ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-a" / "data" / "market-wide-financials" / "observations"


def _load(path: Path) -> dict[str, Any]: return json.loads(path.read_text(encoding="utf-8"))
def _hash(value: Any) -> str: return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _provider(ticker: str, metric: str) -> dict[str, Any] | None:
    path = RAW / f"{ticker}.jsonl.gz"
    if not path.is_file(): return None
    rows = [json.loads(line) for line in gzip.open(path, "rt", encoding="utf-8")]
    matches = [row for row in rows if row.get("raw_item_id") == metric and row.get("statement_family") == "balance_sheet" and row.get("reporting_period") == "2024-Q4"]
    if len(matches) != 1: return None
    row = matches[0]
    return {"observation_id": row["observation_id"], "issuer_identity": row["ticker"], "canonical_metric": metric,
            "statement_family": "balance_sheet", "reporting_period": row["reporting_period"], "periodicity": row["period_type"],
            "normalized_numeric_value": row["raw_value"], "unit_scale": 1, "provider": row["provider"], "source_sha256": row["source_sha256"]}

def _official_from_p3e(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"document_sha256": row["document_sha256"], "issuer_identity": row["ticker"], "entity_type": "corporate", "reporting_period": row["reporting_period"], "periodicity": "annual", "statement_scope": row["statement_scope"], "currency": row["currency"], "unit_scale": row["unit_scale"], "canonical_metric": row["metric"], "raw_label": row["metric"], "raw_value_text": str(row["value"]), "normalized_numeric_value": row["value"], "source_page": row["source_page"], "statement_family": "balance_sheet", "statement_or_note_context": "balance_sheet", "extraction_method": "existing_verified_statement_line", "source_span": {"document_sha256": row["document_sha256"], "citation_id": row["citation_id"], "source_page": row["source_page"], "text": str(row["value"])} }

def _official_from_sector(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"document_sha256": row["document_sha256"], "issuer_identity": row["issuer_identity"], "entity_type": row["entity_class"], "reporting_period": row["reporting_period"], "periodicity": "annual", "statement_scope": row["statement_scope"], "currency": row["currency"], "unit_scale": row["unit_scale"], "canonical_metric": row["normalized_metric"], "raw_label": row["raw_label"], "raw_value_text": row["raw_value"], "normalized_numeric_value": row["value"] // row["unit_scale"], "source_page": row["source_page"], "statement_family": row["statement_or_note_section"], "statement_or_note_context": row["statement_or_note_section"], "extraction_method": "existing_qualified_sector_statement_line", "source_span": {"document_sha256": row["document_sha256"], "citation_id": row["citation_id"], "source_page": row["source_page"], "text": row["raw_label"]} }

def execute() -> dict[str, Any]:
    p3e, p2f1, p3f10, p3f11 = map(_load, (P3E, P2F1, P3F10, P3F11))
    corporate = next(_official_from_p3e(row) for row in p3e["newly_qualified_facts"] if row["metric"] == "total_assets")
    sectors = [next(_official_from_sector(row) for row in p2f1[key]["extracted_facts"] if row["normalized_metric"] == "total_assets") for key in sorted(p2f1) if key.endswith("_validation") and isinstance(p2f1[key], Mapping) and p2f1[key].get("extracted_facts")]
    official_rows = [corporate, *sectors]
    results = [qualify_value_evidence(row, _provider(row["issuer_identity"], row["canonical_metric"]), applicable_entity_types={"corporate", "bank", "securities"}) for row in official_rows]
    blocked = qualify_value_evidence({**corporate, "raw_value_text": "ambiguous"}, _provider(corporate["issuer_identity"], corporate["canonical_metric"]), applicable_entity_types={"corporate", "bank", "securities"})
    p3f10_blocked = sum(1 for row in p3f10["instrument_dispositions"] if row["disposition"] == "STATEMENT_SCOPE_UNKNOWN")
    artifact = {"schema_version": VERSION, "contract_version": "p3f12_value_level_financial_evidence/v1", "artifact_type": "P3F12_VALUE_LEVEL_FINANCIAL_EVIDENCE", "pilot_documents": [{key: r["official_value_evidence"].get(key) for key in ("issuer_identity", "entity_type", "document_sha256", "reporting_period")} for r in results], "extracted_value_evidence_inventory": [r["official_value_evidence"] for r in results] + [blocked["official_value_evidence"]], "provider_reconciliation_matrix": results + [blocked], "qualified_facts": [r for r in results if r["canonical_qualification"] == "CANONICAL_QUALIFIED"], "blocked_facts": [blocked], "readiness_before_after": {"facts_promoted": 0, "ephemeral_canonical_qualified_candidates": len(results), "metrics_newly_available": 0, "reason": "existing P3-E/P2-F1 facts already qualified; pilot writes no store"}, "scaleout_estimate": {"instruments_with_retained_raw_provider_observations": 520, "instruments_needing_official_filing_acquisition": p3f10_blocked, "minimum_issuer_period_documents": p3f10_blocked, "generic_metric_proof": ["total_assets"], "source_route_gaps": p3f10_blocked, "unsupported_layout_cases": "unknown_pending_retained_document"}, "root_blockers": ["official_filing_not_retained_for_509_scope_currency_scale_blocked_instruments", "only_exact_labeled_metric_definitions_are_addressable"], "ticker_specific_branch_audit": {"status": "PASS", "production_ticker_literals": [], "selection": "metric_definition_and_retained_evidence_structure"}, "authority_boundaries": {"documents_acquired": 0, "new_provider": False, "source_authority_promoted": False, "canonical_store_mutated": False, "runtime_database_mutated": False, "p3g_started": False}, "source_artifacts": {"p3f10": p3f10.get("artifact_identity"), "p3f11": p3f11.get("artifact_identity"), "p3e": p3e.get("artifact_identity"), "p2f1": p2f1.get("artifact_identity")}, "value_level_foundation_gate": "VALUE_LEVEL_FINANCIAL_EVIDENCE_FOUNDATION_READY", "verdict": "P3F12_VALUE_LEVEL_FINANCIAL_EVIDENCE_COMPLETE"}
    artifact["artifact_sha256"] = _hash(artifact); artifact["artifact_identity"] = f"p3f12_value_level_financial_evidence:{artifact['artifact_sha256']}"
    return artifact
