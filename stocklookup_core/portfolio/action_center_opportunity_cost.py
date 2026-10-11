"""Optional private Action Center presentation over the existing opportunity-cost v2 engine.

No I/O or production resolver: the caller supplies an explicit bounded research frame,
the exact IID-consumed valuation artifact and an existing portfolio_state/v1 projection.
"""
from __future__ import annotations

import copy
from datetime import date
import math
from typing import Any, Mapping

from stocklookup_core.portfolio import portfolio_opportunity_cost_research as engine

CONTRACT_VERSION = "action_center_opportunity_cost_cases_consumer/v1"
INPUT_CONTRACT = "action_center_opportunity_cost_input/v1"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise engine.OpportunityCostResearchError(reason)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _research_evidence(value: Any) -> Any:
    """Keep source research detail without importing the separate intrinsic model surface."""
    if isinstance(value, Mapping):
        return {k: _research_evidence(v) for k, v in value.items() if k != "intrinsic_scenario_valuation"}
    if isinstance(value, (list, tuple)):
        return [_research_evidence(v) for v in value]
    return copy.deepcopy(value)


def _date(value: Any, reason: str) -> str:
    try:
        _require(isinstance(value, str) and date.fromisoformat(value).isoformat() == value, reason)
    except (TypeError, ValueError):
        raise engine.OpportunityCostResearchError(reason) from None
    return value


def _owner_state(raw: Any, session: str) -> tuple[dict | None, str]:
    if raw is None:
        return None, "PRIVATE_PORTFOLIO_NOT_SUPPLIED"
    _require(isinstance(raw, Mapping), "OWNER_STATE_INVALID")
    if raw.get("contract_version") != engine.PORTFOLIO_STATE_CONTRACT:
        return None, "UNSUPPORTED_PORTFOLIO_STATE"
    if raw.get("status") != "AVAILABLE":
        return None, "PRIVATE_PORTFOLIO_UNAVAILABLE"
    state = copy.deepcopy(dict(raw))
    as_of = _date(state.get("as_of_date"), "OWNER_STATE_DATE_INVALID")
    _require(as_of <= session, "OWNER_STATE_FUTURE_INFORMATION")
    _require(isinstance(state.get("source_identities"), Mapping) and bool(state["source_identities"].get("portfolio_snapshot_identity")),
             "OWNER_SNAPSHOT_IDENTITY_MISSING")
    _require(isinstance(state.get("positions"), Mapping), "OWNER_POSITIONS_INVALID")
    for ticker, position in state["positions"].items():
        _require(isinstance(ticker, str) and ticker == ticker.upper() and isinstance(position, Mapping),
                 "OWNER_POSITION_INVALID")
        _require(position.get("ticker", ticker) == ticker, "OWNER_POSITION_TICKER_MISMATCH")
        _require(isinstance(position.get("is_active"), bool), "OWNER_POSITION_ACTIVE_FLAG_INVALID")
        # Invalid/unresolved quantities never become a holding or a synthetic flat row.
        quantity = position.get("current_quantity")
        _require(not (position.get("current_position_status") == "CLOSED" and _finite(quantity) and quantity > 0),
                 "OWNER_CLOSED_POSITION_QUANTITY_CONFLICT")
        if quantity is not None and (not _finite(quantity) or quantity < 0):
            position["current_quantity"] = None
            position["current_position_status"] = "UNRESOLVED"
        weight = position.get("current_weight")
        _require(weight is None or (_finite(weight) and weight >= 0), "OWNER_WEIGHT_INVALID")
    for key in ("effective_nav", "cash_available"):
        value = state.get(key)
        _require(value is None or (_finite(value) and value >= 0), "OWNER_" + key.upper() + "_INVALID")
    for key in ("sector_weights", "effective_policy"):
        values = state.get(key) or {}
        _require(isinstance(values, Mapping), "OWNER_" + key.upper() + "_INVALID")
        for value in values.values():
            _require(value is None or (_finite(value) and value >= 0), "OWNER_" + key.upper() + "_INVALID")
    return state, "AVAILABLE" if as_of == session else "STALE_OWNER_SNAPSHOT_RESEARCH_ONLY"


def _valuation(source: Any, iid: Mapping, session: str) -> Mapping | None:
    if source is None:
        return None
    from canonical_daily_financial_v2_materialization import _identity
    _require(isinstance(source, Mapping) and source.get("contract_version") == "current_research_valuation_context/v1",
             "VALUATION_CONTRACT_MISMATCH")
    expected = (iid.get("source_artifacts") or {}).get("current_valuation")
    _require(bool(expected) and source.get("artifact_identity") == expected, "VALUATION_IID_SOURCE_MISMATCH")
    try:
        identity = _identity(source)
    except (TypeError, ValueError):
        raise engine.OpportunityCostResearchError("VALUATION_CONTENT_INVALID") from None
    _require(all(source.get(k) == v for k, v in identity.items()), "VALUATION_CONTENT_IDENTITY_MISMATCH")
    _require(isinstance(source.get("records"), Mapping), "VALUATION_RECORDS_INVALID")
    # Canonical evaluated valuation has no session header. Its complete content identity
    # is bound by the verified same-session IID; do not invent a valuation observation date.
    for key in ("session", "valuation_session"):
        if source.get(key) is not None:
            _require(source[key] == session, "VALUATION_SESSION_MISMATCH")
    return source


def build_view(*, session: str, integrated_decision: Mapping[str, Any], request: Mapping[str, Any]) -> dict:
    """Compose, validate and present; never infer positions, thesis or method fitness."""
    from current_evidence_bound_scenario import bind_integrated_scenarios
    _date(session, "SESSION_INVALID")
    _require(isinstance(request, Mapping) and request.get("contract_version") == INPUT_CONTRACT, "OPPORTUNITY_INPUT_CONTRACT_MISMATCH")
    _require(request.get("session") == session, "OPPORTUNITY_INPUT_SESSION_MISMATCH")
    _require(set(request) <= {"contract_version", "session", "research_frames", "owner_portfolio_state", "valuation_artifact"},
             "UNSUPPORTED_OPPORTUNITY_INPUT_FIELD")
    frames = request.get("research_frames")
    _require(isinstance(frames, (list, tuple)) and bool(frames), "EXPLICIT_RESEARCH_FRAMES_REQUIRED")
    allowed = {"ticker", "horizon", "portfolio_role", "thesis_id", "thesis_ids", "thesis_status", "thesis_source",
               "current_returns", "current_return_dates"}
    for frame in frames:
        _require(isinstance(frame, Mapping) and set(frame) <= allowed, "UNSUPPORTED_RESEARCH_FRAME_FIELD")
        ticker = frame.get("ticker")
        _require(isinstance(ticker, str) and ticker.strip() == ticker and ticker == ticker.upper(), "FRAME_TICKER_INVALID")
        _require(frame.get("horizon") in engine.HORIZONS and frame.get("portfolio_role") in engine.PORTFOLIO_ROLES,
                 "EXPLICIT_RESEARCH_HORIZON_AND_ROLE_REQUIRED")
        _require(frame.get("thesis_status", "UNKNOWN") in engine.THESIS_STATUSES, "THESIS_STATUS_INVALID")
        _require(frame.get("thesis_status", "UNKNOWN") == "UNKNOWN" or bool(frame.get("thesis_source")), "THESIS_ASSERTION_SOURCE_REQUIRED")
        if frame.get("thesis_source") is not None:
            _require(isinstance(frame["thesis_source"], str) and bool(frame["thesis_source"].strip()), "THESIS_ASSERTION_SOURCE_INVALID")
        # Date alignment never permits later observations to enter an earlier comparison.
        for observed in frame.get("current_return_dates") or []:
            try:
                parsed = date.fromisoformat(observed)
            except (TypeError, ValueError):
                continue  # PR118 reports malformed date vectors as NOT_COMPARABLE.
            if parsed.isoformat() == observed:
                _require(observed <= session, "RETURN_DATE_FUTURE_INFORMATION")
    tickers = [f["ticker"] for f in frames]
    # Existing binding verifies the whole IID (including siblings), policy, hashes,
    # session, currency, decision identities and structural conditions before any case.
    binding = bind_integrated_scenarios(session=session, integrated_decision=integrated_decision, tickers=tickers)
    valuation = _valuation(request.get("valuation_artifact"), integrated_decision, session)
    state, owner_status = _owner_state(request.get("owner_portfolio_state"), session)
    if state is None:
        return {"contract_version": CONTRACT_VERSION, "status": owner_status, "mode": "OFFLINE_OPT_IN",
                "comparison": None, "is_actionable": False, "reason": "Explicit supported private portfolio state is required; no empty portfolio is synthesized."}
    candidates, evidence = [], {}
    iid_source = integrated_decision["artifact_identity"]
    for frame in frames:
        ticker = frame["ticker"]
        record = integrated_decision["records"][ticker]
        structural = {"source_identity": iid_source, "session": session, "fundamental_state": record["fundamental_state"],
                      "fitness": (record.get("evidence_axes", {}).get("FUNDAMENTAL") or {}).get("fitness"),
                      "thesis_status": frame.get("thesis_status", "UNKNOWN"), "thesis_source": frame.get("thesis_source")}
        candidate = {k: copy.deepcopy(v) for k, v in frame.items() if k not in {"thesis_status", "thesis_source"}}
        candidate.update(session=session, structural=structural,
                         event_ids=copy.deepcopy((record.get("corporate_intelligence_context") or {}).get("event_identities") or []),
                         sector=(state.get("sector_by_ticker") or {}).get(ticker) or ((state.get("positions") or {}).get(ticker) or {}).get("sector"),
                         source_artifact_identities={"integrated_investment_decision_product": iid_source})
        raw_val = ((valuation or {}).get("records") or {}).get(ticker)
        if raw_val is not None:
            _require(isinstance(raw_val, Mapping) and raw_val.get("ticker") == ticker, "VALUATION_TICKER_MISMATCH")
            peers = raw_val.get("peer_relative") or {}
            _require(isinstance(peers, Mapping), "VALUATION_PEER_METHODS_INVALID")
            # Narrow malformed READY claims before the engine's existing workspace predicate.
            for name, detail in peers.items():
                if isinstance(detail, Mapping) and detail.get("status") == "READY_RESEARCH_ONLY":
                    _require(_finite(detail.get("percentile")) and 0 <= detail["percentile"] <= 1
                             and isinstance(detail.get("peer_count"), int) and not isinstance(detail["peer_count"], bool) and detail["peer_count"] > 0
                             and bool(detail.get("basis")), "QUALIFIED_VALUATION_METHOD_INVALID:" + str(name))
            candidate["valuation"] = {"source_identity": valuation["artifact_identity"], "session": session,
                                      "relative_research_state": raw_val.get("relative_research_state"),
                                      "peer_methods": copy.deepcopy(peers), "earnings_state": raw_val.get("earnings_state"),
                                      "fitness": "IID_BOUND_SCOPED_RELATIVE_RESEARCH"}
        candidates.append(candidate)
        evidence[ticker] = {
            "decision_identity": record["decision_identity"], "source_identities": copy.deepcopy(record.get("source_identities")),
            "evidence_axes": _research_evidence(record.get("evidence_axes")),
            "fundamental_synthesis": copy.deepcopy(record.get("fundamental_synthesis")),
            "valuation_context_summary": _research_evidence(record.get("valuation_context_summary")),
            "valuation_source_record": _research_evidence(raw_val),
            "counter_thesis": copy.deepcopy(record.get("counter_thesis") or []),
            "material_uncertainties": copy.deepcopy(record.get("material_uncertainties") or []),
            "corporate_intelligence_context": copy.deepcopy(record.get("corporate_intelligence_context")),
            "evidence_currency": record.get("evidence_currency"),
            "current_research_decision_input": _research_evidence(record.get("current_research_decision_input")),
            "integrated_scenario_record": copy.deepcopy(binding["records"][ticker]),
        }
    comparison = engine.build_integrated_comparison(session=session, integrated_decision=integrated_decision,
        candidates=candidates, integrated_scenario_binding=binding, owner_portfolio_state=state)
    # Presentation may narrow the engine, never widen it. Preserve its exact identity as
    # lineage; identify the narrowed projection separately rather than mislabelling it v2.
    source_comparison_identity = comparison.pop("comparison_identity")
    units = {u["comparison_unit"]["ticker"]: u for u in comparison["comparison_units"]}
    presented = []
    for case in comparison["research_cases"]:
        if case["case"] == engine.ADD_CORE_REVIEW:
            lenses = units[case["ticker"]]["lenses"]
            if not lenses["core_structural"]["comparable"] or not lenses["strategic"]["valuation_qualified"]:
                comparison["narrowed_by_owner_constraints_or_evidence"].append({
                    "ticker": case["ticker"], "case": case["case"], "reason": "CONSUMER_REQUIRES_STRUCTURAL_AND_QUALIFIED_VALUATION_EVIDENCE"})
                continue
        presented.append(case)
    comparison["research_cases"] = presented
    comparison["case_counts"] = {name: sum(c["case"] == name for c in presented) for name in engine.RESEARCH_CASES if any(c["case"] == name for c in presented)}
    for pair in comparison["pairwise"]:
        comp = pair["comparability"]
        left = units[pair["held_ticker"]]["lenses"]["strategic"]["qualified_methods"]
        right = units[pair["candidate_ticker"]]["lenses"]["strategic"]["qualified_methods"]
        common = [m["method"] for m in left for n in right if m["method"] == n["method"] and m["basis"] == n["basis"]]
        comp["common_valuation_methods"] = sorted(common)
        if comp["axes"]["strategic"] == engine.COMPARABLE and not common:
            comp["axes"]["strategic"] = engine.NOT_COMPARABLE
            comp["common_valuation_methods"] = []
            comp["status"] = engine.NOT_COMPARABLE if comp["axes"]["core_structural"] == engine.NOT_COMPARABLE else engine.PARTIALLY_COMPARABLE
            comp["consumer_limitations"] = ["VALUATION_METHOD_BASIS_NOT_COMPARABLE"]
    alternatives = [case for case in comparison["research_cases"] if case["case"] in {
        engine.ALTERNATIVE_INVESTMENT_REVIEW, engine.INSUFFICIENT_COMPARABLE_EVIDENCE}]
    comparison["research_cases"][-1] = engine._cash_case(state, alternatives, state.get("effective_policy") or {})
    comparison["contract_version"] = CONTRACT_VERSION
    comparison["source_engine_comparison_identity"] = source_comparison_identity
    comparison["comparison_identity"] = CONTRACT_VERSION + ":" + engine._sha(comparison)
    return {"contract_version": CONTRACT_VERSION, "status": "AVAILABLE", "mode": "OFFLINE_OPT_IN",
            "owner_state_status": owner_status, "owner_snapshot_as_of": state["as_of_date"],
            "comparison": comparison, "evidence_by_ticker": evidence, "is_actionable": False,
            "valuation_source_header": None if valuation is None else {
                k: copy.deepcopy(v) for k, v in valuation.items() if k not in {"records", "requested_at"}},
            "limitations": ["Thesis and horizon/role are caller-reported research framing, never holding facts.",
                            "Same-session IID binding does not create PIT or current financial-period authority.",
                            "No ranking, winner, trade, sizing, cash return or production activation."]}


_CASE_TEXT = {
    engine.HOLD_CORE_REVIEW: "Review the existing Core holding against its reported thesis and independent evidence.",
    engine.ADD_CORE_REVIEW: "Evidence supports researching an addition; qualified entry and owner constraints remain conditions.",
    engine.VALUATION_TRIM_REVIEW: "Review expensive qualified relative valuation separately from a thesis break.",
    engine.ALTERNATIVE_INVESTMENT_REVIEW: "Compare an alternative with confirmed holdings; no superiority is asserted.",
    engine.CASH_OPTIONALITY_REVIEW: "Review cash availability and the gaps in alternative research; cash yield is unknown.",
    engine.INSUFFICIENT_COMPARABLE_EVIDENCE: "Structural and qualified valuation evidence cannot support a useful comparison.",
}


def markdown(view: Mapping[str, Any]) -> list[str]:
    """Human-readable private section, ordered by ticker/case rather than investment merit."""
    lines = ["## OPPORTUNITY COST — OPTIONAL RESEARCH", "", "Comparisons and decision changers only; the capital decision stays with the owner.", ""]
    if view.get("status") != "AVAILABLE":
        return lines + [f"- {view['status']}: {view['reason']}", ""]
    comparison = view["comparison"]
    lines += [f"- Owner snapshot: {view['owner_snapshot_as_of']} ({view['owner_state_status']}).",
              f"- Source comparison: `{comparison['comparison_identity']}`.", ""]
    for unit in comparison["comparison_units"]:
        ticker = unit["comparison_unit"]["ticker"]
        lines += [f"### {ticker} — {unit['holding_fact']}",
                  f"- Holding basis: {unit['holding_fact_basis']}."]
        for name, lens in unit["lenses"].items():
            value = lens.get("fundamental_state") if name == "core_structural" else lens.get("relative_research_state") if name == "strategic" else lens.get("confirmation")
            lines.append(f"- {name}: {value}; gaps: {', '.join(lens['gaps']) or 'none'}.")
            source_ref = lens.get("source") or {}
            lines.append(f"  - Source: `{source_ref.get('source_identity') or 'not supplied'}`; fitness: {source_ref.get('fitness') or 'not stated'}; comparison session: {source_ref.get('session') or 'not stated'}.")
            for method in lens.get("qualified_methods") or []:
                lines.append(f"  - Qualified {method['method']}: peer percentile {method['percentile']}, {method['peer_count']} peers; basis: {method['basis']}.")
        source = view["evidence_by_ticker"][ticker]
        tactical = unit["lenses"]["tactical"]
        lines += [f"- Thesis: {unit['lenses']['core_structural']['thesis_status']} (caller-reported); horizon/role: {unit['comparison_unit']['horizon']}/{unit['comparison_unit']['portfolio_role']}.",
                  f"- Evidence currency: {source['evidence_currency']}; decision: `{source['decision_identity']}`.",
                  f"- Upstream counter-evidence: {', '.join(source['counter_thesis']) or 'none stated'}.",
                  f"- Upstream gaps: {', '.join(source['material_uncertainties']) or 'none stated'}.", ""]
        fundamental = ((source.get("current_research_decision_input") or {}).get("dimensions") or {}).get("FUNDAMENTAL") or {}
        corporate = source.get("corporate_intelligence_context") or {}
        valuation = source.get("valuation_source_record") or {}
        lines += [f"- Financial period / freshness: {fundamental.get('as_of_financial_period') or 'not stated'}; {fundamental.get('freshness') or 'not stated'}.",
                  f"- Source trigger / invalidation (research conditions): {tactical.get('trigger')} / {tactical.get('invalidation')}; qualified: {tactical.get('trigger_qualified')} / {tactical.get('invalidation_qualified')}.",
                  f"- Corporate event identities: {corporate.get('event_identities') or 'none supplied'}; evidence session: {corporate.get('evidence_session') or 'not stated'}; stale: {corporate.get('evidence_session_stale')}.",
                  f"- Valuation share basis: {valuation.get('share_basis') or 'not stated'}; limitations: {valuation.get('limitations') or valuation.get('valuation_limitations') or 'not stated'}."]
        for name, method in sorted((valuation.get("methods") or {}).items()):
            if isinstance(method, Mapping):
                lines.append(f"  - {name}: {method.get('status')}; period basis: {method.get('period_basis') or 'not stated'}; blockers: {method.get('blocker_reason_codes') or method.get('reason_codes') or 'none stated'}.")
        lines.append("")
    for case in comparison["research_cases"]:
        lines += [f"### {case['ticker'] or 'CASH'} — {case['case']}", _CASE_TEXT[case["case"]],
                  f"- Supporting evidence: {', '.join(case['supporting_evidence']) or 'none'}.",
                  f"- Counter-evidence: {', '.join(case['counter_evidence']) or 'none'}.",
                  f"- Gaps: {', '.join(case['evidence_gaps']) or 'none'}.",
                  f"- Decision changers: {', '.join(case['decision_changers']) or 'none'}.", ""]
        if case["case"] == engine.CASH_OPTIONALITY_REVIEW:
            lines += [f"- Owner cash facts: {case['cash_fact']}; return assumption: {case['return_assumption']}.", ""]
    for pair in comparison["pairwise"]:
        comp = pair["comparability"]
        lines += [f"- {pair['held_ticker']} / {pair['candidate_ticker']}: {comp['status']}; axes {comp['axes']}; common methods {comp['common_valuation_methods']}; overlap {pair['redundancy']['state']}. No winner."]
        lines.append(f"  - Side by side: {comp['side_by_side']}; correlation fitness: {pair['redundancy'].get('current_correlation')}.")
    for narrowed in comparison["narrowed_by_owner_constraints_or_evidence"]:
        lines.append(f"- {narrowed['ticker']} {narrowed['case']} withheld: {narrowed['reason']}.")
    return lines + [""]
