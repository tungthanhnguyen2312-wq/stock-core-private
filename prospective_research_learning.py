"""Immutable prospective research snapshots and later exact-session attribution.

This is shadow prospective learning, never historical PIT backtesting.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any,Mapping
def _canon(x:Any):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def _hash(x:Any):return hashlib.sha256(_canon(x).encode()).hexdigest()
def freeze(product:Mapping[str,Any], analyst:Mapping[str,Any])->dict[str,Any]:
 records={x['ticker']:x for x in product['stock_research']}; briefs={x['ticker']:x for x in analyst['stock_briefs']}; frozen=[]
 for ticker in sorted(records):
  r=records[ticker];f=r['ai_ready_brief']['facts'];frozen.append({'ticker':ticker,'attention_descriptors':r['research_summary']['attention_descriptors'],'queue_member':any(x['ticker']==ticker for x in analyst['research_queue']),'market_technical_state':{'trend_state':r['research_summary']['trend_state'],'momentum_20d':f['momentum_20d'],'volatility_20d':f['volatility_20d'],'relative_volume_provider_scoped':f['relative_volume_provider_scoped']},'fundamental_authority':r['research_summary']['fundamental_authority'],'warnings':r['warnings'],'ai_brief_hash':_hash(briefs[ticker]) if ticker in briefs else None})
 a={'schema_version':'1.0.0','contract_version':'prospective_research_learning/v1','authority':'PROSPECTIVE_RESEARCH_LEARNING_NOT_HISTORICAL_PIT_BACKTEST','research_session':product['daily_market_research']['session'],'source_artifact_identities':{'daily_product':product['artifact_identity'],'analyst':analyst['artifact_identity']},'frozen_records':frozen,'cohort_count':len(frozen),'queue_count':sum(x['queue_member'] for x in frozen),'future_outcomes':'PENDING_FUTURE_OBSERVATION'};a['snapshot_id']='prospective_research_snapshot:'+_hash(a);return a
def write_immutable(path:Path,snapshot:Mapping[str,Any])->None:
 payload=_canon(snapshot)+'\n'
 if path.exists() and path.read_text(encoding='utf-8')!=payload:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_CONFLICT')
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(payload,encoding='utf-8')
def attribute(snapshot:Mapping[str,Any],later:Mapping[str,Any]|None=None)->dict[str,Any]:
 # No row from a later session is consulted unless it is strictly later than the frozen session.
 if not later or str(later.get('session',''))<=str(snapshot['research_session']):return {'snapshot_id':snapshot['snapshot_id'],'outcome_status':'PENDING_FUTURE_OBSERVATION','eligible_count':len(snapshot['frozen_records']),'attribution_groups':[]}
 return {'snapshot_id':snapshot['snapshot_id'],'outcome_status':'UNAVAILABLE','eligible_count':len(snapshot['frozen_records']),'attribution_groups':[]}

def context_extension_dimensions(snapshot:Mapping[str,Any], extension:Mapping[str,Any])->dict[str,Any]:
 """Prepare frozen grouping dimensions for a later strict-future attribution run."""
 if extension.get('original_snapshot_identity') != snapshot.get('snapshot_id') or extension.get('research_session') != snapshot.get('research_session'):
  raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_SNAPSHOT_MISMATCH')
 if extension.get('seal',{}).get('future_outcomes') != 'PENDING_FUTURE_OBSERVATION':raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_NOT_PRE_OUTCOME')
 frozen={row['ticker'] for row in snapshot['frozen_records']}; rows={row['ticker']:row for row in extension.get('records',[])}
 if frozen != set(rows):raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_COHORT_MISMATCH')
 if any(row.get('research_session') != snapshot.get('research_session') for row in rows.values()):raise ValueError('PROSPECTIVE_CONTEXT_EXTENSION_SESSION_MISMATCH')
 return {'snapshot_id':snapshot['snapshot_id'],'extension_content_identity':extension['extension_content_identity'],'research_session':snapshot['research_session'],'outcome_status':'PENDING_FUTURE_OBSERVATION','dimensions':[{'ticker':ticker,'cohort_keys':rows[ticker]['prospective_cohort_keys'],'setup_identity':rows[ticker]['setup']['source_identity'],'market_context_reference':rows[ticker]['market_context_reference']} for ticker in sorted(rows)]}
