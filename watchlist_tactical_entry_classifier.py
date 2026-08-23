"""Watchlist tactical entry-state classifier (WATCHLIST_TACTICAL_ENTRY_DECISION_V1).

Turns already-computed current market-wide descriptive/screening/fundamental research into a
deterministic tactical entry-state classification per ticker, suitable for watchlist review before
the next trading session. This module computes no new technical indicator, ranking, feature store,
or evidence: every input value it reads was already computed by
``market_wide_current_descriptive_research.py`` (technical features, trend state, breadth/regime
descriptors, descriptive liquidity), ``current_market_screening_opportunity_comparison_foundation.py``
(market-relative and sector-relative momentum/volume percentile context), and
``market_wide_current_fundamental_research.py`` (official/provider fundamental-research tier). The
one threshold this module reuses rather than invents is ``price_structure_breakout_context.NEAR``
(2%), applied here only to a close-vs-MA20 proximity test -- the same "near" convention already
established for this project's other close-only descriptive price context.

Two output layers per ticker:
  * ``ticker_structure_state`` -- the ticker's own raw trend/momentum posture (five values),
    derived only from ``trend_state`` and ``momentum_20d``'s sign plus the close-vs-MA20 proximity
    test.
  * ``entry_state`` -- the refined nine-state tactical classification (the required entry
    taxonomy), which additionally folds in market-relative momentum quartile, sector-relative
    momentum quartile, today's session return, provider-relative-volume confirmation, and
    cross-sectional (contemporaneous, not historical) volatility regime. ``EARLY_REVERSAL_CANDIDATE``
    additionally requires at least one independent confirming signal (market-relative momentum,
    sector-relative momentum, or today's return+volume) beyond the bare momentum-sign flip, and
    ``BASE_BUILDING`` additionally requires no bottom-quartile relative momentum and no
    confirmed-down session today, so low volatility alone on an otherwise unconfirmed weak trend no
    longer qualifies for either state (2026-08-23 closeout correction).

Two separate action fields, deliberately not conflated (2026-08-23 closeout correction):
  * ``entry_action`` -- the PRIMARY field, answering "should a reader who may or may not currently
    hold this ticker open new exposure today." A fixed nine-to-five lookup from ``entry_state``
    (``ENTRY_ACTION_BY_ENTRY_STATE``): ``EARLY_ENTRY``, ``BUY_ON_CONFIRMATION``,
    ``ACCUMULATE_IN_BASE``, ``WAIT``, or ``AVOID`` -- never ``HOLD_DO_NOT_ADD`` or ``REDUCE_EXIT``,
    which presuppose an existing position. This pipeline has no holdings/portfolio input anywhere,
    so those two values would be meaningless as an answer to "should I enter."
  * ``action`` -- a SECONDARY, position-management-conditional field (unchanged nine-to-seven
    lookup, ``ACTION_BY_ENTRY_STATE``): only meaningful if the reader already holds this ticker.
    Never use it to decide whether to enter a ticker with unknown or zero holdings.

``is_full_position_ready`` is unconditionally ``False`` for every record, and
``position_sizing_status`` is unconditionally ``"NOT_EVALUATED"``: position sizing is not
implemented anywhere in this pipeline (see ``blocked_outputs.portfolio_weights_or_position_sizes``
== ``SIZING_FORMULA_NOT_YET_IMPLEMENTED``), so this classifier never claims any ticker, under any
condition, is ready for a full-size position.

No ranking, score, probability, target price, portfolio-sizing formula, RAW_AS_TRADED/PIT claim,
or backtest output is produced anywhere in this module.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

import market_wide_current_descriptive_research as descriptive_module
import current_market_screening_opportunity_comparison_foundation as screening_module
import market_wide_current_fundamental_research as fundamental_module
from price_structure_breakout_context import NEAR as _NEAR_MA20_THRESHOLD

CONTRACT_VERSION = "watchlist_tactical_entry_classifier/v1"
MILESTONE = "WATCHLIST_TACTICAL_ENTRY_DECISION_V1"

STRUCTURE_STATES = (
    "ABOVE_MA20_MOMENTUM_POSITIVE",
    "ABOVE_MA20_MOMENTUM_NEGATIVE",
    "BELOW_MA20_MOMENTUM_POSITIVE",
    "BELOW_MA20_MOMENTUM_NEGATIVE",
    "NEAR_MA20_NEUTRAL",
    "NOT_AVAILABLE",
)

ENTRY_STATES = (
    "DOWNTREND",
    "SELLING_PRESSURE_EASING",
    "EARLY_REVERSAL_CANDIDATE",
    "BASE_BUILDING",
    "SIDEWAYS_NEUTRAL",
    "BREAKOUT_READY",
    "UPTREND_CONFIRMED",
    "DISTRIBUTION_RISK",
    "BREAKDOWN_RISK",
)

ACTIONS = (
    "EARLY_ENTRY",
    "BUY_ON_CONFIRMATION",
    "ACCUMULATE_IN_BASE",
    "HOLD_DO_NOT_ADD",
    "WAIT",
    "AVOID",
    "REDUCE_EXIT",
)

# Fixed nine-to-seven lookup, never a recomputed score. SECONDARY, position-management-conditional
# field -- HOLD_DO_NOT_ADD and REDUCE_EXIT are only meaningful if the reader already holds this
# ticker, which this classifier has no way to know (no holdings/portfolio input exists anywhere in
# this pipeline). Never use `action` to decide whether to enter a ticker with unknown or zero
# holdings; use `entry_action` (ENTRY_ACTION_BY_ENTRY_STATE below) for that question instead.
# EARLY_ENTRY is reserved for EARLY_REVERSAL_CANDIDATE only (deterministic evidence of an early
# reversal), matching this milestone's explicit instruction that EARLY_ENTRY must not require a
# confirmed uptrend and must never imply a full-size position (is_full_position_ready is
# unconditionally False for every state; see module docstring).
ACTION_BY_ENTRY_STATE = {
    "BREAKOUT_READY": "BUY_ON_CONFIRMATION",
    "UPTREND_CONFIRMED": "HOLD_DO_NOT_ADD",
    "EARLY_REVERSAL_CANDIDATE": "EARLY_ENTRY",
    "BASE_BUILDING": "ACCUMULATE_IN_BASE",
    "SELLING_PRESSURE_EASING": "WAIT",
    "SIDEWAYS_NEUTRAL": "WAIT",
    "DISTRIBUTION_RISK": "HOLD_DO_NOT_ADD",
    "BREAKDOWN_RISK": "REDUCE_EXIT",
    "DOWNTREND": "AVOID",
}

# PRIMARY field for "should I enter" -- fixed nine-to-five lookup, never HOLD_DO_NOT_ADD or
# REDUCE_EXIT (see ACTION_BY_ENTRY_STATE's docstring on why those two are excluded here). WAIT
# groups every state where fresh entry is not tactically supported by the evidence but the picture
# is not outright bearish either (including UPTREND_CONFIRMED -- already running, with no fresh
# low-risk entry trigger today, is a "wait for the next setup" read for a flat reader, not a signal
# to chase); AVOID groups the two outright-bearish states.
ENTRY_ACTIONS = (
    "EARLY_ENTRY",
    "BUY_ON_CONFIRMATION",
    "ACCUMULATE_IN_BASE",
    "WAIT",
    "AVOID",
)
ENTRY_ACTION_BY_ENTRY_STATE = {
    "BREAKOUT_READY": "BUY_ON_CONFIRMATION",
    "EARLY_REVERSAL_CANDIDATE": "EARLY_ENTRY",
    "BASE_BUILDING": "ACCUMULATE_IN_BASE",
    "UPTREND_CONFIRMED": "WAIT",
    "DISTRIBUTION_RISK": "WAIT",
    "SELLING_PRESSURE_EASING": "WAIT",
    "SIDEWAYS_NEUTRAL": "WAIT",
    "BREAKDOWN_RISK": "AVOID",
    "DOWNTREND": "AVOID",
}

POSITION_SIZING_STATUS = "NOT_EVALUATED"

HORIZON_STATES = ("NEXT_SESSION_WATCH", "SHORT_TERM_FEW_SESSIONS", "MULTI_WEEK_SWING")
HORIZON_BY_ENTRY_STATE = {
    "BREAKOUT_READY": "NEXT_SESSION_WATCH",
    "BREAKDOWN_RISK": "NEXT_SESSION_WATCH",
    "EARLY_REVERSAL_CANDIDATE": "SHORT_TERM_FEW_SESSIONS",
    "SELLING_PRESSURE_EASING": "SHORT_TERM_FEW_SESSIONS",
    "DISTRIBUTION_RISK": "SHORT_TERM_FEW_SESSIONS",
    "BASE_BUILDING": "MULTI_WEEK_SWING",
    "UPTREND_CONFIRMED": "MULTI_WEEK_SWING",
    "DOWNTREND": "MULTI_WEEK_SWING",
    "SIDEWAYS_NEUTRAL": "MULTI_WEEK_SWING",
}
# Missing/blocked fundamental authority limits (never widens) the reported horizon -- one step
# toward the shortest, most-verifiable-soonest tier -- rather than forcing WAIT.
_HORIZON_DOWNGRADE = {
    "MULTI_WEEK_SWING": "SHORT_TERM_FEW_SESSIONS",
    "SHORT_TERM_FEW_SESSIONS": "NEXT_SESSION_WATCH",
    "NEXT_SESSION_WATCH": "NEXT_SESSION_WATCH",
}

RULE_DEFINITIONS = {
    "R0_TECHNICAL_FEATURES_UNAVAILABLE": (
        "Same-session technical features (close/MA20/momentum) are unavailable; no classification is computed."
    ),
    "R1_NEAR_MA20_MID_PACK_MOMENTUM": (
        "Close is within 2% of the 20-day moving average and 20-day momentum is not a same-session "
        "market-cohort quartile extreme."
    ),
    "R2_BREAKOUT_READY_CONFIRMED": (
        "Price above the 20-day moving average, 20-day momentum positive and in the top same-session "
        "market quartile, today's provider-relative volume above the cohort median, today's return "
        "positive, and 20-day volatility below the same-session market median."
    ),
    "R3_UPTREND_CONFIRMED_DEFAULT": (
        "Price above the 20-day moving average and 20-day momentum positive (default bullish case, "
        "not meeting the stricter breakout-confirmation bar of R2)."
    ),
    "R4_DISTRIBUTION_RISK": (
        "Price still above the 20-day moving average but 20-day momentum has turned negative."
    ),
    "R5_BREAKDOWN_RISK": (
        "Price at or below the 20-day moving average, 20-day momentum in the bottom same-session "
        "market quartile, today's provider-relative volume above the cohort median, and today's "
        "return negative."
    ),
    "R6_EARLY_REVERSAL_CANDIDATE": (
        "Price at or below the 20-day moving average but 20-day momentum has turned positive -- "
        "momentum inflecting before price structure confirms -- AND at least one independent "
        "confirming signal: same-session market-relative momentum in the upper half of the market "
        "cohort, same-session sector-relative momentum in the upper half of its own sector cohort, "
        "or today's return positive together with today's provider-relative volume above the "
        "cohort median."
    ),
    "R6B_EARLY_REVERSAL_UNCONFIRMED_NEUTRAL": (
        "Price at or below the 20-day moving average with 20-day momentum positive, but none of "
        "R6's independent confirming signals is present -- an unconfirmed momentum tick rather "
        "than a distinguishable early-reversal candidate, reported as neutral rather than as a "
        "reversal signal the evidence does not yet support."
    ),
    "R7_BASE_BUILDING": (
        "Price at or below the 20-day moving average, 20-day momentum negative, 20-day volatility "
        "below the same-session market median, today's provider-relative volume not above the "
        "cohort median, today's return not negative, and 20-day momentum not ranked in the bottom "
        "same-session market quartile -- a quiet, unforced, non-deteriorating consolidation, not "
        "merely low volatility sitting on top of an otherwise unconfirmed weak or "
        "breakdown-flavored trend."
    ),
    "R8_SELLING_PRESSURE_EASING": (
        "Price at or below the 20-day moving average, 20-day momentum negative, but momentum ranks "
        "in the top half of the same-session market cohort or today's return is positive."
    ),
    "R9_DOWNTREND_DEFAULT": (
        "Price at or below the 20-day moving average and 20-day momentum negative (default bearish "
        "case; none of R5/R7/R8's easing, base, or breakdown conditions were met)."
    ),
}


class WatchlistTacticalEntryClassifierError(ValueError):
    """A retained input or an invariant of this contract is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    """Recompute this artifact's content hash from its own bytes, excluding the identity fields
    it carries itself -- same convention as every sibling market_wide_current_* module, so
    export_ai_bundle.py can verify a retained artifact reproduces its own recorded artifact_sha256
    before attaching any of its records to a bundle."""
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = _hash(payload)
    return {"artifact_sha256": digest, "artifact_identity": f"watchlist_tactical_entry_classifier:{digest}"}


def _verify_descriptive_identity(source: Mapping[str, Any]) -> None:
    identity = descriptive_module.content_identity(source)
    if source.get("artifact_sha256") != identity["artifact_sha256"]:
        raise WatchlistTacticalEntryClassifierError("DESCRIPTIVE_SOURCE_IDENTITY_MISMATCH")


def _verify_screening_identity(source: Mapping[str, Any]) -> None:
    identity = screening_module.content_identity(source)
    if source.get("artifact_sha256") != identity["artifact_sha256"]:
        raise WatchlistTacticalEntryClassifierError("SCREENING_SOURCE_IDENTITY_MISMATCH")


def _verify_fundamental_identity(source: Mapping[str, Any]) -> None:
    identity = fundamental_module.content_identity(source)
    if source.get("artifact_sha256") != identity["artifact_sha256"]:
        raise WatchlistTacticalEntryClassifierError("FUNDAMENTAL_SOURCE_IDENTITY_MISMATCH")


def _market_state(market_breadth: Mapping[str, Any], *, session: str | None) -> dict[str, Any]:
    """Contemporaneous breadth/regime context only -- never a bull/bear call, forecast, or timing
    model (same boundary already carried by market_regime_breadth_context.py /
    market_wide_current_descriptive_research.py's own market_breadth block, reused verbatim
    here, not recomputed)."""
    breadth_descriptor = market_breadth.get("breadth_descriptor", {}).get("descriptor")
    momentum_descriptor = market_breadth.get("momentum_descriptor", {}).get("descriptor")
    if breadth_descriptor == "MARKET_BREADTH_POSITIVE" and momentum_descriptor == "MOMENTUM_BREADTH_POSITIVE":
        state = "RISK_ON_BROAD_PARTICIPATION"
    elif breadth_descriptor == "MARKET_BREADTH_NEGATIVE" and momentum_descriptor == "MOMENTUM_BREADTH_NEGATIVE":
        state = "RISK_OFF_BROAD_WEAKNESS"
    else:
        state = "MIXED_NO_CLEAR_MARKET_REGIME"
    return {
        "market_state": state,
        "session": session,
        "breadth_descriptor": breadth_descriptor,
        "momentum_descriptor": momentum_descriptor,
        "advance_ratio": market_breadth.get("advance_ratio"),
        "quality_state": market_breadth.get("quality_state"),
        "volatility_median": market_breadth.get("volatility", {}).get("median"),
        "authority": "CONTEMPORANEOUS_EMPIRICAL_COHORT_NOT_A_FORECAST_OR_TIMING_MODEL",
    }


def _entry_state_rule(
    *, near_ma20: bool, above_ma20: bool, momentum_positive: bool, momentum_bucket: str | None,
    today_positive: bool | None, elevated_volume: bool | None, volatility_regime: str,
    sector_momentum_bucket: str | None,
) -> tuple[str, str]:
    """The complete, gapless, ordered (first-match-wins) nine-state decision table. Every branch
    uses only already-computed inputs; see RULE_DEFINITIONS for the plain-English predicate each
    rule id names."""
    if near_ma20 and momentum_bucket in (None, "UPPER_MIDDLE", "LOWER_MIDDLE"):
        return "R1_NEAR_MA20_MID_PACK_MOMENTUM", "SIDEWAYS_NEUTRAL"
    if above_ma20 and momentum_positive:
        if (
            momentum_bucket == "UPPER_QUARTILE" and elevated_volume is True
            and today_positive is True and volatility_regime == "BELOW_MARKET_MEDIAN"
        ):
            return "R2_BREAKOUT_READY_CONFIRMED", "BREAKOUT_READY"
        return "R3_UPTREND_CONFIRMED_DEFAULT", "UPTREND_CONFIRMED"
    if above_ma20 and not momentum_positive:
        return "R4_DISTRIBUTION_RISK", "DISTRIBUTION_RISK"
    if (not above_ma20) and momentum_positive:
        # Tightened 2026-08-23 closeout: a bare momentum-sign flip is not enough on its own: at
        # least one independent confirming signal (market-relative momentum, sector-relative
        # momentum, or today's return+volume) must corroborate it before this is reported as a
        # reversal candidate rather than merely neutral.
        reversal_confirmed = (
            momentum_bucket in ("UPPER_QUARTILE", "UPPER_MIDDLE")
            or sector_momentum_bucket in ("UPPER_QUARTILE", "UPPER_MIDDLE")
            or (today_positive is True and elevated_volume is True)
        )
        if reversal_confirmed:
            return "R6_EARLY_REVERSAL_CANDIDATE", "EARLY_REVERSAL_CANDIDATE"
        return "R6B_EARLY_REVERSAL_UNCONFIRMED_NEUTRAL", "SIDEWAYS_NEUTRAL"
    # Remaining quadrant: not above_ma20 and not momentum_positive.
    if momentum_bucket == "LOWER_QUARTILE" and elevated_volume is True and today_positive is False:
        return "R5_BREAKDOWN_RISK", "BREAKDOWN_RISK"
    # Tightened 2026-08-23 closeout: low volatility alone is not enough -- also require no
    # breakdown evidence (momentum not bottom-quartile relative to the market) and no active
    # stabilization failure (today's return not negative), so a persistent weak/downtrend that
    # merely happens to be quiet today no longer qualifies as a base.
    if (
        volatility_regime == "BELOW_MARKET_MEDIAN" and elevated_volume is not True
        and momentum_bucket != "LOWER_QUARTILE" and today_positive is not False
    ):
        return "R7_BASE_BUILDING", "BASE_BUILDING"
    if momentum_bucket in ("UPPER_QUARTILE", "UPPER_MIDDLE") or today_positive is True:
        return "R8_SELLING_PRESSURE_EASING", "SELLING_PRESSURE_EASING"
    return "R9_DOWNTREND_DEFAULT", "DOWNTREND"


_CONFIRMATION_TRIGGER_BY_STATE = {
    "BREAKOUT_READY": (
        "Already showing today's price, momentum, and volume confirmation; the remaining trigger is "
        "whether the next session extends the move on continued above-median relative volume."
    ),
    "UPTREND_CONFIRMED": (
        "The trend is already confirmed; the ongoing trigger is simply continued price above the "
        "20-day moving average with 20-day momentum staying positive."
    ),
    "EARLY_REVERSAL_CANDIDATE": (
        "A reclaim of the 20-day moving average alongside continued positive 20-day momentum would "
        "confirm this as a full reversal, not merely an early candidate."
    ),
    "BASE_BUILDING": (
        "A 20-day momentum flip to positive, or a provider-relative-volume-backed move back above "
        "the 20-day moving average, would confirm the base is resolving higher."
    ),
    "SELLING_PRESSURE_EASING": (
        "20-day momentum turning positive, or price reclaiming the 20-day moving average, would "
        "upgrade this to an early reversal candidate."
    ),
    "SIDEWAYS_NEUTRAL": (
        "A decisive move away from the 20-day moving average combined with a same-session momentum "
        "quartile extreme (top or bottom) would resolve the current lack of a directional edge."
    ),
    "DISTRIBUTION_RISK": (
        "A session close below the 20-day moving average would confirm the momentum rollover already "
        "visible in the 20-day reading."
    ),
    "BREAKDOWN_RISK": (
        "Already showing a provider-relative-volume-confirmed down session below the 20-day moving "
        "average; the remaining trigger is whether the next session continues the break."
    ),
    "DOWNTREND": (
        "A 20-day momentum flip to positive (even before price reclaims the 20-day moving average) "
        "would be the first deterministic sign of stabilization."
    ),
}

_INVALIDATION_BY_STATE = {
    "BREAKOUT_READY": (
        "A session close back below the 20-day moving average, or 20-day momentum turning negative, "
        "invalidates the breakout-ready classification."
    ),
    "UPTREND_CONFIRMED": (
        "20-day momentum turning negative while price is still above the 20-day moving average "
        "invalidates this classification (see DISTRIBUTION_RISK)."
    ),
    "EARLY_REVERSAL_CANDIDATE": (
        "20-day momentum turning negative again invalidates the reversal signal -- a stricter, "
        "faster invalidation than a confirmed-trend state carries, matching this state's early, "
        "pre-confirmation evidence."
    ),
    "BASE_BUILDING": (
        "A provider-relative-volume-confirmed down session, or 20-day momentum dropping into the "
        "bottom same-session market quartile, invalidates the base and points toward a downtrend."
    ),
    "SELLING_PRESSURE_EASING": (
        "A renewed drop to bottom-quartile same-session relative momentum together with an "
        "elevated-volume down session invalidates the easing read."
    ),
    "SIDEWAYS_NEUTRAL": (
        "A move to a same-session momentum quartile extreme (top or bottom) combined with price "
        "moving decisively away from the 20-day moving average would invalidate the neutral read."
    ),
    "DISTRIBUTION_RISK": (
        "A recovery of 20-day momentum back to positive while price remains above the 20-day moving "
        "average invalidates the distribution warning (see UPTREND_CONFIRMED)."
    ),
    "BREAKDOWN_RISK": (
        "A session close reclaiming the 20-day moving average invalidates the active-breakdown "
        "classification."
    ),
    "DOWNTREND": (
        "A 20-day momentum flip to positive invalidates the downtrend classification (see "
        "EARLY_REVERSAL_CANDIDATE); this state itself carries no bullish thesis to invalidate."
    ),
}


def _bucket_direction(bucket: str | None) -> str | None:
    if bucket in ("UPPER_QUARTILE", "UPPER_MIDDLE"):
        return "for"
    if bucket in ("LOWER_QUARTILE", "LOWER_MIDDLE"):
        return "against"
    return None


def _evidence(
    *, above_ma20: bool, momentum: float, momentum_positive: bool, momentum_bucket: str | None,
    return_1d: float | None, today_positive: bool | None, elevated_volume: bool | None,
    volatility_regime: str, sector_comparison: Mapping[str, Any] | None, liquidity_status: str,
    market_state: str, fundamental_tier: str | None, fundamental_readiness: str | None,
    fundamental_status: str,
) -> tuple[list[str], list[str]]:
    """Deterministic string templates over already-computed values only -- never free-form
    generation, never a fabricated number."""
    for_lines: list[str] = []
    against_lines: list[str] = []

    if above_ma20:
        for_lines.append("Price is above its 20-day moving average.")
    else:
        against_lines.append("Price is at or below its 20-day moving average.")

    if momentum_positive:
        for_lines.append(f"20-day momentum is positive ({momentum:.4f}).")
    else:
        against_lines.append(f"20-day momentum is negative ({momentum:.4f}).")

    bucket_direction = _bucket_direction(momentum_bucket)
    if bucket_direction == "for":
        for_lines.append(f"20-day momentum ranks in the {momentum_bucket} of the same-session market cohort.")
    elif bucket_direction == "against":
        against_lines.append(f"20-day momentum ranks in the {momentum_bucket} of the same-session market cohort.")

    if today_positive is True:
        for_lines.append(f"Today's session return is positive ({return_1d:.4f}).")
    elif today_positive is False:
        against_lines.append(f"Today's session return is negative ({return_1d:.4f}).")

    if elevated_volume is True:
        for_lines.append(
            "Provider-relative volume is above the same-session cohort median today "
            "(a descriptive proxy, not liquidity or turnover authority)."
        )
    elif elevated_volume is False:
        against_lines.append("Provider-relative volume is at or below the same-session cohort median today.")

    if volatility_regime == "BELOW_MARKET_MEDIAN":
        for_lines.append(
            "20-day volatility is below the same-session market median "
            "(contemporaneous cross-section only, not a historical compression regime)."
        )
    elif volatility_regime == "AT_OR_ABOVE_MARKET_MEDIAN":
        against_lines.append("20-day volatility is at or above the same-session market median.")

    if isinstance(sector_comparison, Mapping) and sector_comparison.get("status") == "AVAILABLE":
        sector_bucket_direction = _bucket_direction(sector_comparison.get("momentum_bucket"))
        bucket = sector_comparison.get("momentum_bucket")
        if sector_bucket_direction == "for":
            for_lines.append(f"20-day momentum ranks in the {bucket} of its own same-session sector cohort.")
        elif sector_bucket_direction == "against":
            against_lines.append(f"20-day momentum ranks in the {bucket} of its own same-session sector cohort.")

    if liquidity_status == "ELIGIBLE":
        for_lines.append("Current-session descriptive liquidity is eligible (board-composition reading available).")
    else:
        against_lines.append("Current-session descriptive liquidity is unavailable for this ticker.")

    if fundamental_status == "NOT_IN_FUNDAMENTAL_COHORT":
        against_lines.append("Ticker is outside the retained fundamental-research cohort.")
    elif fundamental_tier == "BLOCKED":
        against_lines.append("No official or provider fundamental evidence is retained for this ticker.")
    elif fundamental_tier == "OFFICIAL_QUALIFIED" and fundamental_readiness in ("READY", "PARTIAL"):
        for_lines.append(f"Official-tier fundamental evidence is available (readiness: {fundamental_readiness}).")

    if market_state == "RISK_OFF_BROAD_WEAKNESS":
        against_lines.append("The broader market is in a contemporaneous risk-off / broad-weakness regime.")
    elif market_state == "RISK_ON_BROAD_PARTICIPATION":
        for_lines.append("The broader market is in a contemporaneous risk-on / broad-participation regime.")

    return for_lines, against_lines


def _confidence(*, liquidity_eligible: bool, fundamental_tier: str | None, sector_available: bool) -> str:
    if liquidity_eligible and fundamental_tier == "OFFICIAL_QUALIFIED" and sector_available:
        return "HIGH"
    if liquidity_eligible or fundamental_tier in ("OFFICIAL_QUALIFIED", "PROVIDER_RESEARCH"):
        return "MEDIUM"
    return "LOW"


def _horizon(entry_state: str, fundamental_tier: str | None) -> str:
    base = HORIZON_BY_ENTRY_STATE[entry_state]
    if fundamental_tier in (None, "BLOCKED"):
        return _HORIZON_DOWNGRADE[base]
    return base


def _fundamental_context(fundamental_record: Mapping[str, Any] | None) -> dict[str, Any]:
    if fundamental_record is None:
        return {
            "status": "NOT_IN_FUNDAMENTAL_COHORT",
            "authority_tier": None,
            "fundamental_research_readiness": None,
            "disposition": None,
        }
    tier = fundamental_record.get("authority_tier")
    return {
        "status": "AVAILABLE",
        "authority_tier": tier,
        "fundamental_research_readiness": fundamental_record.get("fundamental_research_readiness") if tier == "OFFICIAL_QUALIFIED" else None,
        "disposition": fundamental_record.get("disposition"),
    }


def _data_quality(
    *, technical_eligible: bool, feature_as_of_session: str | None, is_current_session: bool | None,
    liquidity_status: str, sector_status: str | None, fundamental_context: Mapping[str, Any],
    market_quality_state: str | None, confidence: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    if not technical_eligible:
        warnings.append("Same-session technical features are unavailable for this ticker; no tactical classification could be computed.")
    if liquidity_status != "ELIGIBLE":
        warnings.append("Current-session descriptive liquidity is unavailable for this ticker.")
    if sector_status not in (None, "AVAILABLE"):
        warnings.append(f"Sector-relative comparison is {sector_status}.")
    if fundamental_context.get("status") == "NOT_IN_FUNDAMENTAL_COHORT":
        warnings.append("Ticker is outside the retained fundamental-research cohort.")
    elif fundamental_context.get("authority_tier") == "BLOCKED":
        warnings.append("No fundamental evidence is retained for this ticker (BLOCKED tier).")
    elif fundamental_context.get("authority_tier") == "PROVIDER_RESEARCH":
        warnings.append("Fundamental evidence is provider-research tier only (descriptive, non-calculation-grade).")
    return {
        "confidence": confidence,
        "technical_eligible": technical_eligible,
        "feature_as_of_session": feature_as_of_session,
        "is_current_session": is_current_session,
        "liquidity_status": liquidity_status,
        "sector_relative_status": sector_status,
        "fundamental_tier": fundamental_context.get("authority_tier"),
        "market_breadth_quality_state": market_quality_state,
        "warnings": warnings,
    }


def _insufficient_data_record(
    ticker: str, descriptive_record: Mapping[str, Any], fundamental_record: Mapping[str, Any] | None,
    market_state_block: Mapping[str, Any],
) -> dict[str, Any]:
    technical = descriptive_record.get("technical_features", {}) if isinstance(descriptive_record, Mapping) else {}
    liquidity = descriptive_record.get("liquidity", {}) if isinstance(descriptive_record, Mapping) else {}
    fundamental_context = _fundamental_context(fundamental_record)
    liquidity_status = liquidity.get("status", "NOT_APPLICABLE")
    return {
        "ticker": ticker,
        "market_state": market_state_block["market_state"],
        "ticker_structure_state": "NOT_AVAILABLE",
        "entry_state": None,
        "action": "WAIT",
        "entry_action": "WAIT",
        "evidence_for": [],
        "evidence_against": ["Same-session technical features are unavailable for this ticker."],
        "confirmation_trigger": "Await same-session technical-feature availability before any tactical classification.",
        "invalidation": None,
        "data_quality": _data_quality(
            technical_eligible=False, feature_as_of_session=technical.get("feature_as_of_session"),
            is_current_session=technical.get("is_current_session"), liquidity_status=liquidity_status,
            sector_status=None, fundamental_context=fundamental_context,
            market_quality_state=market_state_block.get("quality_state"), confidence="INSUFFICIENT",
        ),
        "horizon": None,
        "is_full_position_ready": False,
        "position_sizing_status": POSITION_SIZING_STATUS,
        "fundamental_context": fundamental_context,
        "rule_id": "R0_TECHNICAL_FEATURES_UNAVAILABLE",
        "is_actionable": False,
    }


def _classify_ticker(
    ticker: str, *, descriptive_record: Mapping[str, Any], market_breadth: Mapping[str, Any],
    market_state_block: Mapping[str, Any], screening_record: Mapping[str, Any] | None,
    fundamental_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    technical = descriptive_record.get("technical_features", {})
    technical_eligible = technical.get("status") == "SHADOW_ONLY" and technical.get("is_current_session") is True
    if not technical_eligible:
        return _insufficient_data_record(ticker, descriptive_record, fundamental_record, market_state_block)

    values = technical.get("values", {})
    close, ma20 = values.get("close"), values.get("ma_20")
    momentum, return_1d, volatility = values.get("momentum_20d"), values.get("return_1d"), values.get("volatility_20d")
    if not all(isinstance(item, (int, float)) for item in (close, ma20, momentum)) or not ma20:
        return _insufficient_data_record(ticker, descriptive_record, fundamental_record, market_state_block)

    above_ma20 = descriptive_record.get("trend_state") == "ABOVE_MA20"
    momentum_positive = momentum > 0
    today_positive = (return_1d > 0) if isinstance(return_1d, (int, float)) else None
    ma20_distance_pct = (close - ma20) / ma20
    near_ma20 = abs(ma20_distance_pct) <= _NEAR_MA20_THRESHOLD

    screening_ok = (
        isinstance(screening_record, Mapping)
        and screening_record.get("market_relative_comparison", {}).get("status") == "AVAILABLE"
    )
    market_relative = screening_record.get("market_relative_comparison", {}) if screening_ok else {}
    momentum_bucket = market_relative.get("momentum_bucket") if screening_ok else None
    relative_volume_bucket = market_relative.get("relative_volume_bucket") if screening_ok else None
    relative_volume_value = market_relative.get("relative_volume_provider_scoped") if screening_ok else None

    elevated_volume = None
    if screening_ok:
        membership = screening_record.get("screen_membership", {}).get("RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN", {})
        if membership.get("status") == "ELIGIBLE":
            elevated_volume = membership.get("member")

    market_vol_median = market_breadth.get("volatility", {}).get("median")
    volatility_regime = "UNKNOWN"
    if isinstance(volatility, (int, float)) and isinstance(market_vol_median, (int, float)):
        volatility_regime = "AT_OR_ABOVE_MARKET_MEDIAN" if volatility >= market_vol_median else "BELOW_MARKET_MEDIAN"

    sector_comparison = screening_record.get("sector_relative_comparison") if isinstance(screening_record, Mapping) else None
    sector_status = sector_comparison.get("status") if isinstance(sector_comparison, Mapping) else None
    sector_available = sector_status == "AVAILABLE"
    sector_momentum_bucket = sector_comparison.get("momentum_bucket") if sector_available else None

    rule_id, entry_state = _entry_state_rule(
        near_ma20=near_ma20, above_ma20=above_ma20, momentum_positive=momentum_positive,
        momentum_bucket=momentum_bucket, today_positive=today_positive,
        elevated_volume=elevated_volume, volatility_regime=volatility_regime,
        sector_momentum_bucket=sector_momentum_bucket,
    )

    if near_ma20:
        structure_state = "NEAR_MA20_NEUTRAL"
    elif above_ma20:
        structure_state = "ABOVE_MA20_MOMENTUM_POSITIVE" if momentum_positive else "ABOVE_MA20_MOMENTUM_NEGATIVE"
    else:
        structure_state = "BELOW_MA20_MOMENTUM_POSITIVE" if momentum_positive else "BELOW_MA20_MOMENTUM_NEGATIVE"

    liquidity = descriptive_record.get("liquidity", {})
    liquidity_status = liquidity.get("status", "NOT_APPLICABLE")
    liquidity_eligible = liquidity_status == "ELIGIBLE"

    fundamental_context = _fundamental_context(fundamental_record)
    fundamental_tier = fundamental_context["authority_tier"]
    fundamental_readiness = fundamental_context["fundamental_research_readiness"]

    action = ACTION_BY_ENTRY_STATE[entry_state]
    entry_action = ENTRY_ACTION_BY_ENTRY_STATE[entry_state]
    horizon = _horizon(entry_state, fundamental_tier)
    # Position sizing is not implemented anywhere in this pipeline: unconditionally False/
    # NOT_EVALUATED for every entry_state, never derived from liquidity/fundamental/market
    # conditions (see module docstring and blocked_outputs.portfolio_weights_or_position_sizes).
    is_full_position_ready = False
    position_sizing_status = POSITION_SIZING_STATUS
    confidence = _confidence(liquidity_eligible=liquidity_eligible, fundamental_tier=fundamental_tier, sector_available=sector_available)

    evidence_for, evidence_against = _evidence(
        above_ma20=above_ma20, momentum=momentum, momentum_positive=momentum_positive, momentum_bucket=momentum_bucket,
        return_1d=return_1d, today_positive=today_positive, elevated_volume=elevated_volume,
        volatility_regime=volatility_regime, sector_comparison=sector_comparison, liquidity_status=liquidity_status,
        market_state=market_state_block["market_state"], fundamental_tier=fundamental_tier,
        fundamental_readiness=fundamental_readiness, fundamental_status=fundamental_context["status"],
    )

    return {
        "ticker": ticker,
        "market_state": market_state_block["market_state"],
        "ticker_structure_state": structure_state,
        "entry_state": entry_state,
        "action": action,
        "entry_action": entry_action,
        "evidence_for": evidence_for,
        "evidence_against": evidence_against,
        "confirmation_trigger": _CONFIRMATION_TRIGGER_BY_STATE[entry_state],
        "invalidation": _INVALIDATION_BY_STATE[entry_state],
        "data_quality": _data_quality(
            technical_eligible=True, feature_as_of_session=technical.get("feature_as_of_session"),
            is_current_session=technical.get("is_current_session"), liquidity_status=liquidity_status,
            sector_status=sector_status, fundamental_context=fundamental_context,
            market_quality_state=market_state_block.get("quality_state"), confidence=confidence,
        ),
        "horizon": horizon,
        "is_full_position_ready": is_full_position_ready,
        "position_sizing_status": position_sizing_status,
        "fundamental_context": fundamental_context,
        "rule_id": rule_id,
        "signals": {
            "close": close, "ma_20": ma20, "ma20_distance_pct": ma20_distance_pct, "near_ma20": near_ma20,
            "momentum_20d": momentum, "momentum_bucket": momentum_bucket, "return_1d": return_1d,
            "relative_volume_provider_scoped": relative_volume_value, "relative_volume_bucket": relative_volume_bucket,
            "elevated_volume_vs_cohort_median": elevated_volume, "volatility_20d": volatility,
            "volatility_regime_vs_market_median": volatility_regime, "sector_momentum_bucket": sector_momentum_bucket,
        },
        "is_actionable": False,
    }


def build_artifact(
    *, descriptive_source: Mapping[str, Any], screening_source: Mapping[str, Any],
    fundamental_source: Mapping[str, Any], requested_at: str,
) -> dict[str, Any]:
    """Build the complete watchlist tactical entry-state classifier artifact from three already
    -retained, independently-verified inputs. Raises if any input's own recorded content hash does
    not match its bytes, or if screening_source was not built from exactly this descriptive_source
    (a lineage guard, not a recomputation). fundamental_source is verified for its own identity
    only and joined by ticker -- it is a structurally distinct cohort (the P3-F10/P3-F13 evidence
    panel) from the descriptive/screening universe, so a ticker's absence from it is reported as an
    explicit NOT_IN_FUNDAMENTAL_COHORT boundary, never a session/denominator mismatch."""
    _verify_descriptive_identity(descriptive_source)
    _verify_screening_identity(screening_source)
    _verify_fundamental_identity(fundamental_source)

    lineage = screening_source.get("input_lineage", {})
    if lineage.get("current_descriptive_artifact_identity") != descriptive_source.get("artifact_identity"):
        raise WatchlistTacticalEntryClassifierError("SCREENING_SOURCE_LINEAGE_MISMATCH")
    if screening_source.get("session") != descriptive_source.get("session"):
        raise WatchlistTacticalEntryClassifierError("SCREENING_SOURCE_SESSION_MISMATCH")

    descriptive_records = descriptive_source.get("records")
    screening_records = screening_source.get("records")
    fundamental_records = fundamental_source.get("records")
    if not (
        isinstance(descriptive_records, Mapping) and isinstance(screening_records, Mapping)
        and isinstance(fundamental_records, Mapping)
    ):
        raise WatchlistTacticalEntryClassifierError("SOURCE_RECORDS_INVALID")
    if set(descriptive_records) != set(screening_records):
        raise WatchlistTacticalEntryClassifierError("DESCRIPTIVE_SCREENING_TICKER_SET_MISMATCH")

    session = descriptive_source.get("session")
    market_breadth = descriptive_source.get("market_breadth", {})
    market_state_block = _market_state(market_breadth, session=session)

    records: dict[str, dict[str, Any]] = {}
    for ticker in sorted(descriptive_records):
        records[ticker] = _classify_ticker(
            ticker, descriptive_record=descriptive_records[ticker], market_breadth=market_breadth,
            market_state_block=market_state_block, screening_record=screening_records.get(ticker),
            fundamental_record=fundamental_records.get(ticker),
        )

    entry_state_counts = Counter(record["entry_state"] for record in records.values() if record["entry_state"])
    action_counts = Counter(record["action"] for record in records.values())
    entry_action_counts = Counter(record["entry_action"] for record in records.values())
    classified_count = sum(1 for record in records.values() if record["entry_state"] is not None)
    full_position_ready_count = sum(1 for record in records.values() if record["is_full_position_ready"])

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "requested_at": requested_at,
        "session": session,
        "source_artifacts": {
            "descriptive": descriptive_source.get("artifact_identity"),
            "screening": screening_source.get("artifact_identity"),
            "fundamental": fundamental_source.get("artifact_identity"),
        },
        "market_state": market_state_block,
        "state_taxonomy": list(ENTRY_STATES),
        "structure_taxonomy": list(STRUCTURE_STATES),
        "action_taxonomy": list(ACTIONS),
        "action_by_entry_state": dict(ACTION_BY_ENTRY_STATE),
        "entry_action_taxonomy": list(ENTRY_ACTIONS),
        "entry_action_by_entry_state": dict(ENTRY_ACTION_BY_ENTRY_STATE),
        "horizon_by_entry_state": dict(HORIZON_BY_ENTRY_STATE),
        "rule_definitions": dict(RULE_DEFINITIONS),
        "coverage": {
            "candidate_count": len(records),
            "classified_count": classified_count,
            "insufficient_data_count": len(records) - classified_count,
            "entry_state_counts": dict(sorted(entry_state_counts.items())),
            "action_counts": dict(sorted(action_counts.items())),
            "entry_action_counts": dict(sorted(entry_action_counts.items())),
            "full_position_ready_count": full_position_ready_count,
            "fundamental_cohort_intersection_count": sum(1 for ticker in records if ticker in fundamental_records),
        },
        "blocked_outputs": {
            "ordinal_market_ranking": "RANKING_PROHIBITED",
            "opportunity_score": "SCORING_PROHIBITED",
            "probabilities_or_target_prices": "FORECAST_PROHIBITED",
            "portfolio_weights_or_position_sizes": "SIZING_FORMULA_NOT_YET_IMPLEMENTED",
            "historical_raw_as_traded_or_pit": "RAW_AS_TRADED_NOT_PROMOTED",
            "backtesting": "OUT_OF_SCOPE_THIS_MILESTONE",
            "confirmed_bottom_or_top_claims": "EARLY_REVERSAL_OR_BASE_LANGUAGE_ONLY_NEVER_A_CONFIRMED_INFLECTION_CLAIM",
            "traded_value_turnover_adv_adtv": "GROSS_TRADE_AMOUNT_NON_AUTHORITATIVE_SCALE_UNRESOLVED",
        },
        "authority_boundary": {
            "is_actionable": False,
            "not_a_recommendation_or_execution_instruction": True,
            "requires_human_review": True,
            "full_position_sizing_reserved_for_future_milestone": True,
            "position_sizing_not_evaluated_for_any_ticker": True,
            "early_entry_never_implies_full_position": True,
            "market_state_is_context_not_a_forecast_or_gate_on_ticker_entry_state": True,
            "entry_action_is_the_primary_field_for_should_i_enter": True,
            "action_is_secondary_position_management_conditional_on_already_holding": True,
        },
        "records": records,
    }
    identity = content_identity(artifact)
    artifact["artifact_sha256"] = identity["artifact_sha256"]
    artifact["artifact_identity"] = identity["artifact_identity"]
    return artifact
