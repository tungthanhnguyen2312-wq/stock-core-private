"""Level-2 current-session package: temporal classification and post-close fallback.

Canonical Daily Producer remains the governed path. This module does not generate
triage, does not silently reuse a prior-session triage as exact-session input, and
does not advertise triage-dependent scenario/strategy/opportunity outputs as
current-session clean.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from daily_producer_pipeline import DailyProducerError, completed_session_gate
from daily_research_session_operations import load_registry
from mva_exact_session_snapshot import resolved_completed_session
from vn_time import VN_TZ, vn_now

CONTRACT_VERSION = "daily_session_level2_package/v2"
PACKAGE_CLASSIFICATION = "LEVEL_2_GOVERNED_COMPONENT_PACKAGE"
LATEST_COMPLETED_TOKENS = frozenset({"latest-completed", "latest_completed", "LATEST_COMPLETED"})
TACTICAL_SIGNAL_STATES = (
    "BREAKOUT_READY",
    "BASE_BUILDING",
    "EARLY_REVERSAL_CANDIDATE",
    "UPTREND_CONFIRMED",
)
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")

EXACT_SESSION_CLEAN = "EXACT_SESSION_CLEAN"
VALID_PRIOR_CONTEXT_REUSE = "VALID_PRIOR_CONTEXT_REUSE"
BLOCKED_BY_STALE_TRIAGE_DEPENDENCY = "BLOCKED_BY_STALE_TRIAGE_DEPENDENCY"
UNAVAILABLE_REQUIRED_INPUT = "UNAVAILABLE_REQUIRED_INPUT"

ROOT_DEFAULT = Path(__file__).resolve().parent
FALLBACK_RECOVERY_BASELINE = Path("operations-review/market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json")


def _prior_completed_descriptive(root: Path, session: str) -> Path:
    """Use the latest governed completed-session descriptive strictly before target; never glob."""
    registry = load_registry(root)
    prior = sorted(name for name in (registry.get("completed_sessions") or {}) if str(name) < session)
    if prior:
        selection = (registry.get("sessions") or {}).get(prior[-1]) or {}
        entry = selection.get("descriptive") if isinstance(selection, Mapping) else None
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str):
            path = root / entry["path"]
            if path.is_file():
                return path
    fallback = root / FALLBACK_RECOVERY_BASELINE
    if fallback.is_file():
        return fallback
    raise FileNotFoundError("RECOVERY_BASELINE_DESCRIPTIVE_UNAVAILABLE")


def _iso_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError as exc:
        raise ValueError("INVALID_SESSION_FORMAT") from exc


def resolve_level2_session(session_arg: str | None, *, now: datetime | None = None) -> dict[str, Any]:
    """Resolve the target completed trading session.

    Omitted session and ``latest-completed`` use ``mva_exact_session_snapshot.resolved_completed_session``
    (weekday calendar + VN 15:00 close), never civil ``today`` and never a second calendar.
    Explicit ``YYYY-MM-DD`` is replay/reproducibility.
    """
    now = now or vn_now()
    local = now.astimezone(VN_TZ) if now.tzinfo else now.replace(tzinfo=VN_TZ)
    if session_arg is None or str(session_arg).strip() in LATEST_COMPLETED_TOKENS or str(session_arg).strip() == "":
        selected = resolved_completed_session(local)
        return {
            "session": selected,
            "resolution_mode": "LATEST_COMPLETED_WORKING_DATE",
            "policy": "mva_exact_session_snapshot.resolved_completed_session/freshness_history.latest_completed_market_day",
            "observed_at": local.isoformat(timespec="seconds"),
        }
    selected = _iso_date(str(session_arg).strip())
    return {
        "session": selected,
        "resolution_mode": "EXPLICIT_SESSION",
        "policy": "explicit_YYYY-MM-DD_replay",
        "observed_at": local.isoformat(timespec="seconds"),
    }


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _artifact_identity(payload: Mapping[str, Any] | None) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for key in ("artifact_identity", "snapshot_identity"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _artifact_session(payload: Mapping[str, Any] | None) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for key in (
        "session",
        "source_market_session",
        "research_session",
        "valuation_session",
        "resolved_completed_session",
        "target_session",
        "as_of",
        "current_research_as_of",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    input_candidates = payload.get("input_candidates")
    if isinstance(input_candidates, Mapping):
        value = input_candidates.get("resolved_completed_session")
        if isinstance(value, str) and value:
            return value
    return None


def _source_identities(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    for key in ("source_artifact_identities", "source_artifacts", "input_lineage", "source_lineage", "source_contexts"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def session_artifact_paths(root: Path, session: str) -> dict[str, Path]:
    ops = root / "operations-review"
    nodash = session.replace("-", "")
    return {
        "exact_session_snapshot": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f9b_mva_exact_session_snapshot.json",
        "p3f7_bundle": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f7_mva_daily_research_bundle_exact_session.json",
        "p3f8_run": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f8_mva_operational_run_exact_session.json",
        "dnse_only_exact_session_snapshot": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "dnse_only_exact_session_snapshot.json",
        "multi_source_market_evidence": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "multi_source_exact_session_market_evidence.json",
        "breadth_foundation": ops / f"current-market-universe-breadth-foundation-v1-{nodash}" / "current_market_universe_breadth_foundation_artifact.json",
        "universe_resolution": ops / f"current-universe-status-and-session-coverage-resolution-v1-{nodash}" / "current_universe_status_and_session_coverage_resolution_artifact.json",
        "liquidity_research": ops / f"market-wide-current-liquidity-research-v1-{nodash}" / "market_wide_current_liquidity_research_artifact.json",
        "technical_recovery": ops / f"market-wide-current-technical-coverage-scaleout-v1-{nodash}" / "market_wide_current_technical_coverage_recovery_artifact.json",
        "descriptive_research": ops / f"market-wide-current-descriptive-research-v1-{nodash}" / "market_wide_current_descriptive_research_artifact.json",
        "screening_foundation": ops / f"current-market-screening-opportunity-comparison-foundation-v1-{nodash}" / "current_market_screening_opportunity_comparison_foundation_artifact.json",
        "tactical_classifier": ops / f"watchlist-tactical-entry-decision-v1-{nodash}" / "watchlist_tactical_entry_classifier_artifact.json",
        "corporate_intelligence": ops / f"market-wide-current-corporate-intelligence-v1-{nodash}" / "market_wide_current_corporate_intelligence_artifact.json",
        "valuation": ops / f"market-wide-current-valuation-v1-{nodash}-session{nodash}" / "market_wide_current_valuation_artifact.json",
        "sector_leadership": ops / f"current-market-sector-leadership-context-v1-{nodash}" / "current_market_sector_leadership_context_artifact.json",
        "peer_relative": ops / f"sector-aware-relative-research-v1-{nodash}" / "sector_aware_relative_research_artifact.json",
        "scenario": ops / f"current-evidence-bound-scenario-v1-{nodash}" / "current_evidence_bound_scenario_artifact.json",
        "strategy": ops / f"polymorphic-current-strategy-classification-v1-{nodash}" / "polymorphic_current_strategy_classification_artifact.json",
        "opportunity_prioritization": ops / f"current-opportunity-prioritization-v1-{nodash}" / "current_opportunity_prioritization_artifact.json",
        "risk_register": ops / f"current-research-risk-register-v1-{nodash}" / "current_research_risk_register_artifact.json",
        "decision_packet": ops / f"current-research-decision-packet-v1-{nodash}" / "current_research_decision_packet_artifact.json",
        "decision_packet_dashboard": ops / f"current-research-decision-packet-dashboard-shadow-v1-{nodash}" / "market_wide_product_validation.json",
        "technical_coverage_disposition": ops / f"same-session-technical-coverage-recovery-v1-{nodash}" / "same_session_technical_coverage_disposition_artifact.json",
        "fundamental": ops / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json",
        "official_universe": ops / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json",
        "official_event_context": ops / "current-official-event-context-integration-v1-20260824" / "current_official_event_context_artifact.json",
        "catalyst": ops / "catalyst-event-research-context-v1-20260820" / "catalyst_event_research_context_artifact.json",
        "historical_context": ops / "market-wide-historical-research-context-v1-20260824" / "market_wide_historical_research_context_artifact.json",
        "financial_momentum": ops / "current-financial-momentum-context-v1" / "current_financial_momentum_context_artifact.json",
        "corporate_event_context": ops / "current-corporate-event-context-v1" / "current_corporate_event_context_artifact.json",
        "session_triage": ops / f"full-universe-entry-candidate-triage-v1-{nodash}" / f"full_universe_entry_candidate_triage_{nodash}.json",
        "named_20260824_triage": ops / "full-universe-entry-candidate-triage-20260824" / "full_universe_entry_candidate_triage_20260824.json",
        "postclose_20260824_triage": ops / "full-universe-entry-candidate-triage-postclose-20260824" / "full_universe_entry_candidate_triage_20260824.json",
        "integrated_investment_decision_product": ops / f"integrated-investment-decision-product-v1-{nodash}" / "integrated_investment_decision_product_artifact.json",
        "daily_integrated_decision_brief": ops / f"daily-integrated-decision-brief-v1-{nodash}" / "daily_integrated_decision_brief_artifact.json",
        "market_structure_breakout_v3_projection": ops / f"integrated-investment-decision-product-v1-{nodash}" / "market_structure_breakout_v3_projection_artifact.json",
        "financial_analysis_product": ops / f"financial-analysis-product-v2-{nodash}" / "financial_analysis_product_artifact.json",
        "current_valuation_evaluated": ops / f"financial-analysis-product-v2-{nodash}" / "current_research_valuation_context_artifact.json",
    }


def session_triage_status(root: Path, session: str, registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Exact-session triage is required. Prior-day triage is not authorized for reuse."""
    registry = registry if registry is not None else load_registry(root)
    selection = (registry.get("sessions") or {}).get(session)
    if not isinstance(selection, Mapping) or "triage" not in selection:
        return {
            "status": UNAVAILABLE_REQUIRED_INPUT,
            "reason_code": "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE",
            "identity": None,
            "path": None,
            "source_session": None,
        }
    entry = selection["triage"]
    path = root / entry["path"]
    artifact = _load(path)
    identity = (artifact or {}).get("artifact_identity") if artifact else None
    source_session = (artifact or {}).get("source_market_session") if artifact else None
    if not artifact:
        return {
            "status": UNAVAILABLE_REQUIRED_INPUT,
            "reason_code": "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE",
            "identity": entry.get("artifact_identity"),
            "path": str(entry.get("path")),
            "source_session": None,
        }
    if identity != entry.get("artifact_identity"):
        return {
            "status": BLOCKED_BY_STALE_TRIAGE_DEPENDENCY,
            "reason_code": "TRIAGE_IDENTITY_MISMATCH",
            "identity": identity,
            "path": str(entry.get("path")),
            "source_session": source_session,
        }
    if source_session != session:
        return {
            "status": BLOCKED_BY_STALE_TRIAGE_DEPENDENCY,
            "reason_code": "STALE_TRIAGE_SOURCE_SESSION_MISMATCH",
            "identity": identity,
            "path": str(entry.get("path")),
            "source_session": source_session,
        }
    return {
        "status": EXACT_SESSION_CLEAN,
        "reason_code": None,
        "identity": identity,
        "path": str(entry.get("path")),
        "source_session": source_session,
    }


def triage_identity_session(registry: Mapping[str, Any], identity: str | None) -> str | None:
    if not identity:
        return None
    for session, lock in (registry.get("completed_sessions") or {}).items():
        if isinstance(lock, Mapping) and (lock.get("frozen_input_identities") or {}).get("triage") == identity:
            return str(session)
    for session, selection in (registry.get("sessions") or {}).items():
        if isinstance(selection, Mapping) and (selection.get("triage") or {}).get("artifact_identity") == identity:
            return str(session)
    return None


def evaluate_canonical_daily_producer(root: Path, session: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Evaluate canonical eligibility. Does not write canonical producer outputs."""
    now = now or vn_now()
    registry = load_registry(root)
    triage = session_triage_status(root, session, registry)
    result = {
        "canonical_daily_producer_status": "BLOCKED",
        "canonical_refusal": None,
        "root_blocker": "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE",
        "current_session_analysis_still_available": True,
        "triage": triage,
        "fake_canonical_outputs_written": False,
    }
    try:
        completed_session_gate(registry, session, now=now)
    except DailyProducerError as exc:
        text = str(exc)
        result["canonical_refusal"] = text if text.startswith("REFUSE_COMPLETED_SESSION_RUN:") else f"REFUSE_COMPLETED_SESSION_RUN:{text}"
        if triage["status"] != EXACT_SESSION_CLEAN:
            result["root_blocker"] = "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE"
        else:
            result["root_blocker"] = str(exc).split(":")[0]
        return result
    if triage["status"] != EXACT_SESSION_CLEAN:
        result["canonical_refusal"] = "REFUSE_COMPLETED_SESSION_RUN:REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE"
        result["root_blocker"] = "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE"
        return result
    result["canonical_daily_producer_status"] = "ELIGIBLE_NOT_EXECUTED_BY_LEVEL2"
    result["canonical_refusal"] = None
    result["root_blocker"] = None
    return result


def _component(
    *,
    component_id: str,
    path: Path | None,
    root: Path,
    payload: Mapping[str, Any] | None,
    status: str,
    dependency_status: str,
    source_session: str | None,
    allowed_claims: list[str],
    blocked_claims: list[str],
    reason_codes: list[str],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "component_id": component_id,
        "artifact_path": _rel(root, path) if path else None,
        "source_artifact_identity": _artifact_identity(payload),
        "source_session_or_as_of": source_session or _artifact_session(payload),
        "exact_session_vs_reusable_context_status": status,
        "dependency_status": dependency_status,
        "allowed_claims": list(allowed_claims),
        "blocked_claims": list(blocked_claims),
        "reason_codes": list(reason_codes),
        "advertised_as_exact_session_clean": status == EXACT_SESSION_CLEAN,
        "artifact_present": bool(path and path.is_file()),
    }
    if extra:
        row.update(extra)
    return row


def classify_level2_components(root: Path, session: str) -> dict[str, Any]:
    """Classify retained artifacts from identities and as-of fields, not directory names."""
    registry = load_registry(root)
    paths = session_artifact_paths(root, session)
    triage = session_triage_status(root, session, registry)
    loaded = {name: _load(path) for name, path in paths.items()}

    named_triage = loaded.get("named_20260824_triage")
    named_triage_identity = _artifact_identity(named_triage)
    named_triage_session = _artifact_session(named_triage)
    stale_triage_used = None
    scenario = loaded.get("scenario")
    scenario_triage_id = None
    if isinstance(scenario, Mapping):
        scenario_triage_id = (_source_identities(scenario) or {}).get("triage")
        if isinstance(scenario_triage_id, str):
            mapped = triage_identity_session(registry, scenario_triage_id)
            file_session = named_triage_session if scenario_triage_id == named_triage_identity else mapped
            if (mapped or file_session) and (mapped or file_session) != session:
                stale_triage_used = {
                    "identity": scenario_triage_id,
                    "source_session": mapped or file_session,
                    "loaded_from_named_20260824_file": scenario_triage_id == named_triage_identity,
                    "named_file_path": _rel(root, paths["named_20260824_triage"]) if named_triage_identity else None,
                    "reason_code": "STALE_TRIAGE_SOURCE_SESSION_MISMATCH",
                }

    scenario_blocked = triage["status"] != EXACT_SESSION_CLEAN or bool(stale_triage_used)
    strategy = loaded.get("strategy")
    opportunity = loaded.get("opportunity_prioritization")
    packet = loaded.get("decision_packet")
    strategy_blocked = scenario_blocked
    opportunity_blocked = scenario_blocked
    packet_blocked = scenario_blocked
    dashboard_blocked = scenario_blocked
    snapshot_identity = _artifact_identity(loaded.get("exact_session_snapshot"))

    exact_allowed = [
        "Exact-session closing prices, 1-day returns, and 20-session technical features where same-session coverage is proven.",
        "Market breadth descriptors computed only from same-session technical coverage.",
    ]
    tactical_allowed = [
        "Deterministic tactical entry_state and entry_action from watchlist_tactical_entry_classifier/v1.",
        "TACTICAL_CURRENT_SESSION_SIGNAL states BREAKOUT_READY, BASE_BUILDING, EARLY_REVERSAL_CANDIDATE, UPTREND_CONFIRMED and existing entry actions.",
    ]
    scenario_blocked_claims = [
        "Scenario conclusion as current-session clean",
        "Bear/Base/Bull as exact-session current research bound to same-session triage",
        "entry_relevant_90 validation set derived from same-session triage",
    ]
    strategy_blocked_claims = [
        "Strategy conclusion as current-session clean",
        "polymorphic strategy eligibility as an exact-session synthesis over scenario",
    ]
    opportunity_blocked_claims = [
        "FULL_OPPORTUNITY_PRIORITIZATION as current-session clean",
        "PRIORITY_NOW / SETUP_WATCH ranking as exact-session",
        "research priority derived from scenario-ready strategy lanes",
    ]
    packet_blocked_claims = [
        "Decision packet as current-session clean",
        "Cockpit/product projection of triage-dependent opportunity/scenario",
    ]

    components: list[dict[str, Any]] = []

    def _lineage_matches_snapshot(payload: Mapping[str, Any] | None) -> bool:
        if not snapshot_identity or not isinstance(payload, Mapping):
            return False
        sources = _source_identities(payload)
        candidates = payload.get("input_candidates") if isinstance(payload.get("input_candidates"), Mapping) else {}
        return snapshot_identity in {
            sources.get("p3f9b_snapshot_identity"),
            sources.get("snapshot_identity"),
            sources.get("current_price"),
            candidates.get("p3f9b_snapshot_identity"),
            candidates.get("snapshot_identity"),
        }

    def add_exact(component_id: str, key: str, allowed: list[str], extra: Mapping[str, Any] | None = None) -> None:
        payload = loaded.get(key)
        path = paths[key]
        present = isinstance(payload, Mapping)
        session_ok = present and (_artifact_session(payload) == session or _lineage_matches_snapshot(payload))
        status = EXACT_SESSION_CLEAN if present and session_ok else UNAVAILABLE_REQUIRED_INPUT if not present else VALID_PRIOR_CONTEXT_REUSE
        reason = [] if status == EXACT_SESSION_CLEAN else (["ARTIFACT_MISSING"] if not present else ["SOURCE_SESSION_NOT_TARGET"])
        components.append(_component(
            component_id=component_id, path=path, root=root, payload=payload,
            status=status if present else UNAVAILABLE_REQUIRED_INPUT,
            dependency_status="INDEPENDENT_OF_TRIAGE" if present else "MISSING",
            source_session=_artifact_session(payload) or (session if status == EXACT_SESSION_CLEAN else None),
            allowed_claims=allowed if status == EXACT_SESSION_CLEAN else [],
            blocked_claims=[] if status == EXACT_SESSION_CLEAN else ["Not advertised as exact-session clean"],
            reason_codes=reason,
            extra=extra,
        ))

    add_exact("exact_session_market_snapshot", "exact_session_snapshot", exact_allowed)
    add_exact("breadth_foundation", "breadth_foundation", exact_allowed)
    add_exact("universe_resolution", "universe_resolution", exact_allowed)
    add_exact("liquidity_research", "liquidity_research", [
        "Current-session liquidity research dispositions; not qualified liquidity or sizing authority."
    ])
    add_exact("technical_recovery", "technical_recovery", [
        "Same-session technical-history recovery for the target session. Baseline used for candidate selection may be prior descriptive context."
    ], extra={"baseline_research_artifact_identity": (_source_identities(loaded.get("technical_recovery")) or {}).get("baseline_research_artifact_identity")})
    add_exact("descriptive_research", "descriptive_research", exact_allowed)
    add_exact("screening_foundation", "screening_foundation", [
        "Deterministic current-session screening foundation over same-session descriptive research."
    ])
    add_exact("tactical_classifier", "tactical_classifier", tactical_allowed)
    add_exact("corporate_intelligence", "corporate_intelligence", [
        "Current-session corporate intelligence records; event freshness remains per-record."
    ])
    add_exact("valuation", "valuation", [
        "Current-session valuation input context. Strict authoritative valuation remains blocked; shadow proxy is not target-price authority."
    ])
    add_exact("sector_leadership", "sector_leadership", [
        "Current-session market/sector leadership context. Official-universe membership is current-as-of-build, not session-locked."
    ])
    add_exact("peer_relative", "peer_relative", [
        "Current-session sector-aware relative research over tactical/descriptive/fundamental/valuation inputs."
    ])
    add_exact("technical_coverage_disposition", "technical_coverage_disposition", [
        "Same-session technical coverage disposition diagnostic."
    ])

    def add_prior(component_id: str, key: str, allowed: list[str], reason: str) -> None:
        payload = loaded.get(key)
        components.append(_component(
            component_id=component_id, path=paths[key], root=root, payload=payload,
            status=VALID_PRIOR_CONTEXT_REUSE if payload else UNAVAILABLE_REQUIRED_INPUT,
            dependency_status="INDEPENDENT_OF_TRIAGE",
            source_session=_artifact_session(payload),
            allowed_claims=allowed if payload else [],
            blocked_claims=["Not an exact-session current-market claim"] if payload else ["Artifact missing"],
            reason_codes=[reason] if payload else ["ARTIFACT_MISSING"],
        ))

    add_prior("fundamental_research", "fundamental", [
        "Retained/undated fundamental context. Producer policy is REUSE_HISTORICAL_CONTEXT."
    ], "REUSE_HISTORICAL_CONTEXT")
    add_prior("official_market_universe", "official_universe", [
        "Official current exchange-presence universe; current as of build, not session-locked."
    ], "ACCEPTED_CURRENT_ASOF_BUILD_NOT_SESSION_LOCKED")
    add_prior("official_event_context", "official_event_context", [
        "Official event context retained as current-as-of-build, not session-locked."
    ], "ACCEPTED_CURRENT_ASOF_BUILD_NOT_SESSION_LOCKED")
    add_prior("catalyst_context", "catalyst", [
        "Earlier retained catalyst context. Accepted degraded by the daily-session contract."
    ], "ACCEPTED_DEGRADED_EARLIER_RETAINED_CATALYST_CONTEXT")
    add_prior("historical_research_context", "historical_context", [
        "Within-ticker retrospective historical context at its own as-of session."
    ], "VALID_PRIOR_AS_OF_CONTEXT")
    add_prior("financial_momentum_context", "financial_momentum", [
        "Financial momentum context at its own as-of financial/session stamp."
    ], "VALID_PRIOR_AS_OF_CONTEXT")
    add_prior("corporate_event_context", "corporate_event_context", [
        "Corporate event context at its own research_session."
    ], "VALID_PRIOR_AS_OF_CONTEXT")

    risk = loaded.get("risk_register")
    risk_contexts = _source_identities(risk) if risk else {}
    components.append(_component(
        component_id="risk_register", path=paths["risk_register"], root=root, payload=risk,
        status=EXACT_SESSION_CLEAN if risk else UNAVAILABLE_REQUIRED_INPUT,
        dependency_status="INDEPENDENT_OF_TRIAGE",
        source_session=session if risk else None,
        allowed_claims=[
            "Descriptive risk register over independent source_contexts. Source sessions are preserved independently. Not a numeric score, recommendation, or priority ranking."
        ] if risk else [],
        blocked_claims=["Not a substitute for blocked opportunity/scenario conclusions"] if risk else ["Artifact missing"],
        reason_codes=["MIXED_EXACT_SESSION_AND_VALID_PRIOR_SOURCE_CONTEXTS"] if risk else ["ARTIFACT_MISSING"],
        extra={"source_contexts": risk_contexts},
    ))

    def add_blocked(component_id: str, key: str, blocked_claims: list[str], payload: Mapping[str, Any] | None) -> None:
        reasons = ["REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE"]
        if stale_triage_used:
            reasons.append("STALE_TRIAGE_SOURCE_SESSION_MISMATCH")
        reasons.append(BLOCKED_BY_STALE_TRIAGE_DEPENDENCY)
        components.append(_component(
            component_id=component_id, path=paths[key], root=root, payload=payload,
            status=BLOCKED_BY_STALE_TRIAGE_DEPENDENCY,
            dependency_status=BLOCKED_BY_STALE_TRIAGE_DEPENDENCY,
            source_session=_artifact_session(payload),
            allowed_claims=[],
            blocked_claims=blocked_claims,
            reason_codes=reasons,
            extra={
                "retained_bytes_exist_but_not_current_session_clean": bool(payload),
                "stale_triage": stale_triage_used,
                "source_artifact_identities": _source_identities(payload),
            },
        ))

    if scenario_blocked:
        add_blocked("current_evidence_bound_scenario", "scenario", scenario_blocked_claims, scenario)
        add_blocked("polymorphic_current_strategy_classification", "strategy", strategy_blocked_claims, strategy)
        add_blocked("current_opportunity_prioritization", "opportunity_prioritization", opportunity_blocked_claims, opportunity)
        add_blocked("current_research_decision_packet", "decision_packet", packet_blocked_claims, packet)
        add_blocked("decision_packet_dashboard", "decision_packet_dashboard", packet_blocked_claims, loaded.get("decision_packet_dashboard"))
    else:
        add_exact("current_evidence_bound_scenario", "scenario", ["Exact-session evidence-bound scenario over same-session triage."])
        add_exact("polymorphic_current_strategy_classification", "strategy", ["Exact-session polymorphic strategy classification over same-session scenario."])
        add_exact("current_opportunity_prioritization", "opportunity_prioritization", ["Exact-session opportunity prioritization over same-session scenario/strategy/tactical inputs."])
        add_exact("current_research_decision_packet", "decision_packet", ["Exact-session decision packet over same-session opportunity/scenario."])
        add_exact("decision_packet_dashboard", "decision_packet_dashboard", ["Dashboard/product projection of the exact-session decision packet."])

    components.append(_component(
        component_id="full_universe_entry_candidate_triage",
        path=None if triage["path"] is None else root / triage["path"] if triage["path"] else None,
        root=root,
        payload=None,
        status=triage["status"],
        dependency_status=triage["status"],
        source_session=triage.get("source_session"),
        allowed_claims=[],
        blocked_claims=["Exact-session triage for this session", "Silent prior-day triage reuse"],
        reason_codes=[triage["reason_code"]] if triage.get("reason_code") else [],
        extra={"identity": triage.get("identity"), "registry_path": triage.get("path")},
    ))

    tactical_signal = build_tactical_current_session_signal(loaded.get("tactical_classifier"), session)
    return {
        "session": session,
        "triage": triage,
        "stale_triage_dependency_trace": {
            "required_triage_status": triage,
            "named_20260824_triage_file": {
                "path": _rel(root, paths["named_20260824_triage"]),
                "identity": named_triage_identity,
                "source_market_session": named_triage_session,
                "note": "Directory date is not session authority. This file's source_market_session is the as-of that matters.",
            },
            "scenario_triage_identity": scenario_triage_id,
            "stale_triage_used_by_scenario": stale_triage_used,
            "transitive_blocked": {
                "current_evidence_bound_scenario": scenario_blocked,
                "polymorphic_current_strategy_classification": strategy_blocked,
                "current_opportunity_prioritization": opportunity_blocked,
                "current_research_decision_packet": packet_blocked,
                "decision_packet_dashboard": dashboard_blocked,
            },
        },
        "components": components,
        "tactical_current_session_signal": tactical_signal,
        "loaded": loaded,
    }


def build_tactical_current_session_signal(tactical: Mapping[str, Any] | None, session: str) -> dict[str, Any]:
    if not isinstance(tactical, Mapping) or tactical.get("session") != session:
        return {
            "signal_class": "TACTICAL_CURRENT_SESSION_SIGNAL",
            "status": "UNAVAILABLE",
            "full_opportunity_prioritization": "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE",
        }
    records = tactical.get("records") or {}
    by_state: dict[str, list[str]] = {state: [] for state in TACTICAL_SIGNAL_STATES}
    for ticker, row in records.items():
        if not isinstance(row, Mapping):
            continue
        state = row.get("entry_state")
        if state in by_state:
            by_state[state].append(str(ticker))
    for state in by_state:
        by_state[state] = sorted(by_state[state])
    coverage = tactical.get("coverage") or {}
    return {
        "signal_class": "TACTICAL_CURRENT_SESSION_SIGNAL",
        "status": "AVAILABLE",
        "session": session,
        "source_artifact_identity": tactical.get("artifact_identity"),
        "full_opportunity_prioritization": "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE",
        "classified_count": coverage.get("classified_count"),
        "entry_state_counts": coverage.get("entry_state_counts") or {},
        "entry_action_counts": coverage.get("entry_action_counts") or {},
        "selective_tactical_states": {
            state: {"count": len(tickers), "tickers": tickers} for state, tickers in by_state.items()
        },
        "allowed_claims": [
            "Deterministic tactical entry states and entry actions from the current-session tactical classifier.",
            "MARKET RISK HIGH, BUT SELECTIVE TACTICAL OPPORTUNITIES EXIST is a current-session descriptive statement when breadth is defensive and selective tactical states exist.",
        ],
        "blocked_claims": [
            "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE",
            "No current-session strategy conclusion",
            "No current-session scenario conclusion",
            "No current-session priority ranking",
        ],
    }


def market_analysis_scope(classification: Mapping[str, Any]) -> dict[str, Any]:
    loaded = classification.get("loaded") or {}
    descriptive = loaded.get("descriptive_research") or {}
    breadth = descriptive.get("market_breadth") or {}
    signal = classification.get("tactical_current_session_signal") or {}
    selective = signal.get("selective_tactical_states") or {}
    selective_count = sum(int((row or {}).get("count") or 0) for row in selective.values())
    high_risk = (
        (breadth.get("momentum_descriptor") or {}).get("descriptor") == "MOMENTUM_BREADTH_NEGATIVE"
        or (breadth.get("decline_ratio") or 0) > (breadth.get("advance_ratio") or 0)
    )
    statement = None
    if signal.get("status") == "AVAILABLE" and high_risk and selective_count:
        statement = "MARKET RISK HIGH, BUT SELECTIVE TACTICAL OPPORTUNITIES EXIST"
    elif signal.get("status") == "AVAILABLE" and high_risk:
        statement = "MARKET RISK HIGH; SELECTIVE TACTICAL OPPORTUNITIES NOT ESTABLISHED"
    elif signal.get("status") == "AVAILABLE":
        statement = "SELECTIVE TACTICAL CURRENT-SESSION SIGNALS AVAILABLE"
    return {
        "statement": statement,
        "basis": "TACTICAL_CURRENT_SESSION_SIGNAL_PLUS_SAME_SESSION_BREADTH",
        "full_opportunity_prioritization": "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE",
        "scenario_conclusion": "UNAVAILABLE",
        "strategy_conclusion": "UNAVAILABLE",
        "market_breadth": {
            "session": breadth.get("session"),
            "advancing": breadth.get("advancing"),
            "declining": breadth.get("declining"),
            "unchanged": breadth.get("unchanged"),
            "advance_ratio": breadth.get("advance_ratio"),
            "decline_ratio": breadth.get("decline_ratio"),
            "breadth_descriptor": (breadth.get("breadth_descriptor") or {}).get("descriptor"),
            "momentum_descriptor": (breadth.get("momentum_descriptor") or {}).get("descriptor"),
            "same_session_technical_feature_available_count": breadth.get("same_session_technical_feature_available_count"),
            "observed_session_cohort": breadth.get("observed_session_cohort"),
            "current_active_equity_denominator": breadth.get("current_active_equity_denominator"),
        },
        "selective_tactical_counts": {state: (row or {}).get("count") for state, row in selective.items()},
    }


def _watchlist_rows(classification: Mapping[str, Any]) -> list[dict[str, Any]]:
    loaded = classification.get("loaded") or {}
    tactical = loaded.get("tactical_classifier") or {}
    descriptive = loaded.get("descriptive_research") or {}
    t_records = tactical.get("records") or {}
    d_records = descriptive.get("records") or {}
    rows = []
    for ticker in WATCHLIST:
        t_row = t_records.get(ticker) or {}
        d_row = d_records.get(ticker) or {}
        values = ((d_row.get("technical_features") or {}).get("values") or {})
        rows.append({
            "ticker": ticker,
            "close": values.get("close"),
            "return_1d": values.get("return_1d"),
            "entry_state": t_row.get("entry_state"),
            "entry_action": t_row.get("entry_action"),
        })
    return rows


def build_level2_manifest(
    root: Path,
    session: str,
    *,
    classification: Mapping[str, Any],
    canonical: Mapping[str, Any],
    resolution: Mapping[str, Any],
) -> dict[str, Any]:
    components = list(classification["components"])
    scope = market_analysis_scope(classification)
    signal = classification["tactical_current_session_signal"]
    return {
        "schema_version": "2.0.0",
        "package_version": CONTRACT_VERSION,
        "session": session,
        "session_resolution": resolution,
        "package_classification": PACKAGE_CLASSIFICATION,
        "canonical_daily_producer_status": "BLOCKED" if canonical.get("canonical_daily_producer_status") == "BLOCKED" else canonical.get("canonical_daily_producer_status"),
        "canonical_producer_status": {
            "status": "BLOCKED" if canonical.get("canonical_daily_producer_status") == "BLOCKED" else canonical.get("canonical_daily_producer_status"),
            "reason": canonical.get("canonical_refusal"),
            "root_blocker": canonical.get("root_blocker") or "REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE",
            "blocker_explanation": "full_universe_entry_candidate_triage/v1 has no exact-session generator for this session. Prior-day triage reuse is not authorized. Canonical Daily Producer fails closed.",
            "current_session_analysis_still_available": True,
            "fake_canonical_outputs_written": False,
        },
        "stale_triage_dependency_trace": classification["stale_triage_dependency_trace"],
        "tactical_current_session_signal": {key: value for key, value in signal.items() if key != "selective_tactical_states"} | {
            "selective_tactical_states": {
                state: {"count": row["count"], "tickers": row["tickers"] if state != "UPTREND_CONFIRMED" else row["tickers"][:25], "tickers_truncated": state == "UPTREND_CONFIRMED"}
                for state, row in (signal.get("selective_tactical_states") or {}).items()
            }
        },
        "corrected_market_analysis_scope": scope,
        "components": components,
        "governed_claims": {
            "allowed_claims": [
                "Exact-session market snapshot, breadth, universe resolution, liquidity research, technical recovery, descriptive research, screening, tactical classifier, corporate intelligence, valuation context, sector leadership, and peer-relative research where identities prove target-session coherence.",
                "TACTICAL_CURRENT_SESSION_SIGNAL from the tactical classifier.",
                scope.get("statement") or "Current-session analysis still available without canonical Daily Producer.",
                "Prior-as-of fundamental/official-universe/catalyst/event/historical/financial contexts only under their existing reuse contracts.",
            ],
            "blocked_claims": [
                "Canonical Daily Producer success",
                "FULL_OPPORTUNITY_PRIORITIZATION as current-session clean",
                "Scenario conclusion as current-session clean",
                "Strategy conclusion as current-session clean",
                "Silent 2026-08-24 or 2026-08-21 triage reuse as exact-session 2026-08-25 triage",
                "Decision packet / cockpit as exact-session clean synthesis of blocked components",
            ],
            "prohibited_claims": [
                "No price targets or expected returns.",
                "No buy/sell/hold recommendations.",
                "No portfolio weighting or position sizing.",
                "No probabilistic predictions or bull/bear directional certainty.",
                "No unqualified liquidity or execution-capacity assertions.",
            ],
        },
    }


def build_level2_brief(session: str, manifest: Mapping[str, Any], classification: Mapping[str, Any]) -> str:
    canonical = manifest["canonical_producer_status"]
    scope = manifest["corrected_market_analysis_scope"]
    breadth = scope.get("market_breadth") or {}
    signal = classification.get("tactical_current_session_signal") or {}
    selective = signal.get("selective_tactical_states") or {}
    watch = _watchlist_rows(classification)
    clean = [c for c in manifest["components"] if c["exact_session_vs_reusable_context_status"] == EXACT_SESSION_CLEAN]
    prior = [c for c in manifest["components"] if c["exact_session_vs_reusable_context_status"] == VALID_PRIOR_CONTEXT_REUSE]
    blocked = [c for c in manifest["components"] if c["exact_session_vs_reusable_context_status"] in {BLOCKED_BY_STALE_TRIAGE_DEPENDENCY, UNAVAILABLE_REQUIRED_INPUT}]
    lines = [
        f"# Stock Lookup — Session {session} Level-2 Package Brief",
        "",
        f"SESSION {session}",
        "CANONICAL DAILY PRODUCER: BLOCKED" if canonical.get("status") == "BLOCKED" else f"CANONICAL DAILY PRODUCER: {canonical.get('status')}",
        f"BLOCKER: {canonical.get('root_blocker') or 'REQUIRED_TRIAGE_GENERATOR_UNAVAILABLE'}",
        "CURRENT-SESSION ANALYSIS STILL AVAILABLE: YES",
        "TACTICAL_CURRENT_SESSION_SIGNAL: AVAILABLE" if signal.get("status") == "AVAILABLE" else "TACTICAL_CURRENT_SESSION_SIGNAL: UNAVAILABLE",
        "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE",
        "",
        "## Operational status",
        "",
        "Canonical Daily Producer did not succeed. Missing exact-session triage is a required-input blocker.",
        "Prior-day triage was not authorized as a substitute. Dependent scenario, strategy, opportunity-prioritization,",
        "decision-packet, and dashboard outputs are not advertised as current-session clean.",
        "Independent current-session components remain usable.",
        "",
        f"**Corrected market-analysis scope:** {scope.get('statement') or 'Current-session analysis available; opportunity prioritization unavailable.'}",
        "",
        "## CURRENT-SESSION CLEAN COMPONENTS",
        "",
    ]
    for row in clean:
        lines.append(f"- `{row['component_id']}` identity `{row['source_artifact_identity']}` as-of `{row['source_session_or_as_of']}` path `{row['artifact_path']}`")
        for claim in row.get("allowed_claims") or []:
            lines.append(f"  - allowed: {claim}")
    lines += ["", "## PRIOR-AS-OF CONTEXT", ""]
    for row in prior:
        lines.append(f"- `{row['component_id']}` identity `{row['source_artifact_identity']}` as-of `{row['source_session_or_as_of']}` reasons `{','.join(row.get('reason_codes') or [])}`")
        for claim in row.get("allowed_claims") or []:
            lines.append(f"  - allowed as prior context: {claim}")
        for claim in row.get("blocked_claims") or []:
            lines.append(f"  - blocked: {claim}")
    lines += ["", "## UNAVAILABLE / TRIAGE-DEPENDENT COMPONENTS", ""]
    for row in blocked:
        lines.append(f"- `{row['component_id']}` status `{row['exact_session_vs_reusable_context_status']}` identity `{row['source_artifact_identity']}`")
        for code in row.get("reason_codes") or []:
            lines.append(f"  - reason: {code}")
        for claim in row.get("blocked_claims") or []:
            lines.append(f"  - blocked claim: {claim}")
        extra = row.get("stale_triage")
        if extra:
            lines.append(f"  - stale triage identity `{extra.get('identity')}` source session `{extra.get('source_session')}`")
    lines += [
        "",
        "## Current-session market breadth",
        "",
        f"- Observed cohort: {breadth.get('observed_session_cohort')}",
        f"- Same-session technical covered: {breadth.get('same_session_technical_feature_available_count')}",
        f"- Advancing / declining / unchanged: {breadth.get('advancing')} / {breadth.get('declining')} / {breadth.get('unchanged')}",
        f"- Breadth descriptor: `{breadth.get('breadth_descriptor')}`",
        f"- Momentum descriptor: `{breadth.get('momentum_descriptor')}`",
        "",
        "## TACTICAL_CURRENT_SESSION_SIGNAL",
        "",
        "These states come from the current-session tactical classifier. They are not opportunity priority ranks.",
        "",
    ]
    for state in TACTICAL_SIGNAL_STATES:
        row = selective.get(state) or {}
        tickers = row.get("tickers") or []
        shown = ", ".join(f"`{t}`" for t in (tickers if state != "UPTREND_CONFIRMED" else tickers[:20]))
        more = "" if state != "UPTREND_CONFIRMED" or len(tickers) <= 20 else f" (+{len(tickers) - 20} more)"
        lines.append(f"- `{state}` count {row.get('count', 0)}: {shown}{more}")
    lines += [
        "",
        f"- Entry action counts: `{json.dumps(signal.get('entry_action_counts') or {}, sort_keys=True)}`",
        "",
        "## Watchlist tactical states (not priority ranks)",
        "",
        "| Ticker | Close | 1D return | Tactical state | Entry action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in watch:
        ret = row.get("return_1d")
        ret_s = "" if ret is None else f"{ret:.4f}"
        close = row.get("close")
        close_s = "" if close is None else str(close)
        lines.append(f"| `{row['ticker']}` | {close_s} | {ret_s} | `{row.get('entry_state')}` | `{row.get('entry_action')}` |")
    lines += [
        "",
        "## Authority boundary",
        "",
        "- Canonical Daily Producer: BLOCKED.",
        "- No scenario, strategy, or opportunity-priority conclusion is current-session clean.",
        "- No recommendation, target, expected return, or sizing.",
        "",
    ]
    return "\n".join(lines) + "\n"


def package_dir(root: Path, session: str) -> Path:
    return root / "operations-review" / f"daily-session-{session}-level2-package"


def write_level2_package(root: Path, session: str, *, classification: Mapping[str, Any], canonical: Mapping[str, Any], resolution: Mapping[str, Any]) -> dict[str, Path]:
    pkg = package_dir(root, session)
    pkg.mkdir(parents=True, exist_ok=True)
    manifest = build_level2_manifest(root, session, classification=classification, canonical=canonical, resolution=resolution)
    brief = build_level2_brief(session, manifest, classification)
    manifest_path = pkg / "level2_session_manifest.json"
    brief_path = pkg / f"session_brief_{session.replace('-', '_')}.md"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    brief_path.write_text(brief, encoding="utf-8")
    return {"manifest": manifest_path, "brief": brief_path, "package_dir": pkg}


def run_cmd(execution_root: Path, cmd: list[str]) -> None:
    """Run a repository-relative tool from the Producer checkout.

    Level-2 artifacts can be redirected into an isolated canonical post-close
    attempt directory. That output location must never also become the cwd for
    the relative ``tools/...`` commands below.
    """
    print(f"--> {' '.join(cmd)}")
    subprocess.run([sys.executable] + cmd, cwd=str(execution_root), check=True)


def _canonical_snapshot_gate_satisfied(snapshot_path: Path, evidence_path: Path) -> bool:
    """Is an existing on-disk canonical exact-session snapshot safe to reuse unconditionally?

    Corrective fix for the P0 idempotency-escape defect: the OLD ensure_exact_session_snapshot
    wrote the canonical projection before ever checking DNSE provider-health, so a rerun that
    merely found the file present would reuse a possibly-degraded-and-never-verified snapshot
    with no re-verification at all. This function makes that reuse decision explicit by loading
    the sibling multi-source evidence artifact (written alongside the snapshot -- see
    multi_source_market_evidence key in session_artifact_paths) and checking its retained DNSE
    quality sentinel verdict against the snapshot's OWN self-declared
    ``degraded_provider_recovery`` marker (see multi_source_exact_session_resolver.
    resolve_exact_session_with_autorecovery).

    Missing or unreadable companion evidence is treated as "nothing to disprove trust with", not
    as "untrustworthy" -- a bare snapshot fixture (this module's own existing tests, or any
    artifact that predates the multi-source evidence artifact entirely) is reused exactly as
    before this fix. A companion evidence file that DOES show DNSE_BROAD_STALE_OR_INCOMPLETE_EOD,
    with no corresponding COMPLETED recovery marker on the snapshot itself, is exactly the
    pre-corrective idempotency-escape shape (a projection written before the sentinel check ever
    ran, or before this fix existed at all) -- never silently reused.
    """
    if not evidence_path.is_file():
        return True
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    sentinel = evidence.get("dnse_quality_sentinel") if isinstance(evidence, Mapping) else None
    if not isinstance(sentinel, Mapping):
        return True
    from multi_source_market_evidence_contract import DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD
    health = sentinel.get("health") or {}
    if health.get("state") != DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD:
        return True
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    from multi_source_exact_session_resolver import DEGRADED_RECOVERY_COMPLETED
    recovery = snapshot.get("degraded_provider_recovery") if isinstance(snapshot, Mapping) else None
    return isinstance(recovery, Mapping) and recovery.get("mode") == DEGRADED_RECOVERY_COMPLETED


def ensure_exact_session_snapshot(
    artifact_root: Path,
    session: str,
    runtime_root: Path,
    workers: int = 12,
    now: datetime | None = None,
    *,
    execution_root: Path | None = None,
) -> Path:
    """Idempotently acquire the resolved exact-session snapshot for ``session`` under
    ``artifact_root``.

    This is the exact-session acquisition boundary, extracted so a caller that only needs the
    snapshot itself (canonical_post_close_pipeline.acquire_and_materialize, in particular, so it
    can validate exact-session coverage before spending any liquidity or technical-recovery work)
    can call it directly without running the rest of materialize_independent_components.

    2026-09-03 MULTI_SOURCE_EXACT_SESSION_MARKET_EVIDENCE_AND_DAILY_RESILIENCE_V1: previously this
    ran the standalone DNSE-only P3F9B CLI tool as a subprocess and returned its output directly.
    A single thin/lagging DNSE day (17/1683 on 2026-09-03 -- see the same-day investigation this
    milestone's own brief cites) then stopped canonical Daily globally even though this project's
    own existing VCI/KBS acquisition capability (vn_stock_pipeline.py) could independently supply
    most of the same session. This function now runs the same DNSE acquisition in-process (Pass 1,
    byte-identical mva_exact_session_snapshot.materialize_snapshot() logic, unchanged), retains
    it unmodified as a standalone diagnostic artifact ("DNSE_PROVIDER_COVERAGE" -- see
    dnse_only_exact_session_snapshot key), then recovers only DNSE's own gaps through VCI/KBS via
    multi_source_exact_session_resolver.py (Passes 2-4; never re-queries a DNSE-resolved ticker;
    no concurrency against VCI/KBS -- see that module's own docstring) and writes the RESOLVED
    projection to this function's return path. The projected snapshot keeps the exact same
    "p3f9_exact_session_mva_snapshot/v2" shape/contract every existing Level-2/current-research
    tool already reads (assert_post_close_eligible, breadth foundation, universe status,
    liquidity research, technical recovery, descriptive research, valuation, tactical classifier,
    corporate intelligence, sector leadership) -- none of them change. Full multi-source evidence
    (which source supplied each recovered bar, corroboration/conflict, what was blocked) is
    retained separately -- see multi_source_market_evidence key.

    2026-09-04 MULTI_SOURCE_DAILY_DEGRADED_PROVIDER_AUTORECOVERY_AND_IDEMPOTENCY_CORRECTIVE_V1:
    a broadly degraded DNSE day (multi_source_exact_session_resolver.
    DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD) no longer stops here for an operator to re-run with
    an expanded scope -- resolve_exact_session_with_autorecovery expands VCI/KBS verification to
    every DNSE-exact ticker in the SAME call (see that function's own docstring). An existing
    on-disk snapshot is reused only when _canonical_snapshot_gate_satisfied confirms it was never
    subject to an unresolved degradation -- fixing the prior idempotency escape where a projection
    written before the (then operator-gated) sentinel check could be silently reused on rerun with
    no re-verification at all. Raises ValueError("P3F9B_EXISTING_SNAPSHOT_PROVIDER_HEALTH_GATE_
    UNRESOLVED:...") when an existing snapshot fails that check -- callers (canonical_post_close_
    pipeline.resolve_acquisition_root, in particular) must redirect to a fresh attempt root rather
    than call this function again on the same artifact_root; this function never overwrites,
    relabels, or mutates the untrusted existing bytes itself. Raises
    ValueError("P3F9B_ACQUIRED_SESSION_MISMATCH:...") if a freshly acquired snapshot's own resolved
    session does not exactly equal ``session``; no prior/latest substitution is ever silently
    accepted.
    """
    execution_root = execution_root or artifact_root
    paths = session_artifact_paths(artifact_root, session)
    p3f9b_snapshot = paths["exact_session_snapshot"]
    evidence_path = paths["multi_source_market_evidence"]
    if p3f9b_snapshot.exists():
        if not _canonical_snapshot_gate_satisfied(p3f9b_snapshot, evidence_path):
            raise ValueError(
                "P3F9B_EXISTING_SNAPSHOT_PROVIDER_HEALTH_GATE_UNRESOLVED:session=" + session
                + ":retained snapshot reflects an unresolved DNSE_BROAD_STALE_OR_INCOMPLETE_EOD "
                  "verdict with no completed degraded-provider-recovery marker -- never reused "
                  "as-is; caller must redirect to a fresh attempt root."
            )
        return p3f9b_snapshot
    import mva_exact_session_snapshot as snapshotter
    import multi_source_exact_session_resolver as resolver
    from dnse_access import credentials_for_request
    from dnse_secrets_env import ensure_credentials_loaded

    instant = now or vn_now()
    dnse_only_path = paths["dnse_only_exact_session_snapshot"]
    if dnse_only_path.exists():
        # A prior attempt already completed Pass 1 and crashed/stopped before the resolved
        # projection was written; reuse it rather than spending a second live DNSE
        # acquisition -- this still satisfies "exactly one governed market-wide acquisition"
        # upstream (canonical_daily_operation.py counts calls to acquire_and_materialize, not
        # DNSE requests underneath it).
        dnse_snapshot = json.loads(dnse_only_path.read_text(encoding="utf-8"))
    else:
        candidates = snapshotter.canonical_candidates(runtime_root)
        status = ensure_credentials_loaded()
        creds = credentials_for_request()
        if not status.get("configured") or not creds:
            raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")
        dnse_snapshot = snapshotter.materialize_snapshot(
            candidates=candidates, requested_at=instant, target_session=session,
            api_key=creds[0], api_secret=creds[1], workers=workers,
        )
        snapshotter.write_snapshot(dnse_snapshot, dnse_only_path)

    all_tickers = list(dnse_snapshot["records"])
    dnse_exact_tickers = [
        t for t in all_tickers
        if dnse_snapshot["records"][t].get("disposition") == "EXACT_SESSION_RETAINED"
    ]
    candidate_metadata = resolver.read_candidate_metadata(runtime_root, all_tickers)
    sentinel = resolver.select_sentinel_cohort(
        candidate_metadata=candidate_metadata, dnse_exact_tickers=dnse_exact_tickers,
    )
    evidence, projected = resolver.resolve_exact_session_with_autorecovery(
        dnse_snapshot=dnse_snapshot, target_session=session, requested_at=dnse_snapshot["requested_at"],
        sentinel_cohort=sentinel["tickers"],
    )
    if not evidence_path.exists():
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
    snapshotter.write_snapshot(projected, p3f9b_snapshot)
    if projected.get("resolved_completed_session") != session:
        raise ValueError(
            "P3F9B_ACQUIRED_SESSION_MISMATCH:requested=" + session
            + ":resolved=" + str(projected.get("resolved_completed_session"))
        )
    return p3f9b_snapshot


def materialize_independent_components(
    artifact_root: Path,
    session: str,
    runtime_root: Path,
    workers: int = 12,
    now: datetime | None = None,
    *,
    execution_root: Path | None = None,
) -> None:
    """Materialize a session into ``artifact_root`` using ``execution_root`` tools.

    Ordinary Level-2 callers omit ``execution_root`` and retain the historic
    one-root behaviour. Canonical post-close callers provide their isolated
    attempt output root plus the Producer checkout separately.
    """
    execution_root = execution_root or artifact_root
    paths = session_artifact_paths(artifact_root, session)
    retained_paths = session_artifact_paths(execution_root, session)
    p3f9b_snapshot = ensure_exact_session_snapshot(
        artifact_root, session, runtime_root, workers, now, execution_root=execution_root,
    )
    breadth_out = paths["breadth_foundation"]
    if not breadth_out.exists():
        run_cmd(execution_root, ["tools/build_current_market_universe_breadth_foundation.py", "--snapshot", str(p3f9b_snapshot), "--output", str(breadth_out)])
    ur_out = paths["universe_resolution"]
    if not ur_out.exists():
        run_cmd(execution_root, [
            "tools/run_current_universe_status_and_session_coverage_resolution.py",
            "--breadth-foundation-artifact", str(breadth_out),
            "--p3f9b-snapshot", str(p3f9b_snapshot),
            "--output", str(ur_out),
        ])
    liq_out = paths["liquidity_research"]
    liq_dir = liq_out.parent
    if not liq_out.exists():
        snapshot_data = json.loads(p3f9b_snapshot.read_text(encoding="utf-8"))
        num_candidates = len(snapshot_data.get("records", {}))
        num_batches = math.ceil(num_candidates / 100)
        for i in range(num_batches):
            run_cmd(execution_root, [
                "tools/run_market_wide_current_liquidity_research.py",
                "--universe-snapshot", str(p3f9b_snapshot), "--out-dir", str(liq_dir),
                "--session", session, "--batch-index", str(i), "--batch-size", "100", "--workers", str(workers),
            ])
        run_cmd(execution_root, [
            "tools/run_market_wide_current_liquidity_research.py",
            "--universe-snapshot", str(p3f9b_snapshot), "--out-dir", str(liq_dir),
            "--session", session, "--consolidate",
        ])
    tech_out = paths["technical_recovery"]
    tech_dir = tech_out.parent
    baseline_desc = _prior_completed_descriptive(execution_root, session)
    if not tech_out.exists():
        from market_wide_current_technical_coverage_scaleout import recovery_candidates
        b_data = json.loads(baseline_desc.read_text(encoding="utf-8"))
        s_data = json.loads(p3f9b_snapshot.read_text(encoding="utf-8"))
        candidates = recovery_candidates(baseline_artifact=b_data, p3f9b_snapshot=s_data)
        num_batches = math.ceil(len(candidates) / 10) if candidates else 0
        for i in range(num_batches):
            run_cmd(execution_root, [
                "tools/run_market_wide_current_technical_coverage_scaleout.py",
                "--baseline", str(baseline_desc), "--snapshot", str(p3f9b_snapshot),
                "--out-dir", str(tech_dir), "--batch", str(i), "--batch-size", "10",
            ])
        run_cmd(execution_root, [
            "tools/run_market_wide_current_technical_coverage_scaleout.py",
            "--baseline", str(baseline_desc), "--snapshot", str(p3f9b_snapshot),
            "--out-dir", str(tech_dir), "--consolidate", "--batch-size", "10",
        ])
    desc_out = paths["descriptive_research"]
    if not desc_out.exists():
        run_cmd(execution_root, [
            "tools/run_market_wide_current_descriptive_research.py",
            "--universe-resolution-artifact", str(ur_out), "--p3f9b-snapshot", str(p3f9b_snapshot),
            "--liquidity-artifact", str(liq_out), "--technical-history-recovery-artifact", str(tech_out),
            "--output", str(desc_out),
        ])
    screen_out = paths["screening_foundation"]
    if not screen_out.exists():
        run_cmd(execution_root, ["tools/run_current_market_screening_opportunity_comparison_foundation.py", "--source", str(desc_out), "--out", str(screen_out)])
    tactical_out = paths["tactical_classifier"]
    tactical_dir = tactical_out.parent
    fundamental_retained = retained_paths["fundamental"]
    if not tactical_out.exists():
        run_cmd(execution_root, [
            "tools/run_watchlist_tactical_entry_classifier.py",
            "--descriptive-path", str(desc_out), "--screening-path", str(screen_out),
            "--fundamental-path", str(fundamental_retained), "--out-dir", str(tactical_dir),
        ])
    ci_out = paths["corporate_intelligence"]
    if not ci_out.exists():
        run_cmd(execution_root, [
            "tools/run_market_wide_current_corporate_intelligence.py",
            "--session", session, "--descriptive", str(desc_out),
            "--fundamental", str(fundamental_retained), "--output", str(ci_out),
        ])
    val_out = paths["valuation"]
    val_dir = val_out.parent
    if not val_out.exists():
        run_cmd(execution_root, [
            "tools/derive_market_wide_current_valuation_input_scaleout.py",
            "--runtime-root", str(runtime_root), "--price", str(p3f9b_snapshot),
            "--expected-session", session,
            "--output", str(val_out), "--report", str(val_dir / "market_wide_current_valuation_research_scaleout_report.json"),
        ])
    leadership_out = paths["sector_leadership"]
    official_u = retained_paths["official_universe"]
    if not leadership_out.exists():
        run_cmd(execution_root, [
            "tools/run_current_market_sector_leadership_context.py",
            "--current-descriptive-artifact", str(desc_out),
            "--current-screening-artifact", str(screen_out),
            "--current-official-universe-artifact", str(official_u),
            "--output", str(leadership_out),
        ])
    peer_out = paths["peer_relative"]
    if not peer_out.exists():
        run_cmd(execution_root, [
            "tools/run_sector_aware_relative_research.py",
            "--descriptive", str(desc_out), "--tactical", str(tactical_out),
            "--fundamental", str(fundamental_retained), "--valuation", str(val_out),
            "--output", str(peer_out),
        ])
    risk_out = paths["risk_register"]
    if not risk_out.exists():
        run_cmd(execution_root, [
            "tools/run_current_research_risk_register.py",
            "--leadership-context", str(leadership_out),
            "--valuation-context", str(val_out),
            "--output", str(risk_out),
        ])
    disp_out = paths["technical_coverage_disposition"]
    if not disp_out.exists():
        from same_session_technical_coverage_disposition import build as build_disp, content_identity as disp_id
        disp_art = build_disp(
            descriptive=json.loads(desc_out.read_text("utf-8")),
            official_universe=json.loads(official_u.read_text("utf-8")),
            p3f9b_snapshot=json.loads(p3f9b_snapshot.read_text("utf-8")),
            universe_status=json.loads(ur_out.read_text("utf-8")),
            tactical=json.loads(tactical_out.read_text("utf-8")),
            recovery=json.loads(tech_out.read_text("utf-8")),
        )
        disp_art.update(disp_id(disp_art))
        disp_out.parent.mkdir(parents=True, exist_ok=True)
        disp_out.write_text(json.dumps(disp_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def maybe_build_triage_dependent(
    artifact_root: Path,
    session: str,
    *,
    execution_root: Path | None = None,
) -> dict[str, Any]:
    """Build attempt outputs from selected artifacts and retained Producer inputs.

    ``artifact_root`` owns all session-specific output paths. ``execution_root``
    owns the registry and immutable retained inputs; defaults preserve existing
    non-canonical callers.
    """
    execution_root = execution_root or artifact_root
    paths = session_artifact_paths(artifact_root, session)
    retained_paths = session_artifact_paths(execution_root, session)
    if (
        not paths["session_triage"].exists()
        and paths["descriptive_research"].exists()
        and paths["screening_foundation"].exists()
        and paths["tactical_classifier"].exists()
    ):
        from full_universe_entry_candidate_triage import build as build_triage, replay as replay_triage
        triage_art = build_triage(
            descriptive=json.loads(paths["descriptive_research"].read_text(encoding="utf-8")),
            screening=json.loads(paths["screening_foundation"].read_text(encoding="utf-8")),
            tactical=json.loads(paths["tactical_classifier"].read_text(encoding="utf-8")),
            fundamental=_load(retained_paths["fundamental"]),
            session=session,
        )
        replay_triage(triage_art)
        paths["session_triage"].parent.mkdir(parents=True, exist_ok=True)
        paths["session_triage"].write_text(json.dumps(triage_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    registry = load_registry(execution_root)
    triage = session_triage_status(execution_root, session, registry)
    generated_triage = False
    if triage["status"] != EXACT_SESSION_CLEAN:
        generated = _load(paths["session_triage"])
        if generated and generated.get("source_market_session") == session:
            generated_triage = True
            triage = {
                "status": EXACT_SESSION_CLEAN,
                "reason_code": None,
                "identity": generated.get("artifact_identity"),
                "path": _rel(artifact_root, paths["session_triage"]),
                "source_session": session,
            }
        else:
            return {"built": False, "reason": triage}
    if paths["scenario"].exists() and paths["strategy"].exists() and paths["opportunity_prioritization"].exists():
        return {"built": False, "reason": {"status": "ALREADY_PRESENT_EXACT_SESSION_TRIAGE"}}
    from current_evidence_bound_scenario import build as build_scenario
    from polymorphic_current_strategy_classification import build as build_strategy
    from current_opportunity_prioritization import build as build_opp, content_identity as opp_id
    triage_path = paths["session_triage"] if generated_triage else (
        execution_root / triage["path"] if triage.get("path") else paths["session_triage"]
    )
    triage_art = json.loads(triage_path.read_text(encoding="utf-8"))
    cat = _load(retained_paths["catalyst"])
    scenario_art = build_scenario(
        descriptive=json.loads(paths["descriptive_research"].read_text("utf-8")),
        tactical=json.loads(paths["tactical_classifier"].read_text("utf-8")),
        peer_relative=json.loads(paths["peer_relative"].read_text("utf-8")),
        fundamental=json.loads(retained_paths["fundamental"].read_text("utf-8")),
        valuation=json.loads(paths["valuation"].read_text("utf-8")),
        triage=triage_art,
        catalyst=cat,
        screening=json.loads(paths["screening_foundation"].read_text("utf-8")),
        corporate_intelligence=json.loads(paths["corporate_intelligence"].read_text("utf-8")),
    )
    paths["scenario"].parent.mkdir(parents=True, exist_ok=True)
    paths["scenario"].write_text(json.dumps(scenario_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    strategy_art = build_strategy(
        descriptive=json.loads(paths["descriptive_research"].read_text("utf-8")),
        tactical=json.loads(paths["tactical_classifier"].read_text("utf-8")),
        peer_relative=json.loads(paths["peer_relative"].read_text("utf-8")),
        fundamental=json.loads(retained_paths["fundamental"].read_text("utf-8")),
        valuation=json.loads(paths["valuation"].read_text("utf-8")),
        scenario=json.loads(paths["scenario"].read_text("utf-8")),
        corporate_intelligence=json.loads(paths["corporate_intelligence"].read_text("utf-8")),
    )
    paths["strategy"].parent.mkdir(parents=True, exist_ok=True)
    paths["strategy"].write_text(json.dumps(strategy_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    opp_art = build_opp(
        official_universe=json.loads(retained_paths["official_universe"].read_text("utf-8")),
        screening=json.loads(paths["screening_foundation"].read_text("utf-8")),
        tactical=json.loads(paths["tactical_classifier"].read_text("utf-8")),
        strategy=json.loads(paths["strategy"].read_text("utf-8")),
        scenario=json.loads(paths["scenario"].read_text("utf-8")),
        fundamental=json.loads(retained_paths["fundamental"].read_text("utf-8")),
        peer=json.loads(paths["peer_relative"].read_text("utf-8")),
        event_context=json.loads(retained_paths["official_event_context"].read_text("utf-8")),
        descriptive=json.loads(paths["descriptive_research"].read_text("utf-8")),
    )
    opp_art.update(opp_id(opp_art))
    paths["opportunity_prioritization"].parent.mkdir(parents=True, exist_ok=True)
    paths["opportunity_prioritization"].write_text(json.dumps(opp_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"built": True, "reason": triage}


def run_level2_package(
    root: Path,
    *,
    session: str | None,
    runtime_root: Path,
    workers: int = 12,
    now: datetime | None = None,
    acquire: bool = True,
) -> dict[str, Any]:
    resolution = resolve_level2_session(session, now=now)
    selected = resolution["session"]
    canonical = evaluate_canonical_daily_producer(root, selected, now=now)
    if acquire:
        materialize_independent_components(root, selected, runtime_root, workers=workers, now=now or vn_now())
        maybe_build_triage_dependent(root, selected)
    classification = classify_level2_components(root, selected)
    written = write_level2_package(root, selected, classification=classification, canonical=canonical, resolution=resolution)
    status = {
        "session": selected,
        "session_resolution": resolution,
        "canonical_daily_producer_status": "BLOCKED" if canonical.get("canonical_daily_producer_status") == "BLOCKED" else canonical.get("canonical_daily_producer_status"),
        "blocker": canonical.get("root_blocker"),
        "canonical_refusal": canonical.get("canonical_refusal"),
        "current_session_analysis_still_available": True,
        "tactical_current_session_signal": classification["tactical_current_session_signal"].get("status"),
        "full_opportunity_prioritization": (
            "AVAILABLE" if not classification["stale_triage_dependency_trace"]["transitive_blocked"]["current_opportunity_prioritization"]
            else "FULL_OPPORTUNITY_PRIORITIZATION_UNAVAILABLE"
        ),
        "level2_package": str(written["package_dir"]),
        "manifest": str(written["manifest"]),
        "brief": str(written["brief"]),
        "fake_canonical_outputs_written": False,
        "corrected_market_analysis_scope": classification and market_analysis_scope(classification),
    }
    return {"resolution": resolution, "canonical": canonical, "classification": classification, "written": written, "status": status}


def print_structured_status(status: Mapping[str, Any]) -> None:
    print(f"SESSION: {status['session']}")
    print(f"CANONICAL_DAILY_PRODUCER_STATUS: {status['canonical_daily_producer_status']}")
    print(f"BLOCKER: {status.get('blocker')}")
    print(f"CANONICAL_REFUSAL: {status.get('canonical_refusal')}")
    print(f"CURRENT_SESSION_ANALYSIS_STILL_AVAILABLE: YES")
    print(f"TACTICAL_CURRENT_SESSION_SIGNAL: {status.get('tactical_current_session_signal')}")
    print(f"FULL_OPPORTUNITY_PRIORITIZATION: {status.get('full_opportunity_prioritization')}")
    scope = status.get("corrected_market_analysis_scope") or {}
    print(f"MARKET_ANALYSIS_SCOPE: {scope.get('statement')}")
    print(f"LEVEL2_PACKAGE: {status.get('level2_package')}")
    print(f"FAKE_CANONICAL_OUTPUTS_WRITTEN: {status.get('fake_canonical_outputs_written')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Foreground Level-2 daily session package runner.")
    parser.add_argument(
        "--session",
        default=None,
        help="Target completed market session YYYY-MM-DD, or latest-completed. Omitted means latest-completed working-date resolution.",
    )
    parser.add_argument("--runtime-root", type=Path, default=None, help="Dashboard runtime root for governed acquisition reuse.")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--package-only", action="store_true", help="Classify and rewrite the Level-2 package from retained artifacts; do not acquire.")
    args = parser.parse_args(argv)
    root = ROOT_DEFAULT
    runtime_root = args.runtime_root or (root.parent / "dashboard-runtime")
    result = run_level2_package(
        root,
        session=args.session,
        runtime_root=runtime_root,
        workers=args.workers,
        acquire=not args.package_only,
    )
    print_structured_status(result["status"])
    return 0
