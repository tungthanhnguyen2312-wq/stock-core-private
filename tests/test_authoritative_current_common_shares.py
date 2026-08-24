import json
from pathlib import Path
from authoritative_current_common_shares import build_artifact, classify_observation, retain_response

def raw(tmp_path: Path, ticker='AAA', payload=None):
 return retain_response(ticker,status=200,body=json.dumps(payload or {'data':{'outstanding_shares':100,'as_of_date':'2026-08-20'}}).encode(),retrieved_at='2026-08-24T00:00:00Z',output_root=tmp_path)
def test_raw_hash_and_semantic_gate(tmp_path):
 row=raw(tmp_path); assert Path(row['raw_path']).read_bytes(); assert classify_observation(row,target_session='2026-08-21',action_tickers=set())['disposition']=='CONTINUITY_UNPROVEN'
def test_action_stale_and_full_disposition_accounting(tmp_path):
 a=build_artifact(universe=['AAA','BBB'],raw_rows=[raw(tmp_path,'AAA')],target_session='2026-08-21',action_tickers={'AAA'})
 assert a['coverage']['universe_count']==2 and a['coverage']['stale']==1 and a['coverage']['dispositions']['NOT_ATTEMPTED_FOR_JUSTIFIED_SCOPE']==1
 assert a['fitness_for_use']['CURRENT_MARKET_CAP']=='BLOCKED' and a['authority_boundary']['provider_proxy_preserved']
 assert a==build_artifact(universe=['AAA','BBB'],raw_rows=[raw(tmp_path,'AAA')],target_session='2026-08-21',action_tickers={'AAA'})
def test_nonpositive_share_count_fails_closed(tmp_path):
 row=raw(tmp_path,payload={'data':{'outstanding_shares':0,'as_of_date':'2026-08-20'}})
 assert classify_observation(row,target_session='2026-08-21',action_tickers=set())['disposition']=='UNAVAILABLE'
