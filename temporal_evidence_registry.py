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
 if not isinstance(record,Mapping) or record.get("record_type") not in {"document","observation","citation","qualification","canonical_derived_lineage","temporal_promotion"}:raise TemporalRegistryError("record_type_invalid")
 if not isinstance(record.get("record_id"),str) or record["record_id"]!=identity({k:v for k,v in record.items() if k!="record_id"}):raise TemporalRegistryError("identity_invalid")
 temporal=record.get("temporal")
 if not isinstance(temporal,Mapping) or set(temporal)!={"observed_at","published_at","effective_at","period_end","calculated_at"}:raise TemporalRegistryError("temporal_fields_missing")
 if record["record_type"] not in {"document","temporal_promotion"} and record.get("ticker") not in TICKERS:raise TemporalRegistryError("ticker_out_of_slice")
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

def _sidecar_temporal_sources(runtime_root:Path)->tuple[dict[str,dict[str,Any]],dict[str,dict[str,Any]]]:
 base=runtime_root/"data"/"official-evidence";manifest=json.loads((base/"manifest.json").read_text(encoding="utf-8"))
 docs={r.get("evidence_id"):r for r in manifest.get("records",[]) if r.get("evidence_id")}
 citations={}
 for name in ("qualification_citations.jsonl","share_basis_citations.jsonl","market_price_citations.jsonl","ebitda_component_citations.jsonl","cash_dividend_citations.jsonl","non_cash_event_citations.jsonl"):
  p=base/name
  if not p.exists():continue
  for line in p.read_text(encoding="utf-8").splitlines():
   if line:
    row=json.loads(line)
    if row.get("citation_id"):citations[row["citation_id"]]=row
 return docs,citations
def _promoted_temporal(base:Mapping[str,Any],doc:Mapping[str,Any]|None,raw:Mapping[str,Any]|None)->tuple[dict[str,Any],dict[str,str]]:
 original=base["temporal"]; raw=raw or {};doc=doc or {};values=dict(original);reasons={}
 support={"published_at":doc.get("publication_date"),"effective_at":raw.get("effective_date") or raw.get("ex_rights_date"),"period_end":raw.get("period_end"),"observed_at":raw.get("observed_at") or raw.get("retrieved_at"),"calculated_at":raw.get("verified_at")}
 for field,value in support.items():
  if values.get(field) is not None and value is not None and values[field]!=value:raise TemporalRegistryError("contradictory_temporal_"+field)
  if values.get(field) is None and value is not None:values[field]=value
  if values.get(field) is None:reasons[field]="unsupported_no_direct_source"
 return values,reasons
def promote_temporal_metadata(records:list[Mapping[str,Any]],runtime_root:Path)->list[dict[str,Any]]:
 docs,citations=_sidecar_temporal_sources(runtime_root);out=[]
 for base in records:
  if base.get("record_type")=="temporal_promotion":continue
  doc=docs.get(base.get("evidence_id"));raw=citations.get(base.get("citation_id"));temporal,reasons=_promoted_temporal(base,doc,raw)
  direct=any(((doc or {}).get("publication_date"),(raw or {}).get("effective_date") or (raw or {}).get("ex_rights_date"),(raw or {}).get("period_end"),(raw or {}).get("observed_at") or (raw or {}).get("retrieved_at"),(raw or {}).get("verified_at")))
  if temporal==base.get("temporal") and not direct:continue
  promoted={"record_type":"temporal_promotion","base_record_id":base["record_id"],"ticker":base.get("ticker"),"period":base.get("period"),"metric":base.get("metric"),"source":base.get("source"),"qualification_status":base.get("qualification_status"),"observation_id":base.get("observation_id"),"citation_id":base.get("citation_id"),"evidence_id":base.get("evidence_id"),"document_hash":base.get("document_hash"),"lineage":base.get("lineage"),"supersedes":base.get("supersedes",[]),"temporal":temporal,"temporal_reasons":reasons};promoted["record_id"]=identity(promoted);out.append(promoted)
 return out
def run_promoted_vertical_slice(runtime_root:Path)->dict[str,Any]:
 records=source_records(runtime_root)
 with tempfile.TemporaryDirectory(prefix="temporal-promotion-") as d:
  store=Path(d)/"shadow.jsonl";before=append(store,records);base=replay(store);promotions=promote_temporal_metadata(base,runtime_root);first=append(store,promotions);second=append(store,promotions);rows=replay(store);again=replay(store)
  if canonical(rows)!=canonical(again):raise TemporalRegistryError("promotion_replay_not_stable")
  fields=("published_at","effective_at","period_end","observed_at","calculated_at")
  coverage=lambda values:{f:sum(r["temporal"].get(f) is not None for r in values) for f in fields}
  return {"base_count":len(base),"promotion_count":len(promotions),"before":coverage(base),"after":coverage([r for r in rows if r.get("record_type")=="temporal_promotion"]),"first":first,"second":second,"replay_hash":hashlib.sha256(canonical(rows)).hexdigest(),"records":rows}

_PARITY_FIELDS=("record_type","ticker","period","metric","source","qualification_status","observation_id","citation_id","evidence_id","document_hash","lineage","supersedes","temporal")
def classify_replay_parity(source:list[Mapping[str,Any]],rows:list[Mapping[str,Any]],docs:Mapping[str,Any],citations:Mapping[str,Any])->dict[str,Any]:
 source_by_id={r["record_id"]:r for r in source};base=[r for r in rows if r.get("record_type")!="temporal_promotion"];base_by_id={r["record_id"]:r for r in base};promotions=[r for r in rows if r.get("record_type")=="temporal_promotion"]
 exact=missing=semantic=unexpected=0
 for record_id,original in source_by_id.items():
  replayed=base_by_id.get(record_id)
  if replayed is None:missing+=1;continue
  if canonical(original)==canonical(replayed):exact+=1;continue
  raise TemporalRegistryError("source_replay_conflict")
 for record_id in base_by_id:
  if record_id not in source_by_id:unexpected+=1
 expected=0
 for overlay in promotions:
  parent=source_by_id.get(overlay.get("base_record_id"))
  if parent is None:unexpected+=1;continue
  for field in _PARITY_FIELDS[1:-1]:
   if overlay.get(field)!=parent.get(field):raise TemporalRegistryError("promotion_lineage_or_reference_mutation")
  temporal,reasons=_promoted_temporal(parent,docs.get(parent.get("evidence_id")),citations.get(parent.get("citation_id")))
  if overlay.get("temporal")!=temporal or overlay.get("temporal_reasons")!=reasons:raise TemporalRegistryError("promotion_temporal_value_mutation")
  expected+=1
 return {"EXACT":exact,"SEMANTICALLY_EQUIVALENT":semantic,"EXPECTED_ENRICHMENT":expected,"MISSING":missing,"CONFLICT":0,"UNEXPECTED_EXTRA":unexpected,"source_counts":{kind:sum(r.get("record_type")==kind for r in source) for kind in sorted({r.get("record_type") for r in source})},"replay_counts":{kind:sum(r.get("record_type")==kind for r in rows) for kind in sorted({r.get("record_type") for r in rows})}}
def run_replay_parity(runtime_root:Path)->dict[str,Any]:
 source=source_records(runtime_root);docs,citations=_sidecar_temporal_sources(runtime_root)
 with tempfile.TemporaryDirectory(prefix="temporal-parity-") as d:
  store=Path(d)/"shadow.jsonl";first=append(store,source);base=replay(store);promotions=promote_temporal_metadata(base,runtime_root);promotion_first=append(store,promotions);second=append(store,source+promotions);rows=replay(store);again=replay(store)
  if canonical(rows)!=canonical(again):raise TemporalRegistryError("parity_replay_not_byte_stable")
  result=classify_replay_parity(source,rows,docs,citations);result.update({"SOURCE_RECORDS":len(source),"REPLAY_RECORDS":len(rows),"first":first,"promotion_first":promotion_first,"second":second,"REPLAY_HASH":hashlib.sha256(canonical(rows)).hexdigest(),"TEMPORAL_NULLS_PRESERVED":all(r["temporal"].get(k) is None for r in rows if r.get("record_type")=="temporal_promotion" for k in r.get("temporal_reasons",{})),"CROSS_TICKER_ISOLATION":all(len(query(rows,ticker=t))==len([r for r in rows if r.get("ticker")==t]) for t in TICKERS)})
  return result
_READ_FIELDS={"ticker","period","metric","source","record_type"}
def _ordered(records:list[Mapping[str,Any]])->list[dict[str,Any]]:
 return sorted((dict(r) for r in records),key=lambda r:(str(r.get("ticker","")),str(r.get("period","")),str(r.get("metric","")),r["record_id"]))
def authority_read(runtime_root:Path,**filters:Any)->list[dict[str,Any]]:
 if set(filters)-_READ_FIELDS:raise TemporalRegistryError("query_unsupported")
 return _ordered([r for r in source_records(runtime_root) if all(r.get(k)==v for k,v in filters.items())])
def compare_dual_read(authority:list[Mapping[str,Any]],registry:list[Mapping[str,Any]],docs:Mapping[str,Any],citations:Mapping[str,Any])->dict[str,Any]:
 base=[r for r in registry if r.get("record_type")!="temporal_promotion"];overlays=[r for r in registry if r.get("record_type")=="temporal_promotion"];authority_by_id={r["record_id"]:r for r in authority};base_by_id={r["record_id"]:r for r in base}
 exact=expected=semantic=authority_only=registry_only=0;diagnostics={"record_count_mismatch":len(authority)!=len(base),"identity_mismatch":False,"source_hash_or_citation_mismatch":False,"lineage_loss":False,"temporal_mutation":False,"ordering_difference":[r["record_id"] for r in authority]!=[r["record_id"] for r in base],"unsupported_query":False}
 for record_id,row in authority_by_id.items():
  candidate=base_by_id.get(record_id)
  if candidate is None:authority_only+=1;continue
  if canonical(row)==canonical(candidate):exact+=1;continue
  semantic+=1;diagnostics["identity_mismatch"]=True
  if row.get("document_hash")!=candidate.get("document_hash") or row.get("citation_id")!=candidate.get("citation_id"):diagnostics["source_hash_or_citation_mismatch"]=True
  if row.get("lineage")!=candidate.get("lineage") or row.get("supersedes")!=candidate.get("supersedes"):diagnostics["lineage_loss"]=True
  if row.get("temporal")!=candidate.get("temporal"):diagnostics["temporal_mutation"]=True
 for record_id in base_by_id:
  if record_id not in authority_by_id:registry_only+=1
 for overlay in overlays:
  parent=authority_by_id.get(overlay.get("base_record_id"))
  if parent is None:registry_only+=1;continue
  temporal,reasons=_promoted_temporal(parent,docs.get(parent.get("evidence_id")),citations.get(parent.get("citation_id")))
  references=("ticker","period","metric","source","qualification_status","observation_id","citation_id","evidence_id","document_hash","lineage","supersedes")
  if any(overlay.get(field)!=parent.get(field) for field in references):semantic+=1;diagnostics["lineage_loss"]=True;continue
  if overlay.get("temporal")!=temporal or overlay.get("temporal_reasons")!=reasons:semantic+=1;diagnostics["temporal_mutation"]=True;continue
  expected+=1
 return {"EXACT":exact,"EXPECTED_ENRICHMENT":expected,"SEMANTIC_MISMATCH":semantic,"AUTHORITY_ONLY":authority_only,"REGISTRY_ONLY":registry_only,"QUERY_UNSUPPORTED":0,"TEMPORAL_NULLS_PRESERVED":all(row["temporal"].get(field) is None for row in overlays for field in row.get("temporal_reasons",{})),"ORDERING_PARITY":not diagnostics["ordering_difference"],"diagnostics":diagnostics}
def shadow_dual_read(runtime_root:Path,**filters:Any)->dict[str,Any]:
 if set(filters)-_READ_FIELDS:return {"returned_from":"authority","authority":[],"registry":[],"EXACT":0,"EXPECTED_ENRICHMENT":0,"SEMANTIC_MISMATCH":0,"AUTHORITY_ONLY":0,"REGISTRY_ONLY":0,"QUERY_UNSUPPORTED":1,"TEMPORAL_NULLS_PRESERVED":True,"ORDERING_PARITY":True,"diagnostics":{"unsupported_query":True}}
 authority=authority_read(runtime_root,**filters);source=source_records(runtime_root);docs,citations=_sidecar_temporal_sources(runtime_root)
 with tempfile.TemporaryDirectory(prefix="temporal-dual-read-") as d:
  store=Path(d)/"shadow.jsonl";append(store,source);base=replay(store);promotions=promote_temporal_metadata(base,runtime_root);append(store,promotions);all_rows=replay(store);ids={r["record_id"] for r in authority};registry=[r for r in all_rows if r.get("record_type")!="temporal_promotion" and r["record_id"] in ids];registry.extend(r for r in all_rows if r.get("record_type")=="temporal_promotion" and r.get("base_record_id") in ids);registry=_ordered(registry);result=compare_dual_read(authority,registry,docs,citations);result.update({"returned_from":"authority","authority":authority,"registry":registry});return result
def run_shadow_dual_read(runtime_root:Path)->dict[str,Any]:
 kinds=("document","observation","citation","qualification","canonical_derived_lineage");specs=[{}]+[{"ticker":t} for t in sorted(TICKERS)]+[{"record_type":kind} for kind in kinds];first=[shadow_dual_read(runtime_root,**spec) for spec in specs];second=[shadow_dual_read(runtime_root,**spec) for spec in specs]
 if canonical(first)!=canonical(second):raise TemporalRegistryError("dual_read_diagnostics_not_deterministic")
 keys=("EXACT","EXPECTED_ENRICHMENT","SEMANTIC_MISMATCH","AUTHORITY_ONLY","REGISTRY_ONLY","QUERY_UNSUPPORTED")
 return {"AUTHORITY_QUERIES":len(specs),"REGISTRY_QUERIES":len(specs),**{key:sum(r[key] for r in first) for key in keys},"TEMPORAL_NULLS_PRESERVED":all(r["TEMPORAL_NULLS_PRESERVED"] for r in first),"FALLBACK_TO_AUTHORITY":all(r["returned_from"]=="authority" and r["authority"]==authority_read(runtime_root,**spec) for r,spec in zip(first,specs)),"ORDERING_PARITY":all(r["ORDERING_PARITY"] for r in first),"DIAGNOSTICS_DETERMINISTIC":True,"REPLAY_HASH":hashlib.sha256(canonical(first)).hexdigest(),"results":first}