"""Versioned, fail-closed mapping of observed VCI cash-flow and capital items."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


VERSION = "1.3.0"
_CORPORATE = {
    ("cash_flow", "net_cash_inflows_outflows_from_operating_activities"): "operating_cash_flow",
    ("cash_flow", "net_cash_inflows_outflows_from_investing_activities"): "investing_cash_flow",
    ("cash_flow", "net_cash_inflows_outflows_from_financing_activities"): "financing_cash_flow",
    ("cash_flow", "purchases_of_fixed_assets_and_other_long_term_assets"): "capital_expenditure",
    ("balance_sheet", "short_term_borrowings"): "short_term_borrowings",
    ("balance_sheet", "long_term_borrowings"): "long_term_borrowings",
    ("balance_sheet", "short_term_finance_lease"): "short_term_finance_lease_liabilities",
    ("balance_sheet", "long_term_financial_lease"): "long_term_finance_lease_liabilities",
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
    # 1.3.0: distress/strength identity expansion (Phase 6E) -- direct VCI item_ids
    # observed on the same already-cited, already-verified consolidated statement pages.
    ("balance_sheet", "current_liabilities"): "current_liabilities",
    ("balance_sheet", "undistributed_earnings"): "retained_earnings",
    ("income_statement", "profit_before_tax"): "profit_before_tax",
}
_BANK = {
    ("cash_flow", "net_cash_from_operating_activities"): "operating_cash_flow",
    ("cash_flow", "net_cash_from_investing_activities"): "investing_cash_flow",
    ("cash_flow", "purchases_of_fixed_assets_and_other_long_term_assets"): "capital_expenditure",
    ("income_statement", "interest_and_similar_expenses"): "interest_expense",
    ("income_statement", "attributable_to_parent_company"): "net_income_attributable_to_parent",
    # 1.2.0: VCB FY2024 banking archetype pilot (Circular 49/2014/TT-NHNN statement
    # template, VCI/KBS raw item_ids). Entity-type-scoped and reusable for any bank
    # sharing this raw item vocabulary -- never a ticker-specific condition. Banking
    # concepts get their own canonical names rather than reusing a corporate one,
    # except where a downstream contract's existing identity is genuinely the same
    # concept (net_income_attributable_to_parent, total_equity, minority_interest_equity,
    # total_assets, total_liabilities) so the existing reconciliation/derivation rules
    # apply unchanged. See docs/vcb_fy2024_banking_identity_qualification.md.
    ("income_statement", "interest_income_and_similar_income"): "interest_income",
    ("income_statement", "interest_expense_and_similar_expenses"): "interest_expense",
    ("income_statement", "net_interest_income"): "net_interest_income",
    ("income_statement", "net_fee_and_commission_income"): "net_fee_and_commission_income",
    ("income_statement", "net_gain_loss_from_foreign_currencies_and_gold_trading"): "net_gain_loss_fx_and_gold",
    ("income_statement", "net_gain_loss_from_trading_securities"): "net_gain_loss_trading_securities",
    ("income_statement", "net_gain_loss_from_investment_securities"): "net_gain_loss_investment_securities",
    ("income_statement", "net_other_income"): "bank_net_other_income",
    ("income_statement", "income_from_capital_contribution_and_long_term_investments"): "income_from_capital_contribution",
    ("income_statement", "operating_expenses"): "bank_operating_expenses",
    ("income_statement", "operating_profit_before_provision_for_credit_losses"): "operating_profit_before_credit_provision",
    ("income_statement", "provision_for_credit_losses"): "provision_for_credit_losses",
    ("income_statement", "profit_before_tax"): "profit_before_tax",
    ("income_statement", "corporate_income_tax"): "income_tax_expense",
    ("income_statement", "net_profit"): "net_profit_after_tax_total",
    ("income_statement", "net_profit_atttributable_to_the_equity_holders_of_the_bank"): "net_income_attributable_to_parent",
    ("balance_sheet", "cash_and_precious_metals"): "cash_and_precious_metals",
    ("balance_sheet", "balances_with_the_sbv"): "balances_with_central_bank",
    ("balance_sheet", "placements_with_and_loans_to_other_credit_institutions"): "placements_with_other_credit_institutions",
    ("balance_sheet", "loans_and_advances_to_customers"): "customer_loans_gross",
    ("balance_sheet", "less_provision_for_losses_on_loans_and_advances_to_customers"): "customer_loans_allowance",
    ("balance_sheet", "loans_and_advances_to_customers_net"): "customer_loans_net",
    ("balance_sheet", "investment_securities"): "investment_securities_total",
    ("balance_sheet", "total_assets"): "total_assets",
    ("balance_sheet", "total_liabilities"): "total_liabilities",
    ("balance_sheet", "deposits_from_customers"): "customer_deposits",
    ("balance_sheet", "deposits_and_loans_from_other_credit_institutions"): "funding_from_other_credit_institutions",
    ("balance_sheet", "convertible_bonds_cds_and_other_valuable_papers_issued"): "issued_debt_securities",
    ("balance_sheet", "owners_equity"): "total_equity",
    ("balance_sheet", "minority_interest"): "minority_interest_equity",
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
    records.extend(_derive_total_operating_income(records))
    records.extend(_derive_ebit(records))
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


def _derive_ebit(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """EBIT = profit_before_tax - interest_expense. interest_expense's canonical value is
    already negative (VCI's own raw storage sign for this item, reconciled against the
    unsigned printed statement figure by the interest_expenses sign rule in
    semantic_evidence_bridge.py); profit_before_tax is a natural positive subtotal that
    already had that same negative interest_expense deducted. Subtracting the (negative)
    interest_expense value therefore adds its magnitude back, recovering EBIT -- this is
    not EBITDA, operating profit, or any other proxy substituted for EBIT."""
    groups: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    for record in records:
        if record["canonical_metric"] not in {"profit_before_tax","interest_expense"} or record["qualification_state"] == "contradictory": continue
        key=tuple(record[k] for k in ("provider","vnstock_version","source_method","statement_type","reporting_frequency","period","statement_scope","currency","scale"))
        groups.setdefault(key,{})[record["canonical_metric"]]=record
    output=[]
    for group in groups.values():
        pbt,interest=group.get("profit_before_tax"),group.get("interest_expense")
        if not pbt or not interest or pbt["value"] is None or interest["value"] is None: continue
        output.append({**pbt,"canonical_metric":"ebit","value":pbt["value"]-interest["value"],"raw_item_code":None,"raw_label":None,"direct_or_derived":"derived","qualification_state":"partial" if "statement_scope_unknown" in pbt["warnings"] or "currency_or_scale_unknown" in pbt["warnings"] else "qualified","warnings":list(pbt["warnings"]),"provenance":{**pbt["provenance"],"components":[pbt,interest]}})
    return output


def _derive_total_operating_income(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bank total operating income (pre-provision, pre-opex) = the statement's own
    printed operating_profit_before_credit_provision with operating_expenses added
    back -- reverses the printed formula (I+II+...+VII-VIII=IX) instead of summing
    the individual income lines itself, so it can never silently drift from what
    the statement actually prints as its pre-opex operating-income subtotal."""
    groups: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    for record in records:
        if record["canonical_metric"] not in {"operating_profit_before_credit_provision","bank_operating_expenses"} or record["qualification_state"] == "contradictory": continue
        key=tuple(record[k] for k in ("provider","vnstock_version","source_method","statement_type","reporting_frequency","period","statement_scope","currency","scale"))
        groups.setdefault(key,{})[record["canonical_metric"]]=record
    output=[]
    for group in groups.values():
        profit,opex=group.get("operating_profit_before_credit_provision"),group.get("bank_operating_expenses")
        if not profit or not opex or profit["value"] is None or opex["value"] is None: continue
        output.append({**profit,"canonical_metric":"total_operating_income","value":profit["value"]+opex["value"],"raw_item_code":None,"raw_label":None,"direct_or_derived":"derived","qualification_state":"partial" if "statement_scope_unknown" in profit["warnings"] or "currency_or_scale_unknown" in profit["warnings"] else "qualified","warnings":list(profit["warnings"]),"provenance":{**profit["provenance"],"components":[profit,opex]}})
    return output
