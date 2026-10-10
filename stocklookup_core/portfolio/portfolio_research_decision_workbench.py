"""Research-only view of how several opportunities overlap.

This is not position sizing, leverage, or an order. Current correlation is
accepted only when the caller supplies aligned series, and it is labelled
current research rather than historical PIT. A correlation is comparable only
when both series carry dates and are aligned on their shared dates; undated
equal-length series keep their value but are marked unverified.

Sector and style counts here count supplied opportunities. They are not the
owner's exposure; owner exposure comes only from an explicit portfolio state.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "portfolio_research_decision_workbench/v1"
FORBIDDEN = ("weight", "allocation", "position_size", "sizing", "leverage", "order", "buy_score", "target_price", "probability")


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _reject(payload: Mapping[str, Any]) -> None:
    for key in FORBIDDEN:
        if key in payload:
            raise ValueError(f"FORBIDDEN_{key.upper()}")


def _counts(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    missing = 0
    for row in rows:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            missing += 1
            continue
        counts[value] = counts.get(value, 0) + 1
    return {"counts": dict(sorted(counts.items())), "missing": missing}


OPPORTUNITY_COUNT_BASIS = "OPPORTUNITY_COUNT_NOT_OWNER_EXPOSURE"
ALIGNMENT_VERIFIED = "DATE_ALIGNED_ON_SHARED_DATES"
ALIGNMENT_UNVERIFIED = "CALLER_ASSERTED_UNVERIFIED"


def _concentration(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    out = _counts(rows, field)
    out["basis"] = OPPORTUNITY_COUNT_BASIS
    return out


def _finite_number(value: Any) -> tuple[float | None, str | None]:
    if isinstance(value, bool):
        return None, "BOOLEAN_NOT_MEASUREMENT"
    if not isinstance(value, (int, float)):
        return None, "NON_NUMERIC"
    try:
        number = float(value)
    except OverflowError:
        return None, "NUMERIC_RANGE_UNAVAILABLE"
    if not math.isfinite(number):
        return None, "NONFINITE"
    return number, None


def _returns(series: list[Any]) -> list[float] | str:
    values = []
    for value in series:
        number, reason = _finite_number(value)
        if reason:
            return "RETURN_VALUES_" + reason
        values.append(number)
    return values


def _dated(series: Any, dates: Any) -> dict[str, float] | str:
    """Map date -> return, or a reason the series cannot be aligned."""
    if not isinstance(dates, list) or len(dates) != len(series):
        return "DATES_LENGTH_MISMATCH"
    if not all(isinstance(item, str) and item.strip() for item in dates):
        return "DATES_INVALID"
    try:
        if any(date.fromisoformat(item).isoformat() != item for item in dates):
            return "DATES_INVALID"
    except ValueError:
        return "DATES_INVALID"
    if len(set(dates)) != len(dates):
        return "DATES_DUPLICATED"
    return {date: float(value) for date, value in zip(dates, series)}


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    try:
        # Preserve the released arithmetic for ordinary valid inputs.
        mean_left = sum(left) / len(left)
        mean_right = sum(right) / len(right)
        num = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
        den_left = sum((a - mean_left) ** 2 for a in left) ** 0.5
        den_right = sum((b - mean_right) ** 2 for b in right) ** 0.5
        if not all(math.isfinite(value) for value in (mean_left, mean_right, num, den_left, den_right, den_left * den_right)):
            raise ValueError("CORRELATION_NUMERICAL_UNAVAILABLE")
        if den_left == 0 or den_right == 0:
            return None
        result = num / (den_left * den_right)
        if not math.isfinite(result):
            raise ValueError("CORRELATION_NUMERICAL_UNAVAILABLE")
        return result
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("CORRELATION_NUMERICAL_UNAVAILABLE") from exc


def _pair_correlation(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[str, float | None, str | None, int]:
    series_left = left.get("current_returns")
    series_right = right.get("current_returns")
    if not isinstance(series_left, list) or not isinstance(series_right, list):
        if any("current_returns" in row and row["current_returns"] is not None
               and not isinstance(row["current_returns"], list) for row in (left, right)):
            return "NOT_COMPARABLE", None, "RETURN_SERIES_INVALID_SHAPE", 0
        if any("current_returns" in row and row["current_returns"] is None for row in (left, right)):
            return "MISSING", None, "RETURN_SERIES_PRESENT_NULL", 0
        return "MISSING", None, None, 0
    series_left, series_right = _returns(series_left), _returns(series_right)
    for series in (series_left, series_right):
        if isinstance(series, str):
            return "NOT_COMPARABLE", None, series, 0
    dates_left = left.get("current_return_dates")
    dates_right = right.get("current_return_dates")
    if dates_left is None and dates_right is None:
        # Backward-compatible path: the caller asserts alignment. The value is kept, but it is
        # never presented as comparable because nothing proves the points share dates.
        try:
            value = _pearson(series_left, series_right)
        except ValueError:
            return "NOT_COMPARABLE", None, "CORRELATION_NUMERICAL_UNAVAILABLE", min(len(series_left), len(series_right))
        status = "CURRENT_RESEARCH_ONLY" if value is not None else "NOT_COMPARABLE"
        return status, value, ALIGNMENT_UNVERIFIED, min(len(series_left), len(series_right))
    if dates_left is None or dates_right is None:
        return "NOT_COMPARABLE", None, "DATES_ONE_SIDED", 0
    mapped_left = _dated(series_left, dates_left)
    mapped_right = _dated(series_right, dates_right)
    for mapped in (mapped_left, mapped_right):
        if isinstance(mapped, str):
            return "NOT_COMPARABLE", None, mapped, 0
    shared = sorted(set(mapped_left) & set(mapped_right))
    try:
        value = _pearson([mapped_left[date] for date in shared], [mapped_right[date] for date in shared])
    except ValueError:
        return "NOT_COMPARABLE", None, "CORRELATION_NUMERICAL_UNAVAILABLE", len(shared)
    status = "CURRENT_RESEARCH_ONLY" if value is not None else "NOT_COMPARABLE"
    return status, value, ALIGNMENT_VERIFIED, len(shared)


def _correlation(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pairs = []
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            status, value, alignment, points = _pair_correlation(left, right)
            pairs.append({
                "left": left["ticker"],
                "right": right["ticker"],
                "status": status,
                "value": value,
                "date_alignment": alignment,
                "aligned_points": points,
                "comparable": status == "CURRENT_RESEARCH_ONLY" and alignment == ALIGNMENT_VERIFIED,
                "authority": "CURRENT_RESEARCH_ONLY_NOT_PIT",
            })
    return {"status": "PRESENT" if pairs else "MISSING", "pairs": pairs}


def _overlaps(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    thesis: dict[str, list[str]] = {}
    event: dict[str, list[str]] = {}
    for row in rows:
        ticker = row["ticker"]
        for thesis_id in row.get("thesis_ids") or []:
            if isinstance(thesis_id, str):
                thesis.setdefault(thesis_id, []).append(ticker)
        for event_id in row.get("event_ids") or []:
            if isinstance(event_id, str):
                event.setdefault(event_id, []).append(ticker)
    shared_thesis = {key: sorted(value) for key, value in sorted(thesis.items()) if len(value) > 1}
    shared_event = {key: sorted(value) for key, value in sorted(event.items()) if len(value) > 1}
    return {"shared_thesis_ids": shared_thesis, "shared_event_ids": shared_event}


def _rank(rows: Sequence[Mapping[str, Any]], objective: str | None) -> dict[str, Any]:
    if not objective:
        return {"status": "OBJECTIVE_NOT_SUPPLIED", "ordered_tickers": []}
    ranked = []
    missing = []
    rejected = {}
    for row in rows:
        measurements = row.get("measurements") if isinstance(row.get("measurements"), Mapping) else {}
        value = measurements.get(objective)
        number, reason = _finite_number(value)
        if reason is None:
            ranked.append((number, row["ticker"]))
        else:
            missing.append(row["ticker"])
            if objective in measurements:
                rejected[row["ticker"]] = "PRESENT_NULL" if value is None else reason
    ranked.sort(key=lambda item: (-item[0], item[1]))
    result = {
        "status": "RANKED_UNDER_EXPLICIT_OBJECTIVE",
        "objective": objective,
        "ordered_tickers": [ticker for _value, ticker in ranked],
        "measurement_missing": sorted(missing),
        "is_capital_allocation": False,
    }
    if rejected:
        result["measurement_rejected"] = dict(sorted(rejected.items()))
    return result


def build_workbench(opportunities: Sequence[Mapping[str, Any]], *, objective: str | None = None) -> dict[str, Any]:
    seen: set[str] = set()
    rows = []
    duplicates = []
    by_ticker = {}
    for raw in opportunities:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("ticker"), str) or not raw["ticker"].strip():
            raise ValueError("TICKER_REQUIRED")
        _reject(raw)
        ticker = raw["ticker"].strip().upper()
        row = dict(raw)
        row["ticker"] = ticker
        if ticker in seen:
            # Exact duplicate only; input order cannot resolve conflicting evidence.
            if row != by_ticker[ticker] or _canon(row) != _canon(by_ticker[ticker]):
                raise ValueError("CONFLICTING_DUPLICATE_TICKER")
            duplicates.append(ticker)
            continue
        seen.add(ticker)
        by_ticker[ticker] = row
        rows.append(row)
    rows.sort(key=lambda row: row["ticker"])
    body = {
        "contract_version": CONTRACT_VERSION,
        "authority": "RESEARCH_ONLY",
        "is_actionable": False,
        "leverage": None,
        "position_size": None,
        "order": None,
        "member_count": len(rows),
        "duplicate_tickers_collapsed": sorted(set(duplicates)),
        "sector_concentration": _concentration(rows, "sector"),
        "style_concentration": _concentration(rows, "style"),
        "liquidity_context": _counts(rows, "liquidity_context"),
        "volatility_context": _counts(rows, "volatility_context"),
        "overlaps": _overlaps(rows),
        "current_correlation": _correlation(rows),
        "ranking": _rank(rows, objective),
        "evidence_comparison": {
            "evidence_quality": _counts(rows, "evidence_quality"),
            "setup_maturity": _counts(rows, "setup_maturity"),
            "event_risk": _counts(rows, "event_risk"),
            "analogue_quality": _counts(rows, "analogue_quality"),
            "outcome_evidence_quality": _counts(rows, "outcome_evidence_quality"),
            "weights": None,
            "leverage": None,
            "is_optimizer": False,
        },
    }
    body["workbench_identity"] = "portfolio_research_decision_workbench:" + _sha(body)
    return body
