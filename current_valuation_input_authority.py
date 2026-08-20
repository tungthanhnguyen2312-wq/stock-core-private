"""Generic, fail-closed authority for inputs to current valuation research.

This is deliberately an input boundary, not a valuation engine.  It can inspect
any canonical instrument/evidence instance but never turns CURRENT_MARKET
observations into historical RAW_AS_TRADED or PIT authority.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from dnse_market_risk_evidence_store import read_stock_ohlc
from field_temporal_contract import stable_id
from freshness_history import latest_completed_market_day
from current_state_relative_valuation import resolve_current_shares

VERSION = "1.0.0"
CONTRACT_VERSION = "current_valuation_input_authority/v1"
CURRENT_MARKET = "CURRENT_MARKET"
PIT_OBSERVED = "PIT_OBSERVED"
RAW_AS_TRADED = "RAW_AS_TRADED"
ADJUSTED_RETROSPECTIVE = "ADJUSTED_RETROSPECTIVE"
UNKNOWN = "UNKNOWN"
PRICE_READY, PRICE_BLOCKED = "PRICE_READY", "PRICE_BLOCKED"
SHARE_READY, SHARE_BLOCKED = "SHARE_READY", "SHARE_BLOCKED"
COMMON_OUTSTANDING = "common_shares_outstanding"
SHARE_IDENTITIES = frozenset({
    "issued_shares", "listed_shares", COMMON_OUTSTANDING, "treasury_shares",
    "period_end_shares", "weighted_average_basic_shares", "diluted_shares",
})
VIETNAM_TZ = timezone(timedelta(hours=7))
_CLOSE_HOUR = 15


def _time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=VIETNAM_TZ)).astimezone(VIETNAM_TZ)


def _date(value: Any) -> str | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date().isoformat()
    except ValueError:
        return None


def latest_completed_vietnam_session(requested_at: str | datetime, available_sessions: Iterable[str]) -> dict[str, Any]:
    """Resolve the latest fully completed weekday session present in evidence.

    The policy is calendar-only and data-independent.  An evidence instance
    still needs to contain the exact selected session; weekends/holidays are
    represented by absence from ``available_sessions`` rather than guessed.
    """
    now = _time(requested_at)
    candidate = latest_completed_market_day(now)
    session_set = {s for value in available_sessions if (s := _date(value))}
    eligible = sorted(s for s in session_set if s <= candidate.isoformat())
    return {
        "requested_at": now.isoformat(), "calendar_anchor": candidate.isoformat(),
        "session": eligible[-1] if eligible else None,
        "status": "QUALIFIED" if eligible else "SESSION_MISSING",
        "policy": "latest_completed_vietnam_weekday_with_exact_retained_observation",
    }


def canonical_instrument(ticker: str, *, provider_symbol: str | None = None) -> dict[str, Any]:
    """Minimal canonical identity adapter; no ticker-specific routing exists."""
    normalized = str(ticker).strip().upper()
    return {"canonical_ticker": normalized, "provider_symbols": {"DNSE": provider_symbol or normalized}}


def dnse_current_market_observations(runtime_root: Path | str, instrument: Mapping[str, Any]) -> dict[str, Any]:
    """Read arbitrary DNSE retained OHLC evidence without inferring/repairing it."""
    ticker = str(instrument.get("canonical_ticker") or "").strip().upper()
    provider_symbol = ((instrument.get("provider_symbols") or {}).get("DNSE") or ticker)
    record = read_stock_ohlc(runtime_root, str(provider_symbol))
    base = {"provider": "DNSE", "endpoint": "/price/ohlc", "canonical_instrument": dict(instrument),
            "provider_symbol": provider_symbol, "observations": [], "retrieved_at": None,
            "payload_identity": None, "status": "MISSING_EVIDENCE", "reason_codes": []}
    if record is None:
        return base
    raw = record.get("raw_ohlc")
    if not isinstance(raw, Mapping) or any(not isinstance(raw.get(k), list) for k in ("o", "h", "l", "c", "t")):
        return {**base, "status": "MALFORMED", "reason_codes": ["DNSE_PAYLOAD_SHAPE_INVALID"]}
    lengths = {len(raw[k]) for k in ("o", "h", "l", "c", "t")}
    if len(lengths) != 1:
        return {**base, "status": "MALFORMED", "reason_codes": ["DNSE_PAYLOAD_ARRAY_LENGTH_CONFLICT"]}
    rows = []
    for o, h, low, close, epoch in zip(raw["o"], raw["h"], raw["l"], raw["c"], raw["t"]):
        if not isinstance(close, (int, float)) or isinstance(close, bool) or close <= 0:
            return {**base, "status": "MALFORMED", "reason_codes": ["DNSE_CLOSE_INVALID"]}
        try:
            session = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(VIETNAM_TZ).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            return {**base, "status": "MALFORMED", "reason_codes": ["DNSE_SESSION_TIMESTAMP_INVALID"]}
        rows.append({"session": session, "close": close, "open": o, "high": h, "low": low})
    provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
    payload = {"provider": record.get("provider"), "symbol": record.get("symbol"), "raw_ohlc": raw, "provenance": provenance}
    return {**base, "status": "OBSERVED", "observations": rows,
            "retrieved_at": provenance.get("materialized_at"), "payload_identity": stable_id(payload),
            "provenance": provenance}


def qualify_current_market_price(instrument: Mapping[str, Any], evidence: Mapping[str, Any], *, requested_at: str | datetime) -> dict[str, Any]:
    """Qualify one exact DNSE daily close for current valuation use only."""
    base = {"canonical_instrument": dict(instrument), "provider": evidence.get("provider"),
            "dataset_endpoint": evidence.get("endpoint"), "price_namespace": CURRENT_MARKET,
            "historical_pit_eligible": False, "raw_as_traded": "NOT_PROMOTED",
            "qualification_state": "UNKNOWN", "status": PRICE_BLOCKED, "reason_codes": [],
            "allowed_use": "current_market_valuation_only", "value": None, "currency": "VND",
            "field_identity": "close", "session": None, "retrieved_at": evidence.get("retrieved_at"),
            "provenance": evidence.get("provenance"), "payload_identity": evidence.get("payload_identity"),
            "price_basis": ADJUSTED_RETROSPECTIVE}
    if evidence.get("status") != "OBSERVED":
        return {**base, "qualification_state": str(evidence.get("status") or "UNKNOWN"),
                "reason_codes": list(evidence.get("reason_codes") or ["PRICE_EVIDENCE_MISSING"])}
    provider_symbol = str(evidence.get("provider_symbol") or "").upper()
    expected = str((instrument.get("provider_symbols") or {}).get("DNSE") or "").upper()
    if not expected or provider_symbol != expected:
        return {**base, "qualification_state": "INSTRUMENT_UNRESOLVED", "reason_codes": ["DNSE_PROVIDER_SYMBOL_DOES_NOT_MATCH_CANONICAL_INSTRUMENT"]}
    session_policy = latest_completed_vietnam_session(requested_at, [row.get("session") for row in evidence.get("observations", [])])
    if session_policy["status"] != "QUALIFIED":
        return {**base, "qualification_state": "SESSION_MISSING", "reason_codes": ["LATEST_COMPLETED_SESSION_NOT_RETAINED"], "session_policy": session_policy}
    session = session_policy["session"]
    if session != session_policy["calendar_anchor"]:
        return {**base, "qualification_state": "STALE", "reason_codes": ["LATEST_COMPLETED_DNSE_SESSION_NOT_RETAINED"], "session_policy": session_policy}
    matching = [row for row in evidence["observations"] if row.get("session") == session]
    if len(matching) != 1:
        return {**base, "qualification_state": "CONFLICT", "reason_codes": ["DNSE_SESSION_CLOSE_CONFLICT"], "session_policy": session_policy}
    close = matching[0].get("close")
    if not isinstance(close, (int, float)) or isinstance(close, bool) or close <= 0:
        return {**base, "qualification_state": "MALFORMED", "reason_codes": ["DNSE_CLOSE_INVALID"], "session_policy": session_policy}
    return {**base, "status": PRICE_READY, "qualification_state": "QUALIFIED", "value": close * 1000,
            "price_unit": "VND", "raw_provider_unit": "thousands_of_vnd", "session": session,
            "session_policy": session_policy, "observation": matching[0], "freshness": "exact_completed_session"}


def qualify_current_share_basis(instrument: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *, valuation_date: str, corporate_actions: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Accept only explicit common-outstanding candidates with proved coverage.

    Period-end, weighted-average, issued, listed and diluted records are retained
    as semantically distinct candidates but cannot silently become current market
    capitalization shares.
    """
    base = {"canonical_instrument": dict(instrument), "valuation_date": valuation_date,
            "status": SHARE_BLOCKED, "qualification_state": "UNKNOWN", "identity": None,
            "value": None, "reason_codes": [], "allowed_use": "current_market_capitalization_only"}
    ticker = str(instrument.get("canonical_ticker") or "").upper()
    applicable = [dict(row) for row in candidates if str(row.get("canonical_ticker") or ticker).upper() == ticker]
    qualified = [row for row in applicable if row.get("identity") == COMMON_OUTSTANDING and
                 row.get("qualification_state") == "QUALIFIED" and row.get("coverage_through") and
                 str(row["coverage_through"]) >= valuation_date and isinstance(row.get("value"), int) and row["value"] > 0]
    action_blockers = []
    for action in corporate_actions:
        if not action.get("potential_share_change"):
            continue
        effective = _date(action.get("effective_date"))
        if effective is None:
            action_blockers.append("CORPORATE_ACTION_TIMING_UNRESOLVED_NO_EX_DATE_INFERRED")
        elif effective <= valuation_date and action.get("lifecycle") != "completed_with_resulting_common_shares":
            action_blockers.append("CORPORATE_ACTION_INVALIDATES_CURRENT_SHARE_COVERAGE")
    if action_blockers:
        return {**base, "qualification_state": "BLOCKED", "reason_codes": sorted(set(action_blockers))}
    if not qualified:
        identity_reasons = sorted({str(row.get("identity") or "unknown") for row in applicable})
        return {**base, "qualification_state": "STALE_OR_MISSING", "reason_codes": ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN"], "observed_identities": identity_reasons}
    values = {row["value"] for row in qualified}
    if len(values) != 1:
        return {**base, "qualification_state": "CONFLICT", "reason_codes": ["EQUALLY_QUALIFIED_CURRENT_SHARE_VALUES_CONFLICT"]}
    chosen = sorted(qualified, key=lambda row: (str(row.get("coverage_through")), str(row.get("payload_identity") or "")))[-1]
    return {**base, "status": SHARE_READY, "qualification_state": "QUALIFIED", "identity": COMMON_OUTSTANDING,
            "value": chosen["value"], "effective_date": chosen.get("effective_date"),
            "coverage_through": chosen["coverage_through"], "lineage": chosen}


def runtime_share_candidates(runtime_root: Path | str, instrument: Mapping[str, Any], valuation_date: str) -> list[dict[str, Any]]:
    """Adapt existing strict official-evidence transition resolution into evidence rows."""
    ticker = str(instrument.get("canonical_ticker") or "").upper()
    result = resolve_current_shares(runtime_root, ticker, valuation_date)
    bridge = result.get("bridge_result") or {}
    current = bridge.get("current_shares") or {}
    if current.get("qualified"):
        return [{"canonical_ticker": ticker, "identity": COMMON_OUTSTANDING, "value": current["value"],
                 "effective_date": valuation_date, "coverage_through": result.get("coverage_through"),
                 "qualification_state": "QUALIFIED", "source_authority": "official_evidence_share_transition_bridge",
                 "payload_identity": stable_id(result), "lineage": result}]
    return [{"canonical_ticker": ticker, "identity": "period_end_shares", "value": None,
             "coverage_through": result.get("coverage_through"), "qualification_state": "UNKNOWN",
             "reason": current.get("reason"), "payload_identity": stable_id(result), "lineage": result}]


def resolve_current_valuation_inputs(instrument: Mapping[str, Any], *, requested_at: str | datetime,
                                     financial_input_state: Mapping[str, Any], market_evidence: Mapping[str, Any],
                                     share_evidence: Sequence[Mapping[str, Any]], corporate_action_state: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    price = qualify_current_market_price(instrument, market_evidence, requested_at=requested_at)
    valuation_date = price.get("session") or latest_completed_vietnam_session(requested_at, ())["calendar_anchor"]
    shares = qualify_current_share_basis(instrument, share_evidence, valuation_date=valuation_date, corporate_actions=corporate_action_state)
    market_cap = price["value"] * shares["value"] if price["status"] == PRICE_READY and shares["status"] == SHARE_READY else None
    blocker_codes = sorted(set(list(price.get("reason_codes") or []) + list(shares.get("reason_codes") or [])))
    return {"contract_version": CONTRACT_VERSION, "canonical_instrument": dict(instrument), "valuation_session": valuation_date,
            "price": price, "shares": shares, "financial_input_state": dict(financial_input_state),
            "market_cap_readiness": "MARKET_CAP_READY" if market_cap is not None else "MARKET_CAP_BLOCKED",
            "market_cap": market_cap, "valuation_families": dict(financial_input_state.get("families") or {}),
            "blocker_codes": blocker_codes, "is_actionable": False, "historical_pit_eligible": False}


def scan_current_valuation_input_coverage(instruments: Sequence[Mapping[str, Any]], *, runtime_root: Path | str,
                                          requested_at: str | datetime, financial_by_ticker: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Read-only generic scanner; an arbitrary instrument iterable is supported."""
    rows = []
    for instrument in sorted(instruments, key=lambda row: str(row.get("canonical_ticker") or "")):
        evidence = dnse_current_market_observations(runtime_root, instrument)
        policy = latest_completed_vietnam_session(requested_at, [row.get("session") for row in evidence.get("observations", [])])
        date = policy.get("session") or policy["calendar_anchor"]
        shares = runtime_share_candidates(runtime_root, instrument, date)
        financial = (financial_by_ticker or {}).get(str(instrument.get("canonical_ticker") or ""), {})
        rows.append(resolve_current_valuation_inputs(instrument, requested_at=requested_at, financial_input_state=financial,
                                                     market_evidence=evidence, share_evidence=shares))
    counts = Counter()
    reasons = Counter()
    for row in rows:
        counts[row["price"]["status"]] += 1; counts[row["shares"]["status"]] += 1
        counts["BOTH_READY" if row["market_cap_readiness"] == "MARKET_CAP_READY" else "BOTH_NOT_READY"] += 1
        reasons.update(row["blocker_codes"])
    return {"contract_version": CONTRACT_VERSION, "rows": rows, "counts": dict(sorted(counts.items())), "blocker_distribution": dict(sorted(reasons.items()))}


def serialize(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
