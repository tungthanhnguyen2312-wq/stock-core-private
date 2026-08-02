"""Ticker Capability Matrix (P1.5): pure, deterministic eligibility across five
capability tiers, gated exclusively on already-computed Producer contracts.

Scope discipline, matching analysis_lane_eligibility.py: this module never re-resolves a
source identity, never fetches or recomputes evidence, never infers a tier from mere
availability, and never grants a market-dependent capability because a technical field is
merely present. Every input must already be the output of an existing qualified contract
(build_price_basis_contract(), build_distribution_evidence_for_ticker(),
build_historical_fundamental_brief(), or the current-share transition resolver).

Tiers (independently evaluated -- not assumed cumulative in this implementation):
  T0_informational          -- always eligible; profile/news/sector context only.
  T1_technical_display      -- OHLCV/technical coverage exists. Display and single-series
                                pattern reading only -- no return, no adjusted comparison,
                                no cross-corporate-action comparison, no liquidity claim,
                                regardless of price/volume basis state.
  T2_historical_fundamental -- an available historical_fundamental_brief with at least one
                                qualified fact for this ticker.
  T3_distribution_event     -- distribution_evidence.coverage_status == "available" with at
                                least one qualified cash or non-cash distribution event.
  T4_market_dependent       -- price basis is_actionable AND volume basis verified AND
                                current shares proven through the trusted session. All three
                                required; missing any one blocks the tier entirely.

is_actionable is hardcoded False everywhere in this module's output -- it produces
capability gating only, never an investment signal, matching Phase 4B's
analysis_lane_eligibility.py convention exactly.
"""
from __future__ import annotations

from typing import Any, Mapping

VERSION = "1.0.0"

TIERS: tuple[str, ...] = (
    "T0_informational",
    "T1_technical_display",
    "T2_historical_fundamental",
    "T3_distribution_event",
    "T4_market_dependent",
)


def _tier(eligible: bool, reason: str) -> dict[str, Any]:
    return {"eligible": bool(eligible), "reason": reason, "is_actionable": False}


def evaluate_ticker_capability(
    ticker: str,
    *,
    has_technical_coverage: bool,
    historical_fundamental_brief: Mapping[str, Any] | None,
    distribution_evidence: Mapping[str, Any] | None,
    price_basis_provenance: Mapping[str, Any] | None,
    current_shares_proven: bool,
) -> dict[str, Any]:
    """Pure. No I/O, no network, no database access. Returns
    {"schema_version", "ticker", "tiers": {tier_name: {"eligible", "reason",
    "is_actionable": False}}, "is_actionable": False}.
    """
    price_basis_provenance = price_basis_provenance if isinstance(price_basis_provenance, Mapping) else {}
    tiers: dict[str, dict[str, Any]] = {
        "T0_informational": _tier(True, "always eligible: profile/news/sector context only"),
        "T1_technical_display": _tier(
            has_technical_coverage,
            "OHLCV/technical coverage present; display and single-series pattern reading only, "
            "regardless of price or volume basis state" if has_technical_coverage
            else "no technical coverage retained for this ticker",
        ),
    }

    brief = historical_fundamental_brief if isinstance(historical_fundamental_brief, Mapping) else None
    brief_ok = bool(brief) and brief.get("status") == "available" and bool(brief.get("facts"))
    tiers["T2_historical_fundamental"] = _tier(
        brief_ok,
        "available historical_fundamental_brief with at least one qualified fact" if brief_ok
        else "no available historical_fundamental_brief with qualified facts for this ticker",
    )

    dist = distribution_evidence if isinstance(distribution_evidence, Mapping) else None
    event_count = 0
    if dist is not None:
        event_count = len(dist.get("cash_distributions") or []) + len(dist.get("non_cash_distributions") or [])
    dist_ok = bool(dist) and dist.get("coverage_status") == "available" and event_count > 0
    tiers["T3_distribution_event"] = _tier(
        dist_ok,
        f"{event_count} qualified distribution event(s), coverage_status=available" if dist_ok
        else "no qualified distribution event for this ticker",
    )

    price_ok = price_basis_provenance.get("is_actionable") is True
    volume_ok = price_basis_provenance.get("volume_basis_verified") is True
    shares_ok = current_shares_proven is True
    market_ok = price_ok and volume_ok and shares_ok
    blocking = [name for name, ok in (
        ("price_basis", price_ok), ("volume_basis", volume_ok), ("current_shares", shares_ok),
    ) if not ok]
    tiers["T4_market_dependent"] = _tier(
        market_ok,
        "price basis, volume basis, and current shares are all qualified through the trusted session" if market_ok
        else f"blocked on: {', '.join(blocking)}",
    )

    return {"schema_version": VERSION, "ticker": ticker, "tiers": tiers, "is_actionable": False}
