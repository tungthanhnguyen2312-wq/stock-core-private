"""Use-specific RAW_AS_TRADED / POINT_IN_TIME authority matrix (PROSPECTIVE_RAW_PIT_AUTHORITY_V1).

Ten dimensions, never collapsed into one boolean. ``BEFORE`` is the repository's recorded state at
canonical main ac9b8cf (docs/STATE.md Invariant 1, ROADMAP_STATE ``RAW_AS_TRADED_AND_HISTORICAL_PIT``,
``historical_pit_raw_as_traded_evidence`` OUTCOME_D). ``evaluate`` derives ``AFTER`` from measured
evidence counts only, and types every remaining blocker as engineering-creatable, future-calendar-time,
or external source/permission. A dimension is promoted only inside the scope its counts earn.
"""
from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime
import math
from field_temporal_contract import stable_id

CONTRACT_VERSION = "raw_pit_authority_matrix/v1"

DIMENSIONS = (
    "CURRENT_SESSION_PRICE_RESEARCH", "PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE", "PROSPECTIVE_RAW_AS_TRADED_PRICE",
    "HISTORICAL_RAW_AS_TRADED_PRICE", "CORPORATE_ACTION_EVENT_AUTHORITY", "CORPORATE_ACTION_FACTOR_CHAIN",
    "POINT_IN_TIME_ADJUSTED_HISTORY", "RETROSPECTIVE_ADJUSTED_RESEARCH_HISTORY", "PIT_BACKTEST_ELIGIBILITY",
    "EXECUTION_REPLAY_ELIGIBILITY",
)

# R7 is a consumer lens, independent of the historical promotion evaluator below.
USE_CASES = ("CURRENT_RESEARCH", "PORTFOLIO_RISK_RESEARCH", "POSITION_SIZING_RESEARCH",
             "HISTORICAL_PIT_ANALYSIS", "BACKTEST", "EXECUTION_REPLAY",
             "LIVE_POSITION_SIZING", "LIVE_EXECUTION")
HISTORICAL_USES = frozenset({"HISTORICAL_PIT_ANALYSIS", "BACKTEST", "EXECUTION_REPLAY"})
LIVE_USES = frozenset({"LIVE_POSITION_SIZING", "LIVE_EXECUTION"})
RESEARCH_USES = frozenset(USE_CASES[:3])
FEATURES = ("CURRENT_PRICE", "CURRENT_VOLUME", "HISTORICAL_PRICE", "HISTORICAL_VOLUME",
            "RAW_AS_TRADED", "CA_TIMING", "CA_FACTOR_LINEAGE", "PIT_KNOWLEDGE",
            "CURRENT_LIQUIDITY", "ADTV", "ADV", "CA_NORMALIZED_LIQUIDITY",
            "ACTIVE_UNIVERSE", "EXCHANGE_LISTING", "BOARD", "LOT_SIZE", "PRICE_BAND",
            "FEES_TAXES", "SLIPPAGE_IMPACT", "MARGIN", "BORROW_SHORT", "LEVERAGE",
            "CAPITAL", "CASH_POSITIONS", "RISK_BUDGET", "CONCENTRATION_LIMITS",
            "VOLATILITY_CORRELATION", "INVALIDATION", "EXECUTION_REPLAY", "CURRENT_SHARES", "HISTORICAL_SHARES")


def _instant(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def authority_row(*, feature: str, use_case: str, ticker: str, session: str,
                  evidence: Mapping[str, Any] | None = None,
                  knowledge_cutoff: str | None = None) -> dict[str, Any]:
    """Narrow an explicitly bound upstream feature contract; never grant a new use.

    Qualification is feature/use/session specific. The adapter must preserve upstream
    identity, basis, fitness and knowledge semantics; status alone grants nothing.
    Live authority is deliberately outside this implementation's authorization.
    """
    if feature not in FEATURES or use_case not in USE_CASES:
        raise ValueError("UNSUPPORTED_FEATURE_OR_USE_CASE")
    e = dict(evidence or {})
    reasons = list(e.get("blocker_reason_codes") or [])
    status = e.get("source_status", "UNKNOWN")
    state = "UNKNOWN_SEMANTICS" if not e else "BLOCKED_BY_EVIDENCE"
    fit = (e.get("fitness") or {}).get(use_case)
    if e.get("feature") != feature or e.get("ticker") != ticker or e.get("session") != session:
        reasons.append("FEATURE_OR_SCOPE_NOT_BOUND")
    elif fit == "NOT_APPLICABLE":
        state = "NOT_APPLICABLE"
    else:
        if fit not in {"ELIGIBLE", "PARTIAL"}:
            reasons.append("UPSTREAM_USE_NOT_QUALIFIED")
            reasons.extend(e.get("reason_codes") or [])
        if not e.get("source_identity") or not e.get("basis_identity"):
            reasons.append("SOURCE_OR_BASIS_IDENTITY_MISSING")
        if feature == "ADV" and e.get("metric") != "volume_shares":
            reasons.append("ADV_REQUIRES_SHARE_VOLUME_NOT_ADTV")
        if feature == "ADTV" and e.get("metric") != "value_vnd":
            reasons.append("ADTV_REQUIRES_MONETARY_VALUE_NOT_ADV")
        if feature == "CA_NORMALIZED_LIQUIDITY" and e.get("ca_normalized") is not True:
            reasons.append("CA_NORMALIZATION_NOT_QUALIFIED")
        if feature == "RAW_AS_TRADED" and e.get("raw_basis_qualified") is not True:
            reasons.append("RAW_BASIS_NOT_QUALIFIED")
        if use_case == "EXECUTION_REPLAY":
            if feature == "LOT_SIZE" and (isinstance(e.get("lot_size"), bool) or not isinstance(e.get("lot_size"), int) or e["lot_size"] <= 0):
                reasons.append("QUALIFIED_LOT_SIZE_VALUE_MISSING")
            if feature == "PRICE_BAND":
                bounds = [e.get("lower_price"), e.get("upper_price")]
                if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in bounds) or bounds[0] > bounds[1]:
                    reasons.append("QUALIFIED_PRICE_BAND_VALUES_MISSING")
            if feature == "LEVERAGE" and (isinstance(e.get("maximum_leverage"), bool) or not isinstance(e.get("maximum_leverage"), (int, float)) or not math.isfinite(e["maximum_leverage"]) or e["maximum_leverage"] <= 0):
                reasons.append("GOVERNED_LEVERAGE_LIMIT_MISSING")
            if feature == "MARGIN" and e.get("margin_eligible") is not True:
                reasons.append("MARGIN_NOT_EXPLICITLY_ELIGIBLE")
            if feature == "BORROW_SHORT" and e.get("borrow_available") is not True:
                reasons.append("BORROW_NOT_EXPLICITLY_AVAILABLE")
        if use_case in HISTORICAL_USES:
            known, cutoff = _instant(e.get("knowledge_available_at")), _instant(knowledge_cutoff)
            if not known or not cutoff:
                reasons.append("HISTORICAL_KNOWLEDGE_CUTOFF_UNPROVEN")
            elif known > cutoff:
                reasons.append("FUTURE_KNOWN_EVIDENCE")
            basis_known = _instant(e.get("basis_knowledge_available_at"))
            if e.get("basis_knowledge_available_at") is not None and (not basis_known or not cutoff or basis_known > cutoff):
                reasons.append("FUTURE_OR_UNPROVEN_PROVIDER_BASIS_VERDICT")
            if e.get("temporal_semantics") != "KNOWN_AT_DECISION_SESSION":
                reasons.append("CURRENT_OR_RETROSPECTIVE_FACT_NOT_HISTORICAL_PIT")
            if e.get("evidence_kind") in {"R6_PROSPECTIVE_OBSERVATION", "PROSPECTIVE_PRICE_OBSERVATION"} and use_case in {"BACKTEST", "EXECUTION_REPLAY"}:
                reasons.append("PROSPECTIVE_OBSERVATION_NOT_BACKTEST")
        if feature in {"CA_TIMING", "CA_FACTOR_LINEAGE"} and use_case in HISTORICAL_USES:
            if not e.get("explicit_ex_date"):
                reasons.append("EX_DATE_NOT_EXPLICIT_RECORD_DATE_NOT_SUBSTITUTE")
            if not e.get("executed_lifecycle"):
                reasons.append("EXECUTED_LIFECYCLE_UNPROVEN_PLANS_NOT_EXECUTION")
            if feature == "CA_FACTOR_LINEAGE" and not e.get("qualified_factor_chain_identity"):
                reasons.append("QUALIFIED_FACTOR_CHAIN_MISSING")
        if use_case in LIVE_USES:
            reasons.append("SEPARATE_OWNER_AUTHORITY_PROMOTION_REQUIRED")
        if not reasons:
            state = ("RESEARCH_USABLE" if use_case in RESEARCH_USES else
                     "EXECUTION_USABLE" if use_case == "EXECUTION_REPLAY" else "PIT_USABLE")
    if state == "UNKNOWN_SEMANTICS":
        reasons.append("NO_RETAINED_INPUT_BINDING")
    body = {"contract_version": "portfolio_pit_execution_authority_readiness/v1",
            "feature": feature, "use_case": use_case, "ticker": ticker, "session": session,
            "session_scope": e.get("session_scope", [session]),
            "source_identity": e.get("source_identity"), "basis_identity": e.get("basis_identity"),
            "temporal_semantics": e.get("temporal_semantics", "UNKNOWN"),
            "knowledge_available_at": e.get("knowledge_available_at"), "knowledge_cutoff": knowledge_cutoff,
            "current_historical": "HISTORICAL" if use_case in HISTORICAL_USES else "CURRENT",
            "authority_tier": e.get("authority_tier", "NONE"), "source_status": status,
            "source_fitness": fit, "fitness": state, "warnings": sorted(set((e.get("warnings") or []) + (e.get("reason_codes") or []))),
            "blocker_reason_codes": sorted(set(reasons)), "upstream_evidence": e,
            "promotion_status": "NOT_REQUESTED", "authority_effect": "NONE", "is_actionable": False}
    return {**body, "row_identity": "authority_readiness:" + stable_id(body)}


PIT_REQUIRED_FEATURES = ("HISTORICAL_PRICE", "RAW_AS_TRADED", "CA_TIMING", "CA_FACTOR_LINEAGE",
                         "PIT_KNOWLEDGE", "ACTIVE_UNIVERSE", "EXCHANGE_LISTING")
EXECUTION_REQUIRED_FEATURES = (*PIT_REQUIRED_FEATURES, "HISTORICAL_VOLUME", "CURRENT_LIQUIDITY",
                              "LOT_SIZE", "PRICE_BAND", "LEVERAGE")


def use_case_readiness(*, use_case: str, ticker: str, session: str,
                       evidence: Mapping[str, Mapping[str, Any]], knowledge_cutoff: str | None = None,
                       leveraged: bool = False, short: bool = False) -> dict[str, Any]:
    """Eligibility BEFORE any historical calculation; omissions block only this use."""
    required = (PIT_REQUIRED_FEATURES if use_case in {"HISTORICAL_PIT_ANALYSIS", "BACKTEST"} else
                EXECUTION_REQUIRED_FEATURES if use_case == "EXECUTION_REPLAY" else
                ("CURRENT_PRICE", "CAPITAL", "RISK_BUDGET", "INVALIDATION") if use_case == "POSITION_SIZING_RESEARCH" else
                ("CAPITAL", "CASH_POSITIONS", "CONCENTRATION_LIMITS", "VOLATILITY_CORRELATION") if use_case == "PORTFOLIO_RISK_RESEARCH" else
                ("CURRENT_PRICE", "CURRENT_VOLUME") if use_case == "CURRENT_RESEARCH" else
                (*EXECUTION_REQUIRED_FEATURES, "CAPITAL", "CASH_POSITIONS", "RISK_BUDGET", "INVALIDATION", "CONCENTRATION_LIMITS", "FEES_TAXES", "SLIPPAGE_IMPACT"))
    required = tuple(dict.fromkeys((*required, *(("MARGIN",) if leveraged else ()), *(("BORROW_SHORT",) if short else ()))))
    rows = [authority_row(feature=f, use_case=use_case, ticker=ticker, session=session,
                          evidence=evidence.get(f), knowledge_cutoff=knowledge_cutoff) for f in required]
    # NOT_APPLICABLE is not a qualified prerequisite. Optional dimensions are excluded above.
    blocked = [r for r in rows if r["fitness"] not in {"RESEARCH_USABLE", "PIT_USABLE", "EXECUTION_USABLE"}
               or r["source_fitness"] != "ELIGIBLE"]
    return {"use_case": use_case, "feature_scope": list(required), "global_ticker_rejection": False,
            "state": "BLOCKED_BY_EVIDENCE" if blocked else
            "RESEARCH_USABLE" if use_case in RESEARCH_USES else "EXECUTION_USABLE" if use_case == "EXECUTION_REPLAY" else "PIT_USABLE",
            "required_rows": rows, "blocker_reason_codes": sorted({c for r in blocked for c in r["blocker_reason_codes"]}),
            "blocked_features": [r["feature"] for r in blocked], "authority_effect": "NONE"}


def promotion_dossier(readiness: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Review recommendation only. Does not call evaluate or write an authority registry."""
    rows = []
    for use in USE_CASES[3:]:
        scoped = [r for r in readiness if r["use_case"] == use]
        usable = [r for r in scoped if r["state"] in {"PIT_USABLE", "EXECUTION_USABLE"}]
        blocked = sorted({f for r in scoped for f in r["blocked_features"]})
        rows.append({"requested_use_case": use, "coverage": {"tested_scopes": len(scoped), "eligible_scopes": len(usable)},
                     "supporting_evidence_identities": sorted({x["row_identity"] for r in usable for x in r["required_rows"]}),
                     "retained_context_source_identities": sorted({x["source_identity"] for r in scoped for x in r["required_rows"] if x["source_identity"]}),
                     "status": "PROMOTION_CANDIDATE_REQUIRES_OWNER_APPROVAL" if usable else "BLOCKED_BY_EVIDENCE",
                     "recommended_for_owner_review": bool(usable), "remaining_blockers": blocked,
                     "scope_of_possible_promotion": "ONLY_EXPLICITLY_QUALIFIED_TICKER_SESSION_FEATURE_USES",
                     "representative_validation": "tests/test_portfolio_pit_execution_authority_r7.py",
                     "known_limitations": ["DRY_RUN_ONLY", "NO_REGISTRY_CHANGE", "NO_LIVE_ORDERS"],
                     "reopen_gate": {f: "RETAINED_PROVENANCE_BOUND_" + f + "_EXPLICITLY_QUALIFIED_FOR_" + use for f in blocked}})
    return {"contract_version": "execution_authority_promotion_dossier/v1", "use_cases": rows,
            "authority_effect": "NONE", "owner_promotion_required": True}


def current_readiness_context(record: Mapping[str, Any]) -> dict[str, Any]:
    """Public PORTFOLIO_FIT lens of canonical bindings, not an owner account import.

    Ordinary Integrated Decision does not bind governed capital/holdings or strong
    historical authority. Do not infer those from a watchlist or from current facts.
    """
    ticker, session = record.get("ticker"), record.get("as_of_session")
    views = [use_case_readiness(use_case=u, ticker=ticker, session=session, evidence={}) for u in USE_CASES[1:]]
    invalidation = (record.get("invalidation") or {}).get("condition") or {}
    body = {"contract_version": "portfolio_pit_execution_readiness_context/v1", "ticker": ticker, "session": session,
            "use_case_readiness": {r["use_case"]: {k: r[k] for k in ("state", "blocked_features", "blocker_reason_codes")} for r in views},
            "portfolio_capital_binding": "NOT_PROVIDED_TO_CANONICAL_PRODUCT",
            "current_research_source_status": {f: (record.get("current_research_decision_input", {}).get("dimensions", {}).get(f) or {}).get("state", "UNKNOWN")
                                               for f in ("MARKET", "TECHNICAL", "LIQUIDITY")},
            "theoretical_risk_size_research": {"state": "UNAVAILABLE", "quantity": None, "reason_codes": ["GOVERNED_CAPITAL_AND_RISK_BUDGET_NOT_BOUND"]},
            "execution_eligible_size": {"state": "BLOCKED_BY_EVIDENCE", "quantity": None},
            "retained_invalidation_context": {"condition_identity": invalidation.get("condition_identity"), "status": invalidation.get("status", "UNKNOWN")},
            "source_decision_identity": record.get("decision_identity"), "authority_effect": "NONE", "is_actionable": False,
            "does_not_change_research_action_posture": True, "no_live_order_or_account_mutation": True}
    return {**body, "context_identity": "portfolio_readiness:" + stable_id(body)}


def attach_current_readiness(record: Mapping[str, Any]) -> dict[str, Any]:
    """Copy-only integration; action and decision identity remain untouched."""
    import copy
    result = copy.deepcopy(dict(record))
    context = current_readiness_context(result)
    result.setdefault("portfolio_context", {})["authority_readiness"] = context
    axis = (result.get("evidence_axes") or {}).get("PORTFOLIO_FIT")
    if isinstance(axis, dict):
        axis["authority_readiness"] = {"context_identity": context["context_identity"], "use_case_readiness": context["use_case_readiness"], "is_actionable": False}
    return result

BEFORE = {
    "CURRENT_SESSION_PRICE_RESEARCH": "DESCRIPTIVE_QUALIFIED_ONLY",
    "PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE": "EXPERIMENT_SHADOW_ONLY",
    "PROSPECTIVE_RAW_AS_TRADED_PRICE": "NOT_PROMOTED",
    "HISTORICAL_RAW_AS_TRADED_PRICE": "NOT_PROMOTED",
    "CORPORATE_ACTION_EVENT_AUTHORITY": "EX_DATE_UNQUALIFIED_OUTCOME_D",
    "CORPORATE_ACTION_FACTOR_CHAIN": "BLOCKED",
    "POINT_IN_TIME_ADJUSTED_HISTORY": "BLOCKED",
    "RETROSPECTIVE_ADJUSTED_RESEARCH_HISTORY": "RESEARCH_ONLY_ADJUSTED_RETROSPECTIVE",
    "PIT_BACKTEST_ELIGIBILITY": "BLOCKED",
    "EXECUTION_REPLAY_ELIGIBILITY": "BLOCKED",
}


def _blocker(missing: str, *, engineering: bool, future_time: bool, external: bool, note: str = "") -> dict[str, Any]:
    return {"missing_evidence": missing, "engineering_can_create": engineering,
            "only_future_calendar_time_can_create": future_time, "external_permission_or_data_required": external, "note": note}


def evaluate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """``evidence`` carries measured counts (see tools/run_prospective_raw_pit_authority.py)."""
    e = evidence
    after: dict[str, dict[str, Any]] = {}

    prospective_bars = int(e.get("prospective_dnse_bars", 0))
    cross_agreed = int(e.get("prospective_raw_qualified_bars", 0))
    after["CURRENT_SESSION_PRICE_RESEARCH"] = {
        "state": "QUALIFIED_WITH_PROSPECTIVE_LINEAGE" if prospective_bars and e.get("same_session_cross_source_agreement_09_28", 0) else "DESCRIPTIVE_QUALIFIED_ONLY",
        "scope": "exact-session bars linked to a hashed known-time receipt; official HOSE agreement on the latest session",
        "blockers": [],
    }
    after["PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE"] = {
        "state": "OPERATIONAL" if e.get("prospective_sessions", 0) >= 20 and prospective_bars else "BLOCKED",
        "scope": f"{e.get('prospective_sessions', 0)} retained sessions, {prospective_bars} post-close same-session bars; "
                 "possession at known time only, not a never-revised claim",
        "blockers": [_blocker("automated Daily wiring of the receipt manifest", engineering=True, future_time=False, external=False,
                              note="component-local hook added; Daily never fails on it")],
    }
    after["PROSPECTIVE_RAW_AS_TRADED_PRICE"] = {
        "state": "QUALIFIED_SCOPED_CROSS_SOURCE" if cross_agreed else "BLOCKED",
        "scope": f"{cross_agreed} DNSE post-close bars whose values equal the official HOSE series (empirically unadjusted); "
                 "HOSE-listed tickers only; HNX/UPCoM stay as-known-only (bulk acquisition not authorized)",
        "blockers": [_blocker("independent official series for HNX/UPCoM", engineering=False, future_time=False, external=True,
                              note="HNX written permission or information-service agreement")],
    }
    depth = int(e.get("hose_event_tests_unadjusted", 0))
    after["HISTORICAL_RAW_AS_TRADED_PRICE"] = {
        "state": "PARTIAL_HOSE_EMPIRICAL_SCOPED" if depth >= 2 else "BLOCKED",
        "scope": f"HOSE tradingresult series retained for {e.get('hose_tickers', 0)} tickers; empirically unadjusted across "
                 f"{depth} tested events; research grade only (basis undocumented by the source)",
        "blockers": [
            _blocker("documented raw basis statement from HOSE", engineering=False, future_time=False, external=True),
            _blocker("HNX/UPCoM and pre-retention DNSE history", engineering=False, future_time=False, external=True,
                     note="information loss for pre-2026-08-20 non-HOSE sessions, not engineering debt"),
        ],
    }
    ex_dates = int(e.get("explicit_ex_date_events", 0))
    after["CORPORATE_ACTION_EVENT_AUTHORITY"] = {
        "state": "PARTIAL_EX_DATE_QUALIFIED_TERMS_AND_PUBLICATION_TIME_MISSING" if ex_dates else BEFORE["CORPORATE_ACTION_EVENT_AUTHORITY"],
        "scope": f"{ex_dates} official events with an explicit ex-date (HNX rights event index, retained 2026-09-05); "
                 f"{e.get('ratio_or_cash_terms_events', 0)} carry ratio/cash terms; {e.get('publication_time_events', 0)} carry publication time",
        "blockers": [
            _blocker("ratio / cash amount / issue terms per event", engineering=True, future_time=False, external=False,
                     note="official announcement documents must be acquired and parsed"),
            _blocker("publication (knowledge) time of each announcement", engineering=False, future_time=True, external=False,
                     note="only prospective retention at publication time creates it"),
            _blocker("HOSE-listed event calendar", engineering=True, future_time=False, external=False,
                     note="retained index covers HNX/UPCoM; HOSE tickers have 69 events"),
        ],
    }
    chain = int(e.get("qualified_factor_chain_events", 0))
    after["CORPORATE_ACTION_FACTOR_CHAIN"] = {
        "state": "QUALIFIED_BOUNDED" if chain else "BLOCKED",
        "scope": f"{chain} qualified events",
        "blockers": [] if chain else [
            _blocker("official terms + explicit ex-date + executed-lifecycle evidence + publication cutoff for one event",
                     engineering=True, future_time=True, external=False,
                     note="observed re-basing ratios are consistency evidence only and are never used as the factor"),
        ],
    }
    after["POINT_IN_TIME_ADJUSTED_HISTORY"] = {
        "state": "QUALIFIED_BOUNDED" if chain else "BLOCKED",
        "scope": "contract and readiness only (pit_price_reconstruction_contract); needs a qualified factor chain",
        "blockers": [] if chain else [_blocker("qualified factor chain versioned by knowledge time", engineering=True, future_time=True, external=False)],
    }
    after["RETROSPECTIVE_ADJUSTED_RESEARCH_HISTORY"] = {
        "state": "RESEARCH_ONLY_ADJUSTED_RETROSPECTIVE",
        "scope": f"DNSE series re-fetched later is re-based after the fact: {e.get('official_verified_rebasing_pairs', 0)} bar pairs where the "
                 f"unadjusted official series equals the value known at T0; {e.get('t0_bar_not_final_pairs', 0)} same-day bars were later found non-final; "
                 "never labelled raw or point-in-time",
        "blockers": [],
    }
    after["PIT_BACKTEST_ELIGIBILITY"] = {
        "state": "BLOCKED", "scope": "requires factor chain, PIT universe (ACTIVE_UNIVERSE UNKNOWN), PIT features and history depth",
        "blockers": [
            _blocker("PIT-qualified universe membership (ACTIVE_UNIVERSE)", engineering=False, future_time=False, external=True,
                     note="official listing-status route, not another cohort widening"),
            _blocker("sufficient prospective history depth", engineering=False, future_time=True, external=False),
            _blocker("qualified factor chain", engineering=True, future_time=True, external=False),
        ],
    }
    after["EXECUTION_REPLAY_ELIGIBILITY"] = {
        "state": "BLOCKED", "scope": "execution capacity/sizing policy and tick-level raw trades not established",
        "blockers": [
            _blocker("participation-rate, days-to-liquidate and market-impact policy", engineering=True, future_time=False, external=False),
            _blocker("complete historical trade ticks", engineering=False, future_time=False, external=True,
                     note="local corpus holds only page-capped samples; completeness unprovable"),
        ],
    }
    return {"contract_version": CONTRACT_VERSION, "dimensions": list(DIMENSIONS), "before": dict(BEFORE), "after": after,
            "changed": [d for d in DIMENSIONS if after[d]["state"] != BEFORE[d]]}
