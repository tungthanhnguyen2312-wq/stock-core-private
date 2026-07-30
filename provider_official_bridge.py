"""Deterministic, fail-closed links from retained provider observations to official evidence."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping,Sequence
VERSION="1.0.0"
REQUIRED=("identity","reporting_period","statement_scope","unit","sign","raw_value","raw_item_id","observation_id")
def canonical(value:Any)->str:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
def digest(value:Any)->str:return hashlib.sha256(canonical(value).encode()).hexdigest()
def provider_snapshot(*,provider:str,method:str,version:str,parameters:Mapping[str,Any],retrieved_at:str,raw_payload:Any)->dict[str,Any]:
 if provider not in {"VCI","KBS"} or not method or not version or not retrieved_at:raise ValueError("provider_snapshot_identity_invalid")
 payload_hash=digest(raw_payload)
 identity={"provider":provider,"method":method,"version":version,"parameters":dict(parameters),"retrieved_at":retrieved_at,"raw_payload_sha256":payload_hash}
 return {"snapshot_id":digest(identity),**identity,"raw_payload":raw_payload}
def provider_observation(snapshot:Mapping[str,Any],*,identity:str,period:str,scope:str,unit:str,sign:str,raw_item_id:str,raw_label:str,value:Any)->dict[str,Any]:
 if scope!="consolidated" or sign not in {"positive","negative"} or not raw_item_id or not unit:raise ValueError("provider_observation_metadata_invalid")
 record={"provider":snapshot["provider"],"method":snapshot["method"],"version":snapshot["version"],"parameters":snapshot["parameters"],"retrieved_at":snapshot["retrieved_at"],"raw_payload_sha256":snapshot["raw_payload_sha256"],"identity":identity,"reporting_period":period,"statement_scope":scope,"unit":unit,"sign":sign,"raw_item_id":raw_item_id,"raw_label":raw_label,"raw_value":value}
 record["observation_id"]=digest(record)
 return record
def exact_links(provider_rows:Sequence[Mapping[str,Any]],official_rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
 official={str(x.get("identity")):x for x in official_rows};links=[];rejected=[]
 for row in sorted(provider_rows,key=lambda x:str(x.get("observation_id",""))):
  missing=[key for key in REQUIRED if key not in row]
  target=official.get(str(row.get("identity")))
  if missing:rejected.append({"observation_id":row.get("observation_id"),"reason":"provider_fields_missing","fields":missing});continue
  if target is None:rejected.append({"observation_id":row["observation_id"],"reason":"official_identity_missing"});continue
  fields=[key for key in ("reporting_period","statement_scope","unit","sign","raw_item_id","raw_value") if row.get(key)!=target.get(key)]
  if not target.get("citation_id") or not target.get("document_sha256"):fields.append("official_citation_or_hash")
  if fields:rejected.append({"observation_id":row["observation_id"],"reason":"exact_compatibility_failed","fields":fields});continue
  link={"provider_observation_id":row["observation_id"],"official_citation_id":target["citation_id"],"official_document_sha256":target["document_sha256"],"identity":row["identity"],"match":"exact"};link["link_id"]=digest(link);links.append(link)
 return replay({"version":VERSION,"links":links,"rejected":rejected})
def replay(value:Mapping[str,Any])->dict[str,Any]:
 links=[]
 for link in value.get("links",[]):
  expected=digest({key:link[key] for key in ("provider_observation_id","official_citation_id","official_document_sha256","identity","match")})
  if link.get("match")!="exact" or link.get("link_id")!=expected:raise ValueError("provider_official_link_invalid")
  links.append(dict(link))
 rejected=sorted((dict(x) for x in value.get("rejected",[])),key=lambda x:(str(x.get("observation_id")),str(x.get("reason"))))
 return {"version":VERSION,"links":sorted(links,key=lambda x:x["link_id"]),"rejected":rejected}
def canonical_promotions(links:Sequence[Mapping[str,Any]])->list[dict[str,Any]]:
 return [{"canonical_identity":x["identity"],"provider_observation_id":x["provider_observation_id"],"citation_id":x["official_citation_id"],"document_sha256":x["official_document_sha256"],"qualification":"qualified_exact_provider_official_match"} for x in sorted(links,key=lambda x:(x["identity"],x["link_id"]))]