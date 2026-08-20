"""P3-D: residual comparative financial evidence scale-out and gap reconciliation."""
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
    load_promoted_residual_comparative_financial_citations,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "p3d_residual_comparative_financial_evidence/v1"
ARTIFACT_TYPE = "P3D_RESIDUAL_COMPARATIVE_FINANCIAL_EVIDENCE_SCALEOUT"


def _counts(items: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key) or "UNSPECIFIED") for item in items).items()))


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_reconciled_residual_gap_inventory(p3c_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze P3-D's queue and record why P3-C's 55 gaps remained correct."""
    gaps = sorted(
        (dict(row) for row in p3c_artifact.get("remaining_data_gaps", {}).get("gaps", []) if isinstance(row, Mapping)),
        key=lambda row: (
            str(row.get("missing_or_blocked_reason")), str(row.get("ticker")),
            str(row.get("metric_id")), tuple(row.get("periods_used") or []),
        ),
    )
    ssi_2023 = [row for row in gaps if row.get("ticker") == "SSI" and row.get("metric_id") == "earnings_growth_yoy" and row.get("periods_used") == ["2023"]]
    ssi_2024 = [row for row in gaps if row.get("ticker") == "SSI" and row.get("metric_id") == "earnings_growth_yoy" and row.get("periods_used") == ["2024"]]
    if len(gaps) != 55 or len(ssi_2023) != 1 or ssi_2024:
        raise ValueError("P3D_GAP_RECONCILIATION_FAILED: residual inventory is not the expected P3-C recomputation")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "P3D_RECONCILED_STARTING_RESIDUAL_GAP_INVENTORY",
        "frozen_from_artifact_identity": p3c_artifact.get("artifact_identity"),
        "frozen_from_artifact_sha256": p3c_artifact.get("artifact_sha256"),
        "gap_count": len(gaps),
        "gap_counts_by_reason": _counts(gaps, "missing_or_blocked_reason"),
        "reconciliation": {
            "status": "CORRECT_BY_DEFINITION",
            "explanation": "P3-C's newly qualified SSI FY2023 profit resolves the FY2024 earnings-growth comparison, while FY2023 becomes the first observed annual period and therefore has its own required missing FY2022 comparator. The recomputed count stays 55 without a derivation defect.",
            "ssi_resolved_gap": {"ticker": "SSI", "metric_id": "earnings_growth_yoy", "period": "2024"},
            "ssi_new_structural_gap": ssi_2023[0],
        },
        "gaps": gaps,
    }
    payload["inventory_sha256"] = stable_id(payload)
    return payload


def verify_retained_document_bytes(repo_root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Verify immutable document bytes and original page-text lineage before promotion."""
    results: list[dict[str, Any]] = []
    for document in manifest.get("evidence_documents", []):
        document_path = repo_root / str(document["archive_document_path"])
        materialization_path = repo_root / str(document["materialization_path"])
        if not document_path.is_file() or not materialization_path.is_file():
            raise ValueError("P3D_RETAINED_EVIDENCE_ABSENT")
        actual_sha = _stream_sha256(document_path)
        if actual_sha != document.get("document_sha256"):
            raise ValueError("P3D_RETAINED_DOCUMENT_HASH_MISMATCH")
        materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
        if materialization.get("document_sha256") != actual_sha:
            raise ValueError("P3D_MATERIALIZATION_DOCUMENT_HASH_MISMATCH")
        pages = {int(page.get("page", 0)): str(page.get("text", "")) for page in materialization.get("pages", [])}
        for metric, source in document.get("source_page_citations", {}).items():
            page_text = pages.get(int(source.get("page", 0)), "")
            if _normalize_text(str(source.get("source_fragment"))) not in _normalize_text(page_text) or str(source.get("raw_value")) not in page_text:
                raise ValueError(f"P3D_SOURCE_PAGE_LINEAGE_UNVERIFIED: {document['ticker']} {metric}")
        results.append({
            "ticker": document["ticker"], "reporting_period": document["reporting_period"],
            "archive_document_path": str(document["archive_document_path"]).replace("\\", "/"),
            "materialization_path": str(document["materialization_path"]).replace("\\", "/"),
            "document_sha256": actual_sha, "byte_count": document_path.stat().st_size,
            "integrity_status": "SHA256_AND_SOURCE_PAGE_LINEAGE_VERIFIED",
        })
    return results


def _proxy_to_exact(before: Mapping[str, Any], after: Mapping[str, Any], tickers: set[str]) -> list[dict[str, Any]]:
    before_issuers = {row["issuer_identity"]["ticker"]: row for row in before.get("issuer_research_readiness", [])}
    upgrades: list[dict[str, Any]] = []
    for after_issuer in after.get("issuer_research_readiness", []):
        ticker = after_issuer["issuer_identity"]["ticker"]
        if ticker not in tickers:
            continue
        before_metrics = before_issuers.get(ticker, {}).get("metrics", [])
        for after_metric in after_issuer.get("metrics", []):
            if after_metric.get("status") != "EXACT_QUALIFIED":
                continue
            for period in after_metric.get("periods_used", []):
                prior = next((item for item in before_metrics if item.get("metric_id") == after_metric.get("metric_id") and period in item.get("periods_used", []) and item.get("status") == "DERIVED_PROXY"), None)
                if prior:
                    upgrades.append({
                        "ticker": ticker, "metric_id": after_metric["metric_id"], "period": period,
                        "before_status": "DERIVED_PROXY", "after_status": "EXACT_QUALIFIED",
                        "before_method": prior.get("method"), "after_method": after_metric.get("method"),
                    })
    return sorted(upgrades, key=lambda item: (item["ticker"], item["metric_id"], item["period"]))


def _panel_coverage(panel: Mapping[str, Any]) -> dict[str, Any]:
    summary = panel.get("fact_coverage_summary", {})
    issuer_periods = {
        str(issuer.get("issuer_identity", {}).get("ticker")): list(issuer.get("periods_covered", []))
        for issuer in panel.get("issuers", [])
    }
    consecutive_annual_pairs = sum(
        sum(1 for prior, current in zip(years, years[1:]) if current == prior + 1)
        for periods in issuer_periods.values()
        for years in [sorted({int(period) for period in periods if str(period).isdigit()})]
    )
    return {
        **{key: panel.get(key) for key in ("qualified_facts_count", "missing_facts_count", "not_applicable_facts_count", "conflict_facts_count", "total_facts_evaluated")},
        "issuer_period_coverage": issuer_periods,
        "consecutive_annual_pairs": consecutive_annual_pairs,
        "revenue_coverage": summary.get("revenue", {}).get("QUALIFIED", 0),
        "total_assets_coverage": summary.get("total_assets", {}).get("QUALIFIED", 0),
        "assets_equity_denominator_coverage": {
            "total_assets": summary.get("total_assets", {}).get("QUALIFIED", 0),
            "shareholders_equity": summary.get("shareholders_equity", {}).get("QUALIFIED", 0),
        },
        "earnings_cfo_debt_coverage": {
            "net_income": summary.get("net_income", {}).get("QUALIFIED", 0),
            "operating_cash_flow": summary.get("operating_cash_flow", {}).get("QUALIFIED", 0),
            "total_interest_bearing_debt": summary.get("total_interest_bearing_debt", {}).get("QUALIFIED", 0),
        },
    }


def build_p3d_closeout(*, repo_root: Path, p2_artifact: Mapping[str, Any], p3c_artifact: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Build the P3-D immutable closeout without changing P2/P3-C historical replay."""
    starting_inventory = build_reconciled_residual_gap_inventory(p3c_artifact)
    retained_integrity = verify_retained_document_bytes(repo_root, manifest)
    new_citations = load_promoted_residual_comparative_financial_citations(repo_root)
    before_panel = p3c_artifact["refreshed_panel_data"]
    before_readiness = p3c_artifact["refreshed_fundamental_readiness"]
    refreshed_panel = build_multi_period_financial_panel(
        issuers=p2_artifact["panel_data"]["issuers_represented"],
        citations=load_all_authoritative_citations(repo_root, include_p3d_residual_comparative_evidence=True),
        reference_at=p2_artifact["panel_data"].get("reference_at"),
        generated_at="2026-08-20T06:30:00.000000+00:00",
    )
    after_readiness = build_fundamental_research_artifact(refreshed_panel)
    if refreshed_panel["qualified_facts_count"] != before_panel["qualified_facts_count"] + len(new_citations):
        raise ValueError("P3D_PANEL_PRESERVATION_OR_ADDITION_FAILED")
    after_gaps = sorted(after_readiness["data_gap_matrix"], key=lambda row: (row["missing_or_blocked_reason"], row["ticker"], row["metric_id"], row["periods_used"]))
    source_blockers = [row for row in manifest.get("attempted_issuer_periods", []) if row.get("status") == "SOURCE_NOT_APPROVED"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3D_RESIDUAL_EVIDENCE_SCALEOUT_PARTIAL",
        "source_artifacts": {
            "p2_closeout_identity": p2_artifact.get("artifact_identity"),
            "p3c_closeout_identity": p3c_artifact.get("artifact_identity"),
        },
        "reconciled_starting_gap_inventory": starting_inventory,
        "evidence_acquisition": {
            "retained_document_integrity": retained_integrity,
            "attempted_issuer_periods": manifest.get("attempted_issuer_periods", []),
            "source_authority_blockers": source_blockers,
            "capex_boundary": manifest.get("capex_boundary"),
        },
        "newly_qualified_facts": [{key: citation.get(key) for key in (
            "ticker", "metric", "reporting_period", "value", "currency", "unit_scale", "statement_scope",
            "audit_status", "source_locator", "archive_document_path", "materialization_path", "document_sha256", "source_page", "citation_id",
        )} for citation in new_citations],
        "panel_coverage_before_after": {
            "before": _panel_coverage(before_panel), "after": _panel_coverage(refreshed_panel),
            "refreshed_panel_identity": refreshed_panel["artifact_id"], "refreshed_panel_content_hash": refreshed_panel["content_hash"],
        },
        "fundamental_readiness_before_after": {
            "before": before_readiness["coverage_summary"], "after": after_readiness["coverage_summary"],
            "refreshed_p3b_identity": after_readiness["artifact_identity"], "refreshed_p3b_artifact_sha256": after_readiness["artifact_sha256"],
        },
        "proxy_to_exact_upgrades": _proxy_to_exact(before_readiness, after_readiness, {citation["ticker"] for citation in new_citations}),
        "remaining_data_gaps": {"gap_count": len(after_gaps), "gap_counts_by_reason": _counts(after_gaps, "missing_or_blocked_reason"), "gaps": after_gaps},
        "sector_and_authority_boundaries": {
            "no_new_issuers": True, "annual_consolidated_only": True,
            "corporate_debt_semantics_for_intermediaries": "NOT_APPLICABLE",
            "price_liquidity_valuation_execution_authority": "UNCHANGED_AND_NOT_GRANTED",
            "source_registry_mutated": False,
        },
        "refreshed_panel_data": refreshed_panel,
        "refreshed_fundamental_readiness": after_readiness,
    }
    payload["artifact_sha256"] = stable_id(payload)
    payload["artifact_identity"] = f"p3d_residual_comparative_financial_evidence:{payload['artifact_sha256']}"
    return payload
