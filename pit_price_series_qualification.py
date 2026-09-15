"""Deterministic point-in-time (PIT) price-series qualification boundary.

WHAT THIS IS
    A session-by-session verdict boundary that combines two independently-qualified inputs --
    (1) a bounded, provider-scoped raw-input price-basis authority
    (``provider_price_basis_registry.bounded_price_basis_for``) and (2) qualified corporate-action
    factor-chain entries (``qualified_corporate_action_factor_chain.build_factor_chain_entry``)
    -- into an explicit ``QUALIFIED`` / ``PARTIAL`` / ``BLOCKED`` verdict for a caller-supplied,
    explicit list of sessions. It computes no price value and transforms no series; it only
    decides whether a requested session is safe to treat as point-in-time for a decision made
    as of a given cutoff.

WHAT THIS IS NOT
    - Not a price reconstructor: it never derives a raw price from an adjusted one.
    - Not a series filler: a session the caller did not request is never invented, and a missing
      session is never silently skipped over as if it were present.
    - Not a splice point: sessions are evaluated against exactly the bounded authority that
      names them; two incompatible provider windows are never merged into one continuous claim.
    - Not a promotion of "continuous" to "point-in-time": a current retrospectively-adjusted
      series that happens to have no gaps is still not PIT merely for being unbroken -- PIT
      requires an explicit, knowledge-cutoff-bounded factor chain for every applicable event,
      not just basis continuity.

NO-LOOK-AHEAD
    A qualified factor whose ``knowledge_cutoff`` is after the caller's ``decision_as_of`` blocks
    the session it would adjust: an event that occurred historically but became known only later
    cannot rewrite what a strategy could have known earlier.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import price_basis_feature_fitness as fitness
import provider_price_basis_registry as basis_registry

CONTRACT_VERSION = "pit_price_series_qualification/v1"
SCHEMA_VERSION = "1.0.0"

QUALIFIED = "QUALIFIED"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
SERIES_STATES = frozenset({QUALIFIED, PARTIAL, BLOCKED})

_ELIGIBLE_RAW_INPUT_BASES = frozenset({"RAW_AS_TRADED", "ADJUSTED_RETROSPECTIVE"})

REASON_RAW_INPUT_BASIS_UNQUALIFIED = "PIT_SERIES_BLOCKED_RAW_INPUT_BASIS_UNQUALIFIED"
REASON_FACTOR_CHAIN_INCOMPATIBLE = "PIT_SERIES_BLOCKED_FACTOR_CHAIN_INCOMPATIBLE"
REASON_KNOWLEDGE_CUTOFF_MISSING = "PIT_SERIES_BLOCKED_FACTOR_KNOWLEDGE_CUTOFF_MISSING"
REASON_KNOWLEDGE_CUTOFF_AFTER_DECISION = "PIT_SERIES_BLOCKED_FACTOR_KNOWLEDGE_AFTER_DECISION_CUTOFF"
REASON_NO_SESSIONS_REQUESTED = "PIT_SERIES_NO_SESSIONS_REQUESTED"
REASON_DECISION_AS_OF_MISSING = "PIT_SERIES_DECISION_AS_OF_MISSING"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def qualify_session(
    *,
    provider: str,
    dataset: str,
    instrument: str,
    session: str,
    decision_as_of: str | None,
    factor_chain_entries: Sequence[Mapping[str, Any]] = (),
    authorities: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """One deterministic verdict for a single requested session."""
    if not decision_as_of:
        return {"session": session, "state": BLOCKED, "reason_codes": [REASON_DECISION_AS_OF_MISSING]}

    raw = basis_registry.bounded_price_basis_for(provider, dataset, instrument, session, authorities=authorities)
    raw_basis = raw.get("price_basis")
    if raw_basis not in _ELIGIBLE_RAW_INPUT_BASES:
        return {
            "session": session, "state": BLOCKED,
            "reason_codes": [REASON_RAW_INPUT_BASIS_UNQUALIFIED, str(raw.get("reason") or "")],
        }

    # Every qualified factor-chain event whose ex-date falls on or after this session would
    # adjust this session's raw observation; each such event must itself be QUALIFIED and
    # knowable strictly by decision_as_of, or the session fails closed.
    applicable = [
        entry for entry in factor_chain_entries
        if entry.get("ex_date") and str(entry["ex_date"]) >= str(session)
    ]
    for entry in applicable:
        event_ref = f"event:{entry.get('source_event_id') or entry.get('identity')}"
        if entry.get("status") != "QUALIFIED":
            return {"session": session, "state": BLOCKED,
                    "reason_codes": [REASON_FACTOR_CHAIN_INCOMPATIBLE, event_ref]}
        cutoff = entry.get("knowledge_cutoff")
        if not cutoff:
            return {"session": session, "state": BLOCKED,
                    "reason_codes": [REASON_KNOWLEDGE_CUTOFF_MISSING, event_ref]}
        if str(cutoff) > str(decision_as_of):
            return {"session": session, "state": BLOCKED,
                    "reason_codes": [REASON_KNOWLEDGE_CUTOFF_AFTER_DECISION, event_ref]}

    return {
        "session": session, "state": QUALIFIED, "reason_codes": [],
        "raw_input_basis": raw_basis,
        "raw_input_authority_reason": raw.get("reason"),
        "applicable_factor_event_ids": sorted({
            str(entry.get("source_event_id") or entry.get("identity")) for entry in applicable
        }),
    }


def qualify_pit_price_series(
    *,
    ticker: str | None,
    provider: str,
    dataset: str,
    instrument: str,
    sessions: Sequence[str],
    decision_as_of: str | None,
    factor_chain_entries: Sequence[Mapping[str, Any]] = (),
    authorities: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Session-by-session PIT verdict for an explicit, caller-supplied list of sessions.

    ``sessions`` must already be the exact set the caller needs; this never fills a missing
    session and never infers a session range from a start/end pair.
    """
    if not sessions:
        result = {
            "contract_version": CONTRACT_VERSION, "schema_version": SCHEMA_VERSION,
            "ticker": str(ticker).upper() if ticker else None, "provider": provider,
            "dataset": dataset, "instrument": instrument, "decision_as_of": decision_as_of,
            "state": BLOCKED, "reason_codes": [REASON_NO_SESSIONS_REQUESTED],
            "sessions": [], "qualified_session_count": 0, "blocked_session_count": 0,
            "total_session_count": 0,
        }
        result["series_identity"] = "pit_price_series_qualification:" + _identity(
            {key: value for key, value in result.items() if key != "series_identity"})
        return result

    per_session = [
        qualify_session(provider=provider, dataset=dataset, instrument=instrument, session=session,
                        decision_as_of=decision_as_of, factor_chain_entries=factor_chain_entries,
                        authorities=authorities)
        for session in sessions
    ]
    states = {entry["state"] for entry in per_session}
    if states == {QUALIFIED}:
        overall = QUALIFIED
    elif QUALIFIED in states:
        overall = PARTIAL
    else:
        overall = BLOCKED

    result = {
        "contract_version": CONTRACT_VERSION, "schema_version": SCHEMA_VERSION,
        "ticker": str(ticker).upper() if ticker else None, "provider": str(provider).upper() if provider else None,
        "dataset": dataset, "instrument": str(instrument).upper() if instrument else None,
        "decision_as_of": decision_as_of, "state": overall,
        "sessions": per_session,
        "qualified_session_count": sum(1 for entry in per_session if entry["state"] == QUALIFIED),
        "blocked_session_count": sum(1 for entry in per_session if entry["state"] == BLOCKED),
        "total_session_count": len(per_session),
    }
    result["series_identity"] = "pit_price_series_qualification:" + _identity(
        {key: value for key, value in result.items() if key != "series_identity"})
    return result


def price_series_context_for_pit(
    *,
    ticker: str | None,
    provider: str | None,
    source_identity: str | None,
    session_start: str | None,
    session_end: str | None,
    series_qualification: Mapping[str, Any],
    factor_chain_entry: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Feed a series-qualification verdict into ``price_basis_feature_fitness.price_series_context``.

    ``observed_basis`` is only ever declared ``POINT_IN_TIME_ADJUSTED`` when the series verdict
    itself reached ``QUALIFIED`` for every requested session and a qualified factor-chain entry
    was supplied; a ``PARTIAL`` or ``BLOCKED`` verdict is passed through as ``BASIS_UNKNOWN`` so
    ``evaluate_feature_fitness`` correctly reports ``POINT_IN_TIME_SEMANTICS_UNQUALIFIED``.
    """
    fully_qualified = series_qualification.get("state") == QUALIFIED and factor_chain_entry is not None \
        and factor_chain_entry.get("status") == "QUALIFIED"
    observed_basis = fitness.POINT_IN_TIME_ADJUSTED if fully_qualified else fitness.BASIS_UNKNOWN
    return fitness.price_series_context(
        ticker=ticker,
        provider=provider,
        source_identity=source_identity,
        session_start=session_start,
        session_end=session_end,
        observed_basis=observed_basis,
        basis_provenance=[f"pit_price_series_qualification:{series_qualification.get('state', 'UNKNOWN')}"],
        basis_confidence="PIT_SERIES_QUALIFICATION_DERIVED" if fully_qualified else "UNVERIFIED",
        basis_lineage_identity=series_qualification.get("series_identity"),
        adjustment_knowledge_cutoff=(factor_chain_entry or {}).get("knowledge_cutoff") if fully_qualified else None,
        factor_chain=factor_chain_entry if fully_qualified else None,
        reason_codes=() if fully_qualified else tuple(series_qualification.get("reason_codes") or ()),
    )


def contract_summary() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "series_states": sorted(SERIES_STATES),
        "eligible_raw_input_bases": sorted(_ELIGIBLE_RAW_INPUT_BASES),
        "never_fills_missing_sessions": True,
        "never_splices_incompatible_provider_series": True,
        "continuity_alone_never_implies_pit": True,
        "authority_effect": "NONE",
    }
