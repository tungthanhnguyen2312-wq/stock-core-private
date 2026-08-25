"""Deterministic, source-bound current research risk register.

This is a descriptive projection of existing retained context contracts.  It deliberately
preserves independent risk and data-authority dimensions and never aggregates them into a
score, probability, recommendation, or sizing input.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Mapping

import current_official_market_universe as official_universe_module
from current_corporate_event_context import content_identity as event_content_identity
from current_financial_momentum_context import content_identity as financial_content_identity
from current_market_sector_leadership_context import content_identity as leadership_content_identity
from market_wide_current_valuation_input_scaleout import content_identity as valuation_content_identity
from market_wide_historical_research_context import content_identity as historical_content_identity


CONTRACT_VERSION = "current_research_risk_register/v1"
ARTIFACT_TYPE = "CURRENT_RESEARCH_RISK_REGISTER"
FORBIDDEN_USES = (
    "numeric_risk_score", "risk_adjusted_return", "expected_loss", "VaR", "probability",
    "position_size", "participation_cap", "recommendation", "strategy_eligibility",
    "research_priority", "entry_action", "VALUE", "daily_decision_queue",
)
OFFICIAL_CURRENT_STATUSES = frozenset({
    official_universe_module.OFFICIAL_CURRENT_EXCHANGE_SECURITY,
    official_universe_module.OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE,
})


class CurrentResearchRiskRegisterError(ValueError):
    """A source context was not the exact retained contract required by this register."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_research_risk_register:{digest}"}


def _verify_identity(artifact: Mapping[str, Any], *, contract: str, identity, label: str) -> None:
    if artifact.get("contract_version") != contract:
        raise CurrentResearchRiskRegisterError(f"{label}_CONTRACT_UNSUPPORTED")
    if artifact.get("artifact_sha256") != identity(artifact).get("artifact_sha256"):
        raise CurrentResearchRiskRegisterError(f"{label}_IDENTITY_MISMATCH")


def _official_tickers(artifact: Mapping[str, Any]) -> list[str]:
    try:
        official_universe_module._verify(artifact, "CURRENT_OFFICIAL_MARKET_UNIVERSE")
    except Exception as exc:
        raise CurrentResearchRiskRegisterError("OFFICIAL_UNIVERSE_IDENTITY_MISMATCH") from exc
    records = artifact.get("records")
    if not isinstance(records, Mapping):
        raise CurrentResearchRiskRegisterError("OFFICIAL_UNIVERSE_RECORDS_INVALID")
    tickers = sorted(ticker for ticker, row in records.items() if isinstance(row, Mapping)
                     and row.get("stocklookup_candidate") is True
                     and row.get("current_universe_status") in OFFICIAL_CURRENT_STATUSES)
    if not tickers or artifact.get("reconciliation", {}).get("official_total_match") != len(tickers):
        raise CurrentResearchRiskRegisterError("OFFICIAL_UNIVERSE_DENOMINATOR_MISMATCH")
    return tickers


def _item(*, ticker: str, domain: str, risk_type: str, severity: str | None, source: str,
          as_of: Any, facts: Mapping[str, Any], reasons: list[str], authority_tier: str,
          status: str = "ESTABLISHED") -> dict[str, Any]:
    return {
        "risk_id": f"{ticker}:{domain}:{risk_type}", "risk_domain": domain,
        "risk_type": risk_type, "status": status, "severity_band": severity,
        "source_context": source, "source_as_of": as_of, "observed_facts": copy.deepcopy(dict(facts)),
        "reason_codes": list(reasons), "authority_tier": authority_tier,
        "allowed_uses": ["CURRENT_RESEARCH_CONTEXT"], "prohibited_uses": list(FORBIDDEN_USES),
    }


def _technical_items(ticker: str, row: Mapping[str, Any], source_identity: str, session: Any) -> tuple[list, list]:
    material, watch, limitations = [], [], []
    status = row.get("context_status")
    if status not in {"AVAILABLE", "PARTIAL"} or row.get("is_current_session") is not True:
        limitations.append(_item(ticker=ticker, domain="DATA_AUTHORITY", risk_type="EXACT_SESSION_TECHNICAL_CONTEXT_UNAVAILABLE",
            severity="DATA_LIMITATION", source=source_identity, as_of=row.get("as_of_session") or session,
            facts={"context_status": status, "is_current_session": row.get("is_current_session")},
            reasons=["NO_CURRENT_EXACT_SESSION_HISTORICAL_TECHNICAL_CONTEXT"], authority_tier="DESCRIPTIVE_RESEARCH_ONLY", status="DATA_LIMITATION"))
        return material, watch, limitations
    structural = row.get("structural_state") or {}
    if structural.get("value") == "DETERIORATION":
        material.append(_item(ticker=ticker, domain="PRICE_TECHNICAL", risk_type="STRUCTURAL_DETERIORATION",
            severity="MATERIAL", source=source_identity, as_of=row.get("as_of_session") or session,
            facts={"structural_state": structural.get("value"), "primitives": structural.get("primitives")},
            reasons=["HISTORICAL_STRUCTURAL_STATE_DETERIORATION"], authority_tier="RETROSPECTIVE_DESCRIPTIVE"))
    volatility = row.get("volatility_regime") or {}
    if volatility.get("regime") == "HIGH":
        watch.append(_item(ticker=ticker, domain="PRICE_TECHNICAL", risk_type="ELEVATED_HISTORICAL_VOLATILITY_REGIME",
            severity="WATCH", source=source_identity, as_of=row.get("as_of_session") or session,
            facts={"volatility_regime": volatility.get("regime"), "volatility_20d": volatility.get("current_volatility_20d")},
            reasons=["WITHIN_TICKER_VOLATILITY_REGIME_HIGH"], authority_tier="RETROSPECTIVE_DESCRIPTIVE", status="WATCH"))
    momentum = row.get("momentum") or {}
    if momentum.get("sign") == "NEGATIVE":
        watch.append(_item(ticker=ticker, domain="PRICE_TECHNICAL", risk_type="NEGATIVE_CURRENT_MOMENTUM",
            severity="WATCH", source=source_identity, as_of=row.get("as_of_session") or session,
            facts={"momentum_20d": momentum.get("momentum_20d"), "sign": momentum.get("sign")},
            reasons=["HISTORICAL_CONTEXT_MOMENTUM_NEGATIVE"], authority_tier="RETROSPECTIVE_DESCRIPTIVE", status="WATCH"))
    return material, watch, limitations


def _leadership_items(ticker: str, row: Mapping[str, Any], market: Mapping[str, Any], source_identity: str, session: Any) -> tuple[list, list]:
    watch, limitations = [], []
    market_state = market.get("current_breadth_state")
    if market_state in {"MIXED_BREADTH", "DETERIORATING_BREADTH", "NARROW_LEADERSHIP", "DATA_LIMITED"}:
        target = limitations if market_state == "DATA_LIMITED" else watch
        target.append(_item(ticker=ticker, domain="MARKET_BREADTH", risk_type="MARKET_BREADTH_CONTEXT",
            severity="DATA_LIMITATION" if market_state == "DATA_LIMITED" else "WATCH", source=source_identity,
            as_of=session, facts={"market_breadth_state": market_state, "coverage_ratio": market.get("breadth_coverage_ratio")},
            reasons=[f"MARKET_BREADTH_{market_state}"], authority_tier="CURRENT_SESSION_DESCRIPTIVE",
            status="DATA_LIMITATION" if market_state == "DATA_LIMITED" else "WATCH"))
    sector = row.get("sector_leadership_context") or {}
    state = sector.get("leadership_state")
    if state in {"WEAKENING", "LAGGING"}:
        watch.append(_item(ticker=ticker, domain="SECTOR_RELATIVE", risk_type="SECTOR_HEADWIND", severity="WATCH",
            source=source_identity, as_of=session, facts={"leadership_state": state, "group_key": sector.get("group_key")},
            reasons=[f"SECTOR_{state}"], authority_tier="CURRENT_SESSION_DESCRIPTIVE", status="WATCH"))
    relative = row.get("sector_relative_momentum") or {}
    if relative.get("momentum_bucket") == "LOWER_QUARTILE":
        watch.append(_item(ticker=ticker, domain="SECTOR_RELATIVE", risk_type="WEAK_RELATIVE_TO_SECTOR", severity="WATCH",
            source=source_identity, as_of=session, facts={"momentum_percentile": relative.get("momentum_percentile_descriptive"), "bucket": relative.get("momentum_bucket")},
            reasons=["SECTOR_RELATIVE_MOMENTUM_LOWER_QUARTILE"], authority_tier="CURRENT_SESSION_DESCRIPTIVE", status="WATCH"))
    if sector.get("status") != "AVAILABLE":
        limitations.append(_item(ticker=ticker, domain="DATA_AUTHORITY", risk_type="SECTOR_CONTEXT_UNAVAILABLE", severity="DATA_LIMITATION",
            source=source_identity, as_of=session, facts={"sector_status": sector.get("status"), "reason": sector.get("reason")},
            reasons=[sector.get("reason") or "SECTOR_COVERAGE_DATA_LIMITED"], authority_tier="CURRENT_SESSION_DESCRIPTIVE", status="DATA_LIMITATION"))
    return watch, limitations


def _financial_items(ticker: str, row: Mapping[str, Any], source_identity: str, session: Any) -> tuple[list, list, list]:
    material, watch, limitations = [], [], []
    state = row.get("financial_momentum_state")
    facts = {"financial_momentum_state": state, "state_rule": row.get("state_rule"), "coverage_status": row.get("coverage_status"), "weakening_dimensions": row.get("weakening_dimensions")}
    if state == "LOSS_MAKING_OR_STRESSED":
        material.append(_item(ticker=ticker, domain="FINANCIAL", risk_type="FINANCIAL_STRESS", severity="MATERIAL", source=source_identity,
            as_of=row.get("as_of_financial_period"), facts=facts, reasons=[str(row.get("state_rule"))], authority_tier=str(row.get("evidence_tier"))))
    elif state == "DETERIORATING":
        material.append(_item(ticker=ticker, domain="FINANCIAL", risk_type="FINANCIAL_DETERIORATION", severity="MATERIAL", source=source_identity,
            as_of=row.get("as_of_financial_period"), facts=facts, reasons=[str(row.get("state_rule"))], authority_tier=str(row.get("evidence_tier"))))
    elif state == "MIXED":
        watch.append(_item(ticker=ticker, domain="FINANCIAL", risk_type="MIXED_FINANCIAL_EVIDENCE", severity="WATCH", source=source_identity,
            as_of=row.get("as_of_financial_period"), facts=facts, reasons=[str(row.get("state_rule"))], authority_tier=str(row.get("evidence_tier")), status="WATCH"))
    if row.get("coverage_status") == "INSUFFICIENT" or row.get("evidence_tier") in {"PROVIDER_RESEARCH", "UNAVAILABLE", "BLOCKED"}:
        limitations.append(_item(ticker=ticker, domain="DATA_AUTHORITY", risk_type="FINANCIAL_COMPARABILITY_OR_AUTHORITY_LIMITATION", severity="DATA_LIMITATION",
            source=source_identity, as_of=row.get("as_of_financial_period") or session,
            facts={"coverage_status": row.get("coverage_status"), "evidence_tier": row.get("evidence_tier"), "blockers": row.get("blockers")},
            reasons=list(row.get("blockers") or ["FINANCIAL_CONTEXT_LIMITED"]), authority_tier=str(row.get("evidence_tier")), status="DATA_LIMITATION"))
    return material, watch, limitations


def _event_items(ticker: str, row: Mapping[str, Any], source_identity: str, session: Any) -> tuple[list, list, list]:
    watch, limitations, conflicts = [], [], []
    if row.get("planned_unresolved_count", 0):
        watch.append(_item(ticker=ticker, domain="CORPORATE_EVENT", risk_type="PLANNED_NOT_EXECUTED_EVENT", severity="WATCH", source=source_identity,
            as_of=row.get("research_session") or session, facts={"planned_unresolved_count": row.get("planned_unresolved_count")},
            reasons=["PLANNED_NOT_EXECUTED_PRESERVED"], authority_tier="OFFICIAL_QUALIFIED", status="WATCH"))
    if row.get("temporal_incomplete_count", 0) or row.get("data_limited_count", 0):
        limitations.append(_item(ticker=ticker, domain="DATA_AUTHORITY", risk_type="EVENT_TEMPORAL_OR_EXECUTION_LIMITATION", severity="DATA_LIMITATION", source=source_identity,
            as_of=row.get("research_session") or session, facts={"temporal_incomplete_count": row.get("temporal_incomplete_count"), "data_limited_count": row.get("data_limited_count")},
            reasons=["EVENT_TEMPORAL_OR_EXECUTION_DETAILS_INCOMPLETE"], authority_tier="OFFICIAL_SOURCE_TEMPORALLY_LIMITED", status="DATA_LIMITATION"))
    if row.get("conflicting_count", 0):
        conflicts.append(_item(ticker=ticker, domain="CORPORATE_EVENT", risk_type="EVENT_EVIDENCE_CONFLICT", severity=None, source=source_identity,
            as_of=row.get("research_session") or session, facts={"conflicting_count": row.get("conflicting_count")},
            reasons=["CONFLICTING_EVIDENCE"], authority_tier="CONFLICTING_EVIDENCE", status="UNRESOLVED_CONFLICT"))
    return watch, limitations, conflicts


def _valuation_items(ticker: str, row: Mapping[str, Any], source_identity: str, session: Any) -> list:
    metrics = row.get("metrics") or {}
    statuses = Counter(metric.get("status") for metric in metrics.values() if isinstance(metric, Mapping))
    share = row.get("share_basis_input") or {}
    items = []
    if statuses.get("RESEARCH_USABLE", 0):
        items.append(_item(ticker=ticker, domain="VALUATION_AUTHORITY", risk_type="RESEARCH_USABLE_VALUATION_NOT_AUTHORITATIVE", severity="DATA_LIMITATION", source=source_identity,
            as_of=row.get("price_input", {}).get("session") or session, facts={"metric_status_counts": dict(statuses)},
            reasons=["RESEARCH_USABLE_IS_NOT_READY_OR_VALUE_AUTHORITY"], authority_tier="RESEARCH_USABLE", status="DATA_LIMITATION"))
    if statuses.get("BLOCKED", 0):
        items.append(_item(ticker=ticker, domain="VALUATION_AUTHORITY", risk_type="VALUATION_METRICS_BLOCKED", severity="DATA_LIMITATION", source=source_identity,
            as_of=row.get("price_input", {}).get("session") or session, facts={"metric_status_counts": dict(statuses)},
            reasons=["PER_METRIC_BLOCKED_STATUS_PRESERVED"], authority_tier="CURRENT_VALUATION_RESEARCH", status="DATA_LIMITATION"))
    if share.get("authoritative_current_market_cap_eligible") is not True:
        items.append(_item(ticker=ticker, domain="VALUATION_AUTHORITY", risk_type="CURRENT_SHARE_AUTHORITY_UNAVAILABLE", severity="DATA_LIMITATION", source=source_identity,
            as_of=share.get("observation_date") or session, facts={"share_status": share.get("status"), "freshness": share.get("freshness"), "blocked_reasons": share.get("blocked_reasons")},
            reasons=list(share.get("blocked_reasons") or ["AUTHORITATIVE_CURRENT_SHARE_BASIS_UNAVAILABLE"]), authority_tier=str(share.get("authority")), status="DATA_LIMITATION"))
    return items


def build_artifact(*, current_official_universe: Mapping[str, Any], historical_context: Mapping[str, Any],
                   leadership_context: Mapping[str, Any], financial_context: Mapping[str, Any],
                   corporate_event_context: Mapping[str, Any], valuation_context: Mapping[str, Any]) -> dict[str, Any]:
    tickers = _official_tickers(current_official_universe)
    _verify_identity(historical_context, contract="market_wide_historical_research_context/v1", identity=historical_content_identity, label="HISTORICAL_CONTEXT")
    _verify_identity(leadership_context, contract="current_market_sector_leadership_context/v1", identity=leadership_content_identity, label="LEADERSHIP_CONTEXT")
    _verify_identity(financial_context, contract="current_financial_momentum_context/v1", identity=financial_content_identity, label="FINANCIAL_CONTEXT")
    _verify_identity(corporate_event_context, contract="current_corporate_event_context/v1", identity=event_content_identity, label="EVENT_CONTEXT")
    _verify_identity(valuation_context, contract="market_wide_current_valuation/v1", identity=valuation_content_identity, label="VALUATION_CONTEXT")
    sources = {
        "historical": (historical_context.get("records"), historical_context.get("artifact_identity"), historical_context.get("session")),
        "leadership": (leadership_context.get("ticker_contexts"), leadership_context.get("artifact_identity"), leadership_context.get("session")),
        "financial": (financial_context.get("records"), financial_context.get("artifact_identity"), financial_context.get("session")),
        "event": (corporate_event_context.get("records"), corporate_event_context.get("artifact_identity"), corporate_event_context.get("research_session")),
        "valuation": (valuation_context.get("records"), valuation_context.get("artifact_identity"), valuation_context.get("valuation_session")),
    }
    if any(not isinstance(rows, Mapping) for rows, _, _ in sources.values()):
        raise CurrentResearchRiskRegisterError("SOURCE_RECORDS_INVALID")
    if any(ticker not in rows for name, (rows, _, _) in sources.items() if name != "historical" for ticker in tickers):
        raise CurrentResearchRiskRegisterError("OFFICIAL_TICKER_MISSING_FROM_REQUIRED_SOURCE")
    records = {}
    for ticker in tickers:
        material, watch, limitations, conflicts = [], [], [], []
        hrows, hid, hs = sources["historical"]; m, w, l = _technical_items(ticker, hrows.get(ticker, {}), hid, hs); material += m; watch += w; limitations += l
        lrows, lid, ls = sources["leadership"]; w, l = _leadership_items(ticker, lrows[ticker], leadership_context.get("market") or {}, lid, ls); watch += w; limitations += l
        frows, fid, fs = sources["financial"]; m, w, l = _financial_items(ticker, frows[ticker], fid, fs); material += m; watch += w; limitations += l
        erows, eid, es = sources["event"]; w, l, c = _event_items(ticker, erows[ticker], eid, es); watch += w; limitations += l; conflicts += c
        vrows, vid, vs = sources["valuation"]; limitations += _valuation_items(ticker, vrows[ticker], vid, vs)
        records[ticker] = {"ticker": ticker, "material_risks": material, "watch_risks": watch,
            "data_authority_limitations": limitations, "unresolved_conflicts": conflicts,
            "risk_register_status": "MATERIAL_RISKS_ESTABLISHED" if material else "NO_MATERIAL_RISK_ESTABLISHED_FROM_AVAILABLE_EVIDENCE"}
    all_items = [item for row in records.values() for key in ("material_risks", "watch_risks", "data_authority_limitations", "unresolved_conflicts") for item in row[key]]
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "research_mode": "CURRENT_RESEARCH_RISK_CONTEXT_ONLY", "official_universe_denominator": len(tickers), "records": records,
        "source_contexts": {name: {"artifact_identity": identity, "as_of": session, "available": True} for name, (_, identity, session) in sources.items()},
        "coverage": {"official_universe_denominator": len(tickers), "ticker_coverage": len(records), "confirmed_risk_count": sum(len(r["material_risks"]) for r in records.values()), "watch_count": sum(len(r["watch_risks"]) for r in records.values()), "data_authority_limitation_count": sum(len(r["data_authority_limitations"]) for r in records.values()), "conflict_count": sum(len(r["unresolved_conflicts"]) for r in records.values()), "tickers_with_no_material_risk_established": sum(not r["material_risks"] for r in records.values()), "count_by_risk_domain": dict(sorted(Counter(i["risk_domain"] for i in all_items).items())), "count_by_risk_type": dict(sorted(Counter(i["risk_type"] for i in all_items).items()))},
        "blocked_outputs": {name: "NOT_EMITTED_OR_MODIFIED" for name in FORBIDDEN_USES},
        "authority_boundary": {"is_actionable": False, "no_numeric_risk_score": True, "absence_is_not_low_risk": True, "data_limitation_is_not_economic_risk": True, "source_sessions_preserved_independently": True, "no_upstream_decision_mutation": True, "no_sizing_or_participation": True, "raw_as_traded": "NOT_PROMOTED", "pit": "BLOCKED"}}
    artifact.update(content_identity(artifact))
    return artifact


def replay(artifact: Mapping[str, Any]) -> None:
    if artifact.get("contract_version") != CONTRACT_VERSION or artifact.get("artifact_sha256") != content_identity(artifact).get("artifact_sha256"):
        raise CurrentResearchRiskRegisterError("RISK_REGISTER_IDENTITY_MISMATCH")
    if artifact.get("official_universe_denominator") != len(artifact.get("records") or {}):
        raise CurrentResearchRiskRegisterError("RISK_REGISTER_DENOMINATOR_MISMATCH")
