"""Resumable, foreground-only DNSE current-session liquidity scale-out."""
from __future__ import annotations
import argparse, json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import dnse_secrets_env, vn_time
from dnse_access import CREDENTIAL_ENV_PAIRS, credentials_for_request
from dnse_bulk_market_data import fetch_capability_raw
from market_wide_current_liquidity_research import build_artifact, content_identity
DEFAULT_SNAPSHOT=ROOT/"operations-review"/"p3f9b-market-wide-exact-session-scaleout-20260821"/"p3f9b_mva_exact_session_snapshot.json"; DEFAULT_OUT=ROOT/"operations-review"/"market-wide-current-liquidity-research-v1-20260823"
def _norm(x): return {"ok":bool(x.get("ok")),"body":x.get("body"),"disposition":"PROVIDER_REJECTED" if not x.get("ok") else None,"reason":x.get("error_code")}
def _one(t,k,s,day):
    start=datetime.fromisoformat(day).replace(tzinfo=vn_time.VN_TZ); end=start+timedelta(days=1)-timedelta(seconds=1)
    return t,_norm(fetch_capability_raw("trades_latest",api_key=k,api_secret=s,symbol=t,query={})),_norm(fetch_capability_raw("ohlc",api_key=k,api_secret=s,symbol=None,query={"type":"STOCK","symbol":t,"resolution":"1D","from":int(start.timestamp()),"to":int(end.timestamp())}))
def _load(path):
    x=json.loads(Path(path).read_text(encoding="utf-8")); return x,sorted(x["records"])
def _path(out,i): return out/"batches"/f"batch-{i:03d}.json"
def batch(snapshot,out,index,size,session,workers):
    universe,candidates=_load(snapshot); symbols=candidates[index*size:(index+1)*size]; target=_path(out,index)
    if not symbols: raise ValueError("BATCH_INDEX_OUT_OF_RANGE")
    if target.exists():
        old=json.loads(target.read_text(encoding="utf-8"))
        if old["symbols"]==symbols and old["session"]==session: print(f"REUSED {target}"); return
        raise ValueError("BATCH_PATH_CONFLICT")
    dnse_secrets_env.ensure_credentials_loaded(); creds=credentials_for_request()
    if not creds: raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")
    try:
        trades={}; ohlc={}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(_one,t,*creds,session) for t in symbols]
            for future in as_completed(futures):
                t,a,b=future.result(); trades[t]=a; ohlc[t]=b
        target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps({"snapshot_identity":universe.get("snapshot_identity"),"session":session,"symbols":symbols,"trades":trades,"ohlc":ohlc},ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8"); print(target)
    finally:
        for a,b in CREDENTIAL_ENV_PAIRS: os.environ.pop(a,None); os.environ.pop(b,None)
def consolidate(snapshot,out,session):
    universe,candidates=_load(snapshot); seen=[]; trades={}; ohlc={}
    for path in sorted((out/"batches").glob("batch-*.json")):
        x=json.loads(path.read_text(encoding="utf-8"))
        if x.get("snapshot_identity")!=universe.get("snapshot_identity") or x.get("session")!=session: raise ValueError("BATCH_IDENTITY_MISMATCH")
        seen+=x["symbols"]; trades.update(x["trades"]); ohlc.update(x["ohlc"])
    if sorted(seen)!=candidates or len(seen)!=len(set(seen)): raise ValueError(f"INCOMPLETE_BATCH_SET:{len(set(seen))}/{len(candidates)}")
    a=build_artifact(candidates=candidates,trades=trades,ohlc=ohlc,requested_at=f"SESSION_BOUND:{session}"); a["resolved_completed_session"]=session; a["universe"]["source_snapshot_identity"]=universe.get("snapshot_identity")
    # build_artifact() stamps artifact_sha256/artifact_identity BEFORE the two lines above add
    # resolved_completed_session and universe.source_snapshot_identity, so that stamp used to
    # cover a strict subset of the persisted payload. Re-stamp over the complete final dict so
    # the recorded hash actually reproduces from 100% of what gets written to disk -- the same
    # contract every content_identity() sibling (dnse_fhsc_market_composition_scaleout.py,
    # dnse_fhsc_volume_basis.py) already guarantees.
    identity=content_identity(a); a["artifact_sha256"]=identity["artifact_sha256"]; a["artifact_identity"]=identity["artifact_identity"]
    (out/"market_wide_current_liquidity_research_artifact.json").write_text(json.dumps(a,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8"); print(a["artifact_identity"])
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--universe-snapshot",default=str(DEFAULT_SNAPSHOT)); p.add_argument("--out-dir",default=str(DEFAULT_OUT)); p.add_argument("--session",default="2026-08-21"); p.add_argument("--batch-index",type=int); p.add_argument("--batch-size",type=int,default=100); p.add_argument("--workers",type=int,default=8); p.add_argument("--consolidate",action="store_true"); a=p.parse_args(argv); out=Path(a.out_dir)
    if a.consolidate: consolidate(a.universe_snapshot,out,a.session)
    elif a.batch_index is not None: batch(a.universe_snapshot,out,a.batch_index,a.batch_size,a.session,a.workers)
    else: p.error("choose --batch-index or --consolidate")
if __name__=="__main__": main()
