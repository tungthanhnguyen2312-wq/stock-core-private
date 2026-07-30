"""Frozen-time, fail-closed SSI securities-sector semantics pilot (Producer only)."""
from __future__ import annotations
from typing import Any, Mapping

VERSION = "1.1.0"
TICKER = "SSI"
ENTITY_TYPE = "securities"
FROZEN_PERIOD = "2024"
SUPPORTED_PROVIDER_METHODS = {"brokerage_revenue": {"income_statement"}, "margin_lending_balance": {"balance_sheet"}, "proprietary_trading_assets": {"balance_sheet"}, "proprietary_trading_result": {"income_statement"}, "interest_income": {"income_statement"}, "interest_expense": {"income_statement"}, "net_income_attributable_to_parent": {"income_statement"}, "shareholders_equity": {"balance_sheet"}, "period_end_shares": set(), "weighted_average_basic_shares": set()}
OFFICIAL_METRIC_MAP = {"brokerage_revenue":"brokerage_revenue", "financial_assets_fvtpl":"proprietary_trading_assets", "interest_income_demand_deposits":"interest_income", "borrowing_costs":"interest_expense", "profit_after_tax_parent":"net_income_attributable_to_parent", "total_equity":"shareholders_equity", "period_end_outstanding_ordinary_shares":"period_end_shares"}
METRICS = ("brokerage_revenue", "margin_lending_balance", "proprietary_trading_assets", "proprietary_trading_result", "interest_income", "interest_expense", "net_income_attributable_to_parent", "shareholders_equity", "period_end_shares", "weighted_average_basic_shares")


def _unavailable(metric: str, blocker: str) -> dict[str, Any]:
    return {"metric": metric, "state": "unavailable", "value": None, "blocker_code": blocker, "entity_type": ENTITY_TYPE, "period": FROZEN_PERIOD, "lineage": []}


def _official(row: Mapping[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    source=row.get("official_document_source") if isinstance(row.get("official_document_source"), Mapping) else {}
    metric=OFFICIAL_METRIC_MAP.get(str(row.get("canonical_metric") or ""))
    period=(row.get("period_identity") or {}).get("period") if isinstance(row.get("period_identity"), Mapping) else None
    if (not metric or row.get("source")!="official_document_observation" or source.get("source_type")!="official_document_observation" or period!=FROZEN_PERIOD or row.get("statement_scope")!="consolidated" or not source.get("document_sha256") or not source.get("page_citation_id") or row.get("value") is None): return None,None
    unit=row.get("unit")
    if metric in {"period_end_shares","weighted_average_basic_shares"}:
        if unit not in {"shares","number_of_shares"}: return None,None
    elif unit!="VND": return None,None
    return metric,{"metric":metric,"state":"available","value":row["value"],"entity_type":ENTITY_TYPE,"period":FROZEN_PERIOD,"lineage":[{"source_type":"official_document_observation","document_sha256":source["document_sha256"],"citation_id":source["page_citation_id"],"raw_label":source["raw_label"],"page":source["page"],"qualification_version":source["qualification_version"]}]}


def evaluate(records: list[Mapping[str, Any]] | None, *, ticker: str = TICKER, period: str = FROZEN_PERIOD) -> dict[str, Any]:
    """Accept only cited annual consolidated provider or official-document identities."""
    if ticker != TICKER or period != FROZEN_PERIOD:
        return {"schema_version": VERSION, "state": "unavailable", "reason": "frozen_time_scope_mismatch", "metrics": {m: _unavailable(m, "frozen_time_scope_mismatch") for m in METRICS}}
    accepted: dict[str, dict[str, Any]] = {}
    for row in records or []:
        metric, official=_official(row)
        if official is not None:
            accepted[metric]=official; continue
        metric=str(row.get("metric") or "")
        if metric not in METRICS or row.get("provider") not in {"VCI","KBS"} or row.get("method") not in SUPPORTED_PROVIDER_METHODS[metric]: continue
        if row.get("reporting_period")!=FROZEN_PERIOD or row.get("reporting_frequency")!="annual" or row.get("statement_scope")!="consolidated" or not row.get("observation_id") or not row.get("citation_id") or row.get("value") is None: continue
        if row.get("unit")!="VND" and metric not in {"period_end_shares","weighted_average_basic_shares"}: continue
        if metric in {"period_end_shares","weighted_average_basic_shares"} and row.get("unit")!="shares": continue
        accepted[metric]={"metric":metric,"state":"available","value":row["value"],"entity_type":ENTITY_TYPE,"period":FROZEN_PERIOD,"lineage":[{"source_type":"provider_observation","provider":row["provider"],"observation_id":row["observation_id"],"citation_id":row["citation_id"],"raw_item_id":row.get("raw_item_id"),"method":row["method"]}]}
    metrics={metric:accepted.get(metric,_unavailable(metric,"ssi_fy2024_qualified_annual_identity_missing")) for metric in METRICS}
    return {"schema_version":VERSION,"ticker":TICKER,"entity_type":ENTITY_TYPE,"frozen_at":"2024-12-31","state":"available" if accepted else "unavailable","applicability":{"fcff_dcf":"inapplicable","net_net":"inapplicable","ev_ebitda":"inapplicable","ev_sales":"inapplicable","corporate_debt":"inapplicable"},"metrics":metrics}
