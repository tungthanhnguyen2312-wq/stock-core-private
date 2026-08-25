"""Shadow/opt-in analyst-product projection of current_research_decision_packet/v1.

This is a publication/display boundary over the existing daily decision research
product and opt-in export attach. It organizes packet facts already packaged by
the canonical packet. It does not redesign the packet, invent a sibling research
context, or promote packet authority.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from typing import Any, Mapping

from current_research_decision_packet import (
    CONTRACT_VERSION as PACKET_CONTRACT,
    content_identity as packet_content_identity,
    replay as replay_packet,
)

CONTRACT_VERSION = "current_research_decision_packet_product/v1"
SHADOW_MODE = "SHADOW_OPT_IN"
FORBIDDEN = (
    "recommendation", "probability", "expected_return", "target_price",
    "position_size", "sizing", "BUY", "SELL", "HOLD",
)

SCENARIO_LENS = {
    "id": "EVIDENCE_BOUND_BEAR_BASE_BULL",
    "label": "Evidence-bound Bear/Base/Bull family",
    "axes": ["BEAR", "BASE", "BULL"],
    "not_the_conservative_base_speculative_framework": True,
    "scenario_axis_is_not_probability": True,
}
CONSERVATIVE_BASE_SPECULATIVE_LENS = {
    "id": "CONSERVATIVE_BASE_SPECULATIVE",
    "label": "CONSERVATIVE/BASE/SPECULATIVE research scenario framework",
    "axes": ["CONSERVATIVE", "BASE", "SPECULATIVE"],
    "distinct_from_evidence_bound_bear_base_bull": True,
    "scenario_axis_is_not_probability": True,
}
PRIORITY_LENS = {
    "contract": "current_opportunity_prioritization/v1",
    "field": "priority_tier",
    "distinct_from_daily_opportunity_decision_queue": True,
    "research_priority_is_not_entry_action": True,
}

AUTHORITY_PRESENTATION = (
    "NO_MATERIAL_RISK_ESTABLISHED_IS_NOT_LOW_RISK",
    "VALUATION_RESEARCH_USABLE_IS_NOT_AUTHORITATIVE_READY",
    "ADJUSTED_RETROSPECTIVE_IS_NOT_RAW_AS_TRADED",
    "RETROSPECTIVE_HISTORY_IS_NOT_PIT",
    "RECORD_DATE_IS_NOT_EX_DATE",
    "PLANNED_OR_APPROVED_IS_NOT_EXECUTED",
    "SCENARIO_AXIS_IS_NOT_PROBABILITY",
    "RESEARCH_PRIORITY_IS_NOT_ENTRY_ACTION",
    "RESEARCH_STATE_IS_NOT_SIZING_AUTHORITY",
)

COMPONENT_KEYS = {
    "scenario": "scenario_context",
    "risk_register": "risk_register",
    "market_sector": "market_sector_context",
    "financial_momentum": "financial_momentum_context",
    "corporate_event": "corporate_event_context",
    "valuation": "valuation_context",
    "historical": "historical_research_context",
}


def verified_packet(artifact: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Fail closed on missing or incorrect packet identity. Never raises to callers."""
    if not isinstance(artifact, Mapping):
        return None
    try:
        if artifact.get("contract_version") != PACKET_CONTRACT:
            return None
        if artifact.get("artifact_sha256") != packet_content_identity(artifact).get("artifact_sha256"):
            return None
        replay_packet(artifact)
        if not isinstance(artifact.get("records"), Mapping):
            return None
        return dict(artifact)
    except Exception:
        return None


def load_verified_packet(path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8") if hasattr(path, "read_text") else open(path, encoding="utf-8").read())
    except Exception:
        return None
    return verified_packet(payload)


def _component_status(record: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    unresolved = set(record.get("unresolved_components") or [])
    components = record.get("components") or {}
    rows = {}
    for name, payload_key in COMPONENT_KEYS.items():
        row = dict(manifest.get(name) or {})
        present = payload_key in components
        rows[name] = {
            "component_name": name,
            "manifest_status": row.get("status", "ABSENT"),
            "present_on_ticker": present,
            "source_artifact_identity": row.get("source_artifact_identity"),
            "source_as_of": row.get("source_as_of"),
            "authority_use_status": row.get("authority_use_status"),
            "unresolved_on_ticker": name in unresolved,
        }
    return rows


def _cpy(value: Any, enabled: bool) -> Any:
    return copy.deepcopy(value) if enabled else value


def _risk_view(payload: Mapping[str, Any] | None, copy_payload: bool = True) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"status": "ABSENT_OR_UNRESOLVED", "no_material_risk_established_is_not_low_risk": True, "payload": None}
    status = payload.get("risk_register_status")
    return {
        "status": "PRESENT",
        "risk_register_status": status,
        "no_material_risk_established_is_not_low_risk": True,
        "absence_is_not_low_risk": status != "MATERIAL_RISKS_ESTABLISHED",
        "material_risks": _cpy(payload.get("material_risks") or [], copy_payload),
        "watch_risks": _cpy(payload.get("watch_risks") or [], copy_payload),
        "data_authority_limitations": _cpy(payload.get("data_authority_limitations") or [], copy_payload),
        "unresolved_conflicts": _cpy(payload.get("unresolved_conflicts") or [], copy_payload),
        "payload": _cpy(payload, copy_payload),
    }


def _valuation_view(payload: Mapping[str, Any] | None, copy_payload: bool = True) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"status": "ABSENT_OR_UNRESOLVED", "research_usable_is_not_authoritative_ready": True, "payload": None}
    metrics = payload.get("metrics") or {}
    metric_statuses = {name: (value.get("status") if isinstance(value, Mapping) else None) for name, value in metrics.items()}
    return {
        "status": "PRESENT",
        "valuation_session": payload.get("valuation_session"),
        "share_basis_status": payload.get("share_basis_status"),
        "metric_statuses": metric_statuses,
        "research_usable_metrics": sorted(name for name, status in metric_statuses.items() if status == "RESEARCH_USABLE"),
        "blocked_metrics": sorted(name for name, status in metric_statuses.items() if status == "BLOCKED"),
        "authoritative_ready_metrics": sorted(name for name, status in metric_statuses.items() if status == "READY"),
        "research_usable_is_not_authoritative_ready": True,
        "value_strategy": _cpy(payload.get("value_strategy"), copy_payload),
        "payload": _cpy(payload, copy_payload),
    }


def _event_view(payload: Mapping[str, Any] | None, copy_payload: bool = True) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "status": "ABSENT_OR_UNRESOLVED",
            "record_date_is_not_ex_date": True,
            "planned_or_approved_is_not_executed": True,
            "payload": None,
        }
    events = []
    for event in payload.get("events") or []:
        if not isinstance(event, Mapping):
            continue
        events.append({
            "event_id": event.get("event_id"),
            "event_status": event.get("event_status"),
            "event_type": event.get("event_type"),
            "known_at": event.get("known_at"),
            "published_at": event.get("published_at"),
            "record_date": event.get("record_date"),
            "ex_date": event.get("ex_date"),
            "effective_date": event.get("effective_date"),
            "execution_date": event.get("execution_date"),
            "temporal_completeness": event.get("temporal_completeness"),
            "evidence_tier": event.get("evidence_tier"),
            "record_date_is_not_ex_date": event.get("record_date") != event.get("ex_date") if event.get("record_date") or event.get("ex_date") else True,
            "planned_or_approved_is_not_executed": event.get("event_status") != "EXECUTED",
        })
    return {
        "status": "PRESENT",
        "qualified_event_count": payload.get("qualified_event_count"),
        "planned_unresolved_count": payload.get("planned_unresolved_count"),
        "temporal_incomplete_count": payload.get("temporal_incomplete_count"),
        "data_limited_count": payload.get("data_limited_count"),
        "conflicting_count": payload.get("conflicting_count"),
        "research_session": payload.get("research_session"),
        "events": events,
        "record_date_is_not_ex_date": True,
        "planned_or_approved_is_not_executed": True,
        "payload": _cpy(payload, copy_payload),
    }


def _historical_view(payload: Mapping[str, Any] | None, copy_payload: bool = True) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "status": "ABSENT_OR_UNRESOLVED",
            "adjusted_retrospective_is_not_raw_as_traded": True,
            "retrospective_history_is_not_pit": True,
            "payload": None,
        }
    boundary = payload.get("authority_boundary") or {}
    return {
        "status": "PRESENT",
        "as_of_session": payload.get("as_of_session"),
        "context_status": payload.get("context_status"),
        "structural_state": copy.deepcopy(payload.get("structural_state")),
        "volatility_regime": copy.deepcopy(payload.get("volatility_regime")),
        "momentum": copy.deepcopy(payload.get("momentum")),
        "drawdown": copy.deepcopy(payload.get("drawdown")),
        "price_basis": boundary.get("price_basis"),
        "raw_as_traded": boundary.get("RAW_AS_TRADED"),
        "pit": boundary.get("PIT"),
        "adjusted_retrospective_is_not_raw_as_traded": True,
        "retrospective_history_is_not_pit": True,
        "payload": _cpy(payload, copy_payload),
    }


def _scenario_view(payload: Mapping[str, Any] | None, copy_payload: bool = True) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "status": "ABSENT_OR_UNRESOLVED",
            "research_lens": copy.deepcopy(SCENARIO_LENS),
            "payload": None,
        }
    return {
        "status": "PRESENT",
        "research_lens": copy.deepcopy(SCENARIO_LENS),
        "independent_from_conservative_base_speculative_framework": True,
        "scenario_disposition": payload.get("scenario_disposition"),
        "current_state": copy.deepcopy(payload.get("current_state")),
        "bear_case": copy.deepcopy(payload.get("bear_case")),
        "base_case": copy.deepcopy(payload.get("base_case")),
        "bull_case": copy.deepcopy(payload.get("bull_case")),
        "authority_limitations": _cpy(payload.get("authority_limitations") or [], copy_payload),
        "payload": _cpy(payload, copy_payload),
    }


def project_ticker(record: Mapping[str, Any], packet: Mapping[str, Any], *, copy_payload: bool = True) -> dict[str, Any] | None:
    """Organize one packet record for product display. Local absence stays local."""
    if not isinstance(record, Mapping) or not isinstance(record.get("ticker"), str):
        return None
    ticker = record["ticker"]
    components = record.get("components") if isinstance(record.get("components"), Mapping) else {}
    manifest = packet.get("component_manifest") if isinstance(packet.get("component_manifest"), Mapping) else {}
    decision = _cpy(record.get("current_decision_context") or {}, copy_payload)
    view = {
        "ticker": ticker,
        "shadow_mode": SHADOW_MODE,
        "is_actionable": False,
        "packet_status": record.get("packet_status"),
        "ticker_usable": True,
        "component_absence_does_not_make_ticker_unusable": True,
        "current_decision_context": decision,
        "priority_lens": copy.deepcopy(PRIORITY_LENS),
        "component_availability": _component_status(record, manifest),
        "scenario_research_context": _scenario_view(components.get("scenario_context"), copy_payload),
        "conservative_base_speculative_lens": copy.deepcopy(CONSERVATIVE_BASE_SPECULATIVE_LENS),
        "risk_register": _risk_view(components.get("risk_register"), copy_payload),
        "market_sector_context": {
            "status": "PRESENT" if "market_sector_context" in components else "ABSENT_OR_UNRESOLVED",
            "payload": _cpy(components.get("market_sector_context"), copy_payload),
        },
        "financial_momentum_context": {
            "status": "PRESENT" if "financial_momentum_context" in components else "ABSENT_OR_UNRESOLVED",
            "payload": _cpy(components.get("financial_momentum_context"), copy_payload),
        },
        "corporate_event_context": _event_view(components.get("corporate_event_context"), copy_payload),
        "valuation_context": _valuation_view(components.get("valuation_context"), copy_payload),
        "historical_research_context": _historical_view(components.get("historical_research_context"), copy_payload),
        "unresolved_components": list(record.get("unresolved_components") or []),
        "warnings": list(record.get("warnings") or []),
        "packet_authority_limitations": list(record.get("authority_limitations") or []),
        "authority_presentation": list(AUTHORITY_PRESENTATION),
        "provenance": {
            "packet_identity": packet.get("artifact_identity"),
            "packet_sha256": packet.get("artifact_sha256"),
            "source_artifact_identities": _cpy(packet.get("source_artifact_identities") or {}, copy_payload),
            "current_decision_source_input_identities": _cpy(decision.get("source_input_identities") or {}, copy_payload),
        },
        "allowed_uses": list(record.get("allowed_uses") or []),
        "prohibited_uses": list(record.get("prohibited_uses") or list(FORBIDDEN)),
    }
    return view


def _panel_from_verified(verified: Mapping[str, Any], tickers: list[str] | None = None) -> dict[str, Any]:
    selected = list(tickers) if tickers is not None else []
    cards = {}
    malformed = 0
    for ticker in selected:
        record = verified["records"].get(ticker)
        if not isinstance(record, Mapping):
            continue
        view = project_ticker(record, verified)
        if view is None:
            malformed += 1
            continue
        cards[ticker] = view
    return {
        "shadow_mode": SHADOW_MODE,
        "contract_version": CONTRACT_VERSION,
        "source_artifact_identity": verified.get("artifact_identity"),
        "source_contract_version": verified.get("contract_version"),
        "research_session": verified.get("research_session"),
        "component_manifest": copy.deepcopy(verified.get("component_manifest") or {}),
        "source_artifact_identities": copy.deepcopy(verified.get("source_artifact_identities") or {}),
        "coverage": copy.deepcopy(verified.get("coverage") or {}),
        "authority_boundary": copy.deepcopy(verified.get("authority_boundary") or {}),
        "blocked_outputs": copy.deepcopy(verified.get("blocked_outputs") or {}),
        "authority_presentation": list(AUTHORITY_PRESENTATION),
        "semantic_lenses": {
            "packet_scenario": copy.deepcopy(SCENARIO_LENS),
            "conservative_base_speculative": copy.deepcopy(CONSERVATIVE_BASE_SPECULATIVE_LENS),
            "packet_priority": copy.deepcopy(PRIORITY_LENS),
        },
        "cards": cards,
        "cards_requested": selected,
        "malformed_product_payload_count": malformed,
        "is_actionable": False,
    }


def project_shadow_panel(packet: Mapping[str, Any], tickers: list[str] | None = None) -> dict[str, Any] | None:
    """Product-level shadow panel. Optional ticker subset for card attach; empty means panel without cards."""
    verified = verified_packet(packet)
    if verified is None:
        return None
    return _panel_from_verified(verified, tickers)


def validate_market_wide(packet: Mapping[str, Any]) -> dict[str, Any] | None:
    """Render/validate every retained packet record without inventing values."""
    verified = verified_packet(packet)
    if verified is None:
        return None
    records = verified["records"]
    coverage = verified.get("coverage") or {}
    residual = int(coverage.get("universe_denominator") or 0) - len(records)
    malformed = 0
    partial_usable = 0
    complete = 0
    forbidden_hits = 0
    component_local_absence = Counter()
    technical_gap = 0
    blocked_valuation = 0
    material_risk = 0
    no_material_risk = 0
    financial_insufficient = 0
    planned_not_executed = 0
    adjusted_retrospective = 0
    for ticker, record in records.items():
        if not isinstance(record, Mapping) or record.get("ticker") != ticker:
            malformed += 1
            continue
        view = project_ticker(record, verified, copy_payload=False)
        if view is None or view.get("ticker") != ticker or view.get("is_actionable") is True:
            malformed += 1
            continue
        ctx = view.get("current_decision_context") or {}
        if view.get("is_actionable") is True or any(key in ctx for key in ("recommendation", "probability", "expected_return", "target_price", "position_size", "sizing")):
            forbidden_hits += 1
        if ctx.get("entry_action") in {"BUY", "SELL", "HOLD"}:
            forbidden_hits += 1
        if view["packet_status"] == "COMPLETE_FOR_AVAILABLE_COMPONENTS":
            complete += 1
        elif view["packet_status"] == "PARTIAL":
            if view["ticker_usable"] is True:
                partial_usable += 1
            else:
                malformed += 1
        else:
            malformed += 1
        for name in view["unresolved_components"]:
            component_local_absence[name] += 1
        risk = view["risk_register"]
        if any(
            item.get("risk_type") == "EXACT_SESSION_TECHNICAL_CONTEXT_UNAVAILABLE"
            for item in (risk.get("data_authority_limitations") or [])
            if isinstance(item, Mapping)
        ):
            technical_gap += 1
        if risk.get("risk_register_status") == "MATERIAL_RISKS_ESTABLISHED":
            material_risk += 1
        if risk.get("risk_register_status") == "NO_MATERIAL_RISK_ESTABLISHED_FROM_AVAILABLE_EVIDENCE":
            no_material_risk += 1
        if view["valuation_context"].get("blocked_metrics"):
            blocked_valuation += 1
        financial = (view["financial_momentum_context"].get("payload") or {}) if isinstance(view["financial_momentum_context"].get("payload"), Mapping) else {}
        if financial.get("coverage_status") in {"INSUFFICIENT", "INSUFFICIENT_COMPARABLE_DATA"} or financial.get("financial_momentum_state") in {"INSUFFICIENT", "INSUFFICIENT_COMPARABLE_DATA"}:
            financial_insufficient += 1
        events = view["corporate_event_context"].get("events") or []
        if any(event.get("event_status") == "PLANNED_NOT_EXECUTED" for event in events if isinstance(event, Mapping)):
            planned_not_executed += 1
        hist = view["historical_research_context"]
        if hist.get("price_basis") == "ADJUSTED_RETROSPECTIVE":
            adjusted_retrospective += 1
    return {
        "shadow_mode": SHADOW_MODE,
        "source_artifact_identity": verified.get("artifact_identity"),
        "universe_denominator": len(records),
        "coverage_universe_denominator": coverage.get("universe_denominator"),
        "unexplained_ticker_residual": residual,
        "malformed_product_payload_count": malformed,
        "complete_count": complete,
        "partial_packets_remain_usable": partial_usable,
        "forbidden_product_hits": forbidden_hits,
        "component_local_absence_counts": dict(component_local_absence),
        "technical_coverage_gap_count": technical_gap,
        "blocked_valuation_count": blocked_valuation,
        "material_risk_count": material_risk,
        "no_material_risk_established_count": no_material_risk,
        "financial_insufficient_count": financial_insufficient,
        "planned_not_executed_event_count": planned_not_executed,
        "adjusted_retrospective_count": adjusted_retrospective,
        "authority_presentation": list(AUTHORITY_PRESENTATION),
        "is_actionable": False,
        "passed": residual == 0 and malformed == 0 and forbidden_hits == 0 and len(records) == coverage.get("universe_denominator"),
    }


def attach_shadow_to_daily_product(artifact: dict[str, Any], packet: Mapping[str, Any] | None) -> dict[str, Any]:
    """Opt-in attach. Invalid/missing packet leaves the daily product unchanged."""
    verified = verified_packet(packet)
    if verified is None:
        return artifact
    cards = artifact.get("detailed_research_cards")
    tickers = list(cards) if isinstance(cards, Mapping) else []
    panel = _panel_from_verified(verified, tickers)
    artifact["current_research_decision_packet_shadow"] = {k: v for k, v in panel.items() if k != "cards"}
    artifact["source_artifact_identities"]["current_research_decision_packet"] = verified.get("artifact_identity")
    if isinstance(cards, dict):
        for ticker, card in cards.items():
            view = panel["cards"].get(ticker)
            if view is not None:
                card["current_research_decision_packet"] = view
    return artifact


def ticker_markdown(view: Mapping[str, Any]) -> list[str]:
    decision = view.get("current_decision_context") or {}
    scenario = view.get("scenario_research_context") or {}
    risk = view.get("risk_register") or {}
    valuation = view.get("valuation_context") or {}
    events = view.get("corporate_event_context") or {}
    historical = view.get("historical_research_context") or {}
    financial = ((view.get("financial_momentum_context") or {}).get("payload") or {}) if isinstance((view.get("financial_momentum_context") or {}).get("payload"), Mapping) else {}
    lines = [
        f"#### {view.get('ticker')}",
        f"- Packet status: {view.get('packet_status')}; ticker remains usable even if a component is unresolved.",
        f"- Decision context (passthrough): priority_tier={decision.get('priority_tier')} from current_opportunity_prioritization/v1 (not daily_opportunity_decision_queue; not an entry action); entry_action={decision.get('entry_action')} (research state, not sizing); eligible_strategies={decision.get('eligible_strategies')}.",
        f"- Scenario lens: {scenario.get('research_lens', {}).get('label')}; disposition={scenario.get('scenario_disposition')}. This is not CONSERVATIVE/BASE/SPECULATIVE and is not probability.",
        f"- Risk register: {risk.get('risk_register_status')}. NO_MATERIAL_RISK_ESTABLISHED is not LOW_RISK.",
        f"- Valuation: RESEARCH_USABLE={valuation.get('research_usable_metrics')}; BLOCKED={valuation.get('blocked_metrics')}; READY={valuation.get('authoritative_ready_metrics')}. RESEARCH_USABLE is not authoritative READY.",
        f"- Financial momentum: state={financial.get('financial_momentum_state')}; coverage={financial.get('coverage_status')}; evidence_tier={financial.get('evidence_tier')}.",
        f"- Corporate events: planned_unresolved={events.get('planned_unresolved_count')}; planned/approved is not executed; record date is not ex-date.",
        f"- Historical: context_status={historical.get('context_status')}; price_basis={historical.get('price_basis')}; RAW_AS_TRADED={historical.get('raw_as_traded')}; PIT={historical.get('pit')}. ADJUSTED_RETROSPECTIVE is not RAW_AS_TRADED; retrospective history is not PIT.",
        f"- Unresolved components: {view.get('unresolved_components') or []}.",
        f"- Provenance: {((view.get('provenance') or {}).get('packet_identity'))}.",
        "- Human review only; no recommendation, probability, target, or sizing.",
    ]
    return lines


def markdown(panel: Mapping[str, Any], *, include_cards: bool = True) -> str:
    lenses = panel.get("semantic_lenses") or {}
    coverage = panel.get("coverage") or {}
    lines = [
        "# Current research decision packet (shadow / opt-in)",
        "",
        "This section is explicit shadow/opt-in. It does not replace the default daily research product.",
        f"- Source: {panel.get('source_artifact_identity')}",
        f"- Session: {panel.get('research_session')}",
        f"- Universe: {coverage.get('universe_denominator')}; complete={coverage.get('valid_packet_count')}; partial={coverage.get('partial_count')}.",
        f"- Packet scenario lens: {(lenses.get('packet_scenario') or {}).get('label')}. Independent from CONSERVATIVE/BASE/SPECULATIVE.",
        f"- Packet priority_tier is {((lenses.get('packet_priority') or {}).get('contract'))} and is not an entry action.",
        "- Authority: NO_MATERIAL_RISK_ESTABLISHED is not LOW_RISK; RESEARCH_USABLE is not authoritative READY; ADJUSTED_RETROSPECTIVE is not RAW_AS_TRADED; retrospective history is not PIT; record date is not ex-date; planned/approved is not executed; scenario axis is not probability; research priority is not entry action; research state is not sizing authority.",
        "",
    ]
    if include_cards:
        lines.append("## Packet cards")
        for ticker in panel.get("cards_requested") or sorted((panel.get("cards") or {})):
            view = (panel.get("cards") or {}).get(ticker)
            if not view:
                continue
            lines.extend(ticker_markdown(view))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
