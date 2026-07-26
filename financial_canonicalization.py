"""Deterministic canonical financial metric records over existing snapshot rows."""
from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

METRIC_FIELDS = {
    "revenue": "revenue", "gross_profit": "gross_profit", "operating_profit": "operating_profit",
    "profit_before_tax": "profit_before_tax", "net_income": "net_profit",
    "total_assets": "total_assets", "current_assets": "current_assets", "cash_and_equivalents": "cash",
    "receivables": "receivables", "inventory": "inventory", "total_liabilities": "total_liabilities",
    "total_debt": "debt", "shareholders_equity": "equity", "operating_cash_flow": "operating_cash_flow",
    "investing_cash_flow": "investing_cash_flow", "financing_cash_flow": "financing_cash_flow",
    "capital_expenditure": "capex", "interest_expense": "interest_expense", "dividends": "dividends",
    "share_count": "shares_period_end",
}
PERIOD_RE = re.compile(r"^(\d{4})(?:-Q([1-4]))?$")


def _value(value: Any) -> tuple[float | int | None, str | None]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None, "value_missing"
    if isinstance(value, bool): return None, "value_malformed"
    try:
        number = float(value)
    except (TypeError, ValueError): return None, "value_malformed"
    return (int(number) if number.is_integer() else number), None


def _identity(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    period = str(row.get("period") or "")
    match = PERIOD_RE.fullmatch(period)
    if not match: return None, "period_malformed"
    year, quarter = int(match.group(1)), match.group(2)
    kind = str(row.get("period_type") or ("quarter" if quarter else "annual")).lower()
    if quarter and kind not in {"quarter", "quarterly"}: return None, "period_type_incompatible"
    if not quarter and kind not in {"annual", "year", "fy"}: return None, "period_type_incompatible"
    return {"fiscal_year": year, "fiscal_quarter": int(quarter) if quarter else None,
            "period_type": "quarter" if quarter else "annual", "period_end": row.get("period_calendar_end"),
            "report_published_at": row.get("report_published_at"), "period": period}, None


def canonicalize_financial_rows(rows: pd.DataFrame, ticker: str | None = None) -> dict[str, Any]:
    """Return additive records; conflicting duplicate identities never win silently."""
    selected = rows.copy()
    if ticker is not None and "ticker" in selected: selected = selected[selected["ticker"] == ticker]
    records: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    invalid_periods: list[dict[str, Any]] = []
    for row in selected.to_dict("records"):
        identity, bad = _identity(row)
        if bad:
            invalid_periods.append({"period": row.get("period"), "reason": bad}); continue
        raw_scope = row.get("statement_scope") or row.get("operating_cash_flow_report_scope")
        scope = raw_scope if isinstance(raw_scope, str) and raw_scope.strip() else "unknown"
        raw_currency = row.get("statement_currency")
        currency = raw_currency if isinstance(raw_currency, str) and raw_currency.strip() else "unknown"
        raw_scale = row.get("statement_scale")
        scale = None if raw_scale is None or (isinstance(raw_scale, float) and math.isnan(raw_scale)) else raw_scale
        raw_source = row.get("source")
        source = raw_source if isinstance(raw_source, str) and raw_source.strip() else "financial_snapshot"
        for name, field in METRIC_FIELDS.items():
            if field not in row: continue
            value, issue = _value(row.get(field))
            status_key = f"{field}_status"
            derivation = "derived" if str(row.get(status_key) or "").lower() in {"derived", "proxy"} else "reported"
            quality = "unavailable" if issue else ("unknown" if scope == "unknown" else "available")
            record = {"canonical_metric": name, "value": value, "source_field": field,
                      "source_statement": "financial_snapshot", "source": source,
                      "period_identity": identity, "statement_scope": scope,
                      "currency": currency, "unit_scale": scale, "derivation_status": derivation,
                      "quality_state": quality, "reason": issue or ("statement_scope_unknown" if scope == "unknown" else None),
                      "restatement_state": row.get("restatement_state") or "unknown"}
            key = (name, identity["period"], str(scope), str(source))
            previous = seen.get(key)
            if previous and previous["value"] != record["value"]:
                previous["quality_state"] = "incomparable"; previous["reason"] = "duplicate_identity_conflicting_value"
                record["quality_state"] = "incomparable"; record["reason"] = "duplicate_identity_conflicting_value"
            seen[key] = record; records.append(record)
    # A TTM outcome is explicit for every metric/scope combination; unavailable is not synthesized.
    base = list(records)
    for metric, scope in sorted({(r["canonical_metric"], r["statement_scope"]) for r in base}):
        records.append(derive_ttm(base, metric, scope))
    records.sort(key=lambda r: (r["canonical_metric"], (r["period_identity"] or {}).get("period", ""), r["statement_scope"], str(r["source_field"])))
    return {"status": "available" if records else "missing", "ticker": ticker, "records": records,
            "invalid_periods": sorted(invalid_periods, key=lambda x: (str(x["period"]), x["reason"]))}


def derive_ttm(records: list[dict[str, Any]], metric: str, scope: str) -> dict[str, Any]:
    candidates = [r for r in records if r["canonical_metric"] == metric and r["statement_scope"] == scope and r["period_identity"]["period_type"] == "quarter" and r["quality_state"] == "available" and r["derivation_status"] == "reported"]
    by_period = {(r["period_identity"]["fiscal_year"], r["period_identity"]["fiscal_quarter"]): r for r in candidates}
    for year, quarter in sorted(by_period, reverse=True):
        sequence = [(year, quarter - i) for i in range(4)]
        normalized = [(y - 1, q + 4) if q <= 0 else (y, q) for y, q in sequence]
        if all(key in by_period and by_period[key]["value"] is not None for key in normalized):
            return {"canonical_metric": metric, "value": sum(by_period[key]["value"] for key in normalized), "period_identity": {"fiscal_year": year, "fiscal_quarter": quarter, "period_type": "ttm", "period": f"{year}-Q{quarter}-TTM"}, "statement_scope": scope, "derivation_status": "derived", "quality_state": "available", "reason": None, "source_field": "four_compatible_quarters", "source_statement": "financial_snapshot", "source": "financial_snapshot", "currency": by_period[normalized[0]]["currency"], "unit_scale": by_period[normalized[0]]["unit_scale"], "restatement_state": "unknown"}
    return {"canonical_metric": metric, "value": None, "period_identity": None, "statement_scope": scope, "derivation_status": "not_derived", "quality_state": "unavailable", "reason": "requires_four_compatible_standalone_quarters", "source_field": None, "source_statement": "financial_snapshot", "source": "financial_snapshot", "currency": None, "unit_scale": None, "restatement_state": "unknown"}
