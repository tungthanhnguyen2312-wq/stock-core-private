"""P3-E factual valuation-input readiness only; no multiples, targets, or rankings."""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "valuation_input_readiness/v1"
FINANCIAL_INPUT_READY = "FINANCIAL_INPUT_READY"
FINANCIAL_INPUT_PARTIAL = "FINANCIAL_INPUT_PARTIAL"
FINANCIAL_INPUT_BLOCKED = "FINANCIAL_INPUT_BLOCKED"
MARKET_INPUT_BLOCKED = "MARKET_INPUT_BLOCKED"
NOT_APPLICABLE = "NOT_APPLICABLE"


def _qualified_facts(issuer: Mapping[str, Any]) -> set[str]:
    return {
        str(fact.get("canonical_metric")) for fact in issuer.get("facts", [])
        if fact.get("qualification_state") == "QUALIFIED"
    }


def _financial_family(name: str, available: set[str], required: tuple[str, ...], *, applicable: bool = True) -> dict[str, Any]:
    if not applicable:
        return {"family": name, "financial_status": NOT_APPLICABLE, "required_financial_identities": list(required), "missing_financial_identities": []}
    missing = [metric for metric in required if metric not in available]
    if not missing:
        status = FINANCIAL_INPUT_READY
    elif len(missing) == len(required):
        status = FINANCIAL_INPUT_BLOCKED
    else:
        status = FINANCIAL_INPUT_PARTIAL
    return {
        "family": name, "financial_status": status,
        "required_financial_identities": list(required), "missing_financial_identities": missing,
    }


def _share_basis(issuer: Mapping[str, Any]) -> dict[str, Any]:
    available = _qualified_facts(issuer)
    if "period_end_outstanding_ordinary_shares" in available:
        return {"state": "QUALIFIED_FOR_INTENDED_DATE_USE", "identity": "period_end_outstanding_ordinary_shares", "scope": "historical_only"}
    return {"state": "UNKNOWN", "identity": None, "scope": "blocked_for_historical_or_current_per_share_use"}


def evaluate_valuation_input_readiness(panel: Mapping[str, Any]) -> dict[str, Any]:
    """Return factual financial and separately-blocked market readiness per issuer/family."""
    rows: list[dict[str, Any]] = []
    for issuer in panel.get("issuers", []):
        identity = issuer.get("issuer_identity", {})
        ticker = str(identity.get("ticker"))
        entity_type = str(identity.get("entity_type"))
        available = _qualified_facts(issuer)
        if entity_type == "corporate":
            families = [
                _financial_family("P/E", available, ("net_income",)),
                _financial_family("P/B", available, ("shareholders_equity",)),
                _financial_family("P/S", available, ("revenue",)),
                _financial_family("EV/Sales", available, ("revenue", "cash_and_equivalents", "total_interest_bearing_debt")),
                _financial_family("EV/EBITDA", available, ("cash_and_equivalents", "total_interest_bearing_debt", "ebitda")),
                _financial_family("FCFF/DCF", available, ("operating_cash_flow", "capex", "working_capital_change", "tax_expense", "cash_and_equivalents", "total_interest_bearing_debt")),
            ]
        elif entity_type == "bank":
            families = [
                _financial_family("P/E", available, ("net_profit_parent",)),
                _financial_family("P/B", available, ("total_equity",)),
                _financial_family("bank_profitability_book", available, ("net_profit_parent", "total_equity")),
                _financial_family("EV/EBITDA", available, (), applicable=False),
                _financial_family("FCFF/DCF", available, (), applicable=False),
            ]
        elif entity_type == "securities":
            families = [
                _financial_family("P/E", available, ("profit_after_tax_parent",)),
                _financial_family("P/B", available, ("total_equity",)),
                _financial_family("securities_profitability_book", available, ("profit_after_tax_parent", "total_equity")),
                _financial_family("EV/EBITDA", available, (), applicable=False),
                _financial_family("FCFF/DCF", available, (), applicable=False),
            ]
        else:
            families = [_financial_family("unresolved_entity_class", available, (), applicable=False)]
        rows.append({
            "ticker": ticker, "entity_type": entity_type, "financial_facts_available": sorted(available),
            "share_basis": _share_basis(issuer), "market_dependency": {
                "status": MARKET_INPUT_BLOCKED,
                "reasons": ["P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE", "RAW_AS_TRADED_NOT_PROMOTED", "qualified_price_share_PIT_alignment_not_authorized"],
            },
            "families": families,
        })
    return {
        "contract_version": CONTRACT_VERSION, "is_valuation": False,
        "prohibited_outputs": ["valuation_multiple", "target_price", "intrinsic_value", "ranking", "recommendation"],
        "issuers": sorted(rows, key=lambda row: row["ticker"]),
    }
