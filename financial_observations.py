"""Append-only retained VCI financial observations for the bounded Phase 14B pilot."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from cash_flow_debt_mapping import canonicalize_items


SCHEMA_VERSION = "1.0.0"
RELATIVE_STORE = Path("data") / "financial-observations" / "observations.jsonl"
METHODS = ("income_statement", "balance_sheet", "cash_flow")
FREQUENCIES = ("year", "quarter")
_CODES = {"net_cash_inflows_outflows_from_operating_activities", "net_cash_inflows_outflows_from_investing_activities", "net_cash_inflows_outflows_from_financing_activities", "net_cash_from_operating_activities", "net_cash_from_investing_activities", "purchases_of_fixed_assets_and_other_long_term_assets", "short_term_borrowings", "long_term_borrowings", "cash_and_cash_equivalents", "interest_expenses", "interest_and_similar_expenses", "attributable_to_parent_company",
    "total_assets", "owners_equity", "minority_interests", "current_assets", "accounts_receivable", "inventories_net", "liabilities", "net_sales", "net_profit_loss_after_tax",
    # Bank archetype (Circular 49/2014/TT-NHNN statement template) -- entity_type="bank" only,
    # selected via _BANK in cash_flow_debt_mapping.py. Raw VCI/KBS item_ids differ from the
    # corporate (Circular 200/202) template above even where the underlying concept is similar,
    # so they are listed explicitly rather than reused.
    "interest_income_and_similar_income", "interest_expense_and_similar_expenses", "net_interest_income",
    "net_fee_and_commission_income", "net_gain_loss_from_foreign_currencies_and_gold_trading",
    "net_gain_loss_from_trading_securities", "net_gain_loss_from_investment_securities", "net_other_income",
    "income_from_capital_contribution_and_long_term_investments", "operating_expenses",
    "operating_profit_before_provision_for_credit_losses", "provision_for_credit_losses", "profit_before_tax",
    "corporate_income_tax", "net_profit", "net_profit_atttributable_to_the_equity_holders_of_the_bank",
    "cash_and_precious_metals", "balances_with_the_sbv", "placements_with_and_loans_to_other_credit_institutions",
    "loans_and_advances_to_customers", "less_provision_for_losses_on_loans_and_advances_to_customers",
    "loans_and_advances_to_customers_net", "investment_securities", "total_liabilities", "deposits_from_customers",
    "deposits_and_loans_from_other_credit_institutions", "convertible_bonds_cds_and_other_valuable_papers_issued",
    "minority_interest"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool): return None
    try: number=float(value)
    except (TypeError, ValueError): return None
    if number != number: return None
    return int(number) if number.is_integer() else number


def store_path(runtime_root: Path) -> Path:
    return runtime_root / RELATIVE_STORE


def _period(header: str, requested: str) -> tuple[str, str] | None:
    if requested == "year" and header[:4].isdigit() and "Q" not in header: return header[:4], "annual"
    if requested == "quarter" and len(header) >= 7 and header[4:6] == "-Q" and header[6] in "1234": return header[:7], "quarterly"
    return None


def observations_from_frame(frame: Any, *, ticker: str, entity_type: str, method: str, requested_frequency: str, retrieved_at: str, version: str) -> list[dict[str, Any]]:
    columns=[str(c) for c in frame.columns]; headers=[c for c in columns if _period(c, requested_frequency)]
    fingerprint=_hash(columns); response_hash=_hash(json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False)))
    output=[]
    for _, row in frame.iterrows():
        code=str(row.get("item_id") or "")
        if code not in _CODES: continue
        for header in headers:
            value=_number(row.get(header))
            if row.get(header) is not None and value is None: continue
            period, frequency=_period(header, requested_frequency)  # type: ignore[misc]
            identity={"ticker":ticker.upper(),"provider":"VCI","method":method,"parameters":{"period":requested_frequency},"statement_type":method,"period":period,"source_header":header,"raw_item_id":code}
            observation={"schema_version":SCHEMA_VERSION,"identity_key":_hash(identity),"ticker":ticker.upper(),"issuer_identity":ticker.upper(),"provider":"VCI","library":"vnstock","library_version":version,"source_method":method,"parameters":{"period":requested_frequency},"retrieved_at":retrieved_at,"raw_statement_type":method,"requested_reporting_frequency":requested_frequency,"reporting_frequency":frequency,"reporting_period":period,"source_header":header,"raw_item_id":code,"raw_label_vi":row.get("item"),"raw_label_en":row.get("item_en"),"raw_value":value,"raw_currency":None,"raw_scale":None,"statement_scope":"unknown","cumulative_state":"unknown","schema_fingerprint":fingerprint,"source_record_hash":response_hash,"qualification_state":"retained_exact_item_id","warnings":["statement_scope_unknown","currency_and_scale_unknown"]}
            observation["observation_id"]=_hash({**identity,"source_record_hash":response_hash,"raw_value":value,"schema_fingerprint":fingerprint})
            output.append(observation)
    return output


def read_observations(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    records=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip(): records.append(json.loads(line))
    return records


def append_observations(path: Path, observations: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    existing=read_observations(path); ids={row["observation_id"] for row in existing}; path.parent.mkdir(parents=True, exist_ok=True)
    added=[]
    for row in observations:
        if row["observation_id"] not in ids: added.append(dict(row)); ids.add(row["observation_id"])
    if added:
        with path.open("a",encoding="utf-8",newline="\n") as stream:
            for row in added: stream.write(_json(row)+"\n")
    return {"existing":len(existing),"added":len(added),"total":len(existing)+len(added)}


def ingest_pilot(runtime_root: Path, tickers: Mapping[str,str], *, retrieved_at: str | None = None) -> dict[str, Any]:
    from vnstock.api.financial import Finance
    retrieved_at=retrieved_at or datetime.now(timezone.utc).isoformat(); version=importlib.metadata.version("vnstock"); collected=[]
    for ticker, entity in tickers.items():
        for method in METHODS:
            for frequency in FREQUENCIES:
                frame=getattr(Finance(source="VCI",symbol=ticker,show_log=False),method)(period=frequency)
                collected.extend(observations_from_frame(frame,ticker=ticker,entity_type=entity,method=method,requested_frequency=frequency,retrieved_at=retrieved_at,version=version))
    path=store_path(runtime_root); result=append_observations(path,collected)
    return {"path":str(path),"retrieved_at":retrieved_at,"version":version,"counts":{ticker:sum(row["ticker"]==ticker for row in collected) for ticker in tickers},**result}


def canonical_records(path: Path, entity_types: Mapping[str,str]) -> dict[str,list[dict[str,Any]]]:
    rows=read_observations(path); by_ticker={ticker:[] for ticker in entity_types}
    groups: dict[str,list[dict[str,Any]]]={}
    for row in rows: groups.setdefault(row["identity_key"],[]).append(row)
    active=[]
    for versions in groups.values():
        if len({(v["raw_value"],v["schema_fingerprint"],v["source_record_hash"]) for v in versions}) == 1: active.append(versions[-1])
    for ticker, entity in entity_types.items():
        inputs=[{"provider":r["provider"],"vnstock_version":r["library_version"],"source_method":r["source_method"],"parameters":r["parameters"],"statement_type":r["raw_statement_type"],"raw_item_code":r["raw_item_id"],"raw_label":r.get("raw_label_en") or r.get("raw_label_vi"),"reporting_frequency":r["reporting_frequency"],"period":r["reporting_period"],"statement_scope":r["statement_scope"],"value":r["raw_value"],"currency":r["raw_currency"],"scale":r["raw_scale"],"retrieved_at":r["retrieved_at"],"cumulative_state":r["cumulative_state"],"observation_id":r["observation_id"]} for r in active if r["ticker"]==ticker]
        mapped=canonicalize_items(inputs,entity_type=entity)["records"]
        by_ticker[ticker]=[{"canonical_metric":r["canonical_metric"],"value":r["value"],"source":"financial_observation_store","source_field":r["raw_item_code"],"source_statement":r["statement_type"],"period_identity":{"period":r["period"],"period_type":r["reporting_frequency"]},"statement_scope":r["statement_scope"],"currency":r["currency"],"unit_scale":r["scale"],"derivation_status":r["direct_or_derived"],"quality_state":"available" if r["qualification_state"]=="qualified" else "unknown","reason":";".join(r["warnings"]) or None,"restatement_state":"unknown","observation_ids":[x["observation_id"] for x in inputs if x["raw_item_code"]==r["raw_item_code"] and x["period"]==r["period"] and x["statement_type"]==r["statement_type"]]} for r in mapped]
    return by_ticker
