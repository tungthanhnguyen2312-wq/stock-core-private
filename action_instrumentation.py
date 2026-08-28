"""Precision instrumentation for experiment-only shadow action readiness.

Only numerical intermediates already used by the tactical classifier are exposed.  This module
does not modify posture or invent price levels, future fundamentals, or decision authority.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "action_instrumentation_and_invalidation_precision/v1"
SHADOW_INPUT = ROOT / "operations-review" / "shadow-action-readiness-v1-20260828" / "artifact.json"
TACTICAL_INPUT = ROOT / "operations-review" / "watchlist-tactical-entry-decision-v1-20260825" / "watchlist_tactical_entry_classifier_artifact.json"
DESCRIPTIVE_INPUT = ROOT / "operations-review" / "market-wide-current-descriptive-research-v1-20260825" / "market_wide_current_descriptive_research_artifact.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"action_instrumentation:{digest}"}


def _boundary(*, status: str, boundary_type: str | None = None, direction: str | None = None,
              value: float | None = None, unit: str | None = None, comparison_operator: str | None = None,
              source_rule: str | None = None, source_metric: str | None = None,
              baseline_value: float | None = None, baseline_period_session: str | None = None,
              as_of: str | None = None, method: str | None = None, lineage: Mapping[str, Any] | None = None,
              warnings: list[str] | None = None, reason: str | None = None) -> dict[str, Any]:
    return {"status": status, "boundary_type": boundary_type, "direction": direction, "value": value,
            "unit": unit, "comparison_operator": comparison_operator, "source_rule": source_rule,
            "source_metric": source_metric, "baseline_value": baseline_value,
            "baseline_period_session": baseline_period_session, "as_of": as_of, "method": method,
            "evidence_lineage": dict(lineage or {}), "warnings": warnings or [], "reason": reason}


def _technical_context(tactical: Mapping[str, Any] | None, descriptive: Mapping[str, Any] | None) -> tuple[dict[str, Any], str | None]:
    tactical = tactical or {}
    feature = (descriptive or {}).get("technical_features") or {}
    values = feature.get("values") or {}
    session = feature.get("feature_as_of_session")
    price_basis = feature.get("price_basis")
    eligible = feature.get("is_current_session") is True and feature.get("status") == "SHADOW_ONLY"
    lineage = {"tactical_artifact": "watchlist_tactical_entry_classifier/v1", "rule_id": tactical.get("rule_id"),
               "technical_source": (feature.get("technical_history_provenance") or {}).get("source"), "price_basis": price_basis,
               "adjustment_basis": price_basis, "feature_as_of_session": session}
    return {"state": tactical.get("entry_state"), "rule_id": tactical.get("rule_id"), "signals": tactical.get("signals") or {},
            "values": values, "session": session, "price_basis": price_basis, "eligible": eligible, "lineage": lineage}, price_basis


def _ma_boundary(*, kind: str, direction: str, operator: str, context: Mapping[str, Any], reason: str) -> dict[str, Any]:
    ma20 = context["values"].get("ma_20")
    if not context["eligible"] or not isinstance(ma20, (int, float)) or context.get("price_basis") != "ADJUSTED_RETROSPECTIVE":
        return _boundary(status="CONDITIONAL", boundary_type=kind, direction=direction, source_rule=context.get("rule_id"),
                         source_metric="ma_20", as_of=context.get("session"), method="watchlist_tactical_entry_classifier/v1",
                         lineage=context.get("lineage"), warnings=["EXACT_MA20_INPUT_OR_COMPATIBLE_PRICE_BASIS_UNAVAILABLE"], reason=reason)
    return _boundary(status="READY", boundary_type=kind, direction=direction, value=ma20, unit="ADJUSTED_RETROSPECTIVE_PRICE",
                     comparison_operator=operator, source_rule=context.get("rule_id"), source_metric="ma_20",
                     baseline_value=ma20, baseline_period_session=context.get("session"), as_of=context.get("session"),
                     method="watchlist_tactical_entry_classifier/v1 dynamic MA20 state transition", lineage=context.get("lineage"), reason=reason)


def _momentum_boundary(*, kind: str, direction: str, operator: str, context: Mapping[str, Any], reason: str) -> dict[str, Any]:
    momentum = context["values"].get("momentum_20d")
    if not context["eligible"] or not isinstance(momentum, (int, float)):
        return _boundary(status="CONDITIONAL", boundary_type=kind, direction=direction, source_rule=context.get("rule_id"),
                         source_metric="momentum_20d", as_of=context.get("session"), method="watchlist_tactical_entry_classifier/v1",
                         lineage=context.get("lineage"), warnings=["EXACT_MOMENTUM_INPUT_UNAVAILABLE"], reason=reason)
    return _boundary(status="READY", boundary_type=kind, direction=direction, value=0.0, unit="RETURN_RATIO",
                     comparison_operator=operator, source_rule=context.get("rule_id"), source_metric="momentum_20d",
                     baseline_value=momentum, baseline_period_session=context.get("session"), as_of=context.get("session"),
                     method="watchlist_tactical_entry_classifier/v1 momentum-sign transition", lineage=context.get("lineage"), reason=reason)


def _technical_boundaries(posture: str, context: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = context.get("state")
    unavailable = _boundary(status="UNAVAILABLE", reason="ACTION_POSTURE_HAS_NO_RETAINED_TECHNICAL_BOUNDARY")
    if posture == "INSUFFICIENT_ACTION_EVIDENCE":
        return unavailable, unavailable, unavailable
    if posture == "AVOID_CANDIDATE":
        if state in {"BREAKDOWN_RISK", "DISTRIBUTION_RISK"}:
            reversal = _ma_boundary(kind="POSTURE_REVERSAL_MA20_RECLAIM" if state == "BREAKDOWN_RISK" else "POSTURE_REVERSAL_MOMENTUM_RECOVERY",
                direction="ABOVE_TO_REVERSE_NEGATIVE", operator="FUTURE_CLOSE_GT_FUTURE_MA20" if state == "BREAKDOWN_RISK" else "FUTURE_MOMENTUM_20D_GT_0",
                context=context, reason="Existing classifier recovery condition for the adverse state.") if state == "BREAKDOWN_RISK" else _momentum_boundary(
                kind="POSTURE_REVERSAL_MOMENTUM_RECOVERY", direction="ABOVE_TO_REVERSE_NEGATIVE", operator="FUTURE_MOMENTUM_20D_GT_0", context=context,
                reason="Existing classifier recovery condition for the adverse state.")
            return unavailable, unavailable, reversal
        reversal = _momentum_boundary(kind="POSTURE_REVERSAL_MOMENTUM_RECOVERY", direction="ABOVE_TO_REVERSE_NEGATIVE",
            operator="FUTURE_MOMENTUM_20D_GT_0", context=context, reason="Existing downtrend stabilization condition.")
        return unavailable, unavailable, reversal
    if state == "EARLY_REVERSAL_CANDIDATE":
        confirmation = _ma_boundary(kind="EARLY_REVERSAL_CONFIRMATION_MA20_RECLAIM", direction="ABOVE_TO_CONFIRM",
            operator="FUTURE_CLOSE_GT_FUTURE_MA20", context=context, reason="Existing R6 confirmation requires reclaiming MA20.")
        risk = _momentum_boundary(kind="EARLY_REVERSAL_MOMENTUM_FAILURE", direction="BELOW_TO_INVALIDATE",
            operator="FUTURE_MOMENTUM_20D_LT_0", context=context, reason="Existing R6 invalidation is momentum turning negative.")
        return confirmation, risk, unavailable
    if state in {"BREAKOUT_READY", "UPTREND_CONFIRMED"}:
        entry = _boundary(status="CONDITIONAL", boundary_type="ONGOING_EXTENSION_CONFIRMATION", direction="STATE_TRANSITION",
            source_rule=context.get("rule_id"), source_metric="entry_state", as_of=context.get("session"),
            method="watchlist_tactical_entry_classifier/v1", lineage=context.get("lineage"),
            warnings=["EXISTING_RULE_REQUIRES_NEXT_SESSION_EXTENSION_WITHOUT_FIXED_PRICE_LEVEL"],
            reason="The current classifier has no retained fixed next-session extension threshold.")
        risk = _ma_boundary(kind="TREND_MA20_FAILURE", direction="BELOW_TO_INVALIDATE", operator="FUTURE_CLOSE_LT_FUTURE_MA20",
            context=context, reason="Existing state rules depend on MA20 structure.") if state == "BREAKOUT_READY" else _momentum_boundary(
            kind="UPTREND_MOMENTUM_FAILURE", direction="BELOW_TO_INVALIDATE", operator="FUTURE_MOMENTUM_20D_LT_0", context=context,
            reason="Existing R3 invalidation is a momentum rollover while above MA20.")
        return entry, risk, unavailable
    if state == "BASE_BUILDING":
        return _boundary(status="CONDITIONAL", boundary_type="BASE_RESOLUTION", direction="ABOVE_TO_CONFIRM", source_rule=context.get("rule_id"),
            source_metric="ma_20_or_momentum_20d", as_of=context.get("session"), method="watchlist_tactical_entry_classifier/v1",
            lineage=context.get("lineage"), warnings=["EXISTING_RULE_HAS_DISJUNCTIVE_CONFIRMATION_WITHOUT_SINGLE_FIXED_BOUNDARY"],
            reason="R7 confirms through either momentum sign or MA20 reclaim."), _boundary(status="CONDITIONAL", boundary_type="BASE_FAILURE",
            direction="STATE_TRANSITION", source_rule=context.get("rule_id"), source_metric="relative_volume_and_momentum", as_of=context.get("session"),
            method="watchlist_tactical_entry_classifier/v1", lineage=context.get("lineage"), warnings=["MULTI_SIGNAL_RULE_NOT_REDUCED_TO_A_FABRICATED_PRICE_LEVEL"], reason="R7 invalidation is multi-signal."), unavailable
    return _boundary(status="CONDITIONAL", boundary_type="CATEGORICAL_TACTICAL_STATE", direction="STATE_TRANSITION", source_rule=context.get("rule_id"),
        as_of=context.get("session"), method="watchlist_tactical_entry_classifier/v1", lineage=context.get("lineage"),
        warnings=["CURRENT_STATE_HAS_NO_POSTURE-SPECIFIC_EXACT_BOUNDARY"], reason="Categorial state retained without applicable exact action boundary."), unavailable, unavailable


def _fundamental_boundary(shadow: Mapping[str, Any], precision: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if precision and precision.get("fundamental_boundary"):
        return dict(precision["fundamental_boundary"])
    prior = shadow.get("fundamental_invalidation") or {}
    if prior.get("status") == "READY" and prior.get("trigger_type") == "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT":
        return _boundary(status="READY", boundary_type="NET_MARGIN_RELATIVE_DRAWDOWN_20PCT", direction="RELATIVE_DRAWDOWN",
            value=prior.get("threshold"), unit="NET_MARGIN_RATIO", comparison_operator="FUTURE_COMPATIBLE_NET_MARGIN_LTE_BASELINE_X_0_80",
            source_rule=prior.get("trigger_type"), source_metric="ttm_net_margin", baseline_value=prior.get("baseline"),
            baseline_period_session=prior.get("period_basis"), as_of=prior.get("as_of"), method=prior.get("method"),
            lineage={"evidence_tier": prior.get("evidence_tier"), "scope": prior.get("scope")}, reason="Existing margin-led case policy.")
    if prior.get("status") == "UNAVAILABLE":
        return _boundary(status="UNAVAILABLE", reason=prior.get("reason"))
    return _boundary(status="CONDITIONAL", boundary_type=prior.get("trigger_type"), direction="STATE_TRANSITION",
        source_rule=prior.get("source_rule"), as_of=shadow.get("as_of_session"), method="thesis_catalyst_downside_research_cases/v1",
        warnings=["NO_COMPATIBLE_NUMERIC_THESIS_BASELINE_RETAINED"], reason=prior.get("reason"))


def _gate(shadow: Mapping[str, Any], technical: Mapping[str, Any], fundamental: Mapping[str, Any]) -> str:
    posture = shadow.get("shadow_posture")
    if posture == "INSUFFICIENT_ACTION_EVIDENCE" or shadow.get("action_readiness_gate") == "NOT_READY_SHADOW":
        return "NOT_READY_SHADOW"
    if posture in {"INITIATE_CANDIDATE", "ACCUMULATE_CANDIDATE", "HIGH_RISK_SPECULATION_CANDIDATE"} and technical.get("status") == "READY" and fundamental.get("status") == "READY":
        return "READY_SHADOW"
    return shadow.get("action_readiness_gate")


def build_artifact(*, shadow: Mapping[str, Any], tactical: Mapping[str, Any], descriptive: Mapping[str, Any],
                   fundamental_boundaries_by_ticker: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    coverage: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    tactical_records, descriptive_records = tactical.get("records") or {}, descriptive.get("records") or {}
    for ticker in sorted(shadow.get("records") or {}):
        source = shadow["records"][ticker]
        context, price_basis = _technical_context(tactical_records.get(ticker), descriptive_records.get(ticker))
        entry, technical_risk, reversal = _technical_boundaries(source.get("shadow_posture"), context)
        fundamental = _fundamental_boundary(source, (fundamental_boundaries_by_ticker or {}).get(ticker))
        gate = _gate(source, technical_risk, fundamental)
        record = {"ticker": ticker, "shadow_posture": source.get("shadow_posture"), "action_readiness_gate": gate,
                  "entry_or_confirmation_boundary": entry, "technical_risk_boundary": technical_risk,
                  "fundamental_thesis_boundary": fundamental, "posture_reversal_boundary": reversal,
                  "market_confirmation_trigger": source.get("market_confirmation_trigger"), "technical_state": context.get("state"),
                  "fundamental_thesis_archetype": source.get("thesis_archetype"),
                  "boundary_compatibility": {"price_basis": price_basis, "price_basis_compatible": price_basis == "ADJUSTED_RETROSPECTIVE",
                                              "current_session_technical": context.get("eligible")},
                  "reason_codes": [item for item in (entry.get("reason"), technical_risk.get("reason"), fundamental.get("reason"), reversal.get("reason")) if item],
                  "warnings": sorted(set(source.get("warnings") or [])),
                  "authority_boundaries": {"experiment_shadow_only": True, "decision_authority_promoted": False, "pit": False,
                                           "price_basis_not_raw_as_traded": True, "valuation_authority_promoted": False}}
        records[ticker] = record
        for name, boundary in (("ENTRY_OR_CONFIRMATION", entry), ("TECHNICAL_RISK_BOUNDARY", technical_risk),
                               ("FUNDAMENTAL_BOUNDARY", fundamental), ("POSTURE_REVERSAL_BOUNDARY", reversal)):
            coverage[f"{name}_{boundary['status']}"] += 1
            for warning in boundary.get("warnings") or []:
                blocker_counts[warning] += 1
        coverage[f"READINESS_{gate}"] += 1
        if source.get("shadow_posture") in {"INITIATE_CANDIDATE", "ACCUMULATE_CANDIDATE", "HIGH_RISK_SPECULATION_CANDIDATE"} and technical_risk["status"] == fundamental["status"] == "READY":
            coverage["COMPLETE_TECHNICAL_PLUS_FUNDAMENTAL_INSTRUMENTATION"] += 1
            coverage[f"COMPLETE_TECHNICAL_PLUS_FUNDAMENTAL_{source.get('shadow_posture')}"] += 1
        if source.get("shadow_posture") in {"INITIATE_CANDIDATE", "ACCUMULATE_CANDIDATE"}:
            coverage["COMPLETE_POSITIVE_ACTION_INSTRUMENTATION"] += entry["status"] == technical_risk["status"] == fundamental["status"] == "READY"
        if source.get("shadow_posture") == "HIGH_RISK_SPECULATION_CANDIDATE":
            coverage["COMPLETE_SPECULATIVE_INSTRUMENTATION"] += technical_risk["status"] == fundamental["status"] == "READY"
        if source.get("shadow_posture") == "AVOID_CANDIDATE":
            coverage["COMPLETE_AVOID_MONITORING_INSTRUMENTATION"] += reversal["status"] == "READY"
    if len(records) != int(shadow.get("denominator", len(records))):
        raise ValueError("SHADOW_DENOMINATOR_MISMATCH")
    for name in ("ENTRY_OR_CONFIRMATION", "TECHNICAL_RISK_BOUNDARY", "FUNDAMENTAL_BOUNDARY", "POSTURE_REVERSAL_BOUNDARY"):
        for status in ("READY", "CONDITIONAL", "UNAVAILABLE"):
            coverage.setdefault(f"{name}_{status}", 0)
    for gate in ("READY_SHADOW", "CONDITIONAL_SHADOW", "NOT_READY_SHADOW"):
        coverage.setdefault(f"READINESS_{gate}", 0)
    for posture in ("INITIATE_CANDIDATE", "ACCUMULATE_CANDIDATE", "HIGH_RISK_SPECULATION_CANDIDATE"):
        coverage.setdefault(f"COMPLETE_TECHNICAL_PLUS_FUNDAMENTAL_{posture}", 0)
    coverage.setdefault("COMPLETE_TECHNICAL_PLUS_FUNDAMENTAL_INSTRUMENTATION", 0)
    coverage["MARKET_CONFIRMATION_EXACT_LEVEL"] = sum(
        record["market_confirmation_trigger"] is not None and record["entry_or_confirmation_boundary"]["status"] == "READY"
        for record in records.values()
    )
    coverage["MARGIN_LED_EXACT_BOUNDARY"] = sum(
        record["fundamental_thesis_boundary"].get("trigger_type") == "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT"
        for record in records.values()
    )
    coverage["PRICE_BASIS_BLOCKER_COUNT"] = sum(not record["boundary_compatibility"]["price_basis_compatible"] for record in records.values())
    artifact: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "denominator": len(records), "residual": 0,
        "source_artifacts": {"shadow": shadow.get("artifact_identity"), "tactical": tactical.get("artifact_identity"), "descriptive": descriptive.get("artifact_identity")},
        "coverage": {**dict(sorted(coverage.items())), "boundary_blockers": dict(sorted(blocker_counts.items()))},
        "authority_boundary": {"experiment_shadow_only": True, "authoritative_issuer_count_before": 13, "authoritative_issuer_count_after": 13,
                               "no_decision_authority": True, "no_new_evidence": True}, "records": records}
    artifact.update(_identity(artifact))
    return artifact


def execute() -> dict[str, Any]:
    return build_artifact(shadow=json.loads(SHADOW_INPUT.read_text(encoding="utf-8")), tactical=json.loads(TACTICAL_INPUT.read_text(encoding="utf-8")), descriptive=json.loads(DESCRIPTIVE_INPUT.read_text(encoding="utf-8")))
