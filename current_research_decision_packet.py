"""Canonical current-session decision-support packet over retained sibling artifacts."""
from __future__ import annotations
import copy, hashlib, json
from collections import Counter
from typing import Any, Mapping

from current_opportunity_prioritization import content_identity as opportunity_identity
from current_evidence_bound_scenario import content_identity as scenario_identity
from current_research_risk_register import content_identity as risk_identity
from current_market_sector_leadership_context import content_identity as leadership_identity
from current_financial_momentum_context import content_identity as financial_identity
from current_corporate_event_context import content_identity as event_identity
from market_wide_current_valuation_input_scaleout import content_identity as valuation_identity
from market_wide_historical_research_context import content_identity as historical_identity

CONTRACT_VERSION = "current_research_decision_packet/v1"
FORBIDDEN = ("recommendation", "probability", "expected_return", "target_price", "position_size", "sizing")
SPECS = {
 "scenario": ("current_evidence_bound_scenario/v1", scenario_identity, "records", "session"),
 "risk_register": ("current_research_risk_register/v1", risk_identity, "records", None),
 "market_sector": ("current_market_sector_leadership_context/v1", leadership_identity, "ticker_contexts", "session"),
 "financial_momentum": ("current_financial_momentum_context/v1", financial_identity, "records", "session"),
 "corporate_event": ("current_corporate_event_context/v1", event_identity, "records", "research_session"),
 "valuation": ("market_wide_current_valuation/v1", valuation_identity, "records", "valuation_session"),
 "historical": ("market_wide_historical_research_context/v1", historical_identity, "records", "session"),
}

class CurrentResearchDecisionPacketError(ValueError): pass
def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def content_identity(a: Mapping[str, Any]) -> dict[str,str]:
 p=copy.deepcopy(dict(a));p.pop("artifact_sha256",None);p.pop("artifact_identity",None);h=hashlib.sha256(_canon(p)).hexdigest();return {"artifact_sha256":h,"artifact_identity":"current_research_decision_packet:"+h}
def _valid(a, spec):
 contract, identity, records, session = spec
 return isinstance(a, Mapping) and a.get("contract_version")==contract and a.get("artifact_sha256")==identity(a).get("artifact_sha256") and isinstance(a.get(records), Mapping)
def _manifest(name, artifact):
 spec=SPECS[name]
 if artifact is None:return {"component_name":name,"status":"ABSENT","source_artifact_identity":None,"source_as_of":None,"authority_use_status":"OPTIONAL_NOT_SUPPLIED"}
 if not _valid(artifact,spec):return {"component_name":name,"status":"MALFORMED","source_artifact_identity":artifact.get("artifact_identity") if isinstance(artifact,Mapping) else None,"source_as_of":None,"authority_use_status":"FAIL_CLOSED_LOCALLY"}
 return {"component_name":name,"status":"PRESENT","source_artifact_identity":artifact.get("artifact_identity"),"source_content_hash":artifact.get("artifact_sha256"),"source_as_of":artifact.get(spec[3]) if spec[3] else None,"authority_use_status":"PASSTHROUGH_ONLY"}
def _event(row):
 return {k:row.get(k) for k in ("qualified_event_count","planned_unresolved_count","temporal_incomplete_count","data_limited_count","conflicting_count","research_session")} | {"events":[{k:e.get(k) for k in ("event_id","event_status","event_type","known_at","published_at","ex_date","effective_date","execution_date","temporal_completeness","evidence_tier")} for e in row.get("events",[])]}
def _valuation(row):
 return {"valuation_session":(row.get("price_input") or {}).get("session"),"share_basis_status":(row.get("share_basis_input") or {}).get("status"),"metrics":{k:{x:v.get(x) for x in ("status","blocked_reasons","price_session","authority_tier") if x in v} for k,v in sorted((row.get("metrics") or {}).items())},"value_strategy":copy.deepcopy(row.get("value_strategy"))}
def _historical(row, artifact):
 return {"as_of_session":row.get("as_of_session"),"context_status":row.get("context_status"),"structural_state":copy.deepcopy(row.get("structural_state")),"volatility_regime":copy.deepcopy(row.get("volatility_regime")),"momentum":copy.deepcopy(row.get("momentum")),"drawdown":copy.deepcopy(row.get("drawdown")),"authority_boundary":copy.deepcopy(artifact.get("authority_boundary"))}
def _financial(row):
 return {k:copy.deepcopy(row.get(k)) for k in ("as_of_financial_period","financial_momentum_state","coverage_status","evidence_tier","components","blockers","warnings")}
def _scenario(row):
 return {k:copy.deepcopy(row.get(k)) for k in ("scenario_disposition","current_state","bear_case","base_case","bull_case","authority_limitations")}

def build_artifact(*, opportunity: Mapping[str,Any], scenario: Mapping[str,Any]|None=None, risk_register: Mapping[str,Any]|None=None, market_sector: Mapping[str,Any]|None=None, financial_momentum: Mapping[str,Any]|None=None, corporate_event: Mapping[str,Any]|None=None, valuation: Mapping[str,Any]|None=None, historical: Mapping[str,Any]|None=None)->dict[str,Any]:
 if opportunity.get("contract_version")!="current_opportunity_prioritization/v1" or opportunity.get("artifact_sha256")!=opportunity_identity(opportunity).get("artifact_sha256") or not isinstance(opportunity.get("records"),Mapping):raise CurrentResearchDecisionPacketError("CURRENT_DECISION_CONTEXT_INVALID")
 supplied={"scenario":scenario,"risk_register":risk_register,"market_sector":market_sector,"financial_momentum":financial_momentum,"corporate_event":corporate_event,"valuation":valuation,"historical":historical}
 manifest={name:_manifest(name,a) for name,a in supplied.items()}
 valid={name:a for name,a in supplied.items() if manifest[name]["status"]=="PRESENT"}
 records={}
 for ticker, decision in sorted(opportunity["records"].items()):
  unresolved=[name for name,m in manifest.items() if m["status"]!="PRESENT" or ticker not in valid.get(name,{}).get(SPECS[name][2],{})]
  components={}
  if "scenario" in valid and ticker in valid["scenario"]["records"]:components["scenario_context"]=_scenario(valid["scenario"]["records"][ticker])
  if "risk_register" in valid and ticker in valid["risk_register"]["records"]:components["risk_register"]=copy.deepcopy(valid["risk_register"]["records"][ticker])
  if "market_sector" in valid and ticker in valid["market_sector"]["ticker_contexts"]:components["market_sector_context"]={"market":copy.deepcopy(valid["market_sector"].get("market")),"ticker_context":copy.deepcopy(valid["market_sector"]["ticker_contexts"][ticker])}
  if "financial_momentum" in valid and ticker in valid["financial_momentum"]["records"]:components["financial_momentum_context"]=_financial(valid["financial_momentum"]["records"][ticker])
  if "corporate_event" in valid and ticker in valid["corporate_event"]["records"]:components["corporate_event_context"]=_event(valid["corporate_event"]["records"][ticker])
  if "valuation" in valid and ticker in valid["valuation"]["records"]:components["valuation_context"]=_valuation(valid["valuation"]["records"][ticker])
  if "historical" in valid and ticker in valid["historical"]["records"]:components["historical_research_context"]=_historical(valid["historical"]["records"][ticker],valid["historical"])
  current={k:copy.deepcopy(decision.get(k)) for k in ("priority_tier","entry_action","eligible_strategies","lane_priority","tactical_state","scenario_status","blocking_reasons","invalidation_or_context_warnings","source_input_identities")}
  records[ticker]={"ticker":ticker,"packet_status":"COMPLETE_FOR_AVAILABLE_COMPONENTS" if not unresolved else "PARTIAL","current_decision_context":current,"components":components,"unresolved_components":sorted(unresolved),"authority_limitations":[name+"_UNAVAILABLE_OR_MALFORMED" for name in sorted(unresolved)],"warnings":["Component absence does not revise upstream decision state."],"allowed_uses":["AI_RESEARCH_NARRATIVE","HUMAN_REVIEW","AUDIT_REPLAY"],"prohibited_uses":list(FORBIDDEN),"is_actionable":False}
 coverage={"universe_denominator":len(records),"valid_packet_count":sum(not r["unresolved_components"] for r in records.values()),"partial_count":sum(r["packet_status"]=="PARTIAL" for r in records.values()),"malformed_component_count":sum(m["status"]=="MALFORMED" for m in manifest.values()),"component_availability_counts":dict(Counter(m["status"] for m in manifest.values())),"most_common_unresolved_components":dict(Counter(x for r in records.values() for x in r["unresolved_components"])),"packets_with_entry_action_and_partial_context":sum(r["packet_status"]=="PARTIAL" and r["current_decision_context"].get("entry_action") is not None for r in records.values()),"packets_with_scenario_risk_and_blocked_valuation":sum("scenario_context" in r["components"] and "risk_register" in r["components"] and any(x.get("status")=="BLOCKED" for x in r["components"].get("valuation_context",{}).get("metrics",{}).values()) for r in records.values()),"packets_with_no_current_technical_coverage":sum("EXACT_SESSION_TECHNICAL_CONTEXT_UNAVAILABLE" in {x.get("risk_type") for x in r["components"].get("risk_register",{}).get("data_authority_limitations",[])} for r in records.values())}
 artifact={"schema_version":"1.0.0","contract_version":CONTRACT_VERSION,"research_session":opportunity.get("research_session"),"component_manifest":manifest,"source_artifact_identities":{"current_decision_context":opportunity.get("artifact_identity")}|{n:m.get("source_artifact_identity") for n,m in manifest.items()},"records":records,"coverage":coverage,"authority_boundary":{"is_actionable":False,"no_global_authority_score":True,"upstream_decisions_passthrough_only":True,"source_sessions_preserved_independently":True,"no_recommendation_probability_expected_return_target_or_sizing":True,"raw_as_traded":"NOT_PROMOTED","pit":"BLOCKED"},"blocked_outputs":{x:"NOT_EMITTED" for x in FORBIDDEN}}
 artifact.update(content_identity(artifact));return artifact
def replay(a:Mapping[str,Any])->None:
 if a.get("contract_version")!=CONTRACT_VERSION or a.get("artifact_sha256")!=content_identity(a).get("artifact_sha256"):raise CurrentResearchDecisionPacketError("PACKET_IDENTITY_MISMATCH")
 if a.get("coverage",{}).get("universe_denominator")!=len(a.get("records") or {}):raise CurrentResearchDecisionPacketError("PACKET_DENOMINATOR_MISMATCH")
