from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from authoritative_current_common_shares import build_artifact, fetch_and_retain

def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument('--session',default='2026-08-21'); p.add_argument('--output-root',type=Path,default=ROOT/'operations-review'/'authoritative-current-common-shares-qualification-and-scaleout-v1-20260824'); a=p.parse_args()
 descriptive=json.loads((ROOT/'operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json').read_text(encoding='utf-8'))
 universe=sorted(descriptive['records']); pilot=['HPG','VCB','SSI','VNM','FPT','PAN']
 corporate=json.loads((ROOT/'operations-review/market-wide-current-corporate-intelligence-v1-20260824/market_wide_current_corporate_intelligence_artifact.json').read_text(encoding='utf-8'))
 action_tickers={e['ticker'] for e in corporate.get('events',[]) if e.get('event_type') in {'BONUS_OR_STOCK_DIVIDEND','CORPORATE_ACTION'}}
 raw=[fetch_and_retain(t,a.output_root) for t in pilot]
 artifact=build_artifact(universe=universe,raw_rows=raw,target_session=a.session,action_tickers=action_tickers)
 path=a.output_root/'authoritative_current_common_shares_qualification_artifact.json'; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(artifact,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(artifact['artifact_identity']); print(json.dumps(artifact['coverage'],sort_keys=True))
if __name__=='__main__': main()
