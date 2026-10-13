"""Vectorized Phase 3 feature store over Phase 2 canonical observations."""
from __future__ import annotations
import json
import pandas as pd
from pathlib import Path
import hashlib

FEATURE_VERSION="1.0.0"
FEATURE_IDS=("market.close","market.return_1d","market.return_5d","market.ma_5","market.ma_20","market.distance_ma_5","market.volatility_5","market.range_pct","market.drawdown_5","market.relative_position_5","volume.raw","volume.avg_5","volume.ratio_5","quality.suspect","quality.exception_count","market.turnover_proxy")
def build_historical(canonical: pd.DataFrame):
    frame=canonical.copy();frame["session"]=pd.to_datetime(frame["session"],errors="coerce",utc=True)
    valid=frame[frame.session.notna() & frame[["open","high","low","close","volume"]].notna().all(axis=1)].copy()
    valid=valid.sort_values(["canonical_instrument_id","session","quality_status","raw_observation_id"],kind="stable")
    valid["duplicate_lineage_count"]=valid.groupby(["canonical_instrument_id","session"])["raw_observation_id"].transform("size")
    valid=valid.drop_duplicates(["canonical_instrument_id","session"],keep="first").copy();g=valid.groupby("canonical_instrument_id",sort=False)
    valid["market.close"]=valid.close;valid["market.return_1d"]=g.close.pct_change(fill_method=None);valid["market.return_5d"]=g.close.pct_change(5,fill_method=None)
    valid["market.ma_5"]=g.close.transform(lambda x:x.rolling(5,min_periods=5).mean());valid["market.ma_20"]=g.close.transform(lambda x:x.rolling(20,min_periods=20).mean());valid["market.distance_ma_5"]=valid.close/valid["market.ma_5"]-1
    valid["market.volatility_5"]=g["market.return_1d"].transform(lambda x:x.rolling(5,min_periods=5).std(ddof=0));valid["market.range_pct"]=(valid.high-valid.low)/valid.close
    hi=g.high.transform(lambda x:x.rolling(5,min_periods=5).max());lo=g.low.transform(lambda x:x.rolling(5,min_periods=5).min());valid["market.drawdown_5"]=valid.close/hi-1;valid["market.relative_position_5"]=(valid.close-lo)/(hi-lo).where((hi-lo)!=0)
    valid["volume.raw"]=valid.volume;valid["volume.avg_5"]=g.volume.transform(lambda x:x.rolling(5,min_periods=5).mean());valid["volume.ratio_5"]=valid.volume/valid["volume.avg_5"];valid["quality.suspect"]=valid.quality_status.eq("SUSPECT");valid["quality.exception_count"]=valid.quality_flags.fillna("[]").map(lambda x:len(json.loads(x)));valid["market.turnover_proxy"]=pd.NA
    for f in FEATURE_IDS:
        status=pd.Series("HISTORICAL_ONLY",index=valid.index);reason=pd.Series("",index=valid.index)
        if f=="market.turnover_proxy":status[:]="BLOCKED";reason[:]="UNKNOWN_VOLUME_BASIS"
        else: status[valid[f].isna()]="BLOCKED";reason[valid[f].isna()]="INSUFFICIENT_HISTORY_OR_MISSING_INPUT"
        status[valid.quality_status.eq("SUSPECT") & status.ne("BLOCKED")]="SUSPECT";valid[f+"__status"]=status;valid[f+"__reason"]=reason
    valid["feature_version"]=FEATURE_VERSION;valid["pit_status"]="HISTORICAL_ONLY";return valid.reset_index(drop=True),frame[frame.session.isna()].reset_index(drop=True)
def snapshot(historical,as_of=None):
    date=pd.to_datetime(as_of,utc=True) if as_of else historical.session.max();return historical[historical.session.le(date)].sort_values(["canonical_instrument_id","session"]).drop_duplicates("canonical_instrument_id",keep="last").reset_index(drop=True)
def eligibility(historical,placeholders):
    return pd.DataFrame([{"feature_id":f,"eligible_value_count":int(historical[f+"__status"].isin(["HISTORICAL_ONLY","SUSPECT"]).sum()),"blocked_count":int(historical[f+"__status"].eq("BLOCKED").sum()),"suspect_or_degraded_count":int(historical[f+"__status"].eq("SUSPECT").sum()),"insufficient_history_count":int(historical[f+"__reason"].str.contains("INSUFFICIENT").sum()),"empty_ohlc_placeholders":len(placeholders),"feature_version":FEATURE_VERSION} for f in FEATURE_IDS])

def reconcile(canonical,historical,placeholders):
    duplicate=int(canonical[canonical.session.notna()].duplicated(["canonical_instrument_id","session"],keep="first").sum())
    return {"input_canonical_rows":len(canonical),"retained_logical_rows":len(historical),"duplicate_collapsed":duplicate,"placeholders":len(placeholders),"other":len(canonical)-len(historical)-duplicate-len(placeholders),"exact_reconciliation":len(canonical)==len(historical)+duplicate+len(placeholders)}
def write_partitioned(historical,root):
    root=Path(root);root.mkdir(parents=True); data=historical.copy();data["year_month"]=data.session.dt.strftime("%Y-%m")
    files=[]
    for key,part in data.groupby("year_month",sort=True):
        path=root/f"session_month={key}"/"part-000.parquet";path.parent.mkdir();part.drop(columns="year_month").sort_values(["canonical_instrument_id","session"]).to_parquet(path,index=False);files.append(str(path))
    return {"version":FEATURE_VERSION,"scheme":"session_month","files":files,"sha256":hashlib.sha256("\n".join(files).encode()).hexdigest()}
def lazy_read(root,instruments=None,start=None,end=None,columns=None):
    paths=sorted(Path(root).glob("session_month=*/part-000.parquet"));frame=pd.concat([pd.read_parquet(p,columns=columns) for p in paths],ignore_index=True)
    if instruments is not None:frame=frame[frame.canonical_instrument_id.isin(instruments)]
    if start is not None:frame=frame[frame.session>=pd.to_datetime(start,utc=True)]
    if end is not None:frame=frame[frame.session<=pd.to_datetime(end,utc=True)]
    return frame
