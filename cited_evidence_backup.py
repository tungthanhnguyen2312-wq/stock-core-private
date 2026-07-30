"""Temporary, hash-verified backup/recovery pilot for cited official evidence."""
from __future__ import annotations
import hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from official_document_retrieval import SELECTED,build_index,search
VERSION="1.0.0"
def _hash(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def _json(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def build_manifest(root:Path,created_at:str)->dict[str,Any]:
 root=Path(root); raw=json.loads((root/'manifest.json').read_text(encoding='utf-8')); docs=[x for x in raw['records'] if x.get('ticker') in SELECTED and x.get('reporting_period')=='2024' and 'consolidated' in str(x.get('evidence_type','')) and (root/x['filename']).is_file()]
 citations=[json.loads(x) for x in (root/'qualification_citations.jsonl').read_text(encoding='utf-8').splitlines() if x]
 ids={x['evidence_id'] for x in docs}; chosen=[x for x in citations if x.get('evidence_id') in ids]
 files=[root/'manifest.json',root/'qualification_citations.jsonl']+[root/x['filename'] for x in docs]
 index=build_index(root)
 queries=[('HPG','net_sales'),('VNM','net_sales'),('VCB','interest_income_and_similar_income')]
 retrieval={t:search(index,ticker=t,period='2024',metric=metric,limit=1) for t,metric in queries}
 citation_ids=sorted(c['citation_id'] for c in chosen)
 return {'schema_version':VERSION,'created_at':created_at,'contract_versions':{'retrieval':index['schema_version'],'backup':VERSION},'tickers':list(SELECTED),'files':[{'relative_path':str(x.relative_to(root)).replace('\\','/'),'size':x.stat().st_size,'sha256':_hash(x)} for x in sorted(files)],'documents':[{'ticker':x['ticker'],'document_id':x['evidence_id'],'sha256':x['sha256']} for x in sorted(docs,key=lambda x:x['evidence_id'])],'expected_counts':{'documents':len(index['documents']),'chunks':len(index['chunks']),'citations':len(chosen)},'parity_fingerprints':{'citation_ids_sha256':hashlib.sha256(_json(citation_ids).encode()).hexdigest(),'retrieval_sha256':hashlib.sha256(_json(retrieval).encode()).hexdigest()}}
def create_backup(root:Path,target:Path,created_at:str)->dict[str,Any]:
 m=build_manifest(root,created_at); target=Path(target); target.mkdir(parents=True,exist_ok=False)
 for item in m['files']:
  src=Path(root)/item['relative_path']; dst=target/item['relative_path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 (target/'backup_manifest.json').write_text(_json(m),encoding='utf-8')
 return {'status':'success','backup_manifest':m,'backup_hash':hashlib.sha256(_json(m).encode()).hexdigest(),'location':str(target)}
def verify_restore(target:Path)->dict[str,Any]:
 target=Path(target); m=json.loads((target/'backup_manifest.json').read_text(encoding='utf-8')); errors=[]
 for item in m['files']:
  p=target/item['relative_path']
  if not p.is_file():errors.append({'code':'missing_file','path':item['relative_path']})
  elif p.stat().st_size!=item['size'] or _hash(p)!=item['sha256']:errors.append({'code':'source_hash_mismatch','path':item['relative_path']})
 if errors:return {'status':'rejected','diagnostics':errors}
 index=build_index(target); counts={'documents':len(index['documents']),'chunks':len(index['chunks']),'citations':sum(len(x['citations']) for x in index['chunks'])}
 if counts['documents']!=m['expected_counts']['documents'] or counts['chunks']!=m['expected_counts']['chunks']:return {'status':'rejected','diagnostics':[{'code':'identity_or_chunk_count_mismatch','actual':counts,'expected':m['expected_counts']}]} 
 queries=[('HPG','net_sales'),('VNM','net_sales'),('VCB','interest_income_and_similar_income')]
 results={t:search(index,ticker=t,period='2024',metric=metric,limit=1) for t,metric in queries}
 citation_ids=sorted(c['citation_id'] for chunk in index['chunks'] for c in chunk['citations'])
 expected=m.get('parity_fingerprints',{})
 if expected.get('retrieval_sha256') != hashlib.sha256(_json(results).encode()).hexdigest():return {'status':'rejected','diagnostics':[{'code':'retrieval_parity_mismatch'}]}
 if expected.get('citation_ids_sha256') != hashlib.sha256(_json(citation_ids).encode()).hexdigest():return {'status':'rejected','diagnostics':[{'code':'citation_identity_mismatch'}]}
 return {'status':'recovered','counts':counts,'documents':index['documents'],'retrieval_results':results}
def run_report(backup:dict[str,Any], recovery:dict[str,Any], rejection:dict[str,Any])->dict[str,Any]:
 """Compact machine-readable summary for a successful backup, rejection, and recovery run."""
 return {'schema_version':VERSION,'backup_status':backup.get('status'),'backup_hash':backup.get('backup_hash'),'recovery_status':recovery.get('status'),'rejection_status':rejection.get('status'),'rejection_diagnostics':rejection.get('diagnostics',[])}