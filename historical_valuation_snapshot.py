"""Fail-closed historical valuation snapshot pilot; no current-value fallback."""
import hashlib,json
VERSION="1.0.0"
def build_snapshot(x):
 req=("ticker","entity_type","financial_period","publication_cutoff","price_date","price","shares","financial","citations","source_hashes")
 if any(k not in x for k in req):raise ValueError("snapshot_input_missing")
 if x["price_date"]<x["publication_cutoff"]:raise ValueError("price_before_knowledge_cutoff")
 f=x["financial"];m={};cap=x["price"]*x["shares"]
 def put(n,d):m[n]={"state":"available","value":cap/d} if isinstance(d,(int,float)) and d>0 else {"state":"unavailable","reason":"qualified_denominator_missing"}
 put("pe",f.get("net_income"));put("pb",f.get("equity"));put("ps",f.get("sales"))
 if x["entity_type"]=="bank":m["ev_sales"]={"state":"inapplicable","reason":"bank_sector_gate"};m["ev_ebitda"]={"state":"inapplicable","reason":"bank_sector_gate"}
 else:put("ev_sales",f.get("sales"));put("ev_ebitda",f.get("ebitda"))
 r={"version":VERSION,"ticker":x["ticker"],"financial_period":x["financial_period"],"valuation_date":x["price_date"],"knowledge_cutoff":x["publication_cutoff"],"share_basis_identity":x.get("share_basis_identity","period_end_shares_outstanding"),"methods":m,"lineage":{"citations":x["citations"],"source_hashes":x["source_hashes"]},"series_status":"single_date_evidence"};r["snapshot_id"]="hvs-"+hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":")).encode()).hexdigest();return r
def replay(rows):return sorted(rows,key=lambda r:(r["ticker"],r["financial_period"],r["valuation_date"]))