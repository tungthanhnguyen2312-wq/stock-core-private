"""Fail-closed VNM signal-to-fill execution contract; never a backtest."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import date
from typing import Any, Mapping

VERSION="1.0.0"
COST_MODEL_VERSION="1.0.0"
MAX_SESSION_LAG=5

def _canon(value: Any) -> str: return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
def _hash(value: Any) -> str: return hashlib.sha256(_canon(value).encode()).hexdigest()
def _day(value: Any) -> date:
    if not isinstance(value,str): raise ValueError("date_missing")
    return date.fromisoformat(value[:10])
def _unavailable(signal: Mapping[str,Any], reason: str) -> dict[str,Any]:
    sid=signal.get("snapshot_id") if isinstance(signal.get("snapshot_id"),str) else "unavailable_signal"
    cutoff=signal.get("knowledge_cutoff") if isinstance(signal.get("knowledge_cutoff"),str) else None
    identity={"signal_id":sid,"knowledge_cutoff":cutoff,"reason":reason,"execution_contract_version":VERSION}
    return {"schema_version":VERSION,"state":"unavailable","execution_id":"vnm-exec-"+_hash(identity),"signal_id":sid,"knowledge_cutoff":cutoff,"fill_date":None,"fill_date_identity":None,"price_basis":"raw_historical_only","price_source_lineage":{},"cost_assumptions":{},"reason":reason,"backtest_outputs":[]}
def _costs(costs: Mapping[str,Any]) -> dict[str,float]:
    if not isinstance(costs,Mapping) or costs.get("cost_model_version") != COST_MODEL_VERSION: raise ValueError("unsupported_cost_model")
    result={}
    for name in ("commission_bps","slippage_bps","tax_bps"):
        value=costs.get(name)
        if not isinstance(value,(int,float)) or isinstance(value,bool) or value < 0 or value > 1000: raise ValueError("unsupported_cost_parameter:"+name)
        result[name]=float(value)
    return result
def resolve_vnm_fill(*, signal: Mapping[str,Any], raw_sessions: list[Mapping[str,Any]], costs: Mapping[str,Any], max_session_lag: int=MAX_SESSION_LAG) -> dict[str,Any]:
    """Select the first qualified raw-price session strictly after the signal cutoff."""
    if not isinstance(signal,Mapping) or signal.get("ticker") != "VNM": return _unavailable(signal if isinstance(signal,Mapping) else {},"unsupported_or_missing_signal")
    if signal.get("state") not in {"available","partial"}: return _unavailable(signal,"signal_unavailable")
    try: cutoff=_day(signal.get("knowledge_cutoff")); cost_values=_costs(costs)
    except ValueError as exc: return _unavailable(signal,str(exc))
    if not isinstance(max_session_lag,int) or isinstance(max_session_lag,bool) or not 1 <= max_session_lag <= MAX_SESSION_LAG: return _unavailable(signal,"unsupported_session_lag")
    rows=sorted((row for row in raw_sessions if isinstance(row,Mapping)),key=lambda row:str(row.get("trading_date","")))
    eligible=[row for row in rows if _safe_after(row.get("trading_date"),cutoff)]
    if not eligible: return _unavailable(signal,"no_next_eligible_trading_session")
    if len(eligible)>max_session_lag: eligible=eligible[:max_session_lag]
    for offset,row in enumerate(eligible,1):
        reason=_row_reason(row)
        if reason is None:
            lineage={"price_source_id":row["price_source_id"],"citation_id":row["citation_id"],"source_hash":row["source_hash"],"trading_date":row["trading_date"],"price_field":"raw_close","volume_field":"volume"}
            identity={"signal_id":signal["snapshot_id"],"knowledge_cutoff":signal["knowledge_cutoff"],"fill_date":row["trading_date"],"fill_date_identity":"next_eligible_session_"+str(offset),"price_source_lineage":lineage,"execution_contract_version":VERSION,"cost_model_version":COST_MODEL_VERSION,"costs":cost_values}
            return {"schema_version":VERSION,"state":"available","execution_id":"vnm-exec-"+_hash(identity),"signal_id":signal["snapshot_id"],"knowledge_cutoff":signal["knowledge_cutoff"],"fill_date":row["trading_date"],"fill_date_identity":"next_eligible_session_"+str(offset),"price_basis":"raw_historical_only","raw_fill_price":float(row["raw_close"]),"price_source_lineage":lineage,"cost_assumptions":{"cost_model_version":COST_MODEL_VERSION,**cost_values,"kind":"simulation_assumptions_not_observed_facts"},"reason":None,"backtest_outputs":[]}
    return _unavailable(signal,"no_tradable_session_within_lag")
def _safe_after(value: Any, cutoff: date) -> bool:
    try: return _day(value)>cutoff
    except ValueError: return False
def _row_reason(row: Mapping[str,Any]) -> str|None:
    if row.get("price_basis") != "raw_historical": return "price_basis_not_qualified_raw"
    price=row.get("raw_close"); volume=row.get("volume")
    if not isinstance(price,(int,float)) or isinstance(price,bool) or price<=0: return "raw_price_missing_or_invalid"
    if not isinstance(volume,(int,float)) or isinstance(volume,bool) or volume<=0: return "volume_missing_or_not_tradable"
    if row.get("volume_qualification") != "qualified": return "volume_basis_unqualified"
    if not all(isinstance(row.get(k),str) and row[k] for k in ("price_source_id","citation_id","source_hash")): return "price_lineage_missing"
    return None
def run_frozen_pilot() -> dict[str,Any]:
    signal={"ticker":"VNM","snapshot_id":"vnm-pit-demo","knowledge_cutoff":"2026-06-30T00:00:00Z","state":"partial"}; costs={"cost_model_version":"1.0.0","commission_bps":5,"slippage_bps":10,"tax_bps":0}; rows=[{"trading_date":"2026-06-30","raw_close":80,"volume":10,"price_basis":"raw_historical","volume_qualification":"qualified","price_source_id":"p0","citation_id":"c0","source_hash":"h0"},{"trading_date":"2026-07-01","raw_close":81,"volume":11,"price_basis":"raw_historical","volume_qualification":"qualified","price_source_id":"p1","citation_id":"c1","source_hash":"h1"}]
    first=resolve_vnm_fill(signal=signal,raw_sessions=rows,costs=costs); second=resolve_vnm_fill(signal=signal,raw_sessions=rows,costs=costs)
    if _canon(first)!=_canon(second): raise RuntimeError("non_deterministic")
    return {"signal_id":first["signal_id"],"fill_date":first["fill_date"],"execution_id":first["execution_id"],"state":first["state"],"backtest_outputs_emitted":0}
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--frozen-pilot",action="store_true");args=parser.parse_args()
    if args.frozen_pilot: print(_canon(run_frozen_pilot()))
