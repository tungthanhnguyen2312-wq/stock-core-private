"""P3-C: bounded comparative financial evidence scale-out closeout contract."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from field_temporal_contract import stable_id
from fundamental_research_readiness import build_fundamental_research_artifact
from multi_period_financial_panel import (
    build_multi_period_financial_panel,
    load_all_authoritative_citations,
    load_promoted_comparative_financial_citations,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "p3c_comparative_financial_evidence/v1"
ARTIFACT_TYPE = "P3C_COMPARATIVE_FINANCIAL_EVIDENCE_SCALEOUT"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _counts(items: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key) or "UNSPECIFIED") for item in items).items()))


def build_starting_gap_inventory(p3b_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze the P3-B work queue from its immutable closeout identity."""
    rows = sorted(
        (dict(row) for row in p3b_artifact.get("data_gap_matrix", []) if isinstance(row, Mapping)),
        key=lambda row: (str(row.get("missing_or_blocked_reason")), str(row.get("ticker")), str(row.get("metric_id")), tuple(row.get("periods_used") or [])),
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "P3C_FROZEN_STARTING_GAP_INVENTORY",
        "frozen_from_artifact_identity": p3b_artifact.get("artifact_identity"),
        "frozen_from_artifact_sha256": p3b_artifact.get("artifact_sha256"),
        "cohort": p3b_artifact.get("cohort_identity", {}).get("issuers", []),
        "gap_count": len(rows),
        "gap_counts_by_reason": _counts(rows, "missing_or_blocked_reason"),
        "gaps": rows,
    }
    payload["inventory_sha256"] = stable_id(payload)
    return payload


def verify_retained_document_bytes(repo_root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Verify local immutable bytes against the manifest before any promotion is reported."""
    results: list[dict[str, Any]] = []
    for doc in manifest.get("evidence_documents", []):
        relative_path = Path(str(doc["archive_document_path"]))
        path = repo_root / relative_path
        if not path.is_file():
            raise ValueError(f"Required retained P3-C document is absent: {relative_path}")
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha != doc.get("document_sha256"):
            raise ValueError(f"Retained P3-C document hash mismatch: {relative_path}")
        results.append({
            "ticker": doc["ticker"], "reporting_period": doc["reporting_period"],
            "archive_document_path": str(relative_path).replace("\\", "/"),
            "document_sha256": actual_sha, "byte_count": path.stat().st_size,
            "integrity_status": "SHA256_VERIFIED",
        })
    return results


def _proxy_to_exact(before: Mapping[str, Any], after: Mapping[str, Any], promoted_tickers: set[str]) -> list[dict[str, Any]]:
    before_issuers = {row["issuer_identity"]["ticker"]: row for row in before.get("issuer_research_readiness", [])}
    upgrades: list[dict[str, Any]] = []
    for after_issuer in after.get("issuer_research_readiness", []):
        ticker = after_issuer["issuer_identity"]["ticker"]
        if ticker not in promoted_tickers:
            continue
        before_issuer = before_issuers.get(ticker, {})
        before_metrics = before_issuer.get("metrics", [])
        for after_metric in after_issuer.get("metrics", []):
            if after_metric.get("status") != "EXACT_QUALIFIED":
                continue
            for period in after_metric.get("periods_used", []):
                prior = next((metric for metric in before_metrics if metric.get("metric_id") == after_metric.get("metric_id") and period in metric.get("periods_used", []) and metric.get("status") == "DERIVED_PROXY"), None)
                if prior:
                    upgrades.append({
                        "ticker": ticker, "metric_id": after_metric["metric_id"], "period": period,
                        "before_status": "DERIVED_PROXY", "after_status": "EXACT_QUALIFIED",
                        "before_method": prior.get("method"), "after_method": after_metric.get("method"),
                    })
    return sorted(upgrades, key=lambda row: (row["ticker"], row["metric_id"], row["period"]))


def build_p3c_closeout(
    *,
    repo_root: Path,
    p2_artifact: Mapping[str, Any],
    p3b_before: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild the P2 cohort and rerun P3-B after bounded fact promotion."""
    frozen_inventory = build_starting_gap_inventory(p3b_before)
    retained_integrity = verify_retained_document_bytes(repo_root, manifest)
    p3c_citations = load_promoted_comparative_financial_citations(repo_root)
    source_panel = p2_artifact["panel_data"]
    refreshed_panel = build_multi_period_financial_panel(
        issuers=source_panel["issuers_represented"],
        citations=load_all_authoritative_citations(repo_root),
        reference_at=source_panel.get("reference_at"),
        generated_at="2026-08-20T05:30:00.000000+00:00",
    )
    p3b_after = build_fundamental_research_artifact(refreshed_panel)
    after_gap = sorted(p3b_after["data_gap_matrix"], key=lambda row: (row["missing_or_blocked_reason"], row["ticker"], row["metric_id"], row["periods_used"]))
    new_facts = [
        {key: citation.get(key) for key in (
            "ticker", "metric", "reporting_period", "value", "currency", "unit_scale", "statement_scope",
            "audit_status", "source_locator", "archive_document_path", "document_sha256", "source_page", "citation_id",
        )}
        for citation in p3c_citations
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3C_COMPARATIVE_EVIDENCE_SCALEOUT_PARTIAL",
        "source_artifacts": {
            "p2_closeout_identity": p2_artifact.get("artifact_identity"),
            "p3b_before_identity": p3b_before.get("artifact_identity"),
        },
        "starting_gap_inventory": frozen_inventory,
        "evidence_acquisition": {
            "retained_document_integrity": retained_integrity,
            "acquired_qualified_issuer_periods": [{"ticker": "SSI", "reporting_period": "2023", "statement_scope": "consolidated", "status": "ACQUIRED_AND_QUALIFIED"}],
            "blocked_issuer_periods": manifest.get("blocked_acquisition_attempts", []),
        },
        "newly_qualified_facts": new_facts,
        "panel_coverage_before_after": {
            "before": {key: source_panel.get(key) for key in ("qualified_facts_count", "missing_facts_count", "not_applicable_facts_count", "conflict_facts_count", "total_facts_evaluated")},
            "after": {key: refreshed_panel.get(key) for key in ("qualified_facts_count", "missing_facts_count", "not_applicable_facts_count", "conflict_facts_count", "total_facts_evaluated")},
            "refreshed_panel_identity": refreshed_panel["artifact_id"],
            "refreshed_panel_content_hash": refreshed_panel["content_hash"],
        },
        "fundamental_readiness_before_after": {
            "before": p3b_before["coverage_summary"],
            "after": p3b_after["coverage_summary"],
            "refreshed_p3b_identity": p3b_after["artifact_identity"],
            "refreshed_p3b_artifact_sha256": p3b_after["artifact_sha256"],
        },
        "proxy_to_exact_upgrades": _proxy_to_exact(p3b_before, p3b_after, {str(citation["ticker"]) for citation in p3c_citations}),
        "remaining_data_gaps": {
            "gap_count": len(after_gap),
            "gap_counts_by_reason": _counts(after_gap, "missing_or_blocked_reason"),
            "gaps": after_gap,
        },
        "sector_and_authority_boundaries": {
            "no_new_issuers": True,
            "annual_consolidated_only": True,
            "corporate_debt_semantics_for_intermediaries": "NOT_APPLICABLE",
            "capex_boundary": manifest.get("capex_boundary"),
            "price_liquidity_valuation_execution_authority": "UNCHANGED_AND_NOT_GRANTED",
        },
        "refreshed_panel_data": refreshed_panel,
        "refreshed_fundamental_readiness": p3b_after,
    }
    payload["artifact_sha256"] = stable_id(payload)
    payload["artifact_identity"] = f"p3c_comparative_financial_evidence:{payload['artifact_sha256']}"
    return payload
