"""Orchestrate opportunity_context/v1 and security_decision_context/v1 over retained inputs."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping

from current_research_valuation_context import (
    attach_fundamental_peers, attach_peer_relative, evaluate_ticker_valuation, freshness_for_valuation,
    source_session_for_valuation,
)
from opportunity_axis_freshness import assert_artifact_session_not_future, classify_axis_freshness
from opportunity_context import (
    CONTRACT_VERSION as OPPORTUNITY_CONTRACT, MAJOR_AXES, build_ticker_opportunity, compact_opportunity, _records, _session,
)
from security_decision_context import (
    CONTRACT_VERSION as DECISION_CONTRACT, LABELS, build_ticker_decision, compact_decision,
)
from financial_analysis_product_projection import context_for_ticker, validate_product_context

SCHEMA_VERSION = "1.0.0"
MILESTONE = "CURRENT_VALUATION_AND_OPPORTUNITY_INTEGRATION_V1"
_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    kind = value.get("contract_version") or "current_valuation_opportunity_integration"
    return {"artifact_sha256": digest, "artifact_identity": f"{kind}:{digest}"}


def _tickers(*artifacts: Mapping[str, Any] | None) -> list[str]:
    names: set[str] = set()
    for artifact in artifacts:
        names.update(_records(artifact))
    return sorted(names)


def build_artifacts(
    *,
    as_of_session: str,
    feature_store: Mapping[str, Any] | None = None,
    tactical_behavior: Mapping[str, Any] | None = None,
    watchlist: Mapping[str, Any] | None = None,
    valuation: Mapping[str, Any] | None = None,
    liquidity: Mapping[str, Any] | None = None,
    events: Mapping[str, Any] | None = None,
    thesis_cases: Mapping[str, Any] | None = None,
    leadership: Mapping[str, Any] | None = None,
    portfolio: Mapping[str, Any] | None = None,
    financial_analysis_product_context: Mapping[str, Any] | None = None,
    requested_at: str,
) -> dict[str, Any]:
    """Join retained current-research artifacts into opportunity and decision contexts.

    Every ticker present in any supplied source receives a disposition. Missing axes stay
    explicit. Future-session artifacts fail closed rather than joining.
    """
    assert_artifact_session_not_future(_session(tactical_behavior, "session", "as_of_session"), decision_session=as_of_session, label="tactical")
    assert_artifact_session_not_future(_session(watchlist, "session"), decision_session=as_of_session, label="watchlist")
    assert_artifact_session_not_future(source_session_for_valuation(valuation), decision_session=as_of_session, label="valuation")
    assert_artifact_session_not_future(_session(liquidity, "resolved_completed_session", "session", "as_of_session"), decision_session=as_of_session, label="liquidity")
    assert_artifact_session_not_future(_session(events, "research_session", "session", "as_of"), decision_session=as_of_session, label="events")
    assert_artifact_session_not_future(_session(thesis_cases, "as_of_session", "session"), decision_session=as_of_session, label="thesis")
    assert_artifact_session_not_future(_session(leadership, "session"), decision_session=as_of_session, label="leadership")
    assert_artifact_session_not_future(_session(portfolio, "as_of_session") or ((portfolio or {}).get("metadata") or {}).get("as_of_session"),
                                      decision_session=as_of_session, label="portfolio")

    financial_analysis_product_context = validate_product_context(financial_analysis_product_context)
    features = _records(feature_store)
    behaviors = _records(tactical_behavior)
    watch_records = _records(watchlist)
    valuation_records = _records(valuation)
    liquidity_records = _records(liquidity)
    event_records = _records(events)
    thesis_records = _records(thesis_cases)
    leadership_records = (leadership or {}).get("ticker_contexts") if isinstance(leadership, Mapping) else None
    if not isinstance(leadership_records, Mapping):
        leadership_records = {}

    tickers = _tickers(feature_store, tactical_behavior, watchlist, valuation, liquidity, events, thesis_cases)
    if not tickers:
        raise ValueError("EMPTY_OPPORTUNITY_DENOMINATOR")

    valuation_rows = {
        ticker: evaluate_ticker_valuation(
            ticker=ticker, feature_record=features.get(ticker), valuation_record=valuation_records.get(ticker),
        )
        for ticker in tickers
    }
    valuation_rows = attach_peer_relative(valuation_rows)
    fundamental_peers = attach_fundamental_peers(features, valuation_rows)
    valuation_freshness = freshness_for_valuation(decision_session=as_of_session, valuation_artifact=valuation)
    portfolio_session = _session(portfolio, "as_of_session") or ((portfolio or {}).get("metadata") or {}).get("as_of_session")
    portfolio_freshness = classify_axis_freshness(
        axis="portfolio", decision_session=as_of_session, source_session=portfolio_session,
        source_artifact_identity=(portfolio or {}).get("artifact_identity"),
    )
    tactical_identity = (tactical_behavior or {}).get("artifact_identity")
    feature_identity = (feature_store or {}).get("artifact_identity")
    liquidity_session = _session(liquidity, "resolved_completed_session", "session", "as_of_session")
    liquidity_identity = (liquidity or {}).get("artifact_identity")
    events_session = _session(events, "research_session", "session", "as_of")
    events_identity = (events or {}).get("artifact_identity")
    thesis_session = _session(thesis_cases, "as_of_session", "session")
    thesis_identity = (thesis_cases or {}).get("artifact_identity")
    leadership_session = _session(leadership, "session")
    leadership_identity = (leadership or {}).get("artifact_identity")

    opportunity_records: dict[str, Any] = {}
    decision_records: dict[str, Any] = {}
    for ticker in tickers:
        opportunity = build_ticker_opportunity(
            ticker=ticker, decision_session=as_of_session,
            feature_record=features.get(ticker),
            valuation_row=valuation_rows[ticker],
            valuation_freshness=valuation_freshness,
            fundamental_peers=fundamental_peers.get(ticker),
            behavior=behaviors.get(ticker),
            watchlist=watch_records.get(ticker),
            tactical_identity=tactical_identity,
            leadership=leadership_records.get(ticker),
            leadership_session=leadership_session,
            leadership_identity=leadership_identity,
            liquidity_record=liquidity_records.get(ticker),
            liquidity_session=liquidity_session or (liquidity_records.get(ticker) or {}).get("session"),
            liquidity_identity=liquidity_identity,
            events_record=event_records.get(ticker),
            events_session=events_session,
            events_identity=events_identity,
            thesis=thesis_records.get(ticker),
            thesis_session=thesis_session or (thesis_records.get(ticker) or {}).get("as_of_session"),
            thesis_identity=thesis_identity,
            portfolio=portfolio,
            portfolio_freshness=portfolio_freshness,
            feature_store_identity=feature_identity,
            financial_analysis=context_for_ticker(financial_analysis_product_context, ticker),
        )
        opportunity_records[ticker] = opportunity
        decision_records[ticker] = build_ticker_decision(opportunity)

    if set(opportunity_records) != set(tickers) or set(decision_records) != set(tickers):
        raise ValueError("SILENT_TICKER_DROP")

    source_artifacts = {
        "fundamental_feature_store": feature_identity,
        "tactical_behavior_context": tactical_identity,
        "watchlist_tactical_entry_classifier": (watchlist or {}).get("artifact_identity"),
        "current_valuation": (valuation or {}).get("artifact_identity"),
        "liquidity_research": liquidity_identity,
        "corporate_event_context": events_identity,
        "thesis_catalyst_cases": thesis_identity,
        "market_sector_leadership": leadership_identity,
        "portfolio_research_context": (portfolio or {}).get("artifact_identity"),
        "financial_analysis_product_integration": (financial_analysis_product_context or {}).get("artifact_identity"),
    }
    opportunity = _opportunity_artifact(
        as_of_session=as_of_session, requested_at=requested_at, records=opportunity_records,
        source_artifacts=source_artifacts, valuation_rows=valuation_rows, fundamental_peers=fundamental_peers,
    )
    decision = _decision_artifact(
        as_of_session=as_of_session, requested_at=requested_at, records=decision_records,
        source_artifacts=source_artifacts, opportunity_identity=opportunity["artifact_identity"],
    )
    return {"opportunity_context": opportunity, "security_decision_context": decision}


def _opportunity_artifact(*, as_of_session: str, requested_at: str, records: Mapping[str, Any],
                          source_artifacts: Mapping[str, Any], valuation_rows: Mapping[str, Any],
                          fundamental_peers: Mapping[str, Any]) -> dict[str, Any]:
    usable_counts = Counter(record["usable_major_axis_count"] for record in records.values())
    axis_usable = {axis: sum(record[axis].get("research_usable") for record in records.values()) for axis in MAJOR_AXES}
    method_status: dict[str, Counter] = {}
    peer_ready = 0
    fundamental_relative = 0
    freshness = Counter()
    for record in records.values():
        for axis in MAJOR_AXES:
            freshness[(axis, (record[axis].get("freshness") or {}).get("freshness_status"))] += 1
        methods = (record["valuation"].get("applicable_methods") or {})
        for method_id, method in methods.items():
            method_status.setdefault(method_id, Counter())[method.get("status")] += 1
            peer = (method.get("peer_relative") or {})
            if peer.get("status") == "READY_RESEARCH_ONLY":
                peer_ready += 1
        if any(item.get("status") == "READY_RESEARCH_ONLY" for item in (record["fundamental"].get("peer_relative") or {}).values()):
            fundamental_relative += 1
    compact = {ticker: compact_opportunity(record) for ticker, record in records.items()}
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": OPPORTUNITY_CONTRACT, "milestone": MILESTONE,
        "requested_at": requested_at, "as_of_session": as_of_session,
        "source_artifacts": dict(source_artifacts),
        "coverage": {
            "ticker_denominator": len(records),
            "opportunity_context_coverage": len(records),
            "zero_silent_ticker_drops": True,
            "usable_major_axis_count_distribution": dict(sorted(usable_counts.items())),
            "tickers_with_ge_3_usable_major_axes": sum(count >= 3 for count in (record["usable_major_axis_count"] for record in records.values())),
            "tickers_with_ge_5_usable_major_axes": sum(count >= 5 for count in (record["usable_major_axis_count"] for record in records.values())),
            "axis_research_usable": axis_usable,
            "partial_by_evidence": sum(record["disposition"] == "PARTIAL_BY_EVIDENCE" for record in records.values()),
            "insufficient_evidence": sum(record["disposition"] == "INSUFFICIENT_EVIDENCE" for record in records.values()),
            "valuation_method_status": {method: dict(sorted(counts.items())) for method, counts in sorted(method_status.items())},
            "peer_relative_valuation_ready_method_instances": peer_ready,
            "tickers_with_peer_relative_valuation": sum(
                (record["valuation"].get("peer_relative_context") or {}).get("relative_research_state")
                in {"ATTRACTIVE_RELATIVE_RESEARCH", "EXPENSIVE_RELATIVE_RESEARCH", "IN_LINE_RELATIVE_RESEARCH"}
                for record in records.values()
            ),
            "tickers_with_fundamental_relative": fundamental_relative,
            "freshness_status_by_axis": {f"{axis}:{status}": count for (axis, status), count in sorted(freshness.items())},
        },
        "blocked_outputs": {
            "universal_score": "SCORING_PROHIBITED", "ordinal_rank": "RANKING_PROHIBITED",
            "probability_of_success": "FORECAST_PROHIBITED", "target_price": "NOT_EMITTED",
            "dcf_fair_value": "NOT_EMITTED", "portfolio_optimization": "NOT_EMITTED",
            "position_size": "NOT_EMITTED", "exact_execution_capacity": "SEPARATE_FAIL_CLOSED",
        },
        "records": dict(records),
        "opportunity_context": compact,
        "authority_effect": "NONE / RESEARCH_ONLY",
    }
    artifact.update(content_identity(artifact))
    return artifact


def _decision_artifact(*, as_of_session: str, requested_at: str, records: Mapping[str, Any],
                       source_artifacts: Mapping[str, Any], opportunity_identity: str) -> dict[str, Any]:
    stances = Counter(record["research_stance"] for record in records.values())
    for label in LABELS:
        stances.setdefault(label, 0)
    compact = {ticker: compact_decision(record) for ticker, record in records.items()}
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": DECISION_CONTRACT, "milestone": MILESTONE,
        "requested_at": requested_at, "as_of_session": as_of_session,
        "source_artifacts": {**dict(source_artifacts), "opportunity_context": opportunity_identity},
        "coverage": {
            "ticker_denominator": len(records),
            "security_decision_context_coverage": len(records),
            "zero_silent_ticker_drops": True,
            "research_stance_distribution": dict(sorted(stances.items())),
        },
        "blocked_outputs": {
            "universal_score": "SCORING_PROHIBITED", "ordinal_rank": "RANKING_PROHIBITED",
            "probability_of_success": "FORECAST_PROHIBITED", "target_price": "NOT_EMITTED",
            "portfolio_fit_as_security_stance": "NOT_EMITTED",
        },
        "records": dict(records),
        "security_decision_context": compact,
        "authority_effect": "NONE / RESEARCH_ONLY",
    }
    artifact.update(content_identity(artifact))
    return artifact
