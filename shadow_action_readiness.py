"""Deterministic experiment-only action posture and readiness over research cases.

Candidate postures and readiness gates are deliberately independent.  This module is a
read-only consumer of the case artifact and cannot create recommendation authority.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "shadow_action_readiness/v1"
CASE_INPUT = ROOT / "operations-review" / "thesis-catalyst-downside-and-dual-invalidation-v1-20260828" / "artifact.json"
STRONG_INITIATE_STATES = frozenset({"BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE"})
ACCUMULATION_STATES = frozenset({"BASE_BUILDING", "UPTREND_CONFIRMED"})
ADVERSE_STATES = frozenset({"DISTRIBUTION_RISK", "BREAKDOWN_RISK", "DOWNTREND"})
POSTURES = ("INITIATE_CANDIDATE", "ACCUMULATE_CANDIDATE", "WAIT_FOR_CONFIRMATION_CANDIDATE",
            "HIGH_RISK_SPECULATION_CANDIDATE", "AVOID_CANDIDATE", "INSUFFICIENT_ACTION_EVIDENCE")
READINESS_GATES = ("READY_SHADOW", "CONDITIONAL_SHADOW", "NOT_READY_SHADOW")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"shadow_action_readiness:{digest}"}


def _first_evidence(case: Mapping[str, Any], dimension: str) -> Mapping[str, Any]:
    return next((item for item in case.get("thesis_evidence") or [] if item.get("source_dimension") == dimension), {})


def _contexts(case: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    quality = _first_evidence(case, "FUNDAMENTAL_QUALITY")
    tactical = _first_evidence(case, "TACTICAL_SETUP")
    market = _first_evidence(case, "CURRENT_MARKET_SETUP")
    return ({"comparable_cohort_percentile": quality.get("value"), "ranking_basis": quality.get("method"),
             "evidence_tier": quality.get("evidence_tier"), "source_dimension": quality.get("source_dimension")},
            {"market_technical_rank": market.get("metric_or_state"), "momentum_20d": market.get("value"),
             "tactical_state": tactical.get("metric_or_state"), "tactical_rule": tactical.get("value"),
             "as_of_session": case.get("as_of_session")}, tactical.get("metric_or_state"))


def _posture(case: Mapping[str, Any], percentile: float | None, tactical_state: str | None) -> tuple[str, list[str]]:
    disposition = case.get("terminal_disposition")
    if disposition != "OPPORTUNITY_CASE_ELIGIBLE":
        return "INSUFFICIENT_ACTION_EVIDENCE", [
            "MARKET_ONLY_FUNDAMENTAL_CONTEXT_UNAVAILABLE" if disposition == "MARKET_ONLY_RESEARCH_CASE" else "TERMINAL_CASE_EVIDENCE_INSUFFICIENT"
        ]
    if case.get("thesis_archetype") == "HIGH_RISK_SPECULATION_THESIS":
        return "HIGH_RISK_SPECULATION_CANDIDATE", ["CONSTRUCTIVE_SETUP_WITH_BOTTOM_QUARTILE_CORPORATE_QUALITY", "RESEARCH_WARNING_ONLY"]
    if tactical_state in ADVERSE_STATES and isinstance(percentile, (int, float)) and percentile <= .25:
        return "AVOID_CANDIDATE", ["ADVERSE_TACTICAL_STATE", "BOTTOM_QUARTILE_CORPORATE_QUALITY"]
    if tactical_state in STRONG_INITIATE_STATES and isinstance(percentile, (int, float)) and percentile >= .80:
        return "INITIATE_CANDIDATE", ["STRONG_CONSTRUCTIVE_TACTICAL_STATE", "TOP_20_PERCENT_ACTUAL_CORPORATE_COHORT"]
    if tactical_state in ACCUMULATION_STATES and isinstance(percentile, (int, float)) and percentile >= .75:
        return "ACCUMULATE_CANDIDATE", ["CONSTRUCTIVE_NON_BREAKOUT_STRUCTURE", "HIGH_ACTUAL_CORPORATE_COHORT_QUALITY"]
    return "WAIT_FOR_CONFIRMATION_CANDIDATE", ["USEFUL_FUNDAMENTAL_MARKET_CASE_WITHOUT_STRONG_ACTION_POSTURE"]


def _readiness(case: Mapping[str, Any], posture: str) -> tuple[str, list[str]]:
    technical = case.get("technical_invalidation") or {}
    fundamental = case.get("fundamental_invalidation") or {}
    technical_status, fundamental_status = technical.get("status"), fundamental.get("status")
    if posture == "INSUFFICIENT_ACTION_EVIDENCE" or case.get("terminal_disposition") != "OPPORTUNITY_CASE_ELIGIBLE":
        return "NOT_READY_SHADOW", ["SUBSTANTIVE_ACTION_CASE_UNAVAILABLE"]
    if technical_status == "UNAVAILABLE" or fundamental_status == "UNAVAILABLE":
        return "NOT_READY_SHADOW", ["REQUIRED_INVALIDATION_CHANNEL_UNAVAILABLE"]
    if not case.get("as_of_session"):
        return "NOT_READY_SHADOW", ["CURRENT_SESSION_MARKET_EVIDENCE_INCOHERENT"]
    if technical_status == "READY" and fundamental_status == "READY":
        return "READY_SHADOW", ["COMPLETE_DUAL_INVALIDATION_RETAINED"]
    if technical_status in {"READY", "CONDITIONAL"} and fundamental_status in {"READY", "CONDITIONAL"}:
        if (technical_status != "READY" and not technical.get("source_rule")) or (fundamental_status != "READY" and not fundamental.get("source_rule")):
            return "NOT_READY_SHADOW", ["CONDITIONAL_INVALIDATION_RULE_IDENTITY_MISSING"]
        return "CONDITIONAL_SHADOW", ["DUAL_INVALIDATION_CONDITIONAL_WITH_RETAINED_RULE_IDENTITIES"]
    return "NOT_READY_SHADOW", ["ACTION_READINESS_REQUIREMENTS_NOT_MET"]


def build_artifact(*, research_cases: Mapping[str, Any]) -> dict[str, Any]:
    """Create one shadow action-readiness record per terminal research case."""
    source_records = research_cases.get("records") or {}
    records: dict[str, dict[str, Any]] = {}
    postures: Counter[str] = Counter()
    readiness: Counter[str] = Counter()
    cross_tab: Counter[str] = Counter()
    for ticker in sorted(source_records):
        case = source_records[ticker]
        fundamental_context, market_context, tactical_state = _contexts(case)
        percentile = fundamental_context["comparable_cohort_percentile"]
        posture, posture_reasons = _posture(case, percentile, tactical_state)
        gate, gate_reasons = _readiness(case, posture)
        record = {
            "ticker": ticker, "terminal_case_disposition": case.get("terminal_disposition"),
            "research_case_readiness": case.get("case_readiness"), "shadow_posture": posture,
            "shadow_posture_reason_codes": posture_reasons, "action_readiness_gate": gate,
            "readiness_reason_codes": gate_reasons, "fundamental_quality_context": fundamental_context,
            "market_setup_context": market_context, "technical_invalidation": case.get("technical_invalidation"),
            "fundamental_invalidation": case.get("fundamental_invalidation"),
            "fundamental_invalidation": case.get("fundamental_invalidation"),
            "market_confirmation_trigger": case.get("market_confirmation_trigger"),
            "qualified_catalyst": case.get("catalysts") or [], "retained_event_context": case.get("retained_event_context") or [],
            "valuation_context": case.get("valuation_context"), "ttm_context": case.get("ttm_context"),
            "negative_evidence": case.get("counter_thesis_evidence") or [], "evidence_gaps": case.get("evidence_gaps") or [],
            "authority_boundaries": {"experiment_shadow_only": True, "decision_authority_promoted": False,
                                     "portfolio_authority_promoted": False, "pit": False,
                                     "valuation_authority_promoted": False, "market_cap_and_ev_are_size_context_only": True},
            "warnings": sorted(set(case.get("warnings") or [])),
        }
        records[ticker] = record
        postures[posture] += 1
        readiness[gate] += 1
        cross_tab[f"{posture}__{gate}"] += 1
    terminal_dispositions = Counter(record["terminal_case_disposition"] for record in records.values())
    if len(records) != int(research_cases.get("denominator", len(records))) or sum(terminal_dispositions.values()) != len(records):
        raise ValueError("CASE_DENOMINATOR_RECONCILIATION_FAILED")
    valuation_enriched_postures = Counter(
        record["shadow_posture"] for record in records.values()
        if (record["valuation_context"] or {}).get("relative_value", {}).get("status") == "READY_RESEARCH_ONLY"
    )
    ttm_enriched_postures = Counter(
        record["shadow_posture"] for record in records.values()
        if (((record["ttm_context"] or {}).get("derived_metrics") or {}).get("ttm_net_margin") or {}).get("status") == "AVAILABLE"
    )
    for posture in POSTURES:
        postures.setdefault(posture, 0)
    for gate in READINESS_GATES:
        readiness.setdefault(gate, 0)
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "denominator": len(records), "residual": 0,
        "source_artifact": research_cases.get("artifact_identity"),
        "coverage": {"shadow_postures": dict(sorted(postures.items())), "action_readiness_gates": dict(sorted(readiness.items())),
                     "posture_by_readiness": dict(sorted(cross_tab.items())), "terminal_case_dispositions": dict(sorted(terminal_dispositions.items())),
                     "market_confirmation_trigger_count": sum(record["market_confirmation_trigger"] is not None for record in records.values()),
                     "qualified_catalyst_ticker_count": sum(bool(record["qualified_catalyst"]) for record in records.values()),
                     "retained_event_context_ticker_count": sum(bool(record["retained_event_context"]) for record in records.values()),
                     "valuation_enriched_postures": dict(sorted(valuation_enriched_postures.items())),
                     "ttm_enriched_postures": dict(sorted(ttm_enriched_postures.items()))},
        "authority_boundary": {"experiment_shadow_only": True, "no_recommendation_authority": True, "no_new_evidence": True,
                               "no_global_composite": True, "authoritative_issuer_count_before": 13, "authoritative_issuer_count_after": 13},
        "records": records,
    }
    artifact.update(_identity(artifact))
    return artifact


def execute() -> dict[str, Any]:
    return build_artifact(research_cases=json.loads(CASE_INPUT.read_text(encoding="utf-8")))
