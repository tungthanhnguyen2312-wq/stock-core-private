"""DNSE OHLC price basis: corporate-action adjustment qualification.

Evidence base: the 2026-08-10 bounded OHLC price-basis pilot,
`operations-review/dnse-ohlc-price-basis-qualification-20260810/probe_results.json`
(3 calls: 1 auth check + 2 resolution="1D" ohlc calls, symbol/type/from/to
per call -- see tools/dnse_market_data_probe.py::build_price_basis_call_plan()).
This module performs no network I/O; it carries the qualification verdict
that bounded empirical evidence established, plus the small set of generic
classification primitives that evidence was read through, so a future
session can extend the event set without re-deriving the method. It does
not re-derive the active verdict per call.

WHAT WAS DEMONSTRATED, AND WHAT WAS NOT
    Two already-qualified corporate-action events (retained in vn_stock.db's
    corporate_event_records, provider VCI, revision_status="observed"; not
    discovered from provider data here) were used as bounded pre/post-event
    windows:

    - HPG, 2026-05-25, 10% stock dividend (exercise_ratio 0.1). DNSE's
      queried-today O/H/L/C match vn_stock.db's current series exactly for
      all 14 sessions in the window (2026-05-15 through 2026-06-03), and the
      close-to-open transition at the ex-date is a normal +1.25% move, not
      the theoretical -9.09% step (1/1.1 - 1) a raw (unadjusted) series
      would show for this exact ratio.
    - VCB, 2026-07-23, 450 VND cash dividend. DNSE's pre-event O/H/L/C
      (2026-07-13 through 2026-07-17) are systematically lower than the
      independently-retained pre-event archive
      (archive/runtime-backups/VNSTOCK_DATA_BACKUPS/20260719_223620/vn_stock.db,
      snapshotted 2026-07-19, before this event's 2026-07-23 ex-date) by a
      ratio of 0.991667-0.991823 (mean 0.991746, n=20 across O/H/L/C x 5
      sessions) -- matching the already-independently-qualified VCI
      cash-dividend adjustment factor of 0.9917 (docs/DECISIONS.md, "A
      single constant factor 0.9917 reproduces all 13 sessions exactly")
      almost exactly. Volume for these same sessions is byte-identical
      between DNSE and the archive (proving this is a price-only
      transformation, not a different data source or a wholesale
      mismatch). Post-event DNSE prices (2026-07-23 onward) match
      vn_stock.db's current series exactly -- untouched, as a genuine
      traded price should be.

    Together these directly prove DNSE's response for the *same* historical
    calendar dates changed between a pre-event archive (captured before
    2026-07-23) and today's query (after it) -- retrospective rewriting,
    not a one-time-recorded, immutable series. See Step 8's distinction,
    carried here as two independent fields: CURRENT_ANALYSIS_PRICE_BASIS_SAFE
    (True) and BACKTEST_POINT_IN_TIME_SAFE (False) -- never conflate them.

    NOT tested: stock splits, reverse splits, rights issues, any event on a
    ticker other than HPG/VCB, and whether the cash-dividend adjustment is a
    price-return (ex-dividend) style factor or a total-return (dividend-
    reinvested) style factor -- the observed factor matches VCI's own
    already-labelled "standard cash-dividend back-adjustment", which this
    project treats as price-return style, but that label was not
    independently re-derived from first principles within DNSE alone here.
    Coverage generalization beyond these two event types and two tickers is
    explicitly NOT authorized -- see UNQUALIFIED_ACTION_TYPES below.

    DNSE's normal market volume basis remains separately, independently
    unqualified (dnse_market_data_source_qualification_20260810.md) and is
    never inherited by anything in this module -- volume was read only as
    non-authoritative corroborating context (the VCB pre-event volume match
    strengthens confidence that DNSE/the archive are the same underlying
    session, not that DNSE's volume basis is now qualified).

    Not wired into production provider routing. market_data_source_authority.py
    is deliberately untouched, matching every prior DNSE qualification
    milestone in this repository.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

VERSION = "1.0.0"
PROVIDER = "DNSE"
SOURCE_CONTRACT_VERSION = "dnse_ohlc_price_basis/2026-08-10"

# Step 9's formal verdict vocabulary -- exactly the milestone's own four values.
RAW_CONFIRMED = "RAW_CONFIRMED"
ADJUSTED_CONFIRMED = "ADJUSTED_CONFIRMED"
CONDITIONALLY_ADJUSTED = "CONDITIONALLY_ADJUSTED"
INCONCLUSIVE = "INCONCLUSIVE"
PRICE_BASIS_VERDICTS = frozenset(
    {RAW_CONFIRMED, ADJUSTED_CONFIRMED, CONDITIONALLY_ADJUSTED, INCONCLUSIVE}
)

# Per-event/per-session pattern labels -- a narrower, lower-level vocabulary
# than PRICE_BASIS_VERDICTS. combine_event_verdicts() folds these into one
# formal verdict; nothing here is ever exposed as a formal verdict directly.
RAW_PATTERN = "raw_pattern"
ADJUSTED_PATTERN = "adjusted_pattern"
INCONCLUSIVE_PATTERN = "inconclusive_pattern"
_EVENT_PATTERNS = frozenset({RAW_PATTERN, ADJUSTED_PATTERN, INCONCLUSIVE_PATTERN})

FIELDS: tuple[str, ...] = ("o", "h", "l", "c")

# The active, evidence-grounded verdict. A caller may not upgrade this
# locally -- reaching a different verdict, or extending
# QUALIFIED_ACTION_TYPES, requires new evidence, which requires editing
# these constants alongside it.
ACTIVE_PRICE_BASIS_VERDICT = ADJUSTED_CONFIRMED
RETROSPECTIVE_ADJUSTMENT_PROVEN = True
OHLC_ALL_FIELDS_ADJUST_CONSISTENTLY = True
# price-return-style inferred by consistency with VCI's own already-established
# label, not independently re-derived from first principles within DNSE alone.
TOTAL_RETURN_DIVIDEND_ADJUSTMENT = "unknown_inferred_price_return_style_by_vci_consistency"

# Step 8: two separate properties, never conflated.
CURRENT_ANALYSIS_PRICE_BASIS_SAFE = True
BACKTEST_POINT_IN_TIME_SAFE = False

QUALIFIED_ACTION_TYPES = ("stock_dividend_bonus_issue", "cash_dividend")
UNQUALIFIED_ACTION_TYPES = (
    "stock_split",
    "reverse_split",
    "rights_issue",
    "other_or_untested_ticker_or_event",
)

WARNINGS = (
    "dnse_ohlc_price_basis_qualified_for_exactly_two_event_types_on_exactly_two_tickers",
    "coverage_generalization_beyond_hpg_stock_dividend_and_vcb_cash_dividend_not_authorized",
    "retrospective_adjustment_proven_current_query_response_is_not_point_in_time_reproducible",
    "total_return_vs_price_return_dividend_treatment_not_independently_distinguished",
    "dnse_normal_market_volume_basis_remains_separately_unqualified_never_inherited_here",
    "not_wired_into_production_provider_routing",
)

# Reused as-is from vn_stock.db's corporate_event_records (provider VCI,
# revision_status="observed"), independently cited by the already-closed VCI
# price-basis investigation (docs/DECISIONS.md). Not discovered here.
EVIDENCE_EVENTS: tuple[dict[str, Any], ...] = (
    {
        "ticker": "HPG",
        "event_code": "ISS",
        "event_type": "stock_dividend_bonus_issue",
        "exright_date": "2026-05-25",
        "exercise_ratio": 0.1,
        "qualified_source": "VCI corporate_event_records",
        "record_id": "31135d0d92c49322d66f26813bf4161505ce100e71d94057be4891b8467d7775",
        "window": {"from": "2026-05-15", "to": "2026-06-03"},
        "comparison_method": "internal_transition_vs_theoretical_ratio_plus_exact_match_to_vn_stock_db_current_series",
        "sessions_compared": 14,
        "observed_pattern": ADJUSTED_PATTERN,
    },
    {
        "ticker": "VCB",
        "event_code": "DIV",
        "event_type": "cash_dividend",
        "exright_date": "2026-07-23",
        "value_per_share_vnd": 450.0,
        "qualified_source": "VCI corporate_event_records",
        "record_id": "11ff5ae3e7ebbb8a0aca4d0240a33165b117ddafb1cee6d977d5a9c76cd2e534",
        "window": {"from": "2026-07-13", "to": "2026-07-31"},
        "comparison_method": "pre_event_archive_vs_today_query_ratio_plus_post_event_exact_match",
        "pre_event_sessions_compared": 5,
        "post_event_sessions_compared": 7,
        "observed_pre_event_ratio_min": 0.991667,
        "observed_pre_event_ratio_max": 0.991823,
        "observed_pre_event_ratio_mean": 0.991746,
        "reference_vci_factor": 0.9917,
        "volume_unchanged_pre_event": True,
        # Tighter than classify_cross_reference_ratio's defaults, justified by
        # the tight observed cluster above (range 0.000156 across 20 field
        # observations) -- see that function's docstring before reusing these.
        "classification_tolerance": 0.001,
        "classification_min_separation": 0.005,
        "observed_pattern": ADJUSTED_PATTERN,
    },
)


class DnseOhlcPriceBasisError(ValueError):
    """Fail-closed rejection for an out-of-vocabulary or unearned price-basis claim."""


# --------------------------------------------------------------------- Step 3 gate

def assert_ratio_semantics_unambiguous(event: Mapping[str, Any]) -> None:
    """Reject an event whose corporate-action ratio semantics are not
    unambiguous -- exactly Step 3's evidence gate. A share-count event must
    carry a numeric `exercise_ratio` > 0; a cash event must carry a numeric
    `value_per_share_vnd` > 0. An event with neither, or with a
    non-numeric/non-positive value where present, is rejected -- never
    inferred from a label or a price shape."""
    ratio = event.get("exercise_ratio")
    cash = event.get("value_per_share_vnd")
    has_ratio = isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and ratio > 0
    has_cash = isinstance(cash, (int, float)) and not isinstance(cash, bool) and cash > 0
    if not (has_ratio or has_cash):
        raise DnseOhlcPriceBasisError("ambiguous_or_missing_ratio_semantics")


# --------------------------------------------------------------------- Step 6 comparison

def field_ratios(observed: Mapping[str, float], reference: Mapping[str, float]) -> dict[str, float]:
    """observed[f] / reference[f] for each OHLC field. Fails closed on a
    missing or non-positive value in either side -- a ratio cannot be
    computed from an absent or zero/negative price."""
    ratios: dict[str, float] = {}
    for field in FIELDS:
        ref_v = reference.get(field)
        obs_v = observed.get(field)
        if not isinstance(ref_v, (int, float)) or isinstance(ref_v, bool) or ref_v <= 0:
            raise DnseOhlcPriceBasisError(f"reference_field_missing_or_non_positive:{field}")
        if not isinstance(obs_v, (int, float)) or isinstance(obs_v, bool) or obs_v <= 0:
            raise DnseOhlcPriceBasisError(f"observed_field_missing_or_non_positive:{field}")
        ratios[field] = obs_v / ref_v
    return ratios


def assert_consistent_ratios(ratios: Mapping[str, float], *, tolerance: float = 0.003) -> None:
    """Fail closed if O/H/L/C do not move by a consistent ratio. A genuine
    corporate-action price adjustment rescales every OHLC field by the same
    factor; a spread wider than `tolerance` is not a clean adjustment
    signature and must never be silently classified as one (Step 6.C)."""
    values = list(ratios.values())
    spread = max(values) - min(values)
    if spread > tolerance:
        raise DnseOhlcPriceBasisError(f"inconsistent_ohlc_transformation:spread={spread:.6f}")


def classify_cross_reference_ratio(
    mean_ratio: float,
    *,
    adjusted_expected: float,
    raw_expected: float = 1.0,
    tolerance: float = 0.01,
    min_separation: float = 0.02,
) -> str:
    """Classify a DNSE-vs-independent-reference ratio (e.g. DNSE pre-event
    price / archived pre-event price) as RAW_PATTERN, ADJUSTED_PATTERN, or
    INCONCLUSIVE_PATTERN.

    Refuses to discriminate (always INCONCLUSIVE_PATTERN) when raw_expected
    and adjusted_expected are too close together -- an ordinary session
    where a raw and an adjusted series would look identical must never be
    read as proof of either basis (the milestone's own explicit
    instruction).

    The defaults are deliberately conservative (a 1% match tolerance, a 2%
    minimum raw/adjusted separation) and are appropriate for a single
    imprecise observation or a large-magnitude event. A small-magnitude
    event (e.g. a cash dividend worth under 1% of the price, like VCB's
    2026-07-23 450 VND event, separation only ~0.83%) will correctly return
    INCONCLUSIVE_PATTERN at these defaults -- that is not a bug to work
    around by loosening the call blindly. Pass tighter values ONLY when
    justified by the actual observed measurement precision (e.g. a tight
    multi-session ratio cluster, as EVIDENCE_EVENTS records for VCB:
    observed range 0.991667-0.991823 across 20 field observations, which is
    what justifies tolerance=0.001/min_separation=0.005 there instead of
    the defaults). Never loosen these parameters merely to force a
    pattern out of noisy or single-sample data."""
    if abs(raw_expected - adjusted_expected) < min_separation:
        return INCONCLUSIVE_PATTERN
    if abs(mean_ratio - raw_expected) <= tolerance:
        return RAW_PATTERN
    if abs(mean_ratio - adjusted_expected) <= tolerance:
        return ADJUSTED_PATTERN
    return INCONCLUSIVE_PATTERN


def classify_internal_transition(
    prior_close: float,
    exdate_price: float,
    *,
    theoretical_ratio: float,
    noise_tolerance: float = 0.03,
    min_separation: float = 0.02,
) -> str:
    """Classify a single series' own pre-to-post-ex-date transition as
    RAW_PATTERN (a discrete step matching the theoretical raw drop),
    ADJUSTED_PATTERN (no structural discontinuity beyond ordinary daily
    noise), or INCONCLUSIVE_PATTERN.

    `theoretical_ratio` is the share-count multiplier (e.g. 1.1 for a 10%
    stock dividend); the theoretical raw step is 1/theoretical_ratio - 1.
    Refuses to discriminate when that theoretical step is smaller than
    `min_separation` -- too small an event to distinguish from noise."""
    if prior_close <= 0:
        raise DnseOhlcPriceBasisError("prior_close_non_positive")
    theoretical_raw_change = 1.0 / theoretical_ratio - 1.0
    if abs(theoretical_raw_change) < min_separation:
        return INCONCLUSIVE_PATTERN
    observed_change = exdate_price / prior_close - 1.0
    if abs(observed_change - theoretical_raw_change) <= noise_tolerance:
        return RAW_PATTERN
    if abs(observed_change) <= noise_tolerance:
        return ADJUSTED_PATTERN
    return INCONCLUSIVE_PATTERN


# --------------------------------------------------------------------- Step 7/9/12 combination

def combine_event_verdicts(
    event_patterns: Sequence[str], *, single_event_sufficient: bool = False,
) -> str:
    """Combine independent per-event pattern classifications into one formal
    PRICE_BASIS_VERDICTS value.

    Fails closed: any INCONCLUSIVE_PATTERN input, or no input at all, yields
    INCONCLUSIVE overall. Disagreement between events (some raw, some
    adjusted) yields CONDITIONALLY_ADJUSTED -- never silently resolved by
    majority or recency. Fewer than two agreeing events yields INCONCLUSIVE
    unless `single_event_sufficient` is explicitly passed (Step 7: this
    project's price-basis contract does not currently declare one event
    sufficient, so callers must opt in deliberately, not by default)."""
    for pattern in event_patterns:
        if pattern not in _EVENT_PATTERNS:
            raise DnseOhlcPriceBasisError(f"event_pattern_invalid:{pattern}")
    if not event_patterns or any(p == INCONCLUSIVE_PATTERN for p in event_patterns):
        return INCONCLUSIVE
    unique = set(event_patterns)
    if len(unique) > 1:
        return CONDITIONALLY_ADJUSTED
    if len(event_patterns) < 2 and not single_event_sufficient:
        return INCONCLUSIVE
    verdict_pattern = unique.pop()
    return ADJUSTED_CONFIRMED if verdict_pattern == ADJUSTED_PATTERN else RAW_CONFIRMED


# --------------------------------------------------------------------- Step 10 contract

def action_type_qualified(action_type: str) -> bool:
    """Whether a given corporate-action type may rely on
    ACTIVE_PRICE_BASIS_VERDICT. Fails closed (False) for anything not
    explicitly in QUALIFIED_ACTION_TYPES -- no inference, no partial credit,
    no generalization from a similarly-shaped event type."""
    return action_type in QUALIFIED_ACTION_TYPES


def serialize(record: Mapping[str, Any]) -> str:
    """Deterministic JSON serialization -- same input always produces the
    same bytes, so a caller can hash/compare/replay a retained record."""
    return json.dumps(record, sort_keys=True, default=str)


def active_capability_contract() -> dict[str, Any]:
    """The canonical, active DNSE OHLC price-basis verdict, assembled once
    from the 2026-08-10 bounded pilot's evidence. Consumers read this rather
    than re-deriving a verdict from raw evidence files. Deliberately carries
    no provider-routing flag: this stays a qualification record, not a
    wiring decision -- see market_data_source_authority.py, untouched."""
    return {
        "schema_version": VERSION,
        "source": PROVIDER,
        "contract_version": SOURCE_CONTRACT_VERSION,
        "price_basis": ACTIVE_PRICE_BASIS_VERDICT,
        "qualified_action_types": list(QUALIFIED_ACTION_TYPES),
        "unqualified_action_types": list(UNQUALIFIED_ACTION_TYPES),
        "retrospective_adjustment": RETROSPECTIVE_ADJUSTMENT_PROVEN,
        "ohlc_all_fields_adjust_consistently": OHLC_ALL_FIELDS_ADJUST_CONSISTENTLY,
        "total_return_dividend_adjustment": TOTAL_RETURN_DIVIDEND_ADJUSTMENT,
        "current_analysis_price_basis_safe": CURRENT_ANALYSIS_PRICE_BASIS_SAFE,
        "backtest_point_in_time_safe": BACKTEST_POINT_IN_TIME_SAFE,
        "evidence_events": [dict(event) for event in EVIDENCE_EVENTS],
        "warnings": list(WARNINGS),
        "qualification_status": "SOURCE_QUALIFICATION_COMPLETE_NOT_INTEGRATED",
        "evidence": (
            "operations-review/dnse-ohlc-price-basis-qualification-20260810/probe_results.json"
        ),
    }


def assert_fail_closed(verdict: str) -> None:
    """Refuse an out-of-vocabulary formal price-basis verdict."""
    if verdict not in PRICE_BASIS_VERDICTS:
        raise DnseOhlcPriceBasisError(f"price_basis_verdict_invalid:{verdict}")
