"""Fail-closed provider-segmented OHLCV basis qualification; no database mutation."""
from __future__ import annotations
import hashlib,json,sqlite3
from pathlib import Path
from typing import Any,Mapping
from provider_price_basis_registry import active_verdict,blocks_raw_as_traded,ineligibility_reason
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
  result["providers"][provider]={"rows":coverage[provider],"price_basis":"raw_as_quoted_no_adjustment_applied" if raw else "unknown","price_basis_verified":raw,"volume_basis":"unknown","volume_basis_verified":False,"evidence_citation_ids":sorted(r.get("citation_id") for r in evidence[provider]),"limitations":([] if raw else [ineligibility_reason(provider) or "no qualified provider-specific price evidence"])+["no qualified provider-specific volume-basis evidence"],"empirical_basis":_empirical_basis(provider)}
 return result
# `price_basis` above is the *forward-contract* basis and stays "unknown" until a provider
# is qualified for actionable use. That is a different question from what a provider's
# series has been empirically shown to be, and running the two together is what let an
# undocumented provider read as an unusable one. This sidecar answers the second question
# only; nothing downstream may promote it into the first.
def _empirical_basis(provider:str)->dict[str,Any]:
 verdict=active_verdict(provider)
 return {"price_basis":verdict.get("price_basis","unknown"),"qualification":verdict.get("price_basis_qualification","unknown"),
         "historical_mutability":verdict.get("historical_mutability","unknown"),
         "observed_adjustment_dimensions":list(verdict.get("observed_adjustment_dimensions",[])),
         "provider_methodology":verdict.get("provider_methodology","unknown"),
         "coverage_generalization":verdict.get("coverage_generalization","not_authorized"),
         "volume_unit":verdict.get("volume_unit","unknown"),"trading_value_unit":verdict.get("trading_value_unit","unknown"),
         "volume_market_scope":verdict.get("volume_market_scope","unknown"),
         "raw_as_traded_eligible":verdict.get("raw_as_traded_eligible"),
         "official_exchange_price":False,"liquidity_actionable":False,
         "descriptive_and_technical_use":"provider_scoped_available" if verdict.get("price_basis_qualification")=="empirically_deduced" else "unqualified",
         "evidence":list(verdict.get("evidence",[]))}
def validate_forward(record:Mapping[str,Any])->dict[str,Any]:
 required=("provider","price_basis","price_basis_verified","volume_basis","volume_basis_verified","basis_evidence_id")
 if any(k not in record for k in required):raise OHLCVBasisError("forward_basis_fields_missing")
 if record["provider"] not in PROVIDERS or not record["price_basis_verified"] or not record["volume_basis_verified"]:raise OHLCVBasisError("forward_basis_unqualified")
 if record["price_basis"] not in {"raw_as_quoted_no_adjustment_applied","adjusted"} or record["volume_basis"] not in {"raw_shares_traded","adjusted_volume"}:raise OHLCVBasisError("forward_basis_invalid")
 return dict(record)