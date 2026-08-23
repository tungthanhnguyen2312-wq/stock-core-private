"""Foreground resumable DNSE instruments reference retention and qualification."""
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import dnse_secrets_env
from dnse_access import CREDENTIAL_ENV_PAIRS,credentials_for_request
from dnse_bulk_market_data import fetch_capability_raw
from market_wide_current_research_universe import build_artifact
SNAPSHOT=ROOT/'operations-review/p3f9b-market-wide-exact-session-scaleout-20260821/p3f9b_mva_exact_session_snapshot.json'
OUT=ROOT/'operations-review/market-wide-current-research-universe-qualification-v1-20260823'
def page(out,index,size):
 p=out/'reference-batches'/f'page-{index:03d}.json'
 if p.exists(): print('REUSED',p);return
 dnse_secrets_env.ensure_credentials_loaded();c=credentials_for_request()
 if not c:raise RuntimeError('DNSE_CREDENTIAL_INJECTION_REQUIRED')
 try:
  r=fetch_capability_raw('instruments',api_key=c[0],api_secret=c[1],query={'page':index,'pageSize':size})
  if not r.get('ok'):raise RuntimeError(r.get('error_code','INSTRUMENTS_FETCH_FAILED'))
  b=r['body'];
  if not isinstance(b.get('data'),list) or not isinstance(b.get('total'),int):raise RuntimeError('INSTRUMENTS_RESPONSE_MALFORMED')
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'page':index,'page_size':size,'total':b['total'],'rows':b['data']},ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8');print(p)
 finally:
  for a,b in CREDENTIAL_ENV_PAIRS:os.environ.pop(a,None);os.environ.pop(b,None)
def consolidate(out):
 pages=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((out/'reference-batches').glob('page-*.json'))];
 if not pages:raise RuntimeError('NO_RETAINED_REFERENCE_BATCHES')
 total=pages[0]['total']; rows=[x for p in pages for x in p['rows']]
 if {p['total'] for p in pages}!={total} or len(rows)!=total:raise RuntimeError(f'INCOMPLETE_REFERENCE:{len(rows)}/{total}')
 snap=json.loads(SNAPSHOT.read_text(encoding='utf-8'));a=build_artifact(canonical_snapshot=snap,instrument_rows=rows);out.mkdir(parents=True,exist_ok=True);(out/'market_wide_current_research_universe_artifact.json').write_text(json.dumps(a,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');print(a['artifact_identity'])
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--out-dir',default=str(OUT));p.add_argument('--page',type=int);p.add_argument('--page-size',type=int,default=100);p.add_argument('--consolidate',action='store_true');a=p.parse_args(argv);out=Path(a.out_dir)
 if a.consolidate:consolidate(out)
 elif a.page is not None:page(out,a.page,a.page_size)
 else:p.error('choose --page or --consolidate')
if __name__=='__main__':main()
