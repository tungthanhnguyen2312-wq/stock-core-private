"""Canonical, semantic-identity-first capability registry across market-data sources.

WHY THIS MODULE EXISTS
    Every existing capability contract in this repository is organized around a *provider's
    own bounded qualification*: ``provider_price_basis_registry.py`` answers "is this
    provider's price series raw or adjusted", ``market_basis_capability_registry.py``
    answers "what can I compute from KBS/VCI today" (and only KBS/VCI -- DNSE and FHSC are
    outside its ``PROVIDERS`` tuple), and each ``dnse_*_capability.py`` module answers "what
    does this one DNSE endpoint qualify for". None of them start from the *semantic field*
    (a close price, a matched-volume figure, a foreign net-buy value) and ask "which sources
    can answer this, in what native shape, and what would it take to trust it more". That is
    a capability-first question, not a provider-first one, and nothing in the repository
    answered it before this module.

    This module resolves that by delegating, not re-deriving. Every fact recorded here cites
    the bounded module or `docs/STATE.md` entry that already established it. No probe, fetch,
    or qualification is re-run, no verdict is re-litigated, and no existing provider-scoped
    registry (``provider_price_basis_registry.py``, ``market_basis_capability_registry.py``,
    every ``dnse_*_capability.py``/``dnse_fhsc_*.py`` module) is modified or superseded.

WHAT IT ADDS ON TOP
    A canonical semantic-identity taxonomy (:data:`SEMANTIC_FIELDS`) spanning PRICE, VOLUME,
    TRADED_VALUE, FOREIGN, PROPRIETARY, MICROSTRUCTURE and REFERENCE, and one registry
    (:data:`CAPABILITY_REGISTRY`) of records keyed by ``(semantic_identity, source)`` that
    each carry: the source/capability(endpoint) identity, the provider-native and canonical
    representations, a usability state drawn from a fixed vocabulary
    (:data:`USABILITY_STATES`), known semantic gaps, authority requirements, and permitted /
    prohibited use cases. A semantic identity may have zero, one, or several source records
    -- :func:`source_candidates` reports how many -- and one source's absence, weakness or
    rate-limiting affects only that identity's own records, never the registry as a whole.

WHAT IT DOES NOT DO
    It never promotes authority. Every record's ``authority_effect`` is the literal string
    ``"NONE"`` (checked by :func:`assert_registry_fail_closed`), and no record here can make
    ``RAW_AS_TRADED``, PIT, liquidity, sizing, execution or recommendation eligible -- those
    stay exactly where the citing module already put them. It does not widen the legacy
    VNStock/VCI/KBS ingestion architecture (``market_basis_capability_registry.py`` remains
    the authority for that lane, untouched). It does not acquire, probe, backfill or qualify
    anything; every entry reflects evidence already on record as of 2026-08-21. Where no
    supporting module or `docs/STATE.md` entry was found by targeted search, the entry is
    honestly ``MISSING`` rather than fabricated -- see PROPRIETARY and MICROSTRUCTURE below.
"""

from __future__ import annotations

from typing import Any, Mapping

VERSION = "1.0.0"

# ---------------------------------------------------------------------------------
# Sources. Legacy VCI/KBS are represented only where the taxonomy is describing a
# capability that already exists in that lane (e.g. REFERENCE/company-profile shares) --
# this module reads that lane, it does not expand it. DERIVED_CANONICAL is not a market
# data source; it names records this repository itself computes (see OPEN_VND etc.),
# never a provider observation.
# ---------------------------------------------------------------------------------

SOURCE_DNSE = "DNSE"
SOURCE_FHSC = "FHSC"
SOURCE_OFFICIAL = "OFFICIAL"
SOURCE_VCI = "VCI"
SOURCE_KBS = "KBS"
SOURCE_DERIVED = "DERIVED_CANONICAL"

SOURCES = (SOURCE_DNSE, SOURCE_FHSC, SOURCE_OFFICIAL, SOURCE_VCI, SOURCE_KBS, SOURCE_DERIVED)

# ---------------------------------------------------------------------------------
# Semantic family taxonomy -- the owner-specified field identities, verbatim. PRICE
# deliberately lists both the *_KVND (provider-native) and *_VND (canonical) identities as
# distinct semantic identities per the milestone spec; this module reconciles that with a
# per-record provider-native/canonical split by treating the *_VND identities as
# SOURCE_DERIVED records that point back at their *_KVND counterpart (see
# ``derived_from`` in the PRICE section of CAPABILITY_REGISTRY below).
# ---------------------------------------------------------------------------------

FAMILY_PRICE = "PRICE"
FAMILY_VOLUME = "VOLUME"
FAMILY_TRADED_VALUE = "TRADED_VALUE"
FAMILY_FOREIGN = "FOREIGN"
FAMILY_PROPRIETARY = "PROPRIETARY"
FAMILY_MICROSTRUCTURE = "MICROSTRUCTURE"
FAMILY_REFERENCE = "REFERENCE"

SEMANTIC_FIELDS: Mapping[str, tuple[str, ...]] = {
    FAMILY_PRICE: (
        "OPEN_KVND", "HIGH_KVND", "LOW_KVND", "CLOSE_KVND",
        "OPEN_VND", "HIGH_VND", "LOW_VND", "CLOSE_VND",
    ),
    FAMILY_VOLUME: (
        "MATCHED_VOLUME_SHARES", "PUT_THROUGH_VOLUME_SHARES", "TOTAL_VOLUME_SHARES",
    ),
    FAMILY_TRADED_VALUE: (
        "MATCHED_TRADED_VALUE_VND", "PUT_THROUGH_TRADED_VALUE_VND", "TOTAL_TRADED_VALUE_VND",
    ),
    FAMILY_FOREIGN: (
        "FOREIGN_BUY_VOLUME", "FOREIGN_SELL_VOLUME", "FOREIGN_NET_VOLUME",
        "FOREIGN_BUY_VALUE", "FOREIGN_SELL_VALUE", "FOREIGN_NET_VALUE",
        "FOREIGN_ROOM_MAX", "FOREIGN_ROOM_OWNED", "FOREIGN_ROOM_AVAILABLE",
    ),
    # The milestone asks for explicit buy/sell/net volume/value semantics "if already
    # supported or representable without widening scope". Targeted search (foreign*.py,
    # *dnse*.py, *fhsc*.py) found no proprietary/principal-desk trading source anywhere in
    # this repository. The family and its six identities are defined for schema
    # completeness; every record is MISSING -- see CAPABILITY_REGISTRY.
    FAMILY_PROPRIETARY: (
        "PROPRIETARY_BUY_VOLUME", "PROPRIETARY_SELL_VOLUME", "PROPRIETARY_NET_VOLUME",
        "PROPRIETARY_BUY_VALUE", "PROPRIETARY_SELL_VALUE", "PROPRIETARY_NET_VALUE",
    ),
    # Same discipline as PROPRIETARY: the owner's brief describes the shape ("active buy/sell
    # counts and volume semantics") without naming exact fields, so these four identities are
    # this module's own naming. No FHSC contract reviewed this session (fhsc_retained_live_
    # reconciliation.py, fhsc_historical_price_semantics.py) exposes tick-level active
    # buy/sell counts; every record is MISSING.
    FAMILY_MICROSTRUCTURE: (
        "ACTIVE_BUY_COUNT", "ACTIVE_SELL_COUNT", "ACTIVE_BUY_VOLUME", "ACTIVE_SELL_VOLUME",
    ),
    FAMILY_REFERENCE: (
        "SYMBOL", "EXCHANGE", "LISTED_SHARES", "OUTSTANDING_SHARES", "FREE_FLOAT",
    ),
}

ALL_SEMANTIC_IDENTITIES: frozenset[str] = frozenset(
    identity for fields in SEMANTIC_FIELDS.values() for identity in fields
)


def family_of(semantic_identity: str) -> str | None:
    for family, fields in SEMANTIC_FIELDS.items():
        if semantic_identity in fields:
            return family
    return None


# ---------------------------------------------------------------------------------
# Usability state vocabulary. Distinct from, and never a substitute for, any provider's own
# qualification vocabulary (``documented_verified`` / ``empirically_deduced`` per
# docs/AI_RULES.md, or a specific module's own result enum such as
# ``dnse_foreign_flow_capability.PARTIALLY_QUALIFIED``). This vocabulary describes
# *usability for research/analytics purposes*, never source authority -- see
# docs/AI_RULES.md and Section 5 of the 2026-08-21 capability-first rebaseline milestone.
# ---------------------------------------------------------------------------------

RAW_RETAINED = "RAW_RETAINED"  # observed and stored; no semantic mapping performed yet
SEMANTIC_MAPPED = "SEMANTIC_MAPPED"  # field identity is known and mapped; usability untested
RESEARCH_USABLE = "RESEARCH_USABLE"  # usable for the specific bounded use cases it names
SHADOW_CALIBRATED = "SHADOW_CALIBRATED"  # empirically cross-checked against a shadow/reference source
SEMANTIC_UNRESOLVED = "SEMANTIC_UNRESOLVED"  # identity known; meaning/unit/basis not established
CONFLICTING = "CONFLICTING"  # two or more sources or checks disagree; fails closed
PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"  # evidence acquisition blocked by a rate limit
MISSING = "MISSING"  # no supporting source or module identified

USABILITY_STATES = frozenset(
    {RAW_RETAINED, SEMANTIC_MAPPED, RESEARCH_USABLE, SHADOW_CALIBRATED,
     SEMANTIC_UNRESOLVED, CONFLICTING, PROVIDER_RATE_LIMITED, MISSING}
)

#: Usability states that a record must never carry together with a truthy authority claim.
#: Enforced by :func:`assert_registry_fail_closed`; this is the "no automatic authority
#: promotion" guarantee, expressed as data rather than as a comment.
_NON_AUTHORITATIVE_STATES = USABILITY_STATES  # every state in this registry is non-authoritative


class CapabilityRegistryError(ValueError):
    """Fail-closed refusal from the canonical capability registry."""


def _record(
    *, semantic_identity: str, source: str, source_capability_id: str,
    provider_native_representation: Mapping[str, Any] | None,
    canonical_representation: Mapping[str, Any] | None,
    usability_state: str, known_semantic_gaps: tuple[str, ...],
    authority_requirements: tuple[str, ...], permitted_use_cases: tuple[str, ...],
    prohibited_use_cases: tuple[str, ...] = (), evidence: tuple[str, ...],
    derived_from: str | None = None, note: str = "",
) -> dict[str, Any]:
    if semantic_identity not in ALL_SEMANTIC_IDENTITIES:
        raise CapabilityRegistryError(f"unregistered_semantic_identity:{semantic_identity}")
    if source not in SOURCES:
        raise CapabilityRegistryError(f"unregistered_source:{source}")
    if usability_state not in USABILITY_STATES:
        raise CapabilityRegistryError(f"unregistered_usability_state:{usability_state}")
    return {
        "semantic_identity": semantic_identity,
        "semantic_family": family_of(semantic_identity),
        "source": source,
        "source_capability_id": source_capability_id,
        "provider_native_representation": dict(provider_native_representation)
        if provider_native_representation is not None else None,
        "canonical_representation": dict(canonical_representation)
        if canonical_representation is not None else None,
        "usability_state": usability_state,
        "known_semantic_gaps": known_semantic_gaps,
        "authority_requirements": authority_requirements,
        "permitted_use_cases": permitted_use_cases,
        "prohibited_use_cases": prohibited_use_cases,
        "evidence": evidence,
        "derived_from": derived_from,
        "note": note,
        "authority_effect": "NONE",
    }


# ---------------------------------------------------------------------------------
# Instrument class. Nominal today: P0-C.2 (docs/STATE.md) established that
# ACTIVE_UNIVERSE and every ETF/WARRANT/BOND/RIGHT/DERIVATIVE/INDEX tier are structurally
# UNKNOWN pending verified exchange/listing evidence, so "VN_LISTED_EQUITY" below names the
# instrument class every cited capability was actually observed against (HOSE/HNX/UPCOM
# common equity such as HPG/VCB/SSI), not a canonical, PIT-safe universe membership claim.
# ---------------------------------------------------------------------------------

INSTRUMENT_CLASS_VN_LISTED_EQUITY = "VN_LISTED_EQUITY"

# DNSE's own closed-session OHLC endpoint -- the capability behind every *_KVND price record
# sourced from DNSE below.
_DNSE_OHLC_ELIGIBLE_USE = (
    "SOURCE_RECONCILIATION", "FIELD_CONSISTENCY_VALIDATION", "ANOMALY_DETECTION",
    "SCALE_INVARIANT_TECHNICAL_TRANSFORMATIONS_WITHIN_SAME_REPRESENTATION",
)
_DNSE_OHLC_PROHIBITED_USE = (
    "MARKET_CAPITALIZATION", "MONETARY_VALUATION", "VND_POSITION_SIZING", "TRADED_VALUE_LIQUIDITY",
    "ABSOLUTE_TARGET_PRICE", "RAW_AS_TRADED_BACKTEST", "CORPORATE_ACTION_FACTOR_INFERENCE",
    "HISTORICAL_BASIS_SENSITIVE_ANALYTICS",
)
_DNSE_OHLC_EVIDENCE = (
    "dnse_provider_native_closed_ohlc.py (PROVIDER_NATIVE_CLOSED_OHLC_REPRESENTATION, "
    "FORMAL_PRICE_UNIT=UNRESOLVED at this tier)",
    "market_data_source_authority.DNSE_OHLC_PRICE_BASIS="
    "ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME",
)
_DNSE_OHLC_GAPS = (
    "formal_price_unit_unresolved_at_producer_qualification_tier:"
    "dnse_provider_native_closed_ohlc.FORMAL_PRICE_UNIT",
    "raw_as_traded_not_qualified:dnse_provider_native_closed_ohlc.RAW_AS_TRADED",
    "adjustment_basis_is_adjusted_not_raw_not_point_in_time:"
    "market_data_source_authority.DNSE_OHLC_PRICE_BASIS",
)


def _dnse_kvnd_record(identity: str) -> dict[str, Any]:
    field = identity.removesuffix("_KVND").lower()
    return _record(
        semantic_identity=identity, source=SOURCE_DNSE, source_capability_id="dnse:/price/ohlc:1D",
        provider_native_representation={
            "unit": "thousands_of_vnd_per_share", "field": field,
            "representation_class": "PROVIDER_NATIVE_CLOSED_OHLC_REPRESENTATION",
        },
        canonical_representation={
            "derived_identity": identity.removesuffix("_KVND") + "_VND",
            "contract": "price_representation_contract:DNSE:ohlc_1D:" + INSTRUMENT_CLASS_VN_LISTED_EQUITY,
        },
        usability_state=RESEARCH_USABLE,
        known_semantic_gaps=_DNSE_OHLC_GAPS,
        authority_requirements=(
            "official_daily_ticker_session_price_route_or_documented_first_party_unit_declaration",
        ),
        permitted_use_cases=_DNSE_OHLC_ELIGIBLE_USE,
        prohibited_use_cases=_DNSE_OHLC_PROHIBITED_USE,
        evidence=_DNSE_OHLC_EVIDENCE + (
            "dnse_bid_ask_capability.PRICE_UNIT=thousands_of_vnd "
            "(same DNSE API, different endpoint, already-qualified corroborating precedent)",
            "market_basis_capability_registry.OFFICIAL_RAW_PRICE_OBSERVATIONS "
            "(HOSE HPG 2024-12-31 official annual report: 26.65 labelled 'VND Thousand' = "
            "26,650 VND/share -- independent official corroboration of the market-wide "
            "thousands-of-VND quoting convention, not a DNSE-specific proof)",
        ),
        note="Usable today only within the same bounded eligible-use classes already "
             "qualified by dnse_provider_native_closed_ohlc.py; the canonical VND "
             "representation does not widen eligibility beyond that set.",
    )


def _dnse_vnd_record(identity: str) -> dict[str, Any]:
    kvnd_identity = identity.removesuffix("_VND") + "_KVND"
    return _record(
        semantic_identity=identity, source=SOURCE_DERIVED,
        source_capability_id="price_representation_contract:DNSE:ohlc_1D:"
        + INSTRUMENT_CLASS_VN_LISTED_EQUITY,
        provider_native_representation=None,
        canonical_representation={"unit": "vnd_per_share", "field": identity.removesuffix("_VND").lower()},
        usability_state=RESEARCH_USABLE,
        known_semantic_gaps=_DNSE_OHLC_GAPS + (
            "canonical_value_is_computed_not_observed:derived_via_price_representation_contract",
        ),
        authority_requirements=(
            "same_as:" + kvnd_identity,
        ),
        permitted_use_cases=_DNSE_OHLC_ELIGIBLE_USE,
        prohibited_use_cases=_DNSE_OHLC_PROHIBITED_USE,
        evidence=("price_representation_contract.py",),
        derived_from=kvnd_identity,
        note="Computed deterministically from the matching *_KVND record via "
             "price_representation_contract.to_canonical(); never independently observed.",
    )


def _fhsc_price_record(identity: str) -> dict[str, Any]:
    return _record(
        semantic_identity=identity, source=SOURCE_FHSC, source_capability_id="fhsc:daily_history/realtime",
        provider_native_representation={"unit": "UNRESOLVED"},
        canonical_representation=None,
        usability_state=SEMANTIC_UNRESOLVED,
        known_semantic_gaps=(
            "fhsc_price_unit_not_independently_established",
            "observed_ratio_to_dnse_close_is_approximately_1000x_but_fails_closed_as_UNIT_MISMATCH:"
            "see fhsc_retained_live_reconciliation.py and docs/STATE.md "
            "'FHSC DNSE Retained Live Reconciliation V1'",
            "prior_10x10_scale_comparator_superseded_NOT_COMPARABLE:"
            "docs/STATE.md 'FHSC/DNSE OHLC Reconciliation Integrity V1' "
            "(root cause was a P3F9B close-only x1000 materialization defect, unrelated to "
            "this registry or to price_representation_contract.py)",
        ),
        authority_requirements=("documented_first_party_fhsc_price_unit_declaration",),
        permitted_use_cases=(), prohibited_use_cases=("ANY_QUANTITATIVE_USE_PENDING_UNIT_RESOLUTION",),
        evidence=(
            "fhsc_retained_live_reconciliation.py", "fhsc_historical_price_semantics.py",
            "docs/STATE.md 'FHSC Historical Price Semantics Qualification V1' (NO_TRANSFORM_QUALIFIED)",
        ),
        note="FHSC is SHADOW_REFERENCE_PROVIDER (market_data_source_authority.py). This "
             "record is deliberately NOT covered by price_representation_contract.py: unlike "
             "DNSE, no same-API corroborating precedent for a thousands-of-VND unit exists "
             "for FHSC, and extending the DNSE contract to FHSC without evidence would be "
             "exactly the over-generalization docs/AI_RULES.md rule 9 forbids.",
    )


_PRICE_RECORDS: tuple[dict[str, Any], ...] = tuple(
    _dnse_kvnd_record(identity) for identity in SEMANTIC_FIELDS[FAMILY_PRICE] if identity.endswith("_KVND")
) + tuple(
    _dnse_vnd_record(identity) for identity in SEMANTIC_FIELDS[FAMILY_PRICE] if identity.endswith("_VND")
) + tuple(
    _fhsc_price_record(identity) for identity in SEMANTIC_FIELDS[FAMILY_PRICE] if identity.endswith("_KVND")
)

# ---------------------------------------------------------------------------------
# VOLUME. DNSE's own /price/ohlc endpoint exposes exactly one volume figure (`v`),
# empirically shown (11 discriminating HPG/VCB/SSI rows, 2026-08-14..20) to equal FHSC's
# documented *matched* volume -- DNSE has no explicit put-through or total figure of its
# own. FHSC separately documents a matched+put_through=total identity. This makes
# PUT_THROUGH_VOLUME_SHARES and TOTAL_VOLUME_SHARES genuine one-source-only (FHSC-only)
# capabilities today: per the milestone's routing rule, that alone must not block their use.
# ---------------------------------------------------------------------------------

_VOLUME_RECORDS: tuple[dict[str, Any], ...] = (
    _record(
        semantic_identity="MATCHED_VOLUME_SHARES", source=SOURCE_DNSE,
        source_capability_id="dnse:/price/ohlc:1D.v",
        provider_native_representation={"unit": "shares", "field": "v"},
        canonical_representation={"unit": "shares"},
        usability_state=SHADOW_CALIBRATED,
        known_semantic_gaps=(
            "generalization_limited_to_tested_windows:11_discriminating_rows_HPG_VCB_SSI_"
            "sessions_2026-08-14_17_18_19_20",
            "4_zero_put_through_rows_non_discriminating",
        ),
        authority_requirements=("wider_cross-session_and_cross-ticker_replication",),
        permitted_use_cases=("SOURCE_RECONCILIATION", "DESCRIPTIVE_DISPLAY", "WITHIN_SERIES_ANALYTICS"),
        prohibited_use_cases=("LIQUIDITY_AUTHORITY", "POSITION_SIZING"),
        evidence=("dnse_fhsc_volume_basis.py",
                  "docs/STATE.md 'DNSE/FHSC Volume Basis Qualification V1' (DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL)"),
    ),
    _record(
        semantic_identity="MATCHED_VOLUME_SHARES", source=SOURCE_FHSC,
        source_capability_id="fhsc:trading_history.matched_volume",
        provider_native_representation={"unit": "shares"}, canonical_representation={"unit": "shares"},
        usability_state=SEMANTIC_MAPPED,
        known_semantic_gaps=("documented_by_provider_but_not_independently_re-verified_this_session",),
        authority_requirements=(), permitted_use_cases=("SOURCE_RECONCILIATION",),
        evidence=("dnse_fhsc_volume_basis.py (MATCHED_VOLUME identity)",),
    ),
    _record(
        semantic_identity="PUT_THROUGH_VOLUME_SHARES", source=SOURCE_FHSC,
        source_capability_id="fhsc:trading_history.put_through_volume",
        provider_native_representation={"unit": "shares"}, canonical_representation={"unit": "shares"},
        usability_state=SEMANTIC_MAPPED,
        known_semantic_gaps=("dnse_has_no_equivalent_field:one_source_only_capability",),
        authority_requirements=(), permitted_use_cases=("SOURCE_RECONCILIATION",),
        evidence=("dnse_fhsc_volume_basis.py (PUT_THROUGH_VOLUME identity)",),
        note="One-source-only by evidence, not by omission: DNSE's endpoint genuinely does "
             "not expose this figure. Per the capability-first routing rule this must not "
             "block the capability's own registry presence or future use.",
    ),
    _record(
        semantic_identity="TOTAL_VOLUME_SHARES", source=SOURCE_FHSC,
        source_capability_id="fhsc:trading_history.total_volume",
        provider_native_representation={"unit": "shares"}, canonical_representation={"unit": "shares"},
        usability_state=SEMANTIC_MAPPED,
        known_semantic_gaps=("dnse_has_no_explicit_generic_traded_value_or_total_volume_comparator",),
        authority_requirements=(), permitted_use_cases=("SOURCE_RECONCILIATION",),
        evidence=("dnse_fhsc_volume_basis.py (TOTAL_VOLUME identity; matched+put_through=total)",),
    ),
)

# ---------------------------------------------------------------------------------
# TRADED_VALUE. P0-B closed with traded value OBSERVED_ABSENT from DNSE's daily OHLC, and
# STATE.md is explicit that "DNSE has no explicit same-session generic traded-value
# comparator". No *_VALUE (VND aggregate) counterpart to the *_VOLUME (shares) fields above
# was found documented for FHSC either in the modules reviewed this session
# (dnse_fhsc_volume_basis.py defines only *_VOLUME constants). Honestly MISSING throughout.
# ---------------------------------------------------------------------------------

_TRADED_VALUE_RECORDS: tuple[dict[str, Any], ...] = tuple(
    _record(
        semantic_identity=identity, source=SOURCE_DNSE, source_capability_id="dnse:/price/ohlc:1D",
        provider_native_representation=None, canonical_representation=None,
        usability_state=MISSING,
        known_semantic_gaps=("observed_absent_from_dnse_daily_ohlc_endpoint:docs/STATE.md P0-B closure",),
        authority_requirements=("a_source_that_exposes_ticker-level_traded_value",),
        permitted_use_cases=(), evidence=("docs/STATE.md 'P0-B' (TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION)",),
    )
    for identity in SEMANTIC_FIELDS[FAMILY_TRADED_VALUE]
)

# ---------------------------------------------------------------------------------
# FOREIGN. Flow (buy/sell/net, volume and value) is production-enabled for HPG/VNM/QNS.
# Room fields exist but their relationship is explicitly undocumented in the same module's
# own docstring -- SEMANTIC_UNRESOLVED, not RESEARCH_USABLE.
#
# The value unit here is deliberately NOT wired to price_representation_contract.py:
# dnse_foreign_flow_capability.VALUE_UNIT is raw VND, the *opposite* convention from the
# thousands-of-VND price/depth fields on the very same DNSE API. This is the concrete case
# the milestone's "no magnitude heuristic" rule exists for -- two same-provider,
# same-currency-named fields with genuinely different native scales, resolved only by an
# explicit per-capability contract (or, here, the explicit absence of one), never inferred.
# ---------------------------------------------------------------------------------

_FOREIGN_FLOW_EVIDENCE = (
    "dnse_foreign_flow_capability.py",
    "market_data_source_authority.DNSE_FOREIGN_FLOW_VALUE_AUTHORITY=PRODUCTION_ENABLED_HPG_VNM_QNS",
)
_FOREIGN_FLOW_RECORDS: tuple[dict[str, Any], ...] = tuple(
    _record(
        semantic_identity=identity, source=SOURCE_DNSE,
        source_capability_id="dnse:/price/{symbol}/foreign-trading",
        provider_native_representation={
            "unit": "shares" if identity.endswith("VOLUME") else "vnd_raw_not_thousands",
        },
        canonical_representation={
            "unit": "shares" if identity.endswith("VOLUME") else "vnd_raw_not_thousands",
            "note": "already canonical VND; NOT passed through the K-VND->VND representation "
                    "contract, which does not apply to this capability",
        },
        usability_state=RESEARCH_USABLE,
        known_semantic_gaps=(
            "trade_type_composition_matched_vs_negotiated_undocumented",
            "point_in_time_qualified_but_provider_scoped_only",
        ),
        authority_requirements=(), permitted_use_cases=("EOD_FLOW", "INTRADAY_CUMULATIVE_FLOW"),
        prohibited_use_cases=("LIQUIDITY_AUTHORITY", "POSITION_SIZING"),
        evidence=_FOREIGN_FLOW_EVIDENCE,
    )
    for identity in ("FOREIGN_BUY_VOLUME", "FOREIGN_SELL_VOLUME", "FOREIGN_NET_VOLUME",
                      "FOREIGN_BUY_VALUE", "FOREIGN_SELL_VALUE", "FOREIGN_NET_VALUE")
) + tuple(
    _record(
        semantic_identity=identity, source=SOURCE_DNSE,
        source_capability_id="dnse:/price/{symbol}/foreign-trading",
        provider_native_representation={"unit": "shares", "field": identity.lower()},
        canonical_representation=None,
        usability_state=SEMANTIC_UNRESOLVED,
        known_semantic_gaps=(
            "field_relationship_and_meaning_undocumented:"
            "which_is_cap_which_is_remainder_whether_nets_current_holdings",
            "no_ownership_or_free_float_percentage_may_be_derived_from_these_fields:"
            "blocks REFERENCE.FREE_FLOAT derivation from this source",
        ),
        authority_requirements=("first_party_documentation_of_the_two_room_fields_relationship",),
        permitted_use_cases=(), prohibited_use_cases=("OWNERSHIP_OR_FREE_FLOAT_DERIVATION",),
        evidence=_FOREIGN_FLOW_EVIDENCE,
        note="A separate legacy VCI-sourced foreign_room_pct field exists outside DNSE/FHSC "
             "scope; not independently re-verified this session and not represented here.",
    )
    for identity in ("FOREIGN_ROOM_MAX", "FOREIGN_ROOM_OWNED", "FOREIGN_ROOM_AVAILABLE")
)

# ---------------------------------------------------------------------------------
# PROPRIETARY and MICROSTRUCTURE: schema-complete, evidence-empty. See the family
# docstring comments above SEMANTIC_FIELDS for the search performed.
# ---------------------------------------------------------------------------------

_PROPRIETARY_RECORDS: tuple[dict[str, Any], ...] = tuple(
    _record(
        semantic_identity=identity, source=SOURCE_DNSE, source_capability_id="UNIDENTIFIED",
        provider_native_representation=None, canonical_representation=None, usability_state=MISSING,
        known_semantic_gaps=(
            "no_proprietary_desk_trading_source_or_module_identified_in_targeted_search_20260821",
        ),
        authority_requirements=("an_owner-approved_proprietary/principal_trading_data_source",),
        permitted_use_cases=(), evidence=(), note="Family defined for schema completeness only.",
    )
    for identity in SEMANTIC_FIELDS[FAMILY_PROPRIETARY]
)

_MICROSTRUCTURE_RECORDS: tuple[dict[str, Any], ...] = tuple(
    _record(
        semantic_identity=identity, source=SOURCE_FHSC, source_capability_id="UNIDENTIFIED",
        provider_native_representation=None, canonical_representation=None, usability_state=MISSING,
        known_semantic_gaps=(
            "no_confirmed_fhsc_or_dnse_tick-level_active_buy/sell_count_contract_identified_"
            "in_targeted_search_20260821",
        ),
        authority_requirements=("a_confirmed_tick-or-order-level_active_buy/sell_source",),
        permitted_use_cases=(), evidence=(), note="Family defined for schema completeness only.",
    )
    for identity in SEMANTIC_FIELDS[FAMILY_MICROSTRUCTURE]
)

# ---------------------------------------------------------------------------------
# REFERENCE.
# ---------------------------------------------------------------------------------

_REFERENCE_RECORDS: tuple[dict[str, Any], ...] = (
    _record(
        semantic_identity="SYMBOL", source=SOURCE_VCI, source_capability_id="instrument_master_sync",
        provider_native_representation={"unit": "ticker_string"}, canonical_representation={"unit": "ticker_string"},
        usability_state=RAW_RETAINED,
        known_semantic_gaps=("availability_and_history_depend_on_provider_response",),
        authority_requirements=(), permitted_use_cases=("IDENTITY",),
        evidence=("instrument_master_sync.py",
                  "docs/data_capability_inventory.md ('Index universe' row: available_unused)",
                  "docs/STATE.md 'P0-C.1' (3,250 instruments reconciled)"),
    ),
    _record(
        semantic_identity="EXCHANGE", source=SOURCE_VCI, source_capability_id="instrument_master_sync",
        provider_native_representation={"unit": "exchange_code"}, canonical_representation={"unit": "exchange_code"},
        usability_state=RAW_RETAINED,
        known_semantic_gaps=("ACTIVE_UNIVERSE_remains_UNKNOWN:docs/STATE.md P0-C.2",),
        authority_requirements=("verified_exchange/listing-status_evidence",),
        permitted_use_cases=("IDENTITY",),
        evidence=("instrument_master_sync.py", "docs/STATE.md 'P0-C.2'"),
    ),
    _record(
        semantic_identity="LISTED_SHARES", source=SOURCE_VCI, source_capability_id="company_profile_sync.overview.issue_share",
        provider_native_representation={"unit": "shares", "provider_label": "ISSUED_SHARES"},
        canonical_representation=None,
        usability_state=SHADOW_CALIBRATED,
        known_semantic_gaps=(
            "provider_semantic_and_effective_date_undocumented:MORE_EVIDENCE_REQUIRED",
            "authority_not_promoted_pending_owner_decision:docs/STATE.md 'P3-F5'",
        ),
        authority_requirements=("documented_provider_methodology_or_official_share_registry",),
        permitted_use_cases=("MVA_SHADOW_PROXY_ONLY",), prohibited_use_cases=("CURRENT_COMMON_SHARE_AUTHORITY", "MARKET_CAP"),
        evidence=("docs/STATE.md 'P3-F5 Current Share Source Promotion & Allowed-Use Review'",
                  "docs/STATE.md 'P3-F6 MVA Provider-Share Proxy Policy' (PROVIDER_REPORTED_ISSUED_SHARES_PROXY)"),
    ),
    _record(
        semantic_identity="OUTSTANDING_SHARES", source=SOURCE_VCI, source_capability_id="company_profile_sync",
        provider_native_representation={"unit": "shares"}, canonical_representation=None,
        usability_state=SEMANTIC_UNRESOLVED,
        known_semantic_gaps=("source-specific;_no_basic/diluted_share-basis_qualified",),
        authority_requirements=("a_qualified_basic/diluted_share-basis_declaration",),
        permitted_use_cases=(),
        evidence=("company_profile_sync.py",
                  "docs/data_capability_inventory.md ('Company profile / shares' row)"),
    ),
    _record(
        semantic_identity="FREE_FLOAT", source=SOURCE_VCI, source_capability_id="UNIDENTIFIED",
        provider_native_representation=None, canonical_representation=None, usability_state=MISSING,
        known_semantic_gaps=(
            "no_source_identified_in_targeted_search_20260821",
            "cannot_be_derived_from_DNSE_FOREIGN_ROOM_*:those_fields_are_themselves_SEMANTIC_UNRESOLVED",
        ),
        authority_requirements=("a_source_documenting_free_float_or_a_resolved_foreign_room_relationship",),
        permitted_use_cases=(), evidence=(),
    ),
)

CAPABILITY_REGISTRY: tuple[dict[str, Any], ...] = (
    _PRICE_RECORDS + _VOLUME_RECORDS + _TRADED_VALUE_RECORDS + _FOREIGN_FLOW_RECORDS
    + _PROPRIETARY_RECORDS + _MICROSTRUCTURE_RECORDS + _REFERENCE_RECORDS
)


# ---------------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------------


def capabilities_for(semantic_identity: str) -> tuple[dict[str, Any], ...]:
    if semantic_identity not in ALL_SEMANTIC_IDENTITIES:
        raise CapabilityRegistryError(f"unregistered_semantic_identity:{semantic_identity}")
    return tuple(dict(r) for r in CAPABILITY_REGISTRY if r["semantic_identity"] == semantic_identity)


def capability(semantic_identity: str, source: str) -> dict[str, Any]:
    """Look up one (semantic_identity, source) record. Fails closed on no exact match."""
    named_source = str(source).strip().upper()
    matches = [r for r in capabilities_for(semantic_identity) if r["source"] == named_source]
    if len(matches) != 1:
        raise CapabilityRegistryError(f"no_unique_capability_record:{semantic_identity}:{named_source}")
    return dict(matches[0])


def source_candidates(semantic_identity: str) -> tuple[str, ...]:
    """Every source with a registry record for this identity, in registry order.

    Zero sources is a valid answer (nothing yet identified). One source is a valid, complete
    answer -- per the milestone's routing rule, this alone must never be treated as a gap
    blocking that source's use. More than one source means overlap exists, never that it is
    required: see :func:`assert_overlap_not_mandatory`.
    """
    seen: list[str] = []
    for record in capabilities_for(semantic_identity):
        if record["source"] not in seen:
            seen.append(record["source"])
    return tuple(seen)


def is_single_source_capability(semantic_identity: str) -> bool:
    return len(source_candidates(semantic_identity)) == 1


def capabilities_for_family(family: str) -> tuple[dict[str, Any], ...]:
    if family not in SEMANTIC_FIELDS:
        raise CapabilityRegistryError(f"unregistered_semantic_family:{family}")
    return tuple(dict(r) for r in CAPABILITY_REGISTRY if r["semantic_family"] == family)


def capabilities_for_source(source: str) -> tuple[dict[str, Any], ...]:
    named_source = str(source).strip().upper()
    if named_source not in SOURCES:
        raise CapabilityRegistryError(f"unregistered_source:{named_source}")
    return tuple(dict(r) for r in CAPABILITY_REGISTRY if r["source"] == named_source)


# ---------------------------------------------------------------------------------
# Fail-closed assertions
# ---------------------------------------------------------------------------------


def assert_registry_fail_closed() -> None:
    """Refuse a registry that fabricates authority, an unknown vocabulary term, or an
    identity/family the taxonomy does not declare."""
    for record in CAPABILITY_REGISTRY:
        if record["authority_effect"] != "NONE":
            raise CapabilityRegistryError(
                f"record_claims_authority_effect:{record['semantic_identity']}:{record['source']}"
            )
        if record["usability_state"] not in _NON_AUTHORITATIVE_STATES:
            raise CapabilityRegistryError(
                f"record_has_unregistered_usability_state:{record['semantic_identity']}:{record['source']}"
            )
        if record["semantic_identity"] not in ALL_SEMANTIC_IDENTITIES:
            raise CapabilityRegistryError(f"record_has_unregistered_identity:{record['semantic_identity']}")
        if record["semantic_family"] is None:
            raise CapabilityRegistryError(f"record_has_no_resolvable_family:{record['semantic_identity']}")


def assert_overlap_not_mandatory() -> None:
    """For every semantic identity with more than one source, at least one individual
    source's own record must be independently usable (not MISSING/CONFLICTING) without the
    other source being present -- proving overlap is exploited when available, never
    required."""
    degraded = {MISSING, CONFLICTING}
    for identity in ALL_SEMANTIC_IDENTITIES:
        sources = source_candidates(identity)
        if len(sources) < 2:
            continue
        if all(capability(identity, s)["usability_state"] in degraded for s in sources):
            raise CapabilityRegistryError(f"multi_source_identity_has_no_independently_usable_source:{identity}")


def snapshot() -> dict[str, Any]:
    by_state: dict[str, int] = {}
    by_family: dict[str, int] = {}
    for record in CAPABILITY_REGISTRY:
        by_state[record["usability_state"]] = by_state.get(record["usability_state"], 0) + 1
        by_family[record["semantic_family"]] = by_family.get(record["semantic_family"], 0) + 1
    single_source = sorted(i for i in ALL_SEMANTIC_IDENTITIES if is_single_source_capability(i))
    multi_source = sorted(i for i in ALL_SEMANTIC_IDENTITIES if len(source_candidates(i)) > 1)
    unrepresented = sorted(i for i in ALL_SEMANTIC_IDENTITIES if not source_candidates(i))
    return {
        "schema_version": VERSION,
        "semantic_families": {family: list(fields) for family, fields in SEMANTIC_FIELDS.items()},
        "usability_states": sorted(USABILITY_STATES),
        "record_count": len(CAPABILITY_REGISTRY),
        "record_count_by_usability_state": by_state,
        "record_count_by_family": by_family,
        "single_source_identities": single_source,
        "multi_source_identities": multi_source,
        "unrepresented_identities": unrepresented,
        "liquidity_actionable": False,
        "raw_as_traded_actionable": False,
        "authority_effect": "NONE",
    }
