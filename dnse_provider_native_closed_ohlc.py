"""Bounded DNSE provider-native closed-session OHLC semantics."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from dnse_closed_session_ohlc_representation import FIELDS, IDENTITY_TRANSFORMATION


CONTRACT_VERSION = "dnse_provider_native_closed_ohlc_representation/v1"
REPRESENTATION_CLASS = "PROVIDER_NATIVE_CLOSED_OHLC_REPRESENTATION"
FORMAL_PRICE_UNIT = "UNRESOLVED"
ADJUSTMENT_BASIS = "UNRESOLVED"
RAW_AS_TRADED = "NOT_QUALIFIED"
ELIGIBLE_USE_CLASSES = (
    "SOURCE_RECONCILIATION", "FIELD_CONSISTENCY_VALIDATION", "ANOMALY_DETECTION",
    "SCALE_INVARIANT_TECHNICAL_TRANSFORMATIONS_WITHIN_SAME_REPRESENTATION",
)
PROHIBITED_USE_CLASSES = (
    "MARKET_CAPITALIZATION", "MONETARY_VALUATION", "VND_POSITION_SIZING", "TRADED_VALUE_LIQUIDITY",
    "ABSOLUTE_TARGET_PRICE", "RAW_AS_TRADED_BACKTEST", "CORPORATE_ACTION_FACTOR_INFERENCE",
    "HISTORICAL_BASIS_SENSITIVE_ANALYTICS",
)


def closed_historical_session_gate(anchor: Mapping[str, Any]) -> dict[str, Any]:
    """Require a retained one-day observation acquired after its local session date."""
    if anchor.get("status") != "UNIFORM_REPRESENTATION_READY":
        return {"status": "REJECTED", "reason": "UNIFORM_REPRESENTATION_NOT_READY"}
    source = anchor.get("source_evidence")
    if not isinstance(source, Mapping) or source.get("endpoint") != "/price/ohlc":
        return {"status": "REJECTED", "reason": "OHLC_SOURCE_EVIDENCE_MISSING"}
    try:
        session = datetime.fromisoformat(str(anchor["session"])).date()
        retrieved = datetime.fromisoformat(str(source["retrieved_at"])).date()
    except (KeyError, TypeError, ValueError):
        return {"status": "REJECTED", "reason": "SESSION_OR_RETRIEVAL_TIME_INVALID"}
    if retrieved <= session:
        return {"status": "REJECTED", "reason": "CURRENT_OR_INCOMPLETE_SESSION"}
    return {"status": "PASS", "session_completion": "RETAINED_AFTER_SESSION_DATE", "session": session.isoformat(),
            "retrieved_at": str(source["retrieved_at"])}


def qualify_provider_native_closed_ohlc(anchor: Mapping[str, Any]) -> dict[str, Any]:
    """Qualify representation-safe semantics only; retain all price unknowns."""
    closed_gate = closed_historical_session_gate(anchor)
    representations = anchor.get("field_representation")
    if not isinstance(representations, Mapping) or set(representations) != set(FIELDS):
        return {"status": "REJECTED", "reason": "FIELD_REPRESENTATION_INCOMPLETE", "closed_session_gate": closed_gate}
    if set(representations.values()) != {IDENTITY_TRANSFORMATION}:
        return {"status": "REJECTED", "reason": "MIXED_OR_NON_IDENTITY_FIELD_REPRESENTATION", "closed_session_gate": closed_gate}
    if closed_gate["status"] != "PASS":
        return {"status": "REJECTED", "reason": closed_gate["reason"], "closed_session_gate": closed_gate}
    return {
        "status": "QUALIFIED_FOR_BOUNDED_REPRESENTATION_SAFE_USES", "contract_version": CONTRACT_VERSION,
        "representation_class": REPRESENTATION_CLASS, "instrument": anchor["instrument"], "session": anchor["session"],
        "source_evidence": dict(anchor["source_evidence"]), "closed_session_gate": closed_gate,
        "field_representation": dict(representations), "known_semantics": {
            "same_dnse_ohlc_capability": True, "uniform_numeric_representation": True,
            "field_specific_hidden_scaling": False, "raw_values_preserved": True, "deterministic_replayable": True,
        },
        "unknown_semantics": {"formal_price_unit": FORMAL_PRICE_UNIT, "adjustment_basis": ADJUSTMENT_BASIS,
                              "raw_as_traded": RAW_AS_TRADED},
        "eligible_use_classes": list(ELIGIBLE_USE_CLASSES), "prohibited_use_classes": list(PROHIBITED_USE_CLASSES),
        "authority_effect": "NONE",
    }


def scale_invariant_return(*, previous: float, current: float, previous_representation: str,
                           current_representation: str, basis_continuity: str) -> dict[str, Any]:
    """Compute a return only under an independently established safe interval."""
    if previous_representation != current_representation:
        return {"status": "INELIGIBLE", "reason": "CROSS_REPRESENTATION_RETURN"}
    if basis_continuity != "CONFIRMED_COMPATIBLE_INTERVAL":
        return {"status": "INELIGIBLE", "reason": "BASIS_OR_CORPORATE_ACTION_CONTINUITY_UNCONFIRMED"}
    try:
        previous_decimal, current_decimal = Decimal(str(previous)), Decimal(str(current))
    except (InvalidOperation, ValueError):
        return {"status": "INELIGIBLE", "reason": "NON_NUMERIC_PRICE"}
    if previous_decimal <= 0 or current_decimal <= 0:
        return {"status": "INELIGIBLE", "reason": "NON_POSITIVE_PRICE"}
    return {"status": "ELIGIBLE", "return": float(current_decimal / previous_decimal - Decimal(1)),
            "scale_invariant": True, "authority_effect": "NONE"}


def cross_provider_native_agreement(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Report agreement as empirical support only, never source authority."""
    exact = sum(bool(row.get("raw_to_raw_numeric_equal")) for row in rows)
    return {
        "status": "CROSS_PROVIDER_NATIVE_REPRESENTATION_AGREEMENT" if len(rows) == 12 and exact == 12 else "NO_AGREEMENT",
        "exact_raw_to_raw_field_count": exact, "total_field_count": len(rows),
        "fhsc_role": "SHADOW_REFERENCE_PROVIDER", "authority_effect": "NONE",
    }
