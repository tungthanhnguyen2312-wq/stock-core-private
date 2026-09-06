"""Read-only acceptance of a retained Canonical Daily release.

This module deliberately does not generate indicators, calculate valuations, select a
"latest" artifact, or write a release.  It joins the identities and freshness labels
already emitted by the Daily producer, the AI handoff, and the Dashboard projection.
The narrow file layout is the immutable Daily Session Operation directory produced by
``daily_research_session_operations``.  A future producer can additionally retain a
``release_acceptance_input.json`` there when an upstream contract exposes richer
per-component metadata; this checker treats that document as evidence, never as a
replacement for the operation manifest.

Financial period semantics and knowledge timing are intentionally separate.  A future
``financial_evidence_as_of_period`` is structurally impossible for a latest *actual*
reported period, but is not evidence that future knowledge was admitted.  A knowledge
timing violation requires a qualified availability field: direct
``knowledge_available_at``/``effective_knowledge_at``/``known_at``, a qualified
``knowledge_timing`` envelope, or an explicitly qualified publication timestamp.
Materialization, generation, and retrieval times are never timing evidence by themselves.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import owner_research_focus

try:  # Current snapshots use this verifier when they carry its exact contract.
    import prospective_decision_retention
except ImportError:  # pragma: no cover - keeps this pure verifier importable in fixtures
    prospective_decision_retention = None  # type: ignore[assignment]


CONTRACT_VERSION = "canonical_daily_release_acceptance/v1"
INPUT_CONTRACT_VERSION = "canonical_daily_release_acceptance_input/v1"
OVERALL_STATES = ("PASS", "PASS_WITH_EXPLICIT_PARTIALS", "BLOCKED", "INVALID_RELEASE")
DOMAIN_KEYS = (
    "daily_session_lineage",
    "signal_presentation",
    "technical_target_close",
    "valuation_readiness",
    "financial_cutoff",
    "corporate_freshness",
    "prospective_snapshot",
    "ai_handoff",
    "dashboard_release",
    "watchlist_authority",
)

_JSON_CANDIDATES = {
    "operation": ("run_manifest.json",),
    "product": ("current_daily_decision_research_product_artifact.json",),
    "brief": ("daily_integrated_decision_brief.json",),
    "prospective": ("prospective_snapshot.json",),
    "handoff": ("ai_research_session_bundle.json", "session_handoff_bundle.json"),
    "dashboard": ("current_decision_cockpit_projection.json", "dashboard/current_decision_cockpit_projection.json", "data/current_decision_cockpit.json"),
    "dashboard_metadata": ("data/build_info.json", "build_info.json", "dashboard_release_manifest.json"),
}

_FUTURE_OUTCOME_STATES = frozenset({"PENDING_FUTURE_OBSERVATION", "NOT_YET_EVALUABLE", "PENDING", "UNAVAILABLE"})
_EXACT_SIGNAL_STATES = frozenset({"CURRENT", "EXACT_SESSION", "NO_PATTERN_CURRENT_SESSION"})
_PARTIAL_SIGNAL_STATES = frozenset({"STALE", "STALE_BUT_EXPLICITLY_LABELLED", "INSUFFICIENT_HISTORY", "UNAVAILABLE", "UNAVAILABLE_FOR_CURRENT_SESSION"})
_DIRECT_KNOWLEDGE_TIME_FIELDS = ("knowledge_available_at", "effective_knowledge_at", "known_at")
_QUALIFIED_TIMING_STATES = frozenset({"QUALIFIED", "CONTRACT_QUALIFIED", "EVIDENCE_KNOWLEDGE_AVAILABLE_AT"})
_UNQUALIFIED_TIMING_FIELDS = ("materialized_at", "materialization_timestamp", "generated_at", "retrieved_at", "retrieval_timestamp", "observed_at")


class ReleaseAcceptanceError(ValueError):
    """Raised only for invalid invocation shape, never for an acceptance finding."""


@dataclass(frozen=True)
class _Loaded:
    payload: Mapping[str, Any] | None
    relative_path: str | None
    error: str | None = None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _as_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _load_first(root: Path, names: Sequence[str]) -> _Loaded:
    for name in names:
        path = root / name
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _Loaded(None, name, "UNREADABLE_JSON")
        if not isinstance(value, Mapping):
            return _Loaded(None, name, "JSON_NOT_OBJECT")
        return _Loaded(value, name)
    return _Loaded(None, None, "MISSING")


def _session(value: Mapping[str, Any]) -> str | None:
    for key in ("session", "market_session", "research_session", "source_market_session", "valuation_session", "decision_session"):
        candidate = _as_text(value.get(key))
        if candidate:
            return candidate
    return None


def _reason_domain(state: str, reasons: Sequence[str], evidence: Mapping[str, Any], *, fatal: bool = False, producer_impact: bool = False) -> dict[str, Any]:
    return {
        "state": state,
        "reason_codes": sorted(set(reasons)),
        "fatal_for_release": fatal,
        "invalidates_current_research": producer_impact,
        "evidence": dict(evidence),
    }


def _get_path(value: Mapping[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _quarter_end(period: str) -> date | None:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if not match:
        return None
    year, quarter = int(match.group(1)), int(match.group(2))
    return date(year, (3, 6, 9, 12)[quarter - 1], (31, 30, 30, 31)[quarter - 1])


def _date_value(value: Any) -> date | None:
    text = _as_text(value)
    if not text:
        return None
    if _quarter_end(text):
        return _quarter_end(text)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _qualified_knowledge_timing(financial: Mapping[str, Any]) -> tuple[str | None, date | None, list[str]]:
    """Return only timing facts whose field semantics say when evidence was knowable."""
    for field in _DIRECT_KNOWLEDGE_TIME_FIELDS:
        value = _date_value(financial.get(field))
        if value:
            return field, value, []
    timing = _mapping(financial.get("knowledge_timing"))
    qualification = _as_text(timing.get("status")) or _as_text(timing.get("qualification"))
    if qualification in _QUALIFIED_TIMING_STATES:
        for field in ("knowledge_available_at", "effective_knowledge_at", "available_at", "known_at"):
            value = _date_value(timing.get(field))
            if value:
                return "knowledge_timing." + field, value, []
    published_semantics = _as_text(financial.get("published_at_semantics")) or _as_text(financial.get("publication_timing_qualification"))
    if published_semantics in _QUALIFIED_TIMING_STATES:
        value = _date_value(financial.get("published_at"))
        if value:
            return "published_at", value, []
    unqualified = [field for field in _UNQUALIFIED_TIMING_FIELDS if financial.get(field) is not None]
    if financial.get("published_at") is not None:
        unqualified.append("published_at")
    return None, None, unqualified


def _financial_identities(financial: Mapping[str, Any]) -> dict[str, str]:
    fields = ("artifact_identity", "source_artifact_identity", "financial_analysis_product_identity", "financial_v2_engine_identity", "source_context_identity")
    return {field: value for field in fields if (value := _as_text(financial.get(field)))}


def _identity_values(value: Any) -> set[str]:
    if text := _as_text(value):
        return {text}
    if isinstance(value, Mapping):
        return {text for item in value.values() if (text := _as_text(item))}
    return {text for item in _list(value) if (text := _as_text(item))}


def _surface_financial_disposition(surface: Mapping[str, Any] | None, affected: set[str]) -> dict[str, Any]:
    """Classify one consumer only from an explicit admission record or retained identity reference."""
    if not surface:
        return {"state": "UNPROVEN", "identity_matches": [], "explicit_state": None}
    admission = _mapping(surface.get("financial_evidence_admission"))
    explicit_state = _as_text(admission.get("state")) or _as_text(admission.get("status"))
    explicit_ids = _identity_values(admission.get("artifact_identities")) | _identity_values([admission.get("artifact_identity")])
    if explicit_state in {"EXCLUDED", "BLOCKED", "FAIL_CLOSED"} and (not explicit_ids or bool(explicit_ids & affected)):
        return {"state": "EXCLUDED", "identity_matches": sorted(explicit_ids & affected), "explicit_state": explicit_state}
    if explicit_state in {"ADMITTED", "AVAILABLE", "INCLUDED"} and (not explicit_ids or bool(explicit_ids & affected)):
        return {"state": "ADMITTED", "identity_matches": sorted(explicit_ids & affected), "explicit_state": explicit_state}
    references = _identity_values(surface.get("source_artifact_identities"))
    references |= _identity_values(_get_path(surface, "source_artifact_identities.financial"))
    references |= _identity_values(_get_path(surface, "financial_analysis.source_context_identity"))
    references |= _identity_values(_get_path(surface, "financial_analysis.artifact_identity"))
    references |= _identity_values(_get_path(surface, "lineage.source_artifact_identities"))
    references |= _identity_values(_get_path(surface, "source.source_artifact_identities"))
    references |= _identity_values(_get_path(surface, "source.financial_analysis.source_context_identity"))
    matches = sorted(references & affected)
    if matches:
        return {"state": "ADMITTED", "identity_matches": matches, "explicit_state": explicit_state}
    return {"state": "UNPROVEN", "identity_matches": [], "explicit_state": explicit_state}


def _watchlist_tickers(value: Mapping[str, Any]) -> list[str]:
    watchlist = _mapping(value.get("watchlist"))
    tickers = [ticker for ticker in _list(watchlist.get("tickers")) if isinstance(ticker, str)]
    if tickers:
        return tickers
    records = _list(watchlist.get("records"))
    return [str(row["ticker"]) for row in records if isinstance(row, Mapping) and isinstance(row.get("ticker"), str)]


def _records_from_watchlist(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in _list(_mapping(value.get("watchlist")).get("records")) if isinstance(row, Mapping)]


def _input_section(input_payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = input_payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _input_rows(input_payload: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    return [row for row in _list(input_payload.get(name)) if isinstance(row, Mapping)]


def _future_outcome_leak(value: Any, session: date) -> bool:
    """Recognize retained realised-outcome fields without judging their content."""
    if isinstance(value, str):
        return value not in _FUTURE_OUTCOME_STATES
    if not isinstance(value, Mapping):
        return bool(value)
    state = _as_text(value.get("state")) or _as_text(value.get("status"))
    if state in _FUTURE_OUTCOME_STATES:
        return False
    for key in ("observed_at", "as_of", "outcome_session", "realized_at", "evaluation_session"):
        observed = _date_value(value.get(key))
        if observed and observed > session:
            return True
    return bool(value.get("realized_return") is not None or value.get("outcome") is not None)


def _evaluate_daily_lineage(
    operation: Mapping[str, Any] | None, *, target_session: str | None
) -> tuple[dict[str, Any], str | None, str | None]:
    if not operation:
        return _reason_domain("BLOCKED", ["DAILY_OPERATION_MANIFEST_MISSING"], {}, fatal=True, producer_impact=True), target_session, None
    session = _session(operation)
    operation_identity = _as_text(operation.get("operation_identity"))
    reasons: list[str] = []
    if operation.get("contract_version") != "daily_research_session_operation/v1":
        reasons.append("DAILY_OPERATION_CONTRACT_UNRECOGNIZED")
    if not session:
        reasons.append("DAILY_OPERATION_SESSION_MISSING")
    if target_session and session and target_session != session:
        reasons.append("DAILY_OPERATION_SESSION_MISMATCH")
    if not operation_identity:
        reasons.append("DAILY_OPERATION_IDENTITY_MISSING")
    inputs = _mapping(operation.get("input_artifacts"))
    expected = ("descriptive", "screening", "tactical", "triage", "valuation", "corporate_intelligence")
    missing = [name for name in expected if not isinstance(inputs.get(name), Mapping)]
    if missing:
        reasons.append("DAILY_OPERATION_REQUIRED_INPUTS_MISSING")
    for name in expected:
        row = _mapping(inputs.get(name))
        observed = _session(row)
        if row and observed and session and observed != session:
            reasons.append("DAILY_OPERATION_INPUT_SESSION_MISMATCH:" + name.upper())
    fatal = bool(reasons)
    return _reason_domain(
        "INVALID" if fatal else "EXACT_SESSION",
        reasons,
        {"session": session, "operation_identity": operation_identity, "required_input_names": list(expected), "missing_input_names": missing},
        fatal=fatal,
        producer_impact=fatal,
    ), session or target_session, operation_identity


def _evaluate_signals(input_payload: Mapping[str, Any], brief: Mapping[str, Any] | None, dashboard_metadata: Mapping[str, Any] | None, session: str | None) -> dict[str, Any]:
    rows = _input_rows(input_payload, "signal_components")
    if not rows:
        signal_domain = _mapping(_get_path(dashboard_metadata or {}, "domains.signals"))
        components = _mapping(signal_domain.get("components"))
        rows = [
            {"ticker": name, "state": _as_text(_mapping(component).get("status")) or "UNAVAILABLE",
             "source_session": _as_text(_mapping(component).get("source_session")), "derived_from": "dashboard_release_metadata"}
            for name, component in components.items() if isinstance(component, Mapping)
        ]
    if not rows and brief:
        for row in _records_from_watchlist(brief):
            state = "INSUFFICIENT_HISTORY" if row.get("market_structure_state") == "INSUFFICIENT_HISTORY" else "NO_PATTERN_CURRENT_SESSION"
            rows.append({"ticker": row.get("ticker"), "state": state, "source_session": session, "derived_from": "daily_integrated_decision_brief"})
    if not rows:
        return _reason_domain("EXPLICIT_PARTIAL", ["SIGNAL_PRESENTATION_METADATA_UNAVAILABLE"], {"component_count": 0})
    reasons: list[str] = []
    invalid = False
    partial = False
    normalized: list[dict[str, Any]] = []
    for row in rows:
        state = _as_text(row.get("state")) or _as_text(row.get("status")) or "UNAVAILABLE"
        source = _as_text(row.get("source_session"))
        claims_current = row.get("claims_current") is True
        if source and session and source != session:
            reasons.append("SIGNAL_SOURCE_SESSION_MISMATCH")
            partial = True
            if claims_current:
                invalid = True
                reasons.append("SIGNAL_FALSE_CURRENT_CLAIM")
        if state in _PARTIAL_SIGNAL_STATES:
            partial = True
            reasons.append("SIGNAL_" + state)
        elif state not in _EXACT_SIGNAL_STATES:
            partial = True
            reasons.append("SIGNAL_STATE_UNRECOGNIZED")
        normalized.append({"ticker": row.get("ticker"), "state": state, "source_session": source, "claims_current": claims_current})
    return _reason_domain("INVALID" if invalid else "EXPLICIT_PARTIAL" if partial else "EXACT_SESSION", reasons, {"components": normalized}, fatal=invalid)


def _evaluate_technical(input_payload: Mapping[str, Any], brief: Mapping[str, Any] | None, session: str | None) -> dict[str, Any]:
    rows = _input_rows(input_payload, "technical_records") or _records_from_watchlist(brief or {})
    if not rows:
        return _reason_domain("EXPLICIT_PARTIAL", ["TECHNICAL_TARGET_CLOSE_METADATA_UNAVAILABLE"], {"record_count": 0})
    reasons: list[str] = []
    invalid = False
    exposed = False
    for row in rows:
        target_session = _as_text(row.get("target_close_session")) or _as_text(row.get("technical_session")) or _as_text(row.get("price_session"))
        if target_session:
            exposed = True
            if session and target_session != session:
                invalid = True
                reasons.append("TECHNICAL_TARGET_CLOSE_SESSION_MISMATCH")
        if row.get("target_close_claimed_current") is True and not target_session:
            invalid = True
            reasons.append("TECHNICAL_TARGET_CLOSE_LINEAGE_MISSING")
    if not exposed:
        reasons.append("TECHNICAL_TARGET_CLOSE_NOT_EXPOSED")
    return _reason_domain("INVALID" if invalid else "EXPLICIT_PARTIAL" if reasons else "EXACT_SESSION", reasons, {"record_count": len(rows), "target_close_session_exposed": exposed}, fatal=invalid, producer_impact=invalid)


def _evaluate_valuation(input_payload: Mapping[str, Any], operation: Mapping[str, Any] | None, session: str | None) -> dict[str, Any]:
    valuation = _input_section(input_payload, "valuation")
    if not valuation:
        valuation = _mapping(_mapping(operation or {}).get("input_artifacts")).get("valuation") or {}
    valuation = _mapping(valuation)
    if not valuation:
        return _reason_domain("EXPLICIT_PARTIAL", ["VALUATION_CONTEXT_UNAVAILABLE"], {})
    reasons: list[str] = []
    invalid = False
    observed = _session(valuation)
    if observed and session and observed != session:
        invalid = True
        reasons.append("VALUATION_SESSION_MISMATCH")
    for method in _list(valuation.get("methods")):
        if not isinstance(method, Mapping):
            continue
        if _as_text(method.get("status")) in {"BLOCKED", "UNAVAILABLE"}:
            reasons.append("VALUATION_METHOD_BLOCKED")
        if method.get("price_basis_compatible") is False:
            reasons.append("VALUATION_PRICE_BASIS_BLOCKED")
        if method.get("shares_lineage") in {None, "MISSING", "UNRESOLVED"}:
            reasons.append("VALUATION_SHARES_LINEAGE_MISSING")
    status = _as_text(valuation.get("status"))
    if status in {"BLOCKED", "UNAVAILABLE", "PARTIAL"}:
        reasons.append("VALUATION_" + status)
    return _reason_domain("INVALID" if invalid else "EXPLICIT_PARTIAL" if reasons else "EXACT_SESSION", reasons, {"session": observed, "status": status, "artifact_identity": valuation.get("artifact_identity")}, fatal=invalid, producer_impact=invalid)


def _evaluate_financial(input_payload: Mapping[str, Any], brief: Mapping[str, Any] | None, session: str | None) -> dict[str, Any]:
    financial = _input_section(input_payload, "financial") or _mapping((brief or {}).get("financial_evidence_context"))
    if not financial:
        return _reason_domain("EXPLICIT_PARTIAL", ["FINANCIAL_ARTIFACT_UNAVAILABLE"], {})
    reasons: list[str] = []
    release_date = _date_value(session)
    period = _as_text(financial.get("financial_evidence_as_of_period")) or _as_text(financial.get("as_of_period"))
    period_end = _date_value(period)
    timing_field, knowledge_available_at, unqualified_timing_fields = _qualified_knowledge_timing(financial)
    if release_date and period_end and period_end > release_date:
        reasons.append("FINANCIAL_PERIOD_NOT_YET_CONCLUDED")
    if release_date and knowledge_available_at and knowledge_available_at > release_date:
        reasons.append("FINANCIAL_KNOWLEDGE_TIMING_VIOLATION")
    status = _as_text(financial.get("status"))
    if status in {"UNAVAILABLE", "PARTIAL", "BLOCKED"}:
        reasons.append("FINANCIAL_" + status)
    if not period:
        reasons.append("FINANCIAL_AS_OF_PERIOD_MISSING")
    temporal_reasons = {"FINANCIAL_PERIOD_NOT_YET_CONCLUDED", "FINANCIAL_KNOWLEDGE_TIMING_VIOLATION"}
    return _reason_domain(
        "EXPLICIT_PARTIAL" if reasons else "EXACT_SESSION",
        reasons,
        {
            "financial_evidence_as_of_period": period,
            "period_state": "NOT_YET_CONCLUDED" if release_date and period_end and period_end > release_date else "CLOSED_OR_NOT_PROVEN",
            "knowledge_timing": {
                "state": "QUALIFIED_AFTER_CUTOFF" if release_date and knowledge_available_at and knowledge_available_at > release_date else "QUALIFIED_ON_OR_BEFORE_CUTOFF" if knowledge_available_at else "NOT_PROVEN",
                "qualified_field": timing_field,
                "knowledge_available_at": knowledge_available_at.isoformat() if knowledge_available_at else None,
                "unqualified_observed_fields": unqualified_timing_fields,
            },
            "affected_evidence_identities": _financial_identities(financial),
            "temporal_blocker": bool(temporal_reasons & set(reasons)),
            "status": status,
        },
    )


def _evaluate_financial_release_aggregation(
    financial_domain: Mapping[str, Any], *, product: Mapping[str, Any] | None, brief: Mapping[str, Any] | None,
    handoff: Mapping[str, Any] | None, dashboard: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Decide release scope only after a financial blocker is tied to retained consumers."""
    evidence = _mapping(financial_domain.get("evidence"))
    if not evidence.get("temporal_blocker"):
        return {"state": "NOT_APPLICABLE", "reason_codes": [], "affected_reason_codes": [], "surfaces": {}}
    identities = set(_mapping(evidence.get("affected_evidence_identities")).values())
    affected_reasons = [reason for reason in _list(financial_domain.get("reason_codes")) if reason in {"FINANCIAL_PERIOD_NOT_YET_CONCLUDED", "FINANCIAL_KNOWLEDGE_TIMING_VIOLATION"}]
    if not identities:
        return {
            "state": "UNPROVEN",
            "reason_codes": ["FINANCIAL_EVIDENCE_DOWNSTREAM_DISPOSITION_UNPROVEN"],
            "affected_reason_codes": affected_reasons,
            "surfaces": {},
        }
    surfaces = {
        "integrated_decision_product": _surface_financial_disposition(product, identities),
        "decision_evidence_packet": _surface_financial_disposition(brief, identities),
        "ai_handoff": _surface_financial_disposition(handoff, identities),
        "dashboard_decision_release": _surface_financial_disposition(dashboard, identities),
    }
    if any(row["state"] == "ADMITTED" for row in surfaces.values()):
        return {
            "state": "ADMITTED",
            "reason_codes": ["INVALID_FINANCIAL_EVIDENCE_ADMITTED_DOWNSTREAM"],
            "affected_reason_codes": affected_reasons,
            "surfaces": surfaces,
        }
    if all(row["state"] == "EXCLUDED" for row in surfaces.values()):
        return {"state": "EXCLUDED", "reason_codes": [], "affected_reason_codes": affected_reasons, "surfaces": surfaces}
    return {
        "state": "UNPROVEN",
        "reason_codes": ["FINANCIAL_EVIDENCE_DOWNSTREAM_DISPOSITION_UNPROVEN"],
        "affected_reason_codes": affected_reasons,
        "surfaces": surfaces,
    }


def _evaluate_corporate(input_payload: Mapping[str, Any], operation: Mapping[str, Any] | None, session: str | None) -> dict[str, Any]:
    corporate = _input_section(input_payload, "corporate") or _mapping(_mapping(operation or {}).get("input_artifacts")).get("corporate_intelligence") or {}
    corporate = _mapping(corporate)
    if not corporate:
        return _reason_domain("EXPLICIT_PARTIAL", ["CORPORATE_INTELLIGENCE_UNAVAILABLE"], {})
    reasons: list[str] = []
    observed = _session(corporate)
    if observed and session and observed != session:
        return _reason_domain("INVALID", ["CORPORATE_INTELLIGENCE_SESSION_MISMATCH"], {"session": observed}, fatal=True, producer_impact=True)
    freshness = _mapping(corporate.get("freshness_counts"))
    if not freshness:
        freshness = _mapping(_get_path(_mapping(operation or {}), "session_coherence.corporate_intelligence_coverage.freshness_counts"))
    if freshness.get("HISTORICAL_OVER_90_DAYS"):
        reasons.append("CORPORATE_HISTORICAL_EVIDENCE_EXPLICITLY_LABELLED")
    status = _as_text(corporate.get("status"))
    if status in {"UNAVAILABLE", "PARTIAL", "BLOCKED"}:
        reasons.append("CORPORATE_" + status)
    return _reason_domain("EXPLICIT_PARTIAL" if reasons else "EXACT_SESSION", reasons, {"session": observed, "freshness_counts": dict(freshness)}, fatal=False)


def _evaluate_prospective(input_payload: Mapping[str, Any], prospective: Mapping[str, Any] | None, operation: Mapping[str, Any] | None, session: str | None, operation_identity: str | None) -> dict[str, Any]:
    value = _input_section(input_payload, "prospective") or _mapping(prospective)
    if not value:
        return _reason_domain("BLOCKED", ["PROSPECTIVE_SNAPSHOT_MISSING"], {}, fatal=True, producer_impact=True)
    reasons: list[str] = []
    invalid = False
    observed = _session(value)
    if session and observed and observed != session:
        invalid = True
        reasons.append("PROSPECTIVE_SESSION_MISMATCH")
    supplied_operation = _as_text(value.get("operation_identity"))
    if supplied_operation and operation_identity and supplied_operation != operation_identity:
        invalid = True
        reasons.append("PROSPECTIVE_OPERATION_IDENTITY_MISMATCH")
    if not _as_text(value.get("snapshot_id")) and not _as_text(value.get("snapshot_identity")):
        reasons.append("PROSPECTIVE_SNAPSHOT_IDENTITY_MISSING")
    release_date = _date_value(session)
    if release_date and _future_outcome_leak(value.get("future_outcomes"), release_date):
        invalid = True
        reasons.append("FUTURE_OUTCOME_EVIDENCE_REJECTED")
    if prospective_decision_retention and value.get("contract_version") == getattr(prospective_decision_retention, "CONTRACT_VERSION", None):
        if not prospective_decision_retention.validate_snapshot(value):
            invalid = True
            reasons.append("PROSPECTIVE_SNAPSHOT_INTEGRITY_INVALID")
    expected_snapshot = _mapping(operation or {}).get("outputs", {}).get("prospective_snapshot") if isinstance(_mapping(operation or {}).get("outputs"), Mapping) else None
    actual_snapshot = value.get("snapshot_id") or value.get("snapshot_identity")
    if expected_snapshot and actual_snapshot and expected_snapshot != actual_snapshot:
        invalid = True
        reasons.append("PROSPECTIVE_OPERATION_OUTPUT_IDENTITY_MISMATCH")
    return _reason_domain("INVALID" if invalid else "EXPLICIT_PARTIAL" if reasons else "EXACT_SESSION", reasons, {"research_session": observed, "snapshot_identity": actual_snapshot, "operation_identity": supplied_operation}, fatal=invalid, producer_impact=invalid)


def _evaluate_handoff(handoff: Mapping[str, Any] | None, session: str | None, operation_identity: str | None, product: Mapping[str, Any] | None, operation: Mapping[str, Any] | None) -> dict[str, Any]:
    if not handoff:
        return _reason_domain("BLOCKED", ["AI_HANDOFF_MISSING"], {}, fatal=True)
    reasons: list[str] = []
    invalid = False
    if session and _session(handoff) != session:
        invalid = True
        reasons.append("AI_HANDOFF_SESSION_MISMATCH")
    observed_operation = _as_text(handoff.get("operation_identity")) or _as_text(_get_path(handoff, "lineage.operation_identity"))
    if not observed_operation:
        invalid = True
        reasons.append("AI_HANDOFF_OPERATION_IDENTITY_MISSING")
    elif operation_identity and observed_operation != operation_identity:
        invalid = True
        reasons.append("AI_HANDOFF_OPERATION_IDENTITY_MISMATCH")
    expected_product = _mapping(_mapping(operation or {}).get("outputs")).get("daily_product")
    observed_product = _as_text(handoff.get("product_identity")) or _as_text(_get_path(handoff, "lineage.product_identity"))
    if expected_product and observed_product and observed_product != expected_product:
        invalid = True
        reasons.append("AI_HANDOFF_PRODUCT_IDENTITY_MISMATCH")
    return _reason_domain("INVALID" if invalid else "EXACT_SESSION", reasons, {"session": _session(handoff), "operation_identity": observed_operation, "product_identity": observed_product}, fatal=invalid)


def _evaluate_dashboard(dashboard: Mapping[str, Any] | None, metadata: Mapping[str, Any] | None, session: str | None, operation_identity: str | None) -> dict[str, Any]:
    if not dashboard:
        return _reason_domain("BLOCKED", ["DASHBOARD_TARGET_MISSING"], {}, fatal=True)
    reasons: list[str] = []
    invalid = False
    dashboard_session = _session(dashboard)
    if not dashboard_session:
        invalid = True
        reasons.append("DASHBOARD_SESSION_MISSING")
    elif session and dashboard_session != session:
        invalid = True
        reasons.append("DASHBOARD_SESSION_MISMATCH")
    source_operation = _as_text(_get_path(dashboard, "source.operation_identity")) or _as_text(dashboard.get("operation_identity"))
    if source_operation and operation_identity and source_operation != operation_identity:
        invalid = True
        reasons.append("DASHBOARD_OPERATION_IDENTITY_MISMATCH")
    if metadata:
        metadata_session = _session(metadata) or _as_text(metadata.get("data_as_of"))
        if session and metadata_session and metadata_session != session:
            invalid = True
            reasons.append("DASHBOARD_RELEASE_METADATA_SESSION_MISMATCH")
        domains = _mapping(metadata.get("domains"))
        if not domains:
            reasons.append("DASHBOARD_DOMAIN_METADATA_UNAVAILABLE")
        else:
            for name, row in domains.items():
                if not isinstance(row, Mapping):
                    continue
                source_session = _as_text(row.get("source_session"))
                status = _as_text(row.get("status"))
                if source_session not in {None, session}:
                    reasons.append("DASHBOARD_DOMAIN_SOURCE_SESSION_MISMATCH:" + str(name).upper())
                if status in {"STALE", "PARTIAL", "UNAVAILABLE", "UNAVAILABLE_FOR_CURRENT_SESSION"}:
                    reasons.append("DASHBOARD_DOMAIN_" + status + "_EXPLICITLY_LABELLED:" + str(name).upper())
                for component_name, component in _mapping(row.get("components")).items():
                    component_source = _as_text(_mapping(component).get("source_session"))
                    if component_source not in {None, session}:
                        reasons.append("DASHBOARD_COMPONENT_SOURCE_SESSION_MISMATCH:" + str(name).upper() + ":" + str(component_name).upper())
    else:
        reasons.append("DASHBOARD_RELEASE_METADATA_UNAVAILABLE")
    return _reason_domain("INVALID" if invalid else "EXPLICIT_PARTIAL" if reasons else "EXACT_SESSION", reasons, {"session": dashboard_session, "source_operation_identity": source_operation, "metadata_present": bool(metadata)}, fatal=invalid)


def _evaluate_watchlist(input_payload: Mapping[str, Any], product: Mapping[str, Any] | None, brief: Mapping[str, Any] | None, dashboard: Mapping[str, Any] | None, governed_watchlist: Sequence[str]) -> dict[str, Any]:
    authority = tuple(governed_watchlist)
    if not authority or len(set(authority)) != len(authority):
        return _reason_domain("BLOCKED", ["GOVERNED_WATCHLIST_AUTHORITY_INVALID"], {"authority_tickers": list(authority)}, fatal=True, producer_impact=True)
    explicit = _input_section(input_payload, "watchlist")
    surfaces: dict[str, list[str]] = {
        "daily_product": _watchlist_tickers(product or {}),
        "daily_integrated_brief": _watchlist_tickers(brief or {}),
        "dashboard": _watchlist_tickers(dashboard or {}),
    }
    if explicit:
        surfaces["acceptance_input"] = [ticker for ticker in _list(explicit.get("tickers")) if isinstance(ticker, str)]
    validation_only = set(_list(explicit.get("validation_only_tickers"))) if explicit else set()
    missing: dict[str, list[str]] = {}
    extras: dict[str, list[str]] = {}
    unlabelled_extras: dict[str, list[str]] = {}
    for name, values in surfaces.items():
        if not values:
            missing[name] = list(authority)
            continue
        value_set = set(values)
        missing_values = [ticker for ticker in authority if ticker not in value_set]
        extra_values = sorted(value_set - set(authority))
        if missing_values:
            missing[name] = missing_values
        if extra_values:
            extras[name] = extra_values
            unmarked = [ticker for ticker in extra_values if ticker not in validation_only]
            if unmarked:
                unlabelled_extras[name] = unmarked
    reasons: list[str] = []
    if missing:
        reasons.append("WATCHLIST_MEMBER_MISSING")
    if extras:
        reasons.append("WATCHLIST_EXTRA_MEMBER_PRESENT")
    if unlabelled_extras:
        reasons.append("WATCHLIST_EXTRA_MEMBER_UNLABELLED")
    invalid = bool(unlabelled_extras)
    return _reason_domain("INVALID" if invalid else "EXPLICIT_PARTIAL" if reasons else "EXACT_SESSION", reasons, {"authority_source": "owner_research_focus.broader_watchlist/v1", "authority_tickers": list(authority), "surface_missing": missing, "surface_extras": extras, "validation_only_tickers": sorted(validation_only)}, fatal=invalid)


def evaluate_artifact_root(
    artifact_root: Path | str,
    *,
    dashboard_root: Path | str | None = None,
    governed_watchlist: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Evaluate exactly one retained Daily Session Operation directory without writes."""
    root = Path(artifact_root)
    if not root.is_dir():
        raise ReleaseAcceptanceError("ARTIFACT_ROOT_NOT_DIRECTORY:" + str(root))
    input_loaded = _load_first(root, ("release_acceptance_input.json",))
    input_payload = input_loaded.payload or {}
    if input_payload and input_payload.get("contract_version") != INPUT_CONTRACT_VERSION:
        raise ReleaseAcceptanceError("ACCEPTANCE_INPUT_CONTRACT_UNRECOGNIZED")

    loaded = {name: _load_first(root, names) for name, names in _JSON_CANDIDATES.items() if name not in {"dashboard", "dashboard_metadata"}}
    dashboard_base = Path(dashboard_root) if dashboard_root is not None else root
    dashboard = _load_first(dashboard_base, _JSON_CANDIDATES["dashboard"])
    dashboard_metadata = _load_first(dashboard_base, _JSON_CANDIDATES["dashboard_metadata"])
    operation = loaded["operation"].payload
    target_session = _as_text(input_payload.get("session"))
    lineage, session, operation_identity = _evaluate_daily_lineage(operation, target_session=target_session)
    product, brief, prospective, handoff = (loaded[name].payload for name in ("product", "brief", "prospective", "handoff"))
    authority = tuple(governed_watchlist) if governed_watchlist is not None else owner_research_focus.broader_watchlist()
    domains = {
        "daily_session_lineage": lineage,
        "signal_presentation": _evaluate_signals(input_payload, brief, dashboard_metadata.payload, session),
        "technical_target_close": _evaluate_technical(input_payload, brief, session),
        "valuation_readiness": _evaluate_valuation(input_payload, operation, session),
        "financial_cutoff": _evaluate_financial(input_payload, brief, session),
        "corporate_freshness": _evaluate_corporate(input_payload, operation, session),
        "prospective_snapshot": _evaluate_prospective(input_payload, prospective, operation, session, operation_identity),
        "ai_handoff": _evaluate_handoff(handoff, session, operation_identity, product, operation),
        "dashboard_release": _evaluate_dashboard(dashboard.payload, dashboard_metadata.payload, session, operation_identity),
        "watchlist_authority": _evaluate_watchlist(input_payload, product, brief, dashboard.payload, authority),
    }
    release_aggregation = _evaluate_financial_release_aggregation(
        domains["financial_cutoff"], product=product, brief=brief, handoff=handoff, dashboard=dashboard.payload,
    )
    if any(row["fatal_for_release"] for row in domains.values()):
        overall = "INVALID_RELEASE"
    elif release_aggregation["state"] == "ADMITTED":
        overall = "INVALID_RELEASE"
    elif release_aggregation["state"] == "UNPROVEN":
        overall = "BLOCKED"
    elif any(row["state"] == "BLOCKED" for row in domains.values()):
        overall = "BLOCKED"
    elif any(row["state"] == "EXPLICIT_PARTIAL" for row in domains.values()):
        overall = "PASS_WITH_EXPLICIT_PARTIALS"
    else:
        overall = "PASS"
    producer_invalid = any(row["invalidates_current_research"] for row in domains.values())
    producer_partials = any(domains[name]["state"] == "EXPLICIT_PARTIAL" for name in ("signal_presentation", "technical_target_close", "valuation_readiness", "financial_cutoff", "corporate_freshness"))
    report = {
        "contract_version": CONTRACT_VERSION,
        "artifact_root": str(root),
        "input_contract": input_payload.get("contract_version") if input_payload else None,
        "session": session,
        "operation_identity": operation_identity,
        "overall_state": overall,
        "current_research_state": "NOT_USABLE" if producer_invalid else "USABLE_WITH_EXPLICIT_PARTIALS" if producer_partials else "USABLE",
        "current_research_usable": not producer_invalid,
        "domains": domains,
        "release_aggregation": release_aggregation,
        "artifacts_read": {
            name: {"path": item.relative_path, "error": item.error}
            for name, item in {**loaded, "dashboard": dashboard, "dashboard_metadata": dashboard_metadata, "acceptance_input": input_loaded}.items()
        },
        "authority_boundary": {
            "read_only": True,
            "network_calls": False,
            "runtime_data_writes": False,
            "analytical_recalculation": False,
            "watchlist_source": "owner_research_focus.broader_watchlist/v1",
        },
    }
    return report


def human_summary(report: Mapping[str, Any]) -> str:
    """Stable compact summary for an operator terminal; contains no mutable path discovery."""
    lines = [
        "CANONICAL_DAILY_RELEASE_ACCEPTANCE=" + str(report.get("overall_state")),
        "SESSION=" + str(report.get("session") or "UNRESOLVED"),
        "CURRENT_RESEARCH=" + str(report.get("current_research_state")),
        "RELEASE_AGGREGATION=" + str(_mapping(report.get("release_aggregation")).get("state") or "NOT_APPLICABLE"),
    ]
    for name in DOMAIN_KEYS:
        domain = _mapping(_mapping(report.get("domains")).get(name))
        reasons = ",".join(_list(domain.get("reason_codes"))) or "NONE"
        lines.append("DOMAIN_" + name.upper() + "=" + str(domain.get("state")) + " reasons=" + reasons)
    return "\n".join(lines)
