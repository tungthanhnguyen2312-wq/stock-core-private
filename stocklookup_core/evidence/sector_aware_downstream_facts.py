"""Stable export of Phase 7D official-document downstream facts."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
VERSION='1.0.0'; SECTION='sector_aware_downstream_facts'; SOURCE='official_document_observation'
def _hash(v:Any)->str:return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _fact(ticker:str,identity:str,row:Mapping[str,Any])->dict[str,Any]:
 lineage=list(row.get('input_lineage') or []); available=row.get('state')=='available'; fact={'ticker':ticker,'fact_identity':identity,'status':row.get('state'),'formula_applicability_version':row.get('formula_version'),'missing_input_or_inapplicability_reason':list(row.get('missing_inputs') or [])+list(row.get('warnings') or [])}
 if available:
  if len(lineage)!=1 or lineage[0].get('source_type')!=SOURCE:raise ValueError('official_fact_lineage_invalid')
  x=lineage[0];fact.update({'value':x['value'],'unit':x['unit'],'period':x['period'],'statement_scope':x['scope'],'canonical_input_ids':[x['record_id']],'official_document_source_type':SOURCE,'document_sha256':x['document_sha256'],'page_citations':[x['citation_id']]})
 return fact
def export(shadow:Mapping[str,Any])->dict[str,Any]:
 if shadow.get('input_source')!='phase7c_official_document_canonical_activation_only':raise ValueError('phase7d_shadow_input_required')
 facts=[]
 for ticker in ('PAN','SSI'):
  for key,row in ((shadow.get(ticker) or {}).get('outputs') or {}).items():
   if ticker=='PAN' and not key.startswith('share_basis.'):continue
   if ticker=='SSI' and not (key.startswith('securities.') or key in {'relative.pe','relative.pb','relative.ps','relative.ev_ebitda','relative.ev_sales','intrinsic.fcff_dcf','intrinsic.net_net'}):continue
   identity=(row.get('input_lineage') or [{}])[0].get('canonical_input') if row.get('state')=='available' else key
   facts.append(_fact(ticker,str(identity),row))
 if 'SSI' in shadow:
  for name,state in ((shadow['SSI'].get('sector_applicability') or {}).items()):facts.append({'ticker':'SSI','fact_identity':name,'status':state,'formula_applicability_version':VERSION,'missing_input_or_inapplicability_reason':['sector_inapplicable_existing_contract']})
 out={'contract_version':VERSION,'section':SECTION,'facts':sorted(facts,key=lambda x:(x['ticker'],x['fact_identity'],x['status']))};out['section_sha256']=_hash(out['facts']);return replay(out)
def replay(value:Mapping[str,Any])->dict[str,Any]:
 facts=[]
 for x in value.get('facts',[]):
  if x.get('status') not in {'available','unavailable','inapplicable'}:raise ValueError('fact_status_invalid')
  if x['status']=='available' and (x.get('official_document_source_type')!=SOURCE or not x.get('document_sha256') or not x.get('page_citations') or not x.get('canonical_input_ids')):raise ValueError('fact_lineage_invalid')
  if any('path' in k.lower() for k in x):raise ValueError('runtime_path_exposure_invalid')
  facts.append(dict(x))
 facts=sorted(facts,key=lambda x:(x['ticker'],x['fact_identity'],x['status']));return {'contract_version':VERSION,'section':SECTION,'facts':facts,'section_sha256':_hash(facts)}
