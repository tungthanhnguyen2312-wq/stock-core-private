"""The consolidated canonical financial analytical panel
(FINANCIAL_TEMPORAL_SEMANTIC_NORMALIZATION_AND_ANALYTICAL_PANEL_V1).

WHAT THIS IS
    A deterministic per-record join of three already-governed, independently-tested layers:

    * `structured_financial_period_semantics.py` -- period/duration/statement-scope/currency/
      scale/timestamp semantics and (as of this milestone) explicit root-cause classification
      for every unresolved dimension;
    * `bitemporal_semantic_contract.py` -- valid-time and knowledge-availability resolution,
      answering "when may this fact become visible to a historical analysis" without granting
      PIT/RAW_AS_TRADED authority;
    * `financial_flow_semantics_ttm_bridge.py` -- deterministic quarter-from-YTD de-cumulation
      and rolling-4Q TTM, exposed here as explicitly `derived_from`-linked panel rows, never
      merged into or mistaken for a directly-observed fact.

WHAT THIS IS NOT
    Not a new authority tier, not a new fact store, and not a replacement for any of the three
    layers above. Every value on a panel record traces back to exactly one retained source
    observation (`source_lineage.fact_id`) or, for a derived row, to the exact standalone-
    quarter fact ids it was built from (`derived_from`). Nothing here recalculates a financial
    feature, resolves a conflict, or promotes a `provider_reported` fact toward `qualified`.

WHICH USES ARE ALLOWED
    This module does not re-decide feature-level fitness -- `feature_input_fitness_contract.py`
    already owns that question per use-case family. Each panel record instead carries
    `feature_fitness_families`, the exact family names (from that registry) whose authoritative
    module reads this statement_family/canonical_metric, so a caller can look up the current
    verdict without this module re-deriving or caching a copy of it.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

import bitemporal_semantic_contract as bitemporal
import structured_financial_period_semantics as period_semantics

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "canonical_financial_analytical_panel/v1"
ARTIFACT_TYPE = "CANONICAL_FINANCIAL_ANALYTICAL_PANEL"

#: Which `feature_input_fitness_contract.py` use-case families read a given statement family.
#: A static cross-reference, not a re-derivation -- see that module for the actual verdicts.
_FEATURE_FITNESS_FAMILIES_BY_STATEMENT_FAMILY: dict[str, tuple[str, ...]] = {
    "income_statement": ("FINANCIAL_REVENUE_GROWTH", "FINANCIAL_EARNINGS_GROWTH", "FINANCIAL_MARGIN",
                         "FUNDAMENTAL_RATIO", "FUNDAMENTAL_PEER_RELATIVE", "FUNDAMENTAL_OWN_HISTORY",
                         "FINANCIAL_POINT_IN_TIME_BACKTEST"),
    "balance_sheet": ("FINANCIAL_LEVERAGE_LIQUIDITY", "FINANCIAL_ROE_ROA", "ENTERPRISE_VALUE",
                      "FUNDAMENTAL_RATIO", "FUNDAMENTAL_PEER_RELATIVE", "FUNDAMENTAL_OWN_HISTORY",
                      "FINANCIAL_POINT_IN_TIME_BACKTEST"),
    "cash_flow": ("FINANCIAL_CASH_FLOW_QUALITY", "FINANCIAL_FREE_CASH_FLOW_PROXY",
                 "FUNDAMENTAL_PEER_RELATIVE", "FUNDAMENTAL_OWN_HISTORY", "FINANCIAL_POINT_IN_TIME_BACKTEST"),
}

#: financial_flow_semantics_ttm_bridge.FLOW_METRICS, restated here only as a display label --
#: importing the bridge just for this tuple would create a heavier coupling than a panel
#: assembly layer needs; the bridge itself remains the sole authority for which metrics qualify.
_DERIVED_TTM_METRICS = ("revenue", "profit_before_tax", "net_income", "operating_cash_flow",
                        "depreciation_and_amortization")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in artifact.items()
               if key not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _valid_time_domain(statement_family: str | None) -> str:
    return "FINANCIAL_STOCK_FACT" if statement_family == "balance_sheet" else "FINANCIAL_FLOW_FACT"


def _panel_temporal_envelope(row: Mapping[str, Any]) -> dict[str, Any]:
    """Attach bitemporal_semantic_contract's valid-time and knowledge-availability resolution
    to one structured_financial_period_semantics row. Additive only: it never overrides
    `retrieval_or_observation_timestamp`/`published_timestamp`, and a fact with no usable
    timestamp resolves to `KNOWLEDGE_UNKNOWN` here exactly as it already does upstream --
    this never converts an unknown timestamp into a fabricated knowledge date."""
    domain = _valid_time_domain(row.get("statement_family"))
    valid_time = bitemporal.validate_valid_time(
        domain=domain, period_start=row.get("period_start"), period_end=row.get("period_end"),
        statement_scope=row.get("statement_scope"),
    )
    observed_at = row.get("retrieval_or_observation_timestamp")
    published_at = row.get("published_timestamp")
    precision = bitemporal.infer_precision(published_at or observed_at)
    tier = (bitemporal.PublicationAuthorityTier.PROVIDER_REPORTED if row.get("source_status") == "provider_reported"
            else bitemporal.PublicationAuthorityTier.UNVERIFIED)
    publication = bitemporal.PublicationTime(
        source_published_at=published_at, source_published_at_precision=bitemporal.infer_precision(published_at),
        publication_authority_tier=tier, source_identity=(row.get("source_lineage") or {}).get("fact_id"),
        qualification_status=str(row.get("source_qualification_state") or "UNKNOWN"),
        timezone_status=("AWARE" if bitemporal.infer_precision(published_at) == bitemporal.TemporalPrecision.EXACT_DATETIME
                         else "UNKNOWN"),
    )
    knowledge = bitemporal.resolve_knowledge_availability(publication=publication, first_observed_at=observed_at)
    return {
        "valid_time": valid_time.to_dict(),
        "knowledge_resolution": knowledge.to_dict(),
        "effective_from_research_session": knowledge.knowledge_available_research_session,
    }


def build_panel_record(row: Mapping[str, Any], *, entity_type: str | None = None) -> dict[str, Any]:
    """One panel record from one structured_financial_period_semantics row. Pure passthrough
    plus the bitemporal envelope and the feature-fitness family pointer -- no field already on
    `row` is recomputed or overridden."""
    statement_family = row.get("statement_family")
    record = dict(row)
    record["entity_type"] = entity_type if entity_type is not None else row.get("entity_type")
    record["temporal_envelope"] = _panel_temporal_envelope(row)
    record["feature_fitness_families"] = list(_FEATURE_FITNESS_FAMILIES_BY_STATEMENT_FAMILY.get(str(statement_family), ()))
    record["revision_status"] = ("REVISION_HISTORY_UNKNOWN" if not row.get("source_conflicts")
                                 else "REVISION_HISTORY_UNKNOWN_CONFLICT_PRESERVED")
    record["record_identity"] = (row.get("source_lineage") or {}).get("fact_id")
    record["panel_record_kind"] = "OBSERVED"
    return record


def build_derived_ttm_records(qualified_flow_artifact: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Reshape `financial_flow_semantics_ttm_bridge`'s per-ticker output into explicit
    `derived_from`-linked panel rows. `None`/absent input yields an empty list -- the bridge
    remains optional exactly as `market_wide_financial_analysis_v2_scaleout.build_scaleout`
    already treats it; this function performs no derivation of its own."""
    if not qualified_flow_artifact:
        return []
    records: list[dict[str, Any]] = []
    for ticker, ticker_record in sorted((qualified_flow_artifact.get("records") or {}).items()):
        for metric, ttm in sorted((ticker_record.get("ttm") or {}).items()):
            if not isinstance(ttm, Mapping) or ttm.get("value") is None:
                continue
            records.append({
                "ticker": ticker, "canonical_metric": metric, "statement_family": (
                    "cash_flow" if metric in {"operating_cash_flow", "depreciation_and_amortization"} else "income_statement"),
                "metric_nature": "FLOW_DURATION", "period_semantic_state": "ROLLING_TTM_DERIVED",
                "period_duration_root_cause": None, "reported_value": ttm.get("value"),
                "derived_from": list(ttm.get("source_fact_ids") or ttm.get("derived_from") or []),
                "derivation_method": ttm.get("method", "ROLLING_4Q_TTM"),
                "authority_state": "DERIVED_PROXY_NOT_AUTHORITATIVE",
                "research_semantic_state": "RESEARCH_SEMANTIC_READY",
                "is_actionable": False, "record_identity": f"ttm:{ticker}:{metric}:{qualified_flow_artifact.get('artifact_identity')}",
                "panel_record_kind": "DERIVED_TTM",
                "source_lineage": {"provider": "DERIVED", "fact_id": None},
            })
    return records


def _coverage(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "record_count": len(records),
        "kind_distribution": dict(sorted(Counter(str(r["panel_record_kind"]) for r in records).items())),
        "semantic_state_distribution": dict(sorted(Counter(str(r["period_semantic_state"]) for r in records).items())),
        "duration_root_cause_distribution": dict(sorted(Counter(
            str(r["period_duration_root_cause"]) for r in records if r.get("period_duration_root_cause")).items())),
        "knowledge_time_status_distribution": dict(sorted(Counter(
            (r.get("temporal_envelope") or {}).get("knowledge_resolution", {}).get("knowledge_time_status", "NOT_APPLICABLE")
            for r in records).items())),
    }


def build_artifact(*, semantic_rows: Iterable[Mapping[str, Any]],
                   qualified_flow_artifact: Mapping[str, Any] | None = None,
                   entity_type_by_ticker: Mapping[str, str] | None = None,
                   source_identities: Mapping[str, Any] | None = None,
                   requested_at: str) -> dict[str, Any]:
    """Build the full panel artifact. `semantic_rows` must already be
    `structured_financial_period_semantics.project_fact` output (or `build_artifact`'s
    `records`) -- this function does not read raw canonical facts itself."""
    entity_type_by_ticker = entity_type_by_ticker or {}
    observed = [
        build_panel_record(row, entity_type=entity_type_by_ticker.get(str(row.get("ticker"))))
        for row in semantic_rows
    ]
    derived = build_derived_ttm_records(qualified_flow_artifact)
    records = observed + derived
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "requested_at": requested_at,
        "source_identities": dict(source_identities or {}),
        "records": records,
        "coverage": _coverage(records),
        "authority_boundary": {
            "projection_only": True, "authoritative_namespace_overwritten": False,
            "official_or_owner_promotion": False, "recommendation_ranking_valuation_changed": False,
            "pit_or_raw_as_traded_promoted": False, "feature_fitness_rederived": False,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact
