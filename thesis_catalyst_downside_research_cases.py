"""Deterministic, research-only thesis/catalyst/downside cases.

This is a downstream interpretation of retained opportunity, event, and TTM artifacts.  It
does not acquire evidence, score securities globally, or grant decision authority.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "thesis_catalyst_downside_and_dual_invalidation/v1"
OPPORTUNITY_INPUT = ROOT / "operations-review" / "fundamental-plus-market-opportunity-ranking-v1-20260828" / "artifact.json"
EVENT_INPUT = ROOT / "operations-review" / "current-corporate-event-context-v1" / "current_corporate_event_context_artifact.json"
TTM_INPUT = ROOT / "operations-review" / "financial-flow-semantics-and-ttm-bridge-foundation-v1-20260828" / "artifact.json"

CONSTRUCTIVE_STATES = frozenset({"BREAKOUT_READY", "UPTREND_CONFIRMED", "BASE_BUILDING", "EARLY_REVERSAL_CANDIDATE"})
WEAK_STATES = frozenset({"DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND"})
QUALIFIED_CATALYST_STATES = frozenset({"CONFIRMED_UPCOMING", "CONFIRMED_RECENT"})


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"thesis_catalyst_downside_research_cases:{digest}"}


def _evidence(*, source_dimension: str, metric_or_state: str, value: Any, as_of: str | None,
              method: str | None, tier: str, reason: str) -> dict[str, Any]:
    return {"source_dimension": source_dimension, "metric_or_state": metric_or_state, "value": value,
            "as_of": as_of, "method": method, "evidence_tier": tier, "reason": reason}


def _archetype(record: Mapping[str, Any]) -> str:
    classifications = record.get("research_classifications") or {}
    technical = record.get("market_technical_strength") or {}
    quality = record.get("fundamental_quality") or {}
    tactical = (record.get("tactical_setup") or {}).get("state")
    bucket = (record.get("opportunity_research_priority") or {}).get("bucket")
    if quality.get("status") == "INSUFFICIENT_INPUTS" and technical.get("status") == "READY_RESEARCH_ONLY":
        return "MARKET_ONLY_RESEARCH_CASE"
    if classifications.get("HIGH_RISK_SPECULATION", {}).get("status") == "RESEARCH_WARNING":
        return "HIGH_RISK_SPECULATION_THESIS"
    if classifications.get("SUPER_SETUP_RESEARCH", {}).get("status") == "PRESENT" and tactical == "BREAKOUT_READY":
        return "QUALITY_BREAKOUT_THESIS"
    if technical.get("market_technical_rank") == "EARLY_REVERSAL":
        return "EARLY_REVERSAL_THESIS"
    if tactical == "BASE_BUILDING" and quality.get("quality_band") == "HIGH_QUALITY":
        return "QUALITY_BASE_BUILDING_THESIS"
    if bucket == "HIGH_QUALITY_WEAK_SETUP":
        return "HIGH_QUALITY_WAIT_THESIS"
    if "VALUE_WITH_CONFIRMATION" in (record.get("opportunity_lanes") or []):
        return "VALUE_WITH_CONFIRMATION_THESIS"
    if quality.get("quality_band") == "HIGH_QUALITY" and technical.get("market_technical_rank") == "STRONG":
        return "QUALITY_MOMENTUM_THESIS"
    return "NO_BULLISH_ARCHETYPE"


def _case_class(record: Mapping[str, Any], archetype: str) -> str:
    quality = record.get("fundamental_quality") or {}
    technical = record.get("market_technical_strength") or {}
    if archetype == "MARKET_ONLY_RESEARCH_CASE":
        return "MARKET_ONLY_RESEARCH_CASE"
    if quality.get("status") == "READY_RESEARCH_ONLY" and technical.get("status") == "READY_RESEARCH_ONLY":
        return "OPPORTUNITY_CASE_ELIGIBLE"
    return "INSUFFICIENT_CASE_EVIDENCE"


def _thesis_evidence(record: Mapping[str, Any], archetype: str) -> list[dict[str, Any]]:
    session = record.get("market_session")
    quality = record.get("fundamental_quality") or {}
    technical = record.get("market_technical_strength") or {}
    tactical = record.get("tactical_setup") or {}
    axes = record.get("fundamental_axes") or {}
    reasons: list[dict[str, Any]] = []
    if quality.get("status") == "READY_RESEARCH_ONLY":
        reasons.append(_evidence(source_dimension="FUNDAMENTAL_QUALITY", metric_or_state="COMPARABLE_COHORT_PERCENTILE",
            value=quality.get("actual_comparable_cohort_percentile"), as_of=session, method=quality.get("method"),
            tier="OPERATIONAL_PROXY", reason="Existing comparable corporate-quality context."))
    for axis in ("PROFITABILITY_QUALITY", "CAPITAL_EFFICIENCY", "BALANCE_SHEET_TRAJECTORY"):
        item = axes.get(axis) or {}
        if item.get("axis_status") == "READY_RESEARCH_ONLY":
            reasons.append(_evidence(source_dimension="FUNDAMENTAL_AXIS", metric_or_state=axis, value=item.get("score"),
                as_of=session, method=item.get("method"), tier=item.get("evidence_tier", "OPERATIONAL_PROXY"),
                reason="Existing cross-sectional research feature."))
    if technical.get("status") == "READY_RESEARCH_ONLY":
        reasons.append(_evidence(source_dimension="CURRENT_MARKET_SETUP", metric_or_state=technical.get("market_technical_rank"),
            value=technical.get("momentum_20d"), as_of=session, method=technical.get("method"), tier="SHADOW_ONLY",
            reason="Existing current-session technical classification."))
    if tactical.get("state"):
        reasons.append(_evidence(source_dimension="TACTICAL_SETUP", metric_or_state=tactical["state"], value=tactical.get("rule_id"),
            as_of=session, method=tactical.get("method"), tier="SHADOW_ONLY", reason="Existing deterministic tactical state."))
    return reasons


def _event_detail(event: Mapping[str, Any], event_record: Mapping[str, Any] | None) -> dict[str, Any]:
    return {"event_identity": event.get("event_id"), "event_type": event.get("event_type"),
            "event_status": event.get("event_status"), "effective_or_expected_date": event.get("effective_date") or event.get("ex_date") or event.get("execution_date"),
            "as_of": (event_record or {}).get("research_session"), "known_at": event.get("known_at") or event.get("published_at"),
            "source": event.get("source"), "source_record_identity": event.get("source_record_identity"),
            "evidence_tier": event.get("evidence_tier"), "limitations": event.get("warnings") or []}


def _catalysts(event_record: Mapping[str, Any] | None) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    events = (event_record or {}).get("events") or []
    candidate_events = [event for event in events if event.get("event_status") in QUALIFIED_CATALYST_STATES
                        and event.get("evidence_tier") == "OFFICIAL_QUALIFIED"]
    catalysts: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    for event in candidate_events:
        detail = _event_detail(event, event_record)
        has_temporal_basis = bool(detail["effective_or_expected_date"] and detail["known_at"])
        thesis_linkage = event.get("thesis_linkage")
        if has_temporal_basis and thesis_linkage and event.get("causal_thesis_reason") and detail["event_identity"] and detail["event_type"] and detail["source_record_identity"]:
            catalysts.append({**detail, "thesis_linkage": thesis_linkage,
                              "reason": event.get("causal_thesis_reason"), "not_event_driven": True})
        else:
            contexts.append({**detail, "context_status": "RETAINED_EVENT_CONTEXT",
                             "reason": "Retained event lacks the explicit temporal-and-thesis linkage required for a qualified catalyst.",
                             "not_event_driven": True})
    gaps: list[dict[str, Any]] = []
    if not catalysts:
        gaps.append({"dimension": "CATALYST", "status": "EVIDENCE_GAP", "reason": "NO_QUALIFIED_CATALYST"})
    return ("QUALIFIED_CATALYST_AVAILABLE" if catalysts else "NO_QUALIFIED_CATALYST", catalysts, contexts, gaps)


def _counter_evidence(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    session = record.get("market_session")
    result: list[dict[str, Any]] = []
    technical = record.get("market_technical_strength") or {}
    quality = record.get("fundamental_quality") or {}
    tactical = record.get("tactical_setup") or {}
    if technical.get("market_technical_rank") == "WEAK":
        result.append(_evidence(source_dimension="CURRENT_MARKET_SETUP", metric_or_state="WEAK", value=tactical.get("state"),
            as_of=session, method=technical.get("method"), tier="SHADOW_ONLY", reason="Current retained technical setup is weak."))
    percentile = quality.get("actual_comparable_cohort_percentile")
    if isinstance(percentile, (int, float)) and percentile <= .25:
        result.append(_evidence(source_dimension="FUNDAMENTAL_QUALITY", metric_or_state="BOTTOM_QUARTILE_COMPARABLE_QUALITY",
            value=percentile, as_of=session, method=quality.get("method"), tier="OPERATIONAL_PROXY",
            reason="Weak comparable fundamental-quality evidence; this is not a portfolio action."))
    return result


def _technical_invalidation(record: Mapping[str, Any], case_class: str) -> dict[str, Any]:
    tactical = record.get("tactical_setup") or {}
    state, rule = tactical.get("state"), tactical.get("rule_id")
    if case_class != "OPPORTUNITY_CASE_ELIGIBLE" or not state:
        return {"status": "UNAVAILABLE", "reason": "CURRENT_TACTICAL_CASE_CHANNEL_UNAVAILABLE", "threshold": None}
    return {"status": "CONDITIONAL", "trigger_type": "RETAINED_TACTICAL_RULE_FAILURE",
            "threshold": None, "source_rule": rule, "as_of_session": record.get("market_session"),
            "reason": "The retained classifier supplies state/rule but no explicit structural price boundary."}


def _fundamental_invalidation(record: Mapping[str, Any], ttm_record: Mapping[str, Any] | None,
                              case_class: str, archetype: str) -> dict[str, Any]:
    if case_class != "OPPORTUNITY_CASE_ELIGIBLE":
        return {"status": "UNAVAILABLE", "reason": "FUNDAMENTAL_CASE_CHANNEL_UNAVAILABLE", "threshold": None}
    margin = ((ttm_record or {}).get("derived_metrics") or {}).get("ttm_net_margin") or {}
    ttm = (ttm_record or {}).get("ttm") or {}
    value = margin.get("value")
    income, revenue = ttm.get("net_income") or {}, ttm.get("revenue") or {}
    semantic_keys = ("provider", "statement_scope", "currency", "scale", "method")
    compatible = (margin.get("status") == "AVAILABLE" and isinstance(value, (int, float))
                  and all(income.get(key) == revenue.get(key) for key in semantic_keys))
    margin_led = archetype in {"QUALITY_MOMENTUM_THESIS", "QUALITY_BREAKOUT_THESIS", "QUALITY_BASE_BUILDING_THESIS", "HIGH_QUALITY_WAIT_THESIS"}
    if compatible and margin_led:
        return {"status": "READY", "trigger_type": "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT", "baseline": value,
                "threshold": value * .80, "comparison": "FUTURE_COMPATIBLE_NET_MARGIN_LTE_BASELINE_X_0_80",
                "scope": income.get("statement_scope"), "period_basis": income.get("method"),
                "method": margin.get("method"), "evidence_tier": margin.get("evidence_tier", "OPERATIONAL_PROXY"),
                "reason": "Margin-led research context with retained compatible rolling TTM inputs."}
    axes = record.get("fundamental_axes") or {}
    if (axes.get("PROFITABILITY_QUALITY") or {}).get("axis_status") == "READY_RESEARCH_ONLY":
        return {"status": "CONDITIONAL", "trigger_type": "COMPATIBLE_PROFITABILITY_QUALITY_DETERIORATION",
                "threshold": None, "source_rule": (axes["PROFITABILITY_QUALITY"]).get("method"),
                "reason": "A related profitability axis exists but no compatible numeric margin baseline is retained."}
    return {"status": "UNAVAILABLE", "reason": "NO_THESIS_RELATED_COMPATIBLE_FUNDAMENTAL_INVALIDATION_BASELINE", "threshold": None}


def _readiness(case_class: str, catalyst_status: str, technical: Mapping[str, Any], fundamental: Mapping[str, Any]) -> str:
    if case_class == "MARKET_ONLY_RESEARCH_CASE":
        return "MARKET_ONLY_RESEARCH_CASE"
    if case_class != "OPPORTUNITY_CASE_ELIGIBLE":
        return "INSUFFICIENT_CASE_EVIDENCE"
    if technical.get("status") != "READY" or fundamental.get("status") != "READY":
        return "RESEARCH_CASE_READY_WITH_PARTIAL_INVALIDATION"
    if catalyst_status == "NO_QUALIFIED_CATALYST":
        return "RESEARCH_CASE_READY_WITH_MISSING_CATALYST"
    return "RESEARCH_CASE_READY"


def _terminal_set_proof(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Make terminal-disposition set semantics inspectable and fail if they drift."""
    dispositions = ("OPPORTUNITY_CASE_ELIGIBLE", "MARKET_ONLY_RESEARCH_CASE", "INSUFFICIENT_CASE_EVIDENCE")
    sets = {name: sorted(ticker for ticker, record in records.items() if record["terminal_disposition"] == name)
            for name in dispositions}
    intersections = {f"{left}__INTERSECT__{right}": sorted(set(sets[left]) & set(sets[right]))
                     for index, left in enumerate(dispositions) for right in dispositions[index + 1:]}
    union = set().union(*(set(tickers) for tickers in sets.values()))
    if any(intersections.values()) or union != set(records):
        raise ValueError("TERMINAL_DISPOSITION_SET_RECONCILIATION_FAILED")
    return {"terminal_disposition_ticker_sets": sets,
            "pairwise_intersections": intersections,
            "union_count": len(union), "denominator": len(records), "residual": len(set(records) - union)}


def build_artifact(*, opportunity: Mapping[str, Any], events: Mapping[str, Any], ttm: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize one terminal case for each existing opportunity record."""
    opportunity_records = opportunity.get("records") or {}
    event_records = events.get("records") or {}
    ttm_records = ttm.get("records") or {}
    records: dict[str, dict[str, Any]] = {}
    coverage: Counter[str] = Counter()
    archetypes: Counter[str] = Counter()
    catalyst_event_ids: set[str] = set()
    catalyst_tickers: set[str] = set()
    context_event_ids: set[str] = set()
    context_tickers: set[str] = set()
    market_confirmation_trigger_count = 0
    technical_status: Counter[str] = Counter()
    fundamental_status: Counter[str] = Counter()
    for ticker in sorted(opportunity_records):
        source = opportunity_records[ticker]
        archetype = _archetype(source)
        case_class = _case_class(source, archetype)
        catalyst_status, catalysts, retained_event_context, catalyst_gaps = _catalysts(event_records.get(ticker))
        technical = _technical_invalidation(source, case_class)
        fundamental = _fundamental_invalidation(source, ttm_records.get(ticker), case_class, archetype)
        valuation = source.get("relative_value") or {}
        ttm_source = ttm_records.get(ticker) or {}
        gaps = list(catalyst_gaps)
        for name, candidate in (("VALUATION", valuation), ("TTM", ttm_source)):
            if not candidate or candidate.get("status") == "BLOCKED" or candidate.get("status") == "INSUFFICIENT_INPUTS":
                gaps.append({"dimension": name, "status": "EVIDENCE_GAP", "reason": "OPTIONAL_CONTEXT_UNAVAILABLE"})
        market_trigger = None
        tactical = source.get("tactical_setup") or {}
        if tactical.get("state") in CONSTRUCTIVE_STATES:
            market_trigger = {"trigger_type": "MARKET_CONFIRMATION_TRIGGER", "state": tactical.get("state"),
                              "source_rule": tactical.get("rule_id"), "as_of_session": source.get("market_session"),
                              "threshold": None, "reason": "Technical confirmation is distinct from a corporate catalyst."}
        record = {
            "ticker": ticker, "entity_class": source.get("entity_class"), "sector": source.get("sector"),
            "as_of_session": source.get("market_session"), "opportunity_bucket": (source.get("opportunity_research_priority") or {}).get("bucket"),
            "case_class": case_class, "thesis_archetype": archetype,
            "terminal_disposition": case_class,
            "thesis_evidence": _thesis_evidence(source, archetype), "catalyst_status": catalyst_status, "catalysts": catalysts,
            "retained_event_context": retained_event_context,
            "market_confirmation_trigger": market_trigger, "counter_thesis_evidence": _counter_evidence(source),
            "evidence_gaps": gaps, "technical_invalidation": technical, "fundamental_invalidation": fundamental,
            "valuation_context": {"relative_value": valuation, "size_context_only": (valuation.get("size_context") or {})},
            "ttm_context": {"status": ttm_source.get("status", "UNAVAILABLE"), "ttm": ttm_source.get("ttm") or {}, "derived_metrics": ttm_source.get("derived_metrics") or {}},
            "data_confidence": source.get("data_confidence") or {"status": "INSUFFICIENT_INPUTS", "score": None},
            "case_readiness": _readiness(case_class, catalyst_status, technical, fundamental),
            "warnings": sorted(set(source.get("warnings") or [])),
            "authority_boundaries": {"research_only": True, "case_is_not_decision_authority": True,
                                     "authoritative_issuer_count_unchanged": True, "new_evidence_acquired": False,
                                     "market_cap_and_ev_are_size_context_only": True, "confidence_is_not_attractiveness": True,
                                     "event_driven_authority": False, "pit": False},
        }
        records[ticker] = record
        coverage["valuation_enriched"] += valuation.get("status") == "READY_RESEARCH_ONLY"
        coverage["ttm_enriched"] += ((ttm_source.get("derived_metrics") or {}).get("ttm_net_margin") or {}).get("status") == "AVAILABLE"
        coverage["SUPER_SETUP_CASE"] += (source.get("research_classifications") or {}).get("SUPER_SETUP_RESEARCH", {}).get("status") == "PRESENT"
        coverage["HIGH_RISK_SPECULATION_CASE"] += archetype == "HIGH_RISK_SPECULATION_THESIS"
        coverage["complete_dual_invalidation"] += technical.get("status") == "READY" and fundamental.get("status") == "READY"
        coverage["margin_20pct_trigger"] += fundamental.get("trigger_type") == "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT"
        coverage["audit_risk_evidence"] += 0
        archetypes[archetype] += 1
        technical_status[technical["status"]] += 1
        fundamental_status[fundamental["status"]] += 1
        if catalysts:
            catalyst_tickers.add(ticker)
        if retained_event_context:
            context_tickers.add(ticker)
        catalyst_event_ids.update(str(item["event_identity"] or item["source_record_identity"]) for item in catalysts)
        context_event_ids.update(str(item["event_identity"] or item["source_record_identity"]) for item in retained_event_context)
        market_confirmation_trigger_count += market_trigger is not None
    terminal_proof = _terminal_set_proof(records)
    terminal_counts = {name: len(tickers) for name, tickers in terminal_proof["terminal_disposition_ticker_sets"].items()}
    readiness_distribution = dict(sorted(Counter(record["case_readiness"] for record in records.values()).items()))
    independent_flags = {
        "has_qualified_catalyst": len(catalyst_tickers),
        "has_retained_event_context": len(context_tickers),
        "has_market_confirmation_trigger": market_confirmation_trigger_count,
        "no_qualified_catalyst": sum(record["catalyst_status"] == "NO_QUALIFIED_CATALYST" for record in records.values()),
    }
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "denominator": len(records), "residual": 0,
        "source_artifacts": {"opportunity": opportunity.get("artifact_identity"), "events": events.get("artifact_identity"), "ttm": ttm.get("artifact_identity")},
        "coverage": {**dict(sorted(coverage.items())), "terminal_dispositions": terminal_counts,
                     "terminal_readiness_states": readiness_distribution, "independent_readiness_flags": independent_flags,
                     "catalysts": {"qualified_catalyst_tickers": len(catalyst_tickers), "qualified_catalyst_events": len(catalyst_event_ids),
                                   "retained_event_context_tickers": len(context_tickers), "retained_event_context_events": len(context_event_ids),
                                   "event_identity_sets_are_disjoint": not bool(catalyst_event_ids & context_event_ids)},
                     "thesis_archetypes": dict(sorted(archetypes.items())), "technical_invalidation": dict(sorted(technical_status.items())),
                     "fundamental_invalidation": dict(sorted(fundamental_status.items()))},
        "terminal_disposition_reconciliation": terminal_proof,
        "authority_boundary": {"research_only": True, "no_decision_authority": True, "no_new_evidence": True,
                               "authoritative_issuer_count_before": 13, "authoritative_issuer_count_after": 13,
                               "market_cap_and_ev_are_size_context_only": True, "valuation_and_ttm_optional": True},
        "records": records,
    }
    artifact.update(_identity(artifact))
    return artifact


def execute() -> dict[str, Any]:
    return build_artifact(opportunity=json.loads(OPPORTUNITY_INPUT.read_text(encoding="utf-8")),
                          events=json.loads(EVENT_INPUT.read_text(encoding="utf-8")),
                          ttm=json.loads(TTM_INPUT.read_text(encoding="utf-8")))
