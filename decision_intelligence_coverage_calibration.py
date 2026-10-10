"""Coverage, historical enrichment, and calibration context on one spine.

This module joins existing projections. It does not create a decision engine,
a buy score, a probability, or a sizing result. Missing evidence stays missing.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import decision_outcome_calibration_review as calibration
import historical_temporal_research_panel as panel
import stocklookup_core.decision.human_ai_decision_evidence_packet as evidence_packet

CONTRACT_VERSION = "decision_intelligence_coverage_calibration/v1"
CANONICAL_DENOMINATOR = 1683
AUTHORITY_EFFECT = "NONE / DECISION_INTELLIGENCE_RESEARCH_COVERAGE_AND_CALIBRATION_ONLY"
STATUSES = (
    "CURRENT",
    "HISTORICAL_RETAINED",
    "STALE",
    "PROXY",
    "BLOCKED",
    "UNAVAILABLE",
    "UNKNOWN",
    "NOT_APPLICABLE",
)
SPECIALIST_ENTITIES = frozenset({"bank", "securities", "insurance", "finance_company"})
FOCUS_TICKERS = ("HPG", "PAN", "POW", "SSI", "EVF", "FPT", "NVL", "PNJ", "QNS")
VALUATION_METRICS = ("P/E", "P/B", "P/S", "EV/EBITDA", "EV/Sales", "enterprise_value", "market_cap")
STRICT_METRIC_STATUSES = frozenset({"READY", "STRICT_READY", "VALUATION_READY"})
DENOMINATOR_TOKENS = ("DENOMINATOR", "CURRENCY_MISMATCH", "INCONSISTENT_DENOMINATOR")
NOT_RETAINED = "NOT_RETAINED_AT_T0"
NO_ANALOGUE = "No historical analogue conclusion because trigger/invalidation was not retained at T0."


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _status(value: Any) -> str:
    if isinstance(value, str) and value in STATUSES:
        return value
    return "UNKNOWN"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _codes(values: Iterable[Any] | None) -> list[str]:
    found: list[str] = []
    for value in values or []:
        if isinstance(value, str) and value and value not in found:
            found.append(value)
    return found[:12]


def _metric_statuses(metrics: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(metrics, Mapping):
        return []
    statuses = []
    for name in VALUATION_METRICS:
        body = metrics.get(name)
        if isinstance(body, Mapping) and isinstance(body.get("status"), str):
            statuses.append(body["status"])
    return statuses


def _has_token(codes: Iterable[str], tokens: tuple[str, ...]) -> bool:
    for code in codes:
        upper = code.upper()
        if any(token in upper for token in tokens):
            return True
    return False


def project_member(
    ticker: str,
    session: str,
    *,
    universe: Mapping[str, Any] | None = None,
    technical: Mapping[str, Any] | None = None,
    valuation: Mapping[str, Any] | None = None,
    corporate_intelligence: Mapping[str, Any] | None = None,
    events: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """One compact row. Absent projections stay UNKNOWN. They are not inferred."""
    universe = universe or {}
    technical = technical or {}
    valuation = valuation or {}
    corporate_intelligence = corporate_intelligence or {}
    events = events or []

    activity = universe.get("activity_and_session_state")
    if activity == "ACTIVE_LISTED_OBSERVED":
        universe_status = "CURRENT"
    elif activity == "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION":
        universe_status = "UNAVAILABLE"
    elif activity == "INACTIVE_OR_DELISTED":
        universe_status = "BLOCKED"
    elif activity == "NOT_APPLICABLE_NON_EQUITY":
        universe_status = "NOT_APPLICABLE"
    elif universe:
        universe_status = "UNKNOWN"
    else:
        universe_status = "UNKNOWN"

    if technical.get("is_current_session") is True and technical.get("has_exact_session_bar") is True:
        price_status = "CURRENT"
        technical_status = "CURRENT"
    elif technical.get("is_current_session") is False and technical.get("feature_as_of_session"):
        price_status = "STALE"
        technical_status = "STALE"
    elif technical.get("disposition") in {"PROVIDER_SESSION_UNAVAILABLE", "SESSION_MISSING"}:
        price_status = "UNAVAILABLE"
        technical_status = "UNAVAILABLE"
    elif technical:
        price_status = "UNKNOWN"
        technical_status = "UNKNOWN"
    else:
        price_status = "UNKNOWN"
        technical_status = "UNKNOWN"

    financial = (valuation.get("financial_input") or {}) if valuation else {}
    authority = financial.get("authority")
    if authority == "OFFICIAL_QUALIFIED":
        fundamental_status = "CURRENT"
    elif authority == "PROVIDER_RESEARCH":
        fundamental_status = "PROXY"
    elif authority == "UNAVAILABLE":
        fundamental_status = "UNAVAILABLE"
    elif authority == "BLOCKED":
        fundamental_status = "BLOCKED"
    elif valuation:
        fundamental_status = "UNKNOWN"
    else:
        fundamental_status = "UNKNOWN"

    metrics = valuation.get("metrics") if isinstance(valuation.get("metrics"), Mapping) else {}
    statuses = _metric_statuses(metrics)
    research_usable = "RESEARCH_USABLE" in statuses
    strict_ready = any(status in STRICT_METRIC_STATUSES and status != "RESEARCH_USABLE" for status in statuses)
    # RESEARCH_USABLE is not strict. A strict status still has to lack the research-only label.
    if strict_ready:
        for name in VALUATION_METRICS:
            body = metrics.get(name) if isinstance(metrics.get(name), Mapping) else {}
            labels = body.get("labels") or []
            if body.get("status") in STRICT_METRIC_STATUSES and "CURRENT_RESEARCH_ONLY" in labels:
                strict_ready = False
                break
    if not valuation:
        valuation_status = "UNKNOWN"
    elif research_usable and not strict_ready:
        valuation_status = "PROXY"
    elif strict_ready:
        valuation_status = "CURRENT"
    elif statuses and all(status in {"BLOCKED", "NOT_APPLICABLE"} for status in statuses):
        valuation_status = "BLOCKED" if "BLOCKED" in statuses else "NOT_APPLICABLE"
    else:
        valuation_status = "UNAVAILABLE" if statuses else "UNKNOWN"

    blocked: list[str] = []
    share = valuation.get("share_basis_input") if isinstance(valuation.get("share_basis_input"), Mapping) else {}
    blocked.extend(_codes(share.get("blocked_reasons")))
    for name in VALUATION_METRICS:
        body = metrics.get(name) if isinstance(metrics.get(name), Mapping) else {}
        blocked.extend(code for code in _codes(body.get("blocked_reasons")) if code not in blocked)
        compatibility = body.get("monetary_compatibility") if isinstance(body.get("monetary_compatibility"), Mapping) else {}
        if compatibility.get("status") not in (None, "COMPATIBLE"):
            blocked.append(str(compatibility.get("status")))
    denominator_conflict = _has_token(blocked, DENOMINATOR_TOKENS)
    share_blocked = bool(share.get("blocked_reasons"))
    if not valuation:
        share_status = "UNKNOWN"
        denominator_status = "UNKNOWN"
    elif share_blocked:
        share_status = "BLOCKED"
        denominator_status = "BLOCKED" if denominator_conflict else "UNKNOWN"
    elif share.get("status") == "QUALIFIED_OFFICIAL":
        share_status = "CURRENT"
        denominator_status = "BLOCKED" if denominator_conflict else "CURRENT"
    elif share.get("authority") in {"PROVIDER_REPORTED_LAGGED", "qualified_official"} or share.get("status") == "PROVIDER_REPORTED_LAGGED":
        share_status = "STALE" if "LAGGED" in str(share.get("status") or share.get("authority")) else "PROXY"
        denominator_status = "BLOCKED" if denominator_conflict else "UNKNOWN"
    else:
        share_status = "UNKNOWN"
        denominator_status = "BLOCKED" if denominator_conflict else "UNKNOWN"
    if str(share.get("authority") or "").upper() == "PROVIDER_REPORTED_LAGGED" or share.get("status") == "PROVIDER_REPORTED_LAGGED":
        share_status = "STALE"

    disposition = corporate_intelligence.get("intelligence_disposition")
    if disposition == "HISTORICAL_INTELLIGENCE_ONLY":
        ci_status = "HISTORICAL_RETAINED"
    elif disposition == "CURRENT_INTELLIGENCE":
        ci_status = "CURRENT"
    elif disposition == "NO_RETAINED_INTELLIGENCE":
        ci_status = "UNAVAILABLE"
    elif corporate_intelligence:
        ci_status = "UNKNOWN"
    else:
        ci_status = "UNKNOWN"
    freshness_values = []
    for event in ((corporate_intelligence.get("catalyst_research") or {}).get("historical_context") or []):
        if isinstance(event, Mapping) and isinstance(event.get("freshness"), str):
            freshness_values.append(event["freshness"])
    if not corporate_intelligence:
        ci_freshness = "UNKNOWN"
    elif any(value.startswith("CURRENT") for value in freshness_values):
        ci_freshness = "CURRENT"
    elif freshness_values:
        ci_freshness = "HISTORICAL_RETAINED" if any("HISTORICAL" in value for value in freshness_values) else "UNKNOWN"
    else:
        ci_freshness = "UNAVAILABLE" if disposition == "NO_RETAINED_INTELLIGENCE" else "UNKNOWN"

    current_event = "UNKNOWN"
    historical_event = "UNKNOWN"
    if events:
        current_hits = False
        historical_hits = False
        for event in events:
            state = str(event.get("event_state") or "")
            days_to = event.get("days_to_ex_date")
            days_since = event.get("days_since_ex_date")
            if state in {"UPCOMING", "CURRENT"} or (isinstance(days_to, (int, float)) and not isinstance(days_to, bool) and days_to >= 0):
                current_hits = True
            if state in {"PAST", "RECENT"} or (isinstance(days_since, (int, float)) and not isinstance(days_since, bool) and days_since > 0):
                historical_hits = True
        current_event = "CURRENT" if current_hits else "UNKNOWN"
        historical_event = "HISTORICAL_RETAINED" if historical_hits or ci_status == "HISTORICAL_RETAINED" else "UNKNOWN"
    elif ci_status == "HISTORICAL_RETAINED":
        historical_event = "HISTORICAL_RETAINED"

    entity = valuation.get("entity_class") if isinstance(valuation.get("entity_class"), str) else None
    if entity in SPECIALIST_ENTITIES:
        specialist = "CURRENT"
    elif entity == "corporate":
        specialist = "NOT_APPLICABLE"
    elif valuation:
        specialist = "UNKNOWN"
    else:
        specialist = "UNKNOWN"

    price_input = valuation.get("price_input") if isinstance(valuation.get("price_input"), Mapping) else {}
    pit_status = "BLOCKED" if price_input.get("historical_pit_eligible") is False or price_input.get("raw_as_traded") == "NOT_PROMOTED" else "UNKNOWN"

    period = None
    pe = metrics.get("P/E") if isinstance(metrics.get("P/E"), Mapping) else {}
    if isinstance(pe.get("financial_period"), str):
        period = pe["financial_period"]

    return {
        "ticker": ticker,
        "session": session,
        "universe_status": universe_status,
        "price_evidence_status": price_status,
        "technical_status": technical_status,
        "fundamental_evidence_status": fundamental_status,
        "fundamental_period": period,
        "fundamental_knowledge_status": "UNKNOWN",
        "valuation_status": valuation_status,
        "valuation_research_usable": research_usable,
        "valuation_strict_ready": bool(strict_ready and valuation_status == "CURRENT"),
        "denominator_integrity_status": denominator_status if valuation else "UNKNOWN",
        "denominator_conflict": bool(denominator_conflict),
        "share_basis_status": share_status,
        "share_basis_blocked": bool(share_blocked),
        "corporate_intelligence_status": ci_status,
        "ci_freshness": ci_freshness,
        "corporate_action_relevance": historical_event if historical_event == "HISTORICAL_RETAINED" else ci_status if ci_status == "HISTORICAL_RETAINED" else "UNKNOWN",
        "current_event_status": current_event,
        "historical_corporate_action_status": historical_event,
        "specialist_sector_status": specialist,
        "pit_limitation_status": pit_status,
        "primary_blocker_families": blocked[:8],
        "source_identities": {
            "universe": universe.get("ticker") and "current_universe_status_and_session_coverage_resolution/v1",
            "technical_disposition": technical.get("technical_status"),
            "valuation_content": valuation.get("content_identity"),
            "financial_source": financial.get("source_artifact_identity"),
            "corporate_intelligence": corporate_intelligence.get("corporate_intelligence_record_id"),
            "event_ids": [event.get("event_id") for event in events if isinstance(event.get("event_id"), str)][:8],
        },
        "provider_research_financial": authority == "PROVIDER_RESEARCH",
        "official_current_financial": authority == "OFFICIAL_QUALIFIED",
        "earnings_quality": "UNKNOWN",
    }


def summarize_coverage(rows: list[Mapping[str, Any]], *, denominator: int) -> dict[str, Any]:
    if len(rows) != denominator:
        raise ValueError("DENOMINATOR_SWITCH")
    counts = {name: 0 for name in (
        "financial_current",
        "financial_historical",
        "provider_research",
        "valuation_research_usable",
        "valuation_strict",
        "denominator_conflict",
        "share_basis_blocked",
        "ci_current",
        "ci_historical",
        "event_current",
        "event_historical",
        "specialist_sector",
        "missing",
        "price_current",
        "technical_stale",
    )}
    for row in rows:
        if row.get("official_current_financial"):
            counts["financial_current"] += 1
        if row.get("fundamental_evidence_status") == "HISTORICAL_RETAINED":
            counts["financial_historical"] += 1
        if row.get("provider_research_financial"):
            counts["provider_research"] += 1
        if row.get("valuation_research_usable"):
            counts["valuation_research_usable"] += 1
        if row.get("valuation_strict_ready"):
            counts["valuation_strict"] += 1
        if row.get("denominator_conflict"):
            counts["denominator_conflict"] += 1
        if row.get("share_basis_blocked"):
            counts["share_basis_blocked"] += 1
        if row.get("corporate_intelligence_status") == "CURRENT":
            counts["ci_current"] += 1
        if row.get("corporate_intelligence_status") == "HISTORICAL_RETAINED":
            counts["ci_historical"] += 1
        if row.get("current_event_status") == "CURRENT":
            counts["event_current"] += 1
        if row.get("historical_corporate_action_status") == "HISTORICAL_RETAINED":
            counts["event_historical"] += 1
        if row.get("specialist_sector_status") == "CURRENT":
            counts["specialist_sector"] += 1
        if row.get("price_evidence_status") == "CURRENT":
            counts["price_current"] += 1
        if row.get("technical_status") == "STALE":
            counts["technical_stale"] += 1
        if (
            row.get("fundamental_evidence_status") in {"UNKNOWN", "UNAVAILABLE"}
            and not row.get("valuation_research_usable")
            and row.get("corporate_intelligence_status") in {"UNKNOWN", "UNAVAILABLE"}
            and row.get("current_event_status") != "CURRENT"
            and row.get("historical_corporate_action_status") != "HISTORICAL_RETAINED"
        ):
            counts["missing"] += 1
    return {
        "denominator": denominator,
        "rows": len(rows),
        "counts": counts,
        "denominator_switched": False,
    }


def build_coverage_index(session: str, members: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [project_member(
        str(member["ticker"]),
        session,
        universe=member.get("universe") if isinstance(member.get("universe"), Mapping) else {},
        technical=member.get("technical") if isinstance(member.get("technical"), Mapping) else {},
        valuation=member.get("valuation") if isinstance(member.get("valuation"), Mapping) else {},
        corporate_intelligence=member.get("corporate_intelligence") if isinstance(member.get("corporate_intelligence"), Mapping) else {},
        events=member.get("events") if isinstance(member.get("events"), list) else [],
    ) for member in members]
    rows.sort(key=lambda row: row["ticker"])
    tickers = [row["ticker"] for row in rows]
    if len(tickers) != len(set(tickers)):
        raise ValueError("DUPLICATE_UNIVERSE_MEMBER")
    summary = summarize_coverage(rows, denominator=len(rows))
    body = {
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "denominator": len(rows),
        "canonical_denominator_required": CANONICAL_DENOMINATOR,
        "canonical_denominator_met": len(rows) == CANONICAL_DENOMINATOR,
        "authority_effect": AUTHORITY_EFFECT,
        "summary": summary,
        "rows": rows,
    }
    body["index_identity"] = "decision_intelligence_coverage_index:" + _sha({"session": session, "tickers": tickers, "summary": summary["counts"]})
    return body


def require_canonical_denominator(index: Mapping[str, Any]) -> None:
    if index.get("denominator") != CANONICAL_DENOMINATOR or index.get("summary", {}).get("denominator") != CANONICAL_DENOMINATOR:
        raise ValueError("DENOMINATOR_SWITCH")
    if len(index.get("rows") or []) != CANONICAL_DENOMINATOR:
        raise ValueError("DENOMINATOR_SWITCH")


def refuse_lookahead(session: str, knowledge_date: str | None) -> bool:
    """True when a knowledge or event date is after the row session."""
    if not knowledge_date:
        return False
    return str(knowledge_date) > str(session)


def project_corporate_action(event: Mapping[str, Any], session: str) -> dict[str, Any]:
    """Copy a retained action. Planned issuance does not become executed."""
    published = event.get("announcement_date") or event.get("published_at") or event.get("knowledge_date")
    event_date = event.get("event_date") or event.get("ex_date")
    if refuse_lookahead(session, published if isinstance(published, str) else None):
        return {"status": "BLOCKED", "reason": "LOOKAHEAD_KNOWLEDGE_DATE", "executed": False, "ex_date_inferred": False}
    if refuse_lookahead(session, event_date if isinstance(event_date, str) else None) and event.get("ex_date_known_at_session") is not True:
        return {"status": "BLOCKED", "reason": "LOOKAHEAD_EVENT_DATE", "executed": False, "ex_date_inferred": False}
    lifecycle = str(event.get("lifecycle") or event.get("status") or "UNKNOWN")
    planned = lifecycle in {"PLANNED", "APPROVED"}
    executed = lifecycle == "EXECUTED" and not planned
    return {
        "status": "HISTORICAL_RETAINED" if executed else "CURRENT" if planned else "UNKNOWN",
        "type": event.get("event_type"),
        "announcement_date": published if isinstance(published, str) else None,
        "event_date": event.get("ex_date") if isinstance(event.get("ex_date"), str) else None,
        "ex_date_inferred": False,
        "lifecycle": "EXECUTED" if executed else "PLANNED" if planned else lifecycle,
        "executed": executed,
        "planned_shares_converted_to_executed": False,
        "share_basis_relevance": event.get("affected_share_basis") or "UNKNOWN",
        "event_identity": event.get("event_id"),
        "tier": event.get("evidence_tier") or panel.RECONSTRUCTED_RESEARCH,
    }


def feedback_overlay(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compact decision context and a separate outcome namespace."""
    explanatory = calibration.project_explanatory_axes(record)
    population, _reason = calibration._population(record)
    tier = population if population in {"PROSPECTIVE_GENUINE", "PIT_AUTHORITATIVE", "RECONSTRUCTED_RESEARCH", "EXPLANATORY_ONLY"} else "UNKNOWN"
    retained = explanatory["retention"] == "RETAINED"
    decision_status = "PRESENT" if retained else NOT_RETAINED
    tactical = record.get("tactical_structure_state")
    if tactical == calibration.NOT_RETAINED_AT_T0:
        tactical = None
    decision = {
        "trigger": {"value": explanatory.get("trigger_state"), "tier": tier if explanatory.get("trigger_state") else "UNKNOWN", "status": "PRESENT" if explanatory.get("trigger_state") else decision_status},
        "confirmation": {"value": explanatory.get("confirmation_state"), "tier": tier if explanatory.get("confirmation_state") else "UNKNOWN", "status": "PRESENT" if explanatory.get("confirmation_state") else decision_status},
        "invalidation": {"value": explanatory.get("authority_disclaimer_codes") or None, "tier": "EXPLANATORY_ONLY", "status": decision_status if not retained else "PRESENT"},
        "tactical_state": {"value": tactical, "tier": tier if tactical else "UNKNOWN", "status": "PRESENT" if tactical else decision_status},
        "strategy_state": {"value": None, "tier": "UNKNOWN", "status": decision_status},
        "uncertainty": {"value": explanatory["retention"], "tier": "EXPLANATORY_ONLY", "status": "PRESENT"},
    }
    outcomes = []
    for horizon_row in calibration.compact_horizons(record):
        outcomes.append({
            "horizon": horizon_row["horizon"],
            "maturity_status": horizon_row["status"],
            "price_basis_qualification": horizon_row.get("price_basis") or "UNSPECIFIED",
            "source_population": horizon_row.get("population"),
            "tier": horizon_row.get("population") or "UNKNOWN",
            "forward_return": horizon_row.get("forward_return"),
            "mfe": horizon_row.get("mfe"),
            "mae": horizon_row.get("mae"),
            "failure_status": horizon_row.get("outcome_label"),
        })
    return {"decision": decision, "outcomes": outcomes, "explanatory": explanatory}


def panel_field_census(enriched: Mapping[str, Any]) -> dict[str, Any]:
    populated: dict[str, int] = {}
    missing: dict[str, int] = {}
    outcome_rows = 0
    for row in enriched.get("rows") or []:
        for name, field in (row.get("fields") or {}).items():
            status = field.get("status") if isinstance(field, Mapping) else "MISSING"
            if status in {"MISSING", "NOT_OBSERVED", NOT_RETAINED}:
                missing[name] = missing.get(name, 0) + 1
            else:
                populated[name] = populated.get(name, 0) + 1
        if (row.get("outcome_namespace") or {}).get("outcomes"):
            outcome_rows += 1
    return {
        "rows": len(enriched.get("rows") or []),
        "fields_populated": dict(sorted(populated.items())),
        "fields_missing_or_not_retained": dict(sorted(missing.items())),
        "rows_with_outcome_namespace": outcome_rows,
        "parent_tiers": enriched.get("tier_counts"),
        "field_tiers": (enriched.get("enrichment") or {}).get("field_tier_counts"),
    }


def research_distinction(row: Mapping[str, Any]) -> list[str]:
    """Generic readings. No ticker branch."""
    notes = []
    if row.get("earnings_quality") == "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE":
        notes.append("NON_RECURRING_DOES_NOT_AUTHORIZE_RECURRING_CHEAPNESS")
    if row.get("specialist_sector_status") == "CURRENT":
        notes.append("SPECIALIST_SECTOR_VALUATION_SEMANTICS")
    if row.get("technical_status") == "CURRENT" and row.get("fundamental_evidence_status") in {"UNKNOWN", "UNAVAILABLE", "BLOCKED"}:
        notes.append("TECHNICAL_CONTEXT_SEPARATE_FROM_FUNDAMENTAL_EVIDENCE")
    if row.get("share_basis_blocked"):
        notes.append("SHARE_BASIS_CONFLICT_RETAINED")
    if row.get("historical_corporate_action_status") == "HISTORICAL_RETAINED":
        notes.append("CORPORATE_ACTION_NOT_HIDDEN")
    structure = row.get("technical_structure")
    if structure == "UPTREND" or row.get("tactical_state") == "UPTREND_CONFIRMED":
        notes.append("UPTREND_NOT_RELABELED_BOTTOM_FISHING")
    if row.get("price_evidence_status") != "CURRENT" and row.get("fundamental_evidence_status") == "CURRENT":
        notes.append("FUNDAMENTAL_CONTEXT_CAN_COEXIST_WITH_INCOMPLETE_PRICE_CONFIRMATION")
    return notes


def focus_reports(index: Mapping[str, Any], enriched_panel: Mapping[str, Any] | None = None, *, tickers: tuple[str, ...] = FOCUS_TICKERS) -> dict[str, Any]:
    by_ticker = {row["ticker"]: row for row in index.get("rows") or []}
    panel_rows = {}
    for row in (enriched_panel or {}).get("rows") or []:
        panel_rows.setdefault(row.get("ticker"), []).append(row)
    reports = {}
    for ticker in tickers:
        coverage = by_ticker.get(ticker)
        history = panel_rows.get(ticker) or []
        trigger_missing = False
        for item in history:
            trigger = (item.get("fields") or {}).get("trigger") or {}
            if trigger.get("status") in {NOT_RETAINED, "MISSING"}:
                trigger_missing = True
        limitation = NO_ANALOGUE if history and trigger_missing and not any((item.get("fields") or {}).get("trigger", {}).get("value") for item in history) else None
        if not history:
            limitation = limitation or "NO_RETAINED_COHORT_EVIDENCE"
        tactical_states = sorted({
            ((item.get("fields") or {}).get("tactical_state") or {}).get("value")
            for item in history
            if ((item.get("fields") or {}).get("tactical_state") or {}).get("value")
        })
        distinctions = research_distinction(coverage or {})
        if "UPTREND" in tactical_states or "UPTREND_CONFIRMED" in tactical_states:
            if "UPTREND_NOT_RELABELED_BOTTOM_FISHING" not in distinctions:
                distinctions.append("UPTREND_NOT_RELABELED_BOTTOM_FISHING")
        reports[ticker] = {
            "coverage_present": coverage is not None,
            "historical_tactical_states": tactical_states,
            "coverage": {key: (coverage or {}).get(key) for key in (
                "universe_status", "price_evidence_status", "technical_status", "fundamental_evidence_status",
                "valuation_status", "valuation_research_usable", "share_basis_status", "corporate_intelligence_status",
                "current_event_status", "historical_corporate_action_status", "specialist_sector_status",
                "denominator_conflict", "earnings_quality", "primary_blocker_families",
            )},
            "historical_rows": len(history),
            "distinctions": distinctions,
            "retention_limitation": limitation,
        }
    return reports


def build_focus_packet(ticker: str, report: Mapping[str, Any]) -> dict[str, Any]:
    coverage = report.get("coverage") or {}
    return evidence_packet.build_packet(
        ticker=ticker,
        sections={"stock": {key: value for key, value in coverage.items() if value is not None}, "uncertainty": {}},
        feature_measurements={key: value for key, value in coverage.items() if isinstance(value, (str, int, float))},
        spine={
            "coverage_state": coverage.get("fundamental_evidence_status"),
            "denominator_integrity": "CONFLICT" if coverage.get("denominator_conflict") else coverage.get("valuation_status"),
            "ci_freshness": coverage.get("corporate_intelligence_status"),
            "corporate_action_state": coverage.get("historical_corporate_action_status"),
            "sample_quality": None,
            "matched_control_readiness": None,
            "matched_control_edge": None,
            "retention_limitation": report.get("retention_limitation"),
        },
        canonical_packet_identity="current_research_decision_packet:pointer",
    )


def load_retained_coverage(evidence_root: Path, *, session: str = "2026-10-06") -> dict[str, Any]:
    """Join the small 2026-10-06 status artifacts. Full bodies are discarded."""
    root = Path(evidence_root)
    universe_path = root / f"current-universe-status-and-session-coverage-resolution-v1-{session.replace('-', '')}" / "current_universe_status_and_session_coverage_resolution_artifact.json"
    technical_path = root / f"same-session-technical-coverage-recovery-v1-{session.replace('-', '')}" / "same_session_technical_coverage_disposition_artifact.json"
    valuation_path = root / f"market-wide-current-valuation-v1-{session.replace('-', '')}-session{session.replace('-', '')}" / "market_wide_current_valuation_artifact.json"
    intelligence_path = root / f"market-wide-current-corporate-intelligence-v1-{session.replace('-', '')}" / "market_wide_current_corporate_intelligence_artifact.json"
    event_path = root / f"current-official-event-context-integration-v1-{session.replace('-', '')}" / "current_official_event_context_artifact.json"
    universe = _load_json(universe_path)
    technical = _load_json(technical_path)
    valuation = _load_json(valuation_path)
    intelligence = _load_json(intelligence_path)
    events = _load_json(event_path)
    return join_coverage_artifacts(session=session, universe=universe, technical=technical,
                                   valuation=valuation, intelligence=intelligence, events=events)


def join_coverage_artifacts(*, session: str, universe: Mapping[str, Any], technical: Mapping[str, Any],
                            valuation: Mapping[str, Any], intelligence: Mapping[str, Any],
                            events: Mapping[str, Any]) -> dict[str, Any]:
    """Existing coverage projection shared by dated closure and explicit-source inspection."""
    universe_records = universe.get("records") if isinstance(universe.get("records"), Mapping) else {}
    technical_records = technical.get("records") if isinstance(technical.get("records"), Mapping) else {}
    valuation_records = valuation.get("records") if isinstance(valuation.get("records"), Mapping) else {}
    intelligence_records = intelligence.get("records") if isinstance(intelligence.get("records"), Mapping) else {}
    event_rows = events.get("all_current_universe_event_records") if isinstance(events.get("all_current_universe_event_records"), list) else []
    events_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for event in event_rows:
        if isinstance(event, Mapping) and isinstance(event.get("ticker"), str):
            events_by_ticker.setdefault(event["ticker"], []).append(dict(event))
    members = []
    for ticker in sorted(universe_records):
        members.append({
            "ticker": ticker,
            "universe": universe_records[ticker],
            "technical": technical_records.get(ticker) or {},
            "valuation": valuation_records.get(ticker) or {},
            "corporate_intelligence": intelligence_records.get(ticker) or {},
            "events": events_by_ticker.get(ticker) or [],
        })
    del universe, technical, valuation, intelligence, events
    index = build_coverage_index(session, members)
    require_canonical_denominator(index)
    return index


def retained_closure(evidence_root: Path, *, session: str = "2026-10-06") -> dict[str, Any]:
    """Read-only closure over retained evidence. Artifacts are not rewritten."""
    import tracemalloc

    tracemalloc.start()
    index = load_retained_coverage(evidence_root, session=session)
    coverage_bytes = len(_canon(index["rows"]).encode("utf-8"))
    historical = panel.index_retained_root(Path(evidence_root) / "canonical-post-close-v1", focus_tickers=FOCUS_TICKERS)
    keys = {(str(row.get("session")), str(row.get("ticker"))) for row in historical.get("rows") or []}
    overlays: dict[tuple[str, str], dict[str, Any]] = {}
    feedback_path = Path(evidence_root) / "prospective-decision-outcome-feedback-v1" / session / "prospective_decision_feedback_artifact.json"
    review_rows = []
    earliest = None
    warning_rows = 0
    supportive_rows = 0
    if feedback_path.is_file():
        for record in calibration.iter_feedback_records(feedback_path):
            compact_rows = calibration.compact_horizons(record)
            review_rows.extend(compact_rows)
            if compact_rows and isinstance(compact_rows[0].get("warnings"), list):
                warning_rows += 1
            if isinstance(compact_rows[0].get("supportive_features_present"), bool) if compact_rows else False:
                supportive_rows += 1
            axes = compact_rows[0].get("explanatory_axes") if compact_rows else {}
            decision_session = record.get("decision_session")
            if isinstance(axes, Mapping) and axes.get("retention") == "RETAINED" and isinstance(decision_session, str):
                if earliest is None or decision_session < earliest:
                    earliest = decision_session
            key = (str(decision_session), str(record.get("ticker") or ""))
            if key in keys and key not in overlays:
                overlays[key] = feedback_overlay(record)
            del record
    review = calibration.review_observations(review_rows) if review_rows else {}
    del review_rows
    enriched = panel.enrich_panel(historical, overlays)
    census = panel_field_census(enriched)
    reports = focus_reports(index, enriched)
    packets = {ticker: build_focus_packet(ticker, report) for ticker, report in reports.items()}
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    enriched_bytes = len(_canon(enriched["rows"]).encode("utf-8"))
    return {
        "contract_version": CONTRACT_VERSION,
        "authority_effect": AUTHORITY_EFFECT,
        "session": session,
        "coverage_summary": index["summary"],
        "coverage_index_identity": index["index_identity"],
        "coverage_summary_bytes": coverage_bytes,
        "historical_panel": {
            "sessions_opened": historical.get("sessions_opened"),
            "row_count": historical.get("row_count"),
            "tier_counts": historical.get("tier_counts"),
            "panel_identity": historical.get("panel_identity"),
            "enrichment": enriched.get("enrichment"),
            "census": census,
            "census_bytes": enriched_bytes,
        },
        "calibration": {
            "mature_counts": review.get("mature_counts"),
            "cohorts": len(review.get("cohorts") or []),
            "cohorts_with_setup_warnings": sum(1 for item in review.get("cohorts") or [] if (item.get("false_positive_review") or {}).get("status") == "PRESENT"),
            "cohorts_with_supportive_features": sum(1 for item in review.get("cohorts") or [] if (item.get("false_negative_review") or {}).get("status") == "PRESENT"),
            "cohorts_with_mfe": sum(1 for item in review.get("cohorts") or [] if (item.get("mfe") or {}).get("status") == "PRESENT"),
            "cohorts_with_mae": sum(1 for item in review.get("cohorts") or [] if (item.get("mae") or {}).get("status") == "PRESENT"),
            "explanation": review.get("explanation"),
            "control_readiness_counts": review.get("control_readiness_counts"),
            "qualified_control_edges": review.get("qualified_control_edges"),
            "earliest_retained_feature_session": earliest or review.get("earliest_retained_feature_session"),
            "feedback_rows_with_setup_warnings": warning_rows,
            "feedback_rows_with_supportive_flag": supportive_rows,
            "review_identity": review.get("review_identity"),
        },
        "focus": reports,
        "focus_packet_identities": {ticker: packet["packet_identity"] for ticker, packet in packets.items()},
        "focus_limitations": {ticker: packet["sections"]["history"]["spine"]["retention_limitation"] for ticker, packet in packets.items()},
        "peak_traced_bytes": peak,
        "cli": "AVAILABLE_READ_ONLY_EXPLICIT_SOURCES",
        "persisted": False,
    }
