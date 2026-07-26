"""Versioned, fail-closed mapping of observed VCI cash-flow and capital items."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


VERSION = "1.1.0"
_CORPORATE = {
    ("cash_flow", "net_cash_inflows_outflows_from_operating_activities"): "operating_cash_flow",
    ("cash_flow", "net_cash_inflows_outflows_from_investing_activities"): "investing_cash_flow",
    ("cash_flow", "net_cash_inflows_outflows_from_financing_activities"): "financing_cash_flow",
    ("cash_flow", "purchases_of_fixed_assets_and_other_long_term_assets"): "capital_expenditure",
    ("balance_sheet", "short_term_borrowings"): "short_term_borrowings",
    ("balance_sheet", "long_term_borrowings"): "long_term_borrowings",
    ("balance_sheet", "cash_and_cash_equivalents"): "cash_and_equivalents",
    ("income_statement", "interest_expenses"): "interest_expense",
    ("income_statement", "attributable_to_parent_company"): "net_income_attributable_to_parent",
    # 1.1.0: core observation expansion (revenue/assets/equity/debt identity reconciliation).
    ("balance_sheet", "total_assets"): "total_assets",
    ("balance_sheet", "owners_equity"): "total_equity",
    ("balance_sheet", "minority_interests"): "minority_interest_equity",
    ("balance_sheet", "current_assets"): "current_assets",
    ("balance_sheet", "accounts_receivable"): "receivables",
    ("balance_sheet", "inventories_net"): "inventory",
    ("balance_sheet", "liabilities"): "total_liabilities",
    ("income_statement", "net_sales"): "revenue",
    ("income_statement", "net_profit_loss_after_tax"): "net_profit_after_tax_total",
    ("income_statement", "minority_interests"): "minority_interest_net_income",
}
_BANK = {
    ("cash_flow", "net_cash_from_operating_activities"): "operating_cash_flow",
    ("cash_flow", "net_cash_from_investing_activities"): "investing_cash_flow",
    ("cash_flow", "purchases_of_fixed_assets_and_other_long_term_assets"): "capital_expenditure",
    ("income_statement", "interest_and_similar_expenses"): "interest_expense",
    ("income_statement", "attributable_to_parent_company"): "net_income_attributable_to_parent",
}


def _number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool): return None
    try: number = float(value)
    except (TypeError, ValueError): return None
    if math.isnan(number): return None
    return int(number) if number.is_integer() else number


def canonicalize_items(items: Sequence[Mapping[str, Any]], *, entity_type: str) -> dict[str, Any]:
    """Map exact observed VCI item IDs without deriving quarterly standalones."""
    rules = _BANK if entity_type == "bank" else _CORPORATE if entity_type == "corporate" else {}
    records: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for item in items:
        provider, statement = str(item.get("provider") or ""), str(item.get("statement_type") or "")
        metric = rules.get((statement, str(item.get("raw_item_code") or ""))) if provider == "VCI" else None
        if metric is None: continue
        period = str(item.get("period") or "")
        frequency = str(item.get("reporting_frequency") or "unknown")
        value = _number(item.get("value"))
        if item.get("value") is not None and value is None:
            return {"status":"malformed", "records":[], "reason":"value_malformed"}
        scope = str(item.get("statement_scope") or "unknown")
        record = {"canonical_metric":metric, "raw_item_code":item.get("raw_item_code"), "raw_label":item.get("raw_label"),
            "provider":provider, "vnstock_version":item.get("vnstock_version"), "source_method":item.get("source_method"),
            "parameters":dict(item.get("parameters") or {}), "statement_type":statement, "reporting_frequency":frequency,
            "period":period, "statement_scope":scope, "value":value, "currency":item.get("currency"), "scale":item.get("scale"),
            "direct_or_derived":"direct", "qualification_state":"qualified_item_identity" if scope != "unknown" and item.get("currency") and item.get("scale") is not None else "partial",
            "warnings":[warning for warning in (["statement_scope_unknown"] if scope == "unknown" else []) + (["currency_or_scale_unknown"] if not item.get("currency") or item.get("scale") is None else []) + (["quarterly_cumulative_semantics_unknown"] if frequency == "quarterly" and item.get("cumulative_state") != "standalone" else [])],
            "provenance": {"retrieved_at":item.get("retrieved_at"), "cumulative_state":item.get("cumulative_state") or "unknown"}}
        key=(metric, provider, statement, frequency, period)
        prior=seen.get(key)
        if prior and prior["value"] != value:
            prior["qualification_state"]="contradictory"; prior["warnings"].append("conflicting_same_identity_value")
            record["qualification_state"]="contradictory"; record["warnings"].append("conflicting_same_identity_value")
        seen[key]=record; records.append(record)
    records.extend(_derive_total_debt(records))
    records.extend(_derive_shareholders_equity(records))
    return {"status":"available" if records else "unavailable", "records":sorted(records,key=lambda r:(r["canonical_metric"],r["provider"],r["period"]))}


def _derive_total_debt(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    for record in records:
        if record["canonical_metric"] not in {"short_term_borrowings","long_term_borrowings"} or record["qualification_state"] == "contradictory": continue
        key=tuple(record[k] for k in ("provider","vnstock_version","source_method","statement_type","reporting_frequency","period","statement_scope","currency","scale"))
        groups.setdefault(key,{})[record["canonical_metric"]]=record
    output=[]
    for group in groups.values():
        short,long=group.get("short_term_borrowings"),group.get("long_term_borrowings")
        if not short or not long or short["value"] is None or long["value"] is None: continue
        output.append({**short,"canonical_metric":"total_interest_bearing_debt","value":short["value"]+long["value"],"raw_item_code":None,"raw_label":None,"direct_or_derived":"derived","qualification_state":"partial" if "statement_scope_unknown" in short["warnings"] or "currency_or_scale_unknown" in short["warnings"] else "qualified","warnings":list(short["warnings"]),"provenance":{**short["provenance"],"components":[short,long]}})
    return output


def _derive_shareholders_equity(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parent-only equity = total_equity (owners_equity, mã 400) minus minority_interest_equity
    (mã 429); VCI never reports the parent-only (mã 410) subtotal as its own item."""
    groups: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    for record in records:
        if record["canonical_metric"] not in {"total_equity","minority_interest_equity"} or record["qualification_state"] == "contradictory": continue
        key=tuple(record[k] for k in ("provider","vnstock_version","source_method","statement_type","reporting_frequency","period","statement_scope","currency","scale"))
        groups.setdefault(key,{})[record["canonical_metric"]]=record
    output=[]
    for group in groups.values():
        total,minority=group.get("total_equity"),group.get("minority_interest_equity")
        if not total or not minority or total["value"] is None or minority["value"] is None: continue
        output.append({**total,"canonical_metric":"shareholders_equity","value":total["value"]-minority["value"],"raw_item_code":None,"raw_label":None,"direct_or_derived":"derived","qualification_state":"partial" if "statement_scope_unknown" in total["warnings"] or "currency_or_scale_unknown" in total["warnings"] else "qualified","warnings":list(total["warnings"]),"provenance":{**total["provenance"],"components":[total,minority]}})
    return output
