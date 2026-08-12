from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from market_feature_store_v1 import FEATURE_IDS,build_historical,eligibility,snapshot,reconcile,write_partitioned,lazy_read
p=argparse.ArgumentParser();p.add_argument('--canonical-root',required=True);p.add_argument('--output-root',required=True);p.add_argument('--as-of');a=p.parse_args();out=Path(a.output_root)
if out.exists():p.error('--output-root must not already exist')
raw=pd.read_parquet(Path(a.canonical_root)/'canonical_daily_market.parquet');hist,empty=build_historical(raw);snap=snapshot(hist,a.as_of);elig=eligibility(hist,empty);out.mkdir(parents=True);manifest=write_partitioned(hist,out/'historical_partitioned');snap.to_parquet(out/'snapshot_matrix.parquet',index=False);elig.to_parquet(out/'feature_eligibility.parquet',index=False)
readback=lazy_read(out/'historical_partitioned');missing=set(raw.canonical_instrument_id)-set(snap.canonical_instrument_id);report={'input_rows':len(raw),'historical_rows':len(hist),'snapshot_rows':len(snap),'feature_ids':FEATURE_IDS,'as_of':str(snap.session.max()),'row_reconciliation':reconcile(raw,hist,empty),'snapshot_reconciliation':{'canonical_symbols':int(raw.canonical_instrument_id.nunique()),'snapshot_rows':len(snap),'missing':len(missing),'categories':{'no_valid_feature_bearing_row':len(missing)},'exact_reconciliation':len(missing)==len(raw.canonical_instrument_id.unique())-len(snap)},'storage_manifest':manifest,'lazy_readback_rows':len(readback),'eligibility':elig.to_dict('records')};(out/'coverage_report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(report))
