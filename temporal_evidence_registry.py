"""Temporary append-only temporal registry over verified HPG/VNM/VCB evidence sidecars."""
from __future__ import annotations
import hashlib,json,tempfile
from pathlib import Path
from typing import Any,Mapping
from evidence_registry import EvidenceRegistry
VERSION="1.0.0"; TICKERS={"HPG":"corporate","VNM":"corporate","VCB":"bank"}
class TemporalRegistryError(ValueError):pass
def canonical(value:Any)->bytes:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def identity(record:Mapping[str,Any])->str:return "temporal-"+hashlib.sha256(canonical(record)).hexdigest()
def _temporal(raw:Mapping[str,Any],doc:Mapping[str,Any]|None)->dict[str,Any]:
 return {"observed_at":raw.get("observed_at"),"published_at":(doc or {}).get("publication_date"),"effective_at":raw.get("effective_at") or raw.get("ex_rights_date"),"period_end":raw.get("period_end"),"calculated_at":raw.get("verified_at")}
def source_records(runtime_root:Path)->list[dict[str,Any]]:
 reg=EvidenceRegistry(runtime_root,entities=TICKERS).load();facts=[f for f in reg.facts if f.get("ticker") in TICKERS and f.get("qualification_status") in {"qualified","available"}]
 used={f.get("evidence_id") for f in facts if f.get("evidence_id")};out=[]
 for evidence_id in sorted(used):
  doc=reg.documents.get(evidence_id)
  if doc and doc.get("_valid"):
   payload={"record_type":"document","evidence_id":evidence_id,"document_hash":doc.get("sha256"),"source":"official_evidence_manifest","temporal":{"observed_at":None,"published_at":doc.get("publication_date"),"effective_at":None,"period_end":None,"calculated_at":None},"supersedes":[]};payload["record_id"]=identity(payload);out.append(payload)
 for fact in sorted(facts,key=lambda x:x["identity"]):
  raw=fact.get("raw") if isinstance(fact.get("raw"),Mapping) else {};doc=reg.documents.get(fact.get("evidence_id"));kind=fact.get("kind")
  category="canonical_derived_lineage" if kind=="derived" else ("qualification" if kind=="qualification" else "citation")
  payload={"record_type":category,"fact_identity":fact["identity"],"ticker":fact.get("ticker"),"period":fact.get("period"),"metric":fact.get("metric"),"source":fact.get("source"),"qualification_status":fact.get("qualification_status"),"observation_id":fact.get("observation_id"),"citation_id":fact.get("citation_id"),"evidence_id":fact.get("evidence_id"),"document_hash":fact.get("document_hash"),"lineage":fact.get("lineage",{}),"supersedes":(fact.get("lineage") or {}).get("supersedes",[]),"temporal":_temporal(raw,doc)};payload["record_id"]=identity(payload);out.append(payload)
  if fact.get("observation_id"):
   obs={"record_type":"observation","observation_id":fact["observation_id"],"ticker":fact.get("ticker"),"period":fact.get("period"),"metric":fact.get("metric"),"source":"financial_observations","citation_id":fact.get("citation_id"),"evidence_id":fact.get("evidence_id"),"document_hash":fact.get("document_hash"),"temporal":_temporal(raw,doc),"supersedes":[]};obs["record_id"]=identity(obs);out.append(obs)
 return out
def validate(record:Mapping[str,Any])->dict[str,Any]:
 if not isinstance(record,Mapping) or record.get("record_type") not in {"document","observation","citation","qualification","canonical_derived_lineage"}:raise TemporalRegistryError("record_type_invalid")
 if not isinstance(record.get("record_id"),str) or record["record_id"]!=identity({k:v for k,v in record.items() if k!="record_id"}):raise TemporalRegistryError("identity_invalid")
 temporal=record.get("temporal")
 if not isinstance(temporal,Mapping) or set(temporal)!={"observed_at","published_at","effective_at","period_end","calculated_at"}:raise TemporalRegistryError("temporal_fields_missing")
 if record["record_type"]!="document" and record.get("ticker") not in TICKERS:raise TemporalRegistryError("ticker_out_of_slice")
 return dict(record)
def append(path:Path,records:list[Mapping[str,Any]])->dict[str,int]:
 existing={r["record_id"]:canonical(r) for r in replay(path)};added=0;idem=0
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("a",encoding="utf-8",newline="\n") as f:
  for raw in records:
   r=validate(raw);data=canonical(r);prior=existing.get(r["record_id"])
   if prior is not None:
    if prior!=data:raise TemporalRegistryError("conflicting_identity_bytes")
    idem+=1;continue
   f.write(data.decode("utf-8")+"\n");existing[r["record_id"]]=data;added+=1
 return {"added":added,"idempotent":idem}
def replay(path:Path)->list[dict[str,Any]]:
 if not path.exists():return []
 rows=[]
 for line in path.read_text(encoding="utf-8").splitlines():
  if not line:continue
  try:r=json.loads(line)
  except json.JSONDecodeError as exc:raise TemporalRegistryError("malformed_store") from exc
  rows.append(validate(r))
 return sorted(rows,key=lambda r:(str(r.get("ticker","")),str(r.get("period","")),str(r.get("metric","")),r["record_id"]))
def query(rows:list[Mapping[str,Any]],**filters:Any)->list[dict[str,Any]]:
 allowed={"ticker","period","metric","source"}
 if set(filters)-allowed:raise TemporalRegistryError("query_field_invalid")
 return [dict(r) for r in rows if all(r.get(k)==v for k,v in filters.items())]
def run_vertical_slice(runtime_root:Path)->dict[str,Any]:
 records=source_records(runtime_root)
 with tempfile.TemporaryDirectory(prefix="temporal-evidence-") as d:
  store=Path(d)/"shadow.jsonl";first=append(store,records);second=append(store,records);rows=replay(store);again=replay(store)
  if canonical(rows)!=canonical(again):raise TemporalRegistryError("replay_not_byte_stable")
  kinds={k:sum(r["record_type"]==k for r in rows) for k in ("document","observation","citation","qualification","canonical_derived_lineage")};missing=sum(any(v is None for v in r["temporal"].values()) for r in rows)
  return {"record_count":len(rows),"counts":kinds,"tickers":sorted({r.get("ticker") for r in rows if r.get("ticker")}),"missing_temporal_metadata":missing,"first":first,"second":second,"replay_hash":hashlib.sha256(canonical(rows)).hexdigest()}
