"""Current research valuation + same-method peer context over retained inputs.

Reuses existing valuation applicability, share-basis tiers, and Tactical V2 percentile
semantics. It does not invent DCF, fair-value, consensus, target prices, or probabilities.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Mapping, Sequence

from current_market_sector_leadership_context import _percentile
from market_wide_current_valuation_input_scaleout import RESEARCH_SHARE_AUTHORITIES, _applicability
from opportunity_axis_freshness import UNAVAILABLE, axis_is_research_usable, classify_axis_freshness
from sector_relative_research_context import MIN_COHORT_MEMBERS

CONTRACT_VERSION = "current_research_valuation_context/v1"
PE_TTM = "P/E_TTM"
PS_TTM = "P/S_TTM"
PB = "P/B"
PE_EXISTING = "P/E"
PS_EXISTING = "P/S"
EV_EBITDA = "EV/EBITDA"
EV_SALES = "EV/Sales"
MARKET_CAP = "market_cap"
TTM_METHODS = (PE_TTM, PS_TTM)
EXISTING_MULTIPLES = (PE_EXISTING, PS_EXISTING, PB, EV_SALES, EV_EBITDA)
RELATIVE_METHODS = (PE_TTM, PS_TTM, PE_EXISTING, PS_EXISTING, PB, EV_SALES, EV_EBITDA)
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
    return value not in (None, "", "unknown", "UNKNOWN")


def _qualified_ttm(feature_id: str, record: Mapping[str, Any] | None, context_identity: str | None) -> dict[str, Any] | None:
    feature = ((record or {}).get("features") or {}).get(feature_id) or {}
    if feature.get("fitness") != "READY" or not _numeric(feature.get("value")):
        return None
    lineage = list(feature.get("provider_source_provenance") or [])
    provider = lineage[0].get("provider") if lineage else None
    return {"status": "READY", "value": feature.get("value"), "method": feature.get("method"),
            "input_periods": list(feature.get("period_identity") or []), "compatibility_class": "QUALIFIED_FINANCIAL_ANALYSIS_V2",
            "blocker_reason_codes": list(feature.get("reason_codes") or []), "ttm_input_source": "NEW_QUALIFIED_TTM_SELECTED",
            "ttm_source_context_identity": context_identity, "ttm_feature_id": feature_id,
            "ttm_provider": provider, "ttm_currency": feature.get("currency"), "ttm_scale": feature.get("scale"),
            "ttm_fitness": feature.get("fitness"), "ttm_source_conflict": False}


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
        return {**dict(old), "ttm_input_source": "OLD_TTM_FALLBACK_SELECTED", "ttm_source_context_identity": None,
                "ttm_feature_id": old.get("feature_id"), "ttm_provider": ((old.get("provider_source_lineage") or [{}])[0]).get("provider"),
                "ttm_currency": old.get("currency"), "ttm_scale": old.get("scale"), "ttm_fitness": old.get("status"),
                "ttm_source_conflict": False}
    return {**dict(old), "ttm_input_source": "NO_TTM", "ttm_source_context_identity": None,
            "ttm_feature_id": old.get("feature_id"), "ttm_provider": None, "ttm_currency": None,
            "ttm_scale": None, "ttm_fitness": old.get("status"), "ttm_source_conflict": False}


def _monetary_basis_compatible(ttm: Mapping[str, Any], market_cap: Mapping[str, Any]) -> tuple[bool, str | None]:
    ttm_currency, cap_currency = ttm.get("ttm_currency"), market_cap.get("currency")
    ttm_scale, cap_scale = ttm.get("ttm_scale"), market_cap.get("scale")
    if not _known_basis(ttm_currency) or not _known_basis(cap_currency) or ttm_currency != cap_currency:
        return False, "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE"
    if not _known_basis(ttm_scale) or not _known_basis(cap_scale) or ttm_scale != cap_scale:
        return False, "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE"
    return True, None


def _entity(feature_record: Mapping[str, Any] | None, valuation_record: Mapping[str, Any] | None) -> str:
    for source in (valuation_record, feature_record):
        entity = (source or {}).get("entity_class") or (source or {}).get("entity_type")
        if isinstance(entity, str) and entity and entity != "unknown":
            return entity
    return "unknown"


def _method_applicability(entity: str, method_id: str) -> str:
    if method_id == MARKET_CAP:
        mapped = _applicability(entity, "market_cap")
    elif method_id in {PE_TTM, PE_EXISTING}:
        mapped = _applicability(entity, "P/E")
    elif method_id in {PS_TTM, PS_EXISTING}:
        mapped = _applicability(entity, "P/S")
    elif method_id == PB:
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
    return _method_shell(
        method_id, applicability=applicability, status="RESEARCH_USABLE",
        value=market_cap["value"] / denominator,
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


def evaluate_ticker_valuation(*, ticker: str, feature_record: Mapping[str, Any] | None,
                              valuation_record: Mapping[str, Any] | None,
                              financial_analysis_record: Mapping[str, Any] | None = None,
                              financial_analysis_context_identity: str | None = None) -> dict[str, Any]:
    entity = _entity(feature_record, valuation_record)
    share = (valuation_record or {}).get("share_basis_input") or {}
    share_class = share_basis_class(share)
    metrics = (valuation_record or {}).get("metrics") or {}
    market_cap = metrics.get(MARKET_CAP) or {}
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
        EV_SALES: _existing_method(EV_SALES, metrics.get("EV/Sales") or {}, entity=entity, share_class=share_class),
        EV_EBITDA: _ev_ebitda(entity, metrics.get("EV/EBITDA")),
        MARKET_CAP: _existing_method(MARKET_CAP, market_cap, entity=entity, share_class=share_class),
    }
    usable = [item for item in methods.values() if item["status"] in {"RESEARCH_USABLE", "READY"}]
    not_meaningful = [item for item in methods.values() if item["status"] == PE_NOT_MEANINGFUL]
    return {
        "ticker": ticker, "entity_class": entity, "share_basis": share_class,
        "share_authority": share.get("authority"), "share_status": share.get("status"),
        "share_concept": share.get("share_concept"),
        "authoritative_current_market_cap_eligible": bool(share.get("authoritative_current_market_cap_eligible")),
        "earnings_state": earnings_state,
        "pbt_ttm_context": _qualified_ttm("profit_before_tax_ttm", financial_analysis_record, financial_analysis_context_identity),
        "methods": methods,
        "usable_relative_method_count": sum(item["method_id"] in RELATIVE_METHODS and item["status"] in {"RESEARCH_USABLE", "READY"} for item in methods.values()),
        "pe_not_meaningful": bool(not_meaningful),
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


def _peer_key(row: Mapping[str, Any], method: Mapping[str, Any]) -> tuple[Any, ...] | None:
    if method.get("status") not in {"RESEARCH_USABLE", "READY"} or not _numeric(method.get("value")):
        return None
    if method.get("applicability") != APPLICABLE:
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
                    "reason": method.get("status") if method.get("status") != "RESEARCH_USABLE" else "INCOMPATIBLE_OR_UNAVAILABLE_BASIS",
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
        entity = _entity(record, (valuation_rows.get(ticker) if valuation_rows else None))
        envelope = {"entity_class": entity}
        for feature_id in FUNDAMENTAL_PEER_FEATURES:
            feature = _feature(record, feature_id)
            key = _fundamental_peer_key(envelope, feature, feature_id)
            if key is not None:
                cohorts[key].append((ticker, float(feature["value"])))
    out: dict[str, dict[str, Any]] = {}
    for ticker, record in feature_records.items():
        entity = _entity(record, (valuation_rows.get(ticker) if valuation_rows else None))
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
            "peer_relative": (row.get("peer_relative") or {}).get(method_id),
        }
        for method_id, method in (row.get("methods") or {}).items()
    }
    return {
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
