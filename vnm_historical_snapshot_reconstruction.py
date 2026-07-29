"""Reconstruct complete VNM snapshots only from contract-qualified historical input bundles."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any,Mapping
from opportunity_ranking import evaluate_opportunity
from scenario_analysis import evaluate_scenario_analysis
from opportunity_snapshot import build_snapshot
from opportunity_snapshot_retention import RetentionError,append_snapshot,replay_vnm
from vnm_shadow_backtest import run_shadow_backtest

VERSION="1.0.0"
class ReconstructionError(ValueError):pass
def reconstruct_snapshot(record:Mapping[str,Any],retention_path:Path)->dict[str,Any]:
 if not isinstance(record,Mapping) or record.get("ticker")!="VNM":raise ReconstructionError("vnm_record_required")
 metadata=record.get("metadata");entry=record.get("opportunity_entry");scenario_input=record.get("scenario_input");lineage=record.get("input_lineage")
 if not all(isinstance(x,Mapping) for x in (metadata,entry,scenario_input)) or not isinstance(lineage,list):raise ReconstructionError("historical_input_bundle_incomplete")
 opportunity=evaluate_opportunity(entry,ticker="VNM",entity_type=str(record.get("entity_type") or "corporate"))
 scenario_source=dict(scenario_input);scenario_source["opportunity"]=opportunity
 scenario=evaluate_scenario_analysis(scenario_source,metadata.get("knowledge_cutoff"))
 snapshot=build_snapshot(ticker="VNM",opportunity=opportunity,scenario=scenario,market_risk=record.get("market_risk"),metadata=metadata,input_lineage=lineage)
 if snapshot.get("state")=="unavailable":return {"state":"unavailable","reason":(snapshot.get("gate_failures") or ["snapshot_unavailable"])[0],"snapshot":snapshot}
 return {"state":"available","retention_action":append_snapshot(retention_path,snapshot),"snapshot":snapshot}
def reconstruct_and_replay(records:list[Mapping[str,Any]],retention_path:Path,*,raw_sessions:list[Mapping[str,Any]]|None=None,benchmark_sessions:list[Mapping[str,Any]]|None=None,costs:Mapping[str,Any]|None=None)->dict[str,Any]:
 rebuilt=[];unavailable=[]
 for record in sorted(records,key=lambda x:str((x.get("metadata") or {}).get("knowledge_cutoff",""))):
  try: result=reconstruct_snapshot(record,retention_path)
  except (ReconstructionError,RetentionError) as exc:unavailable.append({"reason":str(exc)});continue
  (rebuilt if result["state"]=="available" else unavailable).append(result)
 replay=replay_vnm(retention_path)
 shadow=None
 if replay and raw_sessions is not None and benchmark_sessions is not None and costs is not None:shadow=run_shadow_backtest(snapshots=replay,raw_sessions=raw_sessions,benchmark_sessions=benchmark_sessions,costs=costs)
 return {"schema_version":VERSION,"snapshots_reconstructed":len(rebuilt),"snapshots_persisted":len(replay),"replay":replay,"unavailable":unavailable,"shadow":shadow}
def historical_pilot()->dict[str,Any]:
 return {"schema_version":VERSION,"status":"unavailable","reconstructable_cutoffs":[],"snapshots_reconstructed":0,"reason":"historical_vnm_qualified_input_bundles_not_persisted","backtest_outputs":[]}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--historical-pilot",action="store_true");a=p.parse_args()
 if a.historical_pilot:print(json.dumps(historical_pilot(),sort_keys=True,separators=(",",":")))
