"""Temporary append-only registry for existing partial corporate-action observations."""
from __future__ import annotations
import hashlib,json,sqlite3,tempfile
from pathlib import Path
from typing import Any,Mapping
VERSION="1.0.0";TICKERS={"HPG","PAN","VCB","VNM"};FIELDS={"observed_at","published_at","effective_at","record_at","payment_at","issue_at","listing_at"}
class CorporateActionRegistryError(ValueError):pass
def canonical(x:Any)->bytes:return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def identity(x:Mapping[str,Any])->str:return "ca-"+hashlib.sha256(canonical(x)).hexdigest()
def validate(r:Mapping[str,Any])->dict[str,Any]:
 if r.get("ticker") not in TICKERS or not r.get("provider_event_id") or not r.get("source_hash"):raise CorporateActionRegistryError("identity_or_hash_missing")
 if r.get("record_id")!=identity({k:v for k,v in r.items() if k!="record_id"}):raise CorporateActionRegistryError("identity_invalid")
 if set(r.get("temporal",{}))!=FIELDS:raise CorporateActionRegistryError("temporal_fields_invalid")
 ratio=r.get("share_ratio")
 if ratio is not None and (not isinstance(ratio,(int,float)) or ratio<0):raise CorporateActionRegistryError("unsupported_ratio")
 return dict(r)
def append(path:Path,records:list[Mapping[str,Any]])->dict[str,int]:
 seen={r["record_id"]:canonical(r) for r in replay(path)};added=idem=0;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("a",encoding="utf-8",newline="\n") as f:
  for raw in records:
   r=validate(raw);b=canonical(r);old=seen.get(r["record_id"])
   if old is not None:
    if old!=b:raise CorporateActionRegistryError("conflicting_id")
    idem+=1;continue
   f.write(b.decode()+"\n");seen[r["record_id"]]=b;added+=1
 return {"added":added,"idempotent":idem}
def replay(path:Path)->list[dict[str,Any]]:
 if not path.exists():return []
 return sorted([validate(json.loads(x)) for x in path.read_text(encoding="utf-8").splitlines() if x],key=lambda r:(r["ticker"],r["temporal"].get("effective_at") or "",r["provider_event_id"]))
def query(rows:list[Mapping[str,Any]],ticker:str|None=None,action_type:str|None=None,effective_date:str|None=None)->list[dict[str,Any]]:
 return [dict(r) for r in rows if (ticker is None or r["ticker"]==ticker) and (action_type is None or r["action_type"]==action_type) and (effective_date is None or r["temporal"].get("effective_at")==effective_date)]
def promote_official_stock_dividend(provider,official):
 required={"ticker","provider_event_id","ratio","approval_date","record_date","issuance_date","listing_date","completion_date","source_hash","citation_id","citation"}
 if not required.issubset(official) or provider.get("ticker")!=official["ticker"] or provider.get("provider_event_id")!=official["provider_event_id"]:raise CorporateActionRegistryError("official_identity_mismatch")
 if provider.get("exercise_ratio")!=official["ratio"] or provider.get("record_date")!=official["record_date"]:raise CorporateActionRegistryError("official_ratio_or_record_conflict")
 if official.get("lifecycle")!="completed":raise CorporateActionRegistryError("official_completion_missing")
 temporal={"observed_at":official.get("observed_at"),"published_at":official["approval_date"],"effective_at":official["listing_date"],"record_at":official["record_date"],"payment_at":None,"issue_at":official["issuance_date"],"listing_at":official["listing_date"]}
 r={"schema_version":VERSION,"ticker":official["ticker"],"provider":provider.get("provider","VCI"),"provider_event_id":official["provider_event_id"],"action_type":"stock_dividend","event_code":"ISS","cash_amount":None,"share_ratio":official["ratio"],"temporal":temporal,"source_hash":official["source_hash"],"citation_id":official["citation_id"],"citation_reason":"official_execution_evidence","qualification":"qualified","coverage_limitation":provider.get("coverage_status"),"supersedes":official.get("supersedes",[]),"adjustment_provenance":"shadow_only","date_lineage":{k:official[k] for k in ("approval_date","record_date","issuance_date","listing_date","completion_date")},"citation":official["citation"]};r["record_id"]=identity(r);return r
def shadow_share_factor(record):
 r=validate(record)
 if r.get("qualification")!="qualified" or r.get("action_type")!="stock_dividend" or not r.get("share_ratio"):raise CorporateActionRegistryError("shadow_factor_requires_qualified_stock_dividend")
 f={"factor_version":"1.0.0","event_record_id":r["record_id"],"ticker":r["ticker"],"share_quantity_multiplier":1+r["share_ratio"],"theoretical_price_multiplier":1/(1+r["share_ratio"]),"lineage":{"citation_id":r["citation_id"],"source_hash":r["source_hash"],"date_lineage":r["date_lineage"]},"application":"shadow_only"};f["factor_id"]="sf-"+hashlib.sha256(canonical(f)).hexdigest();return f
def source_records(db:Path)->list[dict[str,Any]]:
 c=sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro",uri=True);c.row_factory=sqlite3.Row
 try:rows=c.execute("SELECT r.*,o.raw_payload_hash,o.retrieved_at FROM corporate_event_records r JOIN corporate_event_observations o USING(record_id) WHERE r.ticker IN ('HPG','PAN','VCB','VNM') AND r.category='DIVIDEND' ORDER BY r.ticker,r.provider,r.provider_event_id").fetchall()
 finally:c.close()
 out=[]
 for x in rows:
  d=dict(x);code=d.get("event_code");action="cash_dividend" if code=="DIV" else ("share_issuance" if code=="ISS" else "dividend_other");temporal={"observed_at":d.get("retrieved_at") or d.get("first_observed_at"),"published_at":None,"effective_at":d.get("exright_date"),"record_at":d.get("record_date"),"payment_at":d.get("payout_date"),"issue_at":d.get("issue_date"),"listing_at":d.get("listing_date")};r={"schema_version":VERSION,"ticker":d["ticker"],"provider":d["provider"],"provider_event_id":d["provider_event_id"],"action_type":action,"event_code":code,"cash_amount":d.get("value_per_share") if code=="DIV" else None,"share_ratio":d.get("exercise_ratio") if code=="ISS" else None,"temporal":temporal,"source_hash":d["raw_payload_hash"],"citation_id":None,"citation_reason":"partial_observation_no_qualified_citation","qualification":"partial","coverage_limitation":d.get("coverage_status"),"supersedes":[],"adjustment_provenance":"not_generated"};r["record_id"]=identity(r);out.append(r)
 return out
def run_slice(db:Path)->dict[str,Any]:
 records=source_records(db)
 with tempfile.TemporaryDirectory(prefix="corporate-action-registry-") as d:
  p=Path(d)/"events.jsonl";first=append(p,records);second=append(p,records);rows=replay(p);again=replay(p)
  if canonical(rows)!=canonical(again):raise CorporateActionRegistryError("replay_not_deterministic")
  projection=[{"ticker":r["ticker"],"action_type":r["action_type"],"effective_at":r["temporal"]["effective_at"],"coverage":r["qualification"]} for r in rows]
  return {"events":len(rows),"tickers":sorted({r["ticker"] for r in rows}),"complete":sum(r["qualification"]=="qualified" for r in rows),"partial":sum(r["qualification"]=="partial" for r in rows),"first":first,"second":second,"replay_hash":hashlib.sha256(canonical(rows)).hexdigest(),"projection":projection}