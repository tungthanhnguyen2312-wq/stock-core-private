"""Isolated deterministic VNM point-in-time shadow backtest; no portfolio or recommendation output."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import date
from typing import Any, Mapping
from vnm_execution_contract import resolve_vnm_fill

VERSION="1.0.0"
SIGNAL_VERSION="1.0.0"
MAX_HOLDING_SESSIONS=3

def _canon(x:Any)->str:return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
def _hash(x:Any)->str:return hashlib.sha256(_canon(x).encode()).hexdigest()
def _day(x:Any)->date:return date.fromisoformat(str(x)[:10])
def _empty(reason:str)->dict[str,Any]:return {"schema_version":VERSION,"state":"unavailable","reason":reason,"signal_rule":"VNM_PIT_AVAILABILITY_TECHNICAL_CONFIRMATION_V1","trades":[],"metrics":{},"result_hash":None}
def _signal(snapshot:Mapping[str,Any])->dict[str,Any]|None:
 dims=(snapshot.get("ranking") or {}).get("dimensions") if isinstance(snapshot.get("ranking"),Mapping) else {}
 scenarios=(snapshot.get("scenarios") or {}).get("records") if isinstance(snapshot.get("scenarios"),Mapping) else {}
 technical=dims.get("technical_current_market_readiness") if isinstance(dims,Mapping) else {}
 bull=scenarios.get("bull") if isinstance(scenarios,Mapping) else {}
 if snapshot.get("ticker")!="VNM" or snapshot.get("state") not in {"available","partial"} or not isinstance(technical,Mapping) or technical.get("state")!="available" or not isinstance(bull,Mapping) or bull.get("state")!="available":return None
 if not isinstance(snapshot.get("snapshot_id"),str) or not isinstance(snapshot.get("knowledge_cutoff"),str):return None
 return {"ticker":"VNM","snapshot_id":snapshot["snapshot_id"],"knowledge_cutoff":snapshot["knowledge_cutoff"],"state":snapshot["state"],"signal_version":SIGNAL_VERSION,"input_vintage":snapshot.get("input_vintage",{}),"input_lineage":snapshot.get("input_lineage",[])}
def _qualified(row:Mapping[str,Any])->bool:return row.get("price_basis")=="raw_historical" and row.get("volume_qualification")=="qualified" and isinstance(row.get("raw_close"),(int,float)) and row["raw_close"]>0 and isinstance(row.get("volume"),(int,float)) and row["volume"]>0 and all(isinstance(row.get(k),str) and row[k] for k in ("price_source_id","citation_id","source_hash"))
def _exit(sessions:list[Mapping[str,Any]],entry_date:str,max_holding:int)->tuple[Mapping[str,Any] | None, str | None]:
 eligible=[r for r in sorted(sessions,key=lambda x:str(x.get("trading_date",""))) if str(r.get("trading_date",""))>entry_date and _qualified(r)]
 if len(eligible)<max_holding:return None,"exit_session_unavailable_within_holding_period"
 return eligible[max_holding-1],None
def _benchmark(rows:list[Mapping[str,Any]],entry:str,exit:str)->tuple[float|None,str|None]:
 by={str(r.get("trading_date")):r for r in rows if isinstance(r,Mapping)};a,b=by.get(entry),by.get(exit)
 if not a or not b:return None,"benchmark_session_missing"
 for r in (a,b):
  if not isinstance(r.get("raw_close"),(int,float)) or r["raw_close"]<=0 or not all(isinstance(r.get(k),str) and r[k] for k in ("price_source_id","citation_id","source_hash")):return None,"benchmark_lineage_or_price_invalid"
 return float(b["raw_close"])/float(a["raw_close"])-1,None
def run_shadow_backtest(*,snapshots:list[Mapping[str,Any]],raw_sessions:list[Mapping[str,Any]],benchmark_sessions:list[Mapping[str,Any]],costs:Mapping[str,Any],max_holding_sessions:int=MAX_HOLDING_SESSIONS)->dict[str,Any]:
 if not isinstance(max_holding_sessions,int) or not 1<=max_holding_sessions<=MAX_HOLDING_SESSIONS:return _empty("unsupported_holding_period")
 trades=[];unavailable=[];last_exit=""
 for snapshot in sorted((s for s in snapshots if isinstance(s,Mapping)),key=lambda s:str(s.get("knowledge_cutoff",""))):
  signal=_signal(snapshot)
  if not signal: unavailable.append({"snapshot_id":snapshot.get("snapshot_id"),"reason":"signal_rule_not_satisfied"});continue
  if str(signal["knowledge_cutoff"])[:10]<=last_exit: unavailable.append({"snapshot_id":signal["snapshot_id"],"reason":"overlapping_signal_after_open_trade"});continue
  entry=resolve_vnm_fill(signal=signal,raw_sessions=raw_sessions,costs=costs)
  if entry.get("state")!="available":unavailable.append({"snapshot_id":signal["snapshot_id"],"reason":entry.get("reason")});continue
  exit_row,reason=_exit(raw_sessions,entry["fill_date"],max_holding_sessions)
  if reason:unavailable.append({"snapshot_id":signal["snapshot_id"],"reason":reason});continue
  bench,reason=_benchmark(benchmark_sessions,entry["fill_date"],exit_row["trading_date"])
  if reason:unavailable.append({"snapshot_id":signal["snapshot_id"],"reason":reason});continue
  total_bps=sum(entry["cost_assumptions"][k] for k in ("commission_bps","slippage_bps","tax_bps"));gross=float(exit_row["raw_close"])/entry["raw_fill_price"]-1;net=(1+gross)*(1-total_bps/10000)**2-1
  trade={"trade_id":"vnm-shadow-"+_hash({"signal":signal["snapshot_id"],"entry":entry["execution_id"],"exit":exit_row["trading_date"],"version":VERSION}),"signal_id":signal["snapshot_id"],"knowledge_cutoff":signal["knowledge_cutoff"],"signal_version":SIGNAL_VERSION,"input_vintage":signal["input_vintage"],"entry":entry,"exit":{"fill_date":exit_row["trading_date"],"raw_fill_price":float(exit_row["raw_close"]),"price_source_lineage":{k:exit_row[k] for k in ("price_source_id","citation_id","source_hash")}},"gross_return":gross,"net_return":net,"benchmark_return":bench,"holding_sessions":max_holding_sessions}
  trades.append(trade);last_exit=exit_row["trading_date"]
 if not trades:return {**_empty("no_qualified_shadow_trades"),"unavailable_signals":unavailable}
 equity=1.0;peak=1.0;drawdown=0.0
 for t in trades: equity*=1+t["net_return"];peak=max(peak,equity);drawdown=min(drawdown,equity/peak-1)
 metrics={"trade_count":len(trades),"gross_return":sum(t["gross_return"] for t in trades),"net_return":equity-1,"benchmark_return":sum(t["benchmark_return"] for t in trades),"max_drawdown":drawdown,"hit_rate":sum(t["net_return"]>0 for t in trades)/len(trades)}
 out={"schema_version":VERSION,"state":"available","signal_rule":"VNM_PIT_AVAILABILITY_TECHNICAL_CONFIRMATION_V1","entry_exit_contract":{"entry":"next qualified raw-price session after snapshot cutoff","exit":"qualified raw-price session at fixed holding-session limit","max_holding_sessions":max_holding_sessions},"trades":trades,"unavailable_signals":unavailable,"metrics":metrics}
 out["result_hash"]=_hash(out);return out
def run_frozen_pilot()->dict[str,Any]:
 snapshot={"ticker":"VNM","snapshot_id":"pit-1","knowledge_cutoff":"2026-06-30T00:00:00Z","state":"partial","input_vintage":{"identity":"v1"},"input_lineage":[{"lineage_id":"x"}],"ranking":{"dimensions":{"technical_current_market_readiness":{"state":"available"}}},"scenarios":{"records":{"bull":{"state":"available"}}}}
 def row(d,p):return {"trading_date":d,"raw_close":p,"volume":10,"price_basis":"raw_historical","volume_qualification":"qualified","price_source_id":"p"+d,"citation_id":"c"+d,"source_hash":"h"+d}
 sessions=[row("2026-06-30",100),row("2026-07-01",101),row("2026-07-02",102),row("2026-07-03",103),row("2026-07-04",104)];bench=[row(d,p) for d,p in [("2026-07-01",200),("2026-07-04",202)]];costs={"cost_model_version":"1.0.0","commission_bps":5,"slippage_bps":5,"tax_bps":0};a=run_shadow_backtest(snapshots=[snapshot],raw_sessions=sessions,benchmark_sessions=bench,costs=costs);b=run_shadow_backtest(snapshots=[snapshot],raw_sessions=sessions,benchmark_sessions=bench,costs=costs)
 if _canon(a)!=_canon(b):raise RuntimeError("non_deterministic")
 return {"state":a["state"],"trade_count":a["metrics"]["trade_count"],"result_hash":a["result_hash"]}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--frozen-pilot",action="store_true");a=p.parse_args()
 if a.frozen_pilot:print(_canon(run_frozen_pilot()))
