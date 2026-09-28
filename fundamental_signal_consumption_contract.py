"""Fundamental Signal Consumption Contract (INTEGRATED_FUNDAMENTAL_STATE_CONSUMPTION_RECONCILIATION_V1,
hardened by FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1).

The one deterministic adapter between the fundamental producers and the Integrated Decision.
The Integrated Decision's fundamental reader was written against a hypothesised vocabulary
(SAFE/STRESSED leverage, EXPANDING growth, a bare ``TURNAROUND``, un-prefixed trajectories) that
the Financial V2 engine never emitted, so most computed states never reached ``fundamental_state``.
This module replaces those scattered string comparisons with one explicit mapping from each
producer's own vocabulary to separate semantic axes:

- LEVEL -- an absolute condition, asserted only where a producer itself classifies one;
- DIRECTION -- change, never quality (an improving debt/equity ratio says nothing about whether
  the debt level is safe);
- TRANSITION -- an earnings sign transition, never ordinary percentage growth;
- COMPOSITION -- a mix trajectory with no producer polarity;
- APPLICABILITY -- the producer's own entity gating (corporate, bank, securities, unresolved);
- FITNESS -- qualification, source feature, period, freshness and basis, carried unchanged.

Every signal also has an explicit policy class (``CURRENT_DECISION_VOTE``,
``RESEARCH_EVIDENCE_ONLY``, ``TRANSITION_EVENT``; per record also ``NON_APPLICABLE`` or
``UNKNOWN``). Only a ``CURRENT`` period may vote into the current directional state: usable
research history is not a current decision signal, so ``STALE_BUT_RESEARCH_USABLE`` evidence stays
visible (strengths/weaknesses, historical context, stale-evidence lists) but never votes and never
triggers TURNAROUND, and a period after the decision session never enters at all. Whether
qualified fundamental evidence exists (``evidence_availability``) is reported apart from whether
the current direction is sufficient (``fundamental_state``).

It computes no ratio, no threshold and no score, and it promotes no authority: a proxy stays a
proxy and a stale period stays labelled stale. ``fundamental_state`` is derived from explicit
current dimension votes by the unchanged Integrated Decision fundamental policy; the components
stay alongside it.

CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1 adds, without new data or thresholds:

- ``fundamental_evidence_availability`` -- CURRENT_DIRECTIONAL / CURRENT_NON_DIRECTIONAL /
  STALE_ONLY / NOT_APPLICABLE_ENTITY / ABSENT, so an insufficient direction never reads as absent
  evidence;
- ``fundamental_risk_level`` -- from qualified LEVEL evidence only (never from a direction), with
  known adverse history kept as known when it is not current, and never a "healthy" claim;
- one vote per balance-sheet observation: capital-structure and short-term-liquidity directions
  measured on the same balance sheet count once when they agree, and stay two opposing votes when
  they disagree;
- a sign transition votes only on a seasonally comparable basis (same-quarter YoY or TTM); a
  sequential (QoQ) flip stays visible as an observation;
- an unresolved entity family keeps its evidence for research but never votes;
- a quarter label after the decision session whose evidence was retained before the session is a
  non-calendar fiscal label: known research evidence whose calendar period (so currency) is
  unresolved, never a vote; without that knowledge proof it stays excluded;
- an explicit policy epoch (``DECISION_POLICY_VERSION``) so states produced under different
  fundamental policies are never compared as issuer or market transitions.
"""
from __future__ import annotations

from collections import Counter
import calendar
from datetime import date
import re
from typing import Any, Mapping, Sequence

from operational_fundamental_context_integration import MAX_COMPLETED_QUARTER_LAG
from opportunity_axis_freshness import CURRENT, STALE_BUT_RESEARCH_USABLE, classify_financial_period_freshness

CONTRACT_VERSION = "fundamental_signal_consumption/v1"
#: The vote policy of this contract version (CURRENT_RESEARCH_FUNDAMENTAL_PROMOTION_HARDENING_V1).
SIGNAL_POLICY = "fundamental_promotion_hardening/v1"
#: The fundamental decision-policy epoch. Every Integrated Decision record carries it, it enters
#: the decision identity, and a state compared across two different epochs is
#: NOT_COMPARABLE_POLICY_CHANGE, never an issuer or market transition.
DECISION_POLICY_VERSION = SIGNAL_POLICY
#: Epochs of records produced before the field existed, resolved from the record's own shape.
LEGACY_POLICY_EPOCH = "legacy_unversioned_fundamental_reader/v0"
CONSUMPTION_POLICY_EPOCH = "fundamental_signal_consumption/v1"
POLICY_EPOCHS = (LEGACY_POLICY_EPOCH, CONSUMPTION_POLICY_EPOCH, "fundamental_signal_policy_hardening/v1",
                 DECISION_POLICY_VERSION)
NOT_COMPARABLE_POLICY_CHANGE = "NOT_COMPARABLE_POLICY_CHANGE"
DERIVATION_RULE = "integrated_fundamental_direction_policy_over_dimension_votes/v1"
VOTE_ELIGIBILITY_RULE = "current_period_comparable_basis_applicable_entity_decision_signals_only/v2"
EVIDENCE_AVAILABILITY_RULE = "research_usable_decision_grade_fundamental_signal_any_usable_period/v1"
FIVE_STATE_AVAILABILITY_RULE = "fundamental_evidence_availability/v1"
RISK_LEVEL_RULE = "fundamental_risk_level_from_qualified_level_evidence_only/v1"
VOTE_GROUPING_RULE = "one_vote_per_balance_sheet_observation/v1"
FISCAL_PERIOD_RULE = "post_session_quarter_label_known_before_session_is_non_calendar_fiscal/v1"

DIALECT_FINANCIAL_V2 = "financial_analysis_compact/v1"
DIALECT_OPERATIONAL_BRIDGE = "entity_aware_operational_fundamental_context_integration/v1"

# ── fundamental_state vocabulary (unchanged; owned here, aliased by the Integrated Decision) ──
FUNDAMENTAL_IMPROVING = "IMPROVING"
FUNDAMENTAL_STABLE = "STABLE"
FUNDAMENTAL_MIXED = "MIXED"
FUNDAMENTAL_DETERIORATING = "DETERIORATING"
FUNDAMENTAL_TURNAROUND = "TURNAROUND"
FUNDAMENTAL_INSUFFICIENT = "INSUFFICIENT"

# ── Axes ─────────────────────────────────────────────────────────────────────────────────────
LEVEL = "LEVEL"
DIRECTION = "DIRECTION"
TRANSITION = "TRANSITION"
COMPOSITION = "COMPOSITION"

HEALTHY = "HEALTHY"
STRESSED = "STRESSED"
DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
IMPROVING = "IMPROVING"
STABLE = "STABLE"
WORSENING = "WORSENING"
MIXED = "MIXED"
RISING = "RISING"
FALLING = "FALLING"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
AVAILABLE = "AVAILABLE"

LOSS_TO_PROFIT = "LOSS_TO_PROFIT"
PROFIT_TO_LOSS = "PROFIT_TO_LOSS"
LOSS_NARROWED = "LOSS_NARROWED"
LOSS_WIDENED = "LOSS_WIDENED"
ZERO_BASE = "ZERO_BASE"
ADVERSE_SIGN_TRANSITION_UNRESOLVED = "ADVERSE_SIGN_TRANSITION_UNRESOLVED"
NONE_OBSERVED = "NONE_OBSERVED"

APPLICABLE = "APPLICABLE"
NON_APPLICABLE = "NON_APPLICABLE"
UNRESOLVED = "UNRESOLVED"

DECISION = "DECISION"
EVIDENCE_ONLY = "EVIDENCE_ONLY"

# ── Policy classes (FUNDAMENTAL_SIGNAL_POLICY_HARDENING_V1) ────────────────────────────────────
#: May vote into the current fundamental directional state, from a CURRENT period only.
CURRENT_DECISION_VOTE = "CURRENT_DECISION_VOTE"
#: Valid research evidence that never votes: evidence-only by contract, or a stale period.
RESEARCH_EVIDENCE_ONLY = "RESEARCH_EVIDENCE_ONLY"
#: An earnings sign-transition event; votes on the transition axis from a CURRENT period only.
TRANSITION_EVENT = "TRANSITION_EVENT"
#: Per record: NON_APPLICABLE (entity gating) or UNKNOWN (value or semantics not established).
POLICY_CLASSES = (CURRENT_DECISION_VOTE, RESEARCH_EVIDENCE_ONLY, TRANSITION_EVENT, NON_APPLICABLE, UNKNOWN)
_ROLE = {CURRENT_DECISION_VOTE: DECISION, TRANSITION_EVENT: DECISION, RESEARCH_EVIDENCE_ONLY: EVIDENCE_ONLY}

FAVORABLE = "FAVORABLE"
ADVERSE = "ADVERSE"
NEUTRAL = "NEUTRAL"

NOT_EVALUATED = "NOT_EVALUATED_NO_DECISION_SESSION"
#: A quarter label after the decision session carried by evidence retained before the session: a
#: non-calendar fiscal label. Known research evidence; its calendar period is unresolved (no
#: governed fiscal-year registry exists), so its currency is unestablished and it never votes.
NON_CALENDAR_FISCAL_PERIOD = "NON_CALENDAR_FISCAL_PERIOD_KNOWN_BY_SESSION"
#: A valid period older than the governed completed-quarter window: research evidence, not a vote.
STALE_NOT_A_CURRENT_VOTE = "STALE_RESEARCH_EVIDENCE_NOT_A_CURRENT_VOTE"
#: Why valid research evidence does not vote (per signal, ``non_vote_reason``).
FISCAL_CALENDAR_UNRESOLVED_NOT_A_VOTE = "NON_CALENDAR_FISCAL_LABEL_CALENDAR_PERIOD_UNRESOLVED_NOT_A_VOTE"
ENTITY_UNRESOLVED_NOT_A_VOTE = "ENTITY_FAMILY_UNRESOLVED_RESEARCH_EVIDENCE_NOT_A_VOTE"
SEQUENTIAL_TRANSITION_NOT_A_VOTE = "SEQUENTIAL_QOQ_SIGN_TRANSITION_OBSERVATION_NOT_A_DECISION_BASIS"
TRANSITION_BASIS_UNRESOLVED_NOT_A_VOTE = "SIGN_TRANSITION_BASIS_UNRESOLVED_NOT_A_DECISION_BASIS"
NON_VOTE_REASONS = (STALE_NOT_A_CURRENT_VOTE, FISCAL_CALENDAR_UNRESOLVED_NOT_A_VOTE, ENTITY_UNRESOLVED_NOT_A_VOTE,
                    SEQUENTIAL_TRANSITION_NOT_A_VOTE, TRANSITION_BASIS_UNRESOLVED_NOT_A_VOTE)
_VOTING_FRESHNESS = frozenset({CURRENT, NOT_EVALUATED})

#: A transition on a seasonally comparable basis. Only these bases may vote or trigger the
#: TURNAROUND override -- mirroring the engine's own TURNAROUND_CONTEXT, which it asserts from
#: the same-quarter YoY transition only. A sequential (QoQ) sign flip is seasonality-prone: it
#: stays a visible observation and never moves the direction or the posture.
TURNAROUND_BASES = frozenset({"SAME_QUARTER_YOY", "TTM"})
DECISION_TRANSITION_BASES = TURNAROUND_BASES
#: TURNAROUND asserts a current event; a stale transition is historical context only.
TURNAROUND_FRESHNESS = _VOTING_FRESHNESS

# ── fundamental_evidence_availability (the five states) ───────────────────────────────────────
CURRENT_DIRECTIONAL = "CURRENT_DIRECTIONAL"
CURRENT_NON_DIRECTIONAL = "CURRENT_NON_DIRECTIONAL"
STALE_ONLY = "STALE_ONLY"
NOT_APPLICABLE_ENTITY = "NOT_APPLICABLE_ENTITY"
ABSENT = "ABSENT"
EVIDENCE_AVAILABILITY_STATES = (CURRENT_DIRECTIONAL, CURRENT_NON_DIRECTIONAL, STALE_ONLY, NOT_APPLICABLE_ENTITY, ABSENT)

# ── fundamental_risk_level (qualified LEVEL evidence only) ──────────────────────────────────
ADVERSE_LEVEL_CURRENT = "ADVERSE_LEVEL_CURRENT"
ADVERSE_LEVEL_KNOWN_NOT_CURRENT = "ADVERSE_LEVEL_KNOWN_NOT_CURRENT"
NO_QUALIFIED_ADVERSE_LEVEL = "NO_QUALIFIED_ADVERSE_LEVEL"
LEVEL_UNKNOWN = "LEVEL_UNKNOWN"
RISK_LEVEL_STATES = (ADVERSE_LEVEL_CURRENT, ADVERSE_LEVEL_KNOWN_NOT_CURRENT, NO_QUALIFIED_ADVERSE_LEVEL, LEVEL_UNKNOWN)
#: Level dimensions with a producer-qualified polarity. Leverage, margin and liquidity levels have
#: no governed classifier and stay unassessed; resilience is an engine composite that also reads
#: margin and balance-sheet directions, so it never feeds a level.
_RISK_LEVEL_DIMENSIONS = ("PROFITABILITY", "CASH_QUALITY")

# ── Entity decision applicability (per record) ──────────────────────────────────────────────
ENTITY_DECISION_APPLICABLE = "DECISION_APPLICABLE"
ENTITY_SPECIALIST_SIGNALS_ONLY = "SPECIALIST_SIGNALS_ONLY"
ENTITY_NO_DECISION_SIGNAL_FAMILY = "NO_DECISION_SIGNAL_FAMILY"
ENTITY_FAMILY_UNRESOLVED = "ENTITY_FAMILY_UNRESOLVED"

# ── One vote per balance-sheet observation ──────────────────────────────────────────────────
#: Capital-structure and short-term-liquidity directions are same-quarter YoY ratios of ONE
#: balance sheet; a single event (a short-term borrowing, a debt-funded asset, a dividend) moves
#: both. Measured on the same observation and agreeing, they are one vote (counted on the member
#: the deterioration gate names); disagreeing, both stay; on different observations, both count.
VOTE_GROUPS = (
    {"group": "BALANCE_SHEET_OBSERVATION",
     "members": (("CAPITAL_STRUCTURE", "DIRECTION"), ("SHORT_TERM_LIQUIDITY", "DIRECTION")),
     "counted": ("CAPITAL_STRUCTURE", "DIRECTION")},
)

_INDUSTRIAL = "INDUSTRIAL_FINANCIAL_ANALYSIS"
_GENERIC = "UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS"
_USABLE_FEATURE_FITNESS = frozenset({"READY", "RESEARCH_PROXY"})
_NI_TRANSITION_FEATURES = ("net_income_qoq", "net_income_same_quarter_yoy", "net_income_ttm_yoy")
#: Which feature carries an engine sign transition: a seasonally comparable basis first, so a
#: transition the same-quarter YoY or TTM series also shows is never read as a QoQ observation.
_NI_TRANSITION_SOURCE_ORDER = ("net_income_same_quarter_yoy", "net_income_ttm_yoy", "net_income_qoq")
_GROWTH_CONSENSUS_FEATURES = ("revenue_qoq", "revenue_same_quarter_yoy", "net_income_qoq", "net_income_same_quarter_yoy")

# Applicability families: which entity a producer computes the signal for.
_CORPORATE = "CORPORATE"
_GENERIC_PRIMITIVE = "GENERIC_PRIMITIVE"  # corporate, or an unresolved entity the producer explicitly allows
_BANK = "BANK"
_SECURITIES = "SECURITIES"

# ── The contract: one row per consumed producer signal ────────────────────────────────────────
# ``values`` maps the producer's own vocabulary to the contract value; any other producer value
# is UNKNOWN and never guessed. ``codes`` are the decision reason codes per polarity.
# ``policy_class`` says whether the state may vote at all; ``policy_reason`` says why.
SIGNALS: dict[str, dict[str, Any]] = {
    "profitability_level": {
        "producer_field": "profitability_state", "dimension": "PROFITABILITY", "axis": LEVEL,
        "family": _GENERIC_PRIMITIVE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"PROFITABLE": HEALTHY, "LOSS_MAKING": STRESSED},
        "codes": {FAVORABLE: "PROFITABLE_CORE_OPERATIONS", ADVERSE: "OBSERVED_LOSS_MAKING"},
        "semantic": "Sign of the latest compatible standalone-quarter net income (a level).",
        "policy_reason": "A current-period profit or loss is an observed level the decision may weigh.",
    },
    "earnings_transition": {
        "producer_field": "earnings_turnaround_state", "dimension": "PROFITABILITY", "axis": TRANSITION,
        "family": _CORPORATE, "policy_class": TRANSITION_EVENT,
        "values": {LOSS_TO_PROFIT: LOSS_TO_PROFIT, PROFIT_TO_LOSS: PROFIT_TO_LOSS, LOSS_NARROWED: LOSS_NARROWED,
                   LOSS_WIDENED: LOSS_WIDENED, ZERO_BASE: ZERO_BASE},
        "codes": {},  # basis-specific, see _transition_code
        "semantic": ("Net-income sign transition between two compatible periods of one semantic series "
                     "(qoq, same-quarter yoy, ttm); never percentage growth."),
        "policy_reason": ("An event, not a level or a growth direction. Only a CURRENT transition on a seasonally "
                          "comparable basis (same-quarter YoY or TTM) votes or triggers TURNAROUND; a sequential "
                          "QoQ flip stays a visible observation."),
    },
    "growth_direction": {
        "producer_field": "growth_state", "dimension": "GROWTH", "axis": DIRECTION,
        "family": _CORPORATE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"GROWING": IMPROVING, "CONTRACTING": WORSENING, "STABLE": STABLE},
        "codes": {FAVORABLE: "REVENUE_GROWTH_EXPANDING", ADVERSE: "REVENUE_CONTRACTION"},
        "semantic": "Engine consensus of positive-base revenue/net-income qoq and same-quarter yoy growth.",
        "policy_reason": ("Every available positive-base growth feature must agree; a disagreement or a sign "
                          "transition is no consensus."),
    },
    "net_margin_direction": {
        "producer_field": "margin_state", "dimension": "MARGINS", "axis": DIRECTION,
        "family": _CORPORATE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"MARGIN_EXPANDING": IMPROVING, "MARGIN_COMPRESSING": WORSENING, "MARGIN_STABLE": STABLE},
        "codes": {FAVORABLE: "MARGIN_EXPANSION", ADVERSE: "MARGIN_COMPRESSION"},
        "semantic": "Consecutive-quarter change of the same-provider net margin (a direction, not a level).",
        "policy_reason": ("A ratio direction over consecutive compatible quarters (not seasonally adjusted); "
                          "never a margin level."),
    },
    "gross_margin_direction": {
        "producer_field": "gross_margin_trajectory_state", "dimension": "MARGINS", "axis": DIRECTION,
        "family": _CORPORATE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"GROSS_MARGIN_IMPROVING": IMPROVING, "GROSS_MARGIN_WORSENING": WORSENING, "GROSS_MARGIN_STABLE": STABLE},
        "codes": {FAVORABLE: "GROSS_MARGIN_EXPANSION", ADVERSE: "GROSS_MARGIN_COMPRESSION"},
        "semantic": "Same-quarter prior-year change of the same-provider gross margin (a direction).",
        "policy_reason": "A seasonally comparable ratio direction; never a margin level.",
    },
    "cash_conversion_level": {
        "producer_field": "cash_conversion_state", "dimension": "CASH_QUALITY", "axis": LEVEL,
        "family": _CORPORATE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"HEALTHY": HEALTHY, "WEAK": STRESSED},
        "codes": {FAVORABLE: "POSITIVE_CASH_CONVERSION_PROXY", ADVERSE: "WEAK_CASH_CONVERSION_PROXY"},
        "semantic": ("Sign of CFO / net income. The sign means cash quality only over positive same-period "
                     "earnings; otherwise the level is not asserted."),
        "policy_reason": "Votes only over positive same-period earnings; otherwise its polarity is UNKNOWN.",
    },
    "free_cash_flow_proxy_direction": {
        "producer_field": "free_cash_flow_proxy_direction_state", "dimension": "CASH_QUALITY", "axis": DIRECTION,
        "family": _CORPORATE, "policy_class": RESEARCH_EVIDENCE_ONLY,
        "values": {"IMPROVING": IMPROVING, "WORSENING": WORSENING, "STABLE": STABLE},
        "codes": {},
        "semantic": "Same-quarter YoY change of OCF + signed capex; the engine declares it never affects decisions.",
        "policy_reason": "Producer-declared evidence only; an amount trajectory with no governed quality contract.",
    },
    "equity_to_assets_direction": {
        "producer_field": "balance_sheet_state", "dimension": "CAPITAL_STRUCTURE", "axis": DIRECTION,
        "family": _GENERIC_PRIMITIVE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"STRENGTHENING": IMPROVING, "DETERIORATING": WORSENING, "STABLE": STABLE},
        "codes": {FAVORABLE: "BALANCE_SHEET_STRENGTHENING", ADVERSE: "BALANCE_SHEET_DETERIORATING"},
        "semantic": ("Equity/assets same-quarter YoY direction; where the engine has no ratio, its feature-store "
                     "fallback (shareholders' equity YoY trajectory, research proxy) with the same labels."),
        "policy_reason": ("A capital ratio direction. The equity-amount fallback keeps its vote because more "
                          "residual equity is more loss-absorbing capital whatever its source; total-asset "
                          "growth is size, so that fallback stays evidence only."),
    },
    "debt_to_equity_direction": {
        "producer_field": "leverage_state", "dimension": "CAPITAL_STRUCTURE", "axis": DIRECTION,
        "family": _CORPORATE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"IMPROVING": IMPROVING, "WORSENING": WORSENING, "STABLE": STABLE},
        "codes": {FAVORABLE: "DEBT_TO_EQUITY_DECREASING", ADVERSE: "DEBT_TO_EQUITY_INCREASING"},
        "semantic": ("Explicit interest-bearing debt / equity same-quarter YoY direction. A direction only: "
                     "an improving ratio never implies a safe debt level."),
        "policy_reason": "A leverage ratio direction; the leverage level stays UNAVAILABLE (no governed classifier).",
    },
    "net_working_capital_direction": {
        "producer_field": "working_capital_trajectory_state", "dimension": "SHORT_TERM_LIQUIDITY", "axis": DIRECTION,
        "family": _CORPORATE, "policy_class": RESEARCH_EVIDENCE_ONLY,
        # The absolute amount rises or falls; no polarity is asserted.
        "values": {"WORKING_CAPITAL_IMPROVING": RISING, "WORKING_CAPITAL_WORSENING": FALLING,
                   "WORKING_CAPITAL_STABLE": STABLE},
        "codes": {},
        "semantic": "Same-quarter YoY change of the absolute amount current assets minus current liabilities.",
        "policy_reason": ("Rising receivables or inventory, or falling payables, raise the amount while quality "
                          "may deteriorate, and cash composition matters. No governed quality/composition "
                          "contract exists, so the amount trajectory has no polarity and never votes."),
    },
    "current_ratio_direction": {
        "producer_field": "current_ratio_trajectory_state", "dimension": "SHORT_TERM_LIQUIDITY", "axis": DIRECTION,
        "family": _CORPORATE, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"CURRENT_RATIO_IMPROVING": IMPROVING, "CURRENT_RATIO_WORSENING": WORSENING,
                   "CURRENT_RATIO_STABLE": STABLE},
        "codes": {FAVORABLE: "CURRENT_RATIO_IMPROVING", ADVERSE: "CURRENT_RATIO_WORSENING"},
        "semantic": ("Short-term liquidity-ratio direction: same-quarter YoY change of current assets / current "
                     "liabilities."),
        "policy_reason": ("A short-term liquidity-ratio direction only: not general balance-sheet health and "
                          "never an absolute liquidity level."),
    },
    "net_working_capital_level": {
        "producer_field": "working_capital_state", "dimension": "SHORT_TERM_LIQUIDITY", "axis": LEVEL,
        "family": _CORPORATE, "policy_class": RESEARCH_EVIDENCE_ONLY,
        "values": {"POSITIVE_NET_WORKING_CAPITAL": DESCRIPTIVE_ONLY, "NEGATIVE_NET_WORKING_CAPITAL": DESCRIPTIVE_ONLY,
                   "ZERO_NET_WORKING_CAPITAL": DESCRIPTIVE_ONLY},
        "codes": {},
        "semantic": "Sign of net working capital; the engine declares it descriptive, never a healthy/avoid verdict.",
        "policy_reason": "Producer-declared descriptive sign.",
    },
    "resilience_level": {
        "producer_field": "resilience_state", "dimension": "RESILIENCE", "axis": LEVEL,
        "family": _CORPORATE, "policy_class": RESEARCH_EVIDENCE_ONLY,
        "values": {"RESILIENT": HEALTHY, "STRESSED": STRESSED},
        "codes": {},
        "semantic": "Engine composite of profitability, margin, cash and balance states; counting it would double-count them.",
        "policy_reason": "A composite of other signals; voting it would double-count them.",
    },
    "bank_asset_quality_direction": {
        "producer_field": "bank_asset_quality_state", "dimension": "BANK_ASSET_QUALITY", "axis": DIRECTION,
        "family": _BANK, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"IMPROVING": IMPROVING, "WORSENING": WORSENING, "STABLE": STABLE},
        "codes": {FAVORABLE: "BANK_ASSET_QUALITY_IMPROVING", ADVERSE: "BANK_ASSET_QUALITY_WORSENING"},
        "semantic": "NPL / customer loans same-quarter YoY direction; falling is improving (engine polarity).",
        "policy_reason": "A bank ratio direction with engine polarity; banks only.",
    },
    "bank_funding_direction": {
        "producer_field": "bank_funding_state", "dimension": "BANK_FUNDING", "axis": DIRECTION,
        "family": _BANK, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"IMPROVING": IMPROVING, "WORSENING": WORSENING, "STABLE": STABLE},
        "codes": {FAVORABLE: "BANK_FUNDING_IMPROVING", ADVERSE: "BANK_FUNDING_WORSENING"},
        "semantic": "Loans / deposits same-quarter YoY direction; falling is improving (engine polarity).",
        "policy_reason": "A bank ratio direction with engine polarity; banks only.",
    },
    "bank_efficiency_direction": {
        "producer_field": "bank_efficiency_state", "dimension": "BANK_EFFICIENCY", "axis": DIRECTION,
        "family": _BANK, "policy_class": CURRENT_DECISION_VOTE,
        "values": {"IMPROVING": IMPROVING, "WORSENING": WORSENING, "STABLE": STABLE},
        "codes": {FAVORABLE: "BANK_EFFICIENCY_IMPROVING", ADVERSE: "BANK_EFFICIENCY_WORSENING"},
        "semantic": "Cost / income same-quarter YoY direction; falling is improving (engine polarity).",
        "policy_reason": "A bank ratio direction with engine polarity; banks only.",
    },
    "securities_fvtpl_intensity": {
        "producer_field": "fvtpl_asset_intensity_trajectory_state", "dimension": "SECURITIES_COMPOSITION",
        "axis": COMPOSITION, "family": _SECURITIES, "policy_class": RESEARCH_EVIDENCE_ONLY,
        "values": {"FVTPL_ASSET_INTENSITY_RISING": RISING, "FVTPL_ASSET_INTENSITY_FALLING": FALLING,
                   "FVTPL_ASSET_INTENSITY_STABLE": STABLE},
        "codes": {},
        "semantic": "Composition trajectory; the engine asserts no polarity.",
        "policy_reason": "A composition trajectory without producer polarity.",
    },
    "securities_margin_lending_intensity": {
        "producer_field": "margin_lending_intensity_trajectory_state", "dimension": "SECURITIES_COMPOSITION",
        "axis": COMPOSITION, "family": _SECURITIES, "policy_class": RESEARCH_EVIDENCE_ONLY,
        "values": {"MARGIN_LENDING_INTENSITY_RISING": RISING, "MARGIN_LENDING_INTENSITY_FALLING": FALLING,
                   "MARGIN_LENDING_INTENSITY_STABLE": STABLE},
        "codes": {},
        "semantic": "Composition trajectory; the engine asserts no polarity.",
        "policy_reason": "A composition trajectory without producer polarity.",
    },
    "securities_brokerage_mix": {
        "producer_field": "brokerage_mix_trajectory_state", "dimension": "SECURITIES_COMPOSITION",
        "axis": COMPOSITION, "family": _SECURITIES, "policy_class": RESEARCH_EVIDENCE_ONLY,
        "values": {"BROKERAGE_MIX_RISING": RISING, "BROKERAGE_MIX_FALLING": FALLING, "BROKERAGE_MIX_STABLE": STABLE},
        "codes": {},
        "semantic": "Composition trajectory; the engine asserts no polarity.",
        "policy_reason": "A composition trajectory without producer polarity.",
    },
}

#: Levels a consumer might expect but no governed classifier provides. They stay UNAVAILABLE,
#: never inferred from a direction or from an unclassified numeric value (a raw leverage value
#: stays visible in the producer record; no threshold here makes it SAFE or STRESSED).
UNCLASSIFIED_LEVELS = {
    "CAPITAL_STRUCTURE": "NO_PRODUCER_LEVERAGE_LEVEL_CLASSIFICATION",
    "MARGINS": "NO_PRODUCER_MARGIN_LEVEL_CLASSIFICATION",
    "SHORT_TERM_LIQUIDITY": "NO_GOVERNED_ABSOLUTE_LIQUIDITY_LEVEL",
}
#: Producer states deliberately not consumed, with the reason (the artifact reports them).
NOT_CONSUMED = {
    "capital_efficiency_state": "PRODUCER_NEVER_STATE_READY_CROSS_PROVIDER_PROXIES",
}
NOT_CONSUMED_POLICY_CLASS = {"capital_efficiency_state": UNKNOWN}

_POLARITY = {HEALTHY: FAVORABLE, STRESSED: ADVERSE, IMPROVING: FAVORABLE, WORSENING: ADVERSE,
             LOSS_TO_PROFIT: FAVORABLE, LOSS_NARROWED: FAVORABLE, LOSS_WIDENED: ADVERSE, PROFIT_TO_LOSS: ADVERSE,
             ADVERSE_SIGN_TRANSITION_UNRESOLVED: ADVERSE}
DIMENSION_ORDER = ("PROFITABILITY", "GROWTH", "MARGINS", "CASH_QUALITY", "CAPITAL_STRUCTURE", "SHORT_TERM_LIQUIDITY",
                   "RESILIENCE", "BANK_ASSET_QUALITY", "BANK_FUNDING", "BANK_EFFICIENCY", "SECURITIES_COMPOSITION")


def polarity(value: Any) -> str:
    return _POLARITY.get(value, NEUTRAL)


def _quarter_end(label: Any) -> date | None:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", str(label or ""))
    if not match:
        return None
    year, month = int(match[1]), int(match[2]) * 3
    return date(year, month, calendar.monthrange(year, month)[1])


def fiscal_period_semantics(period: Any, decision_session: str | None, known_at: Any) -> dict[str, Any]:
    """Whether a quarter label read as a calendar quarter is knowable by the decision session.

    The authoritative test is knowledge time, never the label string alone. A label whose calendar
    quarter ends after the session, carried by evidence retained on or before the session, cannot
    be a calendar quarter: it is a non-calendar fiscal label known by then (its calendar period is
    unresolved -- no governed fiscal-year registry exists). Without a retained knowledge time on or
    before the session the same label fails closed as possible future information.
    """
    end = _quarter_end(period)
    known = str(known_at)[:10] if known_at else None
    session = str(decision_session)[:10] if decision_session else None
    if end is None or session is None:
        status = "NOT_A_QUARTER_LABEL_OR_NO_SESSION"
    elif end.isoformat() <= session:
        status = "CALENDAR_READING_NOT_AFTER_SESSION"
    elif known and known <= session:
        status = NON_CALENDAR_FISCAL_PERIOD
    else:
        status = "KNOWLEDGE_TIME_UNPROVEN_FAIL_CLOSED"
    return {"rule": FISCAL_PERIOD_RULE, "period_label": period, "calendar_quarter_end": end.isoformat() if end else None,
            "decision_session": session, "evidence_known_at": known, "status": status,
            "calendar_period": "UNRESOLVED_NO_GOVERNED_FISCAL_YEAR_REGISTRY" if status == NON_CALENDAR_FISCAL_PERIOD else None}


def evidence_known_at(record: Mapping[str, Any] | None) -> str | None:
    """The retained knowledge time of a Financial V2 record's period semantics (its lineage)."""
    lineage = (record or {}).get("lineage") if isinstance((record or {}).get("lineage"), Mapping) else {}
    identities = lineage.get("source_identities") if isinstance(lineage.get("source_identities"), Mapping) else {}
    value = identities.get("period_semantics_knowledge_time")
    return str(value) if value else None


def policy_epoch(record: Mapping[str, Any] | None) -> str:
    """The fundamental decision-policy epoch of any Integrated Decision record (never rewritten).

    Explicit on records from this epoch on; resolved from the record's own shape before it: a
    synthesis carrying ``signal_policy`` (5729c52), a synthesis without it (66d0fc0), or none at
    all (the legacy reader).
    """
    record = record if isinstance(record, Mapping) else {}
    explicit = record.get("fundamental_decision_policy_version")
    if isinstance(explicit, str) and explicit:
        return explicit
    synthesis = record.get("fundamental_synthesis")
    if isinstance(synthesis, Mapping):
        return str(synthesis.get("signal_policy") or CONSUMPTION_POLICY_EPOCH)
    return LEGACY_POLICY_EPOCH


def epochs_comparable(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> bool:
    """Whether two records' fundamental states were produced under the same decision policy."""
    return policy_epoch(previous) == policy_epoch(current)


def policy_table() -> dict[str, dict[str, Any]]:
    """The static state contract: every producer state with its policy class and reason."""
    table = {spec["producer_field"]: {"signal_id": signal_id, "dimension": spec["dimension"], "axis": spec["axis"],
                                      "family": spec["family"], "policy_class": spec["policy_class"],
                                      "policy_reason": spec["policy_reason"]}
             for signal_id, spec in SIGNALS.items()}
    for field, reason in NOT_CONSUMED.items():
        table[field] = {"signal_id": None, "dimension": None, "axis": None, "family": None,
                        "policy_class": NOT_CONSUMED_POLICY_CLASS[field], "policy_reason": reason}
    return dict(sorted(table.items()))


def _transition_code(value: str, basis: str | None) -> str | None:
    if value == LOSS_TO_PROFIT:
        return "EARNINGS_TURNAROUND_DETECTED" if basis in TURNAROUND_BASES else "EARNINGS_LOSS_TO_PROFIT_SEQUENTIAL"
    return {LOSS_NARROWED: "EARNINGS_LOSS_NARROWING", LOSS_WIDENED: "EARNINGS_LOSS_WIDENING",
            PROFIT_TO_LOSS: "EARNINGS_TURNED_TO_LOSS",
            ADVERSE_SIGN_TRANSITION_UNRESOLVED: "EARNINGS_ADVERSE_SIGN_TRANSITION"}.get(value)


def _freshness(period: Any, session: str | None, known_at: Any = None) -> tuple[str, list[str], int | None]:
    if session is None:
        return NOT_EVALUATED, [], None
    envelope = classify_financial_period_freshness(source_period=period, decision_session=session,
                                                   maximum_completed_quarter_lag=MAX_COMPLETED_QUARTER_LAG)
    reasons = list(envelope["reason_codes"])
    if "FINANCIAL_PERIOD_AFTER_DECISION_SESSION" in reasons:
        fiscal = fiscal_period_semantics(period, session, known_at)
        if fiscal["status"] == NON_CALENDAR_FISCAL_PERIOD:
            return NON_CALENDAR_FISCAL_PERIOD, [NON_CALENDAR_FISCAL_PERIOD], None
        reasons.append(fiscal["status"])
    return envelope["freshness_status"], reasons, envelope["completed_quarter_lag"]


def _applicability(family: str, analysis_family: Any, issuer_type: Any) -> str:
    issuer = str(issuer_type or "unknown").lower()
    if family == _BANK:
        return APPLICABLE if issuer == "bank" else UNRESOLVED if issuer == "unknown" else NON_APPLICABLE
    if family == _SECURITIES:
        return APPLICABLE if issuer == "securities" else UNRESOLVED if issuer == "unknown" else NON_APPLICABLE
    if analysis_family == _INDUSTRIAL:
        return APPLICABLE
    if analysis_family == _GENERIC or issuer == "unknown":
        return UNRESOLVED
    return NON_APPLICABLE


def _consumption_class(policy_class: str, *, role: str, applicability: str, exclusion: str | None,
                       non_vote_reason: str | None) -> str:
    """The per-record class: the static policy class narrowed by entity, semantics and period."""
    if applicability == NON_APPLICABLE:
        return NON_APPLICABLE
    if exclusion is not None:
        return UNKNOWN
    if role == EVIDENCE_ONLY or non_vote_reason is not None:
        return RESEARCH_EVIDENCE_ONLY
    return policy_class


def _non_vote_reason(*, axis: str, freshness: str, applicability: str, basis: str | None) -> str | None:
    """Why usable decision-grade evidence does not vote (period, entity, then transition basis)."""
    if freshness == NON_CALENDAR_FISCAL_PERIOD:
        return FISCAL_CALENDAR_UNRESOLVED_NOT_A_VOTE
    if freshness not in _VOTING_FRESHNESS:
        return STALE_NOT_A_CURRENT_VOTE
    if applicability == UNRESOLVED:
        return ENTITY_UNRESOLVED_NOT_A_VOTE
    if axis == TRANSITION and basis not in DECISION_TRANSITION_BASES:
        return SEQUENTIAL_TRANSITION_NOT_A_VOTE if basis == "QOQ_STANDALONE" else TRANSITION_BASIS_UNRESOLVED_NOT_A_VOTE
    return None


def _signal(signal_id: str, *, producer_value: Any, value: str, applicability: str, qualification: Any,
            source_features: Sequence[str], period: Any, session: str | None, basis: str | None = None,
            role: str | None = None, evidence_only_reason: str | None = None, exclusion: str | None = None,
            observed: Any = None, research_when_unresolved: bool = False, known_at: Any = None) -> dict[str, Any]:
    """One signal. ``exclusion`` means the value is not usable evidence at all (entity, vocabulary,
    availability, period or an undefined sign); ``evidence_only_reason`` means valid evidence this
    record may never vote with; ``non_vote_reason`` names why otherwise decision-grade evidence
    does not vote (a stale or fiscal-unresolved period, an unresolved entity family, a sequential
    transition basis). ``research_when_unresolved`` keeps a generic primitive of an unresolved
    entity as research evidence (it never votes)."""
    spec = SIGNALS[signal_id]
    freshness, freshness_reasons, lag = _freshness(period, session, known_at)
    role = role or _ROLE[spec["policy_class"]]
    reasons: list[str] = list(freshness_reasons)
    if exclusion is None:
        if applicability == NON_APPLICABLE:
            exclusion = "ENTITY_NOT_APPLICABLE"
        elif applicability == UNRESOLVED and not research_when_unresolved:
            exclusion = "ENTITY_UNRESOLVED"
        elif value == NONE_OBSERVED:
            exclusion = "NO_TRANSITION_OBSERVED"
        elif value == UNKNOWN:
            exclusion = "PRODUCER_VALUE_OUTSIDE_CONTRACT_VOCABULARY"
        elif value == UNAVAILABLE:
            exclusion = "PRODUCER_STATE_UNAVAILABLE"
        elif freshness not in (CURRENT, STALE_BUT_RESEARCH_USABLE, NOT_EVALUATED, NON_CALENDAR_FISCAL_PERIOD):
            exclusion = "FINANCIAL_PERIOD_UNAVAILABLE_FOR_DECISION"
    if exclusion:
        reasons.append(exclusion)
    if evidence_only_reason:
        reasons.append(evidence_only_reason)
    usable = exclusion is None
    non_vote = (_non_vote_reason(axis=spec["axis"], freshness=freshness, applicability=applicability, basis=basis)
                if usable and role == DECISION else None)
    if non_vote:
        reasons.append(non_vote)
    pol = polarity(value)
    code = None
    if pol != NEUTRAL:
        code = _transition_code(value, basis) if spec["axis"] == TRANSITION else spec["codes"].get(pol)
    return {
        "signal_id": signal_id,
        "dimension": spec["dimension"],
        "axis": spec["axis"],
        "producer_field": spec["producer_field"],
        "producer_value": producer_value,
        "value": value,
        **({"observed": observed} if observed is not None else {}),
        "polarity": pol,
        "role": role,
        "policy_class": spec["policy_class"],
        "consumption_class": _consumption_class(spec["policy_class"], role=role, applicability=applicability,
                                                exclusion=exclusion, non_vote_reason=non_vote),
        "applicability": applicability,
        "fitness": {
            "qualification": qualification,
            "source_features": list(source_features),
            "as_of_period": period,
            "basis": basis,
            "freshness": freshness,
            "completed_quarter_lag": lag,
        },
        "research_usable": usable,
        "decision_eligible": role == DECISION and usable and non_vote is None,
        "non_vote_reason": non_vote,
        "exclusion": exclusion,
        "reason_code": code,
        "reason_codes": sorted(set(reasons)),
    }


def _ff(record: Mapping[str, Any], feature: str) -> Mapping[str, Any]:
    fitness = record.get("feature_fitness") if isinstance(record.get("feature_fitness"), Mapping) else {}
    return fitness.get(feature) or {}


def _usable(record: Mapping[str, Any], feature: str) -> bool:
    return _ff(record, feature).get("fitness") in _USABLE_FEATURE_FITNESS


def _map(signal_id: str, producer_value: Any) -> str:
    if producer_value in (None, "UNAVAILABLE", "WORKING_CAPITAL_UNAVAILABLE", "NOT_APPLICABLE"):
        return UNAVAILABLE
    return SIGNALS[signal_id]["values"].get(producer_value, UNKNOWN)


def _latest(periods: Sequence[Any]) -> Any:
    concrete = sorted(str(period) for period in periods if period)
    return concrete[-1] if concrete else None


def entity_decision_applicability(record: Mapping[str, Any] | None) -> str:
    """Which Financial V2 signal family may decide this record (never widened by field presence).

    Industrial issuers: the corporate contract. Banks and securities firms (limited family): only
    their specialist signals. Insurers and finance companies (limited family): no decision signal
    family. An unclassified/generic record: unresolved -- its fields stay research evidence and
    never vote, however many happen to exist.
    """
    record = record or {}
    family, issuer = record.get("analysis_family"), str(record.get("issuer_type") or "unknown").lower()
    if family == _INDUSTRIAL:
        return ENTITY_DECISION_APPLICABLE
    if family == _GENERIC or issuer == "unknown":
        return ENTITY_FAMILY_UNRESOLVED
    if issuer in ("bank", "securities"):
        return ENTITY_SPECIALIST_SIGNALS_ONLY
    return ENTITY_NO_DECISION_SIGNAL_FAMILY


def financial_v2_signals(record: Mapping[str, Any], *, decision_session: str | None) -> list[dict[str, Any]]:
    """Every consumed Financial V2 compact state as an explicit signal (see ``SIGNALS``)."""
    family, issuer = record.get("analysis_family"), record.get("issuer_type")
    known_at = evidence_known_at(record)
    out: list[dict[str, Any]] = []

    def simple(signal_id: str, source: str, *, period_source: str | None = None, **extra: Any) -> None:
        spec = SIGNALS[signal_id]
        producer_value = record.get(spec["producer_field"])
        out.append(_signal(signal_id, producer_value=producer_value, value=_map(signal_id, producer_value),
                           applicability=_applicability(spec["family"], family, issuer),
                           qualification=_ff(record, source).get("fitness"), source_features=[source],
                           period=_ff(record, period_source or source).get("as_of_period"),
                           session=decision_session, known_at=known_at, **extra))

    # PROFITABILITY level. TURNAROUND_CONTEXT is the engine's transition flag in this field: the
    # level is then not asserted and the transition is read below.
    producer_value = record.get("profitability_state")
    out.append(_signal(
        "profitability_level", producer_value=producer_value,
        value=UNAVAILABLE if producer_value == "TURNAROUND_CONTEXT" else _map("profitability_level", producer_value),
        applicability=_applicability(_GENERIC_PRIMITIVE, family, issuer),
        qualification=_ff(record, "net_income_sign").get("fitness"), source_features=["net_income_sign"],
        period=_ff(record, "net_income_sign").get("as_of_period"), session=decision_session,
        exclusion="PROFITABILITY_STATE_IS_TURNAROUND_TRANSITION_CONTEXT" if producer_value == "TURNAROUND_CONTEXT" else None,
        research_when_unresolved=True, known_at=known_at))
    profitability_value = out[-1]["value"]
    profitability_period = out[-1]["fitness"]["as_of_period"]

    # PROFITABILITY transition: basis and source come from the feature that carries the same
    # engine-classified sign transition (a comparable basis first); sign transitions never become growth.
    transition = record.get("earnings_turnaround_state")
    if producer_value == "TURNAROUND_CONTEXT" and transition in (None, "UNAVAILABLE"):
        transition = LOSS_TO_PROFIT
    source = next((feature for feature in _NI_TRANSITION_SOURCE_ORDER
                   if transition and _ff(record, feature).get("semantic_transition") == transition), None)
    if producer_value == "TURNAROUND_CONTEXT" and source is None:
        source = "net_income_same_quarter_yoy"
    value = _map("earnings_transition", transition)
    if value == UNAVAILABLE and any(_usable(record, feature) for feature in _NI_TRANSITION_FEATURES):
        value = NONE_OBSERVED
    basis = (_ff(record, source).get("growth_basis") or ("SAME_QUARTER_YOY" if source == "net_income_same_quarter_yoy" else None)
             ) if source else ("UNRESOLVED" if value not in (UNAVAILABLE, NONE_OBSERVED, UNKNOWN) else None)
    out.append(_signal("earnings_transition", producer_value=record.get("earnings_turnaround_state"), value=value,
                       applicability=_applicability(_CORPORATE, family, issuer),
                       qualification=_ff(record, source).get("fitness") if source else None,
                       source_features=[source] if source else list(_NI_TRANSITION_FEATURES),
                       period=_ff(record, source).get("as_of_period") if source else None,
                       session=decision_session, basis=basis, known_at=known_at))

    # GROWTH: the engine's consensus over positive-base growth features only.
    growth_sources = [feature for feature in _GROWTH_CONSENSUS_FEATURES
                      if _ff(record, feature).get("fitness") == "READY" and not _ff(record, feature).get("semantic_transition")]
    growth_value = _map("growth_direction", record.get("growth_state"))
    out.append(_signal("growth_direction", producer_value=record.get("growth_state"), value=growth_value,
                       applicability=_applicability(_CORPORATE, family, issuer),
                       qualification="READY" if growth_sources else None,
                       source_features=growth_sources or list(_GROWTH_CONSENSUS_FEATURES),
                       period=_latest([_ff(record, feature).get("as_of_period") for feature in growth_sources]),
                       session=decision_session, known_at=known_at,
                       exclusion=("ENGINE_GROWTH_SOURCES_WITHOUT_CONSENSUS"
                                  if growth_value == UNAVAILABLE and len(growth_sources) > 1 else None)))

    # MARGINS: the net-margin direction carries no period of its own; it is the change into the
    # current net-margin observation, whose period it takes.
    simple("net_margin_direction", "net_margin_direction", period_source="net_margin")
    simple("gross_margin_direction", "gross_margin_direction")

    # CASH_QUALITY level: CFO/NI sign means cash quality only over positive same-period earnings.
    cash_source = "cfo_to_net_income_ttm" if _ff(record, "cfo_to_net_income_ttm").get("fitness") == "READY" else "cfo_to_net_income"
    cash_value = _map("cash_conversion_level", record.get("cash_conversion_state"))
    cash_period = _ff(record, cash_source).get("as_of_period")
    cash_exclusion = None
    if cash_value in (HEALTHY, STRESSED):
        if cash_source == "cfo_to_net_income_ttm":
            cash_exclusion = "CASH_CONVERSION_TTM_EARNINGS_SIGN_NOT_EXPOSED"
        elif not (profitability_value == HEALTHY and cash_period and cash_period == profitability_period):
            cash_exclusion = "CASH_CONVERSION_SIGN_UNDEFINED_WITHOUT_POSITIVE_SAME_PERIOD_EARNINGS"
    out.append(_signal("cash_conversion_level", producer_value=record.get("cash_conversion_state"), value=cash_value,
                       applicability=_applicability(_CORPORATE, family, issuer),
                       qualification=_ff(record, cash_source).get("fitness"), source_features=[cash_source],
                       period=cash_period, session=decision_session, exclusion=cash_exclusion, known_at=known_at))
    simple("free_cash_flow_proxy_direction", "free_cash_flow_proxy_direction")

    # CAPITAL_STRUCTURE: equity/assets (or its feature-store equity fallback) and explicit D/E.
    balance_value = _map("equity_to_assets_direction", record.get("balance_sheet_state"))
    if _ff(record, "equity_to_assets_direction").get("fitness") == "READY":
        balance_source, balance_role, balance_reason = "equity_to_assets_direction", None, None
    elif _ff(record, "equity_yoy").get("fitness") == "RESEARCH_PROXY" and _ff(record, "equity_yoy").get("semantic_transition"):
        balance_source, balance_role, balance_reason = "equity_yoy", None, None
    elif balance_value != UNAVAILABLE and _ff(record, "assets_yoy").get("fitness") == "RESEARCH_PROXY":
        # Total-asset growth is balance-sheet size, never balance-sheet strength.
        balance_source, balance_role, balance_reason = "assets_yoy", EVIDENCE_ONLY, "ASSET_BASE_GROWTH_IS_NOT_BALANCE_SHEET_STRENGTH"
    else:
        balance_source, balance_role, balance_reason = "equity_to_assets_direction", None, None
    out.append(_signal("equity_to_assets_direction", producer_value=record.get("balance_sheet_state"), value=balance_value,
                       applicability=_applicability(_GENERIC_PRIMITIVE, family, issuer),
                       qualification=_ff(record, balance_source).get("fitness"), source_features=[balance_source],
                       period=_ff(record, balance_source).get("as_of_period"), session=decision_session,
                       role=balance_role, evidence_only_reason=balance_reason, research_when_unresolved=True,
                       known_at=known_at))
    leverage_value = _map("debt_to_equity_direction", record.get("leverage_state"))
    if _ff(record, "debt_to_equity_direction").get("fitness") == "READY" or leverage_value == UNAVAILABLE:
        simple("debt_to_equity_direction", "debt_to_equity_direction")
    else:
        # The engine's fallback re-reads equity/assets: the same measurement, never a second one.
        out.append(_signal("debt_to_equity_direction", producer_value=record.get("leverage_state"), value=leverage_value,
                           applicability=_applicability(_CORPORATE, family, issuer),
                           qualification=_ff(record, "equity_to_assets_direction").get("fitness"),
                           source_features=["equity_to_assets_direction"],
                           period=_ff(record, "equity_to_assets_direction").get("as_of_period"), session=decision_session,
                           role=EVIDENCE_ONLY, evidence_only_reason="LEVERAGE_STATE_IS_EQUITY_TO_ASSETS_FALLBACK_DUPLICATE",
                           known_at=known_at))

    # SHORT_TERM_LIQUIDITY: the current-ratio direction votes; the amount trajectory and sign are evidence.
    simple("net_working_capital_direction", "net_working_capital_direction")
    simple("current_ratio_direction", "current_ratio_direction")
    simple("net_working_capital_level", "net_working_capital", observed=record.get("working_capital_state"))

    # Composite and specialist families.
    simple("resilience_level", "net_income_sign")
    for signal_id, source in (("bank_asset_quality_direction", "bank_npl_ratio"), ("bank_funding_direction", "bank_ldr"),
                              ("bank_efficiency_direction", "bank_cir")):
        producer_value = record.get(SIGNALS[signal_id]["producer_field"])
        out.append(_signal(signal_id, producer_value=producer_value,
                           value=UNKNOWN if producer_value == "AVAILABLE" else _map(signal_id, producer_value),
                           applicability=_applicability(_BANK, family, issuer),
                           qualification=_ff(record, source).get("fitness"), source_features=[source],
                           period=_ff(record, source).get("as_of_period"), session=decision_session, known_at=known_at,
                           exclusion="SINGLE_PERIOD_NO_TRAJECTORY" if producer_value == "AVAILABLE" else None))
    for signal_id, source in (("securities_fvtpl_intensity", "fvtpl_asset_intensity"),
                              ("securities_margin_lending_intensity", "margin_lending_asset_intensity"),
                              ("securities_brokerage_mix", "brokerage_revenue_mix")):
        simple(signal_id, source)
    return out


def operational_bridge_signals(record: Mapping[str, Any], *, decision_session: str | None) -> list[dict[str, Any]]:
    """The operational bridge's governed ``financial_context`` as explicit signals.

    The bridge reports a loss->profit same-quarter transition as ``TURNAROUND`` and a
    turned-to-loss / loss-widened transition as growth ``CONTRACTING``; both are transitions here,
    resolved from the bridge's own preserved source feature where it is present.
    """
    context = record.get("financial_context") if isinstance(record.get("financial_context"), Mapping) else record
    usable = record.get("usable_features") if isinstance(record.get("usable_features"), Mapping) else {}
    profit, earnings = usable.get("profit_state") or {}, usable.get("net_income_same_period_yoy") or {}
    qualification = context.get("fitness") or "OPERATIONAL_PROVIDER_RESEARCH_ONLY"
    level_value = _map("profitability_level", context.get("profitability_state"))
    out = [_signal("profitability_level", producer_value=context.get("profitability_state"), value=level_value,
                   applicability=APPLICABLE, qualification=qualification, source_features=["profit_state"],
                   period=_latest(profit.get("input_periods") or []), session=decision_session)]
    categorical = earnings.get("categorical_state")
    if context.get("earnings_turnaround_state") == "TURNAROUND":
        transition = LOSS_TO_PROFIT
    elif context.get("growth_state") == "CONTRACTING":
        transition = {"TURNED_TO_LOSS": PROFIT_TO_LOSS, "LOSS_WIDENED": LOSS_WIDENED}.get(categorical, ADVERSE_SIGN_TRANSITION_UNRESOLVED)
    else:
        transition = UNAVAILABLE
    out.append(_signal("earnings_transition",
                       producer_value={"earnings_turnaround_state": context.get("earnings_turnaround_state"),
                                       "growth_state": context.get("growth_state")},
                       value=transition, applicability=APPLICABLE, qualification=qualification,
                       source_features=["net_income_same_period_yoy"],
                       period=_latest(earnings.get("input_periods") or []) or _latest(profit.get("input_periods") or []),
                       session=decision_session, basis="SAME_QUARTER_YOY" if transition != UNAVAILABLE else None))
    return out


def _is_stale(signal: Mapping[str, Any]) -> bool:
    return signal.get("non_vote_reason") == STALE_NOT_A_CURRENT_VOTE


def _current_period(signal: Mapping[str, Any]) -> bool:
    """A current (or not session-evaluated) period -- read from the signal's own freshness, so a
    synthesis written before ``non_vote_reason`` existed resolves identically."""
    return (signal.get("fitness") or {}).get("freshness") in _VOTING_FRESHNESS


def _resolve(signals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One dimension/axis: only current decision signals vote; disagreement is shown, never voted."""
    used = [signal for signal in signals if signal["decision_eligible"]]
    polarities = {signal["polarity"] for signal in used} - {NEUTRAL}
    if not used:
        value, vote = None, None
    elif not polarities:
        value, vote = used[0]["value"] if len({signal["value"] for signal in used}) == 1 else STABLE, None
    elif len(polarities) == 1:
        vote = next(iter(polarities))
        value = next(signal["value"] for signal in used if signal["polarity"] == vote)
    else:
        value, vote = MIXED, None
    return {"value": value, "vote": vote, "used": sorted(signal["signal_id"] for signal in used),
            "stale_research_evidence": sorted(signal["signal_id"] for signal in signals
                                              if signal["research_usable"] and signal["role"] == DECISION and _is_stale(signal))}


def _history(signal: Mapping[str, Any]) -> dict[str, Any]:
    fitness = signal["fitness"]
    return {"value": signal["value"], "as_of_period": fitness["as_of_period"], "basis": fitness["basis"],
            "completed_quarter_lag": fitness["completed_quarter_lag"], "freshness": fitness["freshness"]}


def _observation(signal: Mapping[str, Any]) -> dict[str, Any]:
    return {**_history(signal), "non_vote_reason": signal.get("non_vote_reason")}


def _group_votes(resolved: Mapping[tuple[str, str], Mapping[str, Any]],
                 signals: Sequence[Mapping[str, Any]]) -> tuple[set[tuple[str, str]], list[dict[str, Any]]]:
    """One vote per balance-sheet observation (``VOTE_GROUPS``); no weight, no score.

    Agreeing members measured on a shared balance-sheet observation are one vote, counted on the
    group's ``counted`` member; opposing members both stay; distinct observations both count.
    """
    folded: set[tuple[str, str]] = set()
    records: list[dict[str, Any]] = []
    for group in VOTE_GROUPS:
        members = group["members"]
        votes = {member: (resolved.get(member) or {}).get("vote") for member in members}
        if any(vote is None for vote in votes.values()):
            continue
        periods = {member: {s["fitness"]["as_of_period"] for s in signals
                            if (s["dimension"], s["axis"]) == member and s["decision_eligible"]
                            and s["signal_id"] in resolved[member]["used"] and s["fitness"]["as_of_period"]}
                   for member in members}
        shared = set.intersection(*periods.values()) if periods else set()
        label = {member: f"{member[0]}.{member[1]}" for member in members}
        entry: dict[str, Any] = {
            "group": group["group"], "rule": VOTE_GROUPING_RULE, "members": [label[m] for m in members],
            "member_votes": {label[m]: votes[m] for m in members},
            "member_observations": {label[m]: sorted(periods[m]) for m in members},
        }
        if len(set(votes.values())) > 1:
            entry["outcome"] = "OPPOSING_DIMENSIONS_PRESERVED"
        elif shared:
            counted = group["counted"]
            entry.update(outcome="SAME_OBSERVATION_AGREEING_COUNTED_ONCE", counted=label[counted],
                         folded=[label[m] for m in members if m != counted], shared_observation=sorted(shared))
            folded.update(m for m in members if m != counted)
        else:
            entry["outcome"] = "DISTINCT_OBSERVATIONS_COUNTED_SEPARATELY"
        records.append(entry)
    return folded, records


def _evidence_availability(signals: Sequence[Mapping[str, Any]], state: str, entity: str | None) -> dict[str, Any]:
    """Whether qualified fundamental evidence exists, apart from whether the current direction is
    sufficient, as the five-state ``fundamental_evidence_availability``.

    CURRENT_DIRECTIONAL: a direction is established. CURRENT_NON_DIRECTIONAL: current applicable
    evidence exists but establishes no direction (neutral, conflicting, or a sequential
    observation). STALE_ONLY: only non-current evidence (stale beyond the window, or a fiscal label
    whose calendar period is unresolved). NOT_APPLICABLE_ENTITY: the entity family is not decision-
    applicable (unresolved, or no decision signal family); its evidence stays research evidence.
    ABSENT: no qualified fundamental evidence at all.
    """
    evidence = [s for s in signals if s["research_usable"] and s["role"] == DECISION]
    favorable = sorted({s["signal_id"] for s in evidence if s["polarity"] == FAVORABLE})
    adverse = sorted({s["signal_id"] for s in evidence if s["polarity"] == ADVERSE})
    applicable = [s for s in evidence if s["applicability"] == APPLICABLE]
    current = [s for s in applicable if _current_period(s)]
    non_current = [s for s in applicable if not _current_period(s)]
    gated = [s for s in evidence if s["applicability"] == UNRESOLVED]
    if state != FUNDAMENTAL_INSUFFICIENT:
        five = CURRENT_DIRECTIONAL
    elif current:
        five = CURRENT_NON_DIRECTIONAL
    elif non_current:
        five = STALE_ONLY
    elif gated or entity in (ENTITY_FAMILY_UNRESOLVED, ENTITY_NO_DECISION_SIGNAL_FAMILY, ENTITY_SPECIALIST_SIGNALS_ONLY):
        five = NOT_APPLICABLE_ENTITY
    else:
        five = ABSENT
    return {
        "state": AVAILABLE if evidence else UNAVAILABLE,
        "fundamental_evidence_availability": five,
        "rule": EVIDENCE_AVAILABILITY_RULE,
        "five_state_rule": FIVE_STATE_AVAILABILITY_RULE,
        "entity_decision_applicability": entity,
        "current_signals": sorted(s["signal_id"] for s in evidence if s["decision_eligible"]),
        "current_non_voting_signals": sorted(s["signal_id"] for s in current if not s["decision_eligible"]),
        "stale_research_signals": sorted(s["signal_id"] for s in non_current),
        "entity_gated_research_signals": sorted(s["signal_id"] for s in gated),
        "favorable_signals": favorable, "adverse_signals": adverse,
        "polarity": (MIXED if favorable and adverse else ADVERSE if adverse else FAVORABLE if favorable
                     else NEUTRAL if evidence else None),
        "directional_state": state,
        "directional_sufficiency": "INSUFFICIENT" if state == FUNDAMENTAL_INSUFFICIENT else "SUFFICIENT",
    }


def _risk_level(signals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``fundamental_risk_level`` from qualified LEVEL evidence only -- never from a direction.

    Per level dimension the current observation supersedes a non-current one; known adverse
    evidence that is not current stays known (ADVERSE_LEVEL_KNOWN_NOT_CURRENT), never unknown. No
    level is ever called healthy: leverage, margin and liquidity levels have no governed classifier
    and are reported unassessed, and the net-working-capital sign stays a descriptive observation.
    """
    dimensions: dict[str, Any] = {}
    for dimension in _RISK_LEVEL_DIMENSIONS:
        candidates = [s for s in signals if s["dimension"] == dimension and s["axis"] == LEVEL and s["research_usable"]
                      and s["role"] == DECISION and s["polarity"] in (FAVORABLE, ADVERSE)
                      and s["applicability"] != NON_APPLICABLE]
        current = [s for s in candidates if _current_period(s)]
        chosen = current or candidates
        if not chosen:
            continue
        dimensions[dimension] = {
            "polarity": ADVERSE if any(s["polarity"] == ADVERSE for s in chosen) else FAVORABLE,
            "currency": "CURRENT" if current else "NOT_CURRENT",
            "signals": sorted(s["signal_id"] for s in chosen),
            "values": sorted({s["value"] for s in chosen}),
            "as_of_period": _latest([s["fitness"]["as_of_period"] for s in chosen]),
            "freshness": sorted({s["fitness"]["freshness"] for s in chosen}),
        }
    adverse = sorted(d for d, entry in dimensions.items() if entry["polarity"] == ADVERSE)
    constructive = sorted(d for d, entry in dimensions.items() if entry["polarity"] == FAVORABLE)
    if any(dimensions[d]["currency"] == "CURRENT" for d in adverse):
        state = ADVERSE_LEVEL_CURRENT
    elif adverse:
        state = ADVERSE_LEVEL_KNOWN_NOT_CURRENT
    elif constructive:
        state = NO_QUALIFIED_ADVERSE_LEVEL
    else:
        state = LEVEL_UNKNOWN
    descriptive = {s["signal_id"]: {"observed": s.get("observed"), "as_of_period": s["fitness"]["as_of_period"],
                                    "freshness": s["fitness"]["freshness"], "polarity_asserted": False}
                   for s in signals if s["axis"] == LEVEL and s["research_usable"] and s["role"] == EVIDENCE_ONLY
                   and s["value"] == DESCRIPTIVE_ONLY}
    return {
        "state": state,
        "rule": RISK_LEVEL_RULE,
        "level_dimensions": dimensions,
        "adverse_level_dimensions": adverse,
        "constructive_level_dimensions": constructive,
        "constructive_current_level_without_adverse": bool(not adverse and any(
            dimensions[d]["currency"] == "CURRENT" for d in constructive)),
        "descriptive_level_observations": dict(sorted(descriptive.items())),
        "unassessed_level_dimensions": dict(sorted(UNCLASSIFIED_LEVELS.items())),
        "excluded_level_signals": {"resilience_level": "ENGINE_COMPOSITE_READS_MARGIN_AND_BALANCE_SHEET_DIRECTIONS"},
        "derived_from_direction": False,
        "healthy_level_asserted": False,
    }


def risk_level_of_record(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """``fundamental_risk_level`` of any Integrated Decision record, never rewritten: its own field,
    else derived from the signals its synthesis retained (66d0fc0 onward), else LEVEL_UNKNOWN (a
    legacy record carries no qualified level evidence, so none is inferred from its direction)."""
    record = record if isinstance(record, Mapping) else {}
    if isinstance(record.get("fundamental_risk_level"), Mapping):
        return dict(record["fundamental_risk_level"])
    synthesis = record.get("fundamental_synthesis")
    if isinstance(synthesis, Mapping):
        if isinstance(synthesis.get("fundamental_risk_level"), Mapping):
            return dict(synthesis["fundamental_risk_level"])
        return _risk_level([s for s in synthesis.get("signals") or [] if isinstance(s, Mapping)])
    return _risk_level([])


def evidence_availability_of_record(record: Mapping[str, Any] | None) -> str:
    """The five-state availability of any Integrated Decision record, never rewritten: its own
    field, else derived from its retained synthesis, else from the legacy direction alone."""
    record = record if isinstance(record, Mapping) else {}
    if record.get("fundamental_evidence_availability") in EVIDENCE_AVAILABILITY_STATES:
        return record["fundamental_evidence_availability"]
    synthesis = record.get("fundamental_synthesis")
    state = record.get("fundamental_state") or FUNDAMENTAL_INSUFFICIENT
    if isinstance(synthesis, Mapping):
        if synthesis.get("fundamental_evidence_availability") in EVIDENCE_AVAILABILITY_STATES:
            return synthesis["fundamental_evidence_availability"]
        signals = [s for s in synthesis.get("signals") or [] if isinstance(s, Mapping)]
        return _evidence_availability(signals, state, synthesis.get("entity_decision_applicability"))[
            "fundamental_evidence_availability"]
    return CURRENT_DIRECTIONAL if state != FUNDAMENTAL_INSUFFICIENT else ABSENT


def synthesize(signals: Sequence[Mapping[str, Any]], *, dialect: str | None,
               decision_session: str | None, status: Any, entity: str | None = None) -> dict[str, Any]:
    """Multi-dimensional fundamental synthesis plus the compatible ``fundamental_state``."""
    by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for signal in signals:
        by_key.setdefault((signal["dimension"], signal["axis"]), []).append(signal)
    resolved = {key: _resolve(group) for key, group in by_key.items()}
    folded, vote_groups = _group_votes(resolved, signals)

    def axis_value(dimension: str, axis: str) -> Any:
        return (resolved.get((dimension, axis)) or {}).get("value")

    # Counted votes: one per dimension/axis, and one per balance-sheet observation.
    favorable = sorted(f"{d}.{a}" for (d, a), r in resolved.items() if r["vote"] == FAVORABLE and (d, a) not in folded)
    adverse = sorted(f"{d}.{a}" for (d, a), r in resolved.items() if r["vote"] == ADVERSE and (d, a) not in folded)
    transitions = by_key.get(("PROFITABILITY", TRANSITION), [])
    transition = next((s for s in transitions if s["decision_eligible"]), None)
    shown_transition = transition or next((s for s in transitions if s["research_usable"]), None)
    turnaround = bool(transition and transition["value"] == LOSS_TO_PROFIT and transition["fitness"]["basis"] in TURNAROUND_BASES
                      and transition["fitness"]["freshness"] in TURNAROUND_FRESHNESS)
    gate = [label for label, hit in (
        ("PROFITABILITY.LEVEL=STRESSED", axis_value("PROFITABILITY", LEVEL) == STRESSED),
        ("GROWTH.DIRECTION=WORSENING", axis_value("GROWTH", DIRECTION) == WORSENING),
        ("CAPITAL_STRUCTURE.DIRECTION=WORSENING", axis_value("CAPITAL_STRUCTURE", DIRECTION) == WORSENING),
    ) if hit]
    drivers = [label for label, hit in (
        ("GROWTH.DIRECTION=IMPROVING", axis_value("GROWTH", DIRECTION) == IMPROVING),
        ("MARGINS.DIRECTION=IMPROVING", axis_value("MARGINS", DIRECTION) == IMPROVING),
        ("SHORT_TERM_LIQUIDITY.DIRECTION=IMPROVING", axis_value("SHORT_TERM_LIQUIDITY", DIRECTION) == IMPROVING),
    ) if hit]
    # The standing Integrated Decision fundamental policy, unchanged, over counted current votes.
    if turnaround:
        state = FUNDAMENTAL_TURNAROUND
    elif len(adverse) > len(favorable) and gate:
        state = FUNDAMENTAL_DETERIORATING
    elif favorable and not adverse:
        state = FUNDAMENTAL_IMPROVING if drivers else FUNDAMENTAL_STABLE
    elif favorable and adverse:
        state = FUNDAMENTAL_MIXED
    elif axis_value("PROFITABILITY", LEVEL) == HEALTHY:
        state = FUNDAMENTAL_STABLE
    else:
        state = FUNDAMENTAL_INSUFFICIENT

    counted = [s for s in signals if s["decision_eligible"]
               and s["signal_id"] in resolved[(s["dimension"], s["axis"])]["used"] and s["reason_code"]]
    supports = list(dict.fromkeys(s["reason_code"] for s in counted if s["polarity"] == FAVORABLE))
    counters = list(dict.fromkeys(s["reason_code"] for s in counted if s["polarity"] == ADVERSE))
    present = [s for s in signals if s["value"] not in (UNAVAILABLE, NONE_OBSERVED)]
    stale_evidence = [s for s in present if s["research_usable"] and s["role"] == DECISION and _is_stale(s)]
    # Valid decision-grade evidence that does not vote for a reason other than a stale period: a
    # fiscal label with an unresolved calendar period, an unresolved entity family, a sequential
    # or unresolved transition basis. Visible, never a vote.
    observations = [s for s in present if s["research_usable"] and s["role"] == DECISION
                    and s.get("non_vote_reason") and not _is_stale(s)]

    def ids(predicate: Any) -> list[str]:
        return sorted(s["signal_id"] for s in signals if predicate(s))

    dimensions: dict[str, Any] = {}
    for dimension in DIMENSION_ORDER:
        members = [s for s in signals if s["dimension"] == dimension]
        if not members or all(s["applicability"] == NON_APPLICABLE for s in members):
            continue
        entry: dict[str, Any] = {}
        for axis in (LEVEL, DIRECTION, TRANSITION, COMPOSITION):
            group = by_key.get((dimension, axis)) or []
            if not group or all(s["role"] == EVIDENCE_ONLY for s in group):
                continue
            r = resolved[(dimension, axis)]
            value = r["value"]
            if value is None:
                value = NONE_OBSERVED if any(s["value"] == NONE_OBSERVED for s in group) else UNAVAILABLE
            entry[axis.lower()] = value
            if value == MIXED:
                entry.setdefault("conflicting_axes", []).append(axis)
            if (dimension, axis) in folded:
                entry.setdefault("vote_counted_once_with", []).append(
                    next(g["counted"] for g in vote_groups if f"{dimension}.{axis}" in (g.get("folded") or [])))
        if dimension in UNCLASSIFIED_LEVELS:
            entry.setdefault("level", UNAVAILABLE)
            entry["level_reason"] = UNCLASSIFIED_LEVELS[dimension]
        stale = {s["signal_id"]: _history(s) for s in stale_evidence if s["dimension"] == dimension}
        if stale:
            # Usable research history, never a current vote.
            entry["stale_research_evidence"] = dict(sorted(stale.items()))
        observed = {s["signal_id"]: _observation(s) for s in observations if s["dimension"] == dimension}
        if observed:
            entry["research_observations"] = dict(sorted(observed.items()))
        context = {s["signal_id"]: s.get("observed") or s["value"] for s in present
                   if s["dimension"] == dimension and s["role"] == EVIDENCE_ONLY and s["applicability"] != NON_APPLICABLE}
        if context:
            entry["context_only"] = dict(sorted(context.items()))
        if entry:
            dimensions[dimension] = entry
    voting = [s for s in signals if s["decision_eligible"]]
    decision_role = [s for s in present if s["role"] == DECISION and s["applicability"] != NON_APPLICABLE]
    evidence = _evidence_availability(signals, state, entity)
    return {
        "contract_version": CONTRACT_VERSION,
        "signal_policy": SIGNAL_POLICY,
        "fundamental_decision_policy_version": DECISION_POLICY_VERSION,
        "source_dialect": dialect,
        "source_status": status,
        "decision_session": decision_session,
        "fundamental_state": state,
        "fundamental_evidence_availability": evidence["fundamental_evidence_availability"],
        "evidence_availability": evidence,
        "fundamental_risk_level": _risk_level(signals),
        "entity_decision_applicability": entity,
        "derivation": {
            "rule": DERIVATION_RULE,
            "vote_eligibility": VOTE_ELIGIBILITY_RULE,
            "favorable_votes": favorable, "adverse_votes": adverse,
            "vote_grouping": {"rule": VOTE_GROUPING_RULE, "groups": vote_groups,
                              "folded_votes": sorted(f"{d}.{a}" for d, a in folded)},
            "deterioration_gate": gate, "improving_drivers": drivers,
            "turnaround": {"triggered": turnaround,
                           "transition": shown_transition["value"] if shown_transition else None,
                           "basis": shown_transition["fitness"]["basis"] if shown_transition else None,
                           "freshness": shown_transition["fitness"]["freshness"] if shown_transition else None,
                           "current": bool(transition),
                           "required_bases": sorted(TURNAROUND_BASES),
                           "required_freshness": sorted(TURNAROUND_FRESHNESS)},
            "stale_research_dimensions": sorted({f"{s['dimension']}.{s['axis']}" for s in stale_evidence}),
        },
        "dimensions": dimensions,
        # Levels are observations: a stale level stays a (labelled) strength or weakness.
        "strengths": ids(lambda s: s["research_usable"] and s["role"] == DECISION and s["axis"] == LEVEL
                         and s["polarity"] == FAVORABLE),
        "weaknesses": ids(lambda s: s["research_usable"] and s["role"] == DECISION and s["axis"] == LEVEL
                          and s["polarity"] == ADVERSE),
        # Directions are current statements: a stale direction is historical context only.
        "improving": ids(lambda s: s["decision_eligible"] and s["axis"] == DIRECTION and s["polarity"] == FAVORABLE),
        "deteriorating": ids(lambda s: s["decision_eligible"] and s["axis"] == DIRECTION and s["polarity"] == ADVERSE),
        "transitions": [{"signal_id": s["signal_id"], "value": s["value"], "basis": s["fitness"]["basis"],
                         "freshness": s["fitness"]["freshness"], "decision_eligible": s["decision_eligible"],
                         "non_vote_reason": s.get("non_vote_reason")}
                        for s in present if s["axis"] == TRANSITION],
        "historical_context": {s["signal_id"]: _history(s) for s in sorted(stale_evidence, key=lambda s: s["signal_id"])
                               if s["axis"] in (DIRECTION, TRANSITION)},
        "research_observations": {s["signal_id"]: _observation(s) for s in sorted(observations, key=lambda s: s["signal_id"])},
        "context_only": ids(lambda s: s["role"] == EVIDENCE_ONLY and s["value"] not in (UNAVAILABLE, UNKNOWN)
                            and s["applicability"] == APPLICABLE),
        "stale_research_evidence": sorted(s["signal_id"] for s in stale_evidence),
        "evidence_freshness": {s["signal_id"]: s["fitness"]["freshness"]
                               for s in sorted(present, key=lambda s: s["signal_id"]) if s["research_usable"]},
        "excluded": {s["signal_id"]: s["reason_codes"] for s in sorted(present, key=lambda s: s["signal_id"])
                     if not s["research_usable"] and s["role"] == DECISION and s["applicability"] != NON_APPLICABLE},
        "missing": ids(lambda s: s["applicability"] == APPLICABLE and s["exclusion"] == "PRODUCER_STATE_UNAVAILABLE"),
        "non_applicable": ids(lambda s: s["applicability"] == NON_APPLICABLE),
        "unresolved_applicability": ids(lambda s: s["applicability"] == UNRESOLVED),
        "decision_signal_freshness": dict(sorted(Counter(s["fitness"]["freshness"] for s in voting).items())),
        # Vote-capable (decision-role) signals by what their period allowed.
        "signal_freshness_voting": {
            "CURRENT_VOTING": sum(s["decision_eligible"] for s in decision_role),
            "STALE_RESEARCH_ONLY": sum(s["research_usable"] and _is_stale(s) for s in decision_role),
            "UNAVAILABLE_EXCLUDED": sum(s["exclusion"] == "FINANCIAL_PERIOD_UNAVAILABLE_FOR_DECISION" for s in decision_role),
        },
        # Every reason valid decision-grade evidence did not vote.
        "signal_non_vote_reasons": dict(sorted(Counter(s["non_vote_reason"] for s in decision_role
                                                       if s["research_usable"] and s.get("non_vote_reason")).items())),
        "consumption_classes": {s["signal_id"]: s["consumption_class"] for s in sorted(present, key=lambda s: s["signal_id"])},
        "supporting_reason_codes": supports,
        "contradicting_reason_codes": counters,
        # Reason codes of stale research evidence: narrative context, never support or counter-thesis.
        "historical_reason_codes": {
            "favorable": list(dict.fromkeys(s["reason_code"] for s in stale_evidence if s["reason_code"] and s["polarity"] == FAVORABLE)),
            "adverse": list(dict.fromkeys(s["reason_code"] for s in stale_evidence if s["reason_code"] and s["polarity"] == ADVERSE)),
        },
        "signals": [dict(s) for s in present],
        "is_actionable": False,
    }


def evaluate(record: Mapping[str, Any] | None, *, decision_session: str | None = None,
             dialect: str | None = None) -> dict[str, Any]:
    """Synthesis for one producer record; ``dialect`` defaults from the record's own contract."""
    if not isinstance(record, Mapping) or (dialect != DIALECT_OPERATIONAL_BRIDGE
                                           and record.get("status") in (None, "ABSENT", "NOT_SUPPLIED")):
        result = synthesize([], dialect=None, decision_session=decision_session,
                            status=(record or {}).get("status") if isinstance(record, Mapping) else None)
        result["contradicting_reason_codes"] = ["FUNDAMENTAL_CONTEXT_ABSENT"]
        return result
    if dialect is None:
        bridge = record.get("source") == DIALECT_OPERATIONAL_BRIDGE or (
            isinstance(record.get("financial_context"), Mapping) and "usable_features" in record)
        dialect = DIALECT_OPERATIONAL_BRIDGE if bridge else DIALECT_FINANCIAL_V2
    if dialect == DIALECT_OPERATIONAL_BRIDGE:
        # The bridge carries its own governed entity-aware applicability.
        signals, entity = operational_bridge_signals(record, decision_session=decision_session), ENTITY_DECISION_APPLICABLE
    else:
        signals, entity = financial_v2_signals(record, decision_session=decision_session), entity_decision_applicability(record)
    return synthesize(signals, dialect=dialect, decision_session=decision_session, status=record.get("status"), entity=entity)


def research_evidence(synthesis: Mapping[str, Any]) -> dict[str, Any]:
    """The research evidence of a synthesis that did not decide the record (it stays visible)."""
    return {
        "contract_version": CONTRACT_VERSION,
        "source_dialect": synthesis.get("source_dialect"),
        "fundamental_state": synthesis.get("fundamental_state"),
        "fundamental_evidence_availability": synthesis.get("fundamental_evidence_availability"),
        "evidence_availability": synthesis.get("evidence_availability"),
        "fundamental_risk_level": synthesis.get("fundamental_risk_level"),
        "strengths": synthesis.get("strengths") or [],
        "weaknesses": synthesis.get("weaknesses") or [],
        "stale_research_evidence": synthesis.get("stale_research_evidence") or [],
        "historical_context": synthesis.get("historical_context") or {},
        "research_observations": synthesis.get("research_observations") or {},
        "evidence_freshness": synthesis.get("evidence_freshness") or {},
    }


def coverage(syntheses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Market-wide consumption counts over one set of syntheses (no scoring)."""
    present: Counter[str] = Counter()
    eligible: Counter[str] = Counter()
    exclusions: dict[str, Counter[str]] = {}
    freshness: Counter[str] = Counter()
    voting: Counter[str] = Counter()
    classes: dict[str, Counter[str]] = {}
    votes: Counter[str] = Counter()
    evidence: Counter[str] = Counter()
    non_vote: dict[str, Counter[str]] = {}
    grouping: Counter[str] = Counter()
    for synthesis in syntheses:
        for signal in synthesis.get("signals") or []:
            present[signal["signal_id"]] += 1
            classes.setdefault(signal["signal_id"], Counter())[signal.get("consumption_class")] += 1
            if signal["decision_eligible"]:
                eligible[signal["signal_id"]] += 1
                freshness[signal["fitness"]["freshness"]] += 1
            elif signal.get("exclusion"):
                exclusions.setdefault(signal["signal_id"], Counter())[signal["exclusion"]] += 1
            if signal.get("non_vote_reason"):
                non_vote.setdefault(signal["signal_id"], Counter())[signal["non_vote_reason"]] += 1
        voting.update(synthesis.get("signal_freshness_voting") or {})
        derivation = synthesis.get("derivation") or {}
        votes.update(f"{label}:{FAVORABLE}" for label in derivation.get("favorable_votes") or [])
        votes.update(f"{label}:{ADVERSE}" for label in derivation.get("adverse_votes") or [])
        grouping.update(group.get("outcome") for group in (derivation.get("vote_grouping") or {}).get("groups") or [])
        availability = (synthesis.get("evidence_availability") or {})
        evidence[f"{availability.get('state')}:{availability.get('directional_sufficiency')}"] += 1

    def distribution(key: Any) -> dict[str, int]:
        return dict(sorted(Counter(str(key(s)) for s in syntheses).items()))

    return {
        "contract_version": CONTRACT_VERSION,
        "signal_policy": SIGNAL_POLICY,
        "denominator": len(syntheses),
        "source_dialect_distribution": distribution(lambda s: s.get("source_dialect")),
        "fundamental_decision_policy_version": distribution(lambda s: s.get("fundamental_decision_policy_version")),
        "fundamental_evidence_availability": distribution(lambda s: s.get("fundamental_evidence_availability")),
        "fundamental_risk_level": distribution(lambda s: (s.get("fundamental_risk_level") or {}).get("state")),
        "entity_decision_applicability": distribution(lambda s: s.get("entity_decision_applicability")),
        "signal_present": dict(sorted(present.items())),
        "signal_decision_eligible": dict(sorted(eligible.items())),
        "signal_consumption_classes": {key: dict(sorted(value.items())) for key, value in sorted(classes.items())},
        "signal_exclusions": {key: dict(sorted(value.items())) for key, value in sorted(exclusions.items())},
        "signal_non_vote_reasons": {key: dict(sorted(value.items())) for key, value in sorted(non_vote.items())},
        "decision_signal_freshness": dict(sorted(freshness.items())),
        "signal_freshness_voting": dict(sorted(voting.items())),
        "dimension_votes": dict(sorted(votes.items())),
        "vote_grouping_outcomes": dict(sorted(grouping.items())),
        "evidence_availability": dict(sorted(evidence.items())),
        "turnaround_triggered": sum(bool(((s.get("derivation") or {}).get("turnaround") or {}).get("triggered")) for s in syntheses),
        "records_with_stale_research_evidence": sum(bool(s.get("stale_research_evidence")) for s in syntheses),
    }


def compact_components(synthesis: Mapping[str, Any]) -> dict[str, Any]:
    """The small, stable restatement other surfaces carry (no signal detail)."""
    risk = synthesis.get("fundamental_risk_level") or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "signal_policy": synthesis.get("signal_policy"),
        "fundamental_decision_policy_version": synthesis.get("fundamental_decision_policy_version"),
        "evidence_availability": (synthesis.get("evidence_availability") or {}).get("state"),
        "fundamental_evidence_availability": synthesis.get("fundamental_evidence_availability"),
        "directional_sufficiency": (synthesis.get("evidence_availability") or {}).get("directional_sufficiency"),
        "risk_level": {"state": risk.get("state"), "adverse_level_dimensions": risk.get("adverse_level_dimensions") or [],
                       "constructive_level_dimensions": risk.get("constructive_level_dimensions") or []},
        "dimensions": synthesis.get("dimensions") or {},
        "strengths": synthesis.get("strengths") or [],
        "weaknesses": synthesis.get("weaknesses") or [],
        "improving": synthesis.get("improving") or [],
        "deteriorating": synthesis.get("deteriorating") or [],
        "transitions": [item["value"] for item in synthesis.get("transitions") or [] if item.get("decision_eligible")],
        "transition_observations": [{"value": item["value"], "basis": item.get("basis"), "non_vote_reason": item.get("non_vote_reason")}
                                    for item in synthesis.get("transitions") or []
                                    if not item.get("decision_eligible") and item.get("non_vote_reason")],
        "folded_votes": ((synthesis.get("derivation") or {}).get("vote_grouping") or {}).get("folded_votes") or [],
        "stale_research_evidence": synthesis.get("stale_research_evidence") or [],
        "historical_context": synthesis.get("historical_context") or {},
        "evidence_freshness": synthesis.get("evidence_freshness") or {},
        "excluded_unavailable_period": sorted(key for key, codes in (synthesis.get("excluded") or {}).items()
                                              if "FINANCIAL_PERIOD_UNAVAILABLE_FOR_DECISION" in codes),
    }
