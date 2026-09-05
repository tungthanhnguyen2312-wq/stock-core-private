"""Feature-specific input fitness registry (CORE_OPERATING_SPINE_PROVIDER_RESILIENCE_FEATURE_FITNESS_AND_PUBLICATION_V1).

WHY THIS MODULE EXISTS
    A resolved exact-session bar is not universally valid for every downstream feature. This
    repository already enforces that fact correctly in several independent places --
    ``technical_structure_context.resolve_target_session_observations`` (exact-session-close
    compatibility for technical/tactical/momentum history),
    ``market_wide_relative_volume_research``'s strict native-DNSE-volume row check (participation/
    relative-volume), ``multi_source_market_evidence_contract.resolve_ticker`` (per-source price
    resolution), ``monetary_basis_contract.compatible`` (currency/scale compatibility for
    valuation), and ``financial_entity_applicability.metric_applicability`` (entity-class
    applicability for corporate-only metrics) -- but each answers only its own narrow question.
    Nothing previously let a caller ask, in one place: "can THIS evidence support THIS
    feature/use?" This module is that catalog and thin router. It answers the general question by
    naming, for each governed use-case family, the exact existing authority that already governs
    it -- it does not re-implement any of them.

WHAT IT ADDS ON TOP
    :data:`USE_CASE_FAMILIES` names the governed families explicitly.  :data:`FAMILY_REGISTRY`
    records, per family, the required fitness dimensions (source/provider, session, price/volume
    representation and basis, historical-series identity, currency/scale/share basis, period,
    freshness, PIT status, entity-class applicability), the fitness-tier vocabulary the
    authoritative mechanism actually reports, and the module/function that owns the verdict.
    :func:`describe` returns one family's registry entry. Where an existing PUBLIC, pure function
    already answers the per-ticker question cheaply, a thin ``evaluate_*`` wrapper below calls it
    directly (never re-deriving its logic); where the authoritative check lives inside another
    module's private per-row loop or is inherently market-wide rather than per-ticker, the
    registry entry names the authority and the wrapper is intentionally omitted rather than
    reimplemented.  :func:`snapshot` returns the whole registry for the
    ``feature_input_fitness_matrix.json`` operations-review artifact.

WHAT IT DOES NOT DO
    It never assigns a fitness tier by its own independent judgment, never widens a verdict an
    authoritative module already narrowed (AI_RULES.md: "Consumers pass through Producer
    verdicts... may narrow... never widen"), never infers price/volume representation from
    magnitude, and never promotes a blocked capability (see :data:`_STANDING_BLOCKED_FAMILIES`,
    which mirrors ``docs/ROADMAP_STATE.json``'s ``blocked_capabilities`` verbatim -- this module
    does not re-litigate those verdicts, only reflects them). It does not change any existing
    consumer's wiring: every module named here already independently enforces its own gate;
    nothing in this repository is required to import this module for its own gate to remain
    correct. This is a consolidation/catalog layer, not a new authority.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import financial_entity_applicability
import monetary_basis_contract
import multi_source_market_evidence_contract
import technical_structure_context

CONTRACT_VERSION = "feature_input_fitness_contract/v1"

FITNESS_TIERS = ("READY", "RESEARCH_PROXY", "BLOCKED", "NOT_APPLICABLE", "UNKNOWN")

# ---------------------------------------------------------------------------
# Use-case family names (Section 7 of the owner's operating-spine directive).
# ---------------------------------------------------------------------------
CURRENT_SESSION_PRICE = "CURRENT_SESSION_PRICE"
CURRENT_SESSION_RETURN = "CURRENT_SESSION_RETURN"
MARKET_BREADTH = "MARKET_BREADTH"
CURRENT_SESSION_VOLUME = "CURRENT_SESSION_VOLUME"
RELATIVE_VOLUME = "RELATIVE_VOLUME"
TECHNICAL_CLOSE_HISTORY = "TECHNICAL_CLOSE_HISTORY"
TECHNICAL_VOLUME_HISTORY = "TECHNICAL_VOLUME_HISTORY"
OHLC_GEOMETRY = "OHLC_GEOMETRY"
VALUATION_PRICE = "VALUATION_PRICE"
MARKET_CAP = "MARKET_CAP"
P_E = "P_E"
P_B = "P_B"
P_S = "P_S"
EV_EBITDA = "EV_EBITDA"
FUNDAMENTAL_RATIO = "FUNDAMENTAL_RATIO"
TACTICAL_STRUCTURE = "TACTICAL_STRUCTURE"
MOMENTUM = "MOMENTUM"
PARTICIPATION = "PARTICIPATION"
EXECUTION_LIQUIDITY = "EXECUTION_LIQUIDITY"

USE_CASE_FAMILIES: tuple[str, ...] = (
    CURRENT_SESSION_PRICE, CURRENT_SESSION_RETURN, MARKET_BREADTH, CURRENT_SESSION_VOLUME,
    RELATIVE_VOLUME, TECHNICAL_CLOSE_HISTORY, TECHNICAL_VOLUME_HISTORY, OHLC_GEOMETRY,
    VALUATION_PRICE, MARKET_CAP, P_E, P_B, P_S, EV_EBITDA, FUNDAMENTAL_RATIO,
    TACTICAL_STRUCTURE, MOMENTUM, PARTICIPATION, EXECUTION_LIQUIDITY,
)

#: Standing, market-wide blockers this module reflects but never re-derives -- see
#: docs/ROADMAP_STATE.json's own ``blocked_capabilities``. A family listed here is BLOCKED for
#: every ticker/session until an explicit owner-approved reopening changes that upstream record;
#: this module does not itself decide when that happens.
_STANDING_BLOCKED_FAMILIES: dict[str, str] = {
    EXECUTION_LIQUIDITY: (
        "docs/ROADMAP_STATE.json blocked_capabilities.LIQUIDITY_AND_POSITION_SIZING_AUTHORITY: "
        "QUALIFIED_LIQUIDITY_INPUTS=NO and POSITION_SIZING_IS_SAFE=NO market-wide."
    ),
}


class FeatureInputFitnessError(ValueError):
    """An unknown family was requested, or a registry invariant was violated."""


def _entry(
    *, description: str, required_dimensions: tuple[str, ...], fitness_tiers: tuple[str, ...],
    authoritative_module: str, authoritative_functions: tuple[str, ...],
    known_blockers: tuple[str, ...] = (), notes: str = "",
) -> dict[str, Any]:
    return {
        "description": description,
        "required_dimensions": required_dimensions,
        "fitness_tiers": fitness_tiers,
        "authoritative_module": authoritative_module,
        "authoritative_functions": authoritative_functions,
        "known_blockers": known_blockers,
        "notes": notes,
        "standing_block_reason": _STANDING_BLOCKED_FAMILIES.get(authoritative_module, None),
    }


#: The full catalog. Each entry names the ONE existing module/function this repository already
#: uses to answer that family's fitness question -- adding a family here never means adding new
#: enforcement logic; it means pointing at where enforcement already lives.
FAMILY_REGISTRY: dict[str, dict[str, Any]] = {
    CURRENT_SESSION_PRICE: _entry(
        description="Whether a ticker's resolved close/price for the target session is usable at all for Current Research.",
        required_dimensions=("source", "provider_family", "session", "exact_session_identity", "price_representation", "cross_source_conflict"),
        fitness_tiers=("RESOLVED_CORROBORATED", "RESOLVED_CORROBORATED_NON_DNSE_CURRENT_RESEARCH", "RESOLVED_SINGLE_SOURCE_RESEARCH", "SOURCE_CONFLICT", "SESSION_MISSING_ALL_SOURCES"),
        authoritative_module="multi_source_market_evidence_contract",
        authoritative_functions=("resolve_ticker", "resolve_ticker_degraded_dnse"),
        notes="SOURCE_CONFLICT and SESSION_MISSING_ALL_SOURCES both leave resolved_source=None -- neither is usable for any dependent feature.",
    ),
    CURRENT_SESSION_RETURN: _entry(
        description="A same-session price change (today vs. prior close), which additionally requires the prior session's own resolution to be compatible with today's.",
        required_dimensions=("source", "session", "exact_session_identity", "prior_session_identity", "price_representation", "adjustment_basis_agreement"),
        fitness_tiers=FITNESS_TIERS,
        authoritative_module="multi_source_market_evidence_contract",
        authoritative_functions=("resolve_ticker",),
        notes=(
            "No dedicated engine computes a standalone 'current session return' feature in this "
            "repository today; a caller must independently resolve CURRENT_SESSION_PRICE at both "
            "the target and prior session via the same authority and must not assume comparability "
            "across a source change between the two sessions. Documented here as a placeholder "
            "family so a future consumer does not invent an ad hoc comparison."
        ),
    ),
    MARKET_BREADTH: _entry(
        description="Market-wide up/down/unchanged counts and current-equity-universe denominators.",
        required_dimensions=("session", "membership_status", "instrument_class", "exchange"),
        fitness_tiers=FITNESS_TIERS,
        authoritative_module="daily_recovery_eligibility_projection",
        authoritative_functions=("current_market_universe_breadth_foundation (consumer)",),
        notes="Inherently market-wide, not per-ticker; no per-ticker evaluate_* wrapper is provided here.",
    ),
    CURRENT_SESSION_VOLUME: _entry(
        description="Whether a ticker's target-session volume observation is a genuine, correctly-attributed provider-native value.",
        required_dimensions=("provider", "field_identity", "field_representation", "session"),
        fitness_tiers=("READY", "UNAVAILABLE", "PARTIAL", "BLOCKED"),
        authoritative_module="market_wide_relative_volume_research",
        authoritative_functions=("resolve_records_with_recovery", "build_artifact"),
        notes="Every row (current AND historical) is independently re-verified provider=='DNSE' before being trusted -- a defense-in-depth check, not just a caller contract.",
    ),
    RELATIVE_VOLUME: _entry(
        description="Whether a ticker has both a usable current-session volume AND a compatible 20-session same-provider baseline for a dimensionless acceleration/percentile comparison.",
        required_dimensions=("provider", "field_identity", "field_representation", "session", "historical_series_identity", "target_close_compatibility"),
        fitness_tiers=("READY", "PARTIAL", "UNAVAILABLE", "BLOCKED"),
        authoritative_module="market_wide_relative_volume_research",
        authoritative_functions=("resolve_records_with_recovery", "build_artifact"),
        known_blockers=("UNAVAILABLE_INSUFFICIENT_HISTORY", "UNAVAILABLE_ZERO_BASELINE", "CURRENT_VOLUME_UNAVAILABLE", "PROVIDER_MISMATCH", "REPRESENTATION_MISMATCH"),
        notes=(
            "A CURRENT_SESSION_PRICE=RESOLVED_SINGLE_SOURCE_RESEARCH verdict from a non-DNSE source "
            "(e.g. a KBS-only degraded day) does NOT imply RELATIVE_VOLUME fitness -- this is the "
            "exact confusion Section 9 of the owner directive warns against. The two families are "
            "governed by different authorities and must never be inferred from one another."
        ),
    ),
    TECHNICAL_CLOSE_HISTORY: _entry(
        description="Whether a ticker's retained close series (possibly an extended-lookback recovery) is safe to use for any close-based technical/tactical feature.",
        required_dimensions=("session", "historical_series_identity", "current_session_observation_identity", "target_close_compatibility", "provider"),
        fitness_tiers=("RETAINED_TECHNICAL_HISTORY_RECOVERY", "RECOVERY_REJECTED_TARGET_SESSION_CLOSE_MISMATCH", "P3F9B_EXACT_SESSION_RECORD"),
        authoritative_module="technical_structure_context",
        authoritative_functions=("resolve_target_session_observations", "_recovery_overrides"),
        notes="The recovery series is adopted ONLY when its own target-session close matches the resolved exact-session snapshot's close exactly; any mismatch falls back to the pre-recovery P3F9B-only series. Shared verbatim by structure, momentum, and relative-volume/participation so this invariant cannot diverge per consumer.",
    ),
    TECHNICAL_VOLUME_HISTORY: _entry(
        description="Whether a ticker's retained volume series across the technical lookback window is provider-consistent (never a current-KBS/historical-DNSE mix).",
        required_dimensions=("provider", "session", "historical_series_identity", "field_identity"),
        fitness_tiers=("READY", "UNAVAILABLE", "BLOCKED"),
        authoritative_module="market_wide_relative_volume_research",
        authoritative_functions=("resolve_records_with_recovery",),
        notes="Same authority and same target-close-agreement guard as TECHNICAL_CLOSE_HISTORY; every row is independently re-verified DNSE-native regardless of which branch supplied it.",
    ),
    OHLC_GEOMETRY: _entry(
        description="Whether high/low/open are usable for wick-based, true-range, or gap-geometry features.",
        required_dimensions=("price_basis", "provider", "historical_series_identity"),
        fitness_tiers=("BLOCKED",),
        authoritative_module="technical_structure_context",
        authoritative_functions=("HIGH_LOW_BLOCKED_FEATURES",),
        known_blockers=("HIGH_LOW_BASIS_NOT_COMPATIBLE",),
        notes="Standing BLOCKED: the retained high/low basis is ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED with no wick-geometry compatibility proof (TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3, unchanged since). FVG/Order Block/liquidity-sweep remain DEFERRED_INPUT_BASIS_NOT_QUALIFIED for this reason.",
    ),
    VALUATION_PRICE: _entry(
        description="Whether the current-session price is currency/scale-known enough to enter any valuation ratio.",
        required_dimensions=("currency", "scale", "price_representation_contract_id", "basis_status"),
        fitness_tiers=(monetary_basis_contract.QUALIFIED, monetary_basis_contract.RESEARCH_CONTRACT_QUALIFIED, monetary_basis_contract.UNKNOWN),
        authoritative_module="monetary_basis_contract",
        authoritative_functions=("build_basis", "compatible", "known"),
    ),
    MARKET_CAP: _entry(
        description="Market capitalization fitness for use as a valuation denominator.",
        required_dimensions=("currency", "scale", "share_basis", "freshness"),
        fitness_tiers=("ready", "blocked"),
        authoritative_module="market_wide_calculation_readiness",
        authoritative_functions=("evaluate_ticker",),
        notes="provider_reported status only -- price basis is not independently verified market-wide; never silently promoted to qualified.",
    ),
    P_E: _entry(
        description="Price/Earnings ratio fitness -- requires MARKET_CAP and TTM/period earnings on a compatible monetary basis and non-meaningless (positive) denominator.",
        required_dimensions=("currency", "scale", "period", "share_basis", "monetary_basis_status"),
        fitness_tiers=("ready", "research_usable", "blocked"),
        authoritative_module="current_research_valuation_context",
        authoritative_functions=("evaluate_ticker_valuation",),
        known_blockers=("PE_NOT_MEANINGFUL", "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE"),
    ),
    P_B: _entry(
        description="Price/Book ratio fitness -- requires MARKET_CAP and a compatible book-equity figure.",
        required_dimensions=("currency", "scale", "period", "share_basis"),
        fitness_tiers=("ready", "research_usable", "blocked"),
        authoritative_module="current_research_valuation_context",
        authoritative_functions=("evaluate_ticker_valuation",),
    ),
    P_S: _entry(
        description="Price/Sales ratio fitness -- requires MARKET_CAP and compatible TTM/period revenue.",
        required_dimensions=("currency", "scale", "period", "share_basis", "monetary_basis_status"),
        fitness_tiers=("ready", "research_usable", "blocked"),
        authoritative_module="current_research_valuation_context",
        authoritative_functions=("evaluate_ticker_valuation",),
        known_blockers=("TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE",),
    ),
    EV_EBITDA: _entry(
        description="Enterprise Value / EBITDA fitness -- corporate-only, requires MARKET_CAP, debt, cash, and a positive EBITDA denominator.",
        required_dimensions=("currency", "scale", "period", "entity_class_applicability"),
        fitness_tiers=("ready", "blocked", "not_applicable"),
        authoritative_module="market_wide_calculation_readiness",
        authoritative_functions=("evaluate_ev_ebitda",),
        known_blockers=("negative_or_zero_ebitda_denominator", "EXACT_EBITDA_COMPARABILITY_NOT_RETAINED"),
        notes="financial_entity_applicability.CORPORATE_ONLY_METRICS=('ebitda','ev_ebitda') makes bank/securities/insurance/finance_company issuers NOT_APPLICABLE, never blocked-by-evidence.",
    ),
    FUNDAMENTAL_RATIO: _entry(
        description="Generic financial-statement ratio fitness (margins, ROE/ROA, leverage, liquidity) -- entity-class-gated and same-provider/same-period-gated.",
        required_dimensions=("provider", "period", "entity_class_applicability", "same_provider_pair"),
        fitness_tiers=("READY", "RESEARCH_PROXY", "BLOCKED_BY_EVIDENCE", "NOT_APPLICABLE"),
        authoritative_module="financial_analysis_engine_v2",
        authoritative_functions=("build_ticker_context", "build_artifact"),
    ),
    TACTICAL_STRUCTURE: _entry(
        description="Swing/BOS/CHoCH/breakout structure fitness -- close-only, requires the same target-session-close-compatible history as TECHNICAL_CLOSE_HISTORY.",
        required_dimensions=("historical_series_identity", "target_close_compatibility", "session"),
        fitness_tiers=("STRUCTURE_READY", "INSUFFICIENT_HISTORY"),
        authoritative_module="technical_structure_context",
        authoritative_functions=("resolve_target_session_observations", "build_artifact"),
    ),
    MOMENTUM: _entry(
        description="RSI/MA/MACD/divergence fitness -- close-only, requires the identical history authority as TACTICAL_STRUCTURE (shared function, not a diverging copy).",
        required_dimensions=("historical_series_identity", "target_close_compatibility", "session"),
        fitness_tiers=("ELIGIBLE", "NOT_ELIGIBLE"),
        authoritative_module="tactical_momentum_context",
        authoritative_functions=("build_artifact",),
    ),
    PARTICIPATION: _entry(
        description="Volume-based confirmation input for tactical_confirmation_context -- same authority and guard as RELATIVE_VOLUME.",
        required_dimensions=("provider", "field_identity", "session", "historical_series_identity", "target_close_compatibility"),
        fitness_tiers=("READY", "INSUFFICIENT_EVIDENCE"),
        authoritative_module="market_wide_relative_volume_research",
        authoritative_functions=("resolve_records_with_recovery", "build_artifact"),
        notes="tactical_confirmation_context.participation_state() only ever reads acceleration_status=='READY'; every other RELATIVE_VOLUME status becomes INSUFFICIENT_EVIDENCE for this family, never a fabricated neutral reading.",
    ),
    EXECUTION_LIQUIDITY: _entry(
        description="Position-sizing/execution-capacity fitness.",
        required_dimensions=("adv_window_completeness", "matched_traded_value_authority"),
        fitness_tiers=("BLOCKED",),
        authoritative_module="docs/ROADMAP_STATE.json#blocked_capabilities",
        authoritative_functions=(),
        known_blockers=("QUALIFIED_LIQUIDITY_INPUTS=NO", "POSITION_SIZING_IS_SAFE=NO"),
        notes="Standing market-wide block; not a per-ticker computation. See _STANDING_BLOCKED_FAMILIES.",
    ),
}


def describe(family: str) -> dict[str, Any]:
    """Return one family's registry entry. Fails closed on an unknown family name."""
    if family not in FAMILY_REGISTRY:
        raise FeatureInputFitnessError(f"UNKNOWN_USE_CASE_FAMILY:{family}")
    return dict(FAMILY_REGISTRY[family])


def evaluate_current_session_price(ticker: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Delegate to the real CURRENT_SESSION_PRICE authority. Never re-derives its policy."""
    return multi_source_market_evidence_contract.resolve_ticker(ticker, observations)


def evaluate_technical_close_history(
    *, pf_record: Mapping[str, Any] | None, recovery_override: Mapping[str, Any] | None, target_session: str,
) -> dict[str, Any]:
    """Delegate to the shared TECHNICAL_CLOSE_HISTORY / TACTICAL_STRUCTURE / MOMENTUM authority.

    Returns ``{"winning_record": ..., "source": ...}`` -- ``source`` is one of
    ``RETAINED_TECHNICAL_HISTORY_RECOVERY`` (fit for use), ``P3F9B_EXACT_SESSION_RECORD`` (fit for
    use, just not recovery-extended), or ``RECOVERY_REJECTED_TARGET_SESSION_CLOSE_MISMATCH`` (the
    recovery series was rejected; the plain snapshot record is returned instead, which may itself
    still be too shallow for a given feature's own minimum-history requirement)."""
    winning_record, source = technical_structure_context.resolve_target_session_observations(
        pf_record=pf_record, recovery_override=recovery_override, target_session=target_session,
    )
    return {"winning_record": winning_record, "source": source}


def evaluate_valuation_monetary_basis(
    basis_a: Mapping[str, Any] | None, basis_b: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Delegate to the real VALUATION_PRICE/MARKET_CAP/P_E/P_B/P_S/EV_EBITDA monetary-compatibility
    authority. Returns ``{"compatible": bool, "reason": str | None}``."""
    compatible, reason = monetary_basis_contract.compatible(basis_a, basis_b)
    return {"compatible": compatible, "reason": reason}


def evaluate_entity_class_applicability(archetype: Mapping[str, Any], metric: str) -> dict[str, Any]:
    """Delegate to the real entity-class applicability authority for a corporate-only metric
    (e.g. EV_EBITDA). Never widens NOT_APPLICABLE to APPLICABLE by inference."""
    return financial_entity_applicability.metric_applicability(archetype, metric)


def is_standing_blocked(family: str) -> tuple[bool, str | None]:
    """True, reason for a family this repository blocks market-wide today regardless of
    per-ticker evidence (see :data:`_STANDING_BLOCKED_FAMILIES`)."""
    if family not in FAMILY_REGISTRY:
        raise FeatureInputFitnessError(f"UNKNOWN_USE_CASE_FAMILY:{family}")
    reason = _STANDING_BLOCKED_FAMILIES.get(family)
    return reason is not None, reason


def snapshot() -> dict[str, Any]:
    """The full registry, for the operations-review feature_input_fitness_matrix.json artifact."""
    return {
        "contract_version": CONTRACT_VERSION,
        "use_case_families": list(USE_CASE_FAMILIES),
        "registry": {family: FAMILY_REGISTRY[family] for family in USE_CASE_FAMILIES},
        "standing_blocked_families": dict(_STANDING_BLOCKED_FAMILIES),
        "authority_effect": "NONE",
    }
