"""Fail-closed provider-segmented OHLCV basis qualification; no database mutation."""
from __future__ import annotations
import hashlib,json,sqlite3
from pathlib import Path
from typing import Any,Mapping
from provider_price_basis_registry import blocks_raw_as_traded,ineligibility_reason
VERSION="1.0.0"; PROVIDERS=("VCI","KBS")
class OHLCVBasisError(ValueError):pass
def _hash(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def _citations(path:Path)->list[dict[str,Any]]:
 return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
def _provider_evidence(provider:str,rows:list[Mapping[str,Any]],db:Path)->list[dict[str,Any]]:
 conn=sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True);out=[]
 try:
  for row in rows:
   if row.get("provider")!=provider or row.get("source_table")!="ohlcv" or row.get("price_field")!="close":continue
   found=conn.execute("SELECT close,source FROM ohlcv WHERE ticker=? AND date=?",(row.get("ticker"),row.get("trading_date"))).fetchone()
   if found and found[1]==provider and float(found[0])==float(row.get("value")):out.append(row)
 finally:conn.close()
 return out
def qualify(db_path:Path,citation_path:Path)->dict[str,Any]:
 db_path,citation_path=db_path.resolve(),citation_path.resolve();rows=_citations(citation_path);conn=sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro",uri=True)
 try:coverage={p:conn.execute("SELECT COUNT(*) FROM ohlcv WHERE source=?",(p,)).fetchone()[0] for p in PROVIDERS}
 finally:conn.close()
 evidence={p:_provider_evidence(p,rows,db_path) for p in PROVIDERS};result={"schema_version":VERSION,"source_database_hash":_hash(db_path),"citation_source_hash":_hash(citation_path),"providers":{},"historical_rows_classifiable":False,"forward_contract":{"requires":["provider","price_basis","price_basis_verified","volume_basis","volume_basis_verified","basis_evidence_id"],"rejects":["mixed_raw_adjusted","unknown_basis","missing_evidence"]}}
 for provider in PROVIDERS:
  statuses={r.get("adjustment_status") for r in evidence[provider]}
  if len(statuses)>1:raise OHLCVBasisError(f"conflicting_price_basis_evidence:{provider}")
  # Citation agreement is about what the citations say; eligibility is about what the
  # provider's series is. Both must hold, and only the second one can rule out a rewrite.
  raw=bool(statuses=={"raw_as_quoted_no_adjustment_applied"} and len({r.get("ticker") for r in evidence[provider]})>=2 and not blocks_raw_as_traded(provider))
  result["providers"][provider]={"rows":coverage[provider],"price_basis":"raw_as_quoted_no_adjustment_applied" if raw else "unknown","price_basis_verified":raw,"volume_basis":"unknown","volume_basis_verified":False,"evidence_citation_ids":sorted(r.get("citation_id") for r in evidence[provider]),"limitations":([] if raw else [ineligibility_reason(provider) or "no qualified provider-specific price evidence"])+["no qualified provider-specific volume-basis evidence"]}
 return result
def validate_forward(record:Mapping[str,Any])->dict[str,Any]:
 required=("provider","price_basis","price_basis_verified","volume_basis","volume_basis_verified","basis_evidence_id")
 if any(k not in record for k in required):raise OHLCVBasisError("forward_basis_fields_missing")
 if record["provider"] not in PROVIDERS or not record["price_basis_verified"] or not record["volume_basis_verified"]:raise OHLCVBasisError("forward_basis_unqualified")
 if record["price_basis"] not in {"raw_as_quoted_no_adjustment_applied","adjusted"} or record["volume_basis"] not in {"raw_shares_traded","adjusted_volume"}:raise OHLCVBasisError("forward_basis_invalid")
 return dict(record)