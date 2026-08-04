"""What may and may not be computed from a market-volume figure, and on whose authority.

WHY THIS MODULE EXISTS
    Every liquidity gate in this repository was, until this milestone, expressed as
    "blocked while ``volume_basis_verified`` is false". That is a *pending* state, and it
    has an obvious release: verify the basis. The VCI closeout at ``63ecc48`` made that
    release dangerous. The unit is shares and the provider's own arithmetic closes exactly,
    so a future reader has every reason to flip ``volume_basis_verified`` to true -- and
    would thereby open days-to-liquidate, participation-rate sizing and backtest liquidity
    constraints on a figure whose *market composition* nobody has established. Whether the
    number includes put-through trades is unknown, and no amount of unit qualification
    answers it.

    So the gate moved. Liquidity and execution capabilities here are unavailable **by
    contract**, not pending an input. There is no field a caller can set to open them. The
    only stated way out is a different, authoritative source contract, which is Part D's
    registry and is not active.

WHAT IT DELIBERATELY DOES NOT DO
    It does not switch off descriptive volume. Showing a volume history, a 20-session
    moving average or a provider-scoped relative-volume reading was never a liquidity
    claim, and disabling those would be a cost paid for no safety. They stay available
    under their existing freshness and provenance gates, carrying warnings that say what
    the number is and is not.

THE UNKNOWN CLASS IS THE POINT
    A consumer this module has never heard of resolves to ``unknown_or_ambiguous`` and is
    refused. Adding a volume consumer therefore requires classifying it, which is the
    behaviour that keeps this matrix true a year from now.
"""

from __future__ import annotations

from typing import Any, Mapping

import vci_volume_composition as composition

VERSION = "1.0.0"

# ---------------------------------------------------------------------------------
# Classes and availability states
# ---------------------------------------------------------------------------------

CLASS_DESCRIPTIVE = "descriptive_provider_scoped"
CLASS_ANALYTICAL = "analytical_not_liquidity_dependent"
CLASS_LIQUIDITY = "liquidity_dependent"
CLASS_EXECUTION = "execution_dependent"
CLASS_UNKNOWN = "unknown_or_ambiguous"

CAPABILITY_CLASSES = (
    CLASS_DESCRIPTIVE,
    CLASS_ANALYTICAL,
    CLASS_LIQUIDITY,
    CLASS_EXECUTION,
    CLASS_UNKNOWN,
)

#: Available *if its own gates pass*. This module does not assert freshness or provenance;
#: it says the capability is not forbidden, and the existing gates still decide.
AVAILABLE_UNDER_EXISTING_GATES = "available_under_existing_gates"

#: Terminal. Not "blocked", not "pending" -- there is no input that opens it.
UNAVAILABLE_BY_CONTRACT = "unavailable_by_contract"

#: A consumer nobody has classified. Refused until someone does.
UNAVAILABLE_PENDING_CLASSIFICATION = "unavailable_pending_classification"

UNAVAILABLE_REASON = "complete_market_composition_not_qualified"
REOPEN_CONDITION = "new_authoritative_source_contract"

#: The reopen condition spelled out, so nobody reads the short form as "probe VCI again".
REOPEN_NOTE = (
    "Not reopenable by further VCI pagination, further VCI endpoint probing, or by "
    "verifying the volume unit or basis. Only a source that publishes what its volume "
    "figure counts -- matched versus negotiated, auction versus continuous -- can reopen "
    "these, and no such source is active."
)

#: Attached to every descriptive and analytical result. These are not decoration: the
#: capability stays open *because* the caller is required to carry them.
DESCRIPTIVE_WARNINGS = (
    "market_composition_unresolved",
    "corporate_action_adjustment_unresolved",
    "value_is_provider_scoped",
    "not_an_official_exchange_volume_contract",
)


class CapabilityError(ValueError):
    """Fail-closed refusal in the capability matrix."""


# ---------------------------------------------------------------------------------
# Part B -- the matrix
# ---------------------------------------------------------------------------------

def _descriptive(name: str, note: str) -> dict[str, Any]:
    return {
        "capability": name,
        "capability_class": CLASS_DESCRIPTIVE,
        "availability": AVAILABLE_UNDER_EXISTING_GATES,
        "required_warnings": list(DESCRIPTIVE_WARNINGS),
        "namespace": "provider_scoped",
        "note": note,
    }


def _analytical(name: str, note: str) -> dict[str, Any]:
    return {
        "capability": name,
        "capability_class": CLASS_ANALYTICAL,
        "availability": AVAILABLE_UNDER_EXISTING_GATES,
        "required_warnings": list(DESCRIPTIVE_WARNINGS),
        "namespace": "provider_scoped",
        "note": note,
    }


def _unavailable(name: str, capability_class: str, note: str) -> dict[str, Any]:
    return {
        "capability": name,
        "capability_class": capability_class,
        "availability": UNAVAILABLE_BY_CONTRACT,
        "reason": UNAVAILABLE_REASON,
        "reopen_condition": REOPEN_CONDITION,
        "reopen_note": REOPEN_NOTE,
        "required_warnings": [],
        "note": note,
    }


CAPABILITY_MATRIX: dict[str, dict[str, Any]] = {
    # -- descriptive, provider-namespaced -------------------------------------------
    "provider_volume_history_display": _descriptive(
        "provider_volume_history_display",
        "Showing the retained daily volume series as the provider reported it.",
    ),
    "provider_volume_moving_average": _descriptive(
        "provider_volume_moving_average",
        "A mean over the same provider series. Same composition on both sides.",
    ),
    "provider_relative_volume": _descriptive(
        "provider_relative_volume",
        "Today's provider volume against its own trailing mean -- a ratio within one "
        "series, so an unknown constant composition cancels.",
    ),
    "provider_volume_trend_indicator": _descriptive(
        "provider_volume_trend_indicator",
        "Direction of the provider series over time, not a claim about market share.",
    ),
    "provider_volume_anomaly_detection": _descriptive(
        "provider_volume_anomaly_detection",
        "Outliers *within the same provider series*. Cross-provider anomaly detection is "
        "not this capability.",
    ),
    "source_labeled_volume_comparison": _descriptive(
        "source_labeled_volume_comparison",
        "Comparison that names VCI as the source in the output, not in a footnote.",
    ),
    # -- analytical, not liquidity-dependent ----------------------------------------
    "research_only_volume_technical_indicator": _analytical(
        "research_only_volume_technical_indicator",
        "OBV, MFI, Chaikin and similar, whose interpretation is a shape in one series and "
        "does not require knowing the market's complete composition. Research scope: they "
        "may not be presented as a liquidity or executability finding.",
    ),
    "volume_confirmation_signal": _analytical(
        "volume_confirmation_signal",
        "'Did today's bar come with more volume than usual for this ticker' -- a within-"
        "series comparison. It says nothing about how much could have been traded.",
    ),
    "turnover_tier_screening_score": _analytical(
        "turnover_tier_screening_score",
        "Coarse close x volume banding used to rank screening candidates. Retained "
        "because it is a relative screen over one provider series, not a tradable-size "
        "estimate; it must never be labelled or exported as qualified market liquidity.",
    ),
    # -- liquidity-dependent, unavailable by contract ---------------------------------
    "days_to_liquidate": _unavailable(
        "days_to_liquidate",
        CLASS_LIQUIDITY,
        "Divides a position by daily volume. If that volume includes put-through blocks "
        "that were never available to a screen order, the answer is wrong in the "
        "optimistic direction, which is the direction that loses money.",
    ),
    "market_impact_estimation": _unavailable(
        "market_impact_estimation",
        CLASS_LIQUIDITY,
        "Impact models are calibrated against matched continuous volume. Feeding an "
        "undifferentiated total in overstates depth.",
    ),
    "capacity_estimation": _unavailable(
        "capacity_estimation",
        CLASS_LIQUIDITY,
        "Strategy capacity is days-to-liquidate integrated over a book.",
    ),
    "negotiated_versus_matched_flow_analysis": _unavailable(
        "negotiated_versus_matched_flow_analysis",
        CLASS_LIQUIDITY,
        "Requires the split the closeout proved is absent from every observed VCI surface.",
    ),
    "odd_lot_analysis": _unavailable(
        "odd_lot_analysis",
        CLASS_LIQUIDITY,
        "odd_lot_inclusion is unavailable_from_observed_vci_surfaces.",
    ),
    "auction_versus_continuous_decomposition": _unavailable(
        "auction_versus_continuous_decomposition",
        CLASS_LIQUIDITY,
        "One opening-auction quantity was demonstrated to sit inside the accumulator. That "
        "is one leg of one session boundary, not a decomposition -- the closing leg is "
        "unknown and the continuous remainder is a subtraction against unknowns.",
    ),
    "volume_based_ranking_or_recommendation": _unavailable(
        "volume_based_ranking_or_recommendation",
        CLASS_LIQUIDITY,
        "Ranking or recommending on volume presented as qualified market liquidity.",
    ),
    "volume_derived_actionability_upgrade": _unavailable(
        "volume_derived_actionability_upgrade",
        CLASS_LIQUIDITY,
        "No volume finding may raise is_actionable. The unit being shares and the "
        "accumulator reconciling are both true and neither is an actionability input.",
    ),
    # -- execution-dependent, unavailable by contract ---------------------------------
    "participation_rate_sizing": _unavailable(
        "participation_rate_sizing",
        CLASS_EXECUTION,
        "A participation rate is a fraction of *executable matched* volume.",
    ),
    "liquidity_adjusted_position_sizing": _unavailable(
        "liquidity_adjusted_position_sizing",
        CLASS_EXECUTION,
        "Sizing against a figure whose executable fraction is unknown.",
    ),
    "average_daily_volume_portfolio_sizing": _unavailable(
        "average_daily_volume_portfolio_sizing",
        CLASS_EXECUTION,
        "Averaging an undifferentiated total does not differentiate it.",
    ),
    "execution_simulation": _unavailable(
        "execution_simulation",
        CLASS_EXECUTION,
        "Any fill model that treats the volume field as all executable matched liquidity.",
    ),
    "production_backtest_liquidity_constraint": _unavailable(
        "production_backtest_liquidity_constraint",
        CLASS_EXECUTION,
        "A backtest that caps fills by VCI `v` reports a capacity it cannot support.",
    ),
}


def capability(name: str) -> dict[str, Any]:
    """Look a capability up. An unregistered name is refused, never defaulted open."""
    record = CAPABILITY_MATRIX.get(name)
    if record is None:
        raise CapabilityError(f"unregistered_volume_capability:{name}")
    return dict(record)


def capabilities_in_class(capability_class: str) -> list[str]:
    if capability_class not in CAPABILITY_CLASSES:
        raise CapabilityError(f"unknown_capability_class:{capability_class}")
    return sorted(k for k, v in CAPABILITY_MATRIX.items() if v["capability_class"] == capability_class)


UNAVAILABLE_CAPABILITIES = tuple(
    sorted(k for k, v in CAPABILITY_MATRIX.items() if v["availability"] == UNAVAILABLE_BY_CONTRACT)
)
AVAILABLE_CAPABILITIES = tuple(
    sorted(
        k for k, v in CAPABILITY_MATRIX.items() if v["availability"] == AVAILABLE_UNDER_EXISTING_GATES
    )
)


# ---------------------------------------------------------------------------------
# Provider scope -- the verdict belongs to VCI and travels nowhere
# ---------------------------------------------------------------------------------

PROVIDER = "VCI"

#: A field that carries no provider namespace. It cannot inherit a provider's verdict,
#: because it does not say whose number it is.
GENERIC_VOLUME_FIELDS = frozenset(
    {
        "volume",
        "market_volume",
        "total_volume",
        "exchange_volume",
        "official_exchange_volume",
        "matched_volume",
        "traded_volume",
    }
)


def assert_no_generic_field_upgrade(field_name: str) -> None:
    """A generic volume field never inherits the VCI verdict.

    The VCI closeout says something about ``vci.v``. It says nothing about a field called
    ``market_volume``, whose provider is not stated -- and a reader who copies the verdict
    across has silently invented a claim about an unnamed source.
    """
    if str(field_name).strip().lower() in GENERIC_VOLUME_FIELDS:
        raise CapabilityError(f"generic_volume_field_cannot_inherit_provider_verdict:{field_name}")


def provider_scope(provider: str) -> dict[str, Any]:
    """What the VCI contract says about ``provider``. For anyone else: nothing."""
    named = str(provider).strip().upper()
    if named == PROVIDER:
        return {
            "provider": named,
            "contract_applies": True,
            "source": "vci_volume_composition.composition_contract",
        }
    return {
        "provider": named,
        "contract_applies": False,
        "volume_composition": composition.DIMENSION_UNKNOWN,
        "reason": "vci_composition_verdict_does_not_transfer",
        "note": (
            "Another provider's volume field is unqualified because nobody has qualified "
            "it -- not because VCI's verdict was copied onto it. Its own closeout is owed."
        ),
    }


# ---------------------------------------------------------------------------------
# Part C -- the consumer register
# ---------------------------------------------------------------------------------

#: Every volume-touching consumer found in the Producer and Consumer trees, and its class.
#: A consumer absent from this map resolves to ``unknown_or_ambiguous`` and is refused --
#: which is how a newly added consumer gets classified instead of quietly inheriting
#: whatever the surrounding code was allowed to do.
CONSUMER_CLASSIFICATION: dict[str, str] = {
    # Producer
    "risk_liquidity.average_volume": CLASS_DESCRIPTIVE,
    "risk_liquidity.days_to_liquidate": CLASS_LIQUIDITY,
    "risk_liquidity.position_sizing": CLASS_EXECUTION,
    "risk_liquidity.backtest_summary": CLASS_EXECUTION,
    "candlestick_patterns.average_volume20": CLASS_DESCRIPTIVE,
    "candlestick_patterns.rel_vol_calc": CLASS_DESCRIPTIVE,
    "candlestick_patterns.volume_confirmation": CLASS_ANALYTICAL,
    "candlestick_patterns.gtgd20_ty_calc": CLASS_ANALYTICAL,
    "candlestick_patterns.low_liquidity_warning": CLASS_ANALYTICAL,
    "stock_analyzer.score_liquidity": CLASS_ANALYTICAL,
    "stock_analyzer.indicator_volume_features": CLASS_ANALYTICAL,
    "vn_indicators.volume_indicators": CLASS_ANALYTICAL,
    "export_ai_bundle.ohlcv_volume_passthrough": CLASS_DESCRIPTIVE,
    "export_ai_bundle.risk_analysis": CLASS_DESCRIPTIVE,
    "analysis_lane_eligibility.liquidity_claims_gate": CLASS_LIQUIDITY,
    "analysis_lane_eligibility.backtest_claims_gate": CLASS_EXECUTION,
    "market_wide_calculation_readiness.position_sizing": CLASS_EXECUTION,
    "opportunity_snapshot.position_sizing": CLASS_EXECUTION,
    "ticker_capability.T4_market_dependent": CLASS_LIQUIDITY,
    "vnm_execution_contract": CLASS_EXECUTION,
    "vnm_shadow_backtest": CLASS_EXECUTION,
    # Consumer
    "builders.build_ticker_context.risk_analysis_passthrough": CLASS_DESCRIPTIVE,
    "builders.build_ticker_context.price_basis_provenance": CLASS_DESCRIPTIVE,
}


def classify_consumer(consumer_id: str) -> dict[str, Any]:
    """Classify a volume consumer. Unregistered means unavailable, not permitted."""
    capability_class = CONSUMER_CLASSIFICATION.get(consumer_id)
    if capability_class is None:
        return {
            "consumer": consumer_id,
            "capability_class": CLASS_UNKNOWN,
            "availability": UNAVAILABLE_PENDING_CLASSIFICATION,
            "reason": "consumer_not_classified_in_market_volume_capability_matrix",
            "reopen_condition": "classify_the_consumer_in_CONSUMER_CLASSIFICATION",
        }
    if capability_class in {CLASS_LIQUIDITY, CLASS_EXECUTION}:
        return {
            "consumer": consumer_id,
            "capability_class": capability_class,
            "availability": UNAVAILABLE_BY_CONTRACT,
            "reason": UNAVAILABLE_REASON,
            "reopen_condition": REOPEN_CONDITION,
            "reopen_note": REOPEN_NOTE,
        }
    return {
        "consumer": consumer_id,
        "capability_class": capability_class,
        "availability": AVAILABLE_UNDER_EXISTING_GATES,
        "required_warnings": list(DESCRIPTIVE_WARNINGS),
        "note": "Existing freshness and provenance gates still decide; this class does not "
        "bypass them.",
    }


# ---------------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------------

def evaluate(
    name: str,
    *,
    provider: str = PROVIDER,
    field_name: str | None = None,
    existing_gates_passed: bool = False,
) -> dict[str, Any]:
    """Decide one capability for one provider.

    ``existing_gates_passed`` is the caller's own freshness/provenance verdict. It can only
    ever *close* a descriptive capability; it cannot open a contract-unavailable one, and no
    argument to this function can.
    """
    record = capability(name)
    if field_name is not None:
        assert_no_generic_field_upgrade(field_name)
    scope = provider_scope(provider)

    if record["availability"] == UNAVAILABLE_BY_CONTRACT:
        # Deliberately evaluated before the provider check: this capability is unavailable
        # for VCI on composition grounds and unavailable for everyone else on the grounds
        # that they have no closeout at all. There is no provider that opens it.
        return {
            **record,
            "provider": scope["provider"],
            "available": False,
            "liquidity_actionable": False,
        }

    if not scope["contract_applies"]:
        return {
            **record,
            "provider": scope["provider"],
            "available": False,
            "availability": UNAVAILABLE_PENDING_CLASSIFICATION,
            "reason": scope["reason"],
            "note": scope["note"],
            "liquidity_actionable": False,
        }

    return {
        **record,
        "provider": scope["provider"],
        "available": bool(existing_gates_passed),
        "blocked_by": None if existing_gates_passed else "existing_freshness_or_provenance_gate",
        "liquidity_actionable": False,
    }


def matrix_snapshot() -> dict[str, Any]:
    """The whole matrix, for the closeout artifact and for diffing."""
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_contract": "vci_volume_composition",
        "unavailable_reason": UNAVAILABLE_REASON,
        "reopen_condition": REOPEN_CONDITION,
        "reopen_note": REOPEN_NOTE,
        "required_descriptive_warnings": list(DESCRIPTIVE_WARNINGS),
        "capabilities": {name: dict(record) for name, record in sorted(CAPABILITY_MATRIX.items())},
        "consumers": dict(sorted(CONSUMER_CLASSIFICATION.items())),
        "further_vci_pagination_authorized": composition.FURTHER_PAGINATION_AUTHORIZED,
        "further_vci_endpoint_probe_authorized": composition.FURTHER_SPECULATIVE_ENDPOINT_PROBE_AUTHORIZED,
    }


def assert_matrix_fail_closed(snapshot: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Refuse a matrix that has opened something it may not open."""
    snap = snapshot if snapshot is not None else matrix_snapshot()
    for name, record in snap["capabilities"].items():
        klass = record["capability_class"]
        availability = record["availability"]
        if klass in {CLASS_LIQUIDITY, CLASS_EXECUTION} and availability != UNAVAILABLE_BY_CONTRACT:
            raise CapabilityError(f"liquidity_or_execution_capability_is_open:{name}")
        if availability == UNAVAILABLE_BY_CONTRACT:
            if record.get("reason") != UNAVAILABLE_REASON:
                raise CapabilityError(f"unavailable_capability_without_the_contract_reason:{name}")
            if record.get("reopen_condition") != REOPEN_CONDITION:
                raise CapabilityError(f"unavailable_capability_without_reopen_condition:{name}")
        if availability == AVAILABLE_UNDER_EXISTING_GATES:
            if klass not in {CLASS_DESCRIPTIVE, CLASS_ANALYTICAL}:
                raise CapabilityError(f"only_descriptive_or_analytical_may_be_available:{name}")
            missing = set(DESCRIPTIVE_WARNINGS) - set(record.get("required_warnings", []))
            if missing:
                raise CapabilityError(f"available_capability_missing_warnings:{name}:{sorted(missing)}")
    if snap["further_vci_pagination_authorized"] or snap["further_vci_endpoint_probe_authorized"]:
        raise CapabilityError("vci_probing_must_remain_unauthorized")
    return snap
