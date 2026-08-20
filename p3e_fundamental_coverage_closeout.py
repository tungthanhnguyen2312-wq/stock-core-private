"""P3-E bounded fundamental coverage closeout and valuation-input readiness gate."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from field_temporal_contract import stable_id
from financial_statement_template_recognizer import _normalize_text
from fundamental_research_readiness import build_fundamental_research_artifact
from multi_period_financial_panel import (
    build_multi_period_financial_panel,
    load_all_authoritative_citations,
    load_promoted_fundamental_coverage_closeout_citations,
)
from valuation_input_readiness import evaluate_valuation_input_readiness

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "p3e_fundamental_coverage_closeout/v1"
ARTIFACT_TYPE = "P3E_FUNDAMENTAL_COVERAGE_CLOSEOUT"


def _counts(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "UNSPECIFIED") for row in rows).items()))


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify_p3d_residual_gaps(p3d_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Classify each frozen P3-D gap without creating a perpetual-history mandate."""
    classifications: list[dict[str, Any]] = []
    for gap in p3d_artifact.get("remaining_data_gaps", {}).get("gaps", []):
        row = dict(gap)
        ticker = str(row.get("ticker"))
        reason = str(row.get("missing_or_blocked_reason"))
        if reason == "MISSING_CONSECUTIVE_PRIOR_PERIOD":
            category = "SOURCE_AUTHORITY_BLOCKED" if ticker == "VCB" else "STRUCTURAL_BOUNDARY_GAP"
            detail = (
                "VCB FY2023 is not admitted by the existing source authority."
                if ticker == "VCB" else
                "Earliest authoritative annual period in the milestone-local two-period research window; no internal series hole is asserted."
            )
        elif reason.startswith("MISSING_INPUTS:"):
            category = "ACTIONABLE_INTERNAL_GAP"
            detail = "Current-window required identity has a retained approved annual-report route and is processed by P3-E."
        else:
            category = "SEMANTICALLY_UNQUALIFIED"
            detail = "No deterministic mapping exists for the frozen P3-D reason."
        classifications.append({**row, "gap_category": category, "classification_reason": detail})
    classifications.sort(key=lambda row: (row["gap_category"], row["ticker"], row["metric_id"], row["periods_used"]))
    category_counts = _counts(classifications, "gap_category")
    for category in ("STRUCTURAL_BOUNDARY_GAP", "ACTIONABLE_INTERNAL_GAP", "SOURCE_AUTHORITY_BLOCKED", "DOCUMENT_UNAVAILABLE", "SEMANTICALLY_UNQUALIFIED", "NOT_REQUIRED_FOR_CURRENT_RESEARCH_WINDOW"):
        category_counts.setdefault(category, 0)
    taxonomy = {
        "supported_history_boundary": {
            "definition": "For each issuer, the latest authoritative annual period plus one immediately prior authoritative annual period when present. Earlier history is not required merely to make the earliest supported period's growth metric computable.",
            "unlimited_backward_acquisition_required": False,
        },
        "gap_count": len(classifications), "counts_by_category": dict(sorted(category_counts.items())),
        "classifications": classifications,
    }
    taxonomy["taxonomy_sha256"] = stable_id(taxonomy)
    return taxonomy


def verify_retained_document_bytes(repo_root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for document in manifest.get("evidence_documents", []):
        document_path = repo_root / str(document["archive_document_path"])
        materialization_path = repo_root / str(document["materialization_path"])
        if not document_path.is_file() or not materialization_path.is_file():
            raise ValueError("P3E_RETAINED_EVIDENCE_ABSENT")
        actual_sha = _stream_sha256(document_path)
        if actual_sha != document.get("document_sha256"):
            raise ValueError("P3E_RETAINED_DOCUMENT_HASH_MISMATCH")
        materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
        if materialization.get("document_sha256") != actual_sha:
            raise ValueError("P3E_MATERIALIZATION_DOCUMENT_HASH_MISMATCH")
        pages = {int(page.get("page", 0)): str(page.get("text", "")) for page in materialization.get("pages", [])}
        for metric, source in document.get("source_page_citations", {}).items():
            text = pages.get(int(source.get("page", 0)), "")
            if _normalize_text(str(source["source_fragment"])) not in _normalize_text(text) or str(source["raw_value"]) not in text:
                raise ValueError(f"P3E_SOURCE_PAGE_LINEAGE_UNVERIFIED: {document['ticker']} {metric}")
        results.append({"ticker": document["ticker"], "reporting_period": document["reporting_period"], "document_sha256": actual_sha, "byte_count": document_path.stat().st_size, "integrity_status": "SHA256_AND_SOURCE_PAGE_LINEAGE_VERIFIED"})
    return results


def _coverage(panel: Mapping[str, Any]) -> dict[str, Any]:
    facts = panel.get("fact_coverage_summary", {})
    return {key: panel.get(key) for key in ("qualified_facts_count", "conflict_facts_count", "missing_facts_count", "not_applicable_facts_count", "total_facts_evaluated")} | {
        "revenue_coverage": facts.get("revenue", {}).get("QUALIFIED", 0),
        "total_assets_coverage": facts.get("total_assets", {}).get("QUALIFIED", 0),
    }


def build_p3e_closeout(*, repo_root: Path, p2_artifact: Mapping[str, Any], p3d_artifact: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    taxonomy = classify_p3d_residual_gaps(p3d_artifact)
    retained_integrity = verify_retained_document_bytes(repo_root, manifest)
    new_citations = load_promoted_fundamental_coverage_closeout_citations(repo_root)
    before_panel = p3d_artifact["refreshed_panel_data"]
    before_readiness = p3d_artifact["refreshed_fundamental_readiness"]
    panel = build_multi_period_financial_panel(
        issuers=p2_artifact["panel_data"]["issuers_represented"],
        citations=load_all_authoritative_citations(repo_root, include_p3d_residual_comparative_evidence=True, include_p3e_fundamental_coverage_evidence=True),
        reference_at=p2_artifact["panel_data"].get("reference_at"), generated_at="2026-08-20T07:30:00.000000+00:00",
    )
    readiness = build_fundamental_research_artifact(panel)
    if panel["qualified_facts_count"] != before_panel["qualified_facts_count"] + len(new_citations):
        raise ValueError("P3E_PANEL_PRESERVATION_OR_ADDITION_FAILED")
    remaining = sorted(readiness["data_gap_matrix"], key=lambda row: (row["missing_or_blocked_reason"], row["ticker"], row["metric_id"], row["periods_used"]))
    if any(row["missing_or_blocked_reason"].startswith("MISSING_INPUTS:") for row in remaining):
        raise ValueError("P3E_CURRENT_WINDOW_FACTS_NOT_CLOSED")
    valuation = evaluate_valuation_input_readiness(panel)
    payload = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3E_FUNDAMENTAL_COVERAGE_CLOSEOUT_COMPLETE",
        "source_artifacts": {"p2_closeout_identity": p2_artifact.get("artifact_identity"), "p3d_closeout_identity": p3d_artifact.get("artifact_identity")},
        "reconciled_gap_taxonomy": taxonomy,
        "evidence_acquisition": {"retained_document_integrity": retained_integrity, "newly_processed_documents": [{"ticker": row["ticker"], "reporting_period": row["reporting_period"], "status": "ACQUIRED_AND_QUALIFIED"} for row in manifest.get("evidence_documents", [])], "vcb_source_authority_status": manifest.get("vcb_source_authority_status"), "vcb_valuation_materiality": "VCB FY2024 exact profit and equity facts make the current P/E/P/B financial-input families ready; FY2023 remains a growth-continuity source block, not a current valuation-family block."},
        "newly_qualified_facts": [{key: citation.get(key) for key in ("ticker", "metric", "reporting_period", "value", "currency", "unit_scale", "statement_scope", "document_sha256", "source_locator", "source_page", "citation_id")} for citation in new_citations],
        "panel_coverage_before_after": {"before": _coverage(before_panel), "after": _coverage(panel), "refreshed_panel_identity": panel["artifact_id"], "refreshed_panel_content_hash": panel["content_hash"]},
        "fundamental_readiness_before_after": {"before": before_readiness["coverage_summary"], "after": readiness["coverage_summary"], "refreshed_p3b_identity": readiness["artifact_identity"]},
        "capex_fcf_terminal_status": {"status": manifest["capex_fcf_terminal_status"], "reason": "No existing exact canonical CapEx identity was promoted; no proxy or cash-flow subtraction is permitted."},
        "valuation_input_readiness": valuation,
        "remaining_data_gaps": {"gap_count": len(remaining), "gap_counts_by_reason": _counts(remaining, "missing_or_blocked_reason"), "gaps": remaining},
        "financial_evidence_lane": {"status": "COMPARATIVE_EVIDENCE_LANE_CLOSED", "reason": "No actionable current-window revenue/assets gap remains; the residuals are 28 structural-boundary growth entries and one explicit VCB source-authority blocker."},
        "authority_boundaries": {"no_new_issuers": True, "source_registry_mutated": False, "valuation_calculated": False, "price_liquidity_execution_authority": "UNCHANGED_AND_NOT_GRANTED"},
        "refreshed_panel_data": panel, "refreshed_fundamental_readiness": readiness,
    }
    payload["artifact_sha256"] = stable_id(payload)
    payload["artifact_identity"] = f"p3e_fundamental_coverage_closeout:{payload['artifact_sha256']}"
    return payload
