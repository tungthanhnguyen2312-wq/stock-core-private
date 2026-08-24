from __future__ import annotations
import hashlib,json,sys
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hnx_enumerable_universe_kllh_event_disclosure_scaleout import _content,parse_list,parse_events,parse_disclosures,_total
OUT=ROOT/'operations-review'/'hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260824'/'hnx_enumerable_universe_artifact.json'
RAW=OUT.parent/'raw'
UNIVERSE=ROOT/'operations-review'/'current-market-universe-breadth-foundation-v1-20260823'/'current_market_universe_breadth_foundation_artifact.json'
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def pages(surface):
 files=sorted((RAW/surface).glob('*'),key=lambda p:int(p.name.split('-',1)[0]))
 if not files:raise ValueError('MISSING_RAW:'+surface)
 return files
def main():
 list_rows=[];events=[];disclosures=[];captures=[]
 for market,surface in [('HNX_LISTED','hnx_listed_list_bulk'),('UPCOM','upcom_list_bulk')]:
  f=pages(surface)[0];sha=f.stem.split('-',1)[1];doc=_content(f.read_bytes());rows=parse_list(doc,market=market,capture={'official_url':'https://hnx.vn','sha256':sha})
  if len(rows)!=_total(doc):raise ValueError('LIST_ACCOUNTING:'+market)
  list_rows+=rows;captures.append({'surface':surface,'page':1,'sha256':sha,'relative_path':str(f.relative_to(OUT.parent)).replace('\\','/')})
 for market,surface,expect in [('HNX_LISTED','hnx_listed_rights',1367),('UPCOM','upcom_rights',3261)]:
  fs=pages(surface)
  expected_pages=2 if market=='HNX_LISTED' else 327
  if [int(f.name.split('-',1)[0]) for f in fs]!=list(range(1,expected_pages+1)):raise ValueError('EVENT_PAGE_GAP:'+market)
  rows=[]
  for f in fs:
   sha=f.stem.split('-',1)[1];doc=_content(f.read_bytes())
   if _total(doc)!=expect:raise ValueError('EVENT_TOTAL_DRIFT:'+market)
   rows += parse_events(doc,market=market,capture={'official_url':'https://hnx.vn','sha256':sha})
   captures.append({'surface':surface,'page':int(f.name.split('-',1)[0]),'sha256':sha,'relative_path':str(f.relative_to(OUT.parent)).replace('\\','/')})
  if len(rows)!=expect:raise ValueError('EVENT_ACCOUNTING:'+market)
  events+=rows
 for market,surface in [('HNX_LISTED','hnx_listed_disclosure_probe'),('UPCOM','upcom_disclosure_probe')]:
  f=pages(surface)[0];sha=f.stem.split('-',1)[1];doc=_content(f.read_bytes());disclosures+=parse_disclosures(doc,market=market,capture={'official_url':'https://hnx.vn','sha256':sha})
  captures.append({'surface':surface,'page':1,'sha256':sha,'relative_path':str(f.relative_to(OUT.parent)).replace('\\','/')})
 sl=set(json.loads(UNIVERSE.read_text(encoding='utf-8'))['records']);hnx={r['ticker'] for r in list_rows};q=Counter('EQUAL' if r['hnx_kllh_shares']==r['source_listing_or_registration_quantity'] else 'LT' if r['hnx_kllh_shares']<r['source_listing_or_registration_quantity'] else 'GT' for r in list_rows);types=Counter(r['event_type'] for r in events);event_tickers={r['ticker'] for r in events}
 artifact={'schema_version':'1.0.0','contract_version':'hnx_enumerable_universe_kllh_event_and_disclosure_scaleout/v1','captures':captures,'datasets':{'hnx_official_equity_universe/v1':list_rows,'hnx_official_rights_event_index/v1':events,'hnx_official_disclosure_index/v1':disclosures},'source_surface_inventory/v1':[{'surface_id':'listed','role':'UNIVERSE_ENUMERATION','enumerable':True,'total':299},{'surface_id':'upcom','role':'UNIVERSE_ENUMERATION','enumerable':True,'total':821},{'surface_id':'SearchSuggestSymbol','role':'LOOKUP','enumerable':False},{'surface_id':'issuer_profile','role':'ISSUER_DETAIL','enumerable':False},{'surface_id':'rights','role':'EVENT_CALENDAR','enumerable':True,'total':4628},{'surface_id':'disclosure','role':'DISCLOSURE_INDEX','enumerable':True,'total':19726,'retention_scope':'first page per market; title/ticker/date filters supported; no historical backfill'},{'surface_id':'rss','role':'DISCLOSURE_INDEX','enumerable':False},{'surface_id':'attachment','role':'ATTACHMENT','enumerable':False}], 'coverage':{'listed_source_total':299,'upcom_source_total':821,'event_source_total':4628,'event_rows_retained':len(events),'disclosure_source_total':19726,'disclosure_rows_retained':len(disclosures),'event_tickers':len(event_tickers),'ex_date_qualified':sum(r['ex_date'] is not None for r in events),'ex_date_missing':sum(r['ex_date'] is None for r in events),'event_types':dict(types),'kllh_relation':dict(q),'stocklookup_intersection':len(hnx&sl),'stocklookup_only':len(sl-hnx),'hnx_official_only':len(hnx-sl),'hnx_official_only_tickers':sorted(hnx-sl),'event_with_price_history':len(event_tickers&sl)},'authority_result':'ENUMERABLE_HNX_UNIVERSE_AND_EX_DATE_EVENT_INDEX_ONLY_NO_SHARE_OR_RAW_AS_TRADED_PROMOTION','authority_boundary':'KLLH_NOT_COMMON_SHARES_OUTSTANDING; EVENT_EX_DATE_NOT_PRICE_MUTATION; DISCLOSURE_BINDINGS_FAIL_CLOSED','disclosure_binding':{'retained_h1_parents':8,'retained_h1_attachments':27,'exact_ticker_bindings':0,'ticker_resolved_attachments':0,'ticker_unresolved_attachments':27,'result':'BOUNDED_INDEX_PROBE_RETAINED; EXACT_PARENT_FILTERED_SEARCH_PENDING'},'source_exhaustion_record':'SearchSuggestSymbol=LOOKUP_ONLY; disclosure full history not retained because server cap is 10 and bounded filtered scope is sufficient; reopen on exact parent title/date query evidence.','lane_terminal_status':'HNX_UNIVERSE_EVENT_OPERATIONAL_DISCLOSURE_BINDING_PARTIAL','missing_is_zero':False,'canonical_store_mutated':False}
 artifact['artifact_sha256']=digest(artifact);artifact['artifact_identity']='hnx_enumerable_universe_kllh_event_disclosure_scaleout:'+artifact['artifact_sha256'];data=canonical(artifact)+'\n';OUT.write_text(data,encoding='utf-8');print(artifact['artifact_identity'])
if __name__=='__main__':main()
