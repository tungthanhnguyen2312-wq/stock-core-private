"""Scoped current-session execution-capacity research.

This module turns the already-qualified ``ADTV20_MATCHED_ALL_VND`` field from
``official_exchange_liquidity_research/v1`` into a policy-bounded Level-1
research envelope.  It deliberately does not model market impact, fills,
execution price, portfolio allocation, or historical replay.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Mapping


POLICY_CONTRACT = "execution_capacity_policy/v1"
ENVELOPE_CONTRACT = "execution_capacity_research_envelope/v1"
MILESTONE = "LIQUIDITY_EXECUTION_CAPACITY_AND_SIZING_V1"

AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"

CURRENT_SESSION_EXECUTION_CAPACITY_RESEARCH = "CURRENT_SESSION_EXECUTION_CAPACITY_RESEARCH"
CURRENT_SESSION_RISK_SIZE_RESEARCH = "CURRENT_SESSION_RISK_SIZE_RESEARCH"
LIVE_POSITION_SIZING = "LIVE_POSITION_SIZING"
PORTFOLIO_CAPITAL_ALLOCATION = "PORTFOLIO_CAPITAL_ALLOCATION"
HISTORICAL_PIT_SIZE_REPLAY = "HISTORICAL_PIT_SIZE_REPLAY"
PIT_BACKTEST = "PIT_BACKTEST"
EXECUTION_REPLAY = "EXECUTION_REPLAY"

FORBIDDEN_USES = (
    "LIVE_EXECUTION_INSTRUCTION",
    "FILL_GUARANTEE",
    "VWAP_GUARANTEE",
    "MARKET_IMPACT_ADJUSTED",
    "EXECUTION_PRICE_GUARANTEE",
)
_IDENTITY_EXCLUDED = {"artifact_identity", "artifact_sha256", "requested_at"}


class ExecutionCapacityPolicyError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(kind: str, value: Mapping[str, Any]) -> dict[str, str]:
    excluded = _IDENTITY_EXCLUDED | ({"policy_identity"} if kind == "execution_capacity_policy" else set())
    body = {key: item for key, item in value.items() if key not in excluded}
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{kind}:{digest}"}


def _decimal(value: Any, *, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ExecutionCapacityPolicyError(f"{field}:BOOLEAN_NOT_ALLOWED")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ExecutionCapacityPolicyError(f"{field}:INVALID_DECIMAL") from exc
    if not result.is_finite():
        raise ExecutionCapacityPolicyError(f"{field}:NON_FINITE")
    return result


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def build_policy(
    *,
    max_participation_of_adtv20: Any = None,
    max_days_to_liquidate: Any = None,
    min_adtv20_vnd: Any = None,
    board_lot_shares_by_exchange: Mapping[str, Any] | None = None,
    policy_version: str = "EXECUTION_CAPACITY_POLICY_UNBOUND_V1",
    policy_source: str = "SYSTEM_DEFAULT_POLICY_V3",
    effective_from: str | None = None,
) -> dict[str, Any]:
    """Validate and identify policy.  ``None`` means explicitly UNBOUND."""
    participation = _decimal(max_participation_of_adtv20, field="max_participation_of_adtv20")
    if participation is not None and not (Decimal("0") < participation <= Decimal("1")):
        raise ExecutionCapacityPolicyError("max_participation_of_adtv20:OUT_OF_DOMAIN")
    if max_days_to_liquidate is None:
        days = None
    elif isinstance(max_days_to_liquidate, bool):
        raise ExecutionCapacityPolicyError("max_days_to_liquidate:BOOLEAN_NOT_ALLOWED")
    else:
        days_decimal = _decimal(max_days_to_liquidate, field="max_days_to_liquidate")
        if days_decimal != days_decimal.to_integral_value() or not (1 <= int(days_decimal) <= 20):
            raise ExecutionCapacityPolicyError("max_days_to_liquidate:OUT_OF_DOMAIN")
        days = int(days_decimal)
    minimum = _decimal(min_adtv20_vnd, field="min_adtv20_vnd")
    if minimum is not None and minimum < 0:
        raise ExecutionCapacityPolicyError("min_adtv20_vnd:OUT_OF_DOMAIN")
    lots: dict[str, int] = {}
    for exchange, raw in sorted((board_lot_shares_by_exchange or {}).items()):
        if isinstance(raw, bool):
            raise ExecutionCapacityPolicyError(f"board_lot_shares_by_exchange.{exchange}:BOOLEAN_NOT_ALLOWED")
        value = _decimal(raw, field=f"board_lot_shares_by_exchange.{exchange}")
        if value != value.to_integral_value() or int(value) <= 0:
            raise ExecutionCapacityPolicyError(f"board_lot_shares_by_exchange.{exchange}:OUT_OF_DOMAIN")
        lots[str(exchange).upper()] = int(value)
    unbound = [name for name, value in (
        ("max_participation_of_adtv20", participation),
        ("max_days_to_liquidate", days),
    ) if value is None]
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": POLICY_CONTRACT,
        "policy_version": str(policy_version),
        "status": "BOUND" if not unbound else "UNBOUND",
        "max_participation_of_adtv20": _decimal_text(participation),
        "max_days_to_liquidate": days,
        "min_adtv20_vnd": _decimal_text(minimum),
        "board_lot_shares_by_exchange": lots,
        "effective_from": effective_from,
        "provenance": {"policy_source": policy_source, "owner_values_in_public_artifact": False},
        "unbound_fields": unbound,
        "authority_boundary": {
            "policy_not_evidence": True,
            "no_arbitrary_participation_or_horizon_default": True,
            "not_an_execution_instruction": True,
        },
    }
    identity = _identity("execution_capacity_policy", body)
    return {**body, **identity, "policy_identity": identity["artifact_identity"]}


def canonical_unbound_policy() -> dict[str, Any]:
    return build_policy()


def policy_from_private_context(
    *, effective_policy: Mapping[str, Any], field_provenance: Mapping[str, Any] | None = None,
    sizing_policy_version: str, board_lot_shares_by_exchange: Mapping[str, Any] | None = None,
    effective_from: str | None = None,
) -> dict[str, Any]:
    """Bind owner-configured fields without copying any holding/NAV/account value."""
    sources = field_provenance or {}
    used_sources = {
        field: (sources.get(field) or {}).get("effective_source", "PRIVATE_EFFECTIVE_POLICY")
        for field in ("max_participation_of_adtv20", "max_days_to_liquidate", "min_adtv20_vnd")
    }
    return build_policy(
        max_participation_of_adtv20=effective_policy.get("max_participation_of_adtv20"),
        max_days_to_liquidate=effective_policy.get("max_days_to_liquidate"),
        min_adtv20_vnd=effective_policy.get("min_adtv20_vnd"),
        board_lot_shares_by_exchange=board_lot_shares_by_exchange,
        policy_version=f"{sizing_policy_version}:EXECUTION_CAPACITY",
        policy_source="PRIVATE_PORTFOLIO_POLICY_FIELDS:" + _canonical(used_sources),
        effective_from=effective_from,
    )


def use_specific_authority(*, capacity_state: str = PARTIAL, private_size_state: str = PARTIAL) -> dict[str, str]:
    if capacity_state not in (AVAILABLE, PARTIAL, BLOCKED) or private_size_state not in (AVAILABLE, PARTIAL, BLOCKED):
        raise ValueError("INVALID_SCOPED_AUTHORITY_STATE")
    return {
        CURRENT_SESSION_EXECUTION_CAPACITY_RESEARCH: "ELIGIBLE" if capacity_state == AVAILABLE else capacity_state,
        CURRENT_SESSION_RISK_SIZE_RESEARCH: "ELIGIBLE" if private_size_state == AVAILABLE else private_size_state,
        LIVE_POSITION_SIZING: BLOCKED,
        PORTFOLIO_CAPITAL_ALLOCATION: BLOCKED,
        HISTORICAL_PIT_SIZE_REPLAY: BLOCKED,
        PIT_BACKTEST: BLOCKED,
        EXECUTION_REPLAY: BLOCKED,
    }


def _source_record_identity(record: Mapping[str, Any]) -> str:
    return _identity("official_exchange_liquidity_record", record)["artifact_identity"]


def build_envelope(
    *,
    ticker: str,
    session: str,
    official_liquidity_record: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
    current_price: Any = None,
    price_identity: str | None = None,
    source_liquidity_identity: str | None = None,
    historical_t0_use: bool = False,
) -> dict[str, Any]:
    """Build one deterministic Level-1 capacity envelope with exact Decimal arithmetic."""
    if policy.get("contract_version") != POLICY_CONTRACT:
        raise ExecutionCapacityPolicyError("POLICY_CONTRACT_MISMATCH")
    expected_policy_identity = _identity("execution_capacity_policy", policy)["artifact_identity"]
    if policy.get("policy_identity") != expected_policy_identity:
        raise ExecutionCapacityPolicyError("POLICY_IDENTITY_INVALID")
    provenance = policy.get("provenance") or {}
    validated = build_policy(
        max_participation_of_adtv20=policy.get("max_participation_of_adtv20"),
        max_days_to_liquidate=policy.get("max_days_to_liquidate"),
        min_adtv20_vnd=policy.get("min_adtv20_vnd"),
        board_lot_shares_by_exchange=policy.get("board_lot_shares_by_exchange"),
        policy_version=policy.get("policy_version"),
        policy_source=provenance.get("policy_source"),
        effective_from=policy.get("effective_from"),
    )
    if validated["policy_identity"] != expected_policy_identity:
        raise ExecutionCapacityPolicyError("POLICY_CONTENT_INVALID")
    record = official_liquidity_record or {}
    view = record.get("research_view") or {}
    feature = view.get("adtv20_matched_all_vnd") or {}
    coverage = record.get("coverage") or {}
    exchange = record.get("route_exchange")
    adtv = _decimal(feature.get("value"), field="adtv20_matched_all_vnd") if feature.get("value") is not None else None
    price = _decimal(current_price, field="current_price")
    if price is not None and price <= 0:
        price = None
    reasons: list[str] = []
    state = BLOCKED
    notional: Decimal | None = None
    shares: int | None = None
    lot = (policy.get("board_lot_shares_by_exchange") or {}).get(exchange)

    coverage_class = coverage.get("coverage_class")
    adtv_exact = (feature.get("status") == "EXACT_WINDOW"
                  and coverage_class == "EXACT_20_SESSION_WINDOW"
                  and ((record.get("fitness") or {}).get("ADTV_RESEARCH") or {}).get("state") == "ELIGIBLE")
    current_eligible = ((record.get("fitness") or {}).get("CURRENT_SESSION_LIQUIDITY_RESEARCH") or {}).get("state") == "ELIGIBLE"
    if historical_t0_use:
        reasons.append("PIT_REQUIRED_HISTORICAL_USE")
    elif coverage_class == "PUBLIC_ACQUISITION_NOT_AUTHORIZED":
        reasons.append("PUBLIC_ACQUISITION_NOT_AUTHORIZED")
    elif coverage_class in ("SOURCE_NOT_SUPPORTED", "EXCHANGE_IDENTITY_CONFLICT"):
        reasons.append(coverage_class)
    elif not adtv_exact:
        state = PARTIAL if current_eligible else BLOCKED
        reasons.append("CURRENT_LIQUIDITY_ONLY_NO_ADTV" if current_eligible else "ADTV20_NOT_QUALIFIED")
        reasons.extend(code for code in coverage.get("reason_codes") or [] if code not in reasons)
        if coverage_class in ("PARTIAL_WINDOW", "MISSING_SESSION") and "SERIES_STARTS_INSIDE_WINDOW" not in reasons:
            reasons.append("SERIES_STARTS_INSIDE_WINDOW")
    elif policy.get("status") != "BOUND":
        reasons.append("POLICY_UNBOUND")
    else:
        participation = _decimal(policy.get("max_participation_of_adtv20"), field="max_participation_of_adtv20")
        days = int(policy["max_days_to_liquidate"])
        minimum = _decimal(policy.get("min_adtv20_vnd"), field="min_adtv20_vnd")
        if minimum is not None and adtv < minimum:
            notional = Decimal("0")
            reasons.append("BELOW_MIN_ADTV20_POLICY")
        else:
            notional = adtv * participation * Decimal(days)
        if adtv == 0:
            reasons.extend(["ZERO_TRADING_VALID", "ILLIQUID_ZERO_ADTV"])
        if price is None or not price_identity:
            state = PARTIAL
            reasons.append("CURRENT_PRICE_NOT_QUALIFIED")
        elif lot is None:
            state = PARTIAL
            reasons.append("LOT_RULE_UNBOUND")
        else:
            raw_shares = (notional / price).to_integral_value(rounding=ROUND_FLOOR)
            shares = (int(raw_shares) // int(lot)) * int(lot)
            state = AVAILABLE

    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": ENVELOPE_CONTRACT,
        "ticker": str(ticker).upper(),
        "session": session,
        "state": state,
        "authority": "RESEARCH_SCOPED_LEVEL1_ENVELOPE",
        "knowledge_time": "CURRENT_RESEARCH_AS_OF_SESSION_USING_RETROSPECTIVELY_RETRIEVED_OFFICIAL_ADTV20",
        "adtv20_matched_all_vnd": _decimal_text(adtv),
        "current_price": _decimal_text(price),
        "participation_used": policy.get("max_participation_of_adtv20") if policy.get("status") == "BOUND" else None,
        "days_to_liquidate_used": policy.get("max_days_to_liquidate") if policy.get("status") == "BOUND" else None,
        "capacity_notional_vnd": _decimal_text(notional),
        "capacity_shares_lot_rounded": shares,
        "exchange": exchange,
        "board_lot_shares": lot,
        "policy_identity": policy.get("policy_identity"),
        "source_liquidity_identity": source_liquidity_identity or (_source_record_identity(record) if record else None),
        "price_identity": price_identity,
        "reason_codes": list(dict.fromkeys(reasons)),
        "limitations": [
            "LEVEL1_ADTV_PARTICIPATION_ENVELOPE_ONLY",
            "NO_MARKET_IMPACT_MODEL",
            "CURRENT_SESSION_RESEARCH_NOT_HISTORICAL_PIT",
            *FORBIDDEN_USES,
        ],
        "forbidden_uses": list(FORBIDDEN_USES),
    }
    return {**body, **_identity("execution_capacity_research_envelope", body)}


def build_retained_acceptance(
    *, official_liquidity_artifact: Mapping[str, Any], policy: Mapping[str, Any],
) -> dict[str, Any]:
    records = official_liquidity_artifact.get("records") or {}
    session = official_liquidity_artifact.get("resolved_completed_session")
    envelopes = {
        ticker: build_envelope(
            ticker=ticker, session=session, official_liquidity_record=record, policy=policy,
            source_liquidity_identity=official_liquidity_artifact.get("artifact_identity"),
        )
        for ticker, record in sorted(records.items())
    }
    states = Counter(item["state"] for item in envelopes.values())
    reasons = Counter(code for item in envelopes.values() for code in item["reason_codes"])
    share_unavailable_lot = sum(
        item["capacity_notional_vnd"] is not None and item["capacity_shares_lot_rounded"] is None
        and "LOT_RULE_UNBOUND" in item["reason_codes"] for item in envelopes.values()
    )
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": "execution_capacity_retained_acceptance/v1",
        "milestone": MILESTONE,
        "session": session,
        "policy_identity": policy.get("policy_identity"),
        "source_liquidity_identity": official_liquidity_artifact.get("artifact_identity"),
        "counts": {
            "total_governed_records": len(envelopes),
            "current_liquidity_eligible": sum(
                ((record.get("fitness") or {}).get("CURRENT_SESSION_LIQUIDITY_RESEARCH") or {}).get("state") == "ELIGIBLE"
                for record in records.values()
            ),
            "adtv20_exact": sum((record.get("research_view") or {}).get("adtv20_matched_all_vnd", {}).get("status") == "EXACT_WINDOW" for record in records.values()),
            "capacity_AVAILABLE": states[AVAILABLE],
            "capacity_PARTIAL": states[PARTIAL],
            "capacity_BLOCKED": states[BLOCKED],
            "policy_unbound": reasons["POLICY_UNBOUND"],
            "zero_capacity_valid": sum(item["capacity_notional_vnd"] == "0" and "ZERO_TRADING_VALID" in item["reason_codes"] for item in envelopes.values()),
            "missing_adtv": sum((record.get("research_view") or {}).get("adtv20_matched_all_vnd", {}).get("status") != "EXACT_WINDOW" for record in records.values()),
            "rights_gated": reasons["PUBLIC_ACQUISITION_NOT_AUTHORIZED"],
            "exchange_unresolved": reasons["SOURCE_NOT_SUPPORTED"] + reasons["EXCHANGE_IDENTITY_CONFLICT"],
            "share_quantity_unavailable_due_lot_rule": share_unavailable_lot,
        },
        "reason_code_counts": dict(sorted(reasons.items())),
        "records": envelopes,
        "authority_boundary": use_specific_authority(capacity_state=PARTIAL, private_size_state=PARTIAL),
    }
    return {**body, **_identity("execution_capacity_retained_acceptance", body)}


def compare_policy_epochs(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    same = previous.get("policy_identity") == current.get("policy_identity")
    return {
        "state": "COMPARABLE_SAME_POLICY" if same else "NOT_COMPARABLE_POLICY_CHANGE",
        "previous_policy_identity": previous.get("policy_identity"),
        "current_policy_identity": current.get("policy_identity"),
    }
