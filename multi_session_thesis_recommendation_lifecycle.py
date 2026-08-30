"""Prospective continuity over retained current-session research bundles only."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "multi_session_thesis_recommendation_lifecycle/v1"
RESEARCH_TIER = "PROSPECTIVE_MULTI_SESSION_RESEARCH_ONLY"
CONFIRMATION_STATES = frozenset({"BREAKOUT_READY"})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"multi_session_thesis_recommendation_lifecycle:{digest}"}


def _bundle_identity(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {"operation_identity": bundle.get("operation_identity"), "product_identity": bundle.get("product_identity"),
            "source_artifact_sha256": bundle.get("source_artifact_sha256")}


def _contexts(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    result = bundle.get("ticker_research_contexts")
    if not isinstance(result, Mapping):
        raise ValueError("SESSION_BUNDLE_TICKER_CONTEXTS_INVALID")
    return result


def _mapping_component(record: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    """Retain an upstream component unchanged when its structured form exists."""
    value = record.get(key)
    return value if isinstance(value, Mapping) else None


def _recommendation(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    candidate = record.get("recommendation")
    return candidate if isinstance(candidate, Mapping) else None


def _opportunity(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return _mapping_component(record, "research_priority")


def _tactical(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return _mapping_component(record, "current_decision_state")


def _strategy(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return _mapping_component(record, "strategy_fit")


def _scenario(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return _mapping_component(record, "scenario")


def _invalidation(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Only preserve an explicit upstream structured invalidation state."""
    return _mapping_component(record, "fundamental_invalidation")


def _transition(previous: Any, current: Any, *, name: str, previous_state: Any = None, current_state: Any = None) -> dict[str, Any]:
    if previous is None or current is None:
        return {"dimension": name, "transition": "MISSING", "previous": previous, "current": current,
                "previous_state": previous_state, "current_state": current_state}
    return {"dimension": name, "transition": "UNCHANGED" if previous_state == current_state else "STATE_CHANGED",
            "previous": previous, "current": current, "previous_state": previous_state, "current_state": current_state}


def _fields(source: Mapping[str, Any] | None, *names: str) -> dict[str, Any] | None:
    return None if source is None else {name: source.get(name) for name in names}


def _strategy_state(source: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if source is None:
        return None
    strategies = source.get("strategies")
    strategy_statuses = None
    if isinstance(strategies, list):
        strategy_statuses = [
            {"strategy_id": strategy.get("strategy_id"), "status": strategy.get("status")}
            for strategy in strategies if isinstance(strategy, Mapping)
        ]
    return {"status": source.get("status"), "eligible_strategy_ids": source.get("eligible_strategy_ids"),
            "scenario_relationship": source.get("scenario_relationship"), "strategy_statuses": strategy_statuses}


def _scenario_state(source: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if source is None:
        return None
    base = source.get("base_case")
    return {"status": source.get("status"), "probability_status": source.get("probability_status"),
            "base_case_status": base.get("case_status") if isinstance(base, Mapping) else None,
            "base_current_state": base.get("current_state") if isinstance(base, Mapping) else None}


def _tactical_transition(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> dict[str, Any]:
    prior = None if previous is None else previous.get("entry_state")
    now = None if current is None else current.get("entry_state")
    result = _transition(previous, current, name="TACTICAL",
                         previous_state=_fields(previous, "entry_state", "entry_action", "ticker_structure_state"),
                         current_state=_fields(current, "entry_state", "entry_action", "ticker_structure_state"))
    if prior is not None and now is not None and prior not in CONFIRMATION_STATES and now in CONFIRMATION_STATES:
        result["transition"] = "CONFIRMATION_GAINED"
    elif prior in CONFIRMATION_STATES and now not in CONFIRMATION_STATES:
        result["transition"] = "CONFIRMATION_LOST"
    return result


def _invalidation_transition(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> dict[str, Any]:
    prior = None if previous is None else previous.get("current_trigger_state")
    now = None if current is None else current.get("current_trigger_state")
    result = _transition(previous, current, name="FUNDAMENTAL_INVALIDATION",
                         previous_state=_fields(previous, "status", "current_trigger_state", "trigger_type", "reason"),
                         current_state=_fields(current, "status", "current_trigger_state", "trigger_type", "reason"))
    if prior != "TRIGGERED" and now == "TRIGGERED":
        result["transition"] = "INVALIDATION_ACTIVATED"
    elif prior == "TRIGGERED" and now != "TRIGGERED" and now is not None:
        result["transition"] = "INVALIDATION_CLEARED"
    return result


def _lifecycle(*, components: Sequence[Mapping[str, Any]]) -> str:
    invalidation = next(item for item in components if item["dimension"] == "FUNDAMENTAL_INVALIDATION")
    tactical = next(item for item in components if item["dimension"] == "TACTICAL")
    if invalidation["transition"] == "INVALIDATION_ACTIVATED":
        return "INVALIDATED"
    if tactical["transition"] == "CONFIRMATION_GAINED":
        return "CONFIRMED"
    available = [item for item in components if item["transition"] != "MISSING"]
    if not available:
        return "INSUFFICIENT_EVIDENCE"
    if all(item["transition"] == "UNCHANGED" for item in available):
        return "UNCHANGED"
    return "STATE_TRANSITION"


def _material(components: Sequence[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for item in components:
        if item["dimension"] == "RECOMMENDATION" and item["transition"] == "STATE_CHANGED":
            reasons.append("UPSTREAM_RECOMMENDATION_LABEL_CHANGED")
        elif item["dimension"] == "FUNDAMENTAL_INVALIDATION" and item["transition"] == "INVALIDATION_ACTIVATED":
            reasons.append("UPSTREAM_FUNDAMENTAL_INVALIDATION_ACTIVATED")
        elif item["dimension"] == "FUNDAMENTAL_INVALIDATION" and item["transition"] == "INVALIDATION_CLEARED":
            reasons.append("UPSTREAM_FUNDAMENTAL_INVALIDATION_CLEARED")
        elif item["dimension"] == "TACTICAL" and item["transition"] in {"CONFIRMATION_GAINED", "CONFIRMATION_LOST"}:
            reasons.append(f"TACTICAL_{item['transition']}")
        elif item["dimension"] == "OPPORTUNITY" and item["transition"] == "STATE_CHANGED":
            before, after = item["previous_state"], item["current_state"]
            if before.get("research_priority_tier") != "PRIORITY_NOW" and after.get("research_priority_tier") == "PRIORITY_NOW":
                reasons.append("HIGH_PRIORITY_OPPORTUNITY_GAINED")
            elif before.get("research_priority_tier") == "PRIORITY_NOW" and after.get("research_priority_tier") != "PRIORITY_NOW":
                reasons.append("HIGH_PRIORITY_OPPORTUNITY_LOST")
    return reasons


def _record(*, ticker: str, previous_session: str, current_session: str, previous: Mapping[str, Any] | None,
            current: Mapping[str, Any], previous_identity: Mapping[str, Any] | None, current_identity: Mapping[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {"ticker": ticker, "previous_session": None, "current_session": current_session,
                "previous_artifact_identity": None, "current_artifact_identity": current_identity,
                "thesis_lifecycle_state": "INITIAL_OBSERVATION", "component_transitions": [],
                "material_change": False, "material_change_reasons": [], "reason_codes": ["PREVIOUS_QUALIFIED_SESSION_RECORD_ABSENT"],
                "warnings": [], "missing_dimensions": ["PREVIOUS_SESSION_RECORD"], "research_tier": RESEARCH_TIER, "is_actionable": False,
                "current_recommendation": _recommendation(current), "previous_recommendation": None}
    previous_opportunity, current_opportunity = _opportunity(previous), _opportunity(current)
    previous_tactical, current_tactical = _tactical(previous), _tactical(current)
    previous_strategy, current_strategy = _strategy(previous), _strategy(current)
    previous_scenario, current_scenario = _scenario(previous), _scenario(current)
    previous_invalidation, current_invalidation = _invalidation(previous), _invalidation(current)
    components = [
        _transition(previous_opportunity, current_opportunity, name="OPPORTUNITY",
                    previous_state=_fields(previous_opportunity, "research_priority_tier", "entry_relevant", "lane_specific_priority", "status"),
                    current_state=_fields(current_opportunity, "research_priority_tier", "entry_relevant", "lane_specific_priority", "status")),
        _tactical_transition(previous_tactical, current_tactical),
        _transition(previous_strategy, current_strategy, name="STRATEGY", previous_state=_strategy_state(previous_strategy), current_state=_strategy_state(current_strategy)),
        _transition(previous_scenario, current_scenario, name="SCENARIO", previous_state=_scenario_state(previous_scenario), current_state=_scenario_state(current_scenario)),
        _invalidation_transition(previous_invalidation, current_invalidation),
        _transition(_recommendation(previous), _recommendation(current), name="RECOMMENDATION",
                    previous_state=None if _recommendation(previous) is None else _recommendation(previous).get("recommendation_label"),
                    current_state=None if _recommendation(current) is None else _recommendation(current).get("recommendation_label")),
    ]
    missing = [item["dimension"] for item in components if item["transition"] == "MISSING"]
    lifecycle = _lifecycle(components=components)
    reasons = _material(components)
    warnings = sorted(set((previous.get("authority_limitations") or []) + (current.get("authority_limitations") or [])))
    return {"ticker": ticker, "previous_session": previous_session, "current_session": current_session,
            "previous_artifact_identity": previous_identity, "current_artifact_identity": current_identity,
            "previous_opportunity_state": previous_opportunity, "current_opportunity_state": current_opportunity,
            "previous_tactical_state": previous_tactical, "current_tactical_state": current_tactical,
            "previous_strategy_state": previous_strategy, "current_strategy_state": current_strategy,
            "previous_invalidation_state": previous_invalidation, "current_invalidation_state": current_invalidation,
            "previous_recommendation": _recommendation(previous), "current_recommendation": _recommendation(current),
            "component_transitions": components, "thesis_lifecycle_state": lifecycle,
            "material_change": bool(reasons), "material_change_reasons": reasons,
            "reason_codes": [item["dimension"] + "_" + item["transition"] for item in components],
            "warnings": warnings, "missing_dimensions": missing, "research_tier": RESEARCH_TIER, "is_actionable": False}


def build_artifact(*, previous_bundle: Mapping[str, Any] | None, current_bundle: Mapping[str, Any],
                   qualified_session_chain: Sequence[str]) -> dict[str, Any]:
    current_session = current_bundle.get("session")
    if not isinstance(current_session, str):
        raise ValueError("CURRENT_SESSION_MISSING")
    if current_session not in qualified_session_chain:
        raise ValueError("CURRENT_SESSION_NOT_IN_GOVERNED_CHAIN")
    current_index = list(qualified_session_chain).index(current_session)
    current_contexts = _contexts(current_bundle)
    current_identity = _bundle_identity(current_bundle)
    if previous_bundle is None:
        records = {ticker: _record(ticker=ticker, previous_session="", current_session=current_session, previous=None, current=current_contexts[ticker], previous_identity=None, current_identity=current_identity) for ticker in sorted(current_contexts)}
        previous_session, previous_identity, previous_contexts = None, None, {}
    else:
        previous_session = previous_bundle.get("session")
        if not isinstance(previous_session, str) or current_index == 0 or list(qualified_session_chain)[current_index - 1] != previous_session:
            raise ValueError("PREVIOUS_SESSION_NOT_CONSECUTIVE_IN_GOVERNED_CHAIN")
        previous_contexts, previous_identity = _contexts(previous_bundle), _bundle_identity(previous_bundle)
        records = {ticker: _record(ticker=ticker, previous_session=previous_session, current_session=current_session,
                                   previous=previous_contexts.get(ticker), current=current_contexts[ticker],
                                   previous_identity=previous_identity, current_identity=current_identity)
                   for ticker in sorted(current_contexts)}
    state_counts = Counter(record["thesis_lifecycle_state"] for record in records.values())
    material = [record for record in records.values() if record["material_change"]]
    transitions = {name: Counter(next(item for item in record["component_transitions"] if item["dimension"] == name)["transition"]
                               for record in records.values() if record["component_transitions"])
                   for name in ("RECOMMENDATION", "TACTICAL", "FUNDAMENTAL_INVALIDATION", "OPPORTUNITY", "STRATEGY")}
    missing_dimensions = Counter(
        dimension
        for record in records.values()
        for dimension in record["missing_dimensions"]
    )
    warnings = [
        f"{dimension}_MISSING_FOR_{count}_CURRENT_RECORDS"
        for dimension, count in sorted(missing_dimensions.items())
    ]
    artifact: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "previous_session": previous_session, "current_session": current_session,
        "source_artifacts": {"previous": previous_identity, "current": current_identity}, "denominator": len(records),
        "comparable_count": sum(ticker in previous_contexts for ticker in records), "initial_only_count": sum(ticker not in previous_contexts for ticker in records),
        "previous_only_count": sum(ticker not in current_contexts for ticker in previous_contexts),
        "lifecycle_ready_count": sum(record["thesis_lifecycle_state"] != "INITIAL_OBSERVATION" for record in records.values()),
        "insufficient_evidence_count": sum(record["thesis_lifecycle_state"] == "INSUFFICIENT_EVIDENCE" for record in records.values()),
        "records": records, "coverage": {"lifecycle_states": dict(sorted(state_counts.items())), "material_change_count": len(material),
        "recommendation_transitions": dict(sorted(transitions["RECOMMENDATION"].items())), "tactical_transitions": dict(sorted(transitions["TACTICAL"].items())),
        "fundamental_invalidation_transitions": dict(sorted(transitions["FUNDAMENTAL_INVALIDATION"].items())), "opportunity_transitions": dict(sorted(transitions["OPPORTUNITY"].items())), "strategy_transitions": dict(sorted(transitions["STRATEGY"].items())), "missing_dimension_counts": dict(sorted(missing_dimensions.items()))},
        "warnings": warnings,
        "authority_effect": "NONE", "research_tier": RESEARCH_TIER, "is_actionable": False,
        "interpretation_limits": ["PROSPECTIVE_RETAINED_SESSION_CONTINUITY_ONLY", "NO_NEW_RECOMMENDATION_OR_ACTION", "NO_PERFORMANCE_ATTRIBUTION_BACKTEST_PIT_OR_RAW_AS_TRADED_AUTHORITY"]}
    artifact.update(_identity(artifact))
    return artifact
