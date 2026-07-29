"""Fixed-cutoff, axis-preserving HPG/VNM/VCB opportunity integration; no recommendations."""
import hashlib,json
AXES=("quality","valuation","technical","relative_strength","catalyst","downside","data_confidence")
def build_snapshot(inputs,cutoff):
 out=[]
 for ticker in ("HPG","VNM","VCB"):
  x=inputs.get(ticker,{})
  if x.get("cutoff")!=cutoff: out.append({"ticker":ticker,"state":"unavailable","missing_inputs":["cutoff_qualified_inputs"]});continue
  axes={a:x.get("axes",{}).get(a,{"state":"unavailable"}) for a in AXES}
  if ticker=="VCB":
   for k in ("ev_ebitda","fcff","net_net","corporate_debt"):axes["valuation"].pop(k,None) if isinstance(axes["valuation"],dict) else None
  out.append({"ticker":ticker,"state":"available","cutoff":cutoff,"axes":axes,"scenarios":x.get("scenarios",{}),"invalidation":x.get("invalidation"),"missing_inputs":x.get("missing_inputs",[])})
 comparable=[r for r in out if r["state"]=="available" and all(r["axes"][a].get("state")=="available" for a in ("quality","valuation","technical","relative_strength"))]
 return {"cutoff":cutoff,"tickers":out,"comparability":"comparable" if len(comparable)==3 else "partial_comparability","ordering":[r["ticker"] for r in sorted(comparable,key=lambda r:r["ticker"])],"recommendations_emitted":0}
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()