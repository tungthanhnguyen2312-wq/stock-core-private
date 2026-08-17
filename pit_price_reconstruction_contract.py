"""P0-A.3A: the point-in-time price-reconstruction eligibility contract.

WHAT THIS IS
    A deterministic, read-only classifier: given a ticker, session, and knowledge_cutoff, it
    decides whether a point-in-time-safe price (or price-adjustment) may be treated as
    reconstructible -- and if not, exactly why. It is the semantic boundary P0-A.3 needs before
    it may reconstruct any price authoritatively. It is deliberately **not** a price calculator:
    it never reads or multiplies an actual OHLC value, never fetches anything, and never writes
    runtime state. "Reconstruction" here means the eligibility verdict that must exist before a
    later milestone may compute one.

    The correct success condition is not many ``QUALIFIED`` verdicts. It is classifying the
    full P0-A.1 universe honestly, with zero false PIT qualification -- see
    ``classify_universe`` and the module docstring's "WHY MOST VERDICTS ARE NOT QUALIFIED" note.

THE TEMPORAL MODEL
    Two clocks are kept apart everywhere in this module, because collapsing them is exactly
    the look-ahead bug this contract exists to close:

    MARKET / EVENT TIME -- when the underlying market fact occurred: a trading session's own
        date, or a corporate action's ``ex_date``. Answers "when did this happen".

    KNOWLEDGE / OBSERVATION TIME -- when the fact became knowable to Stock Lookup: a raw
        observation's ``retrieved_at``, or an official document's ``observed_at``
        (``evidence_knowledge_time``). Answers "when could we have known this".

    A verdict may only use evidence whose knowledge time is at or before ``knowledge_cutoff``.
    Market time is never substituted for knowledge time, and current knowledge is never
    projected backward onto an earlier cutoff.

WHY ``published_at`` IS NEVER PART OF THE GATE
    ``official_document_store`` records both ``observed_at`` (when this pipeline actually
    retained and verified the bytes) and an optional ``published_at`` (the date the document
    itself claims). Real retained evidence in this repository shows the two routinely weeks
    apart -- e.g. the retained HPG issuer-IR notice states ``published_at: "2026-07-07"`` but
    was not retained until ``observed_at: "2026-08-02T08:10:00Z"``. The legacy, non-authoritative
    ``point_in_time_adjusted_prices.py`` admits a factor when
    ``verified_at <= knowledge_cutoff or decl <= knowledge_cutoff`` -- an OR of exactly these two
    fields. That lets a cutoff sitting between the two dates admit a document this pipeline could
    not actually have had yet, because the early claimed-published date alone satisfies the OR.
    ``evidence_knowledge_time`` in this module returns ``observed_at`` only; ``published_at`` is
    carried in verdict provenance for display and never compared against a cutoff. See
    ``test_pit_price_reconstruction_contract.py``'s look-ahead-gate tests for the direct
    regression against this exact pattern.

REQUIRED OUTPUT VIEW MODES
    ``PIT_AS_KNOWN`` -- a verdict may use only evidence legitimately knowable by
        ``knowledge_cutoff``. Eligible in principle for point-in-time research/backtest use.
    ``RETROSPECTIVE_RESTATED`` -- uses the best currently available evidence, even evidence that
        became known after the historical point being represented. Useful for retrospective
        charting; must never silently become PIT/backtest input. A caller must pass ``mode``
        explicitly -- there is no default, so a caller cannot forget which one it asked for.

WHY MOST VERDICTS ARE NOT QUALIFIED
    DNSE is the only active OHLC provider (``market_data_source_authority.py``), and its own
    qualified capability record is explicit: ``BACKTEST_POINT_IN_TIME_SAFE = False``
    (``dnse_ohlc_price_basis_capability.py``) -- proven, not assumed: the same historical
    calendar date returns different bytes before and after a corporate action. A *current* query
    against DNSE's historical endpoint is therefore never ``PIT_AS_KNOWN``-eligible. Within the
    two narrow HPG/VCB windows ``provider_price_basis_registry.bounded_price_basis_for``
    resolves, the basis is ``ADJUSTED_RETROSPECTIVE`` -- eligible for ``RETROSPECTIVE_RESTATED``,
    never for ``PIT_AS_KNOWN``. Outside those windows, and for every other instrument, price
    basis is ``UNKNOWN``. This is the expected, correct shape of the result, not a shortfall.

POSITIVE-AUTHORITY REQUIREMENT FOR ``PIT_AS_KNOWN`` PRICE BASIS
    An earlier version of this module let a caller-supplied ``contemporaneous_raw_observation``
    reach ``QUALIFIED`` purely because its self-reported ``retrieved_at`` sat close to the
    session -- an independent audit correctly found this let an arbitrary, wholly unauthenticated
    caller dict (``{"retrieved_at": "..."}``, with no connection to any actual retained evidence)
    grant PIT eligibility to any ticker. Temporal proximity alone was never a valid authority; it
    only ever *would have been* safe underneath a source that had already been positively shown
    raw-as-traded, which no source in this repository has. ``_price_basis_state`` now requires
    two things to both hold, in order, before ``contemporaneous_raw_observation`` is even
    considered:

    1. ``provider_price_basis_registry.bounded_price_basis_for`` must itself resolve this exact
       (provider, dataset, ticker, session) to ``market_data_contracts.PriceBasis.RAW_AS_TRADED``
       -- an existing, positive authority verdict, never inferred or invented here. Every bounded
       authority in this repository today asserts ``ADJUSTED_RETROSPECTIVE``, never
       ``RAW_AS_TRADED``, so this gate is not reachable with current real evidence -- see
       ``_RAW_OBSERVATION_IDENTITY_FIELDS`` for the second gate, exercised only via a synthetic
       authority in tests.
    2. Only once (1) holds does the supplied observation's own shape matter: it must carry every
       field ``market_data_contracts.RawObservation`` requires for a retained observation's
       identity (``provider``, ``dataset``, ``instrument``, ``retrieved_at``, ``request_identity``,
       ``raw_payload_hash``, ``schema_version``), matching this exact query, itself knowable by
       ``knowledge_cutoff``, and -- last, and only as a supporting check, never a sufficient one
       on its own -- genuinely contemporaneous with the session.

    Given today's real authority, it is expected and correct that ``PIT_AS_KNOWN`` price basis
    never reaches ``QUALIFIED`` for any real ticker. That is the honest state of the evidence, not
    a defect to work around.

CORPORATE-ACTION GATING, INCLUDING THE CASH-DIVIDEND ADDITIVE BOUNDARY
    ``official_corporate_action_ledger.event_key()`` links observations by share-count identity,
    so a pure cash-dividend observation (no share count) can never become a ledger *entry* -- it
    lands in ``unlinked_observations`` and is otherwise invisible to a caller that only reads
    ``entries``. That would make a real, retained cash-dividend fact silently disappear from this
    contract's view. ``_corporate_action_state`` therefore treats any cutoff-eligible observation
    whose ``event_type`` is price-relevant (dilutive, concentrating, or ``cash_dividend``) as its
    own blocking candidate: a share-count event blocks unless the ledger links it to a
    ``FACTOR_READY`` entry with an explicit ``ex_date``; a cash-dividend event blocks
    unconditionally, because this repository has no qualified, non-ticker-specific methodology
    for turning a cash amount into a price-adjustment factor (the one available data point --
    VCB's empirically observed ~0.9917 factor for a 450 VND dividend --  is a single-event,
    single-ticker magnitude, not a portable formula, and applying it to a different amount or
    ticker would be exactly the fabrication this project's doctrine forbids). Nothing here
    modifies ``event_key()`` or any P0-A.2 extraction semantics.

RELATIONSHIP TO ``dnse_prospective_pit_shadow.py`` (Phase 1 reconciliation, P0-A.3A)
    That module is a separate, untracked, EXPERIMENT_SHADOW-only live WebSocket forward-capture
    prototype for closed intraday OHLC bars: append-only, receipt-time-stamped, and it already
    distinguishes first receipt / revision / duplicate-identical, and receipt time from the
    provider's own ``time``/``lastUpdated`` fields. That is the same MARKET-TIME-vs-KNOWLEDGE-TIME
    distinction this module formalizes, independently re-derived here for a different, backward-
    looking problem (deterministically classifying already-retained historical evidence, not
    capturing new live ticks). This module does not import, extend, or execute any part of it,
    acquires no live observations, and does not create a second forward-capture subsystem --
    disposition ``DEFER``, not ``PORT_SELECTED_PARTS``: the two systems solve disjoint problems
    and can coexist without collision.

MODE ISOLATION: ``pit_backtest_eligible``
    ``verdict == QUALIFIED`` is reachable under ``RETROSPECTIVE_RESTATED`` for real bounded
    evidence (HPG/VCB) -- that is a legitimate retrospective-charting qualification, not a bug.
    But a generic ``verdict``/``qualified_tickers``-shaped field is exactly the kind of value a
    downstream consumer could misread as PIT/backtest-safe regardless of which mode produced it.
    Every verdict record therefore also carries an explicit, derived ``pit_backtest_eligible``
    boolean, true only when ``mode == PIT_AS_KNOWN and verdict == QUALIFIED`` -- always false for
    ``RETROSPECTIVE_RESTATED``, even a ``QUALIFIED`` one. ``classify_universe`` exposes
    ``pit_backtest_eligible_tickers`` and ``retrospective_qualified_tickers`` as two explicit,
    unambiguous lists in place of a single generic ``qualified_tickers``.

ALLOWED DEPENDENCIES
    ``provider_price_basis_registry`` and ``dnse_ohlc_price_basis_capability`` for price basis;
    ``official_corporate_action_ledger`` for share-count-linked corporate-action reconciliation
    (consumed, not modified); ``market_data_contracts`` for the existing ``PriceBasis`` vocabulary
    (``RAW_AS_TRADED`` in particular) and the existing ``RawObservation`` identity-field shape --
    both read as vocabulary/shape references only, nothing from either module is mutated.
    ``corporate_action_events``, ``official_document_store``, ``market_raw_lake``, and
    ``market_data_source_authority`` inform the shapes this module consumes but are not imported,
    to keep this module a pure classifier with no I/O.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
    No network call, no database write, no runtime-root write, no live observation capture, no
    numeric adjusted-price computation, no ticker-specific branch, no rewrite of legacy
    ``point_in_time_adjusted_prices.py`` / ``point_in_time_market_risk.py``, no change to
    ``official_corporate_action_ledger.event_key()``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import market_data_contracts
import official_corporate_action_ledger as ledger
import provider_price_basis_registry as price_basis_registry

VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# --- Required output view modes -----------------------------------------------------

MODE_PIT_AS_KNOWN = "PIT_AS_KNOWN"
MODE_RETROSPECTIVE_RESTATED = "RETROSPECTIVE_RESTATED"
VIEW_MODES = frozenset({MODE_PIT_AS_KNOWN, MODE_RETROSPECTIVE_RESTATED})

# --- Verdict states, applied conservatively -------------------------------------------
#
# QUALIFIED only when every dependency is itself qualified or genuinely not applicable.
# PARTIAL when at least one dependency is qualified but another is merely unresolved
# (UNKNOWN), never when one is actively BLOCKED -- an active obstruction always dominates.

QUALIFIED = "QUALIFIED"
PARTIAL = "PARTIAL"
UNKNOWN = "UNKNOWN"
BLOCKED = "BLOCKED"
NOT_APPLICABLE = "NOT_APPLICABLE"
VERDICT_STATES = frozenset({QUALIFIED, PARTIAL, UNKNOWN, BLOCKED, NOT_APPLICABLE})

# --- Acquisition-status vocabulary, reusing P0-A.1's own terms ------------------------

ACQUISITION_STATUS_SUCCESS = "SUCCESS"
ACQUISITION_STATUS_PERMANENT = "PERMANENT"

# --- Instrument-class scope ------------------------------------------------------------
#
# This contract consumes an already-classified instrument_class (P0-C's job, not this
# module's); it never infers equity-ness itself. A snapshot instrument_class is a *current*
# classification fact, used here only as a coarse in-scope/out-of-scope gate -- never as a
# claim that the instrument was listed, active, or equity-classified on any historical session
# (P0-C's own ACTIVE_UNIVERSE stays structurally UNKNOWN; this module does not touch it and
# never backdates a current label onto history).

_EQUITY_INSTRUMENT_CLASSES = frozenset({"EQUITY"})

# --- Price-relevant corporate-action event types --------------------------------------

_SHARE_COUNT_EVENT_TYPES = frozenset({"stock_dividend", "bonus_shares", "stock_split", "reverse_split"})
_PRICE_RELEVANT_EVENT_TYPES = _SHARE_COUNT_EVENT_TYPES | frozenset({"cash_dividend"})

# --- Identity a caller-supplied raw observation must carry before it is even considered -----
#
# Matches market_data_contracts.RawObservation's own required fields exactly -- an existing
# contract, not a new one invented here. Presence of these fields is necessary but never
# sufficient: see the module docstring's "POSITIVE-AUTHORITY REQUIREMENT" note. A caller cannot
# grant itself PIT authority merely by supplying plausible-looking field names.

_RAW_OBSERVATION_IDENTITY_FIELDS = (
    "provider", "dataset", "instrument", "retrieved_at", "request_identity",
    "raw_payload_hash", "schema_version",
)

# --- Reason codes (exhaustive, deterministic vocabulary) ------------------------------

REASON_OUT_OF_EQUITY_SCOPE = "instrument_class_outside_ohlc_eligible_equity_scope"
REASON_PERMANENT_PROVIDER_INVALID = "permanent_provider_invalid_no_retained_ohlc_observation"
REASON_ACQUISITION_NOT_SUCCESSFUL = "acquisition_status_not_successful_no_retained_ohlc_observation"

REASON_PRICE_BASIS_UNKNOWN = "source_price_basis_unknown_for_provider_dataset_instrument_session"
REASON_PRICE_BASIS_RETROSPECTIVE_ONLY = (
    "source_basis_retrospective_restated_only_current_query_not_pit_as_known_safe")
REASON_NO_CONTEMPORANEOUS_OBSERVATION = (
    "no_contemporaneous_raw_observation_supplied_current_query_not_pit_safe")
REASON_OBSERVATION_NOT_CONTEMPORANEOUS = (
    "supplied_raw_observation_not_contemporaneous_with_session_backfill_capture_not_pit_safe")
REASON_OBSERVATION_NOT_KNOWABLE_BY_CUTOFF = "supplied_raw_observation_retrieved_after_knowledge_cutoff"
REASON_OBSERVATION_NOT_AUTHORITATIVE = "contemporaneous_observation_not_authoritative_for_pit_price_basis"
REASON_PRICE_BASIS_BOUNDED_AUTHORITY_APPLIES = "bounded_price_basis_authority_applies"
REASON_PRICE_BASIS_CONTEMPORANEOUS_OBSERVATION_PROVEN = (
    "contemporaneous_raw_observation_proves_pit_as_known_basis")
REASON_INVALID_SESSION_OR_CUTOFF = "session_or_knowledge_cutoff_not_a_parseable_date"

REASON_NO_EVIDENCE_SUPPLIED = "no_retained_corporate_action_evidence_supplied_for_instrument"
REASON_NO_EVIDENCE_KNOWABLE_BY_CUTOFF = "no_corporate_action_evidence_knowable_by_knowledge_cutoff"
REASON_NO_PRICE_RELEVANT_EVENT = "retained_evidence_considered_no_price_relevant_event_type_applies"
REASON_MISSING_EXPLICIT_EX_DATE = "missing_explicit_official_ex_date"
REASON_SHARE_COUNT_IDENTITY_UNAVAILABLE = "share_count_identity_unavailable_event_unlinked_from_ledger"
REASON_LEDGER_ENTRY_NOT_QUALIFIED = "ledger_entry_not_qualified"
REASON_CASH_DIVIDEND_AMOUNT_UNQUALIFIED = "cash_dividend_amount_not_qualified"
REASON_CASH_DIVIDEND_NO_FACTOR_METHODOLOGY = (
    "cash_dividend_adjustment_factor_methodology_not_qualified_never_fabricated")
REASON_CORPORATE_ACTION_QUALIFIED = "qualified_ex_dated_adjustment_factor_available_for_session"
REASON_CORPORATE_ACTION_NOT_APPLICABLE = "relevant_events_considered_none_apply_to_this_session"

REASON_DEPENDENCY_UNRESOLVED_PARTIAL = "price_basis_qualified_corporate_action_dependency_unresolved"
REASON_TICKER_SCOPE_BLOCKED = "ticker_scope_blocked"
REASON_TICKER_OUT_OF_SCOPE = "ticker_out_of_scope"

REASON_CODES = frozenset(
    value for name, value in list(globals().items())
    if name.startswith("REASON_") and isinstance(value, str)
)


class PitPriceReconstructionContractError(ValueError):
    """Fail-closed rejection for a malformed input this contract will not silently guess at."""


# --- Small deterministic helpers, each private to this module (repo convention) -------

def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_date(value: Any) -> date | None:
    """A calendar date without guessing a malformed or partial timestamp."""
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _parse_instant(value: Any) -> datetime | None:
    """A timezone-aware instant for knowledge-time comparison.

    A bare ``YYYY-MM-DD`` date is read as the *end* of that calendar day (23:59:59.999999 UTC)
    -- the generous "knowable by the end of this date" reading, so it never accidentally
    excludes same-day evidence. A full ISO-8601 timestamp (``...Z`` or an explicit offset) is
    parsed exactly. A naive full timestamp (no offset) is assumed UTC, matching every retained
    ``observed_at`` value in this repository's real evidence, which is always ``...Z``-suffixed;
    this module never guesses a non-UTC offset.
    """
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


def _instant_le(value: Any, cutoff: Any) -> bool | None:
    """``value <= cutoff``, or ``None`` when either side does not parse -- never a guess."""
    left = _parse_instant(value)
    right = _parse_instant(cutoff)
    if left is None or right is None:
        return None
    return left <= right


def evidence_knowledge_time(observation: Mapping[str, Any]) -> str | None:
    """The instant one corporate-action observation actually became knowable to Stock Lookup.

    Deliberately ``observed_at`` only -- see the module docstring's "WHY ``published_at`` IS
    NEVER PART OF THE GATE" for the exact legacy anti-pattern this refuses to repeat.
    """
    value = observation.get("observed_at")
    return str(value) if value else None


# --- Stage 1: ticker/instrument scope ---------------------------------------------------

def _ticker_scope_state(*, instrument_class: str | None, acquisition_status: str | None) -> dict[str, Any]:
    if instrument_class is not None and str(instrument_class).strip().upper() not in _EQUITY_INSTRUMENT_CLASSES:
        return {"state": NOT_APPLICABLE, "reason": REASON_OUT_OF_EQUITY_SCOPE,
                "instrument_class": str(instrument_class).strip().upper()}
    if acquisition_status is not None:
        normalized_status = str(acquisition_status).strip().upper()
        if normalized_status == ACQUISITION_STATUS_PERMANENT:
            return {"state": BLOCKED, "reason": REASON_PERMANENT_PROVIDER_INVALID,
                    "acquisition_status": normalized_status}
        if normalized_status != ACQUISITION_STATUS_SUCCESS:
            return {"state": BLOCKED, "reason": REASON_ACQUISITION_NOT_SUCCESSFUL,
                    "acquisition_status": normalized_status}
    return {"state": QUALIFIED, "reason": None, "acquisition_status": acquisition_status}


# --- Stage 2: price basis ---------------------------------------------------------------

def _is_contemporaneous(retrieved_at: Any, session: date, *, grace_days: int = 1) -> bool | None:
    parsed = _parse_instant(retrieved_at)
    if parsed is None:
        return None
    delta_days = (parsed.date() - session).days
    return 0 <= delta_days <= grace_days


def _price_basis_state(
    *, mode: str, provider: str, dataset: str, ticker: str, session: date, knowledge_cutoff: str,
    price_basis_authorities: Sequence[Mapping[str, Any]] | None,
    contemporaneous_raw_observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    bounded = price_basis_registry.bounded_price_basis_for(
        provider, dataset, ticker, session.isoformat(), authorities=price_basis_authorities)
    basis = bounded.get("price_basis")

    if mode == MODE_RETROSPECTIVE_RESTATED:
        if basis and basis != "UNKNOWN":
            return {"state": QUALIFIED, "reason": REASON_PRICE_BASIS_BOUNDED_AUTHORITY_APPLIES,
                    "source_price_basis": basis, "bounded_authority": bounded.get("authority")}
        return {"state": UNKNOWN, "reason": REASON_PRICE_BASIS_UNKNOWN, "source_price_basis": basis}

    # MODE_PIT_AS_KNOWN. Two positive-authority requirements, both required, checked in order --
    # see the module docstring's "POSITIVE-AUTHORITY REQUIREMENT" note. Neither is ever inferred.
    #
    # (1) The source/dataset/session itself must already carry an EXISTING, authoritative
    #     RAW_AS_TRADED verdict from bounded_price_basis_for. A bounded ADJUSTED_RETROSPECTIVE
    #     authority describes the *current* query's basis, proven retrospectively rewritten --
    #     never sufficient for PIT_AS_KNOWN, regardless of what a caller supplies. This gate is
    #     not reachable with any real evidence in this repository today: no bounded authority
    #     anywhere ever asserts RAW_AS_TRADED. A caller cannot satisfy it merely by attaching a
    #     plausible-looking observation -- that would be exactly the self-asserted authority this
    #     gate exists to refuse.
    if basis != market_data_contracts.PriceBasis.RAW_AS_TRADED:
        if contemporaneous_raw_observation is not None:
            return {"state": BLOCKED, "reason": REASON_OBSERVATION_NOT_AUTHORITATIVE,
                    "source_price_basis": basis}
        if basis and basis != "UNKNOWN":
            return {"state": BLOCKED, "reason": REASON_PRICE_BASIS_RETROSPECTIVE_ONLY,
                    "source_price_basis": basis}
        return {"state": UNKNOWN, "reason": REASON_PRICE_BASIS_UNKNOWN, "source_price_basis": basis}

    # (2) Requirement (1) is met: the source/session pair is positively RAW_AS_TRADED. A
    # temporally-close retrieved_at is now a *supporting*, never sufficient, check -- the
    # supplied observation must first carry every identity field an actual retained raw
    # observation would (market_data_contracts.RawObservation's own required shape), matching
    # this exact query.
    if contemporaneous_raw_observation is None:
        return {"state": BLOCKED, "reason": REASON_NO_CONTEMPORANEOUS_OBSERVATION,
                "source_price_basis": basis}
    missing_identity = sorted(field for field in _RAW_OBSERVATION_IDENTITY_FIELDS
                              if not contemporaneous_raw_observation.get(field))
    if missing_identity:
        return {"state": BLOCKED, "reason": REASON_OBSERVATION_NOT_AUTHORITATIVE,
                "source_price_basis": basis, "missing_identity_fields": missing_identity}
    identity_mismatch = (
        str(contemporaneous_raw_observation.get("provider", "")).strip().upper() != str(provider).strip().upper()
        or str(contemporaneous_raw_observation.get("dataset", "")).strip().lower() != str(dataset).strip().lower()
        or str(contemporaneous_raw_observation.get("instrument", "")).strip().upper() != ticker)
    if identity_mismatch:
        return {"state": BLOCKED, "reason": REASON_OBSERVATION_NOT_AUTHORITATIVE,
                "source_price_basis": basis, "identity_mismatch": True}
    retrieved_at = contemporaneous_raw_observation["retrieved_at"]
    knowable = _instant_le(retrieved_at, knowledge_cutoff)
    if knowable is False:
        return {"state": BLOCKED, "reason": REASON_OBSERVATION_NOT_KNOWABLE_BY_CUTOFF,
                "source_price_basis": basis, "retrieved_at": retrieved_at}
    if knowable is None:
        return {"state": BLOCKED, "reason": REASON_INVALID_SESSION_OR_CUTOFF, "source_price_basis": basis}
    contemporaneous = _is_contemporaneous(retrieved_at, session)
    if contemporaneous is not True:
        return {"state": BLOCKED, "reason": REASON_OBSERVATION_NOT_CONTEMPORANEOUS,
                "source_price_basis": basis, "retrieved_at": retrieved_at}
    return {"state": QUALIFIED, "reason": REASON_PRICE_BASIS_CONTEMPORANEOUS_OBSERVATION_PROVEN,
            "source_price_basis": basis, "retrieved_at": retrieved_at}


# --- Stage 3: corporate-action dependency ------------------------------------------------

def _matching_ledger_entry(entries: Sequence[Mapping[str, Any]], ticker: str,
                           event_type: str) -> Mapping[str, Any] | None:
    candidates = [entry for entry in entries
                  if entry.get("ticker") == ticker and entry.get("event_type") == event_type]
    if not candidates:
        return None
    # A ticker/event_type may in principle have more than one distinct share-change identity
    # (e.g. two separate stock dividends over time); the entry actually relevant to a session is
    # whichever one's ex_date brackets it, so every candidate is checked by the caller in turn --
    # this helper returns the full set via the caller's own loop, not a single "best" pick.
    return candidates


def _cash_dividend_candidate_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    amount = observation.get("cash_amount_per_share")
    if not amount:
        return {"state": BLOCKED, "reason": REASON_CASH_DIVIDEND_AMOUNT_UNQUALIFIED}
    if not observation.get("ex_date"):
        return {"state": BLOCKED, "reason": REASON_MISSING_EXPLICIT_EX_DATE}
    # An explicit ex-date alone still never reaches QUALIFIED here: no non-ticker-specific,
    # non-fabricated cash-adjustment-factor methodology is qualified anywhere in this
    # repository -- see the module docstring. A future milestone that qualifies one belongs in
    # its own authority module, not invented inline here.
    return {"state": BLOCKED, "reason": REASON_CASH_DIVIDEND_NO_FACTOR_METHODOLOGY}


def _corporate_action_state(
    observations: Sequence[Mapping[str, Any]], *, ticker: str, session: date, knowledge_cutoff: str,
) -> dict[str, Any]:
    ticker_observations = [obs for obs in observations if str(obs.get("ticker") or "").upper() == ticker]
    if not ticker_observations:
        return {"state": UNKNOWN, "reason": REASON_NO_EVIDENCE_SUPPLIED,
                "considered_observation_ids": [], "excluded_after_cutoff_observation_ids": []}

    as_known: list[Mapping[str, Any]] = []
    excluded: list[str] = []
    for obs in ticker_observations:
        knowledge_time = evidence_knowledge_time(obs)
        knowable = _instant_le(knowledge_time, knowledge_cutoff) if knowledge_time else None
        if knowable is True:
            as_known.append(obs)
        else:
            excluded.append(str(obs.get("observation_id") or obs.get("document_id") or ""))

    relevant = [obs for obs in as_known if obs.get("event_type") in _PRICE_RELEVANT_EVENT_TYPES]
    if not relevant:
        if as_known:
            return {"state": NOT_APPLICABLE, "reason": REASON_NO_PRICE_RELEVANT_EVENT,
                    "considered_observation_ids": [str(o.get("observation_id")) for o in as_known],
                    "excluded_after_cutoff_observation_ids": sorted(excluded)}
        return {"state": UNKNOWN, "reason": REASON_NO_EVIDENCE_KNOWABLE_BY_CUTOFF,
                "considered_observation_ids": [], "excluded_after_cutoff_observation_ids": sorted(excluded)}

    built = ledger.build_ledger(as_known)
    entries = [entry for entry in built["entries"] if entry.get("ticker") == ticker]

    blocking: list[dict[str, Any]] = []
    qualifying: list[dict[str, Any]] = []
    for obs in relevant:
        event_type = obs.get("event_type")
        if event_type == "cash_dividend":
            sub = _cash_dividend_candidate_state(obs)
            blocking.append({"event_type": event_type, "observation_id": obs.get("observation_id"),
                             "reason": sub["reason"]})
            continue
        matches = _matching_ledger_entry(entries, ticker, event_type)
        if not matches:
            blocking.append({"event_type": event_type, "observation_id": obs.get("observation_id"),
                             "reason": REASON_SHARE_COUNT_IDENTITY_UNAVAILABLE})
            continue
        for entry in matches:
            if entry.get("adjustment_factor_status") != ledger.FACTOR_READY:
                reason = (REASON_MISSING_EXPLICIT_EX_DATE
                         if "missing_explicit_official_ex_date" in (entry.get("adjustment_factor_blocked_by") or [])
                         else REASON_LEDGER_ENTRY_NOT_QUALIFIED)
                blocking.append({"event_type": event_type, "event_id": entry.get("event_id"),
                                 "reason": reason,
                                 "adjustment_factor_blocked_by": entry.get("adjustment_factor_blocked_by")})
                continue
            entry_ex_date = _normalized_date(entry.get("ex_date"))
            if entry_ex_date is None:
                blocking.append({"event_type": event_type, "event_id": entry.get("event_id"),
                                 "reason": REASON_MISSING_EXPLICIT_EX_DATE})
                continue
            if session < entry_ex_date:
                qualifying.append({"event_type": event_type, "event_id": entry.get("event_id"),
                                   "adjustment_factor": entry.get("adjustment_factor"),
                                   "ex_date": entry.get("ex_date")})
            # session >= entry_ex_date: this specific entry does not apply to this session.

    considered_ids = sorted({str(o.get("observation_id")) for o in as_known})
    if blocking:
        return {"state": BLOCKED, "reason": blocking[0]["reason"], "blocking": blocking,
                "qualifying": qualifying, "considered_observation_ids": considered_ids,
                "excluded_after_cutoff_observation_ids": sorted(excluded)}
    if qualifying:
        return {"state": QUALIFIED, "reason": REASON_CORPORATE_ACTION_QUALIFIED, "qualifying": qualifying,
                "considered_observation_ids": considered_ids,
                "excluded_after_cutoff_observation_ids": sorted(excluded)}
    return {"state": NOT_APPLICABLE, "reason": REASON_CORPORATE_ACTION_NOT_APPLICABLE,
            "considered_observation_ids": considered_ids,
            "excluded_after_cutoff_observation_ids": sorted(excluded)}


# --- Combination -------------------------------------------------------------------------

def _combine(price_basis_state: Mapping[str, Any], corporate_action_state: Mapping[str, Any]) -> tuple[str, str]:
    price_state = price_basis_state["state"]
    action_state = corporate_action_state["state"]
    if price_state == BLOCKED:
        return BLOCKED, price_basis_state["reason"]
    if action_state == BLOCKED:
        return BLOCKED, corporate_action_state["reason"]
    if price_state == UNKNOWN:
        return UNKNOWN, price_basis_state["reason"]
    # price_state is QUALIFIED from here on (the only remaining possibility this contract emits).
    if action_state == UNKNOWN:
        return PARTIAL, REASON_DEPENDENCY_UNRESOLVED_PARTIAL
    return QUALIFIED, None


# --- Public entry point -------------------------------------------------------------------

def classify_price_reconstruction(
    *, ticker: str, session: str, knowledge_cutoff: str, mode: str,
    provider: str = "DNSE", dataset: str = "ohlc_1D",
    instrument_class: str | None = None, acquisition_status: str | None = None,
    corporate_action_observations: Sequence[Mapping[str, Any]] = (),
    price_basis_authorities: Sequence[Mapping[str, Any]] | None = None,
    contemporaneous_raw_observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The single verdict for one (ticker, session, knowledge_cutoff, mode).

    Pure and deterministic: no I/O, no clock, no network. Every dependency is supplied by the
    caller. Same inputs always produce the same ``verdict_id``.
    """
    if mode not in VIEW_MODES:
        raise PitPriceReconstructionContractError(f"unknown_view_mode:{mode!r}")
    normalized_ticker = str(ticker).strip().upper()
    if not normalized_ticker:
        raise PitPriceReconstructionContractError("ticker_required")
    normalized_session = _normalized_date(session)
    if normalized_session is None:
        raise PitPriceReconstructionContractError(f"session_not_a_parseable_date:{session!r}")
    if _parse_instant(knowledge_cutoff) is None:
        raise PitPriceReconstructionContractError(f"knowledge_cutoff_not_parseable:{knowledge_cutoff!r}")

    scope = _ticker_scope_state(instrument_class=instrument_class, acquisition_status=acquisition_status)
    if scope["state"] != QUALIFIED:
        verdict, reason = scope["state"], scope["reason"]
        price_basis_result: dict[str, Any] = {"state": NOT_APPLICABLE, "reason": REASON_TICKER_SCOPE_BLOCKED}
        corporate_action_result: dict[str, Any] = {"state": NOT_APPLICABLE, "reason": REASON_TICKER_SCOPE_BLOCKED}
    else:
        price_basis_result = _price_basis_state(
            mode=mode, provider=provider, dataset=dataset, ticker=normalized_ticker,
            session=normalized_session, knowledge_cutoff=knowledge_cutoff,
            price_basis_authorities=price_basis_authorities,
            contemporaneous_raw_observation=contemporaneous_raw_observation)
        corporate_action_result = _corporate_action_state(
            corporate_action_observations, ticker=normalized_ticker, session=normalized_session,
            knowledge_cutoff=knowledge_cutoff)
        verdict, reason = _combine(price_basis_result, corporate_action_result)

    # Mode isolation: the ONLY field a downstream consumer may treat as "safe to use as a
    # PIT/backtest input". Deliberately never true for RETROSPECTIVE_RESTATED, even a QUALIFIED
    # one -- see the module docstring's "MODE ISOLATION" note. Fully derived from mode/verdict,
    # which are both already part of this record, so including it below is not a second source
    # of truth.
    pit_backtest_eligible = mode == MODE_PIT_AS_KNOWN and verdict == QUALIFIED

    record: dict[str, Any] = {
        "contract_version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "ticker": normalized_ticker,
        "session": normalized_session.isoformat(),
        "knowledge_cutoff": str(knowledge_cutoff),
        "mode": mode,
        "provider": str(provider).strip().upper(),
        "dataset": str(dataset).strip().lower(),
        "verdict": verdict,
        "reason": reason,
        "pit_backtest_eligible": pit_backtest_eligible,
        "ticker_scope": scope,
        "price_basis": price_basis_result,
        "corporate_action": corporate_action_result,
    }
    record["verdict_id"] = _fingerprint({key: value for key, value in record.items() if key != "verdict_id"})
    return record


def classify_price_reconstruction_both_modes(**kwargs: Any) -> dict[str, dict[str, Any]]:
    """Convenience: both required output view modes for one (ticker, session, cutoff)."""
    if "mode" in kwargs:
        raise PitPriceReconstructionContractError("mode_is_computed_do_not_pass_it_to_both_modes_helper")
    return {mode: classify_price_reconstruction(mode=mode, **kwargs) for mode in sorted(VIEW_MODES)}


# --- Full-universe, read-only, deterministic denominator classification ------------------

def classify_universe(
    records: Iterable[Mapping[str, Any]], *, session: str, knowledge_cutoff: str, mode: str,
    provider: str = "DNSE", dataset: str = "ohlc_1D",
    corporate_action_observations_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    price_basis_authorities: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify every record exactly once. No record is silently dropped or double-counted.

    ``records``: one mapping per instrument, at minimum ``{"ticker": str}``; optionally
    ``instrument_class`` and ``acquisition_status`` (``"SUCCESS"`` / ``"PERMANENT"`` / other).
    The denominator is ``len(results)``, which is always exactly the number of input records --
    a duplicate ticker raises rather than silently merging or double-counting.
    """
    observations_by_ticker = corporate_action_observations_by_ticker or {}
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for record in records:
        raw_ticker = record.get("ticker")
        if not raw_ticker:
            raise PitPriceReconstructionContractError("universe_record_missing_ticker")
        normalized_ticker = str(raw_ticker).strip().upper()
        if normalized_ticker in seen:
            raise PitPriceReconstructionContractError(f"duplicate_ticker_in_universe:{normalized_ticker}")
        seen.add(normalized_ticker)
        verdict = classify_price_reconstruction(
            ticker=normalized_ticker, session=session, knowledge_cutoff=knowledge_cutoff, mode=mode,
            provider=provider, dataset=dataset,
            instrument_class=record.get("instrument_class"),
            acquisition_status=record.get("acquisition_status"),
            corporate_action_observations=observations_by_ticker.get(normalized_ticker, ()),
            price_basis_authorities=price_basis_authorities,
            contemporaneous_raw_observation=record.get("contemporaneous_raw_observation"),
        )
        results.append(verdict)

    verdict_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    acquisition_status_counts: dict[str, int] = {}
    for verdict in results:
        verdict_counts[verdict["verdict"]] = verdict_counts.get(verdict["verdict"], 0) + 1
        reason_counts[str(verdict["reason"])] = reason_counts.get(str(verdict["reason"]), 0) + 1
        status = verdict["ticker_scope"].get("acquisition_status")
        key = str(status) if status is not None else "NOT_PROVIDED"
        acquisition_status_counts[key] = acquisition_status_counts.get(key, 0) + 1

    return {
        "contract_version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "session": session,
        "knowledge_cutoff": knowledge_cutoff,
        "mode": mode,
        "denominator": len(results),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "acquisition_status_counts": dict(sorted(acquisition_status_counts.items())),
        # Two explicit, mode-scoped lists in place of one generic "qualified_tickers" -- a
        # RETROSPECTIVE_RESTATED QUALIFIED ticker must never be readable as PIT/backtest-eligible
        # merely because it appears in a "qualified" list with no mode qualifier attached. See the
        # module docstring's "MODE ISOLATION" note.
        "pit_backtest_eligible_tickers": sorted(v["ticker"] for v in results if v["pit_backtest_eligible"]),
        "retrospective_qualified_tickers": sorted(
            v["ticker"] for v in results
            if v["verdict"] == QUALIFIED and v["mode"] == MODE_RETROSPECTIVE_RESTATED),
        "results": results,
    }


def contract_summary() -> dict[str, Any]:
    """A provenance record describing this contract's own scope -- not a per-ticker verdict."""
    return {
        "contract_version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "view_modes": sorted(VIEW_MODES),
        "verdict_states": sorted(VERDICT_STATES),
        "reason_codes": sorted(REASON_CODES),
        "price_relevant_event_types": sorted(_PRICE_RELEVANT_EVENT_TYPES),
        "share_count_event_types": sorted(_SHARE_COUNT_EVENT_TYPES),
        "notes": (
            "eligibility/verdict classifier only; computes no numeric adjusted price; "
            "no network I/O; no runtime writes; consumes provider_price_basis_registry, "
            "dnse_ohlc_price_basis_capability (via the registry), and "
            "official_corporate_action_ledger without modifying any of them"
        ),
    }


# --- CLI: bounded, read-only full-universe classification ---------------------------------

def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(
        "Bounded, read-only PIT price-reconstruction classification over an already-materialized "
        "instrument universe. Reads only local JSON files; performs no network call, no database "
        "access, and no runtime write beyond an explicit --out path."))
    parser.add_argument("--universe-json", required=True,
                        help="Path to a JSON list of {ticker, instrument_class, acquisition_status}.")
    parser.add_argument("--session", required=True, help="ISO date, e.g. 2026-08-17.")
    parser.add_argument("--knowledge-cutoff", required=True, help="ISO date or timestamp.")
    parser.add_argument("--mode", choices=sorted(VIEW_MODES), default=MODE_PIT_AS_KNOWN)
    parser.add_argument("--corporate-action-observations-json", default=None,
                        help="Path to a JSON object of {ticker: [observation, ...]}.")
    parser.add_argument("--out", default=None, help="Optional path to write the full per-ticker result.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    universe = _load_json(Path(args.universe_json))
    if not isinstance(universe, list):
        raise PitPriceReconstructionContractError("universe_json_must_be_a_json_list")
    observations_by_ticker: dict[str, Sequence[Mapping[str, Any]]] = {}
    if args.corporate_action_observations_json:
        raw = _load_json(Path(args.corporate_action_observations_json))
        if not isinstance(raw, Mapping):
            raise PitPriceReconstructionContractError(
                "corporate_action_observations_json_must_be_a_json_object")
        observations_by_ticker = {str(k).strip().upper(): v for k, v in raw.items()}

    result = classify_universe(
        universe, session=args.session, knowledge_cutoff=args.knowledge_cutoff, mode=args.mode,
        corporate_action_observations_by_ticker=observations_by_ticker)

    summary = {key: value for key, value in result.items() if key != "results"}
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False, default=str))
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
