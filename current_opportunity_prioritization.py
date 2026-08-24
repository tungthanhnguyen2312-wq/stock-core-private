"""Deterministic, lane-preserving current opportunity prioritization."""
from __future__ import annotations
import copy, hashlib, json
from collections import Counter, defaultdict
from typing import Any, Mapping

CONTRACT_VERSION = "current_opportunity_prioritization/v1"
TIERS = ("PRIORITY_NOW", "SETUP_WATCH", "MONITOR", "DATA_LIMITED", "EXCLUDED")
SETUP_STATES = {"UPTREND_CONFIRMED", "BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING"}

def _canon(v: Any) -> bytes: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def content_identity(a: Mapping[str, Any]) -> dict[str, str]:
    p=copy.deepcopy(dict(a));p.pop("artifact_sha256",None);p.pop("artifact_identity",None);d=hashlib.sha256(_canon(p)).hexdigest();return {"artifact_sha256":d,"artifact_identity":"current_opportunity_prioritization:"+d}

def _lane_tier(strategy: str, tactical: Mapping[str,Any], scenario: str, event: Mapping[str,Any]) -> str:
    if strategy == "EVENT_DRIVEN":
        return "PRIORITY_NOW" if scenario in {"SCENARIO_READY","SCENARIO_PARTIAL"} and event.get("current_or_recent_event_count",0) else "SETUP_WATCH"
    if tactical.get("entry_state") in SETUP_STATES:
        return "PRIORITY_NOW" if scenario == "SCENARIO_READY" else "SETUP_WATCH" if scenario == "SCENARIO_PARTIAL" else "MONITOR"
    return "MONITOR"

def _tier(lanes: Mapping[str,str], tactical: Mapping[str,Any], scenario: str) -> tuple[str,list[str],list[str]]:
    reasons=[]; blocks=[]
    if lanes:
        best=min(lanes.values(),key=TIERS.index); reasons += [f"{s}={v}" for s,v in sorted(lanes.items())]
        if scenario == "SCENARIO_INSUFFICIENT_DATA": blocks.append("SCENARIO_INSUFFICIENT_DATA")
        return best,reasons,blocks
    if not (tactical.get("data_quality") or {}).get("technical_eligible") or scenario == "SCENARIO_INSUFFICIENT_DATA":
        return "DATA_LIMITED",reasons,["CURRENT_TECHNICAL_OR_SCENARIO_EVIDENCE_LIMITED"]
    return "MONITOR",reasons,["NO_EXISTING_STRATEGY_ELIGIBILITY"]

def build(*, official_universe: Mapping[str,Any], screening: Mapping[str,Any], tactical: Mapping[str,Any], strategy: Mapping[str,Any], scenario: Mapping[str,Any], fundamental: Mapping[str,Any], peer: Mapping[str,Any], event_context: Mapping[str,Any], descriptive: Mapping[str,Any]) -> dict[str,Any]:
    official={t:r for t,r in official_universe["records"].items() if r.get("stocklookup_candidate") and r.get("current_universe_status") in {"OFFICIAL_CURRENT_EXCHANGE_SECURITY","OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"}}
    if len(official)!=1507: raise ValueError("CURRENT_OFFICIAL_UNIVERSE_1507_REQUIRED")
    inputs={"official_universe":official_universe["artifact_identity"],"screening":screening["artifact_identity"],"tactical":tactical["artifact_identity"],"strategy":strategy["artifact_identity"],"scenario":scenario["artifact_identity"],"fundamental":fundamental["artifact_identity"],"peer":peer["artifact_identity"],"event_context":event_context["artifact_identity"],"descriptive":descriptive["artifact_identity"]}
    records={}; lane=defaultdict(Counter)
    for ticker in sorted(official):
        ta=tactical["records"][ticker]; st=strategy["records"][ticker]; sc=scenario["records"][ticker]; ev=event_context.get("records",{}).get(ticker,{})
        eligible=list(st.get("eligible_strategy_ids") or []); lanes={name:_lane_tier(name,ta,sc.get("scenario_disposition"),ev) for name in eligible}; priority,reasons,blocks=_tier(lanes,ta,sc.get("scenario_disposition"))
        for name,value in lanes.items(): lane[name][value]+=1
        record={"ticker":ticker,"official_current_universe_status":official[ticker]["current_universe_status"],"eligible_strategies":eligible,"lane_priority":lanes,"tactical_state":ta.get("entry_state"),"entry_action":ta.get("entry_action"),"scenario_status":sc.get("scenario_disposition"),"fundamental_context_status":(fundamental["records"].get(ticker) or {}).get("authority_tier","UNAVAILABLE"),"peer_context_status":((peer["records"].get(ticker) or {}).get("technical_peer_context") or {}).get("status","UNAVAILABLE"),"event_context_status":"AVAILABLE" if ev.get("events") else "UNAVAILABLE","liquidity_context_status":(ta.get("data_quality") or {}).get("liquidity_status","UNAVAILABLE"),"data_quality_status":(ta.get("data_quality") or {}).get("confidence","INSUFFICIENT"),"priority_tier":priority,"priority_reasons":reasons,"blocking_reasons":blocks,"invalidation_or_context_warnings":list(ta.get("data_quality",{}).get("warnings") or []),"source_input_identities":inputs,"is_actionable":False,"position_sizing_status":ta.get("position_sizing_status","NOT_EVALUATED"),"is_full_position_ready":ta.get("is_full_position_ready",False)}
        record["content_identity"]="current_opportunity_record:"+hashlib.sha256(_canon(record)).hexdigest();records[ticker]=record
    counts=Counter(r["priority_tier"] for r in records.values())
    artifact={"schema_version":"1.0.0","contract_version":CONTRACT_VERSION,"research_session":descriptive["session"],"source_artifact_identities":inputs,"records":records,"coverage":{"current_official_universe":len(records),"screening_ready":sum(screening["records"][t].get("market_relative_comparison",{}).get("status")=="AVAILABLE" for t in records),"tactical_classified":sum(tactical["records"][t].get("entry_state") is not None for t in records),"any_strategy_eligible":sum(bool(strategy["records"][t].get("eligible_strategy_ids")) for t in records),"scenario_ready":sum(scenario["records"][t].get("scenario_disposition")=="SCENARIO_READY" for t in records),"scenario_partial":sum(scenario["records"][t].get("scenario_disposition")=="SCENARIO_PARTIAL" for t in records),"scenario_insufficient":sum(scenario["records"][t].get("scenario_disposition")=="SCENARIO_INSUFFICIENT_DATA" for t in records),**{tier:counts[tier] for tier in TIERS}},"lane_coverage":{name:{tier:lane[name][tier] for tier in TIERS}|{"eligible":sum(lane[name].values()),"representative_candidates":[t for t,r in records.items() if name in r["lane_priority"] and r["lane_priority"][name] in {"PRIORITY_NOW","SETUP_WATCH"}][:10]} for name in ("TREND_MOMENTUM","BREAKOUT","EARLY_REVERSAL","BASE_ACCUMULATION","FUNDAMENTAL_IMPROVEMENT","EVENT_DRIVEN","VALUE")},"authority_boundary":"LEXICOGRAPHIC_LANE_PRIORITY_ONLY_NO_GLOBAL_SCORE_NO_RECOMMENDATION_NO_SIZING_EXECUTION_OR_VALUE_PROMOTION","prospective_freeze_contract":{"compatible":True,"rule":"freeze this additive current-session artifact on a future session; prior snapshots remain immutable"}}
    artifact.update(content_identity(artifact));return artifact

def replay(a:Mapping[str,Any])->None:
    if content_identity(a)["artifact_sha256"]!=a.get("artifact_sha256"):raise ValueError("IDENTITY_MISMATCH")
    if len(a.get("records",{}))!=1507:raise ValueError("DENOMINATOR_MISMATCH")
