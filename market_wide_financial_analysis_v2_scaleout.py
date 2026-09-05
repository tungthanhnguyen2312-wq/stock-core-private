"""Market-wide retained-only scaleout for ``financial_analysis_context/v2``.

The existing V2 engine remains the only financial-state implementation.  This adapter
widens its cohort from the qualified Feature Store, retaining period-semantic engine
results when present and attaching Feature Store observations solely as labelled
``RESEARCH_PROXY`` fallback evidence.  It never promotes a proxy to READY.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import financial_analysis_engine_v2 as engine
import financial_flow_semantics_ttm_bridge as qualified_flow

FEATURE_STORE_CONTRACT = "market_wide_fundamental_feature_store/v1"
GENERIC = "UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS"
_FEATURE_MAP = {
    "profit_state": "net_income_sign", "net_margin": "net_margin",
    "operating_cash_flow_sign": "operating_cash_flow_sign", "cfo_to_net_income": "cfo_to_net_income",
    "cash_to_assets": "cash_to_assets", "equity_to_assets": "equity_to_assets",
    "total_assets_pit_trajectory": "assets_yoy", "shareholders_equity_pit_trajectory": "equity_yoy",
    "cash_and_cash_equivalents_pit_trajectory": "cash_yoy", "roa_eop_proxy": "mixed_provider_roa_proxy",
    "roe_eop_proxy": "same_provider_roe",
}
_ADVANCED = frozenset({"revenue_qoq", "profit_before_tax_qoq", "net_income_qoq", "operating_cash_flow_qoq",
                       "revenue_same_quarter_yoy", "profit_before_tax_same_quarter_yoy", "net_income_same_quarter_yoy", "operating_cash_flow_same_quarter_yoy",
                       "revenue_ttm", "profit_before_tax_ttm", "net_income_ttm", "operating_cash_flow_ttm",
                       "revenue_ttm_yoy", "profit_before_tax_ttm_yoy", "net_income_ttm_yoy", "operating_cash_flow_ttm_yoy",
                       "ttm_net_margin", "ttm_pbt_margin", "cfo_to_net_income_ttm"})


class FinancialAnalysisScaleoutError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_feature_store(artifact_path: Path, records_path: Path) -> tuple[dict[str, dict[str, Any]], Mapping[str, Any]]:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if artifact.get("contract_version") != FEATURE_STORE_CONTRACT:
        raise FinancialAnalysisScaleoutError("FEATURE_STORE_CONTRACT_UNSUPPORTED")
    digest = hashlib.sha256(); records: dict[str, dict[str, Any]] = {}
    with gzip.open(records_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line); encoded = _canonical(record) + "\n"
            digest.update(encoded.encode("utf-8")); ticker = str(record.get("ticker") or "").upper()
            if not ticker or ticker in records:
                raise FinancialAnalysisScaleoutError("FEATURE_STORE_TICKER_INVALID_OR_DUPLICATE")
            records[ticker] = record
    payload = artifact.get("records_payload") or {}
    if payload.get("record_count") != len(records) or payload.get("canonical_jsonl_sha256") != digest.hexdigest():
        raise FinancialAnalysisScaleoutError("FEATURE_STORE_PAYLOAD_IDENTITY_MISMATCH")
    return records, artifact


def _store_feature(source: Mapping[str, Any], target: str, store_identity: str) -> dict[str, Any] | None:
    status = str(source.get("status") or "")
    if status not in {"READY_RESEARCH_PROXY", "PARTIAL_RESEARCH"}:
        return None
    return {
        "feature_id": target, "value": source.get("value"), "fitness": "RESEARCH_PROXY",
        "method": "safe_feature_store_fallback/v1", "growth_basis": None,
        "semantic_transition": source.get("categorical_state"),
        "period_identity": copy.deepcopy(source.get("input_periods") or []),
        "provider_source_provenance": copy.deepcopy(source.get("provider_source_lineage") or []),
        "scope": copy.deepcopy(source.get("scope") or []),
        "period_semantics": copy.deepcopy(source.get("duration_semantics") or []),
        "reason_codes": ["FEATURE_STORE_RESEARCH_PROXY"],
        "warnings": ["FEATURE_STORE_PROXY_NEVER_PROMOTED_TO_READY"],
        "source_tier": "SAFE_FEATURE_STORE_FEATURE", "source_artifact_identity": store_identity,
        "is_actionable": False,
    }


def _refresh_states(record: dict[str, Any]) -> None:
    """Add only safe qualitative states for Feature Store fallback; no proxy becomes READY."""
    features = record["features"]
    profit = features["net_income_sign"]
    state = profit.get("semantic_transition")
    if profit["fitness"] == "RESEARCH_PROXY" and state in {"PROFITABLE", "LOSS_MAKING"}:
        record["states"]["profitability_state"] = state
    for feature, state_name in (("assets_yoy", "balance_sheet_state"), ("equity_yoy", "balance_sheet_state")):
        value = features[feature]
        if value["fitness"] == "RESEARCH_PROXY" and value.get("semantic_transition") in {"IMPROVING", "WEAKENING", "STABLE"}:
            record["states"][state_name] = {"IMPROVING": "STRENGTHENING", "WEAKENING": "DETERIORATING", "STABLE": "STABLE"}[value["semantic_transition"]]
    record.update(engine._evidence(record["ticker"], features, record["states"]))


def _bridge_fact(row: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one `structured_financial_period_semantics` row back into the raw-canonical-fact
    field names `financial_flow_semantics_ttm_bridge.flow_semantics`/`_usable`/`_compatible`
    actually read (`value`, `status`, `provider`, `currency`, `scale`, `reporting_period`,
    `cumulative_state`, `source_sha256`, `source_file`, `fact_id`) -- NOT the reshaped
    `reported_value`/`source_status`/`source_lineage.provider`/... names that module exposes
    for its own consumers. Feeding the reshaped row directly (an earlier version of this
    wiring did) makes every field the bridge reads resolve to `None`, so `_usable()` rejects
    every fact and the bridge silently qualifies nothing -- discovered via a real regression on
    `current_research_ready_count` (1380 -> 1276) in `test_canonical_daily_financial_v2_
    materialization.py`, not by inspection alone. This performs no new resolution of its own;
    every value already exists on `row`, just under a different key."""
    lineage = row.get("source_lineage") or {}
    unit = row.get("normalized_candidate_unit") or {}
    return {
        "ticker": row.get("ticker"), "canonical_metric": row.get("canonical_metric"),
        "statement_family": row.get("statement_family"), "reporting_period": row.get("native_period_label"),
        "period_start": row.get("period_start"), "period_end": row.get("period_end"),
        "value": row.get("reported_value"), "status": row.get("source_status"),
        "provider": lineage.get("provider"), "source_sha256": lineage.get("source_sha256"),
        "source_file": lineage.get("source_file"), "fact_id": lineage.get("fact_id"),
        "statement_scope": row.get("statement_scope"),
        "currency": unit.get("currency", row.get("reported_currency")),
        "scale": unit.get("scale", row.get("reported_scale")),
        "cumulative_state": row.get("reported_cumulative_state"),
    }


def build_qualified_flow_artifact(*, semantic_rows: Sequence[Mapping[str, Any]],
                                  feature_records: Mapping[str, Mapping[str, Any]],
                                  requested_at: str) -> dict[str, Any]:
    """Build the `financial_flow_semantics_ttm_bridge` artifact from the same `semantic_rows`/
    `feature_records` a caller already has, so activating `build_scaleout`'s
    `qualified_flow_artifact` is one extra call instead of every caller re-deriving
    `facts_by_ticker`/`entity_type_by_ticker` independently (FINANCIAL_TEMPORAL_SEMANTIC_
    NORMALIZATION_AND_ANALYTICAL_PANEL_V1: the bridge was previously built and tested but never
    invoked by any real caller of `build_scaleout`, so it never actually qualified a flow row
    market-wide despite being wired by import)."""
    names = sorted(feature_records)
    facts_by_ticker: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in semantic_rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            facts_by_ticker[ticker].append(_bridge_fact(row))
    entity_type_by_ticker = {ticker: feature_records[ticker].get("entity_type") for ticker in names}
    return qualified_flow.build_artifact(
        tickers=names, facts_by_ticker=facts_by_ticker,
        entity_type_by_ticker=entity_type_by_ticker, requested_at=requested_at,
    )


def build_scaleout(*, semantic_rows: Sequence[Mapping[str, Any]], feature_records: Mapping[str, Mapping[str, Any]],
                   feature_store_artifact: Mapping[str, Any], period_semantics_identity: str,
                   requested_at: str, legacy_records: Mapping[str, Mapping[str, Any]] | None = None,
                   classification_diagnostics_identity: str | None = None,
                   qualified_flow_artifact: Mapping[str, Any] | None = None) -> dict[str, Any]:
    names = sorted(feature_records)
    issuer_types = {ticker: feature_records[ticker].get("entity_type") for ticker in names}
    legacy_records = {ticker: record for ticker, record in (legacy_records or {}).items() if ticker in feature_records}
    issuer_types.update({ticker: record.get("issuer_type") for ticker, record in legacy_records.items() if ticker in issuer_types})
    qualified_rows: list[Mapping[str, Any]] = []
    qualified_coverage: Mapping[str, Any] | None = None
    if qualified_flow_artifact is not None:
        if qualified_flow_artifact.get("contract_version") != qualified_flow.CONTRACT_VERSION:
            raise FinancialAnalysisScaleoutError("QUALIFIED_FLOW_CONTRACT_UNSUPPORTED")
        expected = qualified_flow.content_identity(qualified_flow_artifact)
        if qualified_flow_artifact.get("artifact_sha256") != expected["artifact_sha256"]:
            raise FinancialAnalysisScaleoutError("QUALIFIED_FLOW_IDENTITY_MISMATCH")
        qualified_rows = qualified_flow.engine_rows_from_artifact(qualified_flow_artifact)
        qualified_coverage = ((qualified_flow_artifact.get("coverage") or {}).get("qualified_flow_before_after"))
    # Flow rows are admitted only through the bridge when supplied.  P-I-T rows remain
    # untouched, which locks working-capital and explicit-debt coverage.
    bridge_metrics = set(qualified_flow.FLOW_METRICS)
    engine_rows = ([row for row in semantic_rows if row.get("canonical_metric") not in bridge_metrics] + qualified_rows
                   if qualified_flow_artifact is not None else list(semantic_rows))
    artifact = engine.build_artifact(
        tickers=names, rows=engine_rows, issuer_types=issuer_types,
        source_identities={
            "period_semantics_contract": "market_wide_structured_financial_period_semantics/v1",
            "period_semantics_identity": period_semantics_identity,
            "feature_store_contract": FEATURE_STORE_CONTRACT,
            "feature_store_artifact_identity": feature_store_artifact.get("artifact_identity"),
            "classification_diagnostics_identity": classification_diagnostics_identity,
            "qualified_flow_artifact_identity": qualified_flow_artifact.get("artifact_identity") if qualified_flow_artifact else None,
        }, requested_at=requested_at,
    )
    for ticker, record in artifact["records"].items():
        store_record = feature_records[ticker]
        if qualified_flow_artifact is not None:
            flow_record = (qualified_flow_artifact.get("records") or {}).get(ticker) or {}
            flow_state = ((flow_record.get("qualitative_states") or {}).get("earnings_turnaround_state"))
            if flow_state and record["analysis_family"] == engine.INDUSTRIAL:
                # The bridge owns exact quarter continuity and its loss-base transition;
                # preserve that qualified state instead of reselecting another series here.
                record["states"]["earnings_turnaround_state"] = flow_state
        # The named 523 replay is a semantic regression oracle, not fallback coverage.
        # Its existing V2 interpretation must remain byte-for-byte feature compatible.
        if ticker in legacy_records:
            for feature in record["features"].values():
                feature.setdefault("source_tier", "LEGACY_V2_REGRESSION_ORACLE")
            continue
        generic = store_record.get("entity_type") in (None, "", "unknown") and store_record.get("entity_applicability") == "GENERIC_RESEARCH_PRIMITIVES_ALLOWED"
        if generic:
            record["analysis_family"] = GENERIC
            record["issuer_type"] = "unknown"
        if record["analysis_family"] == engine.LIMITED:
            for feature in record["features"].values():
                feature.setdefault("source_tier", "ENTITY_APPLICABILITY")
            continue
        for source_id, target_id in _FEATURE_MAP.items():
            existing = record["features"][target_id]
            fallback = _store_feature((store_record.get("features") or {}).get(source_id) or {}, target_id, str(feature_store_artifact.get("artifact_identity")))
            if fallback and existing["fitness"] in {"BLOCKED_BY_EVIDENCE", "NOT_APPLICABLE"}:
                record["features"][target_id] = fallback
        for feature in record["features"].values():
            feature.setdefault("source_tier", "ADVANCED_TTM_OR_STANDALONE" if feature["feature_id"] in _ADVANCED else "PERIOD_SEMANTIC_FACTS")
        # Only V2 READY means current research ready; Feature Store proxies never light it.
        readiness = ("net_margin", "pbt_margin", "equity_to_assets", "cash_to_assets", "assets_yoy", "equity_yoy")
        record["current_research_ready"] = record["analysis_family"] == engine.INDUSTRIAL and any(record["features"][name]["fitness"] == "READY" for name in readiness)
        _refresh_states(record)
    all_features = [feature for record in artifact["records"].values() for feature in record["features"].values()]
    artifact["coverage"].update({
        "ticker_denominator": len(names), "ticker_record_count": len(artifact["records"]),
        "zero_silent_ticker_drops": len(names) == len(artifact["records"]),
        "issuer_family_distribution": dict(sorted(Counter(record["analysis_family"] for record in artifact["records"].values()).items())),
        "current_research_ready_count": sum(record["current_research_ready"] for record in artifact["records"].values()),
        "source_tier_distribution": dict(sorted(Counter(feature["source_tier"] for feature in all_features).items())),
        "feature_fitness": dict(sorted(Counter(feature["fitness"] for feature in all_features).items())),
        "feature_ready_counts": dict(sorted(Counter(feature["feature_id"] for feature in all_features if feature["fitness"] == "READY").items())),
        "feature_proxy_counts": dict(sorted(Counter(feature["feature_id"] for feature in all_features if feature["fitness"] == "RESEARCH_PROXY").items())),
        "evidence_coverage": {name: sum(bool(record[name]) for record in artifact["records"].values()) for name in ("positive_evidence", "negative_evidence", "conflicting_evidence", "missing_dimensions")},
        "state_distribution": {
            name: dict(sorted(Counter(record["states"][name] for record in artifact["records"].values()).items()))
            for name in sorted(next(iter(artifact["records"].values()))["states"])
        },
        "qualified_flow_before_after": copy.deepcopy(qualified_coverage),
    })
    artifact["scaleout"] = {"feature_source_priority": ["QUALIFIED_FLOW_TTM_AND_GROWTH", "PERIOD_SEMANTIC_FACTS", "SAFE_FEATURE_STORE_FEATURE"], "feature_store_proxy_cannot_make_ready": True, "legacy_523_regression_ticker_count": len(legacy_records), "qualified_flow_replaced_raw_flow_rows": qualified_flow_artifact is not None}
    artifact.update(engine.content_identity(artifact))
    return artifact
