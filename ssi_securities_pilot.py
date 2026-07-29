"""Frozen-time, fail-closed SSI securities-sector semantics pilot (Producer only)."""
from __future__ import annotations
from typing import Any, Mapping

VERSION = "1.0.0"
TICKER = "SSI"
ENTITY_TYPE = "securities"
FROZEN_PERIOD = "2024"
METRICS = ("brokerage_revenue", "margin_lending_balance", "proprietary_trading_assets", "proprietary_trading_result", "interest_income", "interest_expense", "net_income_attributable_to_parent", "shareholders_equity", "period_end_shares", "weighted_average_basic_shares")


def _unavailable(metric: str, blocker: str) -> dict[str, Any]:
    return {"metric": metric, "state": "unavailable", "value": None, "blocker_code": blocker, "entity_type": ENTITY_TYPE, "period": FROZEN_PERIOD, "lineage": []}


def evaluate(records: list[Mapping[str, Any]] | None, *, ticker: str = TICKER, period: str = FROZEN_PERIOD) -> dict[str, Any]:
    """Accept only cited, consolidated, annual VCI/KBS identities; never infer a sector metric."""
    if ticker != TICKER or period != FROZEN_PERIOD:
        return {"schema_version": VERSION, "state": "unavailable", "reason": "frozen_time_scope_mismatch", "metrics": {m: _unavailable(m, "frozen_time_scope_mismatch") for m in METRICS}}
    accepted: dict[str, dict[str, Any]] = {}
    for row in records or []:
        metric = str(row.get("metric") or "")
        if metric not in METRICS or row.get("provider") not in {"VCI", "KBS"}: continue
        if row.get("reporting_period") != FROZEN_PERIOD or row.get("reporting_frequency") != "annual": continue
        if row.get("statement_scope") != "consolidated" or not row.get("observation_id") or not row.get("citation_id"): continue
        if row.get("unit") != "VND" and metric not in {"period_end_shares", "weighted_average_basic_shares"}: continue
        if metric in {"period_end_shares", "weighted_average_basic_shares"} and row.get("unit") != "shares": continue
        if row.get("value") is None: continue
        accepted[metric] = {"metric": metric, "state": "available", "value": row["value"], "entity_type": ENTITY_TYPE, "period": FROZEN_PERIOD, "lineage": [{"provider": row["provider"], "observation_id": row["observation_id"], "citation_id": row["citation_id"], "raw_item_id": row.get("raw_item_id")}]} 
    metrics = {metric: accepted.get(metric, _unavailable(metric, "ssi_fy2024_qualified_annual_provider_identity_missing")) for metric in METRICS}
    return {"schema_version": VERSION, "ticker": TICKER, "entity_type": ENTITY_TYPE, "frozen_at": "2024-12-31", "state": "available" if accepted else "unavailable", "applicability": {"fcff_dcf": "inapplicable", "net_net": "inapplicable", "ev_ebitda": "inapplicable", "ev_sales": "inapplicable", "corporate_debt": "inapplicable"}, "metrics": metrics}