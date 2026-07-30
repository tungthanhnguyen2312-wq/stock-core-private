"""Durable bounded OCR sidecar contract; execution adapters are caller supplied."""
from __future__ import annotations
import hashlib,json,os,sys,tempfile
from pathlib import Path
from typing import Any,Callable,Mapping
from ocr_sidecar_encoding import decode_utf8,diagnostic,stable_json
STATES={'ocr_available','ocr_partial','ocr_timeout','ocr_failed','ocr_empty_page','invalid_utf8_ocr_text','source_hash_mismatch'}
def configure_utf8_console(stdout=None,stderr=None)->None:
 """Best-effort UTF-8 console setup for Windows OCR runners and adapters."""
 for stream in (sys.stdout if stdout is None else stdout,sys.stderr if stderr is None else stderr):
  reconfigure=getattr(stream,'reconfigure',None)
  if callable(reconfigure):
   try:reconfigure(encoding='utf-8',errors='replace')
   except (OSError,ValueError,AttributeError):pass
def sha256_file(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def citation_id(doc:str,sha:str,page:int,text:str)->str:return hashlib.sha256(f'ocr|{doc}|{sha}|{page}|{text}'.encode()).hexdigest()
def select_documents(root:Path,ids:tuple[str,...])->list[dict[str,Any]]:
 m=json.loads((Path(root)/'official_document_acquisition_manifest.json').read_text(encoding='utf-8-sig'));rows=[r for r in m['records'] if r.get('document_id') in ids and r.get('extraction_status')=='needs_ocr']
 if len(rows)!=len(ids) or {r['document_id'] for r in rows}!=set(ids):raise ValueError('governed_document_selection_invalid')
 for r in rows:
  p=Path(root)/r['relative_path']
  if not p.is_file() or sha256_file(p)!=r['sha256']:raise ValueError('source_hash_mismatch')
 return sorted(rows,key=lambda r:r['document_id'])
def atomic_write(path:Path,value:Mapping[str,Any])->None:
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent);os.close(fd)
 try:Path(tmp).write_bytes(stable_json(value));os.replace(tmp,path)
 finally:
  if Path(tmp).exists():Path(tmp).unlink()
def load_checkpoint(path:Path)->dict[str,Any]:return json.loads(Path(path).read_text(encoding='utf-8-sig')) if Path(path).exists() else {'schema_version':'1.0.0','pages':[]}
def add_batch(checkpoint:dict[str,Any],record:Mapping[str,Any],pages:list[tuple[int,bytes,bytes]])->dict[str,Any]:
 out={**checkpoint,'schema_version':'1.0.0','pages':list(checkpoint.get('pages',[]))};seen={(x['document_id'],x['page']) for x in out['pages']}
 for page,stdout,stderr in pages:
  if (record['document_id'],page) in seen:continue
  try:text=decode_utf8(stdout,kind='ocr');status='ocr_available' if text.strip() else 'ocr_empty_page'
  except ValueError:text='';status='invalid_utf8_ocr_text'
  row={'document_id':record['document_id'],'document_sha256':record['sha256'],'page':page,'provenance':'ocr','status':status,'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'diagnostic':diagnostic(stderr)}
  if status=='ocr_available':row['citation_id']=citation_id(record['document_id'],record['sha256'],page,text)
  out['pages'].append(row)
 result={'schema_version':'1.0.0','pages':replay(out['pages'])}
 if 'revisions' in out:result['revisions']=replay_revisions(out['revisions'])
 return result
def rotated_revision_id(doc:str,sha:str,page:int,rotation:int,engine:str,text:str)->str:
 return hashlib.sha256(f'ocr_revision|{doc}|{sha}|{page}|{rotation}|{engine}|{text}'.encode()).hexdigest()
def add_rotated_revision(checkpoint:dict[str,Any],record:Mapping[str,Any],page:int,rotation:int,engine:str,stdout:bytes,stderr:bytes)->dict[str,Any]:
 if rotation not in {90,270}:raise ValueError('ocr_rotation_invalid')
 source=next((x for x in checkpoint.get('pages',[]) if x.get('document_id')==record['document_id'] and x.get('page')==page),None)
 if source is None:raise ValueError('ocr_revision_source_page_missing')
 try:text=decode_utf8(stdout,kind='ocr');status='ocr_available' if text.strip() else 'ocr_empty_page'
 except ValueError:text='';status='invalid_utf8_ocr_text'
 rid=rotated_revision_id(record['document_id'],record['sha256'],page,rotation,engine,text);out={**checkpoint,'schema_version':'1.0.0','pages':list(checkpoint.get('pages',[])),'revisions':list(checkpoint.get('revisions',[]))}
 if any(x.get('revision_id')==rid for x in out['revisions']):return {**out,'revisions':replay_revisions(out['revisions'])}
 row={'revision_id':rid,'document_id':record['document_id'],'document_sha256':record['sha256'],'source_page':page,'source_page_citation_id':source.get('citation_id'),'rotation_degrees':rotation,'ocr_engine':engine,'provenance':'ocr_rotated_revision','status':status,'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'diagnostic':diagnostic(stderr),'linkage':'augments','augments_citation_id':source.get('citation_id'),'supersedes_revision_id':None}
 if status=='ocr_available':row['citation_id']=citation_id(record['document_id'],record['sha256'],page,text)
 out['revisions'].append(row);return {**out,'revisions':replay_revisions(out['revisions'])}
def replay(rows:list[Mapping[str,Any]])->list[dict[str,Any]]:
 out=[]
 for r in rows:
  if r.get('provenance')!='ocr' or r.get('status') not in STATES:raise ValueError('ocr_provenance_invalid')
  if int(r.get('page',0))<1:raise ValueError('ocr_page_invalid')
  if r['status']=='ocr_available' and r.get('citation_id')!=citation_id(r['document_id'],r['document_sha256'],int(r['page']),r['text']):raise ValueError('ocr_citation_identity_mismatch')
  out.append(dict(r))
 return sorted(out,key=lambda r:(r['document_id'],int(r['page']),r.get('citation_id','')))
def replay_revisions(rows:list[Mapping[str,Any]])->list[dict[str,Any]]:
 out=[]
 for r in rows:
  if r.get('provenance')!='ocr_rotated_revision' or r.get('status') not in STATES:raise ValueError('ocr_revision_provenance_invalid')
  if int(r.get('source_page',0))<1 or int(r.get('rotation_degrees',0)) not in {90,270}:raise ValueError('ocr_revision_rotation_invalid')
  rid=rotated_revision_id(r['document_id'],r['document_sha256'],int(r['source_page']),int(r['rotation_degrees']),r['ocr_engine'],r['text'])
  if r.get('revision_id')!=rid:raise ValueError('ocr_revision_identity_mismatch')
  if r['status']=='ocr_available' and r.get('citation_id')!=citation_id(r['document_id'],r['document_sha256'],int(r['source_page']),r['text']):raise ValueError('ocr_revision_citation_identity_mismatch')
  out.append(dict(r))
 return sorted(out,key=lambda r:r['revision_id'])