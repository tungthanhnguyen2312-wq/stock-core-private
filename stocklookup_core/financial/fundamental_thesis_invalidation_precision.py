"""Rule-derived fundamental invalidation boundaries for experiment-only shadow research.

This module reuses only the empirical corporate-quality rules already used to produce the
current thesis and posture.  It neither acquires data nor creates a financial stop rule.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping


CONTRACT_VERSION = "fundamental_thesis_invalidation_precision/v1"
QUALITY_COHORT = "CORPORATE_VALID_FUNDAMENTAL_QUALITY_COHORT_EMPIRICAL_PERCENTILE/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"fundamental_thesis_invalidation_precision:{digest}"}


def _boundary(*, status: str, boundary_type: str | None = None, rule_identity: str | None = None,
              thesis_dimension: str | None = None, metric_or_axis: str | None = None,
              direction: str | None = None, threshold: float | None = None,
              baseline_value: float | None = None, baseline_period: str | None = None,
              comparison_basis: str | None = None, cohort_definition: str | None = None,
              future_evaluation_contract: str | None = None, statement_scope: str | None = None,
              period_basis: str | None = None, method: str | None = None,
              evidence_lineage: Mapping[str, Any] | None = None, warnings: list[str] | None = None,
              reason: str | None = None, current_trigger_state: str = "UNKNOWN") -> dict[str, Any]:
    return {
        "status": status, "boundary_type": boundary_type, "rule_identity": rule_identity,
        "source_rule": rule_identity, "thesis_dimension": thesis_dimension, "metric_or_axis": metric_or_axis,
        "direction": direction, "threshold": threshold, "baseline_value": baseline_value,
        "baseline_period": baseline_period, "comparison_basis": comparison_basis,
        "cohort_definition": cohort_definition, "future_evaluation_contract": future_evaluation_contract,
        "statement_scope": statement_scope, "period_basis": period_basis, "method": method,
        "evidence_lineage": dict(evidence_lineage or {}), "warnings": warnings or [], "reason": reason,
        "current_trigger_state": current_trigger_state,
    }


def _quality_transition(source: Mapping[str, Any], *, threshold: float, rule_identity: str,
                        direction: str, boundary_type: str, reason: str) -> dict[str, Any]:
    context = source.get("fundamental_quality_context") or {}
    percentile = context.get("comparable_cohort_percentile")
    cohort = context.get("ranking_basis")
    method = context.get("quality_method")
    if not isinstance(percentile, (int, float)) or cohort != QUALITY_COHORT or not method:
        return _boundary(
            status="CONDITIONAL", boundary_type=boundary_type, rule_identity=rule_identity,
            thesis_dimension="FUNDAMENTAL_QUALITY", metric_or_axis="COMPARABLE_COHORT_PERCENTILE",
            direction=direction, threshold=threshold, baseline_value=percentile if isinstance(percentile, (int, float)) else None,
            baseline_period=context.get("as_of"), comparison_basis="ACTUAL_VALID_CORPORATE_COHORT",
            cohort_definition=cohort, statement_scope="CORPORATE_VALID_COMPARABLE_COHORT",
            period_basis=context.get("period_basis"), method=method,
            warnings=["EXACT_EXISTING_QUALITY_THRESHOLD_LINEAGE_UNAVAILABLE"],
            reason="The current posture has a known threshold but lacks retained compatible cohort lineage.")
    comparison = "FUTURE_PERCENTILE_LT_THRESHOLD" if direction == "BELOW_TO_INVALIDATE" else "FUTURE_PERCENTILE_GT_THRESHOLD"
    return _boundary(
        status="READY", boundary_type=boundary_type, rule_identity=rule_identity,
        thesis_dimension="FUNDAMENTAL_QUALITY", metric_or_axis="COMPARABLE_COHORT_PERCENTILE",
        direction=direction, threshold=threshold, baseline_value=percentile, baseline_period=context.get("as_of"),
        comparison_basis=comparison, cohort_definition=cohort,
        future_evaluation_contract=(
            "Recompute the current ticker's empirical percentile against the actual valid corporate "
            "fundamental-quality cohort using AVAILABLE_FUNDAMENTAL_AXIS_MEAN/v1; evaluate the same "
            f"existing threshold ({comparison})."
        ), statement_scope="CORPORATE_VALID_COMPARABLE_COHORT",
        period_basis=context.get("period_basis") or "CURRENT_CROSS_SECTIONAL_RESEARCH", method=method,
        evidence_lineage={"cohort_size": context.get("cohort_size"), "evidence_tier": context.get("evidence_tier"),
                          "as_of": context.get("as_of"), "quality_method": method},
        reason=reason, current_trigger_state="NOT_TRIGGERED")


def _boundary_for(source: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    posture = source.get("shadow_posture")
    archetype = source.get("thesis_archetype")
    if source.get("terminal_case_disposition") != "OPPORTUNITY_CASE_ELIGIBLE":
        return "OTHER_EXISTING_RULE", _boundary(status="UNAVAILABLE", reason="FUNDAMENTAL_CASE_CHANNEL_UNAVAILABLE")
    if posture == "INITIATE_CANDIDATE":
        return "EXISTING_QUALITY_THRESHOLD_TRANSITION", _quality_transition(
            source, threshold=.80, rule_identity="SUPER_SETUP_PERCENTILE_FLOOR/v1", direction="BELOW_TO_INVALIDATE",
            boundary_type="FUNDAMENTAL_QUALITY_QUALIFICATION_LOST",
            reason="INITIATE_CANDIDATE uses the existing top-20-percent actual corporate-cohort qualification.")
    if posture == "ACCUMULATE_CANDIDATE":
        return "EXISTING_QUALITY_THRESHOLD_TRANSITION", _quality_transition(
            source, threshold=.75, rule_identity="HIGH_QUALITY_THRESHOLD/v1", direction="BELOW_TO_INVALIDATE",
            boundary_type="FUNDAMENTAL_QUALITY_QUALIFICATION_LOST",
            reason="ACCUMULATE_CANDIDATE uses the existing high-quality actual corporate-cohort qualification.")
    if posture == "AVOID_CANDIDATE":
        return "AVOID_RECOVERY_TRANSITION", _quality_transition(
            source, threshold=.25, rule_identity="HIGH_RISK_SPECULATION_PERCENTILE_CEILING/v1", direction="ABOVE_TO_REVERSE_NEGATIVE",
            boundary_type="FUNDAMENTAL_POSTURE_REVERSAL_BOUNDARY",
            reason="AVOID_CANDIDATE's weak-quality condition is reversed only when it no longer satisfies the existing bottom-quartile rule.")
    if archetype == "HIGH_QUALITY_WAIT_THESIS":
        return "EXISTING_QUALITY_THRESHOLD_TRANSITION", _quality_transition(
            source, threshold=.75, rule_identity="HIGH_QUALITY_THRESHOLD/v1", direction="BELOW_TO_INVALIDATE",
            boundary_type="FUNDAMENTAL_QUALITY_QUALIFICATION_LOST",
            reason="HIGH_QUALITY_WAIT_THESIS retains the existing high-quality qualification while market confirmation remains separate.")
    if posture == "HIGH_RISK_SPECULATION_CANDIDATE":
        return "OTHER_EXISTING_RULE", _boundary(
            status="CONDITIONAL", boundary_type="FUNDAMENTAL_RISK_STATE",
            rule_identity="HIGH_RISK_SPECULATION_PERCENTILE_CEILING/v1", thesis_dimension="FUNDAMENTAL_QUALITY",
            metric_or_axis="COMPARABLE_COHORT_PERCENTILE", direction="ABOVE_TO_REVERSE_NEGATIVE", threshold=.25,
            baseline_value=(source.get("fundamental_quality_context") or {}).get("comparable_cohort_percentile"),
            baseline_period=(source.get("fundamental_quality_context") or {}).get("as_of"),
            comparison_basis="EXISTING_BOTTOM_QUARTILE_RESEARCH_WARNING", cohort_definition=(source.get("fundamental_quality_context") or {}).get("ranking_basis"),
            statement_scope="CORPORATE_VALID_COMPARABLE_COHORT", period_basis="CURRENT_CROSS_SECTIONAL_RESEARCH",
            method=(source.get("fundamental_quality_context") or {}).get("quality_method"),
            warnings=["HIGH_RISK_SPECULATION_IS_A_RESEARCH_WARNING_NOT_A_POSITIVE_FUNDAMENTAL_THESIS"],
            reason="No positive thesis invalidation is fabricated for HIGH_RISK_SPECULATION.")
    prior = source.get("fundamental_invalidation") or {}
    if prior.get("status") == "READY" and prior.get("trigger_type") == "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT":
        return "MARGIN_RELATIVE_DRAWDOWN_20PCT", _boundary(
            status="READY", boundary_type="RELATIVE_DRAWDOWN", rule_identity="NET_MARGIN_RELATIVE_DRAWDOWN_20PCT",
            thesis_dimension="PROFITABILITY_QUALITY", metric_or_axis="ttm_net_margin", direction="BELOW_TO_INVALIDATE",
            threshold=prior.get("threshold"), baseline_value=prior.get("baseline"), baseline_period=prior.get("period_basis"),
            comparison_basis="FUTURE_COMPATIBLE_NET_MARGIN_LTE_BASELINE_X_0_80", statement_scope=prior.get("scope"),
            period_basis=prior.get("period_basis"), method=prior.get("method"),
            evidence_lineage={"evidence_tier": prior.get("evidence_tier")}, reason="Existing owner-approved margin-led research policy.",
            current_trigger_state="NOT_TRIGGERED")
    if prior.get("status") == "UNAVAILABLE":
        return "OTHER_EXISTING_RULE", _boundary(status="UNAVAILABLE", reason=prior.get("reason"))
    return "OTHER_EXISTING_RULE", _boundary(
        status="CONDITIONAL", boundary_type="STATE_TRANSITION", rule_identity=prior.get("source_rule"),
        thesis_dimension="FUNDAMENTAL_AXIS", metric_or_axis=prior.get("trigger_type"),
        warnings=["NO_EXPLICIT_THESIS_LINKED_QUALIFICATION_BOUNDARY"], reason=prior.get("reason"))


def build_artifact(*, shadow: Mapping[str, Any]) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    statuses: Counter[str] = Counter()
    families: Counter[str] = Counter()
    trigger_states: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    for ticker in sorted(shadow.get("records") or {}):
        source = shadow["records"][ticker]
        family, boundary = _boundary_for(source)
        records[ticker] = {
            "ticker": ticker, "shadow_posture": source.get("shadow_posture"), "thesis_archetype": source.get("thesis_archetype"),
            "fundamental_boundary": boundary, "boundary_rule_identity": boundary.get("rule_identity"),
            "boundary_type": boundary.get("boundary_type"), "boundary_status": boundary["status"],
            "current_trigger_state": boundary.get("current_trigger_state"), "baseline": boundary.get("baseline_value"),
            "comparison_method": boundary.get("comparison_basis"), "future_evaluation_contract": boundary.get("future_evaluation_contract"),
            "technical_boundary_summary": {"status": (source.get("technical_invalidation") or {}).get("status"),
                                           "rule": (source.get("technical_invalidation") or {}).get("source_rule")},
            "action_readiness_gate_before_precision": source.get("action_readiness_gate"), "warnings": boundary.get("warnings") or [],
            "authority_boundaries": {"experiment_shadow_only": True, "no_action_authority": True, "no_pit_promotion": True,
                                     "no_financial_threshold_invented": True},
        }
        statuses[boundary["status"]] += 1
        families[family] += boundary["status"] == "READY"
        trigger_states[boundary.get("current_trigger_state", "UNKNOWN")] += boundary["status"] == "READY"
        blockers.update(boundary.get("warnings") or [])
        if boundary["status"] != "READY" and boundary.get("reason"):
            blockers[str(boundary["reason"])] += 1
    if len(records) != int(shadow.get("denominator", len(records))):
        raise ValueError("SHADOW_DENOMINATOR_MISMATCH")
    for status in ("READY", "CONDITIONAL", "UNAVAILABLE"):
        statuses.setdefault(status, 0)
    for family in ("EXISTING_QUALITY_THRESHOLD_TRANSITION", "SIGN_TRANSITION", "MARGIN_RELATIVE_DRAWDOWN_20PCT",
                   "AXIS_STATE_TRANSITION", "BALANCE_SHEET_STATE_TRANSITION", "AVOID_RECOVERY_TRANSITION", "OTHER_EXISTING_RULE"):
        families.setdefault(family, 0)
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "denominator": len(records), "residual": 0,
        "source_artifact": shadow.get("artifact_identity"),
        "coverage": {"fundamental_boundary_status": dict(sorted(statuses.items())), "ready_by_rule_family": dict(sorted(families.items())),
                     "ready_current_trigger_states": dict(sorted(trigger_states.items())), "blockers": dict(sorted(blockers.items()))},
        "authority_boundary": {"experiment_shadow_only": True, "authoritative_issuer_count_before": 13,
                               "authoritative_issuer_count_after": 13, "no_recommendation_authority": True,
                               "no_new_evidence": True, "no_pit_promotion": True}, "records": records,
    }
    artifact.update(_identity(artifact))
    return artifact
