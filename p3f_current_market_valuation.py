"""P3-F bounded current-market valuation research.

This module is deliberately a sibling of ``current_state_relative_valuation``.
It selects one retained DNSE CURRENT_MARKET session that is also covered by an
official current-share chain; it never converts the retained, retrospectively
adjusted OHLC history into RAW_AS_TRADED or a PIT valuation price.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping

import dnse_ohlc_price_basis_capability as price_basis
from dnse_current_state_price_analytics import build_current_state_price_analytics_from_evidence_store
from dnse_market_risk_evidence_store import read_stock_ohlc
from field_temporal_contract import stable_id
from current_state_relative_valuation import PRICE_UNIT, PRICE_UNIT_TO_VND, resolve_current_shares

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "p3f_current_market_valuation/v1"
ARTIFACT_TYPE = "P3F_CURRENT_MARKET_VALUATION_RESEARCH"
CURRENT_MARKET = "CURRENT_MARKET"
PIT_OBSERVED = "PIT_OBSERVED"
RAW_AS_TRADED = "RAW_AS_TRADED"
ADJUSTED_RETROSPECTIVE = "ADJUSTED_RETROSPECTIVE"
UNKNOWN = "UNKNOWN"
METHODS = ("P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA")


def _source_time(runtime_root: Path | str, ticker: str) -> str | None:
    record = read_stock_ohlc(runtime_root, ticker)
    provenance = (record or {}).get("provenance") or {}
    value = provenance.get("materialized_at")
    return value if isinstance(value, str) else None


def _market_price_at(ticker: str, runtime_root: Path | str, session: str) -> dict[str, Any]:
    """Return one exact retained DNSE close, or an explicit fail-closed reason."""
    eligibility = price_basis.current_state_eligibility(ticker)
    base: dict[str, Any] = {
        "ticker": ticker,
        "valuation_date": session,
        "status": "PRICE_BLOCKED",
        "reason_codes": [],
        "price_namespace": CURRENT_MARKET,
        "historical_pit_eligible": False,
        "raw_as_traded": RAW_AS_TRADED,
        "price_basis": None,
        "source": "DNSE",
        "field_identity": "close",
        "currency": "VND",
        "price_unit": PRICE_UNIT,
        "observed_value": None,
        "raw_close": None,
        "observed_at_session": None,
        "retrieved_at": _source_time(runtime_root, ticker),
        "provenance": None,
        "eligibility": eligibility,
    }
    if not eligibility.get("eligible_for_current_state_price_analytics"):
        base["reason_codes"] = ["PRICE_NAMESPACE_NOT_QUALIFIED_FOR_TICKER"]
        return base
    try:
        report = build_current_state_price_analytics_from_evidence_store(
            ticker, runtime_root=runtime_root, include_technical_indicators=False,
        )
    except Exception as exc:
        base["reason_codes"] = [f"RETAINED_CURRENT_PRICE_EVIDENCE_MALFORMED:{type(exc).__name__}"]
        return base
    if report.get("status") != "QUALIFIED_FOR_DNSE_CURRENT_STATE_PRICE_ANALYTICS":
        base["reason_codes"] = ["CURRENT_PRICE_ANALYTICS_NOT_QUALIFIED"]
        return base
    observation = next((row for row in report.get("observations", []) if row.get("session_date") == session), None)
    if observation is None:
        base["reason_codes"] = ["FROZEN_VALUATION_SESSION_NOT_RETAINED"]
        return base
    close = observation.get("close")
    if not isinstance(close, (int, float)) or isinstance(close, bool) or close <= 0:
        base["reason_codes"] = ["FROZEN_VALUATION_CLOSE_INVALID"]
        return base
    return {
        **base,
        "status": "PRICE_READY",
        "reason_codes": [],
        "price_basis": report.get("price_basis") or ADJUSTED_RETROSPECTIVE,
        "raw_as_traded": "NOT_PROMOTED",
        "observed_value": close * PRICE_UNIT_TO_VND,
        "raw_close": close,
        "observed_at_session": session,
        "provenance": report.get("provenance"),
        "warnings": list(report.get("warnings") or []),
    }


def _share_basis_at(ticker: str, runtime_root: Path | str, session: str) -> dict[str, Any]:
    result = resolve_current_shares(runtime_root, ticker, session)
    current = (result.get("bridge_result") or {}).get("current_shares") or {}
    if current.get("qualified"):
        return {
            "ticker": ticker, "valuation_date": session, "status": "SHARE_BASIS_READY",
            "reason_codes": [], "identity": "current_common_shares_outstanding",
            "value": current.get("value"), "effective_for_date": session,
            "coverage_through": result.get("coverage_through"), "source": "official_evidence",
            "transition": result,
        }
    reason = current.get("reason") or "current_share_basis_not_qualified"
    diagnostic = result.get("opening_identity_diagnostic") or {}
    return {
        "ticker": ticker, "valuation_date": session, "status": "SHARE_BASIS_BLOCKED",
        "reason_codes": [f"CURRENT_SHARE_BASIS_NOT_QUALIFIED:{reason}"] + (
            [f"OPENING_SHARE_EVIDENCE:{diagnostic.get('detail')}"] if diagnostic.get("detail") else []),
        "identity": None, "value": None, "effective_for_date": None,
        "coverage_through": result.get("coverage_through"), "source": "official_evidence",
        "transition": result,
    }


def _latest_common_session(ticker: str, runtime_root: Path | str) -> str | None:
    """Latest retained DNSE session with an explicitly qualified share chain.

    This is a CURRENT_MARKET session-selection rule, not a historical/PIT price
    reconstruction: it only considers the already-qualified DNSE current-state
    evidence window and keeps its adjusted-retrospective basis label intact.
    """
    try:
        report = build_current_state_price_analytics_from_evidence_store(
            ticker, runtime_root=runtime_root, include_technical_indicators=False,
        )
    except Exception:
        return None
    if report.get("status") != "QUALIFIED_FOR_DNSE_CURRENT_STATE_PRICE_ANALYTICS":
        return None
    for row in reversed(report.get("observations") or []):
        session = row.get("session_date")
        if isinstance(session, str) and _share_basis_at(ticker, runtime_root, session)["status"] == "SHARE_BASIS_READY":
            return session
    return None


def _latest_qualified_fact(issuer: Mapping[str, Any], metric: str) -> dict[str, Any] | None:
    facts = [fact for fact in issuer.get("facts", []) if fact.get("canonical_metric") == metric
             and fact.get("qualification_state") == "QUALIFIED" and fact.get("value") is not None]
    if not facts:
        return None
    return max(facts, key=lambda fact: (str(fact.get("reporting_period")), str(fact.get("observed_at"))))


def _lineage(fact: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if fact is None:
        return None
    return {key: fact.get(key) for key in (
        "canonical_metric", "value", "currency", "unit_scale", "reporting_period", "period_end",
        "period_type", "statement_scope", "temporal_nature", "source_lineage",
    )}


def _method(name: str, *, state: str, value: float | int | None = None,
            blockers: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "valuation_method": name, "status": state, "value": value,
        "formula_version": CONTRACT_VERSION, "is_actionable": False,
        "historical_pit_eligible": False, "blockers": blockers or [], **extra,
    }


def _financial_state(*facts: Mapping[str, Any] | None) -> list[str]:
    return [f"FINANCIAL_IDENTITY_MISSING:{name}" for name, fact in facts if fact is None]


def _evaluate_issuer(issuer: Mapping[str, Any], *, price: Mapping[str, Any], shares: Mapping[str, Any]) -> dict[str, Any]:
    identity = issuer.get("issuer_identity") or {}
    ticker, entity = str(identity.get("ticker")), str(identity.get("entity_type"))
    market_blockers = list(price.get("reason_codes") or []) + list(shares.get("reason_codes") or [])
    market_cap = None
    if not market_blockers:
        market_cap = price["observed_value"] * shares["value"]
    facts = {name: _latest_qualified_fact(issuer, name) for name in (
        "net_income", "shareholders_equity", "revenue", "cash_and_equivalents", "total_interest_bearing_debt",
        "ebitda", "net_profit_parent", "profit_after_tax_parent", "total_equity",
    )}
    methods: dict[str, dict[str, Any]] = {}
    if entity == "corporate":
        family_definitions = (("P/E", "net_income"), ("P/B", "shareholders_equity"), ("P/S", "revenue"))
        for name, fact_name in family_definitions:
            fact = facts[fact_name]
            missing = market_blockers + _financial_state((fact_name, fact))
            if missing:
                methods[name] = _method(name, state="VALUATION_BLOCKED", blockers=missing)
            elif fact["value"] <= 0:
                methods[name] = _method(name, state="INCOMPARABLE_NEGATIVE_OR_ZERO_DENOMINATOR", blockers=["POSITIVE_DENOMINATOR_REQUIRED"], financial_inputs=[_lineage(fact)])
            else:
                methods[name] = _method(name, state="VALUATION_READY", value=market_cap / fact["value"],
                    formula=f"market_cap / {fact_name}", financial_period=fact["reporting_period"],
                    financial_inputs=[_lineage(fact)])
        ev_facts = (facts["revenue"], facts["total_interest_bearing_debt"], facts["cash_and_equivalents"])
        ev_missing = market_blockers + _financial_state(("revenue", ev_facts[0]), ("total_interest_bearing_debt", ev_facts[1]), ("cash_and_equivalents", ev_facts[2]))
        if ev_missing:
            methods["EV/Sales"] = _method("EV/Sales", state="VALUATION_BLOCKED", blockers=ev_missing)
        else:
            ev = market_cap + ev_facts[1]["value"] - ev_facts[2]["value"]
            methods["EV/Sales"] = _method("EV/Sales", state="VALUATION_READY", value=ev / ev_facts[0]["value"],
                formula="(market_cap + total_interest_bearing_debt - cash_and_equivalents) / revenue",
                financial_period=ev_facts[0]["reporting_period"], financial_inputs=[_lineage(fact) for fact in ev_facts], enterprise_value=ev)
        methods["EV/EBITDA"] = _method("EV/EBITDA", state="VALUATION_BLOCKED",
            blockers=market_blockers + _financial_state(("ebitda", facts["ebitda"]), ("total_interest_bearing_debt", facts["total_interest_bearing_debt"]), ("cash_and_equivalents", facts["cash_and_equivalents"])))
    elif entity in {"bank", "securities"}:
        earnings = facts["net_profit_parent"] if entity == "bank" else facts["profit_after_tax_parent"]
        earnings_name = "net_profit_parent" if entity == "bank" else "profit_after_tax_parent"
        equity = facts["total_equity"]
        for name, fact_name, fact in (("P/E", earnings_name, earnings), ("P/B", "total_equity", equity)):
            missing = market_blockers + _financial_state((fact_name, fact))
            methods[name] = (_method(name, state="VALUATION_BLOCKED", blockers=missing) if missing else
                _method(name, state="VALUATION_READY", value=market_cap / fact["value"], formula=f"market_cap / {fact_name}", financial_period=fact["reporting_period"], financial_inputs=[_lineage(fact)]))
        for name in ("P/S", "EV/Sales", "EV/EBITDA"):
            methods[name] = _method(name, state="NOT_APPLICABLE", blockers=[f"{entity.upper()}_INDUSTRIAL_EV_OR_REVENUE_SEMANTICS_NOT_APPLICABLE"])
    else:
        methods = {name: _method(name, state="NOT_APPLICABLE", blockers=["ENTITY_CLASS_UNRESOLVED"]) for name in METHODS}
    for name in METHODS:
        methods.setdefault(name, _method(name, state="VALUATION_BLOCKED", blockers=["METHOD_NOT_MODELLED"]))
    financial_readiness = {}
    for name, method in methods.items():
        if method["status"] == "NOT_APPLICABLE":
            financial_readiness[name] = "NOT_APPLICABLE"
        elif any(str(blocker).startswith("FINANCIAL_IDENTITY_MISSING:") for blocker in method["blockers"]):
            financial_readiness[name] = "FINANCIAL_INPUT_PARTIAL"
        else:
            financial_readiness[name] = "FINANCIAL_INPUT_READY"
    return {
        "ticker": ticker, "entity_class": entity, "valuation_date": price["valuation_date"],
        "price_input": dict(price), "share_basis_input": dict(shares), "market_cap": market_cap,
        "financial_readiness_by_method": financial_readiness,
        "methods": methods, "is_actionable": False,
    }


def build_p3f_valuation_artifact(*, p3e_artifact: Mapping[str, Any], runtime_root: Path | str) -> dict[str, Any]:
    issuers = sorted(p3e_artifact["refreshed_panel_data"]["issuers"], key=lambda row: row["issuer_identity"]["ticker"])
    eligible_sessions = [_latest_common_session(str(row["issuer_identity"]["ticker"]), runtime_root) for row in issuers]
    sessions = sorted({session for session in eligible_sessions if session})
    if not sessions:
        valuation_date, freshness_state = None, "NO_COMMON_QUALIFIED_CURRENT_MARKET_SESSION"
    else:
        valuation_date, freshness_state = sessions[-1], "RETAINED_CURRENT_MARKET_SNAPSHOT_FROZEN"
    rows = []
    for issuer in issuers:
        ticker = str(issuer["issuer_identity"]["ticker"])
        session = valuation_date or "0001-01-01"
        price = _market_price_at(ticker, runtime_root, session) if valuation_date else {"ticker": ticker, "valuation_date": None, "status": "PRICE_BLOCKED", "reason_codes": [freshness_state]}
        shares = _share_basis_at(ticker, runtime_root, session) if valuation_date else {"ticker": ticker, "valuation_date": None, "status": "SHARE_BASIS_BLOCKED", "reason_codes": [freshness_state]}
        rows.append(_evaluate_issuer(issuer, price=price, shares=shares))
    counts = Counter(method["status"] for row in rows for method in row["methods"].values())
    metric_counts = {name: sum(row["methods"][name]["status"] == "VALUATION_READY" for row in rows) for name in METHODS}
    payload = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3F_VALUATION_RESEARCH_PARTIAL" if any(metric_counts.values()) else "P3F_VALUATION_RESEARCH_BLOCKED",
        "source_artifacts": {"p3e_fundamental_coverage_closeout": p3e_artifact.get("artifact_identity")},
        "frozen_valuation_session": {"valuation_date": valuation_date, "session_identity": valuation_date, "source": "DNSE", "freshness_state": freshness_state, "selection_policy": "latest_retained_DNSE_CURRENT_MARKET_session_with_explicit_official_current_share_coverage"},
        "temporal_boundary": {"allowed_price_namespace": CURRENT_MARKET, "retained_price_basis": ADJUSTED_RETROSPECTIVE, "raw_as_traded": "NOT_PROMOTED", "historical_valuation": "HISTORICAL_VALUATION_BLOCKED", "historical_pit_eligible": False, "price_semantic_states": {CURRENT_MARKET: "ALLOWED_FOR_THIS_FROZEN_SNAPSHOT_ONLY", PIT_OBSERVED: "NOT_AUTHORIZED_FOR_VALUATION", RAW_AS_TRADED: "NOT_PROMOTED", ADJUSTED_RETROSPECTIVE: "ALLOWED_ONLY_AS_CURRENT_MARKET_SOURCE_BASIS", UNKNOWN: "BLOCKED"}},
        "issuer_readiness": rows,
        "aggregate": {"metric_ready_counts": metric_counts, "method_status_counts": dict(sorted(counts.items())), "price_ready_issuers": sum(row["price_input"]["status"] == "PRICE_READY" for row in rows), "share_ready_issuers": sum(row["share_basis_input"]["status"] == "SHARE_BASIS_READY" for row in rows)},
        "sector_applicability": {"corporate": ["P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA_when_exact_EBITDA"], "bank": ["P/E", "P/B", "bank_profitability_book_context"], "securities": ["P/E", "P/B", "securities_profitability_book_context"]},
        "blocked_boundaries": {"p3a": "P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE", "historical": "HISTORICAL_VALUATION_BLOCKED", "dcf_fcff": "CAPEX_FCF_BLOCKED_MISSING_EXACT_IDENTITY", "recommendation": "NOT_IMPLEMENTED", "scenario": "BASELINE_FACTS_ONLY_NO_ASSUMPTIONS_OR_TARGET_PRICES"},
        "is_actionable": False,
    }
    payload["artifact_sha256"] = stable_id(payload)
    payload["artifact_identity"] = f"p3f_current_market_valuation:{payload['artifact_sha256']}"
    return payload


def serialize(artifact: Mapping[str, Any]) -> str:
    return json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def market_cap_from_authority_resolver(resolved_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """P3-F2 integration seam: consume qualified generic inputs without formulas.

    P3-F remains the owner of multiple calculations.  This small adapter only
    validates the authority resolver's market-cap readiness and carries its
    exact price/share lineage forward for a P3-F evaluation caller.
    """
    if resolved_inputs.get("market_cap_readiness") != "MARKET_CAP_READY":
        return {"status": "MARKET_CAP_BLOCKED", "value": None,
                "blockers": list(resolved_inputs.get("blocker_codes") or []),
                "is_actionable": False}
    return {"status": "MARKET_CAP_READY", "value": resolved_inputs.get("market_cap"),
            "price_input": resolved_inputs.get("price"), "share_basis_input": resolved_inputs.get("shares"),
            "is_actionable": False}
