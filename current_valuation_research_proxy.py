"""Current-only, research-restricted relative valuation over retained proxy outputs."""
from __future__ import annotations
import json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent
INPUT=ROOT/'operations-review/market-wide-current-valuation-research-scaleout-v1/market_wide_current_valuation_artifact.json'
FUNDAMENTAL=ROOT/'operations-review/fundamental-cross-sectional-scoring-and-ranking-v1-20260828/artifact.json'
def execute():
 a=json.loads(INPUT.read_text(encoding='utf8')); allowed=set(json.loads(FUNDAMENTAL.read_text(encoding='utf8'))['records']); rows={}; vals={}
 for t,r in a['records'].items():
  if t not in allowed: continue
  metrics=(r.get('shadow_proxy_valuation') or {}).get('metrics') or {}; usable={k:v for k,v in metrics.items() if v.get('status')=='SHADOW_PROXY_READY' and isinstance(v.get('value'),(int,float)) and v['value']>0}
  for k,v in usable.items(): vals.setdefault(k,[]).append(v['value'])
  rows[t]={'ticker':t,'entity_class':r.get('entity_class'),'price_session':(r.get('shadow_proxy_valuation') or {}).get('price_session'),'share_basis':(r.get('shadow_proxy_valuation') or {}).get('share_basis_type'),'valuation_tier':'VALUATION_RESEARCH_PROXY_RESTRICTED','metrics':metrics,'warnings':['CURRENT_ONLY_NOT_PIT','PROVIDER_ISSUED_SHARE_PROXY_NOT_OUTSTANDING_SHARES'],'relative_value_axis':{'axis_status':'INSUFFICIENT_INPUTS','score':None}}
 for t,row in rows.items():
  scores=[]
  for k,v in row['metrics'].items():
   if k in vals and v.get('status')=='SHADOW_PROXY_READY' and isinstance(v.get('value'),(int,float)) and v['value']>0:
    p=sum(x<=v['value'] for x in vals[k])/len(vals[k]);v['relative_percentile']=p;scores.append(1-p)
   else:v['relative_percentile']=None
  if scores:row['relative_value_axis']={'axis_status':'READY_RESEARCH_ONLY','score':sum(scores)/len(scores),'method':'LOWER_POSITIVE_MULTIPLE_PERCENTILE/v1','warnings':['NOT_CHEAP_EXPENSIVE_OR_TARGET']}
 cov=Counter(row['relative_value_axis']['axis_status'] for row in rows.values()); out={'contract_version':'current_valuation_research_proxy_and_relative_value_axis/v1','denominator':len(rows),'residual':0,'records':rows,'coverage':{'relative_value_axis':dict(cov),'metric_ready':{k:len(v) for k,v in vals.items()}},'authority_boundary':{'current_only':True,'authoritative_financial_counts_before':13,'authoritative_financial_counts_after':13,'valuation_strategy_or_target':False,'pit':False}}
 out['artifact_sha256']=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(',',':')).encode()).hexdigest();return out
