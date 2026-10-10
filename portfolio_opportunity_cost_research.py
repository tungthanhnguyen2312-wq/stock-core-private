"""Offline comparative research: hold, add, valuation trim, alternative, or cash.

Opt-in companion to ``portfolio_research_decision_workbench``. It answers, for a human,
whether a case exists for holding or adding to a Core position, whether a valuation-based
trim review exists without a thesis break, whether another investment is a meaningful
alternative or merely redundant exposure, and whether cash is defensible.

The output is research cases, never instructions. There is no buy/sell/rotate verdict, no
target weight, no size, no order, no expected return, no universal score and no winner.

Comparison unit: ticker x thesis x horizon x portfolio role x market state.

Four independent lenses:
  * core_structural -- fundamental state and thesis status;
  * strategic       -- qualified relative valuation and catalyst/event context;
  * tactical        -- tactical phase and whether it is confirmed;
  * cash_optionality -- owner cash facts only, never a return.

Each lens reads only evidence already admitted under existing contracts (integrated
decision vocabularies, workspace valuation views, ``portfolio_state/v1``). One lens never
rewrites another. Ownership facts come only from an explicit owner portfolio state and are
kept apart from how attractive a stock looks. Owner policy limits can narrow a case; they
never fabricate a holding or widen eligibility. Nothing is persisted and nothing enters
the Owner Daily path.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import stocklookup_core.decision.investment_decision_workspace_projection as workspace_projection
import portfolio_research_decision_workbench as workbench
from stocklookup_core.valuation.current_research_valuation_context import RELATIVE_METHODS
from stocklookup_core.decision.integrated_investment_decision_product import FUNDAMENTAL_STATES, TACTICAL_PHASES

CONTRACT_VERSION = "portfolio_opportunity_cost_research/v1"
PORTFOLIO_STATE_CONTRACT = "portfolio_state/v1"

LENSES = ("core_structural", "strategic", "tactical", "cash_optionality")
HORIZONS = frozenset({"STRUCTURAL", "STRATEGIC", "TACTICAL"})
PORTFOLIO_ROLES = frozenset({"CORE", "STRATEGIC", "TACTICAL"})
THESIS_STATUSES = frozenset({"INTACT", "UNDER_REVIEW", "BROKEN", "UNKNOWN"})

HOLD_CORE_REVIEW = "HOLD_CORE_REVIEW"
ADD_CORE_REVIEW = "ADD_CORE_REVIEW"
VALUATION_TRIM_REVIEW = "VALUATION_TRIM_REVIEW"
ALTERNATIVE_INVESTMENT_REVIEW = "ALTERNATIVE_INVESTMENT_REVIEW"
CASH_OPTIONALITY_REVIEW = "CASH_OPTIONALITY_REVIEW"
INSUFFICIENT_COMPARABLE_EVIDENCE = "INSUFFICIENT_COMPARABLE_EVIDENCE"
RESEARCH_CASES = (
    HOLD_CORE_REVIEW, ADD_CORE_REVIEW, VALUATION_TRIM_REVIEW,
    ALTERNATIVE_INVESTMENT_REVIEW, CASH_OPTIONALITY_REVIEW, INSUFFICIENT_COMPARABLE_EVIDENCE,
)

COMPARABLE = "COMPARABLE"
PARTIALLY_COMPARABLE = "PARTIALLY_COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"

HELD_CONFIRMED = "HELD_CONFIRMED"
NOT_HELD_CONFIRMED = "NOT_HELD_CONFIRMED"
POSITION_UNRESOLVED = "CURRENT_POSITION_UNRESOLVED"
EXCLUDED_INACTIVE = "EXCLUDED_INACTIVE"
OWNER_STATE_NOT_SUPPLIED = "OWNER_STATE_NOT_SUPPLIED"
BASIS_NOT_LISTED = "TICKER_NOT_LISTED_IN_OWNER_PORTFOLIO_STATE"

_SUPPORTIVE_FUNDAMENTAL = frozenset({"IMPROVING", "STABLE"})
_CONFIRMED_TACTICAL = frozenset({"BREAKOUT_CONFIRMED", "RETEST_AFTER_BREAKOUT", "TREND_CONTINUATION"})
_UNCONFIRMED_TACTICAL = frozenset({"BASE_BUILDING", "EARLY_REVERSAL", "BREAKOUT_SETUP"})
_ADVERSE_TACTICAL = frozenset({"DISTRIBUTION_RISK", "BREAKDOWN"})
THESIS_PROVENANCE = "CALLER_REPORTED_RESEARCH_ASSERTION"
STRUCTURAL_THESIS_AUTHORITY = "REPORTED_RESEARCH_CONTEXT_NOT_QUALIFIED_MULTI_YEAR_THESIS"
SCOPED_VALUATION_AUTHORITY = "SCOPED_RELATIVE_RESEARCH_NOT_STRICT_VALUATION"
_RELATIVE_LABELS = frozenset({"ATTRACTIVE_RELATIVE_RESEARCH", "EXPENSIVE_RELATIVE_RESEARCH", "IN_LINE_RELATIVE_RESEARCH"})
FORBIDDEN = workbench.FORBIDDEN + (
    "expected_return", "universal_score", "composite_score", "score", "recommendation",
    "target_weight", "winner", "rotate", "buy", "sell", "capital_decision",
)


class OpportunityCostResearchError(ValueError):
    """An input contract, session, or identity invariant is violated. Fail closed."""


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise OpportunityCostResearchError(code)


def _reject(payload: Mapping[str, Any], where: str) -> None:
    for key in FORBIDDEN:
        if key in payload:
            raise OpportunityCostResearchError(f"FORBIDDEN_{where}_{key.upper()}")


def _source(lens: Mapping[str, Any], *, session: str, where: str) -> dict[str, Any]:
    """A lens's source identity must exist and its session must equal the comparison session."""
    identity = lens.get("source_identity")
    _require(isinstance(identity, str) and identity.strip(), f"{where}_SOURCE_IDENTITY_MISSING")
    _require(lens.get("session") == session, f"{where}_SESSION_MISMATCH")
    return {"source_identity": identity, "session": session, "fitness": lens.get("fitness") or "NOT_STATED"}


# ── Lenses: each reads only its own evidence ────────────────────────────────────

def _core_structural(raw: Mapping[str, Any] | None, *, session: str, ticker: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or not raw:
        return {"status": "MISSING", "fundamental_state": None, "thesis_status": "UNKNOWN",
                "thesis_provenance": None, "structural_thesis_authority": STRUCTURAL_THESIS_AUTHORITY, "source": None,
                "comparable": False, "gaps": ["STRUCTURAL_EVIDENCE_NOT_SUPPLIED"]}
    _reject(raw, "STRUCTURAL")
    source = _source(raw, session=session, where=f"STRUCTURAL:{ticker}")
    state = raw.get("fundamental_state")
    _require(state in FUNDAMENTAL_STATES, f"STRUCTURAL_STATE_UNKNOWN_VOCABULARY:{ticker}")
    thesis = raw.get("thesis_status") or "UNKNOWN"
    _require(thesis in THESIS_STATUSES, f"THESIS_STATUS_UNKNOWN_VOCABULARY:{ticker}")
    gaps = []
    if state == "INSUFFICIENT":
        gaps.append("FUNDAMENTAL_STATE_INSUFFICIENT")
    if thesis == "UNKNOWN":
        gaps.append("THESIS_STATUS_UNKNOWN")
    # The thesis status is a caller/owner research assertion, kept with its provenance. Neither it
    # nor a current fundamental state proves a qualified multi-year structural company thesis.
    provenance = {"basis": THESIS_PROVENANCE, "thesis_source": raw.get("thesis_source")}
    if thesis != "UNKNOWN" and not raw.get("thesis_source"):
        gaps.append("THESIS_ASSERTION_SOURCE_NOT_STATED")
    return {"status": "PRESENT", "fundamental_state": state, "thesis_status": thesis, "thesis_provenance": provenance,
            "structural_thesis_authority": STRUCTURAL_THESIS_AUTHORITY, "source": source,
            "comparable": state != "INSUFFICIENT", "gaps": gaps}


def _label_supported(label: str, methods: Sequence[Mapping[str, Any]]) -> bool:
    """Same direction rule that produced the upstream label: attractive at or below the 25th peer
    percentile, expensive at or above the 75th with no attractive method, in-line otherwise."""
    percentiles = [m["percentile"] for m in methods if isinstance(m.get("percentile"), (int, float)) and not isinstance(m.get("percentile"), bool)]
    attractive = any(value <= 0.25 for value in percentiles)
    expensive = any(value >= 0.75 for value in percentiles)
    if label == "ATTRACTIVE_RELATIVE_RESEARCH":
        return attractive
    if label == "EXPENSIVE_RELATIVE_RESEARCH":
        return expensive and not attractive
    return bool(methods) and not attractive and not expensive


def _strategic(raw: Mapping[str, Any] | None, *, session: str, ticker: str, event_ids: Sequence[str]) -> dict[str, Any]:
    """Scoped relative research valuation, qualified only through the workspace method predicate.

    ``peer_methods`` is the upstream ``peer_relative_context.methods`` mapping. A method counts only
    when it is a true relative method with upstream status READY_RESEARCH_ONLY; a method name or a
    relative label alone is never qualification. This is research-scoped relative fitness, not
    strict valuation authority.
    """
    base = {"event_ids": sorted(event_ids), "catalyst_context": "EVENT_IDS_ONLY_NO_IMPACT_CLAIM",
            "valuation_authority": SCOPED_VALUATION_AUTHORITY}
    if not isinstance(raw, Mapping) or not raw:
        return {**base, "status": "MISSING", "relative_research_state": "UNAVAILABLE", "reported_relative_label": None,
                "qualified_methods": [], "valuation_qualified": False, "source": None, "comparable": False,
                "gaps": ["VALUATION_EVIDENCE_NOT_SUPPLIED"]}
    _reject(raw, "VALUATION")
    source = _source(raw, session=session, where=f"VALUATION:{ticker}")
    label = raw.get("relative_research_state") or "UNAVAILABLE"
    peer_methods = raw.get("peer_methods")
    gaps = []
    if "supporting_methods" in raw:
        gaps.append("SUPPORTING_METHODS_WITHOUT_UPSTREAM_STATUS_IGNORED")
    if not isinstance(peer_methods, Mapping):
        peer_methods = {}
        gaps.append("PEER_METHOD_FITNESS_NOT_SUPPLIED")
    unqualified = sorted(
        str(method_id) for method_id, detail in peer_methods.items()
        if method_id in RELATIVE_METHODS and not (isinstance(detail, Mapping) and detail.get("status") == "READY_RESEARCH_ONLY")
    )
    if unqualified:
        gaps.append("RELATIVE_METHOD_FITNESS_NOT_READY_RESEARCH_ONLY:" + ",".join(unqualified))
    methods = sorted(
        ({"method": m["method"], "basis": m["basis"], "percentile": m["percentile"], "peer_count": m["peer_count"]}
         for m in workspace_projection.qualified_relative_methods(peer_methods)),
        key=lambda item: str(item["method"]),
    )
    qualified = label in _RELATIVE_LABELS and _label_supported(label, methods)
    state = label
    if label in _RELATIVE_LABELS and not qualified:
        gaps.append("RELATIVE_LABEL_NOT_SUPPORTED_BY_QUALIFIED_METHOD")
        state = "UNQUALIFIED_" + label
    elif label not in _RELATIVE_LABELS:
        gaps.append("RELATIVE_VALUATION_" + str(label))
    return {**base, "status": "PRESENT", "relative_research_state": state, "reported_relative_label": label,
            "qualified_methods": methods if qualified else [], "valuation_qualified": qualified,
            "earnings_state": raw.get("earnings_state"), "source": source, "comparable": qualified, "gaps": gaps}


def _tactical(raw: Mapping[str, Any] | None, *, session: str, ticker: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or not raw:
        return {"status": "MISSING", "tactical_phase": None, "confirmation": "UNKNOWN", "source": None,
                "comparable": False, "gaps": ["TACTICAL_EVIDENCE_NOT_SUPPLIED"]}
    _reject(raw, "TACTICAL")
    source = _source(raw, session=session, where=f"TACTICAL:{ticker}")
    phase = raw.get("tactical_phase")
    _require(phase in TACTICAL_PHASES, f"TACTICAL_PHASE_UNKNOWN_VOCABULARY:{ticker}")
    if phase in _CONFIRMED_TACTICAL:
        confirmation = "CONFIRMED"
    elif phase in _UNCONFIRMED_TACTICAL:
        confirmation = "UNCONFIRMED"
    elif phase in _ADVERSE_TACTICAL:
        confirmation = "ADVERSE"
    elif phase == "EXTENDED":
        confirmation = "EXTENDED"
    else:
        confirmation = "UNKNOWN"
    gaps = ["TACTICAL_PHASE_" + phase] if confirmation == "UNKNOWN" else []
    return {"status": "PRESENT", "tactical_phase": phase, "confirmation": confirmation,
            "research_action_posture": raw.get("research_action_posture"), "source": source,
            "comparable": confirmation != "UNKNOWN", "gaps": gaps}


# ── Owner facts: kept apart from attractiveness ─────────────────────────────────

def _owner_exposure(state: Mapping[str, Any] | None) -> dict[str, Any]:
    if state is None:
        return {"status": OWNER_STATE_NOT_SUPPLIED, "basis": "NO_OWNER_EXPOSURE", "sector_weights": {},
                "uncertainty": ["OWNER_PORTFOLIO_STATE_NOT_SUPPLIED"], "source_identities": None}
    _require(state.get("contract_version") == PORTFOLIO_STATE_CONTRACT, "OWNER_PORTFOLIO_STATE_CONTRACT_MISMATCH")
    if state.get("status") != "AVAILABLE":
        return {"status": "OWNER_STATE_NOT_AVAILABLE", "basis": "NO_OWNER_EXPOSURE", "sector_weights": {},
                "uncertainty": ["OWNER_PORTFOLIO_STATE_" + str(state.get("status"))],
                "source_identities": state.get("source_identities")}
    uncertainty = []
    if state.get("nav_basis") in (None, "UNAVAILABLE"):
        uncertainty.append("NAV_UNAVAILABLE")
    positions = state.get("positions") or {}
    unweighted = sorted(t for t, p in positions.items() if p.get("is_active") and p.get("current_weight") is None)
    unsectored = sorted(t for t, p in positions.items() if p.get("is_active") and not p.get("sector"))
    if unweighted:
        uncertainty.append("ACTIVE_POSITIONS_WITHOUT_CURRENT_WEIGHT:" + ",".join(unweighted))
    if unsectored:
        uncertainty.append("ACTIVE_POSITIONS_WITHOUT_SECTOR:" + ",".join(unsectored))
    return {
        "status": "AVAILABLE" if not uncertainty else "PARTIAL_UNCERTAIN",
        "basis": "OWNER_CURRENT_WEIGHT_OF_NAV",
        "as_of_date": state.get("as_of_date"),
        "nav_basis": state.get("nav_basis"),
        "sector_weights": dict(sorted((state.get("sector_weights") or {}).items())),
        "uncertainty": uncertainty,
        "source_identities": state.get("source_identities"),
    }


def _holding_fact(ticker: str, state: Mapping[str, Any] | None, *, require_explicit_quantity: bool = False) -> tuple[str, str]:
    """(holding fact, basis). ``portfolio_state/v1`` carries no position-coverage guarantee: its
    ``positions`` are only the snapshot's rows. A ticker absent from them is therefore unresolved,
    never confirmed not-held."""
    if state is None or state.get("status") != "AVAILABLE":
        return OWNER_STATE_NOT_SUPPLIED, "NO_OWNER_PORTFOLIO_STATE"
    position = (state.get("positions") or {}).get(ticker)
    if not isinstance(position, Mapping):
        return POSITION_UNRESOLVED, BASIS_NOT_LISTED
    if not position.get("is_active"):
        return EXCLUDED_INACTIVE, "OWNER_RESEARCH_EXCLUSION"
    status = position.get("current_position_status", "UNRESOLVED" if require_explicit_quantity else "CURRENT_CONFIRMED")
    if status == "CLOSED":
        return NOT_HELD_CONFIRMED, "OWNER_LEDGER_POSITION_CLOSED"
    if status != "CURRENT_CONFIRMED":
        return POSITION_UNRESOLVED, "OWNER_LEDGER_POSITION_UNRESOLVED"
    if require_explicit_quantity:
        import math
        quantity = position.get("current_quantity")
        if (not isinstance(quantity, (int, float)) or isinstance(quantity, bool)
                or not math.isfinite(quantity) or quantity < 0):
            return POSITION_UNRESOLVED, "OWNER_CURRENT_QUANTITY_UNRESOLVED"
    if (position.get("current_quantity") or 0) > 0:
        return HELD_CONFIRMED, "OWNER_LEDGER_CURRENT_CONFIRMED"
    return NOT_HELD_CONFIRMED, "OWNER_LEDGER_CURRENT_CONFIRMED_ZERO_QUANTITY"


def _concentration(sector: str | None, exposure: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    limit = policy.get("max_sector_weight")
    if not sector:
        return {"sector": None, "owner_sector_weight": None, "owner_sector_limit": limit,
                "status": "SECTOR_UNKNOWN", "uncertainty": list(exposure["uncertainty"])}
    if exposure["status"] in (OWNER_STATE_NOT_SUPPLIED, "OWNER_STATE_NOT_AVAILABLE"):
        return {"sector": sector, "owner_sector_weight": None, "owner_sector_limit": limit,
                "status": "OWNER_EXPOSURE_UNKNOWN", "uncertainty": list(exposure["uncertainty"])}
    weight = exposure["sector_weights"].get(sector, 0.0)
    if isinstance(limit, (int, float)):
        status = "AT_OR_ABOVE_OWNER_SECTOR_LIMIT" if weight >= limit else "BELOW_OWNER_SECTOR_LIMIT"
    else:
        status = "OWNER_SECTOR_LIMIT_NOT_SET"
    if exposure["uncertainty"]:
        # Unweighted or unsectored holdings could belong to this sector: the true weight may be higher.
        status += "_LOWER_BOUND_ONLY"
    return {"sector": sector, "owner_sector_weight": weight, "owner_sector_limit": limit,
            "status": status, "uncertainty": list(exposure["uncertainty"])}


# ── Pairwise comparability and redundancy ───────────────────────────────────────

def _comparability(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    axes = {}
    for axis in ("core_structural", "strategic", "tactical"):
        axes[axis] = COMPARABLE if (left["lenses"][axis]["comparable"] and right["lenses"][axis]["comparable"]) else NOT_COMPARABLE
    left_methods = {m["method"] for m in left["lenses"]["strategic"]["qualified_methods"]}
    right_methods = {m["method"] for m in right["lenses"]["strategic"]["qualified_methods"]}
    common = sorted(left_methods & right_methods)
    if axes["strategic"] == COMPARABLE and not common:
        axes["strategic"] = NOT_COMPARABLE
    # Earnings/valuation comparability is what opportunity cost rests on; tactical alone is not enough.
    if all(state == COMPARABLE for state in axes.values()):
        overall = COMPARABLE
    elif axes["core_structural"] == NOT_COMPARABLE and axes["strategic"] == NOT_COMPARABLE:
        overall = NOT_COMPARABLE
    else:
        overall = PARTIALLY_COMPARABLE
    return {
        "status": overall, "axes": axes, "common_valuation_methods": common,
        "side_by_side": {
            axis: {left["ticker"]: _axis_value(left, axis), right["ticker"]: _axis_value(right, axis)}
            for axis in ("core_structural", "strategic", "tactical")
        },
        "superiority": None,
        "winner": None,
    }


def _axis_value(unit: Mapping[str, Any], axis: str) -> Any:
    lens = unit["lenses"][axis]
    if axis == "core_structural":
        return {"fundamental_state": lens["fundamental_state"], "thesis_status": lens["thesis_status"]}
    if axis == "strategic":
        return {"relative_research_state": lens["relative_research_state"], "qualified_methods": lens["qualified_methods"]}
    return {"tactical_phase": lens["tactical_phase"], "confirmation": lens["confirmation"]}


def _redundancy(left: Mapping[str, Any], right: Mapping[str, Any], correlation: Mapping[str, Any] | None) -> dict[str, Any]:
    signals = []
    unknown = []
    if left["sector"] and right["sector"]:
        if left["sector"] == right["sector"]:
            signals.append("SAME_SECTOR")
    else:
        unknown.append("SECTOR")
    if left["style"] and right["style"] and left["style"] == right["style"]:
        signals.append("SAME_STYLE_FACTOR")
    shared_thesis = sorted(set(left["thesis_ids"]) & set(right["thesis_ids"]))
    shared_event = sorted(set(left["event_ids"]) & set(right["event_ids"]))
    if shared_thesis:
        signals.append("SHARED_THESIS")
    if shared_event:
        signals.append("SHARED_EVENT")
    corr_view = {"status": "MISSING", "value": None, "comparable": False}
    if correlation is not None:
        corr_view = {key: correlation.get(key) for key in ("status", "value", "date_alignment", "aligned_points", "comparable", "authority")}
    if not corr_view.get("comparable"):
        unknown.append("DATE_ALIGNED_CORRELATION")
    if "SAME_SECTOR" in signals and ("SHARED_THESIS" in signals or "SHARED_EVENT" in signals):
        state = "LIKELY_REDUNDANT_EXPOSURE"
    elif signals:
        state = "PARTIAL_OVERLAP"
    elif "SECTOR" in unknown:
        state = "OVERLAP_UNKNOWN"
    else:
        state = "NO_OVERLAP_OBSERVED"
    return {"state": state, "signals": signals, "shared_thesis_ids": shared_thesis, "shared_event_ids": shared_event,
            "unknown_dimensions": unknown, "current_correlation": corr_view}


# ── Research cases ──────────────────────────────────────────────────────────────

def _case(kind: str, unit: Mapping[str, Any], *, support: list[str], counter: list[str], gaps: list[str],
          changers: list[str], concentration: Mapping[str, Any] | None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    sources = {
        lens: unit["lenses"][lens]["source"] for lens in ("core_structural", "strategic", "tactical")
        if unit["lenses"][lens]["source"] is not None
    }
    body = {
        "case": kind,
        "ticker": unit["ticker"],
        "comparison_unit": unit["comparison_unit"],
        "holding_fact": unit["holding_fact"],
        "holding_fact_basis": unit["holding_fact_basis"],
        "supporting_evidence": support,
        "counter_evidence": counter,
        "evidence_gaps": sorted(set(gaps)),
        "thesis_id": unit["comparison_unit"]["thesis_id"],
        "horizon": unit["comparison_unit"]["horizon"],
        "portfolio_role": unit["comparison_unit"]["portfolio_role"],
        "concentration_overlap": concentration,
        "decision_changers": changers + list(unit["source_invalidation"]),
        "source_identities_and_fitness": sources,
        "is_instruction": False,
    }
    if extra:
        body.update(extra)
    return body


def _structural_evidence(unit: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    lens = unit["lenses"]["core_structural"]
    support, counter = [], []
    if lens["fundamental_state"] in _SUPPORTIVE_FUNDAMENTAL:
        support.append("FUNDAMENTAL_" + lens["fundamental_state"])
    elif lens["fundamental_state"] in ("DETERIORATING", "MIXED"):
        counter.append("FUNDAMENTAL_" + lens["fundamental_state"])
    if lens["thesis_status"] == "INTACT":
        support.append("REPORTED_THESIS_INTACT")
    elif lens["thesis_status"] in ("UNDER_REVIEW", "BROKEN"):
        counter.append("REPORTED_THESIS_" + lens["thesis_status"])
    return support, counter


def _tactical_evidence(unit: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    lens = unit["lenses"]["tactical"]
    if lens.get("research_action_policy_version") == "v2":
        status = lens["confirmation"]
        reason = "TACTICAL_" + lens["posture_condition_class"] + "_" + status
        if status == "ENTRY_ADMITTED":
            return [reason], []
        if status in {"EXTENDED", "REBASE_REQUIRED", "ADVERSE", "DISTRIBUTION_UNCONFIRMED", "VETOED", "NARROWED"}:
            return [], [reason]
        return [], []
    if lens["confirmation"] == "CONFIRMED":
        return ["TACTICAL_" + lens["tactical_phase"] + "_CONFIRMED"], []
    if lens["confirmation"] in ("UNCONFIRMED", "ADVERSE", "EXTENDED"):
        return [], ["TACTICAL_" + lens["tactical_phase"] + "_" + lens["confirmation"]]
    return [], []


def _held_cases(unit: Mapping[str, Any], concentration: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    structural = unit["lenses"]["core_structural"]
    strategic = unit["lenses"]["strategic"]
    tactical = unit["lenses"]["tactical"]
    gaps = structural["gaps"] + strategic["gaps"] + tactical["gaps"]
    s_support, s_counter = _structural_evidence(unit)
    t_support, t_counter = _tactical_evidence(unit)
    cases, narrowed = [], []
    expensive = strategic["valuation_qualified"] and strategic["relative_research_state"] == "EXPENSIVE_RELATIVE_RESEARCH"
    valuation_counter = ["QUALIFIED_EXPENSIVE_RELATIVE_VALUATION"] if expensive else []
    # The Core hold case is judged on the structural lens. Tactical weakness is shown as counter-
    # evidence on a different horizon; it never removes or relabels the structural state.
    cases.append(_case(
        HOLD_CORE_REVIEW, unit, support=s_support, counter=s_counter + valuation_counter + t_counter, gaps=gaps,
        changers=["FUNDAMENTAL_STATE_BECOMES_DETERIORATING", "THESIS_STATUS_BECOMES_BROKEN"],
        concentration=concentration,
        extra={"structural_case_status": _structural_case_status(structural),
               "tactical_lens_is_independent": True},
    ))
    thesis_break = structural["thesis_status"] == "BROKEN" or structural["fundamental_state"] == "DETERIORATING"
    if expensive and not thesis_break:
        cases.append(_case(
            VALUATION_TRIM_REVIEW, unit,
            support=["QUALIFIED_EXPENSIVE_RELATIVE_VALUATION:" + ",".join(m["method"] for m in strategic["qualified_methods"])],
            counter=s_support + t_support, gaps=gaps,
            changers=["RELATIVE_VALUATION_RETURNS_TO_IN_LINE_OR_ATTRACTIVE",
                      "REPORTED_THESIS_BREAK_MOVES_THIS_TO_THESIS_REVIEW_NOT_VALUATION_TRIM"],
            concentration=concentration,
            extra={"fundamental_thesis_break": False, "trim_basis": "VALUATION_ONLY"},
        ))
    elif strategic["relative_research_state"] == "UNQUALIFIED_EXPENSIVE_RELATIVE_RESEARCH":
        narrowed.append({"ticker": unit["ticker"], "case": VALUATION_TRIM_REVIEW,
                         "reason": "EXPENSIVE_LABEL_NOT_SUPPORTED_BY_QUALIFIED_METHOD"})
    entry_allowed = tactical.get("research_action_policy_version") != "v2" or tactical["confirmation"] == "ENTRY_ADMITTED"
    if not entry_allowed:
        narrowed.append({"ticker": unit["ticker"], "case": ADD_CORE_REVIEW, "reason": "NO_QUALIFIED_INTEGRATED_ENTRY_TRIGGER"})
    if s_support and not s_counter and not expensive and not thesis_break and entry_allowed:
        reasons = _owner_limit_reasons(unit, concentration, policy)
        if reasons:
            narrowed.extend({"ticker": unit["ticker"], "case": ADD_CORE_REVIEW, "reason": reason} for reason in reasons)
        else:
            add_gaps = gaps + ([] if strategic["valuation_qualified"] else ["VALUATION_NOT_QUALIFIED_NO_VALUE_CLAIM"])
            cases.append(_case(
                ADD_CORE_REVIEW, unit, support=s_support + t_support, counter=t_counter, gaps=add_gaps,
                changers=["SECTOR_WEIGHT_REACHES_OWNER_LIMIT", "VALUATION_BECOMES_QUALIFIED_EXPENSIVE",
                          "TACTICAL_PHASE_BECOMES_BREAKDOWN"],
                concentration=concentration,
            ))
    return cases, narrowed


def _structural_case_status(lens: Mapping[str, Any]) -> str:
    if lens["status"] == "MISSING" or lens["fundamental_state"] == "INSUFFICIENT":
        return "STRUCTURAL_EVIDENCE_INSUFFICIENT"
    if lens["thesis_status"] == "BROKEN":
        return "REPORTED_THESIS_BREAK"
    if lens["thesis_status"] == "UNDER_REVIEW":
        return "REPORTED_THESIS_UNDER_REVIEW"
    if lens["fundamental_state"] in ("DETERIORATING", "MIXED"):
        return "FUNDAMENTAL_STATE_CONTESTS_REPORTED_THESIS"
    if lens["thesis_status"] == "UNKNOWN":
        return "THESIS_STATUS_UNKNOWN"
    return "REPORTED_THESIS_INTACT_FUNDAMENTAL_STATE_CONSISTENT"


def _owner_limit_reasons(unit: Mapping[str, Any], concentration: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    reasons = []
    if concentration["status"].startswith("AT_OR_ABOVE_OWNER_SECTOR_LIMIT"):
        reasons.append("OWNER_SECTOR_LIMIT_REACHED")
    weight = unit.get("owner_position_weight")
    limit = policy.get("max_single_position_weight")
    if isinstance(weight, (int, float)) and isinstance(limit, (int, float)) and weight >= limit:
        reasons.append("OWNER_SINGLE_POSITION_LIMIT_REACHED")
    return reasons


def _alternative_case(unit: Mapping[str, Any], held: Sequence[Mapping[str, Any]], pairs: Mapping[tuple[str, str], Mapping[str, Any]],
                      concentration: Mapping[str, Any]) -> dict[str, Any]:
    structural = unit["lenses"]["core_structural"]
    strategic = unit["lenses"]["strategic"]
    tactical = unit["lenses"]["tactical"]
    gaps = structural["gaps"] + strategic["gaps"] + tactical["gaps"]
    if not structural["comparable"] and not strategic["comparable"]:
        return _case(
            INSUFFICIENT_COMPARABLE_EVIDENCE, unit, support=[], counter=[], gaps=gaps,
            changers=["STRUCTURAL_OR_QUALIFIED_VALUATION_EVIDENCE_BECOMES_AVAILABLE"], concentration=concentration,
            extra={"comparisons": [pairs[_pair_key(unit["ticker"], h["ticker"])] for h in held]},
        )
    s_support, s_counter = _structural_evidence(unit)
    t_support, t_counter = _tactical_evidence(unit)
    support = s_support + t_support
    if strategic["valuation_qualified"] and strategic["relative_research_state"] == "ATTRACTIVE_RELATIVE_RESEARCH":
        support.append("QUALIFIED_ATTRACTIVE_RELATIVE_VALUATION")
    counter = s_counter + t_counter
    if strategic["valuation_qualified"] and strategic["relative_research_state"] == "EXPENSIVE_RELATIVE_RESEARCH":
        counter.append("QUALIFIED_EXPENSIVE_RELATIVE_VALUATION")
    if concentration["status"].startswith("AT_OR_ABOVE_OWNER_SECTOR_LIMIT"):
        counter.append("OWNER_SECTOR_AT_OR_ABOVE_LIMIT")
    comparisons = [pairs[_pair_key(unit["ticker"], h["ticker"])] for h in held]
    for comparison in comparisons:
        if comparison["redundancy"]["state"] == "LIKELY_REDUNDANT_EXPOSURE":
            counter.append("LIKELY_REDUNDANT_WITH_HELD:" + comparison["held_ticker"])
    if not held:
        gaps.append("NO_CONFIRMED_HOLDING_TO_COMPARE_AGAINST")
    if unit["holding_fact_basis"] == BASIS_NOT_LISTED:
        gaps.append("HOLDING_FACT_UNRESOLVED_" + BASIS_NOT_LISTED)
    return _case(
        ALTERNATIVE_INVESTMENT_REVIEW, unit, support=support, counter=counter, gaps=gaps,
        changers=["NOT_COMPARABLE_AXES_BECOME_COMPARABLE", "OWNER_SECTOR_WEIGHT_CHANGES",
                  "SHARED_THESIS_OR_EVENT_RESOLVES"],
        concentration=concentration,
        extra={"comparisons": comparisons},
    )


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _cash_case(state: Mapping[str, Any] | None, alternatives: Sequence[Mapping[str, Any]], policy: Mapping[str, Any]) -> dict[str, Any]:
    incomplete = sorted(
        case["ticker"] for case in alternatives
        if case["case"] == INSUFFICIENT_COMPARABLE_EVIDENCE
        or any(c["comparability"]["status"] != COMPARABLE for c in case.get("comparisons") or [])
        or any(gap for gap in case["evidence_gaps"])
    )
    support = ["ALTERNATIVES_WITH_INCOMPLETE_EVIDENCE:" + ",".join(incomplete)] if incomplete else []
    counter = ["CASH_HAS_NO_RESEARCH_RETURN_EVIDENCE"]
    gaps = []
    cash_fact: dict[str, Any]
    if state is None or state.get("status") != "AVAILABLE":
        cash_fact = {"status": OWNER_STATE_NOT_SUPPLIED, "cash_available": None, "cash_to_nav": None}
        gaps.append("OWNER_CASH_FACT_NOT_SUPPLIED")
    else:
        cash = state.get("cash_available")
        nav = state.get("effective_nav")
        ratio = (cash / nav) if isinstance(cash, (int, float)) and isinstance(nav, (int, float)) and nav else None
        cash_fact = {"status": "OWNER_STATE_FACT", "cash_available": cash, "cash_to_nav": ratio,
                     "minimum_cash_reserve_to_nav": policy.get("minimum_cash_reserve_to_nav")}
        reserve = policy.get("minimum_cash_reserve_to_nav")
        if ratio is not None and isinstance(reserve, (int, float)) and ratio <= reserve:
            support.append("CASH_AT_OR_BELOW_OWNER_RESERVE_POLICY")
        if ratio is None:
            gaps.append("CASH_TO_NAV_UNAVAILABLE")
    return {
        "case": CASH_OPTIONALITY_REVIEW,
        "ticker": None,
        "comparison_unit": {"ticker": "CASH", "thesis_id": None, "horizon": None, "portfolio_role": "CASH_OPTIONALITY",
                            "market_state": None},
        "holding_fact": cash_fact["status"],
        "cash_fact": cash_fact,
        "supporting_evidence": support,
        "counter_evidence": counter,
        "evidence_gaps": gaps,
        "thesis_id": None,
        "horizon": None,
        "portfolio_role": "CASH_OPTIONALITY",
        "concentration_overlap": None,
        "decision_changers": ["AN_ALTERNATIVE_BECOMES_COMPARABLE_ON_STRUCTURAL_AND_VALUATION_AXES"],
        "source_identities_and_fitness": {"owner_portfolio_state": (state or {}).get("source_identities")},
        "expected_return": None,
        "return_assumption": "NONE_NOT_INVENTED",
        "is_instruction": False,
    }


# ── Entry point ─────────────────────────────────────────────────────────────────

def _unit(raw: Mapping[str, Any], *, session: str, market: Mapping[str, Any] | None,
          state: Mapping[str, Any] | None, integrated_lens: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _require(isinstance(raw, Mapping), "CANDIDATE_INVALID")
    _reject(raw, "CANDIDATE")
    ticker = raw.get("ticker")
    _require(isinstance(ticker, str) and ticker.strip(), "TICKER_REQUIRED")
    ticker = ticker.strip().upper()
    _require(raw.get("session") == session, f"CANDIDATE_SESSION_MISMATCH:{ticker}")
    horizon = raw.get("horizon")
    role = raw.get("portfolio_role")
    _require(horizon in HORIZONS, f"HORIZON_REQUIRED:{ticker}")
    _require(role in PORTFOLIO_ROLES, f"PORTFOLIO_ROLE_REQUIRED:{ticker}")
    thesis_ids = sorted({t for t in raw.get("thesis_ids") or [] if isinstance(t, str) and t.strip()})
    event_ids = sorted({e for e in raw.get("event_ids") or [] if isinstance(e, str) and e.strip()})
    holding, holding_basis = _holding_fact(ticker, state, require_explicit_quantity=integrated_lens is not None)
    position = ((state or {}).get("positions") or {}).get(ticker) or {}
    return {
        "ticker": ticker,
        "comparison_unit": {
            "ticker": ticker, "thesis_id": raw.get("thesis_id"), "horizon": horizon, "portfolio_role": role,
            "market_state": (market or {}).get("market_state"),
        },
        "holding_fact": holding,
        "holding_fact_basis": holding_basis,
        "owner_position_weight": position.get("current_weight") if holding == HELD_CONFIRMED else None,
        "sector": raw.get("sector") if isinstance(raw.get("sector"), str) and raw.get("sector").strip() else None,
        "style": raw.get("style") if isinstance(raw.get("style"), str) and raw.get("style").strip() else None,
        "thesis_ids": thesis_ids,
        "event_ids": event_ids,
        "source_invalidation": [str(item) for item in raw.get("invalidation") or [] if isinstance(item, str)],
        "source_artifact_identities": dict(raw.get("source_artifact_identities") or {}),
        "lenses": {
            "core_structural": _core_structural(raw.get("structural"), session=session, ticker=ticker),
            "strategic": _strategic(raw.get("valuation"), session=session, ticker=ticker, event_ids=event_ids),
            "tactical": dict(integrated_lens) if integrated_lens is not None else _tactical(raw.get("tactical"), session=session, ticker=ticker),
        },
        "_workbench_row": {
            key: raw[key] for key in ("sector", "style", "current_returns", "current_return_dates") if key in raw
        } | {"ticker": ticker, "thesis_ids": thesis_ids, "event_ids": event_ids},
    }


def build_comparison(
    *,
    session: str,
    candidates: Sequence[Mapping[str, Any]],
    owner_portfolio_state: Mapping[str, Any] | None = None,
    market_context: Mapping[str, Any] | None = None,
    _integrated_lenses: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the opt-in comparative research view. Raises on any session or identity mismatch."""
    _require(isinstance(session, str) and session.strip(), "SESSION_REQUIRED")
    if market_context is not None:
        _reject(market_context, "MARKET")
        _source(market_context, session=session, where="MARKET_CONTEXT")
    exposure = _owner_exposure(owner_portfolio_state)
    available_state = owner_portfolio_state if exposure["status"] not in (OWNER_STATE_NOT_SUPPLIED, "OWNER_STATE_NOT_AVAILABLE") else None
    policy = dict((available_state or {}).get("effective_policy") or {})

    units = [_unit(raw, session=session, market=market_context, state=available_state,
                   integrated_lens=(_integrated_lenses or {}).get(raw.get("ticker"))) for raw in candidates]
    tickers = [unit["ticker"] for unit in units]
    _require(len(tickers) == len(set(tickers)), "DUPLICATE_COMPARISON_UNIT_TICKER")
    integrated = {unit["source_artifact_identities"].get("integrated_investment_decision_product") for unit in units} - {None}
    _require(len(integrated) <= 1, "CROSS_SOURCE_INTEGRATED_IDENTITY_MISMATCH")
    units.sort(key=lambda unit: unit["ticker"])

    # Reuse the workbench for overlap, opportunity counts and date-aligned correlation.
    bench = workbench.build_workbench([unit["_workbench_row"] for unit in units])
    correlations = {(pair["left"], pair["right"]): pair for pair in bench["current_correlation"]["pairs"]}

    held = [unit for unit in units if unit["holding_fact"] == HELD_CONFIRMED]
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for unit in units:
        if unit["holding_fact"] == HELD_CONFIRMED:
            continue
        for holding in held:
            key = _pair_key(unit["ticker"], holding["ticker"])
            pairs[key] = {
                "candidate_ticker": unit["ticker"],
                "held_ticker": holding["ticker"],
                "comparability": _comparability(holding, unit),
                "redundancy": _redundancy(holding, unit, correlations.get(key)),
            }

    cases: list[dict[str, Any]] = []
    narrowed: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for unit in units:
        concentration = _concentration(unit["sector"], exposure, policy)
        if unit["holding_fact"] == HELD_CONFIRMED:
            held_cases, held_narrowed = _held_cases(unit, concentration, policy)
            cases.extend(held_cases)
            narrowed.extend(held_narrowed)
        elif unit["holding_fact"] in (NOT_HELD_CONFIRMED, OWNER_STATE_NOT_SUPPLIED) or unit["holding_fact_basis"] == BASIS_NOT_LISTED:
            # A ticker merely absent from the snapshot may be reviewed as an alternative, but its
            # holding fact stays unresolved and is listed as a gap, never as confirmed not-held.
            if unit["holding_fact_basis"] == BASIS_NOT_LISTED:
                unresolved.append({"ticker": unit["ticker"], "holding_fact": unit["holding_fact"], "basis": BASIS_NOT_LISTED})
            cases.append(_alternative_case(unit, held, pairs, concentration))
        else:
            # Excluded or unresolved: the holding fact is unknown or owner-excluded, so no
            # hold/add/trim case may assert it and no alternative case may imply it is free.
            unresolved.append({"ticker": unit["ticker"], "holding_fact": unit["holding_fact"], "basis": unit["holding_fact_basis"]})
    alternatives = [case for case in cases if case["case"] in (ALTERNATIVE_INVESTMENT_REVIEW, INSUFFICIENT_COMPARABLE_EVIDENCE)]
    cases.append(_cash_case(available_state, alternatives, policy))

    case_counts: dict[str, int] = {}
    for case in cases:
        case_counts[case["case"]] = case_counts.get(case["case"], 0) + 1
    body = {
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "authority": "RESEARCH_ONLY",
        "mode": "OFFLINE_OPT_IN",
        "lenses": list(LENSES),
        "comparison_units": [
            {"comparison_unit": unit["comparison_unit"], "holding_fact": unit["holding_fact"],
             "holding_fact_basis": unit["holding_fact_basis"], "lenses": unit["lenses"]}
            for unit in units
        ],
        "owner_exposure": exposure,
        "opportunity_concentration": {
            "sector": bench["sector_concentration"], "style": bench["style_concentration"],
        },
        "pairwise": [pairs[key] for key in sorted(pairs)],
        "research_cases": cases,
        "case_counts": dict(sorted(case_counts.items())),
        "narrowed_by_owner_constraints_or_evidence": narrowed,
        "holding_fact_unresolved_or_excluded": unresolved,
        "market_context": None if market_context is None else {
            "market_state": market_context.get("market_state"),
            "source_identity": market_context.get("source_identity"),
            "use": "DESCRIPTIVE_CONTEXT_ONLY",
        },
        "source_identities": {
            "integrated_investment_decision_product": next(iter(integrated), None),
            "owner_portfolio_state": exposure.get("source_identities"),
            "workbench_identity": bench["workbench_identity"],
        },
        "capital_decision": None,
        "universal_score": None,
        "winner": None,
        "target_weights": None,
        "position_size": None,
        "order": None,
        "expected_return": None,
        "is_actionable": False,
        "persisted": False,
    }
    body["comparison_identity"] = CONTRACT_VERSION + ":" + _sha(body)
    return body


V2_CONTRACT_VERSION = "portfolio_opportunity_cost_research/v2"
V2_CLASSIFICATION = {
    "FRESH_ENTRY_TRIGGER": "ENTRY_ADMITTED", "CONFIRMED_RETEST_ENTRY": "ENTRY_ADMITTED",
    "BASE_UNCONFIRMED": "UNCONFIRMED", "EARLY_MONITOR_NO_TRIGGER": "UNCONFIRMED",
    "CONSTRUCTIVE_TREND_NO_FRESH_ENTRY": "NON_ENTRY", "EXTENDED_NO_CHASE": "EXTENDED",
    "FAILED_BREAKOUT_REBASE_REQUIRED": "REBASE_REQUIRED", "FAILED_BREAKOUT_WITH_DETERIORATION": "ADVERSE",
    "BEARISH_STRUCTURE_ADVERSE": "ADVERSE", "DISTRIBUTION_OR_BREAKDOWN_WITH_DETERIORATION": "ADVERSE",
    "DISTRIBUTION_RISK_NO_FRESH_ENTRY": "DISTRIBUTION_UNCONFIRMED",
    "MISSING_CURRENT_EVIDENCE": "NOT_USABLE", "UNQUALIFIED_TACTICAL_STRUCTURE": "NOT_USABLE",
    "UNQUALIFIED_TACTICAL_AND_FUNDAMENTAL": "NOT_USABLE",
    "FUNDAMENTAL_DETERIORATION_VETO_NO_NEW_ENTRY": "VETOED",
    "EARLY_REVERSAL_AWAITING_HIGHER_LOW": "UNCONFIRMED",
    "PARTICIPATION_CONTRADICTION_NARROWS_ENTRY": "NARROWED",
    "BEARISH_BREADTH_NARROWS_FRESH_ENTRY": "NARROWED",
    "PENDING_DEFINED_CONFIRMATION": "UNCONFIRMED", "OBSERVATIONAL_NO_ENTRY": "NON_ENTRY",
}


def build_integrated_comparison(*, session: str, integrated_decision: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]],
                                integrated_scenario_binding: Mapping[str, Any] | None = None,
                                owner_portfolio_state: Mapping[str, Any] | None = None,
                                market_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Distinct v2 path; legacy callers and historical phase-only research stay v1."""
    import copy
    from current_evidence_bound_scenario import bind_integrated_scenarios, validate_integrated_binding
    tickers = [row.get("ticker") for row in candidates]
    binding = integrated_scenario_binding if integrated_scenario_binding is not None else bind_integrated_scenarios(
        session=session, integrated_decision=integrated_decision, tickers=tickers)
    validate_integrated_binding(binding, session=session, integrated_decision=integrated_decision, tickers=tickers)
    source = integrated_decision["artifact_identity"]
    lenses, prepared = {}, []
    for candidate in candidates:
        ticker = candidate["ticker"]
        record = binding["records"][ticker]
        raw = copy.deepcopy(dict(candidate))
        asserted = (raw.get("source_artifact_identities") or {}).get("integrated_investment_decision_product")
        _require(asserted in (None, source), "CROSS_SOURCE_INTEGRATED_IDENTITY_MISMATCH")
        for name in ("tactical", "structural"):
            if raw.get(name):
                _require(raw[name].get("source_identity") == source, "INTEGRATED_LENS_IDENTITY_MISMATCH")
                _require(raw[name].get("session") == session, "INTEGRATED_LENS_SESSION_MISMATCH")
        if raw.get("tactical"):
            for key in ("research_action_posture", "posture_condition_class", "research_action_policy_version", "decision_identity", "tactical_phase", "evidence_currency"):
                _require(key not in raw["tactical"] or raw["tactical"][key] == record[key], "INTEGRATED_TACTICAL_CONFLICT")
        structural = raw.get("structural") or {}
        _require("fundamental_state" not in structural or structural["fundamental_state"] == record["fundamental_state"], "INTEGRATED_FUNDAMENTAL_CONFLICT")
        raw["structural"] = {**structural, "source_identity": source, "session": session,
                             "fundamental_state": record["fundamental_state"]}
        raw["source_artifact_identities"] = {**(raw.get("source_artifact_identities") or {}), "integrated_investment_decision_product": source}
        status = V2_CLASSIFICATION[record["posture_condition_class"]]
        if status == "ENTRY_ADMITTED" and record["bull_case"]["case_status"] != "CONDITIONAL":
            status = "NOT_USABLE"
        if status == "ADVERSE" and not record["bear_case"]["observed_adverse"]:
            status = "NOT_USABLE"
        lens = {k: copy.deepcopy(record[k]) for k in ("research_action_posture", "posture_condition_class", "research_action_policy_version",
                "decision_identity", "tactical_phase", "evidence_currency", "trigger", "invalidation", "trigger_qualified", "invalidation_qualified")}
        lens.update(status="PRESENT", confirmation=status, source={"source_identity": source, "session": session, "fitness": "VERIFIED_INTEGRATED_V2"},
                    comparable=status != "NOT_USABLE", gaps=["TACTICAL_NOT_USABLE"] if status == "NOT_USABLE" else [],
                    non_entry_context=[record["posture_condition_class"]] if status in {"NON_ENTRY", "UNCONFIRMED"} else [])
        lenses[ticker] = lens
        prepared.append(raw)
    body = build_comparison(session=session, candidates=prepared, owner_portfolio_state=owner_portfolio_state,
                            market_context=market_context, _integrated_lenses=lenses)
    body["contract_version"] = V2_CONTRACT_VERSION
    body["research_action_policy_version"] = "v2"
    body["source_identities"]["integrated_scenario_binding"] = binding["artifact_identity"]
    body.pop("comparison_identity")
    body["comparison_identity"] = V2_CONTRACT_VERSION + ":" + _sha(body)
    return body
