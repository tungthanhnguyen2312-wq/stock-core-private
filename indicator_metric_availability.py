"""Indicator/metric availability reconciliation: ``indicator_metric_availability/v1``.

INDICATOR_AND_METRIC_AVAILABILITY_RECONCILIATION_V1.

This module computes nothing new. It is a deterministic reconciliation layer over
already-materialized per-ticker records -- principally ``investment_decision_workspace_
projection/v1`` ticker cards (``card.build_ticker_card()``'s own diagnostic sub-objects
already carry status/blocker-reason detail for tactical, valuation, fundamental, flow, and
catalyst axes) -- that answers, for one governed metric on one ticker, the question the
Dashboard cannot currently answer deterministically:

    1. Does this capability exist (an engine/producer for it is real)?
    2. Does this ticker currently have a usable value?
    3. If not, exactly why (one blocker class, never a vague "insufficient data")?
    4. Can it be recovered now from retained evidence, or does it need something new?
    5. Does it genuinely need a future session, or is "waiting" stale caution?
    6. Is PIT only blocking historical/backtest authority, or current display too?
    7. Is the metric inapplicable to this ticker's entity class, or merely missing?
    8. Is this ticker simply outside a bounded acquisition cohort (not a data failure)?

The record never widens a Producer verdict (a card that says ``BLOCKED`` never becomes
``READY`` here) and never fabricates a value, a session, or a recovery path. Where the
correct answer is "not documented anywhere, would need a live query," the record says so
via ``UNKNOWN_BLOCKER`` / ``NO_IMPLEMENTATION`` rather than guessing.

Two structurally different producer situations both collapse to ``INSUFFICIENT_DATA`` at
this contract's boundary; ``blocker_class`` and ``recoverability`` are what keep them
distinguishable for later engineering triage:

- ``NOT MATERIALIZED`` (engine exists, has not been run / wired for this ticker session)
- ``DATA DOES NOT EXIST`` (engine ran, the required raw fact is genuinely absent)

Likewise ``NOT HISTORICAL PIT QUALIFIED`` never collapses into ``CURRENT RESEARCH METRIC
CANNOT BE SHOWN``: ``current_research_allowed`` and ``historical_pit_allowed`` are reported
independently on every record (see ``docs/AI_RULES.md`` rules 5-10,
``docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md`` Section 2.1).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "indicator_metric_availability/v1"

# ---------------------------------------------------------------------------
# Governed vocabularies
# ---------------------------------------------------------------------------

#: Internal availability states. These are deliberately the same six states the
#: presentation layer (``indicator_metric_display_state.py``) exposes -- the internal
#: record carries the reasoning (blocker_class/recoverability/...) behind each state;
#: the presentation layer strips that reasoning down to state + Vietnamese text only.
AVAILABILITY_STATES = (
    "READY",
    "INSUFFICIENT_DATA",
    "BUILDING_HISTORY",
    "NOT_APPLICABLE",
    "NOT_TRACKED",
    "TEMPORARILY_UNAVAILABLE",
)

BLOCKER_CLASSES = (
    "READY",
    "RECOVERABLE_FROM_RETAINED_DATA",
    "RECOVERABLE_BY_EXISTING_BACKFILL",
    "MISSING_FINANCIAL_COMPONENT",
    "MISSING_PERIOD_COMPATIBILITY",
    "MISSING_CURRENT_VALUATION_INPUT",
    "MISSING_MONETARY_BASIS",
    "MISSING_SHARE_BASIS",
    "MISSING_PRICE_BASIS_AUTHORITY",
    "HISTORICAL_PIT_AUTHORITY_ONLY",
    "GENUINELY_WAITING_FUTURE_OBSERVATIONS",
    "SECTOR_NOT_APPLICABLE",
    "OUTSIDE_CURRENT_ACQUISITION_SCOPE",
    "NOT_CURRENTLY_PRODUCED",
    "PRESENTATION_TRANSPORT_GAP",
    "UNKNOWN_BLOCKER",
)

RECOVERABILITY_STATES = (
    "RECOVER_NOW_RETAINED_ONLY",
    "RECOVER_NOW_EXISTING_PROVIDER_PATH",
    "REQUIRES_NEW_EVIDENCE",
    "REQUIRES_FUTURE_SESSION",
    "REQUIRES_AUTHORITY_DECISION",
    "NOT_APPLICABLE",
    "NO_IMPLEMENTATION",
)

FAMILIES = (
    "MARKET",
    "PRICE_TECHNICAL",
    "FLOW",
    "FUNDAMENTALS",
    "VALUATION",
    "CORPORATE_RESEARCH_CONTEXT",
)

# ---------------------------------------------------------------------------
# Record construction (fail-closed builder; every resolver funnels through this)
# ---------------------------------------------------------------------------


def _record(
    metric_id: str,
    family: str,
    *,
    applicability: str = "APPLICABLE",
    availability_state: str,
    value_present: bool,
    value: Any = None,
    as_of: str | None = None,
    evidence_fitness: str | None = None,
    blocker_class: str = "READY",
    recoverability: str = "NOT_APPLICABLE",
    requires_future_observation: bool = False,
    current_research_allowed: bool = True,
    historical_pit_allowed: bool = False,
    recovery_action_code: str | None = None,
    source_identity: str | None = None,
) -> dict[str, Any]:
    if family not in FAMILIES:
        raise ValueError(f"unknown metric family: {family!r}")
    if availability_state not in AVAILABILITY_STATES:
        raise ValueError(f"unknown availability_state: {availability_state!r}")
    if blocker_class not in BLOCKER_CLASSES:
        raise ValueError(f"unknown blocker_class: {blocker_class!r}")
    if recoverability not in RECOVERABILITY_STATES:
        raise ValueError(f"unknown recoverability: {recoverability!r}")
    return {
        "contract_version": CONTRACT_VERSION,
        "metric_id": metric_id,
        "family": family,
        "applicability": applicability,
        "availability_state": availability_state,
        "value_present": value_present,
        "value": value,
        "as_of_session": as_of,
        "evidence_fitness": evidence_fitness,
        "blocker_class": blocker_class,
        "recoverability": recoverability,
        "requires_future_observation": requires_future_observation,
        "current_research_allowed": current_research_allowed,
        "historical_pit_allowed": historical_pit_allowed,
        "recovery_action_code": recovery_action_code,
        "source_identity": source_identity,
    }


def _ready(metric_id: str, family: str, *, value: Any, as_of: str | None, evidence_fitness: str | None,
           source_identity: str | None = None, historical_pit_allowed: bool = False) -> dict[str, Any]:
    return _record(
        metric_id, family, availability_state="READY", value_present=value is not None, value=value,
        as_of=as_of, evidence_fitness=evidence_fitness, blocker_class="READY", recoverability="NOT_APPLICABLE",
        historical_pit_allowed=historical_pit_allowed, source_identity=source_identity,
    )


def _not_applicable(metric_id: str, family: str, *, reason_code: str) -> dict[str, Any]:
    return _record(
        metric_id, family, applicability="NOT_APPLICABLE", availability_state="NOT_APPLICABLE",
        value_present=False, blocker_class="SECTOR_NOT_APPLICABLE", recoverability="NOT_APPLICABLE",
        current_research_allowed=False, recovery_action_code=reason_code,
    )


def _not_tracked(metric_id: str, family: str, *, reason_code: str) -> dict[str, Any]:
    return _record(
        metric_id, family, availability_state="NOT_TRACKED", value_present=False,
        blocker_class="OUTSIDE_CURRENT_ACQUISITION_SCOPE", recoverability="REQUIRES_AUTHORITY_DECISION",
        current_research_allowed=False, recovery_action_code=reason_code,
    )


def _not_currently_produced(metric_id: str, family: str, *, reason_code: str,
                             recoverability: str = "REQUIRES_NEW_EVIDENCE") -> dict[str, Any]:
    return _record(
        metric_id, family, availability_state="TEMPORARILY_UNAVAILABLE", value_present=False,
        blocker_class="NOT_CURRENTLY_PRODUCED", recoverability=recoverability,
        current_research_allowed=False, recovery_action_code=reason_code,
    )


# ---------------------------------------------------------------------------
# Blocker-code -> blocker_class reconciliation (never fabricate an unseen mapping)
# ---------------------------------------------------------------------------

#: Every code observed live in ``investment_decision_workspace_projection/v1`` cards'
#: ``blocker_reason_codes``/``warnings_blockers`` sub-fields, mapped to one governed
#: blocker class. A code not in this table maps to ``UNKNOWN_BLOCKER`` -- fail closed,
#: never silently guessed -- and should be added here once triaged, not left implicit.
_BLOCKER_CODE_TO_CLASS: dict[str, str] = {
    "MISSING_SAME_NATIVE_PERIOD_SCOPE_SERIES": "MISSING_PERIOD_COMPATIBILITY",
    "MISSING_SAME_QUARTER_PRIOR_YEAR": "MISSING_PERIOD_COMPATIBILITY",
    "MISSING_CONSECUTIVE_STANDALONE_QUARTER_INPUTS": "MISSING_PERIOD_COMPATIBILITY",
    "CROSS_PROVIDER_OR_DURATION_INCOMPATIBLE": "MISSING_PERIOD_COMPATIBILITY",
    "MISSING_STANDALONE_QUARTER_CFO": "MISSING_FINANCIAL_COMPONENT",
    "EXACT_EBITDA_COMPARABILITY_NOT_RETAINED": "MISSING_FINANCIAL_COMPONENT",
    "ebitda_not_ready": "MISSING_FINANCIAL_COMPONENT",
    "CALCULATION_READINESS_CONTEXT_UNAVAILABLE": "PRESENTATION_TRANSPORT_GAP",
    "price_basis_unknown_and_unverified_universe_wide": "MISSING_PRICE_BASIS_AUTHORITY",
    "share_count_not_evidenced_by_any_retained_provider_line": "MISSING_SHARE_BASIS",
    "unusable_term:cash_and_cash_equivalents": "MISSING_MONETARY_BASIS",
    "unusable_term:total_interest_bearing_debt": "MISSING_MONETARY_BASIS",
    "SECTOR_ENTITY_METHOD_NOT_SUPPORTED": "SECTOR_NOT_APPLICABLE",
    "PE_NOT_MEANINGFUL": "MISSING_CURRENT_VALUATION_INPUT",
    "NEGATIVE_EARNINGS": "MISSING_CURRENT_VALUATION_INPUT",
    "negative_or_zero_ebitda_denominator": "MISSING_CURRENT_VALUATION_INPUT",
    "TTM_INPUT_UNAVAILABLE": "MISSING_FINANCIAL_COMPONENT",
    "MARKET_CAP_RESEARCH_INPUT_UNAVAILABLE": "MISSING_CURRENT_VALUATION_INPUT",
    "INPUT_BLOCKED": "MISSING_CURRENT_VALUATION_INPUT",
    "BELOW_MIN_COHORT_MEMBERS": "MISSING_CURRENT_VALUATION_INPUT",
    "INSUFFICIENT_PEER_COUNT": "MISSING_CURRENT_VALUATION_INPUT",
    "NOT_AVAILABLE": "MISSING_CURRENT_VALUATION_INPUT",
}

#: A blocker class's default recoverability when no per-metric override applies.
#: Conservative by construction: a code is only ever promoted to a "recover now"
#: class inside a specific resolver that has independent evidence a retained backfill
#: path exists (e.g. daily-price lookback, cohort-scoped flow) -- never here by default.
_BLOCKER_CLASS_TO_RECOVERABILITY: dict[str, str] = {
    "READY": "NOT_APPLICABLE",
    "RECOVERABLE_FROM_RETAINED_DATA": "RECOVER_NOW_RETAINED_ONLY",
    "RECOVERABLE_BY_EXISTING_BACKFILL": "RECOVER_NOW_EXISTING_PROVIDER_PATH",
    "MISSING_FINANCIAL_COMPONENT": "REQUIRES_NEW_EVIDENCE",
    "MISSING_PERIOD_COMPATIBILITY": "REQUIRES_NEW_EVIDENCE",
    "MISSING_CURRENT_VALUATION_INPUT": "REQUIRES_NEW_EVIDENCE",
    "MISSING_MONETARY_BASIS": "REQUIRES_NEW_EVIDENCE",
    "MISSING_SHARE_BASIS": "REQUIRES_NEW_EVIDENCE",
    "MISSING_PRICE_BASIS_AUTHORITY": "REQUIRES_AUTHORITY_DECISION",
    "HISTORICAL_PIT_AUTHORITY_ONLY": "REQUIRES_AUTHORITY_DECISION",
    "GENUINELY_WAITING_FUTURE_OBSERVATIONS": "REQUIRES_FUTURE_SESSION",
    "SECTOR_NOT_APPLICABLE": "NOT_APPLICABLE",
    "OUTSIDE_CURRENT_ACQUISITION_SCOPE": "REQUIRES_AUTHORITY_DECISION",
    "NOT_CURRENTLY_PRODUCED": "REQUIRES_NEW_EVIDENCE",
    "PRESENTATION_TRANSPORT_GAP": "REQUIRES_AUTHORITY_DECISION",
    "UNKNOWN_BLOCKER": "NO_IMPLEMENTATION",
}


def _blocker_class_for_codes(codes: Sequence[str] | None) -> str:
    for code in codes or ():
        mapped = _BLOCKER_CODE_TO_CLASS.get(code)
        if mapped:
            return mapped
    return "UNKNOWN_BLOCKER" if codes else "READY"


def _status_to_state(status: str | None) -> str:
    """Map a Producer's own status/fitness string to one of the six governed states.

    Never promotes an unrecognized status to ``READY`` -- an unmapped string fails
    closed to ``INSUFFICIENT_DATA`` (a presentation "not enough data" is honest;
    silently treating an unknown status as available is not).
    """
    token = (status or "").strip().upper()
    if not token or token in ("NONE", "NULL"):
        return "INSUFFICIENT_DATA"
    if token == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    if token == "INSUFFICIENT_HISTORY":
        return "BUILDING_HISTORY"
    if token.startswith("READY") or token in ("AVAILABLE", "AVAILABLE_REFERENCE_ONLY", "RESEARCH_USABLE",
                                                "READY_RESEARCH_ONLY", "PRODUCT_READY_RESEARCH_CONTEXT"):
        return "READY"
    if token in ("BLOCKED", "BLOCKED_BY_EVIDENCE", "INPUT_BLOCKED", "NOT_AVAILABLE", "NOT_COMPARABLE"):
        return "INSUFFICIENT_DATA"
    return "INSUFFICIENT_DATA"


def _generic_from_status(metric_id: str, family: str, *, status: str | None, codes: Sequence[str] | None,
                          value: Any, as_of: str | None, entity_applicable: bool = True,
                          not_applicable_reason: str = "ENTITY_CLASS_NOT_APPLICABLE") -> dict[str, Any]:
    if not entity_applicable:
        return _not_applicable(metric_id, family, reason_code=not_applicable_reason)
    state = _status_to_state(status)
    if state == "NOT_APPLICABLE":
        return _not_applicable(metric_id, family, reason_code=str(status))
    if state == "READY":
        return _ready(metric_id, family, value=value, as_of=as_of, evidence_fitness=status)
    if state == "BUILDING_HISTORY":
        return _record(
            metric_id, family, availability_state="BUILDING_HISTORY", value_present=False, as_of=as_of,
            evidence_fitness=status, blocker_class="GENUINELY_WAITING_FUTURE_OBSERVATIONS",
            recoverability="REQUIRES_FUTURE_SESSION", requires_future_observation=True,
        )
    blocker_class = _blocker_class_for_codes(codes)
    # PRESENTATION_TRANSPORT_GAP means the engine is real and has run somewhere (a
    # bounded replay, a dormant bundle section) but is not currently wired into this
    # session's live projection -- a different, more hopeful situation than a genuine
    # missing input, so it gets its own state rather than collapsing into
    # INSUFFICIENT_DATA (kept consistent with ebitda_case_study_record's own mapping).
    resolved_state = "TEMPORARILY_UNAVAILABLE" if blocker_class == "PRESENTATION_TRANSPORT_GAP" else "INSUFFICIENT_DATA"
    return _record(
        metric_id, family, availability_state=resolved_state, value_present=False, as_of=as_of,
        evidence_fitness=status, blocker_class=blocker_class,
        recoverability=_BLOCKER_CLASS_TO_RECOVERABILITY[blocker_class],
        recovery_action_code=(codes[0] if codes else None),
    )


# ---------------------------------------------------------------------------
# FUNDAMENTALS family -- sourced from card["fundamental"]["current_features"]
# ---------------------------------------------------------------------------

#: metric_id -> current_features key. All corporate/industrial ratios; entity
#: applicability is read from the card's own ``fundamental.entity_applicability``
#: (an industrial ratio is fail-closed NOT_APPLICABLE for bank/securities/insurance,
#: which keep separate specialist families -- see ``financial_entity_applicability.py``).
_FUNDAMENTAL_FEATURE_METRICS: dict[str, str] = {
    "revenue_growth_yoy": "revenue_same_period_yoy",
    "net_income_growth_yoy": "net_income_same_period_yoy",
    "gross_margin": "gross_margin",
    "net_margin": "net_margin",
    "operating_cash_flow_sign": "operating_cash_flow_sign",
    "roe": "roe_eop_proxy",
    "roa": "roa_eop_proxy",
    "debt_to_equity": "debt_to_equity",
    "cash_to_assets": "cash_to_assets",
    "cfo_to_net_income": "cfo_to_net_income",
}


def _fundamental_feature_record(metric_id: str, feature_key: str, card: Mapping[str, Any],
                                 as_of: str | None) -> dict[str, Any]:
    fundamental = card.get("fundamental") or {}
    entity_applicability = fundamental.get("entity_applicability")
    if entity_applicability in ("NOT_APPLICABLE", "SPECIALIST_ONLY"):
        return _not_applicable(metric_id, "FUNDAMENTALS", reason_code=str(entity_applicability))
    current_features = fundamental.get("current_features")
    feature = current_features.get(feature_key) if isinstance(current_features, Mapping) else None
    if isinstance(feature, Mapping):
        return _generic_from_status(
            metric_id, "FUNDAMENTALS",
            status=feature.get("status"), codes=feature.get("blocker_reason_codes"),
            value=feature.get("value") if feature.get("value") is not None else feature.get("categorical_state"),
            as_of=as_of,
        )
    # No per-feature record at all: some tickers collapse the whole fundamental axis to
    # one overall string status (e.g. "financial_health": "UNAVAILABLE") rather than a
    # per-feature dict -- fall back to that honestly instead of guessing "not wired".
    overall_status = fundamental.get("financial_health")
    if isinstance(overall_status, str) and overall_status:
        return _generic_from_status(metric_id, "FUNDAMENTALS", status=overall_status, codes=None, value=None,
                                     as_of=as_of)
    return _not_currently_produced(metric_id, "FUNDAMENTALS",
                                    reason_code="FEATURE_KEY_NOT_PRESENT_IN_PRODUCT_PROJECTION")


def _financial_health_rollup_record(metric_id: str, health_key: str, card: Mapping[str, Any],
                                     as_of: str | None) -> dict[str, Any]:
    """A categorical roll-up (e.g. leverage/cash_quality) -- present even when the
    underlying numeric ratio (e.g. current_ratio) is not itself projected to this card."""
    fundamental = card.get("fundamental") or {}
    health = fundamental.get("financial_health")
    if isinstance(health, Mapping):
        state = health.get(health_key)
    elif isinstance(health, str):
        # Whole fundamental axis collapsed to one status string for this ticker.
        state = health
    else:
        state = None
    return _generic_from_status(metric_id, "FUNDAMENTALS", status=state, codes=None, value=state, as_of=as_of)


# ---------------------------------------------------------------------------
# VALUATION family -- sourced from card["valuation"]["method_diagnostics"]
# ---------------------------------------------------------------------------

_VALUATION_METHOD_METRICS: dict[str, str] = {
    "pe_ttm": "P/E_TTM",
    "ps_ttm": "P/S_TTM",
    "pb": "P/B",
    "ev_sales": "EV/Sales",
    "ev_ebitda": "EV/EBITDA",
    "ev_ebitda_calc_ready": "EV/EBITDA_CALC_READY",
}

def _entity_class_allows_corporate_only(entity_class: str | None) -> bool:
    return (entity_class or "").strip().lower() == "corporate"


def _valuation_method_record(metric_id: str, method_key: str, card: Mapping[str, Any],
                              as_of: str | None) -> dict[str, Any]:
    valuation = card.get("valuation") or {}
    entity_class = valuation.get("entity_class")
    corporate_only = method_key in ("EV/EBITDA", "EV/EBITDA_CALC_READY")
    if corporate_only and not _entity_class_allows_corporate_only(entity_class):
        return _not_applicable(metric_id, "VALUATION", reason_code="CORPORATE_ONLY_METHOD_NOT_APPLICABLE_THIS_ENTITY_CLASS")
    method = (valuation.get("method_diagnostics") or {}).get(method_key)
    if not isinstance(method, Mapping):
        return _not_currently_produced(metric_id, "VALUATION", reason_code="METHOD_NOT_PRESENT_IN_PRODUCT_PROJECTION")
    codes = method.get("blocker_reason_codes")
    status = method.get("availability_state") or method.get("status")
    record = _generic_from_status(
        metric_id, "VALUATION", status=status, codes=codes, value=method.get("value"), as_of=as_of,
    )
    # EV/EBITDA_CALC_READY's specific blocker means the generic calculation-readiness
    # engine is real (market_wide_calculation_readiness.py, 231 tickers EBITDA-ready in a
    # bounded 2026-09-05 replay) but its opt-in bundle wiring is a recorded, deliberate
    # owner decision left off by default (docs/STATE.md 2026-09-05 CORE_VALUATION_METHOD_
    # COVERAGE_AND_CONSISTENCY_V1) -- not a mechanical recovery.
    if record["blocker_class"] == "PRESENTATION_TRANSPORT_GAP":
        record = dict(record, recoverability="REQUIRES_AUTHORITY_DECISION",
                      recovery_action_code="OWNER_DECISION_TO_ENABLE_CALCULATION_READINESS_BUNDLE_SECTION")
    return record


def ebitda_case_study_record(card: Mapping[str, Any], as_of: str | None) -> dict[str, Any]:
    """EBITDA has no standalone method key on the card (see module docstring / Phase 8
    of the milestone brief): it is read off ``EV/EBITDA_CALC_READY``'s own blocker,
    since that is the only per-ticker signal for whether EBITDA itself is ready.
    """
    valuation = card.get("valuation") or {}
    entity_class = valuation.get("entity_class")
    if not _entity_class_allows_corporate_only(entity_class):
        return _not_applicable("ebitda", "VALUATION", reason_code="CORPORATE_ONLY_METRIC_NOT_APPLICABLE_THIS_ENTITY_CLASS")
    calc_ready = (valuation.get("method_diagnostics") or {}).get("EV/EBITDA_CALC_READY") or {}
    codes = calc_ready.get("blocker_reason_codes") or ()
    if "CALCULATION_READINESS_CONTEXT_UNAVAILABLE" in codes:
        return _record(
            "ebitda", "VALUATION", availability_state="TEMPORARILY_UNAVAILABLE", value_present=False, as_of=as_of,
            evidence_fitness="ENGINE_EXISTS_NOT_WIRED_INTO_LIVE_BUNDLE",
            blocker_class="PRESENTATION_TRANSPORT_GAP", recoverability="REQUIRES_AUTHORITY_DECISION",
            recovery_action_code="OWNER_DECISION_TO_ENABLE_CALCULATION_READINESS_BUNDLE_SECTION",
        )
    if "ebitda_not_ready" in codes:
        return _record(
            "ebitda", "VALUATION", availability_state="INSUFFICIENT_DATA", value_present=False, as_of=as_of,
            evidence_fitness="CALCULATION_READINESS_CONTEXT_AVAILABLE_EBITDA_NOT_READY",
            blocker_class="MISSING_FINANCIAL_COMPONENT", recoverability="REQUIRES_NEW_EVIDENCE",
            recovery_action_code="ebitda_not_ready",
        )
    if calc_ready.get("value") is not None:
        return _ready("ebitda", "VALUATION", value=calc_ready.get("value"), as_of=as_of,
                      evidence_fitness="CALCULATION_READINESS_PROVIDER_REPORTED")
    return _generic_from_status("ebitda", "VALUATION", status=calc_ready.get("availability_state"),
                                 codes=codes, value=None, as_of=as_of)


# ---------------------------------------------------------------------------
# PRICE_TECHNICAL family
# ---------------------------------------------------------------------------

def _technical_trend_record(card: Mapping[str, Any], as_of: str | None) -> dict[str, Any]:
    tactical = card.get("tactical") or {}
    state = tactical.get("primary_entry_state")
    if state:
        return _ready("technical_trend_entry_state", "PRICE_TECHNICAL", value=state, as_of=as_of,
                      evidence_fitness=tactical.get("freshness_status"))
    return _record(
        "technical_trend_entry_state", "PRICE_TECHNICAL", availability_state="INSUFFICIENT_DATA",
        value_present=False, as_of=as_of, blocker_class="MISSING_PERIOD_COMPATIBILITY",
        recoverability="RECOVER_NOW_EXISTING_PROVIDER_PATH",
        recovery_action_code="EXTENDED_LOOKBACK_TECHNICAL_HISTORY_RECOVERY",
    )


def _technical_confirmation_record(card: Mapping[str, Any], as_of: str | None) -> dict[str, Any]:
    confirmation = card.get("confirmation") or {}
    status = confirmation.get("confirmation_trigger_state")
    if status in (None, "NOT_AVAILABLE"):
        return _record(
            "technical_confirmation_trigger", "PRICE_TECHNICAL", availability_state="INSUFFICIENT_DATA",
            value_present=False, as_of=confirmation.get("as_of", as_of),
            evidence_fitness=confirmation.get("status"),
            blocker_class="MISSING_CURRENT_VALUATION_INPUT", recoverability="REQUIRES_FUTURE_SESSION",
            recovery_action_code="TRIGGER_CONDITION_NOT_YET_MET",
        )
    return _ready("technical_confirmation_trigger", "PRICE_TECHNICAL", value=status,
                  as_of=confirmation.get("as_of", as_of), evidence_fitness=confirmation.get("status"))


def _technical_invalidation_record(card: Mapping[str, Any], as_of: str | None) -> dict[str, Any]:
    invalidation = (card.get("invalidation") or {}).get("technical") or {}
    status = invalidation.get("status")
    if status:
        return _ready("technical_invalidation", "PRICE_TECHNICAL", value=invalidation.get("boundary_type"),
                      as_of=invalidation.get("as_of", as_of), evidence_fitness=status)
    return _not_currently_produced("technical_invalidation", "PRICE_TECHNICAL",
                                    reason_code="NO_RETAINED_INVALIDATION_BOUNDARY")


def _signal_velocity_record(card: Mapping[str, Any], as_of: str | None) -> dict[str, Any]:
    velocity = card.get("signal_velocity") or {}
    state = velocity.get("overall_transition_state")
    quality = velocity.get("evidence_quality")
    if state and state != "INSUFFICIENT_EVIDENCE":
        return _ready("signal_velocity_state", "PRICE_TECHNICAL", value=state,
                      as_of=velocity.get("source_record_session", as_of), evidence_fitness=quality,
                      source_identity=velocity.get("source_artifact_identity"))
    valid_count = velocity.get("valid_observation_count") or 0
    if quality == "INSUFFICIENT_RETAINED_EVIDENCE" and valid_count and valid_count < 3:
        return _record(
            "signal_velocity_state", "PRICE_TECHNICAL", availability_state="BUILDING_HISTORY", value_present=False,
            as_of=as_of, evidence_fitness=quality, blocker_class="GENUINELY_WAITING_FUTURE_OBSERVATIONS",
            recoverability="REQUIRES_FUTURE_SESSION", requires_future_observation=True,
        )
    return _record(
        "signal_velocity_state", "PRICE_TECHNICAL", availability_state="INSUFFICIENT_DATA", value_present=False,
        as_of=as_of, evidence_fitness=quality, blocker_class="MISSING_PERIOD_COMPATIBILITY",
        recoverability="REQUIRES_NEW_EVIDENCE", recovery_action_code=velocity.get("reason_code"),
    )


def _sector_relative_momentum_record(card: Mapping[str, Any], as_of: str | None) -> dict[str, Any]:
    diagnostic = ((card.get("market_sector") or {}).get("sector_diagnostic") or {}).get("sector_relative_momentum") or {}
    status = diagnostic.get("status")
    if status == "AVAILABLE":
        return _ready("sector_relative_momentum", "PRICE_TECHNICAL",
                      value=diagnostic.get("momentum_percentile_descriptive"), as_of=as_of, evidence_fitness=status)
    return _generic_from_status("sector_relative_momentum", "PRICE_TECHNICAL", status=status, codes=None,
                                 value=None, as_of=as_of)


# ---------------------------------------------------------------------------
# FLOW family -- cohort-scoped (owner_research_focus.broader_watchlist, 11 tickers)
# ---------------------------------------------------------------------------

def _flow_metric_record(metric_id: str, card_field: str, ticker: str, card: Mapping[str, Any],
                         cohort_tickers: frozenset[str], as_of: str | None) -> dict[str, Any]:
    if ticker.upper() not in cohort_tickers:
        return _not_tracked(metric_id, "FLOW", reason_code="OUTSIDE_CURRENT_FLOW_RESEARCH_COHORT")
    flow_price = card.get("flow_price") or {}
    value = flow_price.get(card_field)
    if value in (None, "FLOW_UNAVAILABLE"):
        return _record(
            metric_id, "FLOW", availability_state="INSUFFICIENT_DATA", value_present=False,
            as_of=flow_price.get("reference_session", as_of), blocker_class="MISSING_FINANCIAL_COMPONENT",
            recoverability="REQUIRES_NEW_EVIDENCE",
            recovery_action_code="IN_COHORT_CURRENT_SESSION_VALUE_NOT_YET_RECORDED",
        )
    return _ready(metric_id, "FLOW", value=value, as_of=flow_price.get("reference_session", as_of),
                 evidence_fitness=flow_price.get("evidence_quality"),
                 source_identity=flow_price.get("source_artifact_identity"))


# ---------------------------------------------------------------------------
# CORPORATE_RESEARCH_CONTEXT family
# ---------------------------------------------------------------------------

def _catalyst_event_context_record(card: Mapping[str, Any], as_of: str | None) -> dict[str, Any]:
    catalyst = card.get("catalyst") or {}
    freshness = catalyst.get("freshness_status")
    event_count = catalyst.get("event_count") or 0
    qualified = catalyst.get("qualified_current_catalysts")
    has_content = bool(event_count) or bool(qualified)
    if has_content:
        return _record(
            "catalyst_event_context", "CORPORATE_RESEARCH_CONTEXT", availability_state="READY",
            value_present=True, value=qualified or catalyst.get("status"),
            as_of=catalyst.get("source_session", as_of), evidence_fitness=freshness,
            blocker_class="READY", recoverability="NOT_APPLICABLE",
        )
    return _record(
        "catalyst_event_context", "CORPORATE_RESEARCH_CONTEXT", availability_state="TEMPORARILY_UNAVAILABLE",
        value_present=False, as_of=catalyst.get("source_session", as_of), evidence_fitness=freshness,
        blocker_class="NOT_CURRENTLY_PRODUCED", recoverability="REQUIRES_NEW_EVIDENCE",
        recovery_action_code="CORPORATE_EVENT_CONTEXT_UPSTREAM_RESEARCH_SESSION_STALE",
    )


# ---------------------------------------------------------------------------
# MARKET family (session-wide, not per-ticker)
# ---------------------------------------------------------------------------

def market_wide_records(cards: Mapping[str, Mapping[str, Any]], as_of: str | None) -> dict[str, dict[str, Any]]:
    """Session-level market metrics, derived only from already-published per-ticker
    cards (no new computation) -- see module docstring; this never invents a VN-Index
    level, which this repository genuinely does not produce anywhere (confirmed:
    no VNINDEX price/point-change field exists in any Dashboard-facing contract)."""
    breadth_values = [
        (card.get("market_sector") or {}).get("breadth_regime")
        for card in cards.values()
        if (card.get("market_sector") or {}).get("breadth_regime")
    ]
    liquidity_ready = sum(
        1 for card in cards.values()
        if ((card.get("liquidity") or {}).get("research_usable")) is True
    )
    records: dict[str, dict[str, Any]] = {
        "market_index_level_change": _not_currently_produced(
            "market_index_level_change", "MARKET",
            reason_code="NO_GOVERNED_VN_INDEX_PRICE_AUTHORITY_RETAINED_ANYWHERE",
            recoverability="REQUIRES_NEW_EVIDENCE",
        ),
    }
    if breadth_values:
        records["market_breadth_advancing_declining"] = _ready(
            "market_breadth_advancing_declining", "MARKET",
            value={"sampled_tickers": len(breadth_values), "distinct_states": len(set(breadth_values))},
            as_of=as_of, evidence_fitness="market_regime_breadth_context/v1",
        )
    else:
        records["market_breadth_advancing_declining"] = _not_currently_produced(
            "market_breadth_advancing_declining", "MARKET", reason_code="NO_CARDS_CARRIED_BREADTH_REGIME",
        )
    records["market_relative_liquidity_activity"] = _ready(
        "market_relative_liquidity_activity", "MARKET",
        value={"research_usable_ticker_count": liquidity_ready, "denominator": len(cards)},
        as_of=as_of, evidence_fitness="market_wide_current_liquidity_research/v1",
    ) if cards else _not_currently_produced("market_relative_liquidity_activity", "MARKET",
                                             reason_code="NO_CARDS_SUPPLIED")
    return records


# ---------------------------------------------------------------------------
# Per-ticker orchestration
# ---------------------------------------------------------------------------

def evaluate_ticker(ticker: str, card: Mapping[str, Any], *, cohort_tickers: frozenset[str],
                     as_of_session: str | None = None) -> dict[str, dict[str, Any]]:
    """All governed metric records for one ticker, keyed by ``metric_id``."""
    as_of = as_of_session or card.get("as_of_session")
    records: dict[str, dict[str, Any]] = {}

    for metric_id, feature_key in _FUNDAMENTAL_FEATURE_METRICS.items():
        records[metric_id] = _fundamental_feature_record(metric_id, feature_key, card, as_of)
    records["leverage_state"] = _financial_health_rollup_record("leverage_state", "leverage", card, as_of)
    records["cash_quality_state"] = _financial_health_rollup_record("cash_quality_state", "cash_quality", card, as_of)

    for metric_id, method_key in _VALUATION_METHOD_METRICS.items():
        records[metric_id] = _valuation_method_record(metric_id, method_key, card, as_of)
    records["ebitda"] = ebitda_case_study_record(card, as_of)

    records["technical_trend_entry_state"] = _technical_trend_record(card, as_of)
    records["technical_confirmation_trigger"] = _technical_confirmation_record(card, as_of)
    records["technical_invalidation"] = _technical_invalidation_record(card, as_of)
    records["signal_velocity_state"] = _signal_velocity_record(card, as_of)
    records["sector_relative_momentum"] = _sector_relative_momentum_record(card, as_of)

    records["foreign_flow_state"] = _flow_metric_record("foreign_flow_state", "foreign_flow_state", ticker, card,
                                                         cohort_tickers, as_of)
    records["flow_price_relationship"] = _flow_metric_record("flow_price_relationship", "relationship", ticker, card,
                                                              cohort_tickers, as_of)
    records["flow_persistence_5session"] = _flow_metric_record("flow_persistence_5session", "flow_persistence",
                                                                ticker, card, cohort_tickers, as_of)

    records["catalyst_event_context"] = _catalyst_event_context_record(card, as_of)
    return records


def evaluate_workspace_artifact(artifact: Mapping[str, Any], *,
                                 cohort_tickers: frozenset[str]) -> dict[str, Any]:
    """Every ticker in a real ``investment_decision_workspace_projection/v1`` artifact.

    Returns ``{"as_of_session", "artifact_identity", "tickers": {ticker: {metric_id: record}},
    "market_wide": {metric_id: record}}``. Zero silent drops: every ticker key in the
    source artifact's ``cards`` produces an entry here.
    """
    cards = artifact.get("cards") or {}
    as_of = artifact.get("as_of_session")
    tickers = {ticker: evaluate_ticker(ticker, card, cohort_tickers=cohort_tickers, as_of_session=as_of)
               for ticker, card in cards.items()}
    return {
        "contract_version": CONTRACT_VERSION,
        "as_of_session": as_of,
        "source_artifact_identity": artifact.get("artifact_identity"),
        "ticker_denominator": len(cards),
        "tickers": tickers,
        "market_wide": market_wide_records(cards, as_of),
    }
