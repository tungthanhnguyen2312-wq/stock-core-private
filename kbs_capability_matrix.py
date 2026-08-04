"""What may and may not be computed from a KBS price or volume figure, and on whose authority.

WHY THIS MODULE EXISTS
    Phase 1C closed the KBS lane with ``price_basis = ABSENT``, ``volume_basis = ABSENT``,
    and every consumer fail-closed. The finding was right; the shape of the closure was
    wrong. "No documented semantics" was implemented as "no usable data", so a chart nobody
    ever claimed was an official exchange series got blocked alongside the days-to-liquidate
    calculation that genuinely required one.

    Those two are not the same risk and they do not deserve the same gate. Showing the KBS
    daily series, taking a 20-session mean of it, or computing an RSI over it were never
    claims about market composition or about what the exchange counted. Blocking them
    bought no safety and cost the repository a working failover.

THE LINE THIS MATRIX DRAWS
    A capability is available when its output is a statement *about the KBS series*, and
    unavailable when its output is a statement *about the market*. An RSI over KBS closes
    describes the KBS series. A days-to-liquidate figure describes how much could actually
    have been sold, which requires knowing what the volume field counts -- and for KBS that
    is ``unknown`` and there is no field a caller can set to change it.

    The conditional class in the middle exists because provider-series returns sit on the
    line. They are computable and useful, and they are *not* total shareholder return: the
    series they are computed from was restated for distributions by an undocumented method.
    So they are available under a label that says so, and refused under a label that lies.

THE UNKNOWN CLASS IS THE POINT
    A consumer this module has never heard of resolves to ``unknown_or_ambiguous`` and is
    refused. Adding a KBS consumer therefore requires classifying it, which is what keeps
    this matrix true a year from now.
"""

from __future__ import annotations

from typing import Any, Mapping

import evidence_qualification_tiers as tiers
import kbs_empirical_basis as basis

VERSION = "1.0.0"

PROVIDER = "KBS"
SOURCE_AUTHORITY = basis.SOURCE_AUTHORITY

# ---------------------------------------------------------------------------------
# Classes and availability states
# ---------------------------------------------------------------------------------

CLASS_DESCRIPTIVE = "descriptive_provider_scoped"
CLASS_TECHNICAL = "technical_provider_scoped"
CLASS_CONDITIONAL = "conditional_labelled_provider_series"
CLASS_SHADOW_ELIGIBLE = "shadow_only_eligibility"
CLASS_LIQUIDITY = "liquidity_dependent"
CLASS_EXECUTION = "execution_dependent"
CLASS_HISTORICAL_TRUTH = "point_in_time_dependent"
CLASS_UNKNOWN = "unknown_or_ambiguous"

CAPABILITY_CLASSES = (
    CLASS_DESCRIPTIVE,
    CLASS_TECHNICAL,
    CLASS_CONDITIONAL,
    CLASS_SHADOW_ELIGIBLE,
    CLASS_LIQUIDITY,
    CLASS_EXECUTION,
    CLASS_HISTORICAL_TRUTH,
    CLASS_UNKNOWN,
)

#: Available *if its own gates pass*. This module does not assert freshness, schema or
#: provenance; it says the capability is not forbidden, and the existing gates still decide.
AVAILABLE_UNDER_EXISTING_GATES = "available_under_existing_gates"

#: Available only with an explicit label attached. Dropping the label closes it.
AVAILABLE_WITH_REQUIRED_LABEL = "available_with_required_label"

#: Defined as technically eligible, not switched on. This milestone implements no backtest.
ELIGIBILITY_DEFINED_NOT_IMPLEMENTED = "eligibility_defined_not_implemented"

#: Terminal. Not "blocked", not "pending" -- there is no input that opens it.
UNAVAILABLE_BY_CONTRACT = "unavailable_by_contract"

#: A consumer nobody has classified. Refused until someone does.
UNAVAILABLE_PENDING_CLASSIFICATION = "unavailable_pending_classification"

REASON_MARKET_SCOPE = "kbs_volume_market_composition_not_qualified"
REASON_MUTABLE_SERIES = "kbs_price_series_is_provider_restated_by_an_undocumented_method"

REOPEN_SCOPE = "new_authoritative_source_contract_defining_what_the_volume_figure_counts"
REOPEN_MUTABILITY = "first_party_methodology_or_a_point_in_time_immutable_source"

#: Attached to every available result. These are not decoration: the capability stays open
#: *because* the caller is required to carry them.
REQUIRED_WARNINGS = (
    "provider_scoped_kbs_series",
    "source_authority_observed_public_web_endpoint",
    "documented_semantics_absent",
    "price_basis_empirically_deduced_not_documented",
    "price_series_event_adjusted_by_an_unknown_method",
    "volume_market_composition_unresolved",
    "not_an_official_exchange_contract",
)

#: The provenance every output must carry alongside its numbers.
REQUIRED_PROVENANCE_FIELDS = (
    "provider",
    "source_authority",
    "price_basis_qualification",
    "volume_unit_qualification",
    "volume_market_scope",
    "provider_methodology",
    "scope_limitations",
)

#: The label a provider-series return must wear, and the three it must never wear.
PROVIDER_SERIES_RETURN_LABEL = "provider_series_return"
FORBIDDEN_RETURN_LABELS = frozenset(
    {"raw_as_traded_return", "official_exchange_return", "total_shareholder_return"}
)


class KBSCapabilityError(ValueError):
    """Fail-closed refusal in the KBS capability matrix."""


# ---------------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------------


def _open(name: str, capability_class: str, note: str) -> dict[str, Any]:
    return {
        "capability": name,
        "capability_class": capability_class,
        "availability": AVAILABLE_UNDER_EXISTING_GATES,
        "required_warnings": list(REQUIRED_WARNINGS),
        "required_provenance_fields": list(REQUIRED_PROVENANCE_FIELDS),
        "namespace": "provider_scoped",
        "note": note,
    }


def _unavailable(name: str, capability_class: str, reason: str, reopen: str, note: str) -> dict[str, Any]:
    return {
        "capability": name,
        "capability_class": capability_class,
        "availability": UNAVAILABLE_BY_CONTRACT,
        "reason": reason,
        "reopen_condition": reopen,
        "required_warnings": [],
        "required_provenance_fields": [],
        "note": note,
    }


CAPABILITY_MATRIX: dict[str, dict[str, Any]] = {
    # -- descriptive ------------------------------------------------------------------
    "kbs_ohlcv_display": _open(
        "kbs_ohlcv_display",
        CLASS_DESCRIPTIVE,
        "Showing the retained daily series as the provider reported it. This was never a "
        "claim about adjustment or composition, and blocking it bought nothing.",
    ),
    "kbs_historical_chart": _open(
        "kbs_historical_chart",
        CLASS_DESCRIPTIVE,
        "A chart of one provider's series, labelled as that provider's series.",
    ),
    "kbs_descriptive_price_statistics": _open(
        "kbs_descriptive_price_statistics",
        CLASS_DESCRIPTIVE,
        "Range, mean, dispersion over the KBS series. Descriptive of the series.",
    ),
    "kbs_descriptive_volume_statistics": _open(
        "kbs_descriptive_volume_statistics",
        CLASS_DESCRIPTIVE,
        "Same series on both sides, so an unknown constant composition cancels.",
    ),
    "kbs_descriptive_trading_value_statistics": _open(
        "kbs_descriptive_trading_value_statistics",
        CLASS_DESCRIPTIVE,
        "va is present on only part of the history -- the provider omits it exactly where "
        "it restated prices -- so any statistic must state its own coverage.",
    ),
    "kbs_provider_relative_volume": _open(
        "kbs_provider_relative_volume",
        CLASS_DESCRIPTIVE,
        "Today's KBS volume against its own trailing mean: a ratio within one series.",
    ),
    "kbs_provider_price_momentum": _open(
        "kbs_provider_price_momentum",
        CLASS_DESCRIPTIVE,
        "Direction of the KBS series over time, not a claim about realisable return.",
    ),
    "kbs_anomaly_detection": _open(
        "kbs_anomaly_detection",
        CLASS_DESCRIPTIVE,
        "Outliers within the same provider series. Cross-provider anomaly detection is a "
        "different capability and is not this one.",
    ),
    "kbs_cross_provider_corroboration": _open(
        "kbs_cross_provider_corroboration",
        CLASS_DESCRIPTIVE,
        "Comparing KBS against another provider to detect divergence. Agreement is "
        "compatibility evidence and never raises either provider's authority.",
    ),
    # -- technical --------------------------------------------------------------------
    "kbs_moving_average": _open(
        "kbs_moving_average", CLASS_TECHNICAL, "A mean over the KBS series."
    ),
    "kbs_rsi": _open("kbs_rsi", CLASS_TECHNICAL, "A shape in one series."),
    "kbs_macd": _open("kbs_macd", CLASS_TECHNICAL, "A shape in one series."),
    "kbs_bollinger_bands": _open(
        "kbs_bollinger_bands", CLASS_TECHNICAL, "Dispersion around a mean of the same series."
    ),
    "kbs_technical_pattern_research": _open(
        "kbs_technical_pattern_research",
        CLASS_TECHNICAL,
        "Research scope. It may not be presented as a liquidity or executability finding.",
    ),
    "kbs_shadow_analytics": _open(
        "kbs_shadow_analytics",
        CLASS_TECHNICAL,
        "Analytics that claim no official, raw or executable-market semantics.",
    ),
    # -- conditional ------------------------------------------------------------------
    "kbs_provider_series_return": {
        "capability": "kbs_provider_series_return",
        "capability_class": CLASS_CONDITIONAL,
        "availability": AVAILABLE_WITH_REQUIRED_LABEL,
        "required_label": PROVIDER_SERIES_RETURN_LABEL,
        "forbidden_labels": sorted(FORBIDDEN_RETURN_LABELS),
        "required_warnings": list(REQUIRED_WARNINGS),
        "required_provenance_fields": list(REQUIRED_PROVENANCE_FIELDS),
        "namespace": "provider_scoped",
        "note": (
            "The series is event-adjusted by an undocumented method, so a return computed "
            "over it is neither an as-traded return nor a total shareholder return. It is "
            "the return of this provider's series, and it must say so."
        ),
    },
    "kbs_provider_series_technical_continuity": {
        "capability": "kbs_provider_series_technical_continuity",
        "capability_class": CLASS_CONDITIONAL,
        "availability": AVAILABLE_WITH_REQUIRED_LABEL,
        "required_label": PROVIDER_SERIES_RETURN_LABEL,
        "forbidden_labels": sorted(FORBIDDEN_RETURN_LABELS),
        "required_warnings": list(REQUIRED_WARNINGS),
        "required_provenance_fields": list(REQUIRED_PROVENANCE_FIELDS),
        "namespace": "provider_scoped",
        "corporate_action_factors_reapplication": "forbidden_without_a_compatible_contract",
        "note": (
            "An already-adjusted series is continuous across an ex-date, which is what "
            "makes it usable for indicator continuity. Reapplying a corporate-action "
            "factor to it would adjust it twice."
        ),
    },
    # -- shadow-only eligibility (defined, not implemented) ---------------------------
    "kbs_shadow_backtest": {
        "capability": "kbs_shadow_backtest",
        "capability_class": CLASS_SHADOW_ELIGIBLE,
        "availability": ELIGIBILITY_DEFINED_NOT_IMPLEMENTED,
        "required_warnings": list(REQUIRED_WARNINGS),
        "required_provenance_fields": list(REQUIRED_PROVENANCE_FIELDS),
        "note": (
            "Eligibility only. This milestone implements no backtest, and the eligibility "
            "conditions in SHADOW_BACKTEST_CONDITIONS are all required together."
        ),
    },
    # -- liquidity, unavailable by contract -------------------------------------------
    "kbs_days_to_liquidate": _unavailable(
        "kbs_days_to_liquidate", CLASS_LIQUIDITY, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "Divides a position by daily volume. If that volume includes negotiated blocks "
        "that were never available to a screen order, the answer is wrong in the "
        "optimistic direction, which is the direction that loses money.",
    ),
    "kbs_market_impact_estimation": _unavailable(
        "kbs_market_impact_estimation", CLASS_LIQUIDITY, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "Impact models are calibrated against matched continuous volume.",
    ),
    "kbs_liquidity_adjusted_sizing": _unavailable(
        "kbs_liquidity_adjusted_sizing", CLASS_LIQUIDITY, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "Sizing against a figure whose executable fraction is unknown.",
    ),
    "kbs_negotiated_flow_analysis": _unavailable(
        "kbs_negotiated_flow_analysis", CLASS_LIQUIDITY, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "Requires a split no observed KBS surface carries.",
    ),
    "kbs_odd_lot_analysis": _unavailable(
        "kbs_odd_lot_analysis", CLASS_LIQUIDITY, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "odd_lot_inclusion is unknown for KBS.",
    ),
    "kbs_liquidity_dependent_ranking": _unavailable(
        "kbs_liquidity_dependent_ranking", CLASS_LIQUIDITY, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "Ranking or recommending on volume presented as qualified market liquidity.",
    ),
    "kbs_volume_derived_actionability_upgrade": _unavailable(
        "kbs_volume_derived_actionability_upgrade", CLASS_LIQUIDITY, REASON_MARKET_SCOPE,
        REOPEN_SCOPE,
        "No KBS finding may raise is_actionable. The unit being shares is true and is not "
        "an actionability input.",
    ),
    # -- execution, unavailable by contract -------------------------------------------
    "kbs_participation_rate_sizing": _unavailable(
        "kbs_participation_rate_sizing", CLASS_EXECUTION, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "A participation rate is a fraction of executable matched volume.",
    ),
    "kbs_executable_capacity_claim": _unavailable(
        "kbs_executable_capacity_claim", CLASS_EXECUTION, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "Capacity is days-to-liquidate integrated over a book.",
    ),
    "kbs_production_backtest": _unavailable(
        "kbs_production_backtest", CLASS_EXECUTION, REASON_MARKET_SCOPE, REOPEN_SCOPE,
        "A production backtest reports a capacity it cannot support, over a price series "
        "that is restated after the fact.",
    ),
    # -- point-in-time truth, unavailable by contract ----------------------------------
    "kbs_point_in_time_valuation": _unavailable(
        "kbs_point_in_time_valuation", CLASS_HISTORICAL_TRUTH, REASON_MUTABLE_SERIES,
        REOPEN_MUTABILITY,
        "The value the series reports for a past date is not the value that was quoted on "
        "that date, so it cannot support a claim about what was knowable then.",
    ),
    "kbs_official_exchange_price_claim": _unavailable(
        "kbs_official_exchange_price_claim", CLASS_HISTORICAL_TRUTH, REASON_MUTABLE_SERIES,
        REOPEN_MUTABILITY,
        "An observed web endpoint with no published schema is not the exchange.",
    ),
    "kbs_official_total_return_claim": _unavailable(
        "kbs_official_total_return_claim", CLASS_HISTORICAL_TRUTH, REASON_MUTABLE_SERIES,
        REOPEN_MUTABILITY,
        "Total return requires a known distribution treatment. The method is undocumented.",
    ),
}

OPEN_AVAILABILITIES = frozenset(
    {AVAILABLE_UNDER_EXISTING_GATES, AVAILABLE_WITH_REQUIRED_LABEL}
)

OPEN_CLASSES = frozenset({CLASS_DESCRIPTIVE, CLASS_TECHNICAL, CLASS_CONDITIONAL})
CLOSED_CLASSES = frozenset({CLASS_LIQUIDITY, CLASS_EXECUTION, CLASS_HISTORICAL_TRUTH})

#: Every condition a shadow backtest would need, all required together. Defining them is
#: the whole deliverable here; none of them is switched on.
SHADOW_BACKTEST_CONDITIONS: tuple[str, ...] = (
    "price_field_identity_stable",
    "price_basis_at_least_empirically_deduced",
    "historical_rewrite_behaviour_explicitly_represented",
    "no_point_in_time_claim_made",
    "no_external_corporate_action_factor_reapplied",
    "liquidity_constraints_disabled",
    "results_not_published_and_not_used_as_recommendations",
    "is_actionable_remains_false",
)


def capability(name: str) -> dict[str, Any]:
    """Look a capability up. An unregistered name is refused, never defaulted open."""
    record = CAPABILITY_MATRIX.get(name)
    if record is None:
        raise KBSCapabilityError(f"unregistered_kbs_capability:{name}")
    return dict(record)


def capabilities_in_class(capability_class: str) -> list[str]:
    if capability_class not in CAPABILITY_CLASSES:
        raise KBSCapabilityError(f"unknown_capability_class:{capability_class}")
    return sorted(k for k, v in CAPABILITY_MATRIX.items() if v["capability_class"] == capability_class)


AVAILABLE_CAPABILITIES = tuple(
    sorted(k for k, v in CAPABILITY_MATRIX.items() if v["availability"] in OPEN_AVAILABILITIES)
)
UNAVAILABLE_CAPABILITIES = tuple(
    sorted(k for k, v in CAPABILITY_MATRIX.items() if v["availability"] == UNAVAILABLE_BY_CONTRACT)
)


# ---------------------------------------------------------------------------------
# Provider scope -- the verdict belongs to KBS and travels nowhere
# ---------------------------------------------------------------------------------

#: A field that carries no provider namespace. It cannot inherit a provider's verdict,
#: because it does not say whose number it is.
GENERIC_FIELDS = frozenset(
    {
        "close",
        "adjusted_close",
        "volume",
        "market_volume",
        "total_volume",
        "exchange_volume",
        "official_exchange_volume",
        "official_close",
        "matched_volume",
        "traded_volume",
    }
)


def assert_no_generic_field_upgrade(field_name: str) -> None:
    """A generic field never inherits the KBS verdict."""
    if str(field_name).strip().lower() in GENERIC_FIELDS:
        raise KBSCapabilityError(f"generic_field_cannot_inherit_provider_verdict:{field_name}")


def provider_scope(provider: str) -> dict[str, Any]:
    """What the KBS contract says about ``provider``. For anyone else: nothing."""
    named = str(provider).strip().upper()
    if named == PROVIDER:
        return {"provider": named, "contract_applies": True, "source": "kbs_empirical_basis"}
    return {
        "provider": named,
        "contract_applies": False,
        "reason": "kbs_verdict_does_not_transfer",
        "note": (
            "Another provider's fields are unqualified because nobody qualified them -- not "
            "because the KBS verdict was copied across. Its own bounded lane is owed."
        ),
    }


# ---------------------------------------------------------------------------------
# The consumer register
# ---------------------------------------------------------------------------------

#: Every KBS-touching consumer, and its class. A consumer absent from this map resolves to
#: ``unknown_or_ambiguous`` and is refused.
CONSUMER_CLASSIFICATION: dict[str, str] = {
    "vn_stock_pipeline.kbs_ohlcv_failover_ingest": CLASS_DESCRIPTIVE,
    "export_ai_bundle.ohlcv_passthrough": CLASS_DESCRIPTIVE,
    "candlestick_patterns.average_volume20": CLASS_DESCRIPTIVE,
    "candlestick_patterns.rel_vol_calc": CLASS_DESCRIPTIVE,
    "vn_indicators.moving_average": CLASS_TECHNICAL,
    "vn_indicators.rsi": CLASS_TECHNICAL,
    "vn_indicators.macd": CLASS_TECHNICAL,
    "vn_indicators.bollinger": CLASS_TECHNICAL,
    "stock_analyzer.indicator_features": CLASS_TECHNICAL,
    "shadow_analytics_pilot.provider_scoped_series": CLASS_TECHNICAL,
    "point_in_time_adjusted_returns.series_return": CLASS_CONDITIONAL,
    "risk_liquidity.days_to_liquidate": CLASS_LIQUIDITY,
    "risk_liquidity.position_sizing": CLASS_EXECUTION,
    "risk_liquidity.backtest_summary": CLASS_EXECUTION,
    "analysis_lane_eligibility.liquidity_claims_gate": CLASS_LIQUIDITY,
    "analysis_lane_eligibility.backtest_claims_gate": CLASS_EXECUTION,
    "opportunity_snapshot.position_sizing": CLASS_EXECUTION,
    "ticker_capability.T4_market_dependent": CLASS_LIQUIDITY,
    "historical_valuation_snapshot.point_in_time_price": CLASS_HISTORICAL_TRUTH,
    "point_in_time_adjusted_prices.reconstruction": CLASS_HISTORICAL_TRUTH,
}


def classify_consumer(consumer_id: str) -> dict[str, Any]:
    """Classify a KBS consumer. Unregistered means unavailable, not permitted."""
    capability_class = CONSUMER_CLASSIFICATION.get(consumer_id)
    if capability_class is None:
        return {
            "consumer": consumer_id,
            "capability_class": CLASS_UNKNOWN,
            "availability": UNAVAILABLE_PENDING_CLASSIFICATION,
            "reason": "consumer_not_classified_in_kbs_capability_matrix",
            "reopen_condition": "classify_the_consumer_in_CONSUMER_CLASSIFICATION",
        }
    if capability_class in CLOSED_CLASSES:
        return {
            "consumer": consumer_id,
            "capability_class": capability_class,
            "availability": UNAVAILABLE_BY_CONTRACT,
            "reason": REASON_MARKET_SCOPE
            if capability_class in {CLASS_LIQUIDITY, CLASS_EXECUTION}
            else REASON_MUTABLE_SERIES,
            "reopen_condition": REOPEN_SCOPE
            if capability_class in {CLASS_LIQUIDITY, CLASS_EXECUTION}
            else REOPEN_MUTABILITY,
        }
    return {
        "consumer": consumer_id,
        "capability_class": capability_class,
        "availability": AVAILABLE_UNDER_EXISTING_GATES,
        "required_warnings": list(REQUIRED_WARNINGS),
        "note": "Existing freshness, schema and provenance gates still decide; this class "
        "does not bypass them.",
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
    label: str | None = None,
) -> dict[str, Any]:
    """Decide one capability for one provider.

    ``existing_gates_passed`` is the caller's own freshness/schema/provenance verdict. It
    can only ever *close* an open capability; no argument to this function opens a
    contract-unavailable one.
    """
    record = capability(name)
    if field_name is not None:
        assert_no_generic_field_upgrade(field_name)
    scope = provider_scope(provider)

    if record["availability"] == UNAVAILABLE_BY_CONTRACT:
        # Evaluated before the provider check on purpose: this capability is unavailable
        # for KBS on its own grounds and unavailable for everyone else on the grounds that
        # they have no lane at all. No provider opens it.
        return {**record, "provider": scope["provider"], "available": False, "liquidity_actionable": False}

    if record["availability"] == ELIGIBILITY_DEFINED_NOT_IMPLEMENTED:
        return {
            **record,
            "provider": scope["provider"],
            "available": False,
            "reason": "eligibility_defined_but_not_implemented_in_this_milestone",
            "conditions": list(SHADOW_BACKTEST_CONDITIONS),
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

    if record["availability"] == AVAILABLE_WITH_REQUIRED_LABEL:
        if label in FORBIDDEN_RETURN_LABELS:
            raise KBSCapabilityError(f"forbidden_return_label:{label}")
        if label != record["required_label"]:
            return {
                **record,
                "provider": scope["provider"],
                "available": False,
                "reason": f"required_label_missing:{record['required_label']}",
                "liquidity_actionable": False,
            }

    return {
        **record,
        "provider": scope["provider"],
        "available": bool(existing_gates_passed),
        "blocked_by": None if existing_gates_passed else "existing_freshness_or_provenance_gate",
        "liquidity_actionable": False,
    }


def assert_corporate_action_factors_not_reapplied(
    *, series_already_adjusted: bool, factor_source_contract: str | None
) -> None:
    """Refuse to adjust an already-adjusted series a second time.

    A compatible contract would have to state what the provider already applied. None
    exists for KBS, so the only safe answer is no.
    """
    if not series_already_adjusted:
        return
    if factor_source_contract:
        raise KBSCapabilityError(
            f"corporate_action_factor_reapplication_requires_a_compatible_contract:"
            f"{factor_source_contract}"
        )
    raise KBSCapabilityError("corporate_action_factors_cannot_be_reapplied_to_an_adjusted_series")


def shadow_backtest_eligibility(conditions: Mapping[str, bool]) -> dict[str, Any]:
    """Whether a shadow backtest *would* be eligible. It is never thereby implemented."""
    unmet = [name for name in SHADOW_BACKTEST_CONDITIONS if not conditions.get(name)]
    return {
        "eligible": not unmet,
        "unmet_conditions": unmet,
        "implemented": False,
        "availability": ELIGIBILITY_DEFINED_NOT_IMPLEMENTED,
        "is_actionable": False,
        "liquidity_actionable": False,
    }


def matrix_snapshot() -> dict[str, Any]:
    """The whole matrix, for the closeout artifact and for diffing."""
    return {
        "schema_version": VERSION,
        "provider": PROVIDER,
        "source_authority": SOURCE_AUTHORITY,
        "source_contract": "kbs_empirical_basis",
        "documented_semantics": "absent",
        "field_identity": "qualified",
        "empirical_semantics": "partially_available",
        "descriptive_capability": "available",
        "technical_capability": "provider_scoped_available",
        "liquidity_capability": "unavailable",
        "required_warnings": list(REQUIRED_WARNINGS),
        "required_provenance_fields": list(REQUIRED_PROVENANCE_FIELDS),
        "capabilities": {name: dict(record) for name, record in sorted(CAPABILITY_MATRIX.items())},
        "consumers": dict(sorted(CONSUMER_CLASSIFICATION.items())),
        "shadow_backtest_conditions": list(SHADOW_BACKTEST_CONDITIONS),
        "volume_market_scope": basis.market_scope_contract()["volume_market_scope"],
        "liquidity_actionable": False,
        "is_actionable_effect": "none",
    }


def assert_matrix_fail_closed(snapshot: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Refuse a matrix that has opened something it may not open."""
    snap = snapshot if snapshot is not None else matrix_snapshot()
    for name, record in snap["capabilities"].items():
        klass = record["capability_class"]
        availability = record["availability"]
        if klass in CLOSED_CLASSES and availability != UNAVAILABLE_BY_CONTRACT:
            raise KBSCapabilityError(f"closed_class_capability_is_open:{name}")
        if availability == UNAVAILABLE_BY_CONTRACT:
            if record.get("reason") not in {REASON_MARKET_SCOPE, REASON_MUTABLE_SERIES}:
                raise KBSCapabilityError(f"unavailable_capability_without_a_contract_reason:{name}")
            if not record.get("reopen_condition"):
                raise KBSCapabilityError(f"unavailable_capability_without_reopen_condition:{name}")
        if availability in OPEN_AVAILABILITIES:
            if klass not in OPEN_CLASSES:
                raise KBSCapabilityError(f"only_open_classes_may_be_available:{name}")
            missing = set(REQUIRED_WARNINGS) - set(record.get("required_warnings", []))
            if missing:
                raise KBSCapabilityError(f"available_capability_missing_warnings:{name}:{sorted(missing)}")
            missing_provenance = set(REQUIRED_PROVENANCE_FIELDS) - set(
                record.get("required_provenance_fields", [])
            )
            if missing_provenance:
                raise KBSCapabilityError(
                    f"available_capability_missing_provenance:{name}:{sorted(missing_provenance)}"
                )
        if availability == AVAILABLE_WITH_REQUIRED_LABEL:
            if record.get("required_label") != PROVIDER_SERIES_RETURN_LABEL:
                raise KBSCapabilityError(f"conditional_capability_without_its_label:{name}")
            if set(record.get("forbidden_labels", ())) != FORBIDDEN_RETURN_LABELS:
                raise KBSCapabilityError(f"conditional_capability_forbidden_labels_drifted:{name}")
    if snap["liquidity_actionable"]:
        raise KBSCapabilityError("liquidity_actionable_must_stay_false")
    if snap["volume_market_scope"] != "unknown":
        raise KBSCapabilityError("kbs_volume_market_scope_must_stay_unknown")
    if tiers.may_claim_official_semantics(
        snap.get("price_basis_qualification", tiers.EMPIRICALLY_DEDUCED)
    ):
        raise KBSCapabilityError("kbs_has_no_documented_semantics_to_claim")
    return snap
