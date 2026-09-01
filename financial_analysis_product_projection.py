"""Compact, product-safe Financial Analysis V2 projection.

The Financial Analysis engine record is deliberately rich and can contain statement
lineage that is unsuitable for normal product delivery.  This module is the only
adapter from ``financial_analysis_context/v2`` into product consumers.  It never
recomputes ratios or promotes a proxy to READY.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping, Sequence

ENGINE_CONTRACT = "financial_analysis_context/v2"
COMPACT_CONTRACT = "financial_analysis_compact/v1"
TICKER_INDEX_CONTRACT = "financial_analysis_ticker_index/v1"
MARKET_SUMMARY_CONTRACT = "financial_analysis_market_summary/v1"
LINEAGE_CONTRACT = "financial_analysis_lineage/v1"
INTEGRATION_CONTRACT = "financial_analysis_product_integration/v1"
ABSENT = "ABSENT"


class FinancialAnalysisProductProjectionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any], contract: str | None = None) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{contract or value.get('contract_version')}:{digest}"}


def _names(tickers: Sequence[str]) -> list[str]:
    names = sorted({str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()})
    if not names:
        raise FinancialAnalysisProductProjectionError("EMPTY_PRODUCT_TICKER_DENOMINATOR")
    return names


def _as_of_period(record: Mapping[str, Any]) -> str | None:
    labels: list[str] = []
    for feature in (record.get("features") or {}).values():
        if isinstance(feature, Mapping):
            labels.extend(str(item) for item in (feature.get("period_identity") or []) if item)
    return max(labels) if labels else None


def _growth_basis(record: Mapping[str, Any]) -> str | None:
    for feature_name in ("revenue_qoq", "revenue_same_quarter_yoy", "revenue_ytd_yoy", "revenue_ttm_yoy"):
        feature = (record.get("features") or {}).get(feature_name) or {}
        if feature.get("fitness") == "READY" and feature.get("growth_basis"):
            return feature["growth_basis"]
    return None


def _lineage(engine: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("source_identities") if isinstance(record.get("source_identities"), Mapping) else engine.get("source_identities")
    payload: dict[str, Any] = {
        "contract_version": LINEAGE_CONTRACT,
        "source_context_identity": engine.get("artifact_identity"),
        "source_context_contract": ENGINE_CONTRACT,
        "source_identities": dict(source or {}),
        "local_only": True,
        "published_path": None,
    }
    payload.update(_identity(payload, LINEAGE_CONTRACT))
    return payload


def _compact(engine: Mapping[str, Any], ticker: str, record: Mapping[str, Any]) -> dict[str, Any]:
    states = record.get("states") if isinstance(record.get("states"), Mapping) else {}
    lineage = _lineage(engine, record)
    # Every value below is copied from the deterministic engine; numbers/statements
    # are intentionally not exposed for downstream AI recomputation.
    return {
        "contract_version": COMPACT_CONTRACT,
        "ticker": ticker,
        "status": "AVAILABLE",
        "source_context_identity": engine.get("artifact_identity"),
        "financial_content_identity": engine.get("artifact_sha256"),
        "issuer_type": record.get("issuer_type"),
        "analysis_family": record.get("analysis_family"),
        "as_of_financial_period": _as_of_period(record),
        "current_research_ready": record.get("current_research_ready") is True,
        "pit_authority": record.get("pit_authority"),
        "profitability_state": states.get("profitability_state"),
        "margin_state": states.get("margin_state"),
        "growth_state": states.get("growth_state"),
        "growth_basis": _growth_basis(record),
        "cash_conversion_state": states.get("cash_conversion_state"),
        "balance_sheet_state": states.get("balance_sheet_state"),
        "leverage_state": states.get("leverage_state"),
        "capital_efficiency_state": states.get("capital_efficiency_state"),
        "resilience_state": states.get("resilience_state"),
        "working_capital_state": states.get("working_capital_state"),
        "working_capital_trajectory_state": states.get("working_capital_trajectory_state"),
        "current_ratio_trajectory_state": states.get("current_ratio_trajectory_state"),
        "valuation_hints": list(record.get("valuation_hints") or []),
        "deterministic_positive_evidence": list(record.get("positive_evidence") or []),
        "negative_evidence": list(record.get("negative_evidence") or []),
        "conflicting_evidence": list(record.get("conflicting_evidence") or []),
        "missing_dimensions": list(record.get("missing_dimensions") or []),
        "warnings": list(record.get("warnings") or []),
        "lineage_ref": lineage["artifact_identity"],
        "lineage": lineage,
        "feature_fitness": {
            key: {"fitness": feature.get("fitness"), "reason_codes": list(feature.get("reason_codes") or [])}
            for key, feature in sorted((record.get("features") or {}).items()) if isinstance(feature, Mapping)
        },
        "is_actionable": False,
        "raw_engine_record_exposed": False,
    }


def absent_context(ticker: str, *, source_context_identity: str | None = None) -> dict[str, Any]:
    return {
        "contract_version": COMPACT_CONTRACT,
        "ticker": ticker,
        "status": ABSENT,
        "source_context_identity": source_context_identity,
        "financial_content_identity": None,
        "reason": "FA_V2_CONTEXT_ABSENT",
        "lineage_ref": None,
        "is_actionable": False,
        "raw_engine_record_exposed": False,
    }


def build_product_projection(*, financial_context: Mapping[str, Any], product_tickers: Sequence[str], requested_at: str) -> dict[str, Any]:
    """Project a V2 engine artifact over the supplied product denominator.

    Product tickers outside the retained engine cohort get an explicit ``ABSENT``
    record.  The engine denominator is never used as a product-universe selector.
    """
    if financial_context.get("contract_version") != ENGINE_CONTRACT:
        raise FinancialAnalysisProductProjectionError("FINANCIAL_ANALYSIS_ENGINE_CONTRACT_REQUIRED")
    expected = _identity(financial_context, ENGINE_CONTRACT)
    if financial_context.get("artifact_sha256") != expected["artifact_sha256"]:
        raise FinancialAnalysisProductProjectionError("FINANCIAL_ANALYSIS_ENGINE_IDENTITY_MISMATCH")
    engine_records = financial_context.get("records")
    if not isinstance(engine_records, Mapping):
        raise FinancialAnalysisProductProjectionError("FINANCIAL_ANALYSIS_ENGINE_RECORDS_INVALID")
    names = _names(product_tickers)
    records: dict[str, Any] = {}
    for ticker in names:
        record = engine_records.get(ticker)
        records[ticker] = _compact(financial_context, ticker, record) if isinstance(record, Mapping) else absent_context(
            ticker, source_context_identity=financial_context.get("artifact_identity")
        )
    if set(records) != set(names):
        raise FinancialAnalysisProductProjectionError("SILENT_TICKER_DROP")
    available = [record for record in records.values() if record["status"] == "AVAILABLE"]
    summary = {
        "contract_version": MARKET_SUMMARY_CONTRACT,
        "source_context_identity": financial_context.get("artifact_identity"),
        "product_ticker_denominator": len(names),
        "engine_ticker_denominator": len(engine_records),
        "compact_coverage": len(available),
        "absent_coverage": len(names) - len(available),
        "current_research_ready_count": sum(record.get("current_research_ready") is True for record in available),
        "issuer_family_distribution": dict(sorted(Counter(record.get("analysis_family") for record in available).items())),
        "fitness_counts": dict(sorted(Counter(
            feature.get("fitness") for record in available for feature in record.get("feature_fitness", {}).values()
        ).items())),
        "mixed_provider_proxy_count": sum(
            feature.get("fitness") == "RESEARCH_PROXY" and "CROSS_PROVIDER_UNRESOLVED_SCALE" in feature.get("reason_codes", [])
            for record in available for feature in record.get("feature_fitness", {}).values()
        ),
        "is_actionable": False,
    }
    ticker_index = {
        ticker: {"contract_version": TICKER_INDEX_CONTRACT, "status": record["status"], "lineage_ref": record.get("lineage_ref"),
                 "source_context_identity": record.get("source_context_identity"), "is_actionable": False}
        for ticker, record in records.items()
    }
    payload: dict[str, Any] = {
        "contract_version": INTEGRATION_CONTRACT,
        "requested_at": requested_at,
        "source_context_identity": financial_context.get("artifact_identity"),
        "financial_analysis_market_summary": summary,
        "financial_analysis_ticker_index": ticker_index,
        "records": records,
        "coverage": {"ticker_denominator": len(names), "compact_coverage": len(available),
                     "absent_coverage": len(names) - len(available), "zero_silent_ticker_drops": True},
        "authority_boundary": {"is_actionable": False, "research_only": True,
                               "proxies_never_promoted_to_ready": True, "no_score": True,
                               "no_target_price": True, "no_probability": True},
    }
    payload.update(_identity(payload, INTEGRATION_CONTRACT))
    return payload


def validate_product_context(context: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if context is None:
        return None
    if context.get("contract_version") == ENGINE_CONTRACT:
        raise FinancialAnalysisProductProjectionError("RAW_FINANCIAL_ENGINE_RECORD_REJECTED")
    if context.get("contract_version") != INTEGRATION_CONTRACT:
        raise FinancialAnalysisProductProjectionError("FINANCIAL_ANALYSIS_PRODUCT_CONTEXT_REQUIRED")
    expected = _identity(context, INTEGRATION_CONTRACT)
    if context.get("artifact_sha256") != expected["artifact_sha256"]:
        raise FinancialAnalysisProductProjectionError("FINANCIAL_ANALYSIS_PRODUCT_CONTEXT_IDENTITY_MISMATCH")
    records = context.get("records")
    if not isinstance(records, Mapping):
        raise FinancialAnalysisProductProjectionError("FINANCIAL_ANALYSIS_PRODUCT_RECORDS_INVALID")
    return context


def context_for_ticker(context: Mapping[str, Any] | None, ticker: str) -> dict[str, Any] | None:
    """Return compact/ABSENT context, preserving the no-input compatibility path."""
    if context is None:
        return None
    records = validate_product_context(context).get("records") or {}
    value = records.get(ticker)
    if not isinstance(value, Mapping):
        raise FinancialAnalysisProductProjectionError("SILENT_TICKER_DROP")
    if value.get("contract_version") != COMPACT_CONTRACT:
        raise FinancialAnalysisProductProjectionError("FINANCIAL_ANALYSIS_COMPACT_CONTRACT_REQUIRED")
    return dict(value)
