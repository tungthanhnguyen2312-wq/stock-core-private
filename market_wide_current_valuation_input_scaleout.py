"""Deterministic, fail-closed market-wide current valuation snapshot.

This consumes retained current-session price, share-basis, and fundamental
artifacts only. It emits a blocked metric rather than substitute provider
trends, issued shares, or a historical price for a missing compatible input.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping

from field_temporal_contract import stable_id

CONTRACT_VERSION = "market_wide_current_valuation/v1"
ARTIFACT_TYPE = "MARKET_WIDE_CURRENT_VALUATION"
METRICS = ("market_cap", "P/E", "P/B", "P/S", "enterprise_value", "EV/Sales", "EV/EBITDA")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"market_wide_current_valuation:{digest}"}


def _share_disposition(ticker: str, promotion: Mapping[str, Any]) -> dict[str, Any]:
    """Only ticker-level retained share evidence may describe a ticker's basis."""
    cohort = (promotion.get("projected_coverage_impact") or {}).get("cohort_rows") or []
    row = next((item for item in cohort if item.get("ticker") == ticker), None)
    source = promotion.get("artifact_identity")
    if row is None:
        return {"status": "UNAVAILABLE", "authority": "UNAVAILABLE", "value": None,
                "source_artifact_identity": source, "freshness": "UNKNOWN",
                "blocked_reasons": ["NO_TICKER_LEVEL_CURRENT_SHARE_BASIS_EVIDENCE_RETAINED"]}
    # The retained official reference did not prove coverage through the newer price session.
    return {"status": "PROVIDER_REPORTED_STALE", "authority": str(row.get("resolver_authority") or "UNAVAILABLE"),
            "value": row.get("provider_value"), "source_artifact_identity": source,
            "freshness": str(row.get("freshness_state") or "UNKNOWN"),
            "blocked_reasons": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN_THROUGH_PRICE_SESSION"],
            "retained_evidence": dict(row)}


def _price_input(record: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    observation = (record.get("observations") or [{}])[-1]
    ready = record.get("disposition") == "EXACT_SESSION_RETAINED"
    return {"status": "PRICE_READY" if ready else "PRICE_UNAVAILABLE", "value": observation.get("close") if ready else None,
            "session": snapshot.get("resolved_completed_session"), "source": snapshot.get("source"),
            "basis": "CURRENT_SESSION_DESCRIPTIVE_CURRENT_VALUATION_PRICE_LEG", "currency": "VND",
            "raw_as_traded": "NOT_PROMOTED", "historical_pit_eligible": False,
            "source_snapshot_identity": snapshot.get("snapshot_identity"),
            "blocked_reasons": [] if ready else [f"PRICE_{record.get('disposition', 'UNAVAILABLE')}"]}


def _applicability(entity: str, metric: str) -> str:
    if metric == "market_cap":
        return "APPLICABLE"
    if entity == "corporate":
        return "APPLICABLE" if metric != "EV/EBITDA" else "APPLICABLE_IF_EXACT_EBITDA"
    if entity in {"bank", "securities"}:
        return "APPLICABLE" if metric in {"P/E", "P/B"} else "NOT_APPLICABLE"
    if entity in {"finance_company", "insurance"}:
        return "NOT_APPLICABLE"
    return "BLOCKED_ENTITY_CLASS_UNKNOWN"


def _financial_input(fundamental: Mapping[str, Any] | None, artifact: Mapping[str, Any]) -> dict[str, Any]:
    if fundamental is None:
        return {"authority": "UNAVAILABLE", "calculation_grade": False, "blocked_reasons": ["NO_RETAINED_FINANCIAL_RECORD"]}
    tier = fundamental.get("authority_tier")
    if tier != "OFFICIAL_QUALIFIED":
        return {"authority": tier, "calculation_grade": False,
                "blocked_reasons": ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"],
                "source_artifact_identity": artifact.get("artifact_identity")}
    return {"authority": "OFFICIAL_QUALIFIED", "calculation_grade": True,
            "source_artifact_identity": artifact.get("artifact_identity"),
            "metric_count": len(fundamental.get("metrics") or []),
            "period_context": fundamental.get("official_metric_context")}


def _metric(metric: str, applicability: str, price: Mapping[str, Any], share: Mapping[str, Any], financial: Mapping[str, Any]) -> dict[str, Any]:
    if applicability == "NOT_APPLICABLE":
        return {"metric_id": metric, "status": "NOT_APPLICABLE", "value": None, "applicability": applicability,
                "formula_version": CONTRACT_VERSION, "blocked_reasons": ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]}
    blockers = []
    if price["status"] != "PRICE_READY":
        blockers.extend(price["blocked_reasons"])
    if share["status"] != "QUALIFIED_OFFICIAL":
        blockers.extend(share["blocked_reasons"])
    if metric != "market_cap":
        if applicability == "BLOCKED_ENTITY_CLASS_UNKNOWN":
            blockers.append("ENTITY_CLASS_UNRESOLVED")
        if not financial["calculation_grade"]:
            blockers.extend(financial["blocked_reasons"])
        if metric == "EV/EBITDA":
            blockers.append("EXACT_EBITDA_COMPARABILITY_NOT_RETAINED")
    return {"metric_id": metric, "status": "BLOCKED", "value": None, "applicability": applicability,
            "formula_version": CONTRACT_VERSION, "blocked_reasons": sorted(set(blockers)),
            "price_session": price.get("session"), "is_actionable": False, "historical_pit_eligible": False}


def build_current_valuation_artifact(*, price_snapshot: Mapping[str, Any], fundamental_artifact: Mapping[str, Any],
                                     share_promotion_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize one record per retained price-universe ticker without imputation."""
    records: dict[str, Any] = {}
    fundamentals = fundamental_artifact.get("records") or {}
    for ticker, price_record in sorted((price_snapshot.get("records") or {}).items()):
        fundamental = fundamentals.get(ticker)
        entity = str((fundamental or {}).get("entity_class") or "unknown")
        price = _price_input(price_record, price_snapshot)
        share = _share_disposition(ticker, share_promotion_artifact)
        financial = _financial_input(fundamental, fundamental_artifact)
        metric_rows = {metric: _metric(metric, _applicability(entity, metric), price, share, financial) for metric in METRICS}
        row = {"ticker": ticker, "entity_class": entity, "entity_class_source": (fundamental or {}).get("entity_class_provenance"),
               "price_input": price, "share_basis_input": share, "financial_input": financial,
               "metrics": metric_rows, "warnings": ["CURRENT_DESCRIPTIVE_NOT_HISTORICAL_PIT", "NO_RANKING_OR_RECOMMENDATION"],
               "is_actionable": False}
        row["content_identity"] = stable_id(row)
        records[ticker] = row
    metric_ready = {metric: sum(row["metrics"][metric]["status"] == "READY" for row in records.values()) for metric in METRICS}
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "valuation_session": price_snapshot.get("resolved_completed_session"),
        "source_artifacts": {"current_price": price_snapshot.get("snapshot_identity"), "fundamental": fundamental_artifact.get("artifact_identity"), "share_basis": share_promotion_artifact.get("artifact_identity")},
        "records": records,
        "coverage": {"candidate_universe": len(records), "price_ready": sum(r["price_input"]["status"] == "PRICE_READY" for r in records.values()),
                     "share_ready": sum(r["share_basis_input"]["status"] == "QUALIFIED_OFFICIAL" for r in records.values()),
                     "both_price_and_share_ready": sum(r["price_input"]["status"] == "PRICE_READY" and r["share_basis_input"]["status"] == "QUALIFIED_OFFICIAL" for r in records.values()),
                     "metric_ready_counts": metric_ready,
                     "share_authority_tiers": dict(sorted(Counter(r["share_basis_input"]["status"] for r in records.values()).items())),
                     "financial_authority_tiers": dict(sorted(Counter(r["financial_input"]["authority"] for r in records.values()).items())),
                     "entity_classes": dict(sorted(Counter(r["entity_class"] for r in records.values()).items())),
                     "blocked_or_not_applicable": dict(sorted(Counter(m["status"] for r in records.values() for m in r["metrics"].values()).items()))},
        "authority_boundary": {"current_snapshot_only": True, "historical_pit_eligible": False, "raw_as_traded": "NOT_PROMOTED", "provider_financial_absolute_inputs": "BLOCKED", "ranking": False, "recommendation": False, "target_price": False},
        "valuation_context": {"status": "SKIPPED", "reason": "NO_METRIC_READY_COMPARABLE_COHORT"}, "is_actionable": False,
    }
    artifact.update(content_identity(artifact))
    return artifact
