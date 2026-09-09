"""Portfolio-Aware Decision And Risk Sizing (PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1).

Turns the existing objective Integrated Investment Decision into a private, personalized
portfolio decision layer:

    Market Decision x Private Portfolio State x Risk Policy
        -> Portfolio-Aware Action + Risk Quantity Ceiling + Funding/Margin Context

This module joins a private, local-only portfolio state (``private_portfolio_context.py``'s
``portfolio_snapshot/v1``, which itself embeds an ``account_snapshot/v1`` and an already
owner/system-default-resolved ``portfolio_policy/v1``) against a finished
``integrated_investment_decision_product/v1`` per-ticker record, and emits a
``portfolio_aware_decision/v1`` record with two nested, independently identified sub-contracts:
``portfolio_risk_sizing/v1`` (the deterministic quantity ceilings and their calculation trace)
and ``margin_economics/v1`` (tactical-trade-only financing research capacity).

Guiding boundary (unchanged from ``integrated_investment_decision_product.py``'s own Guiding
Principle 5): security attractiveness stays strictly separate from portfolio fit. This module
never mutates ``research_action_posture``, never invents a stop price or a price target, never
emits a forced-liquidation instruction, and never fabricates a positive expected utility for new
margin. It reuses ``current_portfolio_risk_envelope/v1``'s existing boundary rather than building
a second risk engine: ``execution_qualified_quantity`` stays ``NOT_QUALIFIED`` unconditionally,
because exact liquidity/execution authority is not established anywhere in this repository.

Owner profile: CORE_LONG_TERM_WITH_TACTICAL_OVERLAY. A long-term core position and an unrelated
tactical opportunity in the same, or a different, ticker are not in conflict: existing exposure
above a policy cap means NO NEW ADDITION by default (``OVER_LIMIT_REVIEW``), never an automatic
sell. Cost basis and lifetime cash-recovery breakeven are surfaced as context only (see
``cost_basis_context`` below) and are never read by any constraint, sizing, or eligibility
computation in this module.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import exchange_industry_classification as _industry_classification
import private_portfolio_context as _private_portfolio_context

CONTRACT_VERSION = "portfolio_aware_decision/v1"
RISK_SIZING_CONTRACT_VERSION = "portfolio_risk_sizing/v1"
MARGIN_ECONOMICS_CONTRACT_VERSION = "margin_economics/v1"
PORTFOLIO_STATE_CONTRACT = "portfolio_state/v1"
MILESTONE = "PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1"

POSITION_STATES = frozenset({"NOT_HELD", "HELD", "HELD_ABOVE_POLICY_CAP", "EXCLUDED_INACTIVE"})
POSITION_LANES = frozenset({"CORE", "TACTICAL", "UNSPECIFIED"})

# Full-size add: the security decision's own trigger already fired (or a bullish retest is
# confirmed). Probe: the same product's early-entry/monitoring state, before any trigger fires,
# with a deterministic invalidation already available -- never manufactured from oversold status
# or subjective judgment (see ``_probe_eligible`` below).
ADD_ELIGIBLE_POSTURES = frozenset({"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST"})
PROBE_ELIGIBLE_POSTURES = frozenset({"EARLY_WATCH"})
AVOID_LIKE_POSTURES = frozenset({"AVOID", "REDUCE"})

SIZING_MODE_NOT_APPLICABLE = "NOT_APPLICABLE"
SIZING_MODE_FULL = "FULL_RISK_BUDGET"
SIZING_MODE_PROBE = "PROBE_RISK_BUDGET"
SIZING_MODES = frozenset({SIZING_MODE_NOT_APPLICABLE, SIZING_MODE_FULL, SIZING_MODE_PROBE})

#: Sector-resolution lineage tags. `NOT_EVALUATED_MISSING_SECTOR` is the honest terminal state when
#: neither an explicit caller-supplied sector nor an already-existing current-session governed
#: classification names one -- missing evidence is never treated as evidence of zero sector exposure.
SECTOR_SOURCE_CALLER_SUPPLIED = "CALLER_SUPPLIED_GOVERNED_SECTOR"
SECTOR_SOURCE_EXCHANGE_INDUSTRY_CLASSIFICATION = "EXCHANGE_INDUSTRY_CLASSIFICATION_SNAPSHOT"
SECTOR_SOURCE_NOT_EVALUATED = "NOT_EVALUATED_MISSING_SECTOR"

PORTFOLIO_ACTION_RESEARCH_STATES = frozenset({
    "NOT_EVALUATED",
    "EXCLUDED_FROM_ACTIVE_PORTFOLIO",
    "INSUFFICIENT_FOR_PORTFOLIO_DECISION",
    "OVER_LIMIT_REVIEW",
    "HOLD_EXISTING_NO_ACTION",
    "AVOID_NO_PORTFOLIO_ACTION",
    "NO_ADD",
    "ADD_ELIGIBLE_SIZING_UNAVAILABLE",
    "ADD_WITHIN_RISK_CEILING",
    "ADD_WITHIN_EVALUATED_CONSTRAINTS",
    "PROBE_ELIGIBLE_SIZING_UNAVAILABLE",
    "PROBE_WITHIN_RISK_CEILING",
    "PROBE_WITHIN_EVALUATED_CONSTRAINTS",
})

#: The constraint dimensions that can gate/size a specific add or probe. MARGIN_DEBT is
#: deliberately excluded -- it is always descriptive-only for a *cash*-funded ceiling (see
#: BINDING_CONSTRAINT_PRIORITY below); it only participates in margin *research capacity*.
_GATING_CONSTRAINT_NAMES = ("SINGLE_POSITION", "SECTOR", "GROSS_EXPOSURE", "CASH_RESERVE", "RISK_BUDGET")
_EVALUATED_CONSTRAINT_STATUSES = frozenset({"WITHIN_LIMIT", "AT_LIMIT", "LIMIT_BREACH", "AVAILABLE"})
PORTFOLIO_CONSTRAINT_COMPLETENESS_STATES = frozenset({"FULL", "PARTIAL", "INSUFFICIENT", "NOT_APPLICABLE"})

# First-match-wins priority for `binding_constraint`. MARGIN_DEBT is deliberately never a
# binding_constraint value here: an existing margin-debt breach is a standing portfolio-risk fact
# (reported via `margin_debt_constraint`) but does not by itself block a specific new *cash*-funded
# add -- it would conflate an unrelated funding source with this ticker's own risk-policy eligibility.
# It does, however, cap margin *research capacity* (see `_margin_debt_room_quantity`).
BINDING_CONSTRAINT_PRIORITY = ("RISK_BUDGET", "SINGLE_POSITION", "SECTOR", "GROSS_EXPOSURE", "CASH_RESERVE")

MARGIN_BAND_NO_MARGIN = "NO_MARGIN"
MARGIN_BAND_INTERPOLATED = "INTERPOLATED_MIN_TO_MAX"
MARGIN_BAND_MAX = "MAX_BAND"
MARGIN_BANDS = frozenset({MARGIN_BAND_NO_MARGIN, MARGIN_BAND_INTERPOLATED, MARGIN_BAND_MAX})

MARGIN_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
MARGIN_STATUS_NOT_EVALUATED = "NOT_EVALUATED"
MARGIN_STATUS_EVALUATED = "EVALUATED"

_EPS = 1e-9


# ── Canonical identity ────────────────────────────────────────────────────────

def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}


def content_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    body = {key: value for key, value in payload.items() if key not in _IDENTITY_EXCLUDED}
    digest = _sha256(body)
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _identity(kind: str, payload: Mapping[str, Any]) -> dict[str, str]:
    body = {key: value for key, value in payload.items() if key not in _IDENTITY_EXCLUDED}
    digest = _sha256(body)
    return {"artifact_sha256": digest, "artifact_identity": f"{kind}:{digest}"}


def _decision_identity(record: Mapping[str, Any]) -> str:
    fields = {
        "ticker": record.get("ticker"),
        "as_of_session": record.get("as_of_session"),
        "policy_version": "v1",
        "security_research_action_posture": record.get("security_research_action_posture"),
        "portfolio_action_research": record.get("portfolio_action_research"),
        "position_state": record.get("position_state"),
        "position_lane": record.get("position_lane"),
        "sizing_mode": record.get("sizing_mode"),
        "portfolio_risk_quantity_ceiling": record.get("portfolio_risk_quantity_ceiling"),
        "binding_constraint": record.get("binding_constraint"),
        "portfolio_constraint_completeness": record.get("portfolio_constraint_completeness"),
        "constraints_not_evaluated": record.get("constraints_not_evaluated"),
        "margin_economics_status": (record.get("margin_economics") or {}).get("status"),
        "margin_research_band": (record.get("margin_economics") or {}).get("margin_research_band"),
        "evidence_lineage": record.get("evidence_lineage"),
    }
    return f"portfolio_decision:{record.get('ticker')}:{_sha256(fields)[:16]}"


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def default_private_output_root() -> Path:
    """The sole default local storage root for this module's own output artifacts.

    Reuses ``private_portfolio_context.default_portfolio_root()`` (``%USERPROFILE%
    \\.stocklookup\\portfolio``) rather than inventing a second private boundary; this module
    never writes to ``operations-review/``, Git, the Dashboard/AI-handoff repositories, or any
    other tracked path. Callers still choose their own filename; this only fixes the parent
    directory.
    """
    return _private_portfolio_context.default_portfolio_root() / "portfolio_aware_decisions"


def resolve_sector_by_ticker(
    *, explicit_sector_by_ticker: Mapping[str, Any] | None = None,
    governed_sector_snapshot: Mapping[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, str], str | None]:
    """Resolve a ticker -> governed sector map, with explicit lineage per ticker.

    Reuses existing authority only -- this is not a new sector-classification engine. Preferred
    resolution order (never a fuzzy name match, never a stale mtime/latest filesystem scan; the
    caller supplies exactly which already-identified session artifact, if any, to read):

      1. ``explicit_sector_by_ticker`` -- an explicit, caller-supplied governed sector.
      2. ``governed_sector_snapshot`` -- an already-loaded ``exchange_industry_classification``
         snapshot, read only through that module's own ``industry_index()``.
      3. Neither resolves a given ticker -> absent from the returned maps. Callers record this
         as ``NOT_EVALUATED_MISSING_SECTOR``, never ``UNCONSTRAINED``.
    """
    explicit = {
        str(ticker).upper(): sector for ticker, sector in (explicit_sector_by_ticker or {}).items()
        if isinstance(sector, str) and sector.strip()
    }
    index = _industry_classification.industry_index(governed_sector_snapshot)
    snapshot_identity = governed_sector_snapshot.get("records_fingerprint") if isinstance(governed_sector_snapshot, Mapping) else None

    sector_by_ticker: dict[str, str] = {}
    sector_source_by_ticker: dict[str, str] = {}
    for ticker in set(explicit) | set(index):
        if ticker in explicit:
            sector_by_ticker[ticker] = explicit[ticker]
            sector_source_by_ticker[ticker] = SECTOR_SOURCE_CALLER_SUPPLIED
            continue
        label = (index.get(ticker) or {}).get("icb_level_2_label")
        if isinstance(label, str) and label.strip():
            sector_by_ticker[ticker] = label
            sector_source_by_ticker[ticker] = SECTOR_SOURCE_EXCHANGE_INDUSTRY_CLASSIFICATION
    return sector_by_ticker, sector_source_by_ticker, snapshot_identity


def _constraint_completeness(
    *, single_constraint: Mapping[str, Any], sector_constraint: Mapping[str, Any], gross_constraint: Mapping[str, Any],
    cash_reserve_constraint: Mapping[str, Any], risk_sizing: Mapping[str, Any],
) -> tuple[str, list[str], list[str]]:
    """Which of the constraints capable of gating/sizing a specific add/probe were evaluated.

    ``MARGIN_DEBT`` is deliberately not one of these -- see ``BINDING_CONSTRAINT_PRIORITY``.
    """
    status_by_name = {
        "SINGLE_POSITION": single_constraint.get("status"),
        "SECTOR": sector_constraint.get("status"),
        "GROSS_EXPOSURE": gross_constraint.get("status"),
        "CASH_RESERVE": cash_reserve_constraint.get("status"),
        "RISK_BUDGET": risk_sizing.get("status"),
    }
    evaluated = [name for name in _GATING_CONSTRAINT_NAMES if status_by_name[name] in _EVALUATED_CONSTRAINT_STATUSES]
    not_evaluated = [name for name in _GATING_CONSTRAINT_NAMES if name not in evaluated]
    if not not_evaluated:
        completeness = "FULL"
    elif evaluated:
        completeness = "PARTIAL"
    else:
        completeness = "INSUFFICIENT"
    return completeness, evaluated, not_evaluated


# ── Portfolio state derivation (PRIVATE PORTFOLIO STATE box) ──────────────────

def _resolve_lane_context(current_quantity: float, lanes_input: Mapping[str, Any]) -> tuple[dict[str, float], str]:
    if not lanes_input:
        return ({"UNSPECIFIED": current_quantity} if current_quantity else {}), "NO_LANE_INPUT_ALL_UNSPECIFIED"
    lanes: dict[str, float] = {}
    total = 0.0
    for lane, qty in lanes_input.items():
        lane_name = str(lane).upper()
        if lane_name not in POSITION_LANES:
            continue
        value = _num(qty) or 0.0
        lanes[lane_name] = lanes.get(lane_name, 0.0) + value
        total += value
    remainder = round(current_quantity - total, 6)
    if remainder > 1e-6:
        lanes["UNSPECIFIED"] = lanes.get("UNSPECIFIED", 0.0) + remainder
        return lanes, "PARTIAL_OR_INCONSISTENT"
    if remainder < -1e-6:
        return lanes, "PARTIAL_OR_INCONSISTENT"
    return lanes, "RECONCILED"


def derive_portfolio_state(
    *,
    portfolio_snapshot: Mapping[str, Any] | None,
    prices: Mapping[str, Any] | None = None,
    sector_by_ticker: Mapping[str, Any] | None = None,
    governed_sector_snapshot: Mapping[str, Any] | None = None,
    position_lanes: Mapping[str, Mapping[str, Any]] | None = None,
    excluded_tickers: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Read-only projection of a private ``portfolio_snapshot/v1`` into decision-ready state.

    ``portfolio_snapshot`` is never mutated and never re-derived; every value below is read
    straight from its ``positions`` / ``account_snapshot`` / ``portfolio_policy`` sub-contracts.
    A missing or not-yet-imported snapshot (the honest ``OWNER_INPUT_NOT_PRESENT`` case) returns
    ``status: "NOT_PROVIDED"`` rather than raising, so a caller with no real workbook still gets
    a well-formed state.

    Owner-excluded tickers (``excluded_tickers``) are marked ``is_active: False`` and are never
    counted in sector or gross-exposure weights; they participate only as a read-only, clearly
    labelled position row (``EXCLUDED_INACTIVE``), never in active exposure/action output.
    """
    prices_map = {str(ticker).upper(): _num(value) for ticker, value in (prices or {}).items()}
    sectors, sector_sources, governed_sector_snapshot_identity = resolve_sector_by_ticker(
        explicit_sector_by_ticker=sector_by_ticker, governed_sector_snapshot=governed_sector_snapshot,
    )
    lanes_by_ticker = position_lanes or {}
    excluded = {str(ticker).upper() for ticker in (excluded_tickers or [])}

    if not isinstance(portfolio_snapshot, Mapping) or "positions" not in portfolio_snapshot:
        return {
            "schema_version": "portfolio_state_v1",
            "contract_version": PORTFOLIO_STATE_CONTRACT,
            "status": "NOT_PROVIDED",
            "reason": "PRIVATE_PORTFOLIO_STATE_NOT_PROVIDED",
            "as_of_date": None,
            "positions": {},
            "prices": prices_map,
            "sector_by_ticker": sectors,
            "sector_source_by_ticker": sector_sources,
            "effective_nav": None,
            "nav_basis": "UNAVAILABLE",
            "nav_reconciliation": None,
            "cash_available": None,
            "cash_reserved": None,
            "margin_debt": None,
            "margin_available_minimum": None,
            "margin_available_maximum": None,
            "annual_margin_rate_percent": None,
            "effective_policy": {},
            "sector_weights": {},
            "gross_exposure_weight": None,
            "source_identities": {"portfolio_snapshot_identity": None, "governed_sector_snapshot_identity": governed_sector_snapshot_identity},
        }

    account_fields = ((portfolio_snapshot.get("account_snapshot") or {}).get("fields")) or {}
    policy = portfolio_snapshot.get("portfolio_policy") or {}
    effective_policy = {key: _num(value) for key, value in (policy.get("effective_fields") or {}).items()}

    cash_available = _num(account_fields.get("cash_available"))
    cash_reserved = _num(account_fields.get("cash_reserved"))
    margin_debt = _num(account_fields.get("margin_debt"))
    margin_min = _num(account_fields.get("margin_available_minimum"))
    margin_max = _num(account_fields.get("margin_available_maximum"))
    annual_margin_rate_percent = _num(account_fields.get("annual_margin_rate_percent"))
    broker_nav = _num(account_fields.get("net_asset_value"))

    positions: dict[str, dict[str, Any]] = {}
    priced_market_value_sum = 0.0
    for row in portfolio_snapshot.get("positions") or []:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        quantity = _num(row.get("current_quantity")) or 0.0
        price = prices_map.get(ticker)
        market_value = quantity * price if price is not None else None
        if market_value is not None:
            priced_market_value_sum += market_value
        lane_context, lane_reconciliation = _resolve_lane_context(quantity, lanes_by_ticker.get(ticker) or {})
        positions[ticker] = {
            "ticker": ticker,
            "current_quantity": quantity,
            "current_price": price,
            "current_market_value": market_value,
            "cost_basis_per_share": _num(row.get("current_position_cost_basis_per_share")),
            "cost_basis_method": row.get("current_position_cost_basis_method"),
            "lifetime_cash_recovery_breakeven": _num(row.get("lifetime_cash_recovery_breakeven")),
            "lifetime_cash_recovery_breakeven_method": row.get("lifetime_cash_recovery_breakeven_method"),
            "position_episode_holding_days": row.get("position_episode_holding_days"),
            "sector": sectors.get(ticker),
            "sector_source": sector_sources.get(ticker, SECTOR_SOURCE_NOT_EVALUATED),
            "is_active": ticker not in excluded,
            "existing_position_lane_context": lane_context,
            "lane_reconciliation": lane_reconciliation,
        }

    computed_nav = (cash_available + priced_market_value_sum - (margin_debt or 0.0)) if cash_available is not None else None
    if broker_nav is not None:
        effective_nav, nav_basis = broker_nav, "NAV_BROKER_REPORTED"
    elif computed_nav is not None:
        effective_nav, nav_basis = computed_nav, "NAV_COMPUTED_FROM_CASH_AND_MARKED_POSITIONS"
    else:
        effective_nav, nav_basis = None, "UNAVAILABLE"

    nav_reconciliation = None
    if broker_nav is not None and computed_nav is not None:
        diff = abs(broker_nav - computed_nav)
        relative = (diff / broker_nav) if broker_nav else None
        nav_reconciliation = {
            "broker_nav": broker_nav, "computed_nav": computed_nav,
            "absolute_difference": diff, "relative_difference": relative,
            "status": "RECONCILED" if (relative is not None and relative <= 0.01) else "WARNING",
        }

    sector_weights: dict[str, float] = {}
    for pos in positions.values():
        if not pos["is_active"] or pos["current_market_value"] is None or not effective_nav:
            pos["current_weight"] = None
            pos["current_weight_status"] = "UNAVAILABLE_NO_PRICE_OR_NAV" if pos["is_active"] else "EXCLUDED_INACTIVE"
            continue
        weight = pos["current_market_value"] / effective_nav
        pos["current_weight"] = weight
        pos["current_weight_status"] = "AVAILABLE"
        if pos["sector"]:
            sector_weights[pos["sector"]] = sector_weights.get(pos["sector"], 0.0) + weight

    gross_exposure_weight = None
    if effective_nav:
        gross_exposure_weight = sum(
            (pos["current_market_value"] or 0.0) for pos in positions.values() if pos["is_active"]
        ) / effective_nav

    return {
        "schema_version": "portfolio_state_v1",
        "contract_version": PORTFOLIO_STATE_CONTRACT,
        "status": "AVAILABLE",
        "as_of_date": portfolio_snapshot.get("snapshot_as_of_date"),
        "positions": positions,
        "prices": prices_map,
        "sector_by_ticker": sectors,
        "sector_source_by_ticker": sector_sources,
        "effective_nav": effective_nav,
        "nav_basis": nav_basis,
        "nav_reconciliation": nav_reconciliation,
        "cash_available": cash_available,
        "cash_reserved": cash_reserved,
        "margin_debt": margin_debt,
        "margin_available_minimum": margin_min,
        "margin_available_maximum": margin_max,
        "annual_margin_rate_percent": annual_margin_rate_percent,
        "effective_policy": effective_policy,
        "sector_weights": sector_weights,
        "gross_exposure_weight": gross_exposure_weight,
        "source_identities": {
            "portfolio_snapshot_identity": portfolio_snapshot.get("artifact_identity"),
            "governed_sector_snapshot_identity": governed_sector_snapshot_identity,
        },
    }


# ── Constraint evaluation ──────────────────────────────────────────────────────

def _weight_constraint(*, observed_weight: float | None, limit: float | None, effective_nav: float | None, entry_price: float | None) -> dict[str, Any]:
    if limit is None or observed_weight is None or not effective_nav:
        return {"status": "UNAVAILABLE", "observed_weight": observed_weight, "limit": limit,
                "remaining_weight": None, "remaining_notional": None, "remaining_quantity": None}
    remaining_weight = max(0.0, limit - observed_weight)
    remaining_notional = remaining_weight * effective_nav
    remaining_quantity = math.floor(remaining_notional / entry_price) if entry_price and entry_price > 0 else None
    if observed_weight > limit + _EPS:
        status = "LIMIT_BREACH"
    elif observed_weight >= limit - _EPS:
        status = "AT_LIMIT"
    else:
        status = "WITHIN_LIMIT"
    return {"status": status, "observed_weight": observed_weight, "limit": limit,
            "remaining_weight": remaining_weight, "remaining_notional": remaining_notional,
            "remaining_quantity": remaining_quantity}


def _floor_amount_constraint(*, observed_amount: float | None, floor_fraction: float | None, effective_nav: float | None) -> dict[str, Any]:
    """Breach when ``observed_amount`` falls below ``floor_fraction * effective_nav`` (cash reserve)."""
    if floor_fraction is None or observed_amount is None or not effective_nav:
        return {"status": "UNAVAILABLE", "observed_amount": observed_amount, "limit_amount": None, "remaining_amount": None}
    limit_amount = floor_fraction * effective_nav
    remaining_amount = observed_amount - limit_amount
    if observed_amount < limit_amount - _EPS:
        status = "LIMIT_BREACH"
    elif observed_amount <= limit_amount + _EPS:
        status = "AT_LIMIT"
    else:
        status = "WITHIN_LIMIT"
    return {"status": status, "observed_amount": observed_amount, "limit_amount": limit_amount, "remaining_amount": remaining_amount}


def _ceiling_amount_constraint(*, observed_amount: float | None, cap_fraction: float | None, effective_nav: float | None) -> dict[str, Any]:
    """Breach when ``observed_amount`` exceeds ``cap_fraction * effective_nav`` (margin debt)."""
    if cap_fraction is None or observed_amount is None or not effective_nav:
        return {"status": "UNAVAILABLE", "observed_amount": observed_amount, "limit_amount": None, "remaining_amount": None}
    limit_amount = cap_fraction * effective_nav
    remaining_amount = max(0.0, limit_amount - observed_amount)
    if observed_amount > limit_amount + _EPS:
        status = "LIMIT_BREACH"
    elif observed_amount >= limit_amount - _EPS:
        status = "AT_LIMIT"
    else:
        status = "WITHIN_LIMIT"
    return {"status": status, "observed_amount": observed_amount, "limit_amount": limit_amount, "remaining_amount": remaining_amount}


# ── Risk sizing ─────────────────────────────────────────────────────────────

def _compute_risk_sizing(*, entry_price: float | None, invalidation_price: float | None, effective_nav: float | None, risk_budget_fraction: float | None) -> dict[str, Any]:
    if invalidation_price is None:
        return {"status": "UNAVAILABLE_MISSING_INVALIDATION", "per_share_downside": None, "risk_budget_amount": None, "risk_budget_quantity": None}
    if entry_price is None:
        return {"status": "UNAVAILABLE_MISSING_ENTRY_PRICE", "per_share_downside": None, "risk_budget_amount": None, "risk_budget_quantity": None}
    if not effective_nav:
        return {"status": "UNAVAILABLE_MISSING_NAV", "per_share_downside": None, "risk_budget_amount": None, "risk_budget_quantity": None}
    if risk_budget_fraction is None:
        return {"status": "UNAVAILABLE_MISSING_RISK_BUDGET_POLICY", "per_share_downside": None, "risk_budget_amount": None, "risk_budget_quantity": None}
    per_share_downside = abs(entry_price - invalidation_price)
    if per_share_downside <= 0:
        return {"status": "UNAVAILABLE_DEGENERATE_DOWNSIDE", "per_share_downside": 0.0, "risk_budget_amount": None, "risk_budget_quantity": None}
    risk_budget_amount = effective_nav * risk_budget_fraction
    risk_budget_quantity = max(0, math.floor(risk_budget_amount / per_share_downside))
    return {"status": "AVAILABLE", "per_share_downside": per_share_downside,
            "risk_budget_amount": risk_budget_amount, "risk_budget_quantity": risk_budget_quantity}


def _probe_eligible(*, posture: str, invalidation_price: float | None, entry_price: float | None) -> bool:
    """Never manufactured from oversold status or subjective judgment.

    A ticker is probe-eligible only when the existing, already-governed security decision
    product itself reports the early-entry/monitoring posture (``EARLY_WATCH`` -- an early
    bullish structural reversal / base compression ahead of any breakout trigger) *and* that
    same product already supplies a deterministic invalidation level and a proposed entry/trigger
    reference. No new technical state, oversold indicator, or AI judgment is evaluated here.
    """
    return posture in PROBE_ELIGIBLE_POSTURES and invalidation_price is not None and entry_price is not None


# ── Margin economics (margin_economics/v1; tactical trades only) ─────────────

def _margin_authority_boundary() -> dict[str, Any]:
    return {
        "research_funding_ceiling_not_execution_instruction": True,
        "no_fabricated_probability_or_expected_return": True,
        "deterministic_upside_never_called_expected_return": True,
        "does_not_permanently_choose_min_or_max": True,
    }


def _margin_economics_not_applicable(reason_code: str) -> dict[str, Any]:
    body = {
        "contract_version": MARGIN_ECONOMICS_CONTRACT_VERSION,
        "status": MARGIN_STATUS_NOT_APPLICABLE,
        "reason_code": reason_code,
        "margin_research_band": MARGIN_BAND_NO_MARGIN,
        "inputs": None,
        "calculation": None,
        "research_capacity": None,
        "authority_boundary": _margin_authority_boundary(),
    }
    return {**body, **_identity("margin_economics", body)}


def _evaluate_margin_economics(
    *, sizing_mode: str, entry_price: float | None, invalidation_price: float | None,
    reward_boundary: float | None, annual_margin_rate_percent: float | None,
    margin_available_minimum: float | None, margin_available_maximum: float | None,
    tactical_margin_holding_days: float | None, min_net_reward_risk_for_margin: float | None,
    strong_net_reward_risk_for_max_margin: float | None, max_financing_cost_fraction_of_gross_upside: float | None,
) -> dict[str, Any]:
    """Deterministic tactical-trade-only margin research-capacity band.

    ``status`` distinguishes three layers so a consumer never conflates "not a tactical trade"
    with "a tactical trade whose economics cannot be computed" with "computed and evaluated":
      * ``NOT_APPLICABLE`` -- this ticker is not a new tactical decision sleeve this session.
      * ``NOT_EVALUATED``  -- it is, but a required input (reward/upside boundary, margin rate,
        or a non-degenerate downside) is missing. Never invents a target or a rate.
      * ``EVALUATED``      -- the full calculation ran; ``margin_research_band`` carries the result.
    """
    if sizing_mode not in (SIZING_MODE_FULL, SIZING_MODE_PROBE):
        return _margin_economics_not_applicable("NOT_A_TACTICAL_DECISION_SLEEVE_THIS_SESSION")
    if entry_price is None or invalidation_price is None:
        return _margin_economics_not_applicable("PROPOSED_ENTRY_OR_INVALIDATION_UNAVAILABLE")

    downside_per_share = entry_price - invalidation_price
    inputs = {
        "proposed_entry_or_trigger": entry_price,
        "deterministic_invalidation": invalidation_price,
        "deterministic_tactical_upside_or_target": reward_boundary,
        "reward_boundary_status": "PROVIDED" if reward_boundary is not None else "UNAVAILABLE_NO_QUALIFIED_UPSIDE_BASIS_UPSTREAM",
        "annual_margin_rate_percent": annual_margin_rate_percent,
        "margin_available_minimum": margin_available_minimum,
        "margin_available_maximum": margin_available_maximum,
        "tactical_margin_holding_days": tactical_margin_holding_days,
        "min_net_reward_risk_for_margin": min_net_reward_risk_for_margin,
        "strong_net_reward_risk_for_max_margin": strong_net_reward_risk_for_max_margin,
        "max_financing_cost_fraction_of_gross_upside": max_financing_cost_fraction_of_gross_upside,
    }

    def not_evaluated(reason_code: str) -> dict[str, Any]:
        body = {
            "contract_version": MARGIN_ECONOMICS_CONTRACT_VERSION,
            "status": MARGIN_STATUS_NOT_EVALUATED,
            "reason_code": reason_code,
            "margin_research_band": MARGIN_BAND_NO_MARGIN,
            "inputs": inputs,
            "calculation": None,
            "research_capacity": None,
            "authority_boundary": _margin_authority_boundary(),
        }
        return {**body, **_identity("margin_economics", body)}

    if downside_per_share <= 0:
        return not_evaluated("DEGENERATE_OR_NEGATIVE_DOWNSIDE")
    if reward_boundary is None:
        # "If no usable upside/reward boundary exists, margin selection is NOT_EVALUATED; do
        # not invent a target or probability." -- the one path this function refuses to guess.
        return not_evaluated("NO_QUALIFIED_UPSIDE_OR_REWARD_BASIS_UPSTREAM")
    if annual_margin_rate_percent is None:
        return not_evaluated("NO_MARGIN_RATE_BASIS")
    if tactical_margin_holding_days is None or min_net_reward_risk_for_margin is None or strong_net_reward_risk_for_max_margin is None:
        return not_evaluated("POLICY_DEFAULTS_UNAVAILABLE")

    gross_upside_per_share = reward_boundary - entry_price
    financing_cost_per_share = entry_price * (annual_margin_rate_percent / 100.0) * (tactical_margin_holding_days / 365.0)
    financing_adjusted_upside_per_share = gross_upside_per_share - financing_cost_per_share
    net_reward_risk = financing_adjusted_upside_per_share / downside_per_share
    financing_cost_fraction_of_gross_upside = (
        financing_cost_per_share / gross_upside_per_share if gross_upside_per_share > 0 else None
    )

    calculation = {
        "gross_upside_per_share": gross_upside_per_share,
        "downside_per_share": downside_per_share,
        "financing_cost_per_share": financing_cost_per_share,
        "financing_adjusted_upside_per_share": financing_adjusted_upside_per_share,
        "net_reward_risk": net_reward_risk,
        "financing_cost_fraction_of_gross_upside": financing_cost_fraction_of_gross_upside,
    }

    financing_gate_breached = (
        max_financing_cost_fraction_of_gross_upside is not None
        and financing_cost_fraction_of_gross_upside is not None
        and financing_cost_fraction_of_gross_upside > max_financing_cost_fraction_of_gross_upside + _EPS
    )

    if financing_gate_breached:
        band, reason_code, fraction = MARGIN_BAND_NO_MARGIN, "FINANCING_COST_EXCEEDS_POLICY_MAX_FRACTION_OF_GROSS_UPSIDE", 0.0
    elif net_reward_risk < min_net_reward_risk_for_margin - _EPS:
        band, reason_code, fraction = MARGIN_BAND_NO_MARGIN, "BELOW_MIN_NET_REWARD_RISK_ECONOMICS", 0.0
    elif net_reward_risk >= strong_net_reward_risk_for_max_margin - _EPS:
        band, reason_code, fraction = MARGIN_BAND_MAX, "STRONG_NET_REWARD_RISK_ECONOMICS", 1.0
    else:
        span = strong_net_reward_risk_for_max_margin - min_net_reward_risk_for_margin
        fraction = (net_reward_risk - min_net_reward_risk_for_margin) / span if span > 0 else 0.0
        fraction = max(0.0, min(1.0, fraction))
        band, reason_code = MARGIN_BAND_INTERPOLATED, "QUALIFYING_ECONOMICS_BETWEEN_MIN_AND_MAX_THRESHOLDS"

    if margin_available_minimum is None or margin_available_maximum is None:
        return not_evaluated("MARGIN_CAPACITY_FIELDS_UNAVAILABLE")

    capacity_before_caps = margin_available_minimum + fraction * (margin_available_maximum - margin_available_minimum)
    if band == MARGIN_BAND_NO_MARGIN:
        capacity_before_caps = 0.0

    body = {
        "contract_version": MARGIN_ECONOMICS_CONTRACT_VERSION,
        "status": MARGIN_STATUS_EVALUATED,
        "reason_code": reason_code,
        "margin_research_band": band,
        "inputs": inputs,
        "calculation": calculation,
        "research_capacity": {
            "capacity_before_portfolio_caps_notional": capacity_before_caps,
            "capacity_before_portfolio_caps_quantity": (
                math.floor(capacity_before_caps / entry_price) if entry_price > 0 else 0
            ),
            "final_margin_research_capacity_notional": None,
            "final_margin_research_capacity_quantity": None,
            "capped_by": [],
        },
        "authority_boundary": _margin_authority_boundary(),
    }
    return {**body, **_identity("margin_economics", body)}


def _apply_portfolio_caps_to_margin_capacity(
    margin_economics: Mapping[str, Any], *, entry_price: float | None,
    single_remaining_quantity: int | None, sector_remaining_quantity: int | None,
    gross_remaining_quantity: int | None, margin_debt_remaining_quantity: int | None,
    portfolio_risk_quantity_ceiling: int | None,
) -> dict[str, Any]:
    """Cap research capacity again by margin-debt-to-NAV, gross exposure, concentration and the
    risk-budget ceiling itself -- a research funding ceiling never exceeds the risk ceiling it
    would fund.
    """
    if margin_economics.get("status") != MARGIN_STATUS_EVALUATED:
        return margin_economics
    capacity = dict(margin_economics["research_capacity"])
    candidates = [
        ("MARGIN_RESEARCH_CAPACITY_BEFORE_CAPS", capacity["capacity_before_portfolio_caps_quantity"]),
        ("SINGLE_POSITION", single_remaining_quantity),
        ("SECTOR", sector_remaining_quantity),
        ("GROSS_EXPOSURE", gross_remaining_quantity),
        ("MARGIN_DEBT", margin_debt_remaining_quantity),
        ("PORTFOLIO_RISK_QUANTITY_CEILING", portfolio_risk_quantity_ceiling),
    ]
    numeric = [(name, value) for name, value in candidates if value is not None]
    if not numeric:
        capped_by, final_quantity = [], None
    else:
        tightest_name, tightest_value = min(numeric, key=lambda pair: pair[1])
        final_quantity = max(0, math.floor(tightest_value))
        capped_by = [tightest_name] if tightest_name != "MARGIN_RESEARCH_CAPACITY_BEFORE_CAPS" else []
    capacity["final_margin_research_capacity_quantity"] = final_quantity
    capacity["final_margin_research_capacity_notional"] = (
        final_quantity * entry_price if (final_quantity is not None and entry_price is not None) else None
    )
    capacity["capped_by"] = capped_by
    result = dict(margin_economics)
    result["research_capacity"] = capacity
    result.pop("artifact_identity", None)
    result.pop("artifact_sha256", None)
    result.update(_identity("margin_economics", result))
    return result


# ── Portfolio action research decision ─────────────────────────────────────────

def _decide_portfolio_action_research(
    *, sizing_mode: str, position_state: str, posture: str,
    single_constraint: Mapping[str, Any], sector_constraint: Mapping[str, Any], gross_constraint: Mapping[str, Any],
    cash_reserve_constraint: Mapping[str, Any], risk_sizing: Mapping[str, Any],
    portfolio_risk_quantity_ceiling: int | None, tightest_name: str | None,
    constraints_not_evaluated: Sequence[str] = (),
) -> tuple[str, str, str]:
    if position_state == "EXCLUDED_INACTIVE":
        return "EXCLUDED_FROM_ACTIVE_PORTFOLIO", "NOT_APPLICABLE", "NONE"
    if posture == "INSUFFICIENT_CURRENT_RESEARCH":
        return "INSUFFICIENT_FOR_PORTFOLIO_DECISION", "NOT_APPLICABLE", "NONE"

    if sizing_mode == SIZING_MODE_NOT_APPLICABLE:
        if position_state in ("HELD", "HELD_ABOVE_POLICY_CAP"):
            if position_state == "HELD_ABOVE_POLICY_CAP":
                return "OVER_LIMIT_REVIEW", "NOT_APPLICABLE", "SINGLE_POSITION"
            return "HOLD_EXISTING_NO_ACTION", "NOT_APPLICABLE", "NONE"
        if posture in AVOID_LIKE_POSTURES:
            return "AVOID_NO_PORTFOLIO_ACTION", "NOT_APPLICABLE", "NONE"
        return "NO_ADD", "NOT_APPLICABLE", "NONE"

    is_probe = sizing_mode == SIZING_MODE_PROBE
    within_ceiling_state = "PROBE_WITHIN_RISK_CEILING" if is_probe else "ADD_WITHIN_RISK_CEILING"
    within_evaluated_state = "PROBE_WITHIN_EVALUATED_CONSTRAINTS" if is_probe else "ADD_WITHIN_EVALUATED_CONSTRAINTS"
    sizing_unavailable_state = "PROBE_ELIGIBLE_SIZING_UNAVAILABLE" if is_probe else "ADD_ELIGIBLE_SIZING_UNAVAILABLE"

    # Add/probe-eligible posture from here.
    if position_state == "HELD_ABOVE_POLICY_CAP":
        return "OVER_LIMIT_REVIEW", "BLOCKED_BY_CONSTRAINT", "SINGLE_POSITION"

    breached: list[str] = []
    if single_constraint.get("status") == "LIMIT_BREACH":
        breached.append("SINGLE_POSITION")
    if sector_constraint.get("status") == "LIMIT_BREACH":
        breached.append("SECTOR")
    if gross_constraint.get("status") == "LIMIT_BREACH":
        breached.append("GROSS_EXPOSURE")
    if cash_reserve_constraint.get("status") == "LIMIT_BREACH":
        breached.append("CASH_RESERVE")
    if risk_sizing.get("status") == "AVAILABLE" and (risk_sizing.get("risk_budget_quantity") or 0) <= 0:
        breached.append("RISK_BUDGET")
    if breached:
        binding = next(name for name in BINDING_CONSTRAINT_PRIORITY if name in breached)
        return "NO_ADD", "BLOCKED_BY_CONSTRAINT", binding

    if risk_sizing.get("status") != "AVAILABLE":
        return sizing_unavailable_state, "SIZING_UNAVAILABLE", "NONE"

    if portfolio_risk_quantity_ceiling is not None and portfolio_risk_quantity_ceiling <= 0:
        binding = tightest_name if tightest_name in BINDING_CONSTRAINT_PRIORITY else "RISK_BUDGET"
        return "NO_ADD", "BLOCKED_BY_CONSTRAINT", binding

    # Everything evaluable allows the add/probe, but at least one gating constraint (most
    # commonly SECTOR, when no governed classification resolved it) was never evaluated at all --
    # this is never described as fully constraint-qualified.
    if constraints_not_evaluated:
        return within_evaluated_state, "ELIGIBLE_TO_SIZE", "NONE"

    return within_ceiling_state, "ELIGIBLE_TO_SIZE", "NONE"


# ── Narrative (deterministic, template-based -- no invented facts) ────────────

def _build_narrative(
    *, sizing_mode: str, position_state: str, single_constraint: Mapping[str, Any], sector_constraint: Mapping[str, Any],
    gross_constraint: Mapping[str, Any], cash_reserve_constraint: Mapping[str, Any], margin_debt_constraint: Mapping[str, Any],
    risk_sizing: Mapping[str, Any], entry_basis: str, security_decision: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    support: list[str] = []
    counter: list[str] = []
    uncertainties: list[str] = []
    would_change: list[str] = []

    if sizing_mode == SIZING_MODE_FULL:
        support.append("SECURITY_POSTURE_ADD_ELIGIBLE")
    elif sizing_mode == SIZING_MODE_PROBE:
        support.append("SECURITY_POSTURE_PROBE_ELIGIBLE_EARLY_ENTRY")

    if single_constraint.get("status") == "WITHIN_LIMIT":
        support.append("SINGLE_POSITION_CAPACITY_AVAILABLE")
    elif single_constraint.get("status") == "LIMIT_BREACH":
        counter.append("SINGLE_POSITION_CAP_BREACHED")
        would_change.append("Single-position weight dropping back under the policy cap would clear this constraint.")

    if sector_constraint.get("status") == "NOT_EVALUATED_MISSING_SECTOR":
        uncertainties.append("SECTOR_NOT_EVALUATED_MISSING_GOVERNED_CLASSIFICATION")
        would_change.append(
            "An explicit or governed sector classification (e.g. the exchange industry-classification "
            "snapshot Financial V2 already consumes) would allow the sector constraint to be evaluated."
        )
    elif sector_constraint.get("status") == "UNAVAILABLE":
        uncertainties.append("SECTOR_POLICY_CAP_UNAVAILABLE")
        would_change.append("A sector policy cap (effective_policy.max_sector_weight) would allow the sector constraint to be evaluated.")
    elif sector_constraint.get("status") == "LIMIT_BREACH":
        counter.append("SECTOR_CAP_BREACHED")
        would_change.append("Sector weight dropping back under the policy cap would clear this constraint.")
    elif sector_constraint.get("status") == "WITHIN_LIMIT":
        support.append("SECTOR_CAPACITY_AVAILABLE")

    if gross_constraint.get("status") == "LIMIT_BREACH":
        counter.append("GROSS_EXPOSURE_CAP_BREACHED")
        would_change.append("Gross exposure dropping back under the policy cap would clear this constraint.")
    elif gross_constraint.get("status") == "WITHIN_LIMIT":
        support.append("GROSS_EXPOSURE_CAPACITY_AVAILABLE")

    if cash_reserve_constraint.get("status") == "LIMIT_BREACH":
        counter.append("CASH_RESERVE_ALREADY_BELOW_POLICY_FLOOR")
        would_change.append("Cash available rising back above the minimum reserve floor would clear this constraint.")
    elif cash_reserve_constraint.get("status") == "WITHIN_LIMIT":
        support.append("CASH_RESERVE_WITHIN_LIMIT")

    if margin_debt_constraint.get("status") == "LIMIT_BREACH":
        uncertainties.append("MARGIN_DEBT_ALREADY_ABOVE_POLICY_CAP")

    sizing_status = risk_sizing.get("status")
    if sizing_status == "UNAVAILABLE_MISSING_INVALIDATION":
        counter.append("INVALIDATION_LEVEL_MISSING")
        would_change.append("A structural invalidation level from the security decision would make risk-based sizing computable.")
    elif sizing_status == "UNAVAILABLE_MISSING_ENTRY_PRICE":
        counter.append("ENTRY_REFERENCE_PRICE_MISSING")
        would_change.append("A trigger level or current market price would make risk-based sizing computable.")
    elif sizing_status == "UNAVAILABLE_MISSING_NAV":
        uncertainties.append("EFFECTIVE_NAV_UNAVAILABLE")
        would_change.append("A broker-reported NAV, or priced positions plus cash, would make sizing and weight checks computable.")
    elif sizing_status == "UNAVAILABLE_DEGENERATE_DOWNSIDE":
        uncertainties.append("ENTRY_PRICE_EQUALS_INVALIDATION_PRICE")
    elif sizing_status == "UNAVAILABLE_MISSING_RISK_BUDGET_POLICY":
        uncertainties.append("RISK_BUDGET_POLICY_FIELD_UNAVAILABLE")

    if entry_basis == "CURRENT_MARKET_PRICE_FALLBACK":
        uncertainties.append("ENTRY_REFERENCE_PRICE_IS_CURRENT_MARKET_PRICE_NOT_A_TRIGGER_LEVEL")
    elif entry_basis == "UNAVAILABLE":
        uncertainties.append("ENTRY_REFERENCE_PRICE_UNAVAILABLE")

    if position_state == "HELD_ABOVE_POLICY_CAP":
        counter.append("EXISTING_POSITION_ABOVE_SINGLE_POSITION_CAP")
        would_change.append("This is a review flag, not a sell instruction; NAV growth or weight reduction elsewhere would clear it.")

    counter.extend(f"SECURITY_LEVEL:{item}" for item in (security_decision.get("counter_thesis") or [])[:5])

    dedupe = lambda items: list(dict.fromkeys(items))
    return dedupe(support), dedupe(counter), dedupe(uncertainties), dedupe(would_change)


# ── Per-ticker builder ─────────────────────────────────────────────────────────

_UNAVAILABLE_WEIGHT_CONSTRAINT = {"status": "UNAVAILABLE", "observed_weight": None, "limit": None,
                                  "remaining_weight": None, "remaining_notional": None, "remaining_quantity": None}
_UNAVAILABLE_AMOUNT_CONSTRAINT = {"status": "UNAVAILABLE", "observed_amount": None, "limit_amount": None, "remaining_amount": None}
_AUTHORITY_BOUNDARY = {
    "is_actionable": False,
    "security_attractiveness_separate_from_portfolio_fit": True,
    "no_forced_liquidation": True,
    "no_execution_authority": True,
    "no_fabricated_stop_price": True,
    "no_fabricated_margin_justification": True,
    "cost_basis_and_breakeven_are_context_only_never_a_market_trigger": True,
    "existing_exposure_above_cap_is_no_new_addition_not_an_automatic_sell": True,
}


def _cost_basis_context(pos: Mapping[str, Any] | None) -> dict[str, Any]:
    pos = pos or {}
    return {
        "cost_basis_per_share": pos.get("cost_basis_per_share"),
        "cost_basis_method": pos.get("cost_basis_method"),
        "lifetime_cash_recovery_breakeven": pos.get("lifetime_cash_recovery_breakeven"),
        "lifetime_cash_recovery_breakeven_method": pos.get("lifetime_cash_recovery_breakeven_method"),
        "position_episode_holding_days": pos.get("position_episode_holding_days"),
        "authority_boundary": {
            "context_only": True,
            "never_a_market_invalidation_stop_loss_or_sell_trigger": True,
        },
    }


def _not_evaluated_record(*, ticker: str, security_decision: Mapping[str, Any], posture: str, position_lane: str | None) -> dict[str, Any]:
    trigger = security_decision.get("trigger") or {}
    invalidation = security_decision.get("invalidation") or {}
    trigger_level = trigger.get("trigger_level")
    margin_economics = _margin_economics_not_applicable("PRIVATE_PORTFOLIO_STATE_NOT_PROVIDED")
    return {
        "ticker": ticker,
        "as_of_session": security_decision.get("as_of_session"),
        "security_research_action_posture": posture,
        "portfolio_action_research": "NOT_EVALUATED",
        "position_state": "NOT_HELD",
        "position_lane": position_lane if position_lane in POSITION_LANES else "UNSPECIFIED",
        "existing_position_lane_context": {},
        "sizing_mode": SIZING_MODE_NOT_APPLICABLE,
        "current_quantity": None,
        "current_weight": None,
        "current_weight_status": "UNAVAILABLE",
        "cost_basis_context": _cost_basis_context(None),
        "incremental_action_state": "NOT_APPLICABLE",
        "entry_reference_price": trigger_level,
        "entry_reference_price_basis": "TRIGGER_LEVEL" if trigger_level is not None else "UNAVAILABLE",
        "portfolio_risk_quantity_ceiling": None,
        "portfolio_risk_notional_ceiling": None,
        "risk_sizing_status": "UNAVAILABLE_PORTFOLIO_STATE_NOT_PROVIDED",
        "risk_sizing_context": {"status": "UNAVAILABLE_PORTFOLIO_STATE_NOT_PROVIDED"},
        "portfolio_risk_sizing": {
            "contract_version": RISK_SIZING_CONTRACT_VERSION,
            "status": "UNAVAILABLE_PORTFOLIO_STATE_NOT_PROVIDED",
            "sizing_mode": SIZING_MODE_NOT_APPLICABLE,
        },
        "execution_qualified_quantity": None,
        "execution_qualified_quantity_status": "NOT_EVALUATED",
        "execution_qualified_quantity_reason": "EXACT_LIQUIDITY_INPUTS_NOT_QUALIFIED",
        "cash_funding_capacity": {"status": "UNAVAILABLE", "cash_available": None, "cash_reserve_floor": None,
                                   "deployable_cash": None, "max_cash_fundable_quantity": None},
        "margin_account_context": {"current_margin_debt": None, "margin_available_minimum": None,
                                    "margin_available_maximum": None, "annual_margin_rate_percent": None},
        "margin_economics": margin_economics,
        "single_position_constraint": _UNAVAILABLE_WEIGHT_CONSTRAINT,
        "sector_constraint": _UNAVAILABLE_WEIGHT_CONSTRAINT,
        "gross_exposure_constraint": _UNAVAILABLE_WEIGHT_CONSTRAINT,
        "cash_reserve_constraint": _UNAVAILABLE_AMOUNT_CONSTRAINT,
        "margin_debt_constraint": _UNAVAILABLE_AMOUNT_CONSTRAINT,
        "risk_budget_constraint": {"status": "UNAVAILABLE_PORTFOLIO_STATE_NOT_PROVIDED", "risk_budget_fraction": None,
                                    "risk_budget_amount": None, "per_share_downside": None, "remaining_quantity": None},
        "binding_constraint": "NONE",
        "portfolio_constraint_completeness": "NOT_APPLICABLE",
        "constraints_evaluated": [],
        "constraints_not_evaluated": [],
        "trigger": trigger,
        "invalidation": invalidation,
        "security_counter_thesis": security_decision.get("counter_thesis") or [],
        "portfolio_thesis_support": [],
        "portfolio_counter_thesis": ["PRIVATE_PORTFOLIO_STATE_NOT_PROVIDED"],
        "material_uncertainties": ["PRIVATE_PORTFOLIO_STATE_NOT_PROVIDED"],
        "what_would_change_view": [
            "Importing a portfolio workbook (private_portfolio_context.import_workbook) would make portfolio-aware evaluation possible.",
        ],
        "evidence_lineage": {
            "portfolio_state_identity": None, "security_decision_identity": security_decision.get("decision_identity"),
            "governed_sector_snapshot_identity": None,
        },
        "authority_boundary": dict(_AUTHORITY_BOUNDARY),
    }


def build_ticker_portfolio_aware_decision(
    *, ticker: str, portfolio_state: Mapping[str, Any], security_decision: Mapping[str, Any] | None,
    position_lane: str | None = None, reward_boundary: float | None = None,
) -> dict[str, Any]:
    """Build one ticker's ``portfolio_aware_decision/v1`` record.

    ``reward_boundary`` is an optional, explicit, caller-supplied deterministic tactical
    upside/target (or equivalent existing reward boundary) for the margin-economics
    calculation. Nothing upstream in this repository emits one today (no target price is ever
    fabricated anywhere in this codebase); when absent, margin economics reports
    ``NOT_EVALUATED`` rather than inventing a target or a probability.
    """
    ticker = str(ticker).upper()
    security_decision = security_decision or {}
    posture = security_decision.get("research_action_posture") or "INSUFFICIENT_CURRENT_RESEARCH"

    if portfolio_state.get("status") != "AVAILABLE":
        record = _not_evaluated_record(ticker=ticker, security_decision=security_decision, posture=posture, position_lane=position_lane)
        record["portfolio_decision_identity"] = _decision_identity(record)
        return record

    trigger = security_decision.get("trigger") or {}
    invalidation = security_decision.get("invalidation") or {}

    default_pos = {
        "current_quantity": 0.0, "current_price": (portfolio_state.get("prices") or {}).get(ticker),
        "current_market_value": 0.0, "current_weight": 0.0 if portfolio_state.get("effective_nav") else None,
        "current_weight_status": "AVAILABLE" if portfolio_state.get("effective_nav") else "UNAVAILABLE_NO_PRICE_OR_NAV",
        "sector": (portfolio_state.get("sector_by_ticker") or {}).get(ticker),
        "sector_source": (portfolio_state.get("sector_source_by_ticker") or {}).get(ticker, SECTOR_SOURCE_NOT_EVALUATED),
        "is_active": True, "existing_position_lane_context": {}, "lane_reconciliation": "NO_LANE_INPUT_ALL_UNSPECIFIED",
    }
    pos = (portfolio_state.get("positions") or {}).get(ticker) or default_pos
    current_quantity = pos.get("current_quantity") or 0.0
    is_active = pos.get("is_active", True)

    effective_policy = portfolio_state.get("effective_policy") or {}
    max_single = effective_policy.get("max_single_position_weight")
    max_sector = effective_policy.get("max_sector_weight")
    max_gross = effective_policy.get("max_gross_exposure_to_nav")
    min_cash_reserve = effective_policy.get("minimum_cash_reserve_to_nav")
    max_margin_debt = effective_policy.get("max_margin_debt_to_nav")
    risk_budget_fraction = effective_policy.get("risk_budget_per_investment_decision_to_nav")
    probe_multiplier = effective_policy.get("probe_risk_budget_multiplier")
    tactical_margin_holding_days = effective_policy.get("tactical_margin_holding_days")
    min_net_reward_risk_for_margin = effective_policy.get("min_net_reward_risk_for_margin")
    strong_net_reward_risk_for_max_margin = effective_policy.get("strong_net_reward_risk_for_max_margin")
    max_financing_cost_fraction_of_gross_upside = effective_policy.get("max_financing_cost_fraction_of_gross_upside")

    effective_nav = portfolio_state.get("effective_nav")

    if not is_active:
        position_state = "EXCLUDED_INACTIVE"
    elif current_quantity > 0:
        weight = pos.get("current_weight")
        position_state = "HELD_ABOVE_POLICY_CAP" if (max_single is not None and weight is not None and weight > max_single + _EPS) else "HELD"
    else:
        position_state = "NOT_HELD"

    entry_price = trigger.get("trigger_level")
    entry_basis = "TRIGGER_LEVEL"
    if entry_price is None:
        entry_price = pos.get("current_price")
        entry_basis = "CURRENT_MARKET_PRICE_FALLBACK" if entry_price is not None else "UNAVAILABLE"
    invalidation_price = invalidation.get("invalidation_level")

    add_eligible = posture in ADD_ELIGIBLE_POSTURES
    probe_eligible = (not add_eligible) and _probe_eligible(posture=posture, invalidation_price=invalidation_price, entry_price=entry_price)
    if position_state == "EXCLUDED_INACTIVE" or posture == "INSUFFICIENT_CURRENT_RESEARCH":
        sizing_mode = SIZING_MODE_NOT_APPLICABLE
    elif add_eligible:
        sizing_mode = SIZING_MODE_FULL
    elif probe_eligible:
        sizing_mode = SIZING_MODE_PROBE
    else:
        sizing_mode = SIZING_MODE_NOT_APPLICABLE

    if sizing_mode == SIZING_MODE_PROBE:
        effective_risk_budget_fraction = (
            risk_budget_fraction * probe_multiplier
            if (risk_budget_fraction is not None and probe_multiplier is not None) else None
        )
    elif sizing_mode == SIZING_MODE_FULL:
        effective_risk_budget_fraction = risk_budget_fraction
    else:
        effective_risk_budget_fraction = None

    single_constraint = _weight_constraint(observed_weight=pos.get("current_weight"), limit=max_single, effective_nav=effective_nav, entry_price=entry_price)

    sector = pos.get("sector")
    sector_source = pos.get("sector_source", SECTOR_SOURCE_NOT_EVALUATED)
    if sector is None:
        # Missing evidence is not evidence of zero sector exposure: this is an explicit
        # not-evaluated state, never UNCONSTRAINED.
        sector_constraint = {"status": "NOT_EVALUATED_MISSING_SECTOR", "reason": "GOVERNED_SECTOR_CLASSIFICATION_NOT_AVAILABLE",
                              "observed_weight": None, "limit": max_sector, "sector_source": sector_source,
                              "remaining_weight": None, "remaining_notional": None, "remaining_quantity": None}
    else:
        sector_weight = (portfolio_state.get("sector_weights") or {}).get(sector, 0.0)
        sector_constraint = {
            **_weight_constraint(observed_weight=sector_weight, limit=max_sector, effective_nav=effective_nav, entry_price=entry_price),
            "sector_source": sector_source,
        }

    gross_constraint = _weight_constraint(observed_weight=portfolio_state.get("gross_exposure_weight"), limit=max_gross, effective_nav=effective_nav, entry_price=entry_price)
    cash_reserve_constraint = _floor_amount_constraint(observed_amount=portfolio_state.get("cash_available"), floor_fraction=min_cash_reserve, effective_nav=effective_nav)
    margin_debt_constraint = _ceiling_amount_constraint(observed_amount=portfolio_state.get("margin_debt"), cap_fraction=max_margin_debt, effective_nav=effective_nav)
    margin_debt_remaining_quantity = (
        math.floor(margin_debt_constraint["remaining_amount"] / entry_price)
        if (margin_debt_constraint.get("remaining_amount") is not None and entry_price) else None
    )

    risk_sizing = _compute_risk_sizing(entry_price=entry_price, invalidation_price=invalidation_price, effective_nav=effective_nav, risk_budget_fraction=effective_risk_budget_fraction)

    ceiling_candidates = [
        ("RISK_BUDGET", risk_sizing.get("risk_budget_quantity")),
        ("SINGLE_POSITION", single_constraint.get("remaining_quantity")),
        ("SECTOR", sector_constraint.get("remaining_quantity")),
        ("GROSS_EXPOSURE", gross_constraint.get("remaining_quantity")),
    ]
    numeric_candidates = [(name, value) for name, value in ceiling_candidates if value is not None]
    portfolio_risk_quantity_ceiling = None
    tightest_name = None
    if risk_sizing.get("status") == "AVAILABLE" and numeric_candidates:
        tightest_name, tightest_value = min(numeric_candidates, key=lambda pair: pair[1])
        portfolio_risk_quantity_ceiling = max(0, math.floor(tightest_value))
    portfolio_risk_notional_ceiling = (
        portfolio_risk_quantity_ceiling * entry_price
        if (portfolio_risk_quantity_ceiling is not None and entry_price is not None) else None
    )

    cash_available = portfolio_state.get("cash_available")
    cash_reserve_floor = (min_cash_reserve * effective_nav) if (min_cash_reserve is not None and effective_nav) else None
    deployable_cash = None
    max_cash_fundable_quantity = None
    if cash_available is not None and cash_reserve_floor is not None:
        deployable_cash = max(0.0, cash_available - cash_reserve_floor)
        if entry_price:
            max_cash_fundable_quantity = math.floor(deployable_cash / entry_price)
    cash_funding_capacity = {
        "status": "AVAILABLE" if deployable_cash is not None else "UNAVAILABLE",
        "cash_available": cash_available, "cash_reserve_floor": cash_reserve_floor,
        "deployable_cash": deployable_cash, "max_cash_fundable_quantity": max_cash_fundable_quantity,
    }

    margin_min = portfolio_state.get("margin_available_minimum")
    margin_max = portfolio_state.get("margin_available_maximum")
    annual_margin_rate_percent = portfolio_state.get("annual_margin_rate_percent")
    margin_account_context = {
        "current_margin_debt": portfolio_state.get("margin_debt"),
        "margin_available_minimum": margin_min,
        "margin_available_maximum": margin_max,
        "annual_margin_rate_percent": annual_margin_rate_percent,
    }

    margin_economics = _evaluate_margin_economics(
        sizing_mode=sizing_mode, entry_price=entry_price, invalidation_price=invalidation_price,
        reward_boundary=reward_boundary, annual_margin_rate_percent=annual_margin_rate_percent,
        margin_available_minimum=margin_min, margin_available_maximum=margin_max,
        tactical_margin_holding_days=_num(tactical_margin_holding_days),
        min_net_reward_risk_for_margin=_num(min_net_reward_risk_for_margin),
        strong_net_reward_risk_for_max_margin=_num(strong_net_reward_risk_for_max_margin),
        max_financing_cost_fraction_of_gross_upside=_num(max_financing_cost_fraction_of_gross_upside),
    )
    margin_economics = _apply_portfolio_caps_to_margin_capacity(
        margin_economics, entry_price=entry_price,
        single_remaining_quantity=single_constraint.get("remaining_quantity"),
        sector_remaining_quantity=sector_constraint.get("remaining_quantity"),
        gross_remaining_quantity=gross_constraint.get("remaining_quantity"),
        margin_debt_remaining_quantity=margin_debt_remaining_quantity,
        portfolio_risk_quantity_ceiling=portfolio_risk_quantity_ceiling,
    )

    portfolio_constraint_completeness, constraints_evaluated, constraints_not_evaluated = _constraint_completeness(
        single_constraint=single_constraint, sector_constraint=sector_constraint, gross_constraint=gross_constraint,
        cash_reserve_constraint=cash_reserve_constraint, risk_sizing=risk_sizing,
    )

    portfolio_action_research, incremental_action_state, binding_constraint = _decide_portfolio_action_research(
        sizing_mode=sizing_mode, position_state=position_state, posture=posture,
        single_constraint=single_constraint, sector_constraint=sector_constraint, gross_constraint=gross_constraint,
        cash_reserve_constraint=cash_reserve_constraint, risk_sizing=risk_sizing,
        portfolio_risk_quantity_ceiling=portfolio_risk_quantity_ceiling, tightest_name=tightest_name,
        constraints_not_evaluated=constraints_not_evaluated,
    )

    lane = position_lane if position_lane in POSITION_LANES else ("TACTICAL" if sizing_mode != SIZING_MODE_NOT_APPLICABLE else "UNSPECIFIED")

    thesis_support, portfolio_counter_thesis, uncertainties, what_would_change = _build_narrative(
        sizing_mode=sizing_mode, position_state=position_state, single_constraint=single_constraint, sector_constraint=sector_constraint,
        gross_constraint=gross_constraint, cash_reserve_constraint=cash_reserve_constraint, margin_debt_constraint=margin_debt_constraint,
        risk_sizing=risk_sizing, entry_basis=entry_basis, security_decision=security_decision,
    )

    portfolio_risk_sizing = {
        "contract_version": RISK_SIZING_CONTRACT_VERSION,
        "status": risk_sizing.get("status"),
        "sizing_mode": sizing_mode,
        "risk_budget_fraction_used": effective_risk_budget_fraction,
        "probe_risk_budget_multiplier_applied": probe_multiplier if sizing_mode == SIZING_MODE_PROBE else None,
        "entry_reference_price": entry_price,
        "invalidation_level": invalidation_price,
        "per_share_downside": risk_sizing.get("per_share_downside"),
        "ceilings": {
            "risk_budget_quantity": risk_sizing.get("risk_budget_quantity"),
            "single_position_quantity": single_constraint.get("remaining_quantity"),
            "sector_quantity": sector_constraint.get("remaining_quantity"),
            "gross_exposure_quantity": gross_constraint.get("remaining_quantity"),
            "cash_funded_quantity": max_cash_fundable_quantity,
        },
        "portfolio_risk_quantity_ceiling": portfolio_risk_quantity_ceiling,
        "portfolio_risk_notional_ceiling": portfolio_risk_notional_ceiling,
        "binding_constraint": binding_constraint,
        "constraints_evaluated": constraints_evaluated,
        "constraints_not_evaluated": constraints_not_evaluated,
    }
    portfolio_risk_sizing.update(_identity("portfolio_risk_sizing", portfolio_risk_sizing))

    record: dict[str, Any] = {
        "ticker": ticker,
        "as_of_session": security_decision.get("as_of_session") or portfolio_state.get("as_of_date"),
        "security_research_action_posture": posture,
        "portfolio_action_research": portfolio_action_research,
        "position_state": position_state,
        "position_lane": lane,
        "existing_position_lane_context": pos.get("existing_position_lane_context") or {},
        "sizing_mode": sizing_mode,
        "current_quantity": current_quantity,
        "current_weight": pos.get("current_weight"),
        "current_weight_status": pos.get("current_weight_status"),
        "cost_basis_context": _cost_basis_context(pos),
        "incremental_action_state": incremental_action_state,
        "entry_reference_price": entry_price,
        "entry_reference_price_basis": entry_basis,
        "portfolio_risk_quantity_ceiling": portfolio_risk_quantity_ceiling,
        "portfolio_risk_notional_ceiling": portfolio_risk_notional_ceiling,
        "risk_sizing_status": risk_sizing.get("status"),
        "risk_sizing_context": risk_sizing,
        "portfolio_risk_sizing": portfolio_risk_sizing,
        "execution_qualified_quantity": None,
        "execution_qualified_quantity_status": "NOT_EVALUATED",
        "execution_qualified_quantity_reason": "EXACT_LIQUIDITY_INPUTS_NOT_QUALIFIED",
        "cash_funding_capacity": cash_funding_capacity,
        "margin_account_context": margin_account_context,
        "margin_economics": margin_economics,
        "single_position_constraint": single_constraint,
        "sector_constraint": sector_constraint,
        "gross_exposure_constraint": gross_constraint,
        "cash_reserve_constraint": cash_reserve_constraint,
        "margin_debt_constraint": margin_debt_constraint,
        "risk_budget_constraint": {
            "status": risk_sizing.get("status"), "risk_budget_fraction": effective_risk_budget_fraction,
            "risk_budget_amount": risk_sizing.get("risk_budget_amount"), "per_share_downside": risk_sizing.get("per_share_downside"),
            "remaining_quantity": risk_sizing.get("risk_budget_quantity"),
        },
        "binding_constraint": binding_constraint,
        "portfolio_constraint_completeness": portfolio_constraint_completeness,
        "constraints_evaluated": constraints_evaluated,
        "constraints_not_evaluated": constraints_not_evaluated,
        "trigger": trigger,
        "invalidation": invalidation,
        "security_counter_thesis": security_decision.get("counter_thesis") or [],
        "portfolio_thesis_support": thesis_support,
        "portfolio_counter_thesis": portfolio_counter_thesis,
        "material_uncertainties": list(dict.fromkeys(uncertainties + (security_decision.get("material_uncertainties") or [])[:5])),
        "what_would_change_view": what_would_change,
        "evidence_lineage": {
            "portfolio_state_identity": (portfolio_state.get("source_identities") or {}).get("portfolio_snapshot_identity"),
            "security_decision_identity": security_decision.get("decision_identity"),
            "governed_sector_snapshot_identity": (portfolio_state.get("source_identities") or {}).get("governed_sector_snapshot_identity"),
        },
        "authority_boundary": dict(_AUTHORITY_BOUNDARY),
    }
    record["portfolio_decision_identity"] = _decision_identity(record)
    return record


# ── Market-wide artifact builder ───────────────────────────────────────────────

def build_artifact(
    *, session: str, requested_at: str, portfolio_state: Mapping[str, Any],
    integrated_decision_artifact: Mapping[str, Any], position_lanes_by_ticker: Mapping[str, str] | None = None,
    reward_boundary_by_ticker: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    records_in = integrated_decision_artifact.get("records") or {}
    lanes_by_ticker = position_lanes_by_ticker or {}
    reward_boundaries = reward_boundary_by_ticker or {}
    records: dict[str, Any] = {}
    action_counts: dict[str, int] = {}
    binding_counts: dict[str, int] = {}
    completeness_counts: dict[str, int] = {}
    margin_band_counts: dict[str, int] = {}
    margin_status_counts: dict[str, int] = {}
    for ticker in sorted(records_in):
        record = build_ticker_portfolio_aware_decision(
            ticker=ticker, portfolio_state=portfolio_state, security_decision=records_in[ticker],
            position_lane=lanes_by_ticker.get(ticker), reward_boundary=_num(reward_boundaries.get(ticker)),
        )
        records[ticker] = record
        action = record["portfolio_action_research"]
        binding = record["binding_constraint"]
        completeness = record["portfolio_constraint_completeness"]
        margin_status = record["margin_economics"]["status"]
        margin_band = record["margin_economics"]["margin_research_band"]
        action_counts[action] = action_counts.get(action, 0) + 1
        binding_counts[binding] = binding_counts.get(binding, 0) + 1
        completeness_counts[completeness] = completeness_counts.get(completeness, 0) + 1
        margin_status_counts[margin_status] = margin_status_counts.get(margin_status, 0) + 1
        margin_band_counts[margin_band] = margin_band_counts.get(margin_band, 0) + 1

    active_position_count = sum(
        1 for pos in (portfolio_state.get("positions") or {}).values()
        if pos.get("is_active", True) and (pos.get("current_quantity") or 0) > 0
    )

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "session": session,
        "requested_at": requested_at,
        "records": records,
        "coverage": {
            "security_denominator": len(records_in),
            "portfolio_state_status": portfolio_state.get("status"),
            "active_position_count": active_position_count,
            "by_portfolio_action_research": dict(sorted(action_counts.items())),
            "by_binding_constraint": dict(sorted(binding_counts.items())),
            "by_portfolio_constraint_completeness": dict(sorted(completeness_counts.items())),
            "by_margin_economics_status": dict(sorted(margin_status_counts.items())),
            "by_margin_research_band": dict(sorted(margin_band_counts.items())),
        },
        "source_artifact_identities": {
            "portfolio_state_identity": (portfolio_state.get("source_identities") or {}).get("portfolio_snapshot_identity"),
            "integrated_investment_decision_product_identity": integrated_decision_artifact.get("artifact_identity"),
        },
        "authority_boundary": {
            "is_actionable": False,
            "security_attractiveness_separate_from_portfolio_fit": True,
            "no_forced_liquidation": True,
            "no_execution_or_liquidity_authority_promotion": True,
        },
    }
    artifact.update(content_identity(artifact))
    return artifact


def public_console_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Safe CLI surface: identities/counts/reason-codes only, never private holdings,
    quantities, prices, NAV, cash, margin balances, or sizing values.
    """
    coverage = artifact.get("coverage") or {}
    return {
        "status": "EVALUATED",
        "milestone": MILESTONE,
        "session": artifact.get("session"),
        "portfolio_aware_decision_identity": artifact.get("artifact_identity"),
        "portfolio_state_status": coverage.get("portfolio_state_status"),
        "active_position_count": coverage.get("active_position_count"),
        "security_denominator": coverage.get("security_denominator"),
        "by_portfolio_action_research": coverage.get("by_portfolio_action_research"),
        "by_binding_constraint": coverage.get("by_binding_constraint"),
        "by_portfolio_constraint_completeness": coverage.get("by_portfolio_constraint_completeness"),
        "by_margin_economics_status": coverage.get("by_margin_economics_status"),
        "by_margin_research_band": coverage.get("by_margin_research_band"),
        "execution_qualified_count": 0,
        "execution_qualified_quantity_status": "NOT_QUALIFIED_EXACT_LIQUIDITY_AUTHORITY_ABSENT",
        "source_artifact_identities": artifact.get("source_artifact_identities"),
    }


# ── Optional local Daily integration boundary (demonstration only; never imported by
# canonical_post_close_pipeline.py or any other frozen production path) ───────────────

def build_private_overlay_or_skip(
    *, session: str, requested_at: str, portfolio_snapshot: Mapping[str, Any] | None,
    integrated_decision_artifact: Mapping[str, Any], prices: Mapping[str, Any] | None = None,
    sector_by_ticker: Mapping[str, Any] | None = None, governed_sector_snapshot: Mapping[str, Any] | None = None,
    position_lanes: Mapping[str, Mapping[str, Any]] | None = None, excluded_tickers: Sequence[str] | None = None,
    position_lanes_by_ticker: Mapping[str, str] | None = None, reward_boundary_by_ticker: Mapping[str, float] | None = None,
) -> dict[str, Any] | None:
    """Shows the intended shape of a future local Daily integration: PUBLIC Current Research
    Daily -> Integrated Investment Decision -> (if private portfolio context exists) build a
    PRIVATE portfolio-aware overlay locally, else skip cleanly.

    Returns ``None`` when no private portfolio snapshot is supplied. Not wired into
    ``canonical_post_close_pipeline.py`` or any other frozen production path.
    """
    if not isinstance(portfolio_snapshot, Mapping) or "positions" not in portfolio_snapshot:
        return None
    portfolio_state = derive_portfolio_state(
        portfolio_snapshot=portfolio_snapshot, prices=prices, sector_by_ticker=sector_by_ticker,
        governed_sector_snapshot=governed_sector_snapshot, position_lanes=position_lanes,
        excluded_tickers=excluded_tickers,
    )
    return build_artifact(
        session=session, requested_at=requested_at, portfolio_state=portfolio_state,
        integrated_decision_artifact=integrated_decision_artifact, position_lanes_by_ticker=position_lanes_by_ticker,
        reward_boundary_by_ticker=reward_boundary_by_ticker,
    )


# ── CLI-facing retained-artifact resolution (read-only; no Daily run, no provider call) ────

def default_latest_completed_session(repo_root: Path) -> str | None:
    """Lexicographically latest ``operations-review/canonical-post-close-v1/<date>`` directory
    that already has a materialized Integrated Decision artifact.

    Matches the established idiom in this codebase (``daily_session_level2_package.
    _latest_official_event_context_dir``): a sorted glob of dated directories, never an mtime
    scan and never a second calendar. Returns ``None`` when nothing has ever completed.
    """
    ops = repo_root / "operations-review" / "canonical-post-close-v1"
    if not ops.is_dir():
        return None
    candidates = sorted(
        candidate.name for candidate in ops.iterdir()
        if candidate.is_dir() and (candidate / "enrichment" / "integrated_investment_decision_product.json").is_file()
    )
    return candidates[-1] if candidates else None


def load_integrated_decision_artifact(repo_root: Path, session: str) -> dict[str, Any]:
    """Read the already-retained, already-completed Integrated Decision artifact for ``session``.

    Read-only: this never triggers Daily, never calls a market-data provider, and never
    recomputes the security decision -- it is exactly the same bytes canonical_post_close_
    pipeline.py already wrote to this path on that session's real run.
    """
    path = repo_root / "operations-review" / "canonical-post-close-v1" / session / "enrichment" / "integrated_investment_decision_product.json"
    if not path.is_file():
        raise FileNotFoundError(f"INTEGRATED_DECISION_ARTIFACT_NOT_RETAINED_FOR_SESSION:{session}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_descriptive_prices(repo_root: Path, session: str) -> dict[str, float]:
    """Best-effort current-session close prices from the same session's retained descriptive
    research artifact (the same field ``current_portfolio_risk_envelope.py`` already reads:
    ``records[ticker].technical_features.values.close``). Returns ``{}`` when not retained --
    weight/sizing computations then honestly report ``UNAVAILABLE_NO_PRICE_OR_NAV`` rather than
    guessing a price.
    """
    nodash = session.replace("-", "")
    path = (
        repo_root / "operations-review" / f"market-wide-current-descriptive-research-v1-{nodash}"
        / "market_wide_current_descriptive_research_artifact.json"
    )
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    prices: dict[str, float] = {}
    for ticker, record in (data.get("records") or {}).items():
        technical_features = (record or {}).get("technical_features") or {}
        close = (technical_features.get("values") or {}).get("close")
        value = _num(close)
        if value is not None:
            prices[str(ticker).upper()] = value
    return prices


_DEFAULT_SECTOR_SNAPSHOT_PATH = Path("operations-review/market-wide-financial-entity-classification-scaleout-v1-20260901/exchange_industry_classification_snapshot.json")


def load_governed_sector_snapshot(repo_root: Path, *, explicit_path: Path | None = None) -> dict[str, Any] | None:
    """Best-effort load of an already-retained ``exchange_industry_classification`` snapshot.

    A missing snapshot is not an error: ``resolve_sector_by_ticker`` already reports
    ``NOT_EVALUATED_MISSING_SECTOR`` per ticker rather than fabricating a sector.
    """
    path = explicit_path or (repo_root / _DEFAULT_SECTOR_SNAPSHOT_PATH)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_from_retained_artifacts(
    *, repo_root: Path, session: str | None = None, portfolio_root: Path | None = None,
    sector_snapshot_path: Path | None = None, position_lanes_by_ticker: Mapping[str, str] | None = None,
    excluded_tickers: Sequence[str] | None = None, requested_at: str,
) -> dict[str, Any]:
    """One deterministic, read-only evaluation over already-retained artifacts.

    Never runs Daily, never calls a provider, never parses the owner workbook (that is
    Foundation's job -- this only reads the private artifacts it already produced). Raises
    ``FileNotFoundError`` if no completed session (explicit or latest) has a retained Integrated
    Decision artifact, and returns a well-formed ``NOT_PROVIDED`` per-ticker state (never raises)
    when the private portfolio has simply never been imported.
    """
    resolved_session = session or default_latest_completed_session(repo_root)
    if not resolved_session:
        raise FileNotFoundError("NO_RETAINED_COMPLETED_INTEGRATED_DECISION_SESSION_AVAILABLE")
    integrated_decision_artifact = load_integrated_decision_artifact(repo_root, resolved_session)
    status = _private_portfolio_context.portfolio_status(portfolio_root=portfolio_root)
    portfolio_snapshot = status.get("snapshot") if status.get("status") == "READY" else None
    prices = load_descriptive_prices(repo_root, resolved_session)
    governed_sector_snapshot = load_governed_sector_snapshot(repo_root, explicit_path=sector_snapshot_path)
    portfolio_state = derive_portfolio_state(
        portfolio_snapshot=portfolio_snapshot, prices=prices, governed_sector_snapshot=governed_sector_snapshot,
        position_lanes=None, excluded_tickers=excluded_tickers,
    )
    return build_artifact(
        session=resolved_session, requested_at=requested_at, portfolio_state=portfolio_state,
        integrated_decision_artifact=integrated_decision_artifact, position_lanes_by_ticker=position_lanes_by_ticker,
    )


def write_private_artifact(artifact: Mapping[str, Any], *, portfolio_root: Path | None = None) -> Path:
    """Persist the full artifact under the sole private output root, never under Git,
    ``operations-review/``, the Dashboard, or the AI-handoff repository.
    """
    root = (
        (portfolio_root.expanduser().resolve() / "portfolio_aware_decisions")
        if portfolio_root is not None else default_private_output_root()
    )
    session = artifact.get("session") or "unknown-session"
    destination = root / session / "portfolio_aware_decision_v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(artifact) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    import os as _os
    _os.replace(temporary, destination)
    return destination


def project_portfolio_fit_for_integrated_decision(portfolio_state: Mapping[str, Any], ticker: str) -> dict[str, Any]:
    """Shape one ticker's portfolio state into the ad hoc ``portfolio_record`` shape
    ``integrated_investment_decision_product.build_ticker_integrated_decision()`` already
    accepts (``is_held`` / ``concentration_flag`` / ``sector_overlap`` / ``status``) -- the same
    shape that feeds the existing ``PORTFOLIO_FIT`` evidence axis. Demonstration/adapter only.
    """
    ticker = str(ticker).upper()
    if portfolio_state.get("status") != "AVAILABLE":
        return {"status": "NOT_PROVIDED", "is_held": False,
                "policy_note": "No explicit portfolio supplied; security attractiveness is independently evaluated."}
    pos = (portfolio_state.get("positions") or {}).get(ticker) or {}
    is_held = bool(pos and (pos.get("current_quantity") or 0) > 0 and pos.get("is_active", True))
    weight = pos.get("current_weight")
    max_single = (portfolio_state.get("effective_policy") or {}).get("max_single_position_weight")
    concentration_flag = bool(weight is not None and max_single is not None and weight > max_single + _EPS)
    sector = pos.get("sector") or (portfolio_state.get("sector_by_ticker") or {}).get(ticker)
    sector_weight = (portfolio_state.get("sector_weights") or {}).get(sector) if sector else None
    max_sector = (portfolio_state.get("effective_policy") or {}).get("max_sector_weight")
    sector_overlap = bool(sector_weight is not None and max_sector is not None and sector_weight > max_sector + _EPS)
    return {"status": "AVAILABLE", "is_held": is_held, "concentration_flag": concentration_flag, "sector_overlap": sector_overlap}
