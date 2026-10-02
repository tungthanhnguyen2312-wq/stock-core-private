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

def replay_return_semantics(entry: float, exit: float, costs: Mapping[str, Any] | None) -> dict[str, Any]:
 """Existing round-trip bps method; missing costs are unavailable, never zero."""
 from vnm_execution_contract import _costs
 import math
 if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in (entry, exit)):
  return {"gross_return": None, "net_return": None, "reason_codes": ["INVALID_PRICE"]}
 gross = float(exit) / float(entry) - 1
 try:
  c = _costs(costs)
 except ValueError:
  return {"gross_return": gross, "net_return": None, "reason_codes": ["GOVERNED_FEES_TAXES_SLIPPAGE_MODEL_MISSING_OR_INVALID"]}
 net = (1 + gross) * (1 - sum(c.values()) / 10000) ** 2 - 1
 return {"gross_return": gross, "net_return": net, "reason_codes": []}


def run_market_only_gross_replay(*, snapshot: Mapping[str, Any], entry_observation: Mapping[str, Any],
                                 exit_observation: Mapping[str, Any], signal_eligibility: Mapping[str, Any],
                                 entry_eligibility: Mapping[str, Any], exit_eligibility: Mapping[str, Any]) -> dict[str, Any]:
 """Bounded adapter of this existing signal/return engine; no fill or net assumption.

 Eligible market data alone does not fabricate an emitted T0 feature or signal.
 Entry/exit are explicitly bound close-to-close research observations, never orders.
 """
 from market_only_pit_eligibility import CONTRACT_VERSION, EXISTING_VNM_SIGNAL, _price_ready, _volume_ready
 import prospective_market_snapshot_contract as market
 reasons = []
 signal = _signal(snapshot)
 if signal is None: reasons.append("EXISTING_SIGNAL_RULE_NOT_SATISFIED")
 gates = (signal_eligibility, entry_eligibility, exit_eligibility)
 for gate in gates:
  if (gate.get("contract_version") != CONTRACT_VERSION or gate.get("state") != "ELIGIBLE" or
      gate.get("ticker") != "VNM" or gate.get("signal_requirements", {}).get("signal_id") != EXISTING_VNM_SIGNAL):
   reasons.append("MARKET_ONLY_INPUT_GATE_NOT_ELIGIBLE")
  if gate.get("artifact_identity") != market.content_identity(gate,kind="market_only_pit_eligibility")["artifact_identity"]:
   reasons.append("MARKET_INPUT_GATE_IDENTITY_MISMATCH")
 if signal_eligibility.get("knowledge_cutoff") != snapshot.get("knowledge_cutoff"):
  reasons.append("SIGNAL_CUTOFF_NOT_BOUND")
 if snapshot.get("snapshot_id") not in (snapshot.get("market_feature_lineage") or {}).get("signal_snapshot_identities", []):
  reasons.append("T0_MARKET_FEATURE_LINEAGE_MISSING")
 lineage = snapshot.get("market_feature_lineage") or {}
 if (lineage.get("input_snapshot_identities") != signal_eligibility.get("selected_snapshot_identities") or
     lineage.get("knowledge_cutoff") != snapshot.get("knowledge_cutoff")):
  reasons.append("T0_FEATURE_INPUTS_NOT_BOUND")
 try:
  if market._utc(lineage.get("feature_knowledge_available_at"),"feature_known") > market._utc(snapshot.get("knowledge_cutoff"),"cutoff"):
   reasons.append("KNOWLEDGE_CUTOFF_VIOLATION")
 except (AttributeError, TypeError, ValueError): reasons.append("T0_FEATURE_KNOWLEDGE_TIME_MISSING")
 for observation, gate in ((entry_observation,entry_eligibility),(exit_observation,exit_eligibility)):
  if (observation.get("snapshot_identity") not in gate.get("selected_snapshot_identities",[]) or
      observation.get("trading_session") != gate.get("session") or not gate.get("signal_requirements",{}).get("volume_required")):
   reasons.append("OUTCOME_OBSERVATION_NOT_BOUND")
  try:
   if not _price_ready(observation,mode=gate.get("signal_requirements",{}).get("price_mode"),cutoff=market._utc(gate.get("knowledge_cutoff"),"cutoff")) or not _volume_ready(observation):
    reasons.append("OUTCOME_OBSERVATION_NOT_QUALIFIED")
  except (AttributeError, TypeError, ValueError): reasons.append("OUTCOME_OBSERVATION_NOT_QUALIFIED")
 if not (signal_eligibility.get("session", "9999") < entry_eligibility.get("session", "") < exit_eligibility.get("session", "")):
  reasons.append("FUTURE_OUTCOME_SESSION_ORDER_INVALID")
 body = {"contract_version":"market_only_vnm_gross_replay/v1", "signal_rule":EXISTING_VNM_SIGNAL,
         "signal_snapshot_identity":snapshot.get("snapshot_id"), "mode":"GROSS_MARKET_RESEARCH_REPLAY",
         "state":"EXCLUDED" if reasons else "INFRASTRUCTURE_VALIDATION_ONLY", "gross_return":None,
         "net_return":None, "execution_state":"UNAVAILABLE", "trade_count":0, "live_orders":0,
         "outcome_semantics":"EXPLICIT_QUALIFIED_CLOSE_TO_CLOSE_RESEARCH_OBSERVATIONS",
         "reason_codes":sorted(set(reasons)),"authority_effect":"NONE"}
 if not reasons:
  returns = replay_return_semantics(entry_observation["normalized"]["ohlc"]["close"], exit_observation["normalized"]["ohlc"]["close"], None)
  body.update(gross_return=returns["gross_return"], reason_codes=returns["reason_codes"], trade_count=1)
 body["result_hash"] = _hash(body)
 return body


def run_authority_gated_replay(*, snapshot: Mapping[str, Any], raw_sessions: list[Mapping[str, Any]],
                              evidence: Mapping[str, Mapping[str, Any]], costs: Mapping[str, Any] | None = None,
                              max_holding_sessions: int | None = None, leveraged: bool = False, short: bool = False) -> dict[str, Any]:
 """R7 dry-run adapter of this existing isolated VNM engine, not a general backtester.

 Features used for the T0 signal are checked at T0. Each future fill uses its own
 qualification context at its own session close; never copied backward into T0.
 The legacy fixed-holding exit remains explicit, with no inferred stop or policy.
 """
 from raw_pit_authority_matrix import use_case_readiness
 from vnm_execution_contract import _row_reason, _costs
 from field_temporal_contract import stable_id
 ticker = snapshot.get("ticker")
 cutoff = snapshot.get("knowledge_cutoff")
 session = str(cutoff or "")[:10]
 gate = use_case_readiness(use_case="EXECUTION_REPLAY", ticker=ticker, session=session, evidence=evidence,
                          knowledge_cutoff=cutoff, leveraged=leveraged, short=short)
 reasons = list(gate["blocker_reason_codes"])
 if ticker != "VNM": reasons.append("EXISTING_REPLAY_ENGINE_VNM_ONLY")
 if leveraged or short: reasons.append("EXISTING_REPLAY_ENGINE_LONG_UNLEVERED_ONLY")
 if isinstance(max_holding_sessions, bool) or not isinstance(max_holding_sessions, int) or not 1 <= max_holding_sessions <= MAX_HOLDING_SESSIONS:
  reasons.append("EXPLICIT_SUPPORTED_HOLDING_POLICY_REQUIRED")
 signal = _signal(snapshot)
 if signal is None: reasons.append("EXISTING_SIGNAL_RULE_NOT_SATISFIED")
 body = {"contract_version": "authority_gated_vnm_replay/v1", "ticker": ticker, "decision_session": session,
         "knowledge_cutoff": cutoff, "signal_identity": snapshot.get("snapshot_id"), "eligibility": gate,
         "mode": "DRY_RUN_RESEARCH_ONLY", "state": "BLOCKED_BY_EVIDENCE", "trade": None,
         "gross_return": None, "net_return": None, "authority_effect": "NONE", "live_orders": 0}
 rows = sorted(raw_sessions, key=lambda r: str(r.get("trading_date", "")))
 if len({r.get("trading_date") for r in rows}) != len(rows): reasons.append("DUPLICATE_FILL_SESSION")
 if not reasons:
  valid = []
  for row in rows:
   if str(row.get("trading_date", "")) <= session: continue
   if str(row.get("fill_knowledge_cutoff", ""))[:10] != row.get("trading_date"):
    reasons.append("FILL_CUTOFF_MUST_BELONG_TO_FILL_SESSION")
   fill_gate = use_case_readiness(use_case="EXECUTION_REPLAY", ticker=ticker, session=row.get("trading_date"),
              evidence=row.get("authority_evidence") or {}, knowledge_cutoff=row.get("fill_knowledge_cutoff"))
   if fill_gate["state"] != "EXECUTION_USABLE" or _row_reason(row):
    reasons.append("FILL_SESSION_AUTHORITY_OR_RAW_PRICE_UNQUALIFIED:" + str(row.get("trading_date")))
   else:
    band = row['authority_evidence']['PRICE_BAND']
    if not band['lower_price'] <= row['raw_close'] <= band['upper_price']:
     reasons.append("FILL_PRICE_OUTSIDE_QUALIFIED_SESSION_BAND")
    else: valid.append(row)
  if not reasons:
   # Cost model qualification is separate from otherwise valid gross replay.
   net_rows = [evidence.get(f) or {} for f in ("FEES_TAXES", "SLIPPAGE_IMPACT")]
   from raw_pit_authority_matrix import authority_row
   net_qualified = all(authority_row(feature=f, use_case="EXECUTION_REPLAY", ticker=ticker, session=session,
                        evidence=e, knowledge_cutoff=cutoff)["fitness"] == "EXECUTION_USABLE"
                       for f,e in zip(("FEES_TAXES", "SLIPPAGE_IMPACT"), net_rows))
   governed_costs = costs if net_qualified and costs and costs.get("policy_identity") and all(e.get("policy_identity") == costs["policy_identity"] for e in net_rows) else None
   try: _costs(governed_costs)
   except ValueError: governed_costs = None
   entry = resolve_vnm_fill(signal=signal, raw_sessions=valid, costs=governed_costs, gross_research_only=governed_costs is None)
   exit_row, exit_reason = _exit(valid, entry.get("fill_date") or "9999", max_holding_sessions)
   if entry["state"] != "available" or exit_reason:
    reasons.append(entry.get("reason") or exit_reason)
   else:
    returns = replay_return_semantics(entry["raw_fill_price"], exit_row["raw_close"], governed_costs)
    body.update(state="GROSS_RESEARCH_AVAILABLE" if returns["net_return"] is None else "GROSS_AND_NET_RESEARCH_AVAILABLE",
                gross_return=returns["gross_return"], net_return=returns["net_return"],
                trade={"entry": entry, "exit": dict(exit_row), "exit_semantics": "EXISTING_FIXED_QUALIFIED_HOLDING_SESSION_LIMIT",
                       "holding_sessions": max_holding_sessions, "ca_treatment": "EXPLICIT_QUALIFIED_FACTOR_LINEAGE_REQUIRED",
                       "cost_semantics": "EXISTING_MULTIPLICATIVE_ROUND_TRIP_BPS_METHOD"})
    reasons.extend(returns["reason_codes"])
 body["reason_codes"] = sorted(set(reasons))
 return {**body, "replay_identity": "authority_gated_vnm_replay:" + stable_id(body)}
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
  returns=replay_return_semantics(entry["raw_fill_price"],float(exit_row["raw_close"]),costs);gross=returns["gross_return"];net=returns["net_return"]
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
