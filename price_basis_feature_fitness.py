"""Shadow-only price-basis semantics and price-derived feature fitness.

This contract answers one deliberately narrow question: whether two retained price contexts have
the same *economic basis* for a named price-derived use.  It is not a price transformer, a
corporate-action-factor calculator, a technical-indicator engine, or an authority-promotion
route.  In particular, the presence of ``RAW_AS_TRADED`` in this vocabulary does not grant that
authority: the repository's standing authority remains ``NOT_PROMOTED`` and raw execution replay
therefore fails closed here as well.

The distinction matters because a material numerical gap can be a legitimate result of a later
split, bonus, or dividend adjustment.  Numeric divergence is retained as an anomaly signal only;
it is never used as a compatibility or authority gate.  Corporate-action factors are accepted
only when a caller explicitly supplies an already-qualified chain identity with executed,
explicit-ex-date evidence.  A record date is intentionally not read as an ex-date anywhere in
this module.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "price_basis_semantics_and_feature_fitness/v1"
SCHEMA_VERSION = "1.0.0"

RAW_AS_TRADED = "RAW_AS_TRADED"
CURRENT_RETROSPECTIVE_ADJUSTED = "CURRENT_RETROSPECTIVE_ADJUSTED"
POINT_IN_TIME_ADJUSTED = "POINT_IN_TIME_ADJUSTED"
BASIS_UNKNOWN = "BASIS_UNKNOWN"
BASIS_VOCABULARY = frozenset({
    RAW_AS_TRADED,
    CURRENT_RETROSPECTIVE_ADJUSTED,
    POINT_IN_TIME_ADJUSTED,
    BASIS_UNKNOWN,
})

MA20 = "MA20"
MA50 = "MA50"
MA200 = "MA200"
RSI = "RSI"
MOMENTUM_RETURN = "MOMENTUM_RETURN"
LOCAL_PRICE_ACTION = "LOCAL_PRICE_ACTION"
PIT_BACKTEST = "PIT_BACKTEST"
EXECUTION_RAW_REPLAY = "EXECUTION_RAW_REPLAY"
PRICE_DERIVED_FEATURES = frozenset({
    MA20, MA50, MA200, RSI, MOMENTUM_RETURN, LOCAL_PRICE_ACTION,
    PIT_BACKTEST, EXECUTION_RAW_REPLAY,
})

BASIS_COMPATIBLE = "BASIS_COMPATIBLE"
BASIS_COMPATIBLE_RESEARCH_ONLY = "BASIS_COMPATIBLE_RESEARCH_ONLY"
BASIS_UNVERIFIED = "BASIS_UNVERIFIED"
BASIS_INCOMPATIBLE = "BASIS_INCOMPATIBLE"
POINT_IN_TIME_SEMANTICS_UNQUALIFIED = "POINT_IN_TIME_SEMANTICS_UNQUALIFIED"
FITNESS_STATES = frozenset({
    BASIS_COMPATIBLE,
    BASIS_COMPATIBLE_RESEARCH_ONLY,
    BASIS_UNVERIFIED,
    BASIS_INCOMPATIBLE,
    POINT_IN_TIME_SEMANTICS_UNQUALIFIED,
})

RAW_AS_TRADED_AUTHORITY = "NOT_PROMOTED"

REASON_BASIS_UNKNOWN = "BASIS_UNKNOWN_OR_UNSUPPORTED"
REASON_SOURCE_IDENTITY_MISSING = "SOURCE_OR_PROVIDER_IDENTITY_MISSING"
REASON_DATE_RANGE_MISSING = "SESSION_OR_DATE_RANGE_MISSING"
REASON_PROVENANCE_MISSING = "BASIS_PROVENANCE_MISSING"
REASON_BASIS_MISMATCH = "PRICE_BASIS_MISMATCH"
REASON_LINEAGE_MISMATCH = "PRICE_BASIS_LINEAGE_MISMATCH"
REASON_ADJUSTMENT_CHAIN_UNQUALIFIED = "CORPORATE_ACTION_FACTOR_CHAIN_UNQUALIFIED"
REASON_NO_QUALIFIED_FACTOR_CHAIN = "NO_QUALIFIED_CORPORATE_ACTION_FACTOR_CHAIN"
REASON_RECORD_DATE_NOT_EX_DATE = "RECORD_DATE_DOES_NOT_ESTABLISH_EX_DATE"
REASON_RAW_AS_TRADED_NOT_PROMOTED = "RAW_AS_TRADED_NOT_PROMOTED"
REASON_CURRENT_ADJUSTED_RESEARCH_ONLY = "CURRENT_RETROSPECTIVE_ADJUSTED_RESEARCH_ONLY"
REASON_PIT_REQUIRES_POINT_IN_TIME_ADJUSTED = "PIT_REQUIRES_POINT_IN_TIME_ADJUSTED_SERIES"
REASON_PIT_FACTOR_AFTER_DECISION = "PIT_FACTOR_NOT_KNOWABLE_BY_DECISION_CUTOFF"
REASON_PIT_CUTOFF_MISSING = "PIT_ADJUSTMENT_KNOWLEDGE_CUTOFF_MISSING"
REASON_PIT_FACTOR_CHAIN_UNQUALIFIED = "PIT_QUALIFIED_FACTOR_CHAIN_REQUIRED"
REASON_EXECUTION_REQUIRES_RAW = "EXECUTION_REPLAY_REQUIRES_RAW_AS_TRADED"
REASON_NUMERIC_DIVERGENCE_ANOMALY_ONLY = "NUMERIC_DIVERGENCE_IS_ANOMALY_SIGNAL_NOT_AUTHORITY_GATE"


class PriceBasisFitnessError(ValueError):
    """Raised for a malformed request rather than guessing a semantic field."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _instant(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        if len(text) <= 10:
            parsed = datetime.combine(parsed.date(), time(23, 59, 59, 999999))
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _basis(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    aliases = {
        "RAW": RAW_AS_TRADED,
        "RAW_AS_TRADED": RAW_AS_TRADED,
        "ADJUSTED_RETROSPECTIVE": CURRENT_RETROSPECTIVE_ADJUSTED,
        "RETROSPECTIVELY_ADJUSTED": CURRENT_RETROSPECTIVE_ADJUSTED,
        "CURRENT_RETROSPECTIVE_ADJUSTED": CURRENT_RETROSPECTIVE_ADJUSTED,
        "POINT_IN_TIME_ADJUSTED": POINT_IN_TIME_ADJUSTED,
        "PIT_ADJUSTED": POINT_IN_TIME_ADJUSTED,
        "UNKNOWN": BASIS_UNKNOWN,
        "BASIS_UNKNOWN": BASIS_UNKNOWN,
    }
    return aliases.get(normalized, BASIS_UNKNOWN)


def _factor_chain(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize a supplied factor-chain claim without deriving any event date or factor."""
    if not isinstance(value, Mapping):
        return {
            "identity": None,
            "status": "NOT_PROVIDED",
            "knowledge_cutoff": None,
            "event_types": [],
            "reason_codes": [REASON_NO_QUALIFIED_FACTOR_CHAIN],
        }
    identity = value.get("identity") or value.get("factor_chain_identity")
    execution = str(value.get("official_execution_status") or value.get("execution_status") or "").upper()
    ex_date_status = str(value.get("ex_date_status") or "").upper()
    status = str(value.get("status") or "").upper()
    cutoff = value.get("knowledge_cutoff") or value.get("adjustment_knowledge_cutoff")
    event_types = sorted({str(item) for item in (value.get("event_types") or []) if str(item).strip()})
    is_qualified = bool(identity) and status == "QUALIFIED" and execution == "EXECUTED" and ex_date_status == "EXPLICIT_OFFICIAL"
    reasons = list(value.get("reason_codes") or [])
    if value.get("record_date") and not value.get("ex_date"):
        reasons.append(REASON_RECORD_DATE_NOT_EX_DATE)
    if not is_qualified:
        reasons.append(REASON_ADJUSTMENT_CHAIN_UNQUALIFIED)
    return {
        "identity": str(identity) if identity else None,
        "status": "QUALIFIED" if is_qualified else "UNQUALIFIED",
        "knowledge_cutoff": str(cutoff) if cutoff else None,
        "event_types": event_types,
        "reason_codes": sorted(set(str(reason) for reason in reasons)),
    }


def price_series_context(
    *,
    ticker: str | None = None,
    provider: str | None,
    source_identity: str | None,
    session_start: str | None,
    session_end: str | None,
    observed_basis: str,
    basis_provenance: Sequence[str] = (),
    basis_confidence: str = "UNVERIFIED",
    basis_lineage_identity: str | None = None,
    adjustment_knowledge_cutoff: str | None = None,
    factor_chain: Mapping[str, Any] | None = None,
    reason_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the complete, explicit context shape consumed by the fitness evaluator.

    This constructor preserves missing source, dates, provenance, and factor knowledge as named
    reason codes.  It never fills a missing ex-date from a record date and never derives a factor.
    """
    selected_basis = _basis(observed_basis)
    start, end = _date_text(session_start), _date_text(session_end)
    provenance = sorted({str(item) for item in basis_provenance if str(item).strip()})
    chain = _factor_chain(factor_chain)
    reasons = {str(reason) for reason in reason_codes if str(reason).strip()}
    if selected_basis == BASIS_UNKNOWN:
        reasons.add(REASON_BASIS_UNKNOWN)
    if not source_identity:
        reasons.add(REASON_SOURCE_IDENTITY_MISSING)
    if not start or not end:
        reasons.add(REASON_DATE_RANGE_MISSING)
    if not provenance:
        reasons.add(REASON_PROVENANCE_MISSING)
    if not provider:
        reasons.add("PROVIDER_IDENTITY_NOT_RETAINED")
    if start and end and start > end:
        reasons.add("SESSION_RANGE_INVALID")
    context = {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "ticker": str(ticker).strip().upper() if ticker else None,
        "provider": str(provider).strip().upper() if provider else None,
        "source_identity": str(source_identity) if source_identity else None,
        "session_start": start,
        "session_end": end,
        "observed_basis": selected_basis,
        "adjustment_knowledge_cutoff": str(adjustment_knowledge_cutoff) if adjustment_knowledge_cutoff else None,
        "corporate_action_factor_chain": chain,
        "basis_provenance": provenance,
        "basis_confidence": str(basis_confidence),
        "basis_lineage_identity": str(basis_lineage_identity or source_identity) if (basis_lineage_identity or source_identity) else None,
        "reason_codes": sorted(reasons),
        "raw_as_traded_authority": RAW_AS_TRADED_AUTHORITY,
        "authority_effect": "NONE",
    }
    context["context_identity"] = "price_basis_context:" + _identity(context)
    return context


def current_research_context_from_technical_features(
    *, ticker: str, technical_features: Mapping[str, Any], source_artifact_identity: str | None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Adapt an existing Current Research technical record without changing its output.

    Existing technical artifacts declare ``ADJUSTED_RETROSPECTIVE`` and retain their own source
    lineage.  The adapter exposes that declaration as the more precise current-basis vocabulary,
    while preserving absent provider/factor-chain fields as explicit gaps rather than assuming
    DNSE or inventing a corporate-action chain.
    """
    session = technical_features.get("feature_as_of_session")
    provenance_record = technical_features.get("technical_history_provenance") or {}
    provenance = [str(source_artifact_identity)] if source_artifact_identity else []
    if isinstance(provenance_record, Mapping) and provenance_record.get("source"):
        provenance.append(str(provenance_record["source"]))
    reasons: list[str] = []
    if not provider:
        reasons.append("PROVIDER_IDENTITY_NOT_RETAINED_IN_TECHNICAL_FEATURE_CONTEXT")
    return price_series_context(
        ticker=ticker,
        provider=provider,
        source_identity=source_artifact_identity,
        session_start=str(session) if session else None,
        session_end=str(session) if session else None,
        observed_basis=str(technical_features.get("price_basis") or BASIS_UNKNOWN),
        basis_provenance=provenance,
        basis_confidence="SOURCE_SCOPED_CURRENT_RESEARCH_ONLY",
        basis_lineage_identity=source_artifact_identity,
        reason_codes=reasons,
    )


def _context_problems(context: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if context.get("observed_basis") not in BASIS_VOCABULARY or context.get("observed_basis") == BASIS_UNKNOWN:
        problems.append(REASON_BASIS_UNKNOWN)
    if not context.get("source_identity"):
        problems.append(REASON_SOURCE_IDENTITY_MISSING)
    if not context.get("session_start") or not context.get("session_end"):
        problems.append(REASON_DATE_RANGE_MISSING)
    if not context.get("basis_provenance"):
        problems.append(REASON_PROVENANCE_MISSING)
    return sorted(set(problems))


def _anomaly_context(observed_price_divergence_pct: float | None) -> dict[str, Any]:
    if not isinstance(observed_price_divergence_pct, (int, float)):
        return {"observed_price_divergence_pct": None, "authority_gate": False, "reason_codes": []}
    return {
        "observed_price_divergence_pct": float(observed_price_divergence_pct),
        "authority_gate": False,
        "reason_codes": [REASON_NUMERIC_DIVERGENCE_ANOMALY_ONLY],
    }


def _same_lineage(current: Mapping[str, Any], history: Mapping[str, Any]) -> bool:
    current_lineage, history_lineage = current.get("basis_lineage_identity"), history.get("basis_lineage_identity")
    if current_lineage and history_lineage and current_lineage == history_lineage:
        return True
    current_chain = (current.get("corporate_action_factor_chain") or {}).get("identity")
    history_chain = (history.get("corporate_action_factor_chain") or {}).get("identity")
    return bool(current_chain and current_chain == history_chain)


def _pit_context_is_qualified(context: Mapping[str, Any], decision_as_of: str | None) -> tuple[bool, str]:
    if context.get("observed_basis") != POINT_IN_TIME_ADJUSTED:
        return False, REASON_PIT_REQUIRES_POINT_IN_TIME_ADJUSTED
    chain = context.get("corporate_action_factor_chain") or {}
    if chain.get("status") != "QUALIFIED" or not chain.get("identity"):
        return False, REASON_PIT_FACTOR_CHAIN_UNQUALIFIED
    cutoff = context.get("adjustment_knowledge_cutoff") or chain.get("knowledge_cutoff")
    if _instant(cutoff) is None or _instant(decision_as_of) is None:
        return False, REASON_PIT_CUTOFF_MISSING
    if _instant(cutoff) > _instant(decision_as_of):
        return False, REASON_PIT_FACTOR_AFTER_DECISION
    return True, "PIT_ADJUSTMENT_KNOWABLE_BY_DECISION_CUTOFF"


def evaluate_feature_fitness(
    *,
    feature: str,
    current_context: Mapping[str, Any],
    history_context: Mapping[str, Any] | None = None,
    decision_as_of: str | None = None,
    observed_price_divergence_pct: float | None = None,
) -> dict[str, Any]:
    """Return one deterministic semantic-fitness verdict for a price-derived use.

    The evaluator intentionally knows no price levels.  A caller may retain a numerical
    divergence for diagnostics, but that value never affects ``state`` or ``reason_codes``.
    """
    if feature not in PRICE_DERIVED_FEATURES:
        raise PriceBasisFitnessError(f"UNKNOWN_PRICE_DERIVED_FEATURE:{feature}")
    history = history_context or current_context
    current = dict(current_context)
    historical = dict(history)
    reasons = _context_problems(current) + _context_problems(historical)
    anomaly = _anomaly_context(observed_price_divergence_pct)

    if reasons:
        state = BASIS_UNVERIFIED
    elif feature == EXECUTION_RAW_REPLAY:
        if current.get("observed_basis") != RAW_AS_TRADED or historical.get("observed_basis") != RAW_AS_TRADED:
            state, reasons = BASIS_INCOMPATIBLE, [REASON_EXECUTION_REQUIRES_RAW]
        else:
            state, reasons = BASIS_INCOMPATIBLE, [REASON_RAW_AS_TRADED_NOT_PROMOTED]
    elif feature == PIT_BACKTEST:
        current_ready, current_reason = _pit_context_is_qualified(current, decision_as_of)
        history_ready, history_reason = _pit_context_is_qualified(historical, decision_as_of)
        if not current_ready or not history_ready:
            state, reasons = POINT_IN_TIME_SEMANTICS_UNQUALIFIED, sorted({current_reason, history_reason})
        elif current.get("observed_basis") != historical.get("observed_basis") or not _same_lineage(current, historical):
            state, reasons = BASIS_INCOMPATIBLE, [REASON_BASIS_MISMATCH if current.get("observed_basis") != historical.get("observed_basis") else REASON_LINEAGE_MISMATCH]
        else:
            state, reasons = BASIS_COMPATIBLE, ["PIT_FACTORS_AND_SERIES_KNOWABLE_BY_DECISION_CUTOFF"]
    elif current.get("observed_basis") != historical.get("observed_basis"):
        state, reasons = BASIS_INCOMPATIBLE, [REASON_BASIS_MISMATCH]
    elif not _same_lineage(current, historical):
        state, reasons = BASIS_INCOMPATIBLE, [REASON_LINEAGE_MISMATCH]
    elif current.get("observed_basis") == CURRENT_RETROSPECTIVE_ADJUSTED:
        state, reasons = BASIS_COMPATIBLE_RESEARCH_ONLY, [REASON_CURRENT_ADJUSTED_RESEARCH_ONLY]
    elif current.get("observed_basis") == POINT_IN_TIME_ADJUSTED:
        state, reasons = BASIS_COMPATIBLE, ["POINT_IN_TIME_ADJUSTED_LINEAGE_COMPATIBLE"]
    elif current.get("observed_basis") == RAW_AS_TRADED:
        state, reasons = BASIS_UNVERIFIED, [REASON_RAW_AS_TRADED_NOT_PROMOTED]
    else:
        state, reasons = BASIS_UNVERIFIED, [REASON_BASIS_UNKNOWN]

    result = {
        "contract_version": CONTRACT_VERSION,
        "feature": feature,
        "state": state,
        "reason_codes": sorted(set(reasons)),
        "current_context_identity": current.get("context_identity"),
        "history_context_identity": historical.get("context_identity"),
        "decision_as_of": decision_as_of,
        "numeric_divergence": anomaly,
        "authority_effect": "NONE",
        "not_an_execution_or_backtest_authorization": True,
    }
    result["fitness_identity"] = "price_basis_feature_fitness:" + _identity(result)
    return result


def contract_summary() -> dict[str, Any]:
    """Return the closed vocabulary for reporting and validation, without any price values."""
    return {
        "contract_version": CONTRACT_VERSION,
        "basis_vocabulary": sorted(BASIS_VOCABULARY),
        "feature_vocabulary": sorted(PRICE_DERIVED_FEATURES),
        "fitness_states": sorted(FITNESS_STATES),
        "raw_as_traded_authority": RAW_AS_TRADED_AUTHORITY,
        "numeric_divergence_is_authority_gate": False,
        "record_date_inferred_as_ex_date": False,
        "authority_effect": "NONE",
    }
