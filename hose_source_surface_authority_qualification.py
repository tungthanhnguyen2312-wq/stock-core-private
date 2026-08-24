"""First-party HOSE source-surface capability qualification, not data acquisition."""
from __future__ import annotations
import hashlib,json,tempfile
from datetime import UTC,datetime
from pathlib import Path
from urllib.request import Request,urlopen

CATALOG='https://staticfile.hsx.vn/Uploads/UploadDocuments/2406142/Bieu%20gia%20dich%20vu%20cung%20cap%20tin.pdf'
SPA_SURFACES=('https://www.hsx.vn/Modules/Listed/Web/Symbols','https://www.hsx.vn/Modules/News/Web/Disclosure','https://www.hsx.vn/Modules/Market/Web/CorporateAction','https://www.hsx.vn/Modules/Market/Web/ForeignRoom')
def sha(x:bytes)->str:return hashlib.sha256(x).hexdigest()
def now()->str:return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00','Z')
def atomic(p:Path,b:bytes)->None:
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b:raise ValueError('IMMUTABLE_CONTENT_CONFLICT')
 if p.exists():return
 with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as t:t.write(b);q=Path(t.name)
 q.replace(p)
def fetch(url:str)->dict:
 at=now()
 try:
  with urlopen(Request(url,headers={'User-Agent':'StockLookup-HOSE-Surface/1.0'}),timeout=20) as r:return {'url':r.geturl(),'requested_url':url,'retrieved_at':at,'status':r.status,'content_type':r.headers.get_content_type(),'data':r.read()}
 except Exception as e:return {'url':url,'requested_url':url,'retrieved_at':at,'status':None,'content_type':None,'data':b'','error':type(e).__name__}
def retain(r:dict,d:Path,surface:str)->dict:
 h=sha(r['data']);rel=f'raw/{surface}/{h}.bin';atomic(d/rel,r['data']);return {k:r.get(k) for k in ('url','requested_url','retrieved_at','status','content_type','error')}|{'surface':surface,'sha256':h,'relative_path':rel}
def build(destination:Path)->dict:
 captures=[];catalog=fetch(CATALOG);captures.append(retain(catalog,destination,'licensed_catalog'))
 if catalog['status']!=200 or catalog['content_type']!='application/pdf':raise ValueError('CATALOG_FETCH_FAILED')
 for url in SPA_SURFACES:captures.append(retain(fetch(url),destination,'public_spa_shell'))
 fields=[
 ('listed_shares','KLCP NY','LICENSED_OFFICIAL_PRODUCT','LISTED_SHARES'),('outstanding_shares','KLCP ĐLH','LICENSED_OFFICIAL_PRODUCT','EXCHANGE_REPORTED_OUTSTANDING_OR_CIRCULATING_SHARES'),('restricted_shares','KLCP hạn chế chuyển nhượng','LICENSED_OFFICIAL_PRODUCT','RESTRICTED_SHARES'),('free_float','% free float hiện tại','LICENSED_OFFICIAL_PRODUCT','FREE_FLOAT'),('corporate_event_ex_date','ex-date','LICENSED_OFFICIAL_PRODUCT','EX_DATE'),('corporate_event_adjustment_ratio','tỉ lệ điều chỉnh giá','LICENSED_OFFICIAL_PRODUCT','ADJUSTMENT_RATIO'),('corporate_event_adjusted_reference','giá tham chiếu điều chỉnh','LICENSED_OFFICIAL_PRODUCT','ADJUSTED_REFERENCE_PRICE')]
 products=[{'product_id':'ownership_and_free_float_statistics','field_id':x[0],'official_label':x[1],'access_class':x[2],'candidate_stocklookup_identity':x[3],'qualification':'CATALOG_METADATA_ONLY_NOT_TICKER_OBSERVATION','source_document_identity':captures[0]['sha256']} for x in fields[:4]]+ [{'product_id':'corporate_events','field_id':x[0],'official_label':x[1],'access_class':x[2],'candidate_stocklookup_identity':x[3],'qualification':'CATALOG_METADATA_ONLY_NOT_EVENT_OBSERVATION','source_document_identity':captures[0]['sha256']} for x in fields[4:]]
 a={'schema_version':'1.0.0','contract_version':'hose_source_surface_and_market_data_authority_qualification/v1','captures':captures,'hose_official_data_product_capability/v1':products,'source_capability_map/v1':{'universe':'BLOCKED_PUBLIC_SPA_SHELL_ONLY','issued_shares':'LICENSED_DATA_AVAILABLE','outstanding_shares':'LICENSED_DATA_AVAILABLE','restricted_shares':'LICENSED_DATA_AVAILABLE','corporate_actions':'LICENSED_DATA_AVAILABLE','ex_date':'LICENSED_DATA_AVAILABLE','disclosures':'PUBLIC_METADATA_ONLY_SPA_SHELL','financial_filings':'PUBLIC_METADATA_ONLY_SPA_SHELL','foreign_room':'PUBLIC_METADATA_ONLY_SPA_SHELL'},'source_exhaustion_record':{'public_master_disclosure_corporate_action_foreign_room':'static/public SPA shells inspected; no public rows or pagination contract; reopen only with first-party static index, documented public endpoint, or owner-approved license'},'owner_decision_packet':{'official_product':'HOSE information-service catalog products: ownership/free-float statistics and corporate-event list','documented_access_model':'LICENSED_OFFICIAL_PRODUCT','fields':[x[1] for x in fields],'resolves_if_licensed':['listed shares','exchange-reported outstanding/circulating','restricted shares','free float','corporate event ex-date and adjustment fields'],'does_not_resolve':['accounting common shares outstanding','RAW_AS_TRADED/PIT price authority without separate evidence'],'owner_action_required':'Approve a licensed HOSE access path; no purchase or authentication attempted'},'public_observations':0,'authority_result':'LICENSED_FIELD_CONTRACT_IDENTIFIED_ZERO_TICKER_OBSERVATIONS','authority_boundary':'CATALOG_METADATA_NEVER_PROMOTED_TO_SECURITY_OR_EVENT_OBSERVATIONS','lane_terminal_status':'HOSE_PUBLIC_METADATA_AND_LICENSED_CAPABILITY_IDENTIFIED'}
 h=sha(json.dumps(a,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode());a['artifact_sha256']=h;a['artifact_identity']='hose_source_surface_authority_qualification:'+h;return a
