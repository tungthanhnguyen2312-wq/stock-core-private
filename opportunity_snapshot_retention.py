"""Append-only replay store for full VNM point-in-time opportunity snapshots."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from opportunity_snapshot import IDENTITY_VERSION, SCENARIO_CONTRACT_VERSION, VERSION, _canonical
from opportunity_ranking import VERSION as RANKING_VERSION

RETENTION_VERSION="1.0.0"
class RetentionError(ValueError): pass

def _time(value:Any)->datetime:
 if not isinstance(value,str):raise RetentionError("malformed_knowledge_cutoff")
 try: parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
 except ValueError as exc:raise RetentionError("malformed_knowledge_cutoff") from exc
 if parsed.tzinfo is None:raise RetentionError("malformed_knowledge_cutoff")
 return parsed.astimezone(timezone.utc)
def _not_later(value:Any,cutoff:datetime,field:str)->None:
 if value is not None and _time(value)>cutoff:raise RetentionError("future_data_leakage:"+field)
def validate_snapshot(snapshot:Mapping[str,Any])->dict[str,Any]:
 if not isinstance(snapshot,Mapping):raise RetentionError("snapshot_not_mapping")
 if snapshot.get("schema_version")!=VERSION or snapshot.get("ticker")!="VNM":raise RetentionError("legacy_or_incompatible_snapshot")
 if not isinstance(snapshot.get("snapshot_id"),str) or not snapshot["snapshot_id"].startswith("vnm-pit-"):raise RetentionError("snapshot_id_invalid")
 cutoff=_time(snapshot.get("knowledge_cutoff"));identity=snapshot.get("snapshot_identity");vintage=snapshot.get("input_vintage")
 if not isinstance(identity,Mapping) or not isinstance(vintage,Mapping):raise RetentionError("identity_or_vintage_missing")
 if identity.get("identity_version")!=IDENTITY_VERSION or identity.get("ticker")!="VNM" or identity.get("knowledge_cutoff")!=snapshot.get("knowledge_cutoff"):raise RetentionError("snapshot_identity_incompatible")
 if identity.get("calculation_contract_version")!=VERSION or identity.get("ranking_contract_version")!=RANKING_VERSION or identity.get("scenario_contract_version")!=SCENARIO_CONTRACT_VERSION:raise RetentionError("contract_versions_incompatible")
 if not isinstance(vintage.get("identity"),str) or identity.get("input_vintage_identity")!=vintage.get("identity"):raise RetentionError("mixed_vintage_identity")
 for key in ("price_observation_cutoff","financial_statement_publication_cutoff","corporate_action_evidence_cutoff","market_risk_calculation_cutoff"):_not_later(vintage.get(key),cutoff,key)
 lineage=snapshot.get("input_lineage")
 if not isinstance(lineage,list) or not lineage:raise RetentionError("lineage_missing")
 for item in lineage:
  if not isinstance(item,Mapping) or not all(isinstance(item.get(k),str) and item[k] for k in ("lineage_id","source_hash","citation_id")):raise RetentionError("lineage_or_citation_invalid")
  for key in ("observed_date","published_date","effective_date","calculation_date"):_not_later(item.get(key),cutoff,key)
 if not isinstance(snapshot.get("ranking"),Mapping) or not isinstance(snapshot.get("scenarios"),Mapping) or not isinstance(snapshot.get("market_risk"),Mapping):raise RetentionError("payload_missing")
 if snapshot.get("backtest_outputs") not in ([],None):raise RetentionError("backtest_output_not_allowed")
 return dict(snapshot)
def _load(path:Path)->list[dict[str,Any]]:
 if not path.exists():return []
 rows=[]
 for line in path.read_text(encoding="utf-8").splitlines():
  if not line:continue
  try: row=json.loads(line)
  except json.JSONDecodeError as exc:raise RetentionError("retention_record_malformed") from exc
  rows.append(validate_snapshot(row))
 return rows
def append_snapshot(path:Path,snapshot:Mapping[str,Any])->str:
 record=validate_snapshot(snapshot);payload=_canonical(record);existing=_load(path)
 for row in existing:
  if row["snapshot_id"]==record["snapshot_id"]:
   if _canonical(row)==payload:return "idempotent"
   raise RetentionError("duplicate_snapshot_id_conflicting_bytes")
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("a",encoding="utf-8",newline="\n") as out:out.write(payload+"\n")
 return "appended"
def replay_vnm(path:Path)->list[dict[str,Any]]:
 return sorted(_load(path),key=lambda row:(row["knowledge_cutoff"],row["snapshot_id"]))
def historical_reconstruction_pilot()->dict[str,Any]:
 return {"retention_contract_version":RETENTION_VERSION,"status":"unavailable","historical_snapshots_reconstructed":0,"earliest_cutoff":None,"latest_cutoff":None,"reason":"historical_vnm_opportunity_snapshots_not_persisted","backtest_outputs":[]}
if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--historical-pilot",action="store_true");args=parser.parse_args()
 if args.historical_pilot:print(_canonical(historical_reconstruction_pilot()))
