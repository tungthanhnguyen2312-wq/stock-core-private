"""Isolated SQLite replay and read-only parity for Evidence Registry JSONL inputs."""
from __future__ import annotations
import argparse,hashlib,json,sqlite3,uuid
from pathlib import Path
from typing import Any,Iterable
from evidence_registry import EvidenceRegistry,EVIDENCE,FILES,SUPPORTED_SHARE

def sha(p:Path)->str:
 h=hashlib.sha256();h.update(p.read_bytes());return h.hexdigest()
def j(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def sources(root:Path):
 return [("manifest",root/EVIDENCE/'manifest.json'),("observations",root/'data'/'financial-observations'/'observations.jsonl')]+[(k,root/EVIDENCE/f) for k,f in FILES.items()]
def rows(kind:str,p:Path):
 if kind=='manifest': return json.loads(p.read_text(encoding='utf-8-sig')).get('records',[])
 return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def ident(kind,row):
 return row.get('evidence_id') if kind=='manifest' else row.get('observation_id') if kind=='observations' else row.get('citation_id')
def init(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS replay_sources(path TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,completed INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS replay_items(kind TEXT,identity TEXT,payload_hash TEXT,payload TEXT,PRIMARY KEY(kind,identity));CREATE TABLE IF NOT EXISTS replay_facts(identity TEXT PRIMARY KEY,payload TEXT);''')
def validate(c):
 by={k:{x[0] for x in c.execute('select identity from replay_items where kind=?',(k,))} for k in ['manifest','observations']}; issues=[]
 for kind,payload in c.execute("select kind,payload from replay_items where kind not in ('manifest','observations')"):
  x=json.loads(payload); eid=x.get('evidence_id'); oid=x.get('observation_id'); metric=x.get('identity_type')
  if kind!='market_price' and eid not in by['manifest']:issues.append('dangling_document:'+str(x.get('citation_id')))
  if kind=='qualification' and oid not in by['observations']:issues.append('dangling_observation:'+str(x.get('citation_id')))
  if kind=='share_basis' and metric not in SUPPORTED_SHARE:issues.append('unsupported_metric_semantics:'+str(x.get('citation_id')))
 groups={}
 for kind,payload in c.execute("select kind,payload from replay_items where kind not in ('manifest','observations')"):
  x=json.loads(payload); k=(kind,x.get('ticker'),x.get('reporting_period') or x.get('trading_date'),x.get('identity_type') or x.get('raw_item_id') or x.get('metric'),x.get('raw_statement_type'));groups.setdefault(k,[]).append(x)
 for k,xs in groups.items():
  if len(xs)>1:
   ids={x.get('citation_id') for x in xs}; ok=[x for x in xs if set(x.get('supersedes_citation_ids',[]))==ids-{x.get('citation_id')} and all(x.get('value')==y.get('value') for y in xs)]
   if len(ok)!=1:issues.append('duplicate_or_supersession_conflict:'+str(k))
 return issues
def replay(root:Path,db:Path)->dict[str,Any]:
 root=Path(root);db=Path(db); c=sqlite3.connect(db);init(c); fps=[]
 for kind,p in sources(root):
  if not p.is_file():raise ValueError('missing_source:'+str(p))
  fp=sha(p);fps.append((str(p.relative_to(root)),fp)); prior=c.execute('select fingerprint from replay_sources where path=?',(str(p.relative_to(root)),)).fetchone()
  if prior and prior[0]!=fp:raise ValueError('source_fingerprint_changed:'+str(p))
  for n,x in enumerate(rows(kind,p)):
   i=ident(kind,x)
   if not i:raise ValueError('missing_identity:'+kind+':'+str(n))
   ph=hashlib.sha256(j(x).encode()).hexdigest(); old=c.execute('select payload_hash from replay_items where kind=? and identity=?',(kind,i)).fetchone()
   if old and old[0]!=ph:raise ValueError('duplicate_identity_conflict:'+kind+':'+str(i))
   c.execute('insert or ignore into replay_items values(?,?,?,?)',(kind,i,ph,j(x)))
  c.execute('insert or replace into replay_sources values(?,?,1)',(str(p.relative_to(root)),fp))
 issues=validate(c)
 if issues:c.commit();c.close();raise ValueError('fail_closed:'+','.join(issues))
 legacy=EvidenceRegistry(root).load()
 if legacy.issues:c.close();raise ValueError('legacy_registry_issues:'+j(legacy.issues))
 for f in legacy.facts:c.execute('insert or replace into replay_facts values(?,?)',(f['identity'],j(f)))
 c.commit(); stored=[json.loads(x[0]) for x in c.execute('select payload from replay_facts order by identity')]; expected=sorted(legacy.facts,key=lambda x:x['identity'])
 if stored!=expected:c.close();raise ValueError('blocking_parity_difference')
 result={'fingerprint':fps,'items':c.execute('select count(*) from replay_items').fetchone()[0],'facts':len(stored),'issues':issues,'parity_pass':True};c.close();return result
def main(argv:Iterable[str]|None=None):
 p=argparse.ArgumentParser();p.add_argument('--runtime-root',required=True);p.add_argument('--db',required=True);p.add_argument('--output',required=True);a=p.parse_args(argv);out=Path(a.output)
 if out.exists():p.error('output exists')
 result=replay(Path(a.runtime_root),Path(a.db));out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8');return 0
if __name__=='__main__':raise SystemExit(main())