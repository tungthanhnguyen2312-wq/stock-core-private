import pandas as pd
from market_feature_store_v1 import build_historical,snapshot
def test_vectorized_duplicates_asof_and_insufficient_history():
 rows=[]
 for s in ('A','B'):
  for d in range(6):rows.append({'canonical_instrument_id':'DNSE:'+s,'session':f'2026-01-{d+1:02d}','open':10+d,'high':11+d,'low':9+d,'close':10+d,'volume':100+d,'quality_status':'CANONICAL','quality_flags':'[]','raw_observation_id':f'{s}{d}'})
 rows.append({**rows[0],'raw_observation_id':'duplicate'});h,e=build_historical(pd.DataFrame(rows));assert len(h)==12 and h['market.ma_20__status'].eq('BLOCKED').all() and e.empty and len(snapshot(h,'2026-01-03'))==2 and h.duplicate_lineage_count.max()==2
