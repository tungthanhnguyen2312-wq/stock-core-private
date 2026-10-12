"""Compact current-session liquidity and explicit-portfolio research projections.

This module consumes precomputed completed-session risk output.  It deliberately
does not calculate execution capacity, position sizes, or recommendations.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "research_liquidity_and_explicit_portfolio/v1"
LOOKBACKS = ("L20", "L60", "L120", "L250")


def _identity(kind: str, value: Mapping[str, Any]) -> dict[str, str]:
    payload = {k: v for k, v in value.items() if k not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{kind}:{digest}"}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _positions(portfolio: Mapping[str, Any], prices: Mapping[str, Any]) -> tuple[list[dict[str, Any]], float]:
    positions = portfolio.get("positions")
    if not portfolio.get("portfolio_id") or not isinstance(positions, list) or not positions:
        raise ValueError("EXPLICIT_PORTFOLIO_POSITIONS_REQUIRED")
    rows: list[dict[str, Any]] = []
    for position in positions:
        ticker = str(position.get("ticker") or "").upper()
        supplied = [key for key in ("quantity", "explicit_weight", "explicit_market_value") if position.get(key) is not None]
        if not ticker or len(supplied) != 1 or not _number(position.get(supplied[0])):
            raise ValueError("POSITION_INPUT_INVALID_OR_MIXED")
        key = supplied[0]
        if key == "quantity":
            price = prices.get(ticker)
            if not _number(price) or price == 0:
                raise ValueError(f"QUANTITY_PRICE_UNAVAILABLE:{ticker}")
            exposure, basis = float(position[key]) * float(price), "QUANTITY_X_RETAINED_CURRENT_PRICE"
        else:
            exposure, basis = float(position[key]), "EXPLICIT_WEIGHT" if key == "explicit_weight" else "EXPLICIT_MARKET_VALUE"
        rows.append({"ticker": ticker, "raw_exposure": exposure, "exposure_basis": basis, "cost_basis": position.get("cost_basis")})
    total = sum(row["raw_exposure"] for row in rows) + float(portfolio.get("cash", 0) or 0)
    if total <= 0:
        raise ValueError("PORTFOLIO_TOTAL_EXPOSURE_NONPOSITIVE")
    for row in rows:
        row["weight"] = row["raw_exposure"] / total
    return rows, total


def build_liquidity_research_context(*, as_of_session: str, records: Mapping[str, Mapping[str, Any]], source_identity: str | None = None) -> dict[str, Any]:
    """Project supplied descriptive volume records; missing data stays unavailable."""
    projected = {}
    for ticker, row in sorted(records.items()):
        current = row.get("current_volume")
        rolling = row.get("rolling_volume")
        ready = _number(current)
        projected[ticker] = {
            "ticker": ticker, "as_of_session": as_of_session,
            "current_session_volume": current if _number(current) else None,
            "rolling_volume": rolling if _number(rolling) else None,
            "relative_volume": (float(current) / float(rolling) if ready and _number(rolling) and rolling > 0 else None),
            "research_proxy_status": "LIQUIDITY_RESEARCH_PROXY" if ready else "LIQUIDITY_RESEARCH_UNAVAILABLE",
            "exact_execution_capacity_status": row.get("exact_execution_capacity_status", "EXECUTION_CAPACITY_EXACT_BLOCKED"),
            "board_composition_context": row.get("board_composition_context", "UNKNOWN"),
            "reason_codes": [] if ready else ["DESCRIPTIVE_VOLUME_INPUT_UNAVAILABLE"],
            "authority_boundary": "RESEARCH_PROXY_ONLY_NOT_EXECUTION_SIZING",
        }
    artifact: dict[str, Any] = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION,
        "as_of_session": as_of_session, "source_identity": source_identity, "records": projected,
        "coverage": {"security_denominator": len(projected), "research_proxy_ready": sum(r["research_proxy_status"] == "LIQUIDITY_RESEARCH_PROXY" for r in projected.values()),
                     "exact_execution_capacity_blocked": sum(r["exact_execution_capacity_status"] != "EXECUTION_CAPACITY_EXACT_READY" for r in projected.values())},
        "authority_boundary": {"liquidity_research_proxy": "CURRENT_DESCRIPTIVE_ONLY", "execution_capacity_exact": "SEPARATE_FAIL_CLOSED", "position_sizing": "NOT_EMITTED"}}
    return {**artifact, **_identity("liquidity_research_context", artifact)}


def build_portfolio_research_context(*, portfolio: Mapping[str, Any], risk_artifact: Mapping[str, Any], liquidity_context: Mapping[str, Any], prices: Mapping[str, Any] | None = None, tactical_states: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build an explicit user-portfolio research context from completed-session inputs."""
    prices, tactical_states = prices or {}, tactical_states or {}
    session = (risk_artifact.get("metadata") or {}).get("as_of_session")
    if portfolio.get("as_of_session") != session:
        raise ValueError("PORTFOLIO_SESSION_MISMATCH")
    rows, total = _positions(portfolio, prices)
    risks, liquids = risk_artifact.get("ticker_risk_context") or {}, liquidity_context.get("records") or {}
    for row in rows:
        risk, liquidity = risks.get(row["ticker"], {}), liquids.get(row["ticker"], {})
        row.update({"sector": risk.get("sector") or "UNKNOWN", "tactical_state": tactical_states.get(row["ticker"], "UNKNOWN"),
                    "volatility": {horizon: ((risk.get("volatility_context") or {}).get(horizon) or {}).get("annualized_research_volatility") for horizon in LOOKBACKS},
                    "liquidity_research_context": liquidity.get("research_proxy_status", "LIQUIDITY_RESEARCH_UNAVAILABLE"),
                    "exact_execution_capacity_status": liquidity.get("exact_execution_capacity_status", "EXECUTION_CAPACITY_EXACT_BLOCKED")})
    held = {row["ticker"] for row in rows}
    selected = next((horizon for horizon in LOOKBACKS if held.issubset(set(((risk_artifact.get("joint_matrix_context") or {}).get(horizon) or {}).get("included_tickers") or [])) and ((risk_artifact.get("joint_matrix_context") or {}).get(horizon) or {}).get("status") == "JOINT_MATRIX_READY"), None)
    sectors: dict[str, float] = defaultdict(float); tactical: dict[str, float] = defaultdict(float)
    for row in rows: sectors[row["sector"]] += row["weight"]; tactical[row["tactical_state"]] += row["weight"]
    limits, breaches = portfolio.get("risk_limits") or {}, []
    if limits.get("max_single_name_weight") is not None:
        for row in rows:
            if row["weight"] > float(limits["max_single_name_weight"]): breaches.append({"reason": "MAX_SINGLE_NAME_WEIGHT", "ticker": row["ticker"]})
    if limits.get("max_sector_weight") is not None:
        for sector, weight in sectors.items():
            if weight > float(limits["max_sector_weight"]): breaches.append({"reason": "MAX_SECTOR_WEIGHT", "sector": sector})
    artifact: dict[str, Any] = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "portfolio_id": portfolio["portfolio_id"], "as_of_session": session,
        "normalized_positions": rows, "cash_weight": float(portfolio.get("cash", 0) or 0) / total,
        "sector_concentration": dict(sorted(sectors.items())), "tactical_concentration": dict(sorted(tactical.items())),
        "selected_joint_risk_horizon": selected or "UNAVAILABLE", "joint_risk_status": "READY" if selected else "UNAVAILABLE",
        "pairwise_correlation_status": "AVAILABLE_SEPARATELY_FROM_JOINT_MATRIX", "user_limit_breaches": breaches,
        "warnings": [] if selected else ["NO_COMPLETED_SESSION_JOINT_MATRIX_FOR_ALL_HOLDINGS"],
        "calculation_lineage": {"risk_artifact_identity": risk_artifact.get("artifact_identity"), "liquidity_context_identity": liquidity_context.get("artifact_identity"), "completed_session_contract": "20_60_120_250_ONLY"},
        "authority_boundary": {"explicit_portfolio_required": True, "no_autonomous_optimization": True, "no_recommended_position_size": True, "no_execution_capacity_promotion": True, "is_actionable": False}}
    return {**artifact, **_identity("portfolio_research_context", artifact)}
