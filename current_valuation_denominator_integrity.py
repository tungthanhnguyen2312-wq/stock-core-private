"""Deterministic integrity diagnostics for current valuation inputs.

Provider multiples stay provider multiples. An arithmetic check such as
price / supplied EPS is a diagnostic. It never replaces the reported multiple
and never becomes a target price, probability, or recommendation.

Sector-specialist instruments are not forced through a generic industrial
multiple. Missing evidence blocks only the uses that depend on the missing field.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "current_valuation_denominator_integrity/v1"

CONSISTENT = "CONSISTENT"
INCONSISTENT_DENOMINATOR = "INCONSISTENT_DENOMINATOR"
PERIOD_MISMATCH = "PERIOD_MISMATCH"
SHARE_BASIS_MISMATCH = "SHARE_BASIS_MISMATCH"
CORPORATE_ACTION_PENDING = "CORPORATE_ACTION_PENDING"
EARNINGS_SEMANTICS_UNQUALIFIED = "EARNINGS_SEMANTICS_UNQUALIFIED"
NOT_COMPARABLE = "NOT_COMPARABLE"
INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
UNKNOWN = "UNKNOWN"

INTEGRITY_STATES = (
    CONSISTENT, INCONSISTENT_DENOMINATOR, PERIOD_MISMATCH, SHARE_BASIS_MISMATCH,
    CORPORATE_ACTION_PENDING, EARNINGS_SEMANTICS_UNQUALIFIED, NOT_COMPARABLE,
    INSUFFICIENT_INPUT, UNKNOWN,
)

NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE = "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE"
RECURRING_EARNINGS_QUALIFIED = "RECURRING_EARNINGS_QUALIFIED"
EARNINGS_QUALITY_UNKNOWN = "UNKNOWN"

STRICT_ALLOWED = "RESEARCH_PRESENTATION_ONLY"
STRICT_QUARANTINED = "STRICT_VALUATION_QUARANTINED"

CLAIM_FACT = "FACT"
CLAIM_DATA_WARNING = "DATA_WARNING"
CLAIM_INFERENCE = "INFERENCE"
CLAIM_MISSING = "MISSING"
CLAIM_STALE = "STALE"
CLAIM_PROXY = "PROXY"
CLAIM_CONFLICT = "CONFLICT"
CLAIM_CLASSES = (
    CLAIM_FACT, CLAIM_DATA_WARNING, CLAIM_INFERENCE, CLAIM_MISSING,
    CLAIM_STALE, CLAIM_PROXY, CLAIM_CONFLICT,
)

# Relative band for comparing a provider multiple with an independently
# computed arithmetic multiple. Outside this band the denominator is reported
# inconsistent. The provider value is left unchanged either way.
_CONSISTENCY_RELATIVE_BAND = 0.01

_EARNINGS_MULTIPLES = frozenset({"P/E", "PE", "PE_TTM", "P/E_TTM"})
_SPECIALIST_ENTITIES = frozenset({"bank", "securities", "securities_company", "insurance", "finance_company"})
_GENERIC_INDUSTRIAL_ONLY = frozenset({"EV/EBITDA", "EV/Sales"})

_NON_RECURRING_FLAGS = frozenset({
    "disposal_gain", "disposal_loss", "unusual_provision", "one_time_gain", "one_time_loss",
    "accounting_restatement", "extraordinary_corporate_action", "non_recurring_component",
})


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _same(left: Any, right: Any) -> bool | None:
    """True/False when both sides are present. None when either side is absent."""
    if left in (None, "", UNKNOWN) or right in (None, "", UNKNOWN):
        return None
    return str(left) == str(right)


def classify_earnings_quality(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Expose non-recurring risk without inventing a recurring earnings number.

    A qualified recurring decomposition is reported only when the evidence
    already says the decomposition exists. Otherwise a flagged component, or an
    explicit possibility, yields NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE.
    """
    payload = dict(evidence or {})
    flags = {str(item) for item in (payload.get("component_flags") or [])}
    present = flags & _NON_RECURRING_FLAGS
    possible = bool(payload.get("non_recurring_possible"))
    qualified = payload.get("recurring_decomposition_qualified") is True
    if present or possible:
        status = NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE
    elif qualified:
        status = RECURRING_EARNINGS_QUALIFIED
    elif payload:
        status = EARNINGS_SEMANTICS_UNQUALIFIED
    else:
        status = EARNINGS_QUALITY_UNKNOWN
    recurring_value = payload.get("recurring_earnings") if qualified and not present and not possible else None
    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "component_flags": sorted(present),
        "provenance": list(payload.get("provenance") or []),
        "recurring_earnings": recurring_value,
        "recurring_earnings_invented": False,
        "strict_recurring_multiple_allowed": status == RECURRING_EARNINGS_QUALIFIED,
        "allowed_uses": ["research_context", "earnings_quality_warning"],
        "prohibited_uses": ["recurring_pe_conclusion", "target_price", "recommendation"],
    }


def diagnose_multiple(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Compare one supplied multiple with arithmetic only when the semantics allow it."""
    method = str(observation.get("method_id") or "UNKNOWN")
    provider = _number(observation.get("provider_multiple"))
    price = _number(observation.get("price"))
    denominator = _number(observation.get("denominator"))
    entity = str(observation.get("entity_class") or "unknown")
    applicable = observation.get("method_applicable")
    if applicable is None:
        applicable = not (entity in _SPECIALIST_ENTITIES and method in _GENERIC_INDUSTRIAL_ONLY)
    earnings = classify_earnings_quality(observation.get("earnings_quality"))
    reasons: list[str] = []
    arithmetic = None
    status = UNKNOWN

    units_comparable = _same(observation.get("price_unit"), observation.get("denominator_unit"))
    currency_comparable = _same(observation.get("price_currency"), observation.get("denominator_currency"))
    if units_comparable is False or currency_comparable is False:
        status = NOT_COMPARABLE
        reasons.append("UNIT_OR_CURRENCY_NOT_COMPARABLE")
    elif applicable is False:
        status = NOT_COMPARABLE
        reasons.append("SECTOR_SPECIALIST_METHOD_NOT_APPLICABLE")
    elif observation.get("corporate_action_lifecycle") == "PENDING":
        status = CORPORATE_ACTION_PENDING
        reasons.append("CORPORATE_ACTION_PENDING_SHARE_BASIS_NOT_EXECUTED")
    elif _same(observation.get("price_share_basis"), observation.get("denominator_share_basis")) is False:
        status = SHARE_BASIS_MISMATCH
        reasons.append("PRICE_AND_DENOMINATOR_SHARE_BASIS_DIFFER")
    elif _same(observation.get("price_period"), observation.get("denominator_period")) is False:
        status = PERIOD_MISMATCH
        reasons.append("PRICE_AND_DENOMINATOR_PERIOD_DIFFER")
    elif method in _EARNINGS_MULTIPLES and earnings["status"] in {
        EARNINGS_SEMANTICS_UNQUALIFIED, NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE, EARNINGS_QUALITY_UNKNOWN,
    } and observation.get("require_qualified_earnings") is True:
        status = EARNINGS_SEMANTICS_UNQUALIFIED
        reasons.append(earnings["status"])
    elif price is None or denominator is None or denominator == 0:
        if provider is None and price is None and denominator is None:
            status = INSUFFICIENT_INPUT
            reasons.append("PRICE_DENOMINATOR_AND_PROVIDER_MULTIPLE_ABSENT")
        elif price is None or denominator is None or denominator == 0:
            status = INSUFFICIENT_INPUT if provider is None else UNKNOWN
            reasons.append("ARITHMETIC_INPUT_INSUFFICIENT")
            if provider is not None and status == UNKNOWN:
                reasons.append("PROVIDER_MULTIPLE_RETAINED_WITHOUT_ARITHMETIC_CHECK")
        else:
            status = INSUFFICIENT_INPUT
    else:
        arithmetic = price / denominator
        if provider is None:
            status = UNKNOWN
            reasons.append("PROVIDER_MULTIPLE_ABSENT_ARITHMETIC_NOT_SUBSTITUTED")
        else:
            scale = max(abs(provider), 1e-12)
            if abs(provider - arithmetic) / scale <= _CONSISTENCY_RELATIVE_BAND:
                status = CONSISTENT
            else:
                status = INCONSISTENT_DENOMINATOR
                reasons.append("PROVIDER_MULTIPLE_DIFFERS_FROM_PRICE_OVER_SUPPLIED_DENOMINATOR")

    quarantine = status in {
        INCONSISTENT_DENOMINATOR, PERIOD_MISMATCH, SHARE_BASIS_MISMATCH,
        CORPORATE_ACTION_PENDING, EARNINGS_SEMANTICS_UNQUALIFIED, NOT_COMPARABLE, UNKNOWN,
    }
    if method in _EARNINGS_MULTIPLES and earnings["status"] == NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE:
        quarantine = True
        reasons.append(NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE)
    if status not in INTEGRITY_STATES:
        status = UNKNOWN
    return {
        "contract_version": CONTRACT_VERSION,
        "method_id": method,
        "status": status,
        "provider_multiple": provider,
        "arithmetic_multiple": arithmetic,
        "provider_multiple_replaced": False,
        "strict_valuation_use": STRICT_QUARANTINED if quarantine or status == INSUFFICIENT_INPUT else STRICT_ALLOWED,
        "research_presentation_allowed": status != NOT_COMPARABLE,
        "reason_codes": reasons,
        "earnings_quality": earnings,
        "is_actionable": False,
        "target_price": None,
        "probability": None,
    }


def diagnose_methods(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [diagnose_multiple(item) for item in observations]
    counts = Counter(row["status"] for row in rows)
    return {
        "contract_version": CONTRACT_VERSION,
        "multiples": rows,
        "status_counts": dict(sorted(counts.items())),
        "any_strict_quarantine": any(row["strict_valuation_use"] == STRICT_QUARANTINED for row in rows),
        "provider_multiples_replaced": 0,
    }


def project_corporate_event_binding(event: Mapping[str, Any]) -> dict[str, Any]:
    """Project an already-qualified event. Never infer an ex-date or executed shares."""
    lifecycle = str(event.get("lifecycle") or event.get("event_status") or UNKNOWN)
    planned = lifecycle in {"PLANNED", "PROPOSED", "ANNOUNCED", "CONFIRMED_UPCOMING"}
    executed = lifecycle in {"EXECUTED", "CONFIRMED_RECENT"} and event.get("execution_evidence_qualified") is True
    ex_date = event.get("ex_date") if event.get("ex_date_qualified") is True else None
    share_delta = event.get("share_delta") if executed else None
    return {
        "contract_version": CONTRACT_VERSION,
        "event_type": event.get("event_type"),
        "event_status": lifecycle,
        "event_date": event.get("event_date"),
        "knowledge_date": event.get("known_at") or event.get("announcement_date"),
        "record_date": event.get("record_date") if event.get("record_date_qualified") is True else None,
        "ex_date": ex_date,
        "ex_date_inferred": False,
        "lifecycle": "EXECUTED" if executed else "PLANNED" if planned else lifecycle,
        "affected_share_basis": event.get("affected_share_basis") or UNKNOWN,
        "dilution_status": event.get("dilution_status") or ("DILUTION_POSSIBLE" if planned and event.get("event_type") in {"ISSUANCE", "RIGHTS"} else UNKNOWN),
        "planned_shares_converted_to_executed": False,
        "executed_share_delta": share_delta,
        "valuation_impact_class": event.get("valuation_impact_class") or UNKNOWN,
        "freshness": event.get("freshness") or UNKNOWN,
        "evidence_tier": event.get("evidence_tier") or UNKNOWN,
        "issuer_route_promoted": False,
    }


def classify_claim(field: Mapping[str, Any] | None) -> str:
    """One claim class for a supplied field. Absence is MISSING, not a fact."""
    if not field:
        return CLAIM_MISSING
    if field.get("conflict") is True:
        return CLAIM_CONFLICT
    if field.get("stale") is True:
        return CLAIM_STALE
    if field.get("proxy") is True:
        return CLAIM_PROXY
    if field.get("warning") is True:
        return CLAIM_DATA_WARNING
    if field.get("inference") is True:
        return CLAIM_INFERENCE
    if field.get("present") is True or field.get("value") is not None:
        return CLAIM_FACT
    return CLAIM_MISSING


def dependent_use_blocked(claim: str, *, use_requires_field: bool) -> bool:
    """Missing or conflicted evidence blocks only uses that require the field."""
    if not use_requires_field:
        return False
    return claim in {CLAIM_MISSING, CLAIM_CONFLICT, CLAIM_STALE}


def classify_coverage_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """One universe member. Low coverage stays visible as its own state."""
    fundamentals = str(row.get("fundamentals") or "NO_EVIDENCE")
    valuation = str(row.get("valuation") or "NO_EVIDENCE")
    corporate_intelligence = str(row.get("corporate_intelligence") or "NO_EVIDENCE")
    corporate_action = str(row.get("corporate_action") or "NOT_RELEVANT")
    specialist = bool(row.get("sector_specialist_required"))
    valuation_state = "QUARANTINED" if valuation == "QUARANTINED" else "USABLE" if valuation == "USABLE" else "UNAVAILABLE"
    return {
        "ticker": row.get("ticker"),
        "fundamentals": fundamentals if fundamentals in {"QUALIFIED_CURRENT", "RETAINED_STALE", "NO_EVIDENCE"} else "NO_EVIDENCE",
        "valuation": valuation_state,
        "corporate_intelligence": corporate_intelligence if corporate_intelligence in {"CURRENT", "HISTORICAL", "NO_EVIDENCE"} else "NO_EVIDENCE",
        "corporate_action": corporate_action if corporate_action in {"RELEVANT", "NOT_RELEVANT"} else "NOT_RELEVANT",
        "sector_specialist_required": specialist,
        "evidence": "NO_EVIDENCE" if fundamentals == "NO_EVIDENCE" and valuation_state == "UNAVAILABLE" and corporate_intelligence == "NO_EVIDENCE" else "SOME_EVIDENCE",
    }


def summarize_coverage(rows: Sequence[Mapping[str, Any]], *, universe_denominator: int | None = None) -> dict[str, Any]:
    classified = [classify_coverage_row(row) for row in rows]
    denominator = universe_denominator if universe_denominator is not None else len(classified)
    counts = Counter()
    for row in classified:
        counts["fundamentals_" + row["fundamentals"]] += 1
        counts["valuation_" + row["valuation"]] += 1
        counts["corporate_intelligence_" + row["corporate_intelligence"]] += 1
        counts["corporate_action_" + row["corporate_action"]] += 1
        if row["sector_specialist_required"]:
            counts["sector_specialist_required"] += 1
        if row["evidence"] == "NO_EVIDENCE":
            counts["no_evidence"] += 1
    missing_from_supply = max(0, denominator - len(classified))
    counts["no_evidence"] += missing_from_supply
    return {
        "contract_version": CONTRACT_VERSION,
        "universe_denominator": denominator,
        "classified_rows": len(classified),
        "unclassified_universe_members": missing_from_supply,
        "counts": dict(sorted(counts.items())),
        "low_coverage_visible": True,
        "authority_effect": "NONE",
    }
