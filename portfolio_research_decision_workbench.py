"""Research-only view of how several opportunities overlap.

This is not position sizing, leverage, or an order. Current correlation is
accepted only when the caller supplies aligned series, and it is labelled
current research rather than historical PIT.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "portfolio_research_decision_workbench/v1"
FORBIDDEN = ("weight", "allocation", "position_size", "sizing", "leverage", "order", "buy_score", "target_price", "probability")


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    num = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    den_left = sum((a - mean_left) ** 2 for a in left) ** 0.5
    den_right = sum((b - mean_right) ** 2 for b in right) ** 0.5
    if den_left == 0 or den_right == 0:
        return None
    return num / (den_left * den_right)


def _correlation(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pairs = []
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            series_left = left.get("current_returns")
            series_right = right.get("current_returns")
            if not isinstance(series_left, list) or not isinstance(series_right, list):
                status = "MISSING"
                value = None
            else:
                value = _pearson([float(item) for item in series_left], [float(item) for item in series_right])
                status = "CURRENT_RESEARCH_ONLY" if value is not None else "NOT_COMPARABLE"
            pairs.append({
                "left": left["ticker"],
                "right": right["ticker"],
                "status": status,
                "value": value,
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
    for row in rows:
        measurements = row.get("measurements") if isinstance(row.get("measurements"), Mapping) else {}
        value = measurements.get(objective)
        if isinstance(value, (int, float)):
            ranked.append((float(value), row["ticker"]))
        else:
            missing.append(row["ticker"])
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return {
        "status": "RANKED_UNDER_EXPLICIT_OBJECTIVE",
        "objective": objective,
        "ordered_tickers": [ticker for _value, ticker in ranked],
        "measurement_missing": sorted(missing),
        "is_capital_allocation": False,
    }


def build_workbench(opportunities: Sequence[Mapping[str, Any]], *, objective: str | None = None) -> dict[str, Any]:
    seen: set[str] = set()
    rows = []
    duplicates = []
    for raw in opportunities:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("ticker"), str) or not raw["ticker"].strip():
            raise ValueError("TICKER_REQUIRED")
        _reject(raw)
        ticker = raw["ticker"].strip().upper()
        if ticker in seen:
            duplicates.append(ticker)
            continue
        seen.add(ticker)
        row = dict(raw)
        row["ticker"] = ticker
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
        "sector_concentration": _counts(rows, "sector"),
        "style_concentration": _counts(rows, "style"),
        "liquidity_context": _counts(rows, "liquidity_context"),
        "volatility_context": _counts(rows, "volatility_context"),
        "overlaps": _overlaps(rows),
        "current_correlation": _correlation(rows),
        "ranking": _rank(rows, objective),
    }
    body["workbench_identity"] = "portfolio_research_decision_workbench:" + _sha(body)
    return body
