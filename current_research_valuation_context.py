"""Current research valuation + same-method peer context over retained inputs.

Reuses existing valuation applicability, share-basis tiers, and Tactical V2 percentile
semantics. It does not invent DCF, fair-value, consensus, target prices, or probabilities.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
import re
from statistics import median
from typing import Any, Mapping, Sequence

from current_market_sector_leadership_context import _percentile
import monetary_basis_contract as basis_contract
from market_wide_current_valuation_input_scaleout import RESEARCH_SHARE_AUTHORITIES, _applicability, _market_cap_monetary_basis
from operational_fundamental_context_integration import MAX_COMPLETED_QUARTER_LAG
from opportunity_axis_freshness import UNAVAILABLE, axis_is_research_usable, classify_axis_freshness, completed_quarter_lag
from sector_relative_research_context import MIN_COHORT_MEMBERS

CONTRACT_VERSION = "current_research_valuation_context/v1"
PE_TTM = "P/E_TTM"
PS_TTM = "P/S_TTM"
PB = "P/B"
PB_CURRENT_RESEARCH = "P/B_CURRENT_RESEARCH"
PE_EXISTING = "P/E"
PS_EXISTING = "P/S"
EV_EBITDA = "EV/EBITDA"
EV_SALES = "EV/Sales"
MARKET_CAP = "market_cap"
# MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1: a second, genuinely distinct
# EV/EBITDA method identity sourced from `market_wide_calculation_readiness.py` (sign-aware,
# cross-statement-coherent, currency/scale/period-compatible by construction -- CORE_VALUATION_
# METHOD_COVERAGE_AND_CONSISTENCY_V1 activated that engine but deliberately did not wire it into
# any live product). `EV_EBITDA` above stays untouched: its own upstream (`market_wide_current_
# valuation_input_scaleout`) structurally never retains an exact EBITDA figure, so it is always
# INPUT_BLOCKED by construction -- never collapsed into or relabelled as this new method.
EV_EBITDA_CALC_READY = "EV/EBITDA_CALC_READY"
TTM_METHODS = (PE_TTM, PS_TTM)
EXISTING_MULTIPLES = (PE_EXISTING, PS_EXISTING, PB, EV_SALES, EV_EBITDA)
CALCULATION_READINESS_METHODS = (EV_EBITDA_CALC_READY,)
RELATIVE_METHODS = (PE_TTM, PS_TTM, PE_EXISTING, PS_EXISTING, PB, PB_CURRENT_RESEARCH, EV_SALES, EV_EBITDA, EV_EBITDA_CALC_READY)
APPLICABLE = "APPLICABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
INPUT_BLOCKED = "INPUT_BLOCKED"
EXACT_OR_QUALIFIED = "EXACT_OR_QUALIFIED"
CURRENT_SHARE_RESEARCH_PROXY = "CURRENT_SHARE_RESEARCH_PROXY"
PROVIDER_VALUATION_PROXY = "PROVIDER_VALUATION_PROXY"
SHARE_UNAVAILABLE = "UNAVAILABLE"
NEGATIVE_EARNINGS = "NEGATIVE_EARNINGS"
ZERO_OR_NEAR_ZERO_EARNINGS = "ZERO_OR_NEAR_ZERO_EARNINGS"
PE_NOT_MEANINGFUL = "PE_NOT_MEANINGFUL"
TURNAROUND_CONTEXT = "TURNAROUND_CONTEXT"
READY_STATUSES = frozenset({"READY_RESEARCH", "READY_RESEARCH_PROXY", "PARTIAL_RESEARCH", "RESEARCH_USABLE", "READY"})
IMPLIED_EXPECTATIONS_UNAVAILABLE = "IMPLIED_EXPECTATIONS_UNAVAILABLE"
# WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: availability and authority
# are orthogonal. AVAILABLE_QUALIFIED / AVAILABLE_REFERENCE_ONLY / NOT_AVAILABLE describe
# whether a genuine retained value exists and, if so, whether it is qualified for the stronger
# (peer-relative) use -- never a replacement for `status`/`applicability`, only an additive
# display-oriented lens over them.
AVAILABLE_QUALIFIED = "AVAILABLE_QUALIFIED"
AVAILABLE_REFERENCE_ONLY = "AVAILABLE_REFERENCE_ONLY"
NOT_AVAILABLE = "NOT_AVAILABLE"


def share_basis_class(share: Mapping[str, Any] | None) -> str:
    """Map existing share-authority vocabulary onto the opportunity share-basis contract."""
    share = share or {}
    authority = str(share.get("authority") or "")
    if share.get("authoritative_current_market_cap_eligible") or authority in {
        "qualified_official", "qualified_current_common_shares",
    }:
        return EXACT_OR_QUALIFIED
    if share.get("research_proxy_eligible") or authority in RESEARCH_SHARE_AUTHORITIES:
        return CURRENT_SHARE_RESEARCH_PROXY
    if authority in {"", "unavailable", "unknown"} or share.get("status") in {None, "UNAVAILABLE"}:
        return SHARE_UNAVAILABLE
    return PROVIDER_VALUATION_PROXY


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _feature(record: Mapping[str, Any] | None, feature_id: str) -> Mapping[str, Any]:
    context = (record or {}).get("fundamental_feature_context") or {}
    features = context.get("current_features") or (record or {}).get("features") or {}
    item = features.get(feature_id) or {}
    return item if isinstance(item, Mapping) else {}


def _known_basis(value: Any) -> bool:
    """Delegates to the shared contract so "unknown" spellings are recognized in one place."""
    return basis_contract.known(value)


def _ttm_monetary_basis(*, currency: Any, scale: Any, feature_id: str, provider: Any) -> dict[str, Any]:
    """TTM flow basis is never official and lacks retained unit-scale proof.

    The VCI balance-sheet stock verdict does not qualify income-statement flows.
    Retained TTM inputs remain UNKNOWN without their own monetary proof.
    """
    return basis_contract.build_basis(
        currency=currency, scale=scale,
        basis_source=f"financial_analysis_engine_v2 feature={feature_id!r} provider={provider!r}",
    )


def _qualified_ttm(feature_id: str, record: Mapping[str, Any] | None, context_identity: str | None) -> dict[str, Any] | None:
    feature = ((record or {}).get("features") or {}).get(feature_id) or {}
    if feature.get("fitness") != "READY" or not _numeric(feature.get("value")):
        return None
    lineage = list(feature.get("provider_source_provenance") or [])
    provider = lineage[0].get("provider") if lineage else None
    basis = _ttm_monetary_basis(currency=feature.get("currency"), scale=feature.get("scale"),
                                feature_id=feature_id, provider=provider)
    return {"status": "READY", "value": feature.get("value"), "method": feature.get("method"),
            "input_periods": list(feature.get("period_identity") or []), "compatibility_class": "QUALIFIED_FINANCIAL_ANALYSIS_V2",
            "blocker_reason_codes": list(feature.get("reason_codes") or []), "ttm_input_source": "NEW_QUALIFIED_TTM_SELECTED",
            "ttm_source_context_identity": context_identity, "ttm_feature_id": feature_id,
            "ttm_provider": provider, "ttm_currency": basis["currency"], "ttm_scale": basis["native_scale"],
            "ttm_fitness": feature.get("fitness"), "ttm_source_conflict": False, "ttm_monetary_basis": basis}


def _select_ttm(*, old: Mapping[str, Any], qualified: Mapping[str, Any] | None) -> dict[str, Any]:
    old_ready = old.get("status") in READY_STATUSES and _numeric(old.get("value"))
    if qualified:
        conflict = old_ready and float(old["value"]) != float(qualified["value"])
        result = dict(qualified)
        result["ttm_input_source"] = "BOTH_PRESENT_CONFLICT" if conflict else ("BOTH_PRESENT_NEW_SELECTED" if old_ready else "NEW_QUALIFIED_TTM_SELECTED")
        result["ttm_source_conflict"] = conflict
        result["old_ttm_value"] = old.get("value") if old_ready else None
        return result
    if old_ready:
        old_provider = ((old.get("provider_source_lineage") or [{}])[0]).get("provider")
        old_basis = _ttm_monetary_basis(currency=old.get("currency"), scale=old.get("scale"),
                                        feature_id=str(old.get("feature_id")), provider=old_provider)
        return {**dict(old), "ttm_input_source": "OLD_TTM_FALLBACK_SELECTED", "ttm_source_context_identity": None,
                "ttm_feature_id": old.get("feature_id"), "ttm_provider": old_provider,
                "ttm_currency": old_basis["currency"], "ttm_scale": old_basis["native_scale"], "ttm_fitness": old.get("status"),
                "ttm_source_conflict": False, "ttm_monetary_basis": old_basis}
    no_ttm_basis = _ttm_monetary_basis(currency=None, scale=None, feature_id=str(old.get("feature_id")), provider=None)
    return {**dict(old), "ttm_input_source": "NO_TTM", "ttm_source_context_identity": None,
            "ttm_feature_id": old.get("feature_id"), "ttm_provider": None, "ttm_currency": None,
            "ttm_scale": None, "ttm_fitness": old.get("status"), "ttm_source_conflict": False,
            "ttm_monetary_basis": no_ttm_basis}


def _market_cap_basis_envelope(market_cap: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct the market_cap metric's monetary basis from its own flat fields.

    Prefers the richer `monetary_basis` envelope `market_wide_current_valuation_input_
    scaleout.py` attaches when present; falls back to the flat `currency`/`scale` pair
    (and, absent even those, UNKNOWN) so a caller supplying a minimal/synthetic
    market_cap dict -- as tests do -- is judged on exactly the fields it declares.
    """
    envelope = market_cap.get("monetary_basis")
    if isinstance(envelope, Mapping) and envelope.get("basis_status") in basis_contract.BASIS_STATUSES:
        return dict(envelope)
    return basis_contract.build_basis(
        currency=market_cap.get("currency"), scale=market_cap.get("scale"),
        basis_status=market_cap.get("monetary_basis_status"),
        basis_source=str(market_cap.get("monetary_basis_source") or "market_cap.currency/scale"),
    )


def _monetary_basis_compatible(ttm: Mapping[str, Any], market_cap: Mapping[str, Any]) -> tuple[bool, str | None]:
    ttm_basis = ttm.get("ttm_monetary_basis")
    if not isinstance(ttm_basis, Mapping):
        ttm_basis = basis_contract.build_basis(
            currency=ttm.get("ttm_currency"), scale=ttm.get("ttm_scale"),
            basis_source=f"ttm_feature={ttm.get('ttm_feature_id')!r}",
        )
    return basis_contract.compatible(ttm_basis, _market_cap_basis_envelope(market_cap))


def _entity(feature_record: Mapping[str, Any] | None, valuation_record: Mapping[str, Any] | None,
            entity_applicability: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Resolve method applicability's entity class from every supplied surface.

    The upstream valuation lane's class comes from its own narrower issuer panel, so it is often
    ``unknown`` for issuers the governed current-state authority already classifies. Any known
    class may resolve; two known classes that disagree fail closed as a conflict.
    """
    upstream = (valuation_record or {}).get("entity_class") or (valuation_record or {}).get("entity_type")
    feature = (feature_record or {}).get("entity_class") or (feature_record or {}).get("entity_type")
    governed_status = (entity_applicability or {}).get("applicability_status")
    governed = (entity_applicability or {}).get("entity_class") if governed_status == "RESOLVED" else None
    known = {
        source: value for source, value in (
            ("UPSTREAM_VALUATION_LANE", upstream), ("FEATURE_STORE_RECORD", feature),
            ("GOVERNED_CURRENT_STATE_AUTHORITY", governed),
        ) if isinstance(value, str) and value and value != "unknown"
    }
    detail = {
        "upstream_valuation_lane_entity_class": upstream if isinstance(upstream, str) and upstream else "unknown",
        "governed_applicability_status": governed_status or "NOT_SUPPLIED",
        "governed_authority_tier": (entity_applicability or {}).get("authority_tier"),
        "authority_scope": "CURRENT_STATE_ONLY", "historical_pit_authority": "NOT_ESTABLISHED",
    }
    if governed_status == "CONFLICT" or len(set(known.values())) > 1:
        return "unknown", {**detail, "status": "CONFLICT", "sources": sorted(known), "reason_codes": ["ENTITY_CLASS_CONFLICT"]}
    if known:
        return next(iter(known.values())), {**detail, "status": "RESOLVED", "sources": sorted(known), "reason_codes": []}
    return "unknown", {**detail, "status": "UNRESOLVED", "sources": [], "reason_codes": ["ENTITY_CLASS_UNRESOLVED"]}


def _method_applicability(entity: str, method_id: str) -> str:
    if method_id == MARKET_CAP:
        mapped = _applicability(entity, "market_cap")
    elif method_id in {PE_TTM, PE_EXISTING}:
        mapped = _applicability(entity, "P/E")
    elif method_id in {PS_TTM, PS_EXISTING}:
        mapped = _applicability(entity, "P/S")
    elif method_id in {PB, PB_CURRENT_RESEARCH}:
        mapped = _applicability(entity, "P/B")
    elif method_id == EV_EBITDA:
        mapped = _applicability(entity, "EV/EBITDA")
    elif method_id == EV_SALES:
        mapped = _applicability(entity, "EV/Sales")
    else:
        mapped = "BLOCKED_ENTITY_CLASS_UNKNOWN"
    if mapped == "NOT_APPLICABLE":
        return NOT_APPLICABLE
    if mapped in {"BLOCKED_ENTITY_CLASS_UNKNOWN"}:
        return INPUT_BLOCKED
    return APPLICABLE


def _earnings_state(ttm: Mapping[str, Any], profit: Mapping[str, Any]) -> str | None:
    value = ttm.get("value") if ttm.get("status") in READY_STATUSES else None
    if _numeric(value) and value < 0:
        return NEGATIVE_EARNINGS
    if _numeric(value) and value == 0:
        return ZERO_OR_NEAR_ZERO_EARNINGS
    state = profit.get("categorical_state")
    if state == "LOSS_MAKING":
        return TURNAROUND_CONTEXT
    if state == "BREAK_EVEN":
        return ZERO_OR_NEAR_ZERO_EARNINGS
    return None


def _method_shell(method_id: str, *, applicability: str, status: str, value: Any = None,
                  blockers: Sequence[str] = (), extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "method_id": method_id, "applicability": applicability, "status": status,
        "value": value if status in {"RESEARCH_USABLE", "READY"} else None,
        "blocker_reason_codes": list(blockers),
        "is_actionable": False, "target_price": None, "fair_value": None, "probability": None,
    }
    if extra:
        row.update(dict(extra))
    return row


def _ttm_method(*, method_id: str, metric: str, ttm: Mapping[str, Any], market_cap: Mapping[str, Any],
                share_class: str, entity: str, earnings_state: str | None) -> dict[str, Any]:
    applicability = _method_applicability(entity, method_id)
    extra = {
        "period_basis": "TTM_SUM",
        "ttm_method": ttm.get("method"),
        "ttm_status": ttm.get("status"),
        "ttm_compatibility_class": ttm.get("compatibility_class"),
        "input_periods": list(ttm.get("input_periods") or []),
        "ttm_periods": list(ttm.get("input_periods") or []),
        "share_basis": share_class,
        "numerator": "RESEARCH_USABLE_MARKET_CAP",
        "denominator_feature": metric,
        "ttm_input_source": ttm.get("ttm_input_source"), "ttm_source_context_identity": ttm.get("ttm_source_context_identity"),
        "ttm_feature_id": ttm.get("ttm_feature_id"), "ttm_provider": ttm.get("ttm_provider"),
        "ttm_currency": ttm.get("ttm_currency"), "ttm_scale": ttm.get("ttm_scale"), "ttm_fitness": ttm.get("ttm_fitness"),
        "ttm_source_conflict": bool(ttm.get("ttm_source_conflict")),
        "ttm_monetary_basis": ttm.get("ttm_monetary_basis"),
        "market_cap_monetary_basis": _market_cap_basis_envelope(market_cap),
    }
    if applicability == NOT_APPLICABLE:
        return _method_shell(method_id, applicability=applicability, status=NOT_APPLICABLE,
                             blockers=["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"], extra=extra)
    ttm_ready = ttm.get("status") in READY_STATUSES and _numeric(ttm.get("value"))
    if method_id == PE_TTM and ttm_ready and ttm["value"] <= 0:
        state = NEGATIVE_EARNINGS if ttm["value"] < 0 else ZERO_OR_NEAR_ZERO_EARNINGS
        return _method_shell(method_id, applicability=applicability, status=PE_NOT_MEANINGFUL,
                             blockers=[state, PE_NOT_MEANINGFUL], extra={**extra, "earnings_state": state})
    if method_id == PE_TTM and not ttm_ready and earnings_state in {NEGATIVE_EARNINGS, ZERO_OR_NEAR_ZERO_EARNINGS, TURNAROUND_CONTEXT}:
        return _method_shell(method_id, applicability=applicability, status=PE_NOT_MEANINGFUL,
                             blockers=[earnings_state, PE_NOT_MEANINGFUL, *(ttm.get("blocker_reason_codes") or [])],
                             extra={**extra, "earnings_state": earnings_state})
    if ttm.get("status") not in READY_STATUSES or not _numeric(ttm.get("value")):
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=list(ttm.get("blocker_reason_codes") or ["TTM_INPUT_UNAVAILABLE"]), extra=extra)
    if market_cap.get("status") not in {"RESEARCH_USABLE", "READY"} or not _numeric(market_cap.get("value")):
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["MARKET_CAP_RESEARCH_INPUT_UNAVAILABLE"], extra=extra)
    if share_class == SHARE_UNAVAILABLE:
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["SHARE_BASIS_UNAVAILABLE"], extra=extra)
    basis_ok, basis_blocker = _monetary_basis_compatible(ttm, market_cap)
    if not basis_ok:
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=[basis_blocker], extra=extra)
    denominator = ttm["value"]
    if method_id == PE_TTM and denominator <= 0:
        state = NEGATIVE_EARNINGS if denominator < 0 else ZERO_OR_NEAR_ZERO_EARNINGS
        return _method_shell(method_id, applicability=applicability, status=PE_NOT_MEANINGFUL,
                             blockers=[state, PE_NOT_MEANINGFUL], extra={**extra, "earnings_state": state})
    if denominator == 0:
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["ZERO_DENOMINATOR"], extra=extra)
    # Normalize each side through its own proven multiplier before dividing (a no-op today,
    # since no multiplier is ever proven -- see `_ttm_monetary_basis`/`_market_cap_monetary_
    # basis` -- but correct once one is: two quantities that share one unproven native scale
    # already divide validly without it, per `monetary_basis_contract.normalize_value`).
    normalized_cap = basis_contract.normalize_value(market_cap["value"], _market_cap_basis_envelope(market_cap))
    normalized_denominator = basis_contract.normalize_value(denominator, ttm.get("ttm_monetary_basis"))
    return _method_shell(
        method_id, applicability=applicability, status="RESEARCH_USABLE",
        value=normalized_cap / normalized_denominator,
        extra={**extra, "formula": "research_usable_market_cap / compatible_ttm_sum",
               "limitations": ["CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE", "NOT_FOR_TARGET_PRICE",
                               "SHARE_BASIS=" + share_class]},
    )


def _existing_method(method_id: str, metric: Mapping[str, Any], *, entity: str, share_class: str) -> dict[str, Any]:
    applicability = _method_applicability(entity, method_id)
    extra = {
        "period_basis": metric.get("financial_period") or "EXISTING_CURRENT_VALUATION_METHOD",
        "share_basis": share_class,
        "share_identity": metric.get("share_identity"),
        "p3f_method_status": metric.get("p3f_method_status") or metric.get("status"),
        "formula": metric.get("formula"),
        "source_status": metric.get("status"),
        "financial_inputs": metric.get("financial_inputs"),
        "price_representation": metric.get("price_representation"),
        "monetary_compatibility": metric.get("monetary_compatibility"),
        "price_session": metric.get("price_session"),
        "monetary_basis": metric.get("monetary_basis"),
    }
    source_status = metric.get("status")
    if applicability == NOT_APPLICABLE or source_status == "NOT_APPLICABLE":
        return _method_shell(method_id, applicability=NOT_APPLICABLE, status=NOT_APPLICABLE,
                             blockers=list(metric.get("blocked_reasons") or ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]), extra=extra)
    if source_status in {"RESEARCH_USABLE", "READY"} and _numeric(metric.get("value")):
        return _method_shell(method_id, applicability=APPLICABLE, status="RESEARCH_USABLE" if source_status != "READY" else "READY",
                             value=metric["value"], extra=extra)
    return _method_shell(method_id, applicability=applicability if applicability != NOT_APPLICABLE else INPUT_BLOCKED,
                         status=INPUT_BLOCKED, blockers=list(metric.get("blocked_reasons") or ["VALUATION_INPUT_BLOCKED"]), extra=extra)


def _ev_ebitda(entity: str, existing: Mapping[str, Any] | None) -> dict[str, Any]:
    applicability = _method_applicability(entity, EV_EBITDA)
    extra = {"period_basis": "EXISTING_CURRENT_VALUATION_METHOD", "required_semantics": "COMPATIBLE_ENTERPRISE_VALUE_AND_EXACT_EBITDA"}
    if applicability == NOT_APPLICABLE:
        return _method_shell(EV_EBITDA, applicability=NOT_APPLICABLE, status=NOT_APPLICABLE,
                             blockers=["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"], extra=extra)
    blockers = list((existing or {}).get("blocked_reasons") or ["EXACT_EBITDA_COMPARABILITY_NOT_RETAINED"])
    if "EXACT_EBITDA_COMPARABILITY_NOT_RETAINED" not in blockers:
        blockers.append("EXACT_EBITDA_COMPARABILITY_NOT_RETAINED")
    if existing and existing.get("status") in {"RESEARCH_USABLE", "READY"} and _numeric(existing.get("value")):
        return _method_shell(EV_EBITDA, applicability=APPLICABLE, status=existing["status"], value=existing["value"], extra=extra)
    return _method_shell(EV_EBITDA, applicability=APPLICABLE, status=INPUT_BLOCKED, blockers=blockers, extra=extra)


def _latest_readiness_period(calculation_readiness_record: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    periods = (calculation_readiness_record or {}).get("calculation_readiness")
    if not isinstance(periods, list) or not periods:
        return None
    latest = periods[-1]
    return latest if isinstance(latest, Mapping) else None


def readiness_period_blocker(reporting_period: Any, decision_session: str | None) -> str | None:
    """Temporal fitness of a readiness denominator's reporting period for a decision session.

    A current enterprise value divided by a fundamental from years earlier is not a current
    valuation. The bound is the one the operational fundamental bridge already applies
    (``operational_fundamental_context_integration.MAX_COMPLETED_QUARTER_LAG``); a period that ends
    after the decision session is never admitted. ``None`` session keeps the legacy (ungated) call.
    """
    if not decision_session:
        return None
    lag, _, blocker = completed_quarter_lag(reporting_period, decision_session)
    if blocker == "FINANCIAL_SOURCE_PERIOD_UNRESOLVED":
        return "CALCULATION_READINESS_PERIOD_UNRESOLVED"
    if blocker:
        return "CALCULATION_READINESS_PERIOD_AFTER_DECISION_SESSION"
    if lag > MAX_COMPLETED_QUARTER_LAG:
        return "CALCULATION_READINESS_PERIOD_STALE"
    return None


def _calculation_readiness_method(
    *, capability: str, method_id: str, applicability_method_id: str, entity: str,
    calculation_readiness_record: Mapping[str, Any] | None, decision_session: str | None = None,
) -> dict[str, Any]:
    """A method sourced directly from `market_wide_calculation_readiness.py`'s per-period
    verdict -- never re-deriving the formula, only projecting its already-computed value.

    Reuses this module's own `_method_applicability` (same metric concept, same entity gate
    as the pre-existing `EV_EBITDA` method) rather than a second, independent entity-class
    call, so the two EV/EBITDA method identities can never silently disagree on WHICH entities
    the metric applies to -- only on whether a usable number exists for one that does.

    The engine's denominator is ONE reporting period (quarterly payloads, never annualised --
    multiplying a quarter would manufacture a TTM figure), so a usable value is labelled as a
    single-period ratio: comparable only within a same-period peer cohort, not to a TTM multiple.
    """
    applicability = _method_applicability(entity, applicability_method_id)
    period = _latest_readiness_period(calculation_readiness_record)
    extra = {
        "period_basis": period.get("reporting_period") if period else None,
        "source": "market_wide_calculation_readiness/v1",
        "required_semantics": "SIGN_AWARE_CROSS_STATEMENT_COHERENT_CALCULATION_READINESS",
        "denominator_period_semantics": "SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED",
    }
    if applicability == NOT_APPLICABLE:
        return _method_shell(method_id, applicability=NOT_APPLICABLE, status=NOT_APPLICABLE,
                             blockers=["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"], extra=extra)
    verdict = period.get(capability) if period else None
    if not isinstance(verdict, Mapping):
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["CALCULATION_READINESS_CONTEXT_UNAVAILABLE"], extra=extra)
    extra["formula"] = verdict.get("formula")
    if verdict.get("readiness") == "not_applicable":
        return _method_shell(method_id, applicability=NOT_APPLICABLE, status=NOT_APPLICABLE,
                             blockers=list(verdict.get("blocked_by") or ["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"]), extra=extra)
    if verdict.get("readiness") != "ready" or not _numeric(verdict.get("value")):
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=list(verdict.get("blocked_by") or ["CALCULATION_READINESS_NOT_READY"]), extra=extra)
    period_blocker = readiness_period_blocker(extra["period_basis"], decision_session)
    if period_blocker:
        return _method_shell(method_id, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=[period_blocker], extra={**extra, "decision_session": decision_session})
    return _method_shell(
        method_id, applicability=applicability, status="RESEARCH_USABLE", value=verdict["value"],
        extra={**extra, "readiness_status": verdict.get("status"),
               # Own-history is explicitly not available for this method: the upstream
               # canonical_daily_financial_v2_materialization.build_calculation_readiness_context
               # pipeline retains only the LATEST reporting period per ticker (by
               # canonical_financial_bundle_section.build_section's own deliberate "latest period
               # only" contract), so no multi-period series exists here to compute a percentile
               # from. Reported explicitly rather than silently omitted.
               "own_history_status": "UNAVAILABLE_LATEST_PERIOD_ONLY_PIPELINE",
               "limitations": ["CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE", "NOT_FOR_TARGET_PRICE",
                               "PROVIDER_REPORTED_PRICE_BASIS_NOT_INDEPENDENTLY_VERIFIED",
                               "OWN_HISTORY_UNAVAILABLE_LATEST_PERIOD_ONLY_PIPELINE",
                               "SINGLE_REPORTING_PERIOD_DENOMINATOR_NOT_TTM"]},
    )


_READINESS_EQUIVALENTS = {
    PE_EXISTING: "pe",
    PB: "pb",
    MARKET_CAP: "market_capitalisation",
    EV_EBITDA: "ev_ebitda",
}


def _calculation_readiness_reconciliation(
    methods: Mapping[str, Mapping[str, Any]], readiness_record: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """State exactly whether two existing valuation methods are comparable.

    The readiness engine and the retained-current valuation lane may use different
    reporting periods.  A numerical comparison is made only when both name the same
    period and are ready; otherwise the reason is retained rather than silently
    preferring either figure.
    """
    readiness_record = readiness_record or {}
    periods = readiness_record.get("calculation_readiness") or []
    period = periods[-1] if isinstance(periods, list) and periods else {}
    out: dict[str, dict[str, Any]] = {}
    for method_id, current in methods.items():
        readiness_metric = _READINESS_EQUIVALENTS.get(method_id)
        base = {
            "current_research_method_id": method_id,
            "readiness_method_id": readiness_metric,
            "current_research_period": current.get("period_basis"),
            "readiness_reporting_period": period.get("reporting_period") if isinstance(period, Mapping) else None,
            "current_research_value": current.get("value"),
        }
        if readiness_metric is None:
            out[method_id] = {
                **base, "comparison_status": "NOT_SEMANTICALLY_EQUIVALENT",
                "reason": "NO_EQUIVALENT_METHOD_IN_CALCULATION_READINESS_ENGINE",
            }
            continue
        engine = period.get(readiness_metric) if isinstance(period, Mapping) else None
        if not isinstance(engine, Mapping):
            out[method_id] = {
                **base, "comparison_status": "READINESS_CONTEXT_UNAVAILABLE",
                "reason": readiness_record.get("reason") or "READINESS_METHOD_NOT_RETAINED",
            }
            continue
        base.update({
            "readiness_value": engine.get("value"),
            "readiness_state": engine.get("readiness"),
            "readiness_status": engine.get("status"),
            "readiness_blockers": list(engine.get("blocked_by") or []),
        })
        if current.get("status") not in {"RESEARCH_USABLE", "READY"} or not _numeric(current.get("value")):
            out[method_id] = {**base, "comparison_status": "CURRENT_RESEARCH_METHOD_NOT_USABLE",
                              "reason": "CURRENT_RESEARCH_METHOD_BLOCKED_OR_NOT_MEANINGFUL"}
        elif engine.get("readiness") != "ready" or not _numeric(engine.get("value")):
            out[method_id] = {**base, "comparison_status": "READINESS_METHOD_NOT_READY",
                              "reason": engine.get("reason") or "READINESS_METHOD_BLOCKED"}
        elif str(current.get("period_basis")) != str(period.get("reporting_period")):
            out[method_id] = {**base, "comparison_status": "NOT_COMPARABLE_DIFFERENT_REPORTING_PERIOD",
                              "reason": "METHODS_USE_DIFFERENT_RETAINED_REPORTING_PERIODS"}
        else:
            delta = float(current["value"]) - float(engine["value"])
            tolerance = 1e-6 * max(1.0, abs(float(current["value"])), abs(float(engine["value"])))
            out[method_id] = {
                **base,
                "comparison_status": "AGREES_WITHIN_REPRESENTATION_TOLERANCE" if abs(delta) <= tolerance else "MISMATCH_EXPLICIT_REVIEW_REQUIRED",
                "reason": "SAME_PERIOD_DETERMINISTIC_REPRESENTATION_COMPARISON",
                "value_delta": delta,
                "tolerance": tolerance,
            }
    return out


def _official_equity_row(official_equity_facts: Sequence[Mapping[str, Any]] | None, ticker: str) -> Mapping[str, Any] | None:
    """Newest qualified official equity for the same issuer; FY aliases to Q4, H1 to Q2."""
    best = None
    for fact in official_equity_facts or ():
        if str(fact.get("ticker") or "").upper() != ticker:
            continue
        if fact.get("canonical_metric") not in {"shareholders_equity", "total_equity"}:
            continue
        if fact.get("qualification_state") != "QUALIFIED":
            continue
        if fact.get("statement_scope") not in (None, "consolidated"):
            continue
        if fact.get("currency") != "VND" or not fact.get("unit_scale"):
            continue
        if best is None or str(fact.get("knowledge_available_at") or "") > str(best.get("knowledge_available_at") or ""):
            best = fact
    return best


def _book_value_method(
    *, ticker: str, entity: str, share_class: str, market_cap: Mapping[str, Any],
    equity_rows: Sequence[Mapping[str, Any]] | None, decision_session: str | None,
    verdict: Mapping[str, Any] | None,
    official_equity_facts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Current-research P/B using a pinned VCI unit verdict and one typed equity stock."""
    applicability = _method_applicability(entity, PB_CURRENT_RESEARCH)
    extra: dict[str, Any] = {"share_basis": share_class,
                             "equity_definition": "TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT",
                             "period_basis": "POINT_IN_TIME_BALANCE_SHEET",
                             "source": "FINANCIAL_V2_PINNED_SEMANTIC_ROWS",
                             "monetary_basis_verdict_identity": (verdict or {}).get("artifact_identity"),
                             "market_cap_monetary_basis": _market_cap_basis_envelope(market_cap)}
    if applicability == NOT_APPLICABLE:
        return _method_shell(PB_CURRENT_RESEARCH, applicability=NOT_APPLICABLE, status=NOT_APPLICABLE,
                             blockers=["SECTOR_ENTITY_METHOD_NOT_SUPPORTED"], extra=extra)
    if applicability == INPUT_BLOCKED:
        return _method_shell(PB_CURRENT_RESEARCH, applicability=INPUT_BLOCKED, status=INPUT_BLOCKED,
                             blockers=["ENTITY_CLASS_UNRESOLVED"], extra=extra)
    contract = ((verdict or {}).get("semantic_basis_registry") or {}).get("contracts", {}).get("VCI:balance_sheet") or {}
    if (contract.get("verdict") != "PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED"
            or contract.get("currency") != "VND" or contract.get("scale") != "units"
            or contract.get("multiplier_to_vnd") != 1):
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["MONETARY_BASIS_VERDICT_UNAVAILABLE"], extra=extra)
    if market_cap.get("status") not in {"RESEARCH_USABLE", "READY"} or not _numeric(market_cap.get("value")):
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["MARKET_CAP_RESEARCH_INPUT_UNAVAILABLE"], extra=extra)
    if share_class == SHARE_UNAVAILABLE:
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["SHARE_BASIS_UNAVAILABLE"], extra=extra)
    if not decision_session:
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["BOOK_EQUITY_DECISION_SESSION_UNAVAILABLE"], extra=extra)
    day = date.fromisoformat(decision_session[:10])
    quarter = (day.month - 1) // 3 + 1
    session_index = day.year * 4 + quarter
    candidates: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in equity_rows or ():
        period = str(row.get("native_period_label") or "")
        if (row.get("canonical_metric") == "shareholders_equity"
                and (row.get("source_lineage") or {}).get("provider") == "VCI"
                and row.get("period_semantic_state") == "POINT_IN_TIME_BALANCE_SHEET"
                and re.fullmatch(r"\d{4}-Q[1-4]", period)
                and row.get("period_end") and str(row["period_end"]) <= decision_session[:10]):
            candidates[period].append(row)
    if not candidates:
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=["BOOK_EQUITY_UNAVAILABLE"], extra=extra)
    chosen = None
    chosen_period = None
    latest_period = max(candidates)
    for period in sorted(candidates, reverse=True):
        if readiness_period_blocker(period, decision_session):
            continue
        rows = candidates[period]
        usable = [row for row in rows if (row.get("source_status") == "provider_reported"
                  and row.get("lineage_complete") is True and not row.get("source_conflicts")
                  and _numeric(row.get("reported_value"))
                  and (row.get("source_lineage") or {}).get("source_sha256")
                  and (row.get("source_lineage") or {}).get("source_file"))]
        if len(rows) == 1 and len(usable) == 1:
            chosen, chosen_period = usable[0], period
            break
    if chosen is None:
        reason = "BOOK_EQUITY_PERIOD_STALE" if all(readiness_period_blocker(period, decision_session)
                                                     for period in candidates) else "BOOK_EQUITY_SOURCE_CONFLICT_OR_INCOMPLETE"
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=[reason], extra=extra)
    lag = session_index - (int(chosen_period[:4]) * 4 + int(chosen_period[-1]))
    equity_basis = basis_contract.build_basis(
        currency="VND", scale="units", basis_status=basis_contract.RESEARCH_CONTRACT_QUALIFIED,
        multiplier_to_vnd=1, normalized_unit="VND",
        basis_source=f"{verdict['artifact_identity']}:VCI:balance_sheet")
    extra.update({"book_period": chosen_period, "book_period_lag_quarters": lag,
                  "input_periods": [chosen_period], "statement_scope": chosen.get("statement_scope"),
                  "equity_monetary_basis": equity_basis,
                  "equity_lineage": dict(chosen.get("source_lineage") or {}),
                  "equity_source_status": chosen.get("source_status"),
                  "ttm_compatibility_class": f"VCI_TOTAL_OWNERS_EQUITY_CURRENT_RESEARCH:{chosen.get('statement_scope')}"})
    warning = ["LATEST_BALANCE_SHEET_PERIOD_UNUSABLE_EARLIER_PERIOD_USED"] if chosen_period != latest_period else []
    if chosen["reported_value"] <= 0:
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status="PB_NOT_MEANINGFUL",
                             blockers=["NON_POSITIVE_BOOK_EQUITY"], extra={**extra, "warnings": warning})
    official = _official_equity_row(official_equity_facts, ticker)
    equity_value = chosen["reported_value"]
    formula = "research_usable_market_cap / VCI_total_owners_equity"
    if official is not None:
        from official_legacy_precedence import EXACT_MATCH, TRUE_CONFLICT, compare_official_and_legacy
        official_period = str(official.get("reporting_period") or "")
        legacy_period = chosen_period
        if official_period.isdigit():
            official_period_q = f"{official_period}-Q4"
        elif official_period == "2026-H1":
            official_period_q = "2026-Q2"
        else:
            official_period_q = official_period
        compared = compare_official_and_legacy(
            {**dict(official), "statement_family": "balance_sheet",
             "normalized_value": official.get("normalized_value") or official.get("value"),
             "already_normalized": True},
            {"canonical_metric": "shareholders_equity", "reporting_period": legacy_period,
             "statement_family": "balance_sheet", "statement_scope": chosen.get("statement_scope"),
             "normalized_value": chosen["reported_value"], "already_normalized": True},
        )
        extra["official_legacy_precedence"] = compared["status"]
        extra["official_equity_period"] = official.get("reporting_period")
        extra["legacy_equity_visible"] = True
        extra["legacy_source_status"] = "provider_reported"
        if compared["status"] == TRUE_CONFLICT and official_period_q == chosen_period:
            return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                                 blockers=["OFFICIAL_LEGACY_TRUE_CONFLICT"], extra={**extra, "warnings": warning})
        if compared["status"] == EXACT_MATCH or official_period_q == chosen_period:
            official_value = official.get("normalized_value") or official.get("value")
            if _numeric(official_value) and official_value > 0:
                equity_value = official_value
                formula = "research_usable_market_cap / official_total_owners_equity"
                extra["source"] = "OFFICIAL_QUALIFIED_EQUITY"
                extra["equity_source_status"] = "qualified"
                extra["equity_lineage"] = {
                    "provider": "official_issuer_ir",
                    "document_sha256": official.get("document_sha256"),
                    "source_sha256": official.get("document_sha256"),
                    "source_file": official.get("source_locator"),
                }
    compatible, blocker = basis_contract.compatible(equity_basis, _market_cap_basis_envelope(market_cap))
    if not compatible:
        return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status=INPUT_BLOCKED,
                             blockers=[blocker or "MONETARY_BASIS_INCOMPATIBLE"], extra=extra)
    exact_anchor = any(anchor.get("ticker") == ticker and anchor.get("canonical_metric") == "shareholders_equity"
                       and anchor.get("reporting_period") == chosen_period
                       and anchor.get("classification") == "EXACT_OR_DISPLAY_ROUNDED"
                       for anchor in ((verdict.get("source_reconciliation") or {}).get("shapes") or {}).get("('VCI', 'balance_sheet')", {}).get("anchors", []))
    limitations = ["CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE", "NOT_FOR_TARGET_PRICE",
                   "NCI_NOT_DEDUCTED", "SHARE_BASIS=" + share_class]
    if not exact_anchor and formula.endswith("VCI_total_owners_equity"):
        limitations.append("PROVIDER_EQUITY_VALUE_NOT_INDEPENDENTLY_RECONCILED")
    value = (basis_contract.normalize_value(market_cap["value"], _market_cap_basis_envelope(market_cap)) /
             basis_contract.normalize_value(equity_value, equity_basis))
    return _method_shell(PB_CURRENT_RESEARCH, applicability=applicability, status="RESEARCH_USABLE",
                         value=value, extra={**extra, "formula": formula,
                                             "warnings": warning, "limitations": limitations})


def evaluate_ticker_valuation(*, ticker: str, feature_record: Mapping[str, Any] | None,
                              valuation_record: Mapping[str, Any] | None,
                              financial_analysis_record: Mapping[str, Any] | None = None,
                              financial_analysis_context_identity: str | None = None,
                              calculation_readiness_record: Mapping[str, Any] | None = None,
                              entity_applicability: Mapping[str, Any] | None = None,
                              decision_session: str | None = None,
                              book_equity_rows: Sequence[Mapping[str, Any]] | None = None,
                              monetary_basis_verdict: Mapping[str, Any] | None = None,
                              official_equity_facts: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    entity, entity_detail = _entity(feature_record, valuation_record, entity_applicability)
    share = (valuation_record or {}).get("share_basis_input") or {}
    share_class = share_basis_class(share)
    metrics = (valuation_record or {}).get("metrics") or {}
    market_cap = dict(metrics.get(MARKET_CAP) or {})
    if valuation_record and market_cap and valuation_record.get("price_input") and valuation_record.get("share_basis_input"):
        cap_basis = _market_cap_monetary_basis((valuation_record or {}).get("price_input") or {}, share)
        market_cap.update({"monetary_basis": cap_basis, "monetary_basis_status": cap_basis["basis_status"],
                           "monetary_basis_source": cap_basis["basis_source"],
                           "currency": cap_basis["currency"], "scale": cap_basis["native_scale"]})
    ttm_ni = _select_ttm(old=_feature(feature_record, "net_income_ttm_sum"),
                         qualified=_qualified_ttm("net_income_ttm", financial_analysis_record, financial_analysis_context_identity))
    ttm_rev = _select_ttm(old=_feature(feature_record, "revenue_ttm_sum"),
                          qualified=_qualified_ttm("revenue_ttm", financial_analysis_record, financial_analysis_context_identity))
    profit = _feature(feature_record, "profit_state")
    earnings_state = _earnings_state(ttm_ni, profit)
    methods = {
        PE_TTM: _ttm_method(method_id=PE_TTM, metric="net_income_ttm_sum", ttm=ttm_ni, market_cap=market_cap,
                            share_class=share_class, entity=entity, earnings_state=earnings_state),
        PS_TTM: _ttm_method(method_id=PS_TTM, metric="revenue_ttm_sum", ttm=ttm_rev, market_cap=market_cap,
                            share_class=share_class, entity=entity, earnings_state=None),
        PE_EXISTING: _existing_method(PE_EXISTING, metrics.get("P/E") or {}, entity=entity, share_class=share_class),
        PS_EXISTING: _existing_method(PS_EXISTING, metrics.get("P/S") or {}, entity=entity, share_class=share_class),
        PB: _existing_method(PB, metrics.get("P/B") or {}, entity=entity, share_class=share_class),
        PB_CURRENT_RESEARCH: _book_value_method(
            ticker=ticker, entity=entity, share_class=share_class, market_cap=market_cap,
            equity_rows=book_equity_rows, decision_session=decision_session,
            verdict=monetary_basis_verdict, official_equity_facts=official_equity_facts),
        EV_SALES: _existing_method(EV_SALES, metrics.get("EV/Sales") or {}, entity=entity, share_class=share_class),
        EV_EBITDA: _ev_ebitda(entity, metrics.get("EV/EBITDA")),
        EV_EBITDA_CALC_READY: _calculation_readiness_method(
            capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
            entity=entity, calculation_readiness_record=calculation_readiness_record,
            decision_session=decision_session),
        MARKET_CAP: _existing_method(MARKET_CAP, market_cap, entity=entity, share_class=share_class),
    }
    readiness_reconciliation = _calculation_readiness_reconciliation(methods, calculation_readiness_record)
    usable = [item for item in methods.values() if item["status"] in {"RESEARCH_USABLE", "READY"}]
    not_meaningful = [item for item in methods.values() if item["status"] == PE_NOT_MEANINGFUL]
    # Earnings yield (section 11): the reciprocal of a usable P/E_TTM. A pure derived
    # convenience field, not a new formula or a peer/history-eligible method -- P/E_TTM
    # already carries its own peer/history context, and inverting it would only duplicate
    # that comparison on a rescaled axis.
    pe_ttm_method = methods[PE_TTM]
    earnings_yield_ttm = (
        {"status": "RESEARCH_USABLE", "value": 1.0 / pe_ttm_method["value"], "basis": "1_DIVIDED_BY_PE_TTM"}
        if pe_ttm_method["status"] == "RESEARCH_USABLE" and _numeric(pe_ttm_method.get("value")) and pe_ttm_method["value"] > 0
        else {"status": "BLOCKED", "value": None, "blocker_reason_codes": list(pe_ttm_method.get("blocker_reason_codes") or ["PE_TTM_NOT_RESEARCH_USABLE"])}
    )
    # FCF yield (section 11): explicitly not built. financial_analysis_engine_v2 only retains
    # a standalone-quarter free_cash_flow_proxy, never a TTM sum (no _ttm_sum call exists for
    # it) -- adding one would be new engine surface inside the regression-locked FA V2 core,
    # not a wiring/join task. Reported as a named, honest residual rather than fabricated.
    fcf_yield_ttm = {"status": "BLOCKED", "value": None, "blocker_reason_codes": ["FCF_TTM_NOT_RETAINED_STANDALONE_QUARTER_PROXY_ONLY"]}
    return {
        "ticker": ticker, "entity_class": entity, "entity_applicability": entity_detail, "share_basis": share_class,
        "share_authority": share.get("authority"), "share_status": share.get("status"),
        "share_concept": share.get("share_concept"),
        "authoritative_current_market_cap_eligible": bool(share.get("authoritative_current_market_cap_eligible")),
        "earnings_state": earnings_state,
        "pbt_ttm_context": _qualified_ttm("profit_before_tax_ttm", financial_analysis_record, financial_analysis_context_identity),
        "methods": methods,
        "calculation_readiness_context": dict(calculation_readiness_record or {}),
        "valuation_method_reconciliation": readiness_reconciliation,
        "usable_relative_method_count": sum(item["method_id"] in RELATIVE_METHODS and item["status"] in {"RESEARCH_USABLE", "READY"} for item in methods.values()),
        "pe_not_meaningful": bool(not_meaningful),
        "earnings_yield_ttm": earnings_yield_ttm,
        "fcf_yield_ttm": fcf_yield_ttm,
        "implied_expectations": {
            "status": IMPLIED_EXPECTATIONS_UNAVAILABLE,
            "reason": "NO_QUALIFIED_INTRINSIC_OUTPUTS",
            "reverse_dcf_manufactured": False,
        },
        "limitations": sorted({
            "CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE", "NOT_FOR_TARGET_PRICE", "NOT_DCF", "NOT_PIT",
            *(["SHARE_BASIS=" + share_class] if share_class != SHARE_UNAVAILABLE else ["SHARE_BASIS_UNAVAILABLE"]),
            *([PE_NOT_MEANINGFUL] if not_meaningful else []),
        }),
        "has_usable_method": bool(usable or not_meaningful),
    }


#: A statement scope the source never labelled. Two such rows are not proven to share a
#: consolidated/separate basis, so they never enter a cross-issuer peer cohort; the row's own
#: value stays usable (FINANCIAL_V2_ANALYSIS_INPUT_INTEGRITY_V1).
UNPROVEN_STATEMENT_SCOPES = frozenset({None, "", "unknown", "UNKNOWN"})
SCOPE_NOT_PEER_COMPARABLE = "STATEMENT_SCOPE_UNKNOWN_NOT_PEER_COMPARABLE"


def _scope_blocks_peers(method: Mapping[str, Any]) -> bool:
    return "statement_scope" in method and method.get("statement_scope") in UNPROVEN_STATEMENT_SCOPES


def _peer_key(row: Mapping[str, Any], method: Mapping[str, Any]) -> tuple[Any, ...] | None:
    if method.get("status") not in {"RESEARCH_USABLE", "READY"} or not _numeric(method.get("value")):
        return None
    if method.get("applicability") != APPLICABLE or _scope_blocks_peers(method):
        return None
    periods = tuple(method.get("input_periods") or [])
    latest = periods[-1] if periods else method.get("period_basis")
    return (
        method["method_id"],
        row.get("entity_class"),
        method.get("share_basis"),
        method.get("ttm_method") or method.get("period_basis"),
        method.get("ttm_compatibility_class") or "EXISTING_METHOD",
        latest,
    )


def attach_peer_relative(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Same-method peer comparison only; incompatible bases are excluded from the cohort."""
    cohorts: dict[tuple[Any, ...], list[tuple[str, float]]] = defaultdict(list)
    for ticker, row in rows.items():
        for method in (row.get("methods") or {}).values():
            key = _peer_key(row, method)
            if key is None:
                continue
            cohorts[key].append((ticker, float(method["value"])))
    for ticker, row in rows.items():
        relatives: dict[str, Any] = {}
        for method_id, method in (row.get("methods") or {}).items():
            key = _peer_key(row, method)
            if key is None:
                relatives[method_id] = {
                    "status": "NOT_COMPARABLE",
                    "reason": (method.get("status") if method.get("status") != "RESEARCH_USABLE"
                               else SCOPE_NOT_PEER_COMPARABLE if _scope_blocks_peers(method)
                               else "INCOMPATIBLE_OR_UNAVAILABLE_BASIS"),
                    "peer_count": 0, "peer_median": None, "percentile": None,
                    "premium_or_discount_to_peer_median": None,
                    "methodology": "same_method_same_basis_peer_cohort/v1",
                    "minimum_peer_count": MIN_COHORT_MEMBERS,
                }
                continue
            values = [value for _, value in cohorts[key]]
            if len(values) < MIN_COHORT_MEMBERS:
                relatives[method_id] = {
                    "status": "INSUFFICIENT_PEER_COUNT", "reason": "BELOW_MIN_COHORT_MEMBERS",
                    "peer_count": len(values), "peer_median": None, "percentile": None,
                    "premium_or_discount_to_peer_median": None,
                    "methodology": "same_method_same_basis_peer_cohort/v1",
                    "minimum_peer_count": MIN_COHORT_MEMBERS,
                    "percentile_formula": "(below + 0.5 * equal) / n",
                }
                continue
            mid = median(values)
            percentile = _percentile(values, float(method["value"]))
            relatives[method_id] = {
                "status": "READY_RESEARCH_ONLY",
                "peer_count": len(values),
                "peer_median": mid,
                "percentile": percentile,
                "premium_or_discount_to_peer_median": (float(method["value"]) / mid - 1) if mid else None,
                "methodology": "same_method_same_basis_peer_cohort/v1",
                "basis": {
                    "method_id": method_id, "entity_class": row.get("entity_class"),
                    "share_basis": method.get("share_basis"), "period_basis": method.get("period_basis"),
                    "compatibility_class": method.get("ttm_compatibility_class"),
                    "ttm_method": method.get("ttm_method"),
                },
                "minimum_peer_count": MIN_COHORT_MEMBERS,
                "percentile_formula": "(below + 0.5 * equal) / n",
            }
        # Market cap (and EV, if ever added here) is size context, never a relative-value input --
        # same invariant current_valuation_research_proxy.py enforces via its own RELATIVE_MULTIPLES
        # allowlist. Without this filter a ticker with zero usable P/E, P/S, P/B, or EV multiples can
        # still be labelled ATTRACTIVE_RELATIVE_RESEARCH purely from a cheap-looking market-cap
        # percentile against its peer cohort -- confirmed live on the 2026-08-28 opportunity_context
        # artifact (440/1699 tickers, 25.9%, had usable_relative_method_count == 0 yet a market-cap-
        # driven ATTRACTIVE_RELATIVE_RESEARCH label).
        attractive = [item for method_id, item in relatives.items() if method_id in RELATIVE_METHODS and item.get("status") == "READY_RESEARCH_ONLY" and _numeric(item.get("percentile")) and item["percentile"] <= 0.25]
        expensive = [item for method_id, item in relatives.items() if method_id in RELATIVE_METHODS and item.get("status") == "READY_RESEARCH_ONLY" and _numeric(item.get("percentile")) and item["percentile"] >= 0.75]
        in_line = [item for method_id, item in relatives.items() if method_id in RELATIVE_METHODS and item.get("status") == "READY_RESEARCH_ONLY"]
        if attractive:
            relative_state = "ATTRACTIVE_RELATIVE_RESEARCH"
        elif expensive and not attractive:
            relative_state = "EXPENSIVE_RELATIVE_RESEARCH"
        elif in_line:
            relative_state = "IN_LINE_RELATIVE_RESEARCH"
        elif row.get("usable_relative_method_count"):
            relative_state = "ABSOLUTE_RESEARCH_ONLY"
        elif row.get("pe_not_meaningful"):
            relative_state = PE_NOT_MEANINGFUL
        else:
            relative_state = "UNAVAILABLE"
        row["peer_relative"] = relatives
        row["relative_research_state"] = relative_state
    return dict(rows)


def _fundamental_peer_key(row: Mapping[str, Any], feature: Mapping[str, Any], feature_id: str) -> tuple[Any, ...] | None:
    if feature.get("status") not in READY_STATUSES or not _numeric(feature.get("value")):
        return None
    if feature.get("compatibility_class") in {None, "BLOCKED_INCOMPATIBLE"}:
        return None
    periods = tuple(feature.get("input_periods") or [])
    latest = periods[-1] if periods else None
    if not latest:
        return None
    return (feature_id, row.get("entity_class"), feature.get("method"), feature.get("compatibility_class"), latest)


FUNDAMENTAL_PEER_FEATURES = (
    "net_margin", "revenue_same_period_yoy", "net_income_same_period_yoy", "equity_to_assets",
)


def attach_fundamental_peers(feature_records: Mapping[str, Mapping[str, Any]],
                             valuation_rows: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Same-method fundamental relative context; ROE/ROA stay excluded unless method identity matches."""
    cohorts: dict[tuple[Any, ...], list[tuple[str, float]]] = defaultdict(list)
    for ticker, record in feature_records.items():
        entity = _entity(record, (valuation_rows.get(ticker) if valuation_rows else None))[0]
        envelope = {"entity_class": entity}
        for feature_id in FUNDAMENTAL_PEER_FEATURES:
            feature = _feature(record, feature_id)
            key = _fundamental_peer_key(envelope, feature, feature_id)
            if key is not None:
                cohorts[key].append((ticker, float(feature["value"])))
    out: dict[str, dict[str, Any]] = {}
    for ticker, record in feature_records.items():
        entity = _entity(record, (valuation_rows.get(ticker) if valuation_rows else None))[0]
        envelope = {"entity_class": entity}
        relatives: dict[str, Any] = {}
        for feature_id in FUNDAMENTAL_PEER_FEATURES:
            feature = _feature(record, feature_id)
            key = _fundamental_peer_key(envelope, feature, feature_id)
            if key is None:
                relatives[feature_id] = {
                    "status": "NOT_COMPARABLE",
                    "reason": list(feature.get("blocker_reason_codes") or ["FEATURE_NOT_COMPARABLE"]),
                    "peer_count": 0, "method": feature.get("method"),
                    "compatibility_class": feature.get("compatibility_class"),
                }
                continue
            values = [value for _, value in cohorts[key]]
            if len(values) < MIN_COHORT_MEMBERS:
                relatives[feature_id] = {
                    "status": "INSUFFICIENT_PEER_COUNT", "peer_count": len(values),
                    "minimum_peer_count": MIN_COHORT_MEMBERS, "method": feature.get("method"),
                    "compatibility_class": feature.get("compatibility_class"),
                }
                continue
            relatives[feature_id] = {
                "status": "READY_RESEARCH_ONLY", "peer_count": len(values),
                "peer_median": median(values),
                "percentile": _percentile(values, float(feature["value"])),
                "subject_value": feature["value"],
                "method": feature.get("method"),
                "compatibility_class": feature.get("compatibility_class"),
                "input_periods": list(feature.get("input_periods") or []),
                "percentile_formula": "(below + 0.5 * equal) / n",
                "minimum_peer_count": MIN_COHORT_MEMBERS,
            }
        out[ticker] = relatives
    return out


#: financial_analysis_engine_v2 features this milestone exposes sector/industry peer
#: context for. Deliberately the same already-READY-capable ratios `history_context`
#: targets in that module -- not every feature the engine computes, to keep both
#: additions bounded to metrics that are genuinely usable across a wide cohort.
ENGINE_PEER_FEATURES = (
    "gross_margin", "net_margin", "equity_to_assets", "current_ratio",
    "same_provider_roe_avg_equity", "same_provider_roa_avg_assets",
)
SECTOR_COHORT_LEVEL = "SECTOR_INDUSTRY_DESCRIPTIVE"
ENTITY_CLASS_COHORT_LEVEL = "ENTITY_CLASS_FALLBACK"


def _engine_cohort(ticker: str, record: Mapping[str, Any], industry_by_ticker: Mapping[str, str] | None) -> tuple[str, str]:
    """(cohort_id, cohort_level): a retained descriptive sector/industry label when one is
    available for this ticker, else the coarser entity-class grouping `attach_peer_relative`
    already uses for valuation. Never a fabricated, inferred, or manually assigned sector --
    absence of a retained label degrades only to the entity-class cohort, never to a guess.
    """
    industry = (industry_by_ticker or {}).get(ticker)
    if isinstance(industry, str) and industry.strip():
        return f"SECTOR:{industry.strip().casefold()}", SECTOR_COHORT_LEVEL
    issuer_type = record.get("issuer_type") or record.get("entity_class") or "unknown"
    return f"ENTITY_CLASS:{issuer_type}", ENTITY_CLASS_COHORT_LEVEL


def _engine_feature(record: Mapping[str, Any] | None, feature_id: str) -> Mapping[str, Any]:
    features = (record or {}).get("features") or {}
    item = features.get(feature_id)
    return item if isinstance(item, Mapping) else {}


def _engine_peer_key(cohort_id: str, feature: Mapping[str, Any], feature_id: str) -> tuple[Any, ...] | None:
    if feature.get("fitness") != "READY" or not _numeric(feature.get("value")):
        return None
    periods = tuple(feature.get("period_identity") or [])
    latest = periods[-1] if periods else None
    if not latest or not feature.get("scope") or any(scope in UNPROVEN_STATEMENT_SCOPES for scope in feature["scope"]):
        return None
    return (feature_id, cohort_id, feature.get("method"), tuple(feature.get("scope") or []),
            feature.get("currency"), feature.get("scale"), latest)


def attach_engine_fundamental_peers(engine_records: Mapping[str, Mapping[str, Any]],
                                    *, industry_by_ticker: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """Sector/industry (falling back to entity-class) peer median/tie-aware percentile/rank
    for a curated set of already-READY `financial_analysis_engine_v2` features.

    Deliberately additive and separate from `attach_fundamental_peers` above, which reads
    the older market-wide fundamental feature store's differently-shaped and differently-
    named features. Compares only rows sharing an identical feature method, cohort, scope,
    currency, scale and latest retained period -- the same same-representation discipline
    the engine itself enforces before computing any one ticker's own value. Missing peers
    (or a subject feature that is not READY) degrade only that one metric's comparison,
    never the ticker's other metrics.
    """
    cohorts: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    cohort_of: dict[str, tuple[str, str]] = {}
    for ticker, record in engine_records.items():
        cohort_id, cohort_level = _engine_cohort(ticker, record or {}, industry_by_ticker)
        cohort_of[ticker] = (cohort_id, cohort_level)
        for feature_id in ENGINE_PEER_FEATURES:
            key = _engine_peer_key(cohort_id, _engine_feature(record, feature_id), feature_id)
            if key is not None:
                cohorts[key].append(float(_engine_feature(record, feature_id)["value"]))
    out: dict[str, dict[str, Any]] = {}
    for ticker, record in engine_records.items():
        cohort_id, cohort_level = cohort_of[ticker]
        relatives: dict[str, Any] = {}
        for feature_id in ENGINE_PEER_FEATURES:
            feature = _engine_feature(record, feature_id)
            key = _engine_peer_key(cohort_id, feature, feature_id)
            if key is None:
                scope_unproven = (feature.get("fitness") == "READY" and _numeric(feature.get("value"))
                                  and any(scope in UNPROVEN_STATEMENT_SCOPES for scope in (feature.get("scope") or [None])))
                relatives[feature_id] = {
                    "status": "NOT_COMPARABLE",
                    "reason": [SCOPE_NOT_PEER_COMPARABLE] if scope_unproven else list(feature.get("reason_codes") or ["FEATURE_NOT_COMPARABLE"]),
                    "peer_count": 0, "cohort_id": cohort_id, "cohort_level": cohort_level,
                    "method": feature.get("method"), "minimum_peer_count": MIN_COHORT_MEMBERS,
                }
                continue
            values = cohorts[key]
            if len(values) < MIN_COHORT_MEMBERS:
                relatives[feature_id] = {
                    "status": "INSUFFICIENT_PEER_COUNT", "peer_count": len(values),
                    "minimum_peer_count": MIN_COHORT_MEMBERS, "cohort_id": cohort_id, "cohort_level": cohort_level,
                    "method": feature.get("method"),
                }
                continue
            subject = float(feature["value"])
            relatives[feature_id] = {
                "status": "READY_RESEARCH_ONLY", "peer_count": len(values),
                "peer_median": median(values), "percentile": _percentile(values, subject),
                "subject_value": subject, "cohort_id": cohort_id, "cohort_level": cohort_level,
                "method": feature.get("method"), "as_of_period": (feature.get("period_identity") or [None])[-1],
                "percentile_formula": "(below + 0.5 * equal) / n", "minimum_peer_count": MIN_COHORT_MEMBERS,
            }
        out[ticker] = relatives
    return out


def method_availability_state(method: Mapping[str, Any], peer_detail: Mapping[str, Any] | None) -> str:
    """Diagnostic availability for one valuation method -- orthogonal to `status`/`applicability`.

    A usable multiple with a numeric value is AVAILABLE_QUALIFIED only when its own
    peer-relative comparison is itself qualified (enough same-basis peers, see
    `attach_peer_relative`); otherwise it is AVAILABLE_REFERENCE_ONLY -- the multiple is
    real and displayable research context, it just does not support a relative-valuation
    label (ATTRACTIVE/EXPENSIVE_RELATIVE_RESEARCH). PE_NOT_MEANINGFUL retains a genuine
    observed `earnings_state` even though the ratio's own value is deliberately None --
    also AVAILABLE_REFERENCE_ONLY, never NOT_AVAILABLE (the state itself is real evidence).
    Everything else (INPUT_BLOCKED, NOT_APPLICABLE) has no genuine retained value to show.
    """
    if method.get("status") in {"RESEARCH_USABLE", "READY"} and _numeric(method.get("value")):
        if isinstance(peer_detail, Mapping) and peer_detail.get("status") == "READY_RESEARCH_ONLY":
            return AVAILABLE_QUALIFIED
        return AVAILABLE_REFERENCE_ONLY
    if method.get("status") == PE_NOT_MEANINGFUL:
        return AVAILABLE_REFERENCE_ONLY
    return NOT_AVAILABLE


def _valuation_display_summary(methods_view: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Display-oriented rollup: never a target/fair value, never "N absolute valuation models".

    Only counts the true relative-valuation method identities (`RELATIVE_METHODS`) -- market
    cap is size context, not a valuation method, and is deliberately excluded here exactly as
    `attach_peer_relative` excludes it from ATTRACTIVE/EXPENSIVE_RELATIVE_RESEARCH labelling.
    """
    relevant = {method_id: method for method_id, method in methods_view.items() if method_id in RELATIVE_METHODS}
    qualified = {mid: m for mid, m in relevant.items() if m.get("availability_state") == AVAILABLE_QUALIFIED}
    reference_only = {mid: m for mid, m in relevant.items() if m.get("availability_state") == AVAILABLE_REFERENCE_ONLY}
    missing = {mid: m for mid, m in relevant.items() if m.get("availability_state") == NOT_AVAILABLE}
    available_count = len(qualified) + len(reference_only)
    if qualified:
        display_state = "PEER_RELATIVE_QUALIFIED"
    elif available_count:
        display_state = "RESEARCH_METHODS_AVAILABLE_NOT_PEER_QUALIFIED"
    else:
        display_state = "NO_VALUATION_METHOD_AVAILABLE"
    return {
        "valuation_display_state": display_state,
        "available_method_count": available_count,
        "qualified_relative_method_count": len(qualified),
        "reference_only_method_count": len(reference_only),
        "missing_method_count": len(missing),
        "summary_reason_codes": sorted({
            code for m in missing.values() for code in (m.get("blocker_reason_codes") or [])
        }),
        "display_note": (
            f"{available_count} valuation method(s) available for research. "
            + ("Peer-relative valuation qualified." if qualified else "Peer-relative valuation not yet qualified.")
        ) if available_count else "No valuation method available for research.",
        "not_intrinsic_fair_value": True,
        "not_dcf_or_target_price": True,
    }


def valuation_axis(*, ticker: str, decision_session: str, valuation_artifact: Mapping[str, Any] | None,
                   feature_store: Mapping[str, Any] | None, row: Mapping[str, Any],
                   freshness: Mapping[str, Any]) -> dict[str, Any]:
    usable = axis_is_research_usable(freshness) and (
        row.get("has_usable_method") or row.get("relative_research_state") not in {None, "UNAVAILABLE"}
    )
    readiness = "UNAVAILABLE"
    if not axis_is_research_usable(freshness):
        readiness = freshness.get("freshness_status") or UNAVAILABLE
    elif row.get("usable_relative_method_count") or row.get("methods", {}).get(MARKET_CAP, {}).get("status") in {"RESEARCH_USABLE", "READY"}:
        readiness = "READY_RESEARCH_PROXY"
    elif row.get("pe_not_meaningful"):
        readiness = PE_NOT_MEANINGFUL
    methods_view = {
        method_id: {
            "applicability": method["applicability"], "status": method["status"], "value": method.get("value"),
            "share_basis": method.get("share_basis"), "period_basis": method.get("period_basis"),
            "blocker_reason_codes": method.get("blocker_reason_codes"),
            "ttm_input_source": method.get("ttm_input_source"), "ttm_source_context_identity": method.get("ttm_source_context_identity"),
            "ttm_feature_id": method.get("ttm_feature_id"), "ttm_method": method.get("ttm_method"),
            "ttm_periods": method.get("ttm_periods"),
            "ttm_provider": method.get("ttm_provider"), "ttm_currency": method.get("ttm_currency"),
            "ttm_scale": method.get("ttm_scale"), "ttm_fitness": method.get("ttm_fitness"),
            "ttm_source_conflict": method.get("ttm_source_conflict"),
            "ttm_monetary_basis": method.get("ttm_monetary_basis"),
            "market_cap_monetary_basis": method.get("market_cap_monetary_basis"),
            "equity_monetary_basis": method.get("equity_monetary_basis"),
            "book_period": method.get("book_period"),
            "book_period_lag_quarters": method.get("book_period_lag_quarters"),
            "equity_definition": method.get("equity_definition"),
            "statement_scope": method.get("statement_scope"),
            "limitations": method.get("limitations"),
            "peer_relative": (row.get("peer_relative") or {}).get(method_id),
            "availability_state": method_availability_state(method, (row.get("peer_relative") or {}).get(method_id)),
        }
        for method_id, method in (row.get("methods") or {}).items()
    }
    return {
        "valuation_summary": _valuation_display_summary(methods_view),
        "readiness": readiness,
        "freshness": dict(freshness),
        "entity_class": row.get("entity_class"),
        "share_basis": row.get("share_basis"),
        "earnings_state": row.get("earnings_state"),
        "pbt_ttm_context": row.get("pbt_ttm_context"),
        "applicable_methods": methods_view,
        "absolute_research_context": {
            "usable_relative_method_count": row.get("usable_relative_method_count"),
            "market_cap_status": (row.get("methods") or {}).get(MARKET_CAP, {}).get("status"),
            "implied_expectations": row.get("implied_expectations"),
        },
        "peer_relative_context": {
            "relative_research_state": row.get("relative_research_state"),
            "methods": row.get("peer_relative") or {},
        },
        "valuation_limitations": row.get("limitations") or [],
        "research_usable": bool(usable),
    }


def source_session_for_valuation(valuation_artifact: Mapping[str, Any] | None) -> str | None:
    if not isinstance(valuation_artifact, Mapping):
        return None
    return valuation_artifact.get("valuation_session") or valuation_artifact.get("session")


def freshness_for_valuation(*, decision_session: str, valuation_artifact: Mapping[str, Any] | None) -> dict[str, Any]:
    return classify_axis_freshness(
        axis="valuation", decision_session=decision_session,
        source_session=source_session_for_valuation(valuation_artifact),
        source_artifact_identity=(valuation_artifact or {}).get("artifact_identity"),
    )
