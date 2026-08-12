"""Deterministic current-regime DNSE daily-OHLC price-basis qualification.

This module composes the existing DNSE event-pattern primitives.  It never grants
provider-wide authority: a post-event query without a retained pre-event snapshot may describe
the current series, but cannot prove that its earlier rows were retrospectively rewritten.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from dnse_ohlc_price_basis_capability import (
    ADJUSTED_PATTERN,
    EVIDENCE_EVENTS,
    RAW_PATTERN,
    classify_internal_transition,
)
from vn_time import VN_TZ

CURRENT_REGIME_START = "2026-01-01"
CURRENT_REGIME_END = "2026-08-11"
DATASET = "ohlc_1D"
MIN_PRE_SESSIONS = 3
MIN_POST_SESSIONS = 3
SUPPORTED_EVENT_CODES = {"DIV": "cash_dividend", "ISS": "stock_dividend_bonus_issue"}


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _event_input(row: Mapping[str, Any]) -> tuple[str, float] | None:
    code = str(row.get("event_code") or "").upper()
    value = row.get("value_per_share") if code == "DIV" else row.get("exercise_ratio")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return ("value_per_share_vnd" if code == "DIV" else "exercise_ratio", float(value))


def comparison_window(exright_date: str, *, calendar_days: int = 10) -> dict[str, str]:
    event_date = _date(exright_date)
    if event_date is None:
        raise ValueError("explicit_exright_date_required")
    return {
        "from": (event_date - timedelta(days=calendar_days)).isoformat(),
        "to": (event_date + timedelta(days=calendar_days)).isoformat(),
    }


def select_cohort(
    events: Iterable[Mapping[str, Any]],
    universe_by_symbol: Mapping[str, Mapping[str, Any]],
    *,
    start: str = CURRENT_REGIME_START,
    end: str = CURRENT_REGIME_END,
) -> dict[str, list[dict[str, Any]]]:
    """Select and explain every current-regime event deterministically."""
    start_date, end_date = _date(start), _date(end)
    if start_date is None or end_date is None or start_date > end_date:
        raise ValueError("invalid_current_regime_range")
    eligible, excluded = [], []
    for raw in sorted(events, key=lambda row: (str(row.get("exright_date")), str(row.get("ticker")), str(row.get("record_id")))):
        row = dict(raw)
        ticker = str(row.get("ticker") or "").upper()
        event_date = _date(row.get("exright_date"))
        code = str(row.get("event_code") or "").upper()
        reason = None
        if event_date is None:
            reason = "explicit_exright_date_required"
        elif not start_date <= event_date <= end_date:
            reason = "outside_current_regime"
        elif code not in SUPPORTED_EVENT_CODES:
            reason = "event_type_not_supported_by_existing_deterministic_contract"
        elif universe_by_symbol.get(ticker, {}).get("instrument_class") != "EQUITY":
            reason = "instrument_not_retained_as_st_equity"
        elif _event_input(row) is None:
            reason = "official_adjustment_input_missing_or_ambiguous"
        elif str(row.get("revision_status")) != "observed":
            reason = "event_revision_status_not_observed"
        elif (_date(row.get("public_date")) or event_date) > event_date:
            reason = "event_publication_after_exright_date"
        if reason:
            excluded.append({"ticker": ticker, "record_id": row.get("record_id"), "exright_date": row.get("exright_date"), "reason": reason})
            continue
        input_name, input_value = _event_input(row) or ("", 0.0)
        eligible.append({
            "ticker": ticker, "record_id": str(row["record_id"]), "event_code": code,
            "event_type": SUPPORTED_EVENT_CODES[code], "official_exright_date": event_date.isoformat(),
            "official_adjustment_inputs": {input_name: input_value},
            "event_evidence": {"provider": row.get("provider"), "revision_status": row.get("revision_status"), "coverage_status": row.get("coverage_status")},
            "exchange_raw": universe_by_symbol[ticker].get("exchange_raw"),
            "comparison_window": comparison_window(event_date.isoformat()),
            "already_active_regression": any(
                event["record_id"] == row["record_id"] for event in EVIDENCE_EVENTS
            ),
        })
    return {"eligible": eligible, "excluded": excluded}


def query_for_window(window: Mapping[str, str], *, symbol: str) -> dict[str, Any]:
    """Build the exact daily-OHLC query without performing network I/O."""
    start, end = _date(window["from"]), _date(window["to"])
    if start is None or end is None:
        raise ValueError("invalid_comparison_window")
    if not str(symbol).strip():
        raise ValueError("symbol_required_for_ohlc_query")
    return {
        "type": "STOCK", "symbol": str(symbol).strip().upper(), "resolution": "1D",
        "from": int(datetime.combine(start, datetime.min.time(), VN_TZ).timestamp()),
        "to": int(datetime.combine(end + timedelta(days=1), datetime.min.time(), VN_TZ).timestamp()) - 1,
    }


def _bars(body: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    arrays = {key: body.get(key) for key in ("t", "o", "h", "l", "c", "v")}
    if not all(isinstance(value, list) for value in arrays.values()):
        return None
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1:
        return None
    result = []
    for index in range(len(arrays["t"])):
        timestamp = arrays["t"][index]
        if not isinstance(timestamp, (int, float)):
            return None
        result.append({
            "session": datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat(),
            **{key: arrays[key][index] for key in ("o", "h", "l", "c", "v")},
        })
    return sorted(result, key=lambda row: row["session"])


def qualify_event(case: Mapping[str, Any], probe: Mapping[str, Any] | None) -> dict[str, Any]:
    """Produce a fail-closed event result from one retained/current probe."""
    result = dict(case)
    result["provider"] = "DNSE"
    result["dataset"] = DATASET
    if case.get("already_active_regression"):
        result.update({
            "sessions_observed": None,
            "raw_hypothesis_result": "REGRESSION_CASE_NOT_REEVALUATED",
            "adjusted_hypothesis_result": "ALREADY_ACTIVE",
            "verdict": "ADJUSTED_RETROSPECTIVE",
            "qualification_status": "ALREADY_ACTIVE_REGRESSION",
            "evidence_lineage": ["dnse_ohlc_price_basis_capability.py"],
            "blocker": None,
        })
        return result
    if probe is None:
        result.update({"sessions_observed": 0, "raw_hypothesis_result": "NOT_TESTED", "adjusted_hypothesis_result": "NOT_TESTED",
                       "verdict": "UNKNOWN/INSUFFICIENT_EVIDENCE", "qualification_status": "REQUEST_FAILURE",
                       "evidence_lineage": [], "blocker": "dnse_probe_not_retained"})
        return result
    if not probe.get("ok"):
        result.update({"sessions_observed": 0, "raw_hypothesis_result": "NOT_TESTED", "adjusted_hypothesis_result": "NOT_TESTED",
                       "verdict": "UNKNOWN/INSUFFICIENT_EVIDENCE", "qualification_status": "REQUEST_FAILURE",
                       "evidence_lineage": [probe.get("request_identity")], "blocker": str(probe.get("error_code", "provider_request_failed"))})
        return result
    bars = _bars(probe.get("body", {}))
    event_date = case["official_exright_date"]
    if bars is None:
        result.update({"sessions_observed": 0, "raw_hypothesis_result": "INVALID_PAYLOAD", "adjusted_hypothesis_result": "INVALID_PAYLOAD",
                       "verdict": "UNKNOWN/INSUFFICIENT_EVIDENCE", "qualification_status": "INSUFFICIENT_EVIDENCE",
                       "evidence_lineage": [probe.get("raw_payload_hash")], "blocker": "dnse_ohlc_payload_schema_invalid"})
        return result
    pre = [bar for bar in bars if bar["session"] < event_date]
    post = [bar for bar in bars if bar["session"] >= event_date]
    observations = {"total": len(bars), "pre_event": len(pre), "post_event": len(post), "exdate_present": any(bar["session"] == event_date for bar in bars)}
    result["sessions_observed"] = observations
    result["evidence_lineage"] = [probe.get("raw_payload_hash"), probe.get("request_identity")]
    if len(pre) < MIN_PRE_SESSIONS or len(post) < MIN_POST_SESSIONS or not observations["exdate_present"]:
        result.update({"raw_hypothesis_result": "INSUFFICIENT_SESSIONS", "adjusted_hypothesis_result": "INSUFFICIENT_SESSIONS",
                       "verdict": "UNKNOWN/INSUFFICIENT_EVIDENCE", "qualification_status": "INSUFFICIENT_EVIDENCE",
                       "blocker": "required_pre_post_sessions_or_exdate_observation_missing"})
        return result
    if case["event_code"] == "DIV":
        result.update({"raw_hypothesis_result": "NOT_DETERMINISTIC_FROM_SINGLE_CURRENT_CASH_WINDOW",
                       "adjusted_hypothesis_result": "NOT_DETERMINISTIC_FROM_SINGLE_CURRENT_CASH_WINDOW",
                       "verdict": "UNKNOWN/INSUFFICIENT_EVIDENCE", "qualification_status": "INSUFFICIENT_EVIDENCE",
                       "blocker": "cash_dividend_requires_independent_reference_or_pre_event_snapshot"})
        return result
    prior, exdate = pre[-1], next(bar for bar in post if bar["session"] == event_date)
    ratio = 1.0 + float(case["official_adjustment_inputs"]["exercise_ratio"])
    pattern = classify_internal_transition(float(prior["c"]), float(exdate["o"]), theoretical_ratio=ratio)
    result.update({
        "raw_hypothesis_result": "SUPPORTED" if pattern == RAW_PATTERN else "NOT_SUPPORTED",
        "adjusted_hypothesis_result": "SUPPORTED" if pattern == ADJUSTED_PATTERN else "NOT_SUPPORTED",
        "observed_event_pattern": pattern,
        "verdict": "UNKNOWN/INSUFFICIENT_EVIDENCE",
        "qualification_status": "INSUFFICIENT_EVIDENCE",
        "blocker": "current_query_has_no_pre_event_snapshot_to_establish_retroactive_rewrite",
    })
    return result


def reconcile(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    status_counts = Counter(str(row.get("qualification_status")) for row in rows)
    verdict_counts = Counter(str(row.get("verdict")) for row in rows)
    return {
        "eligible_official_cases": len(rows), "qualified_adjusted": verdict_counts["ADJUSTED_RETROSPECTIVE"],
        "qualified_raw": verdict_counts["RAW_AS_TRADED"],
        "insufficient_evidence": status_counts["INSUFFICIENT_EVIDENCE"],
        "provider_request_failures": status_counts["REQUEST_FAILURE"],
        "other": len(rows) - status_counts["INSUFFICIENT_EVIDENCE"] - status_counts["REQUEST_FAILURE"] - status_counts["ALREADY_ACTIVE_REGRESSION"],
        "already_active_regression": status_counts["ALREADY_ACTIVE_REGRESSION"],
        "exact_reconciliation": len(rows) == sum(status_counts.values()),
        "by_exchange_raw": dict(Counter(str(row.get("exchange_raw")) for row in rows)),
        "by_event_type": dict(Counter(str(row.get("event_type")) for row in rows)),
        "by_event_month": dict(Counter(str(row.get("official_exright_date"))[:7] for row in rows)),
        "by_verdict": dict(verdict_counts),
    }


def promotion_analysis(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    qualified = [row for row in rows if row.get("qualification_status") in {"NEWLY_QUALIFIED", "ALREADY_ACTIVE_REGRESSION"}]
    unresolved = [row for row in rows if row.get("qualification_status") == "INSUFFICIENT_EVIDENCE"]
    contradictions = [
        row for row in rows
        if row.get("qualification_status") == "CONTRADICTION"
        or row.get("verdict") == "CONTRADICTORY"
    ]
    exchanges = sorted({str(row.get("exchange_raw")) for row in qualified})
    types = sorted({str(row.get("event_type")) for row in qualified})
    dates = sorted(str(row.get("official_exright_date")) for row in qualified)
    blockers = []
    if len(exchanges) < 2: blockers.append("fewer_than_two_distinct_exchange_raw_groups")
    if contradictions: blockers.append("contradictory_event_verdicts_present")
    if unresolved: blockers.append("unresolved_event_cases_present")
    if not any(row.get("qualification_status") == "NEWLY_QUALIFIED" for row in rows): blockers.append("no_new_event_level_qualification")
    return {"lifecycle": "PROMOTION_REVIEW", "result": "NO_BROADER_PROMOTION_SUPPORTED", "proposed_scope": None,
            "evidence_count": len(qualified), "instruments": sorted({str(row.get("ticker")) for row in qualified}),
            "exchanges": exchanges, "event_types": types, "date_range": [dates[0], dates[-1]] if dates else None,
            "contradictions": [str(row.get("record_id")) for row in contradictions],
            "unresolved_cases": len(unresolved), "blockers": blockers}


def snapshot_coverage(snapshot_rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    statuses = Counter(str(row.get("price_basis_status", "UNKNOWN")) for row in snapshot_rows)
    known = sum(count for basis, count in statuses.items() if basis != "UNKNOWN")
    return {"candidates": sum(statuses.values()), "known_basis_under_active_authority": known, "unknown_basis": statuses["UNKNOWN"]}
