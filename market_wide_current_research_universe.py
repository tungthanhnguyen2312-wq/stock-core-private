"""Current descriptive research-universe qualification over retained DNSE evidence."""
from __future__ import annotations
import hashlib,json
from collections import Counter
from typing import Any,Mapping,Sequence
from dnse_instrument_universe import normalize_instrument_record,EQUITY
from dnse_security_group_semantics import refine_records

CONTRACT_VERSION='market_wide_current_research_universe/v1'
def _canon(x:Any)->str:return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def build_artifact(*,canonical_snapshot:Mapping[str,Any],instrument_rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
    candidates=sorted(canonical_snapshot['records']); normalized=refine_records([normalize_instrument_record(x,retrieved_at='RETAINED_CURRENT_REFERENCE',page=0) for x in instrument_rows]); by={}
    for item in normalized: by.setdefault(item['symbol'],[]).append(item)
    records={}
    for ticker in candidates:
        masters=by.get(ticker,[]); master=masters[0] if len(masters)==1 else None; market=canonical_snapshot['records'][ticker]
        if len(masters)>1: state,reason='UNKNOWN','AMBIGUOUS_SECURITY_MASTER_SYMBOL'
        elif not master: state,reason='UNKNOWN','SECURITY_MASTER_SYMBOL_NOT_RETAINED'
        elif master['instrument_class']!=EQUITY:
            state,reason=('UNKNOWN','INSTRUMENT_CLASS_UNKNOWN') if master['instrument_class']=='UNKNOWN_SECURITY_GROUP' else ('EXCLUDED',f"INSTRUMENT_CLASS_{master['instrument_class']}")
        elif market.get('status')!='OBSERVED': state,reason='EXCLUDED',f"CURRENT_MARKET_{market.get('disposition','UNAVAILABLE')}"
        else: state,reason='INCLUDED','CURRENT_DESCRIPTIVE_EQUITY_WITH_EXACT_SESSION_OBSERVATION'
        records[ticker]={'ticker':ticker,'instrument_class':master['instrument_class'] if master else 'UNKNOWN','instrument_class_basis':master.get('classification_basis') if master else 'MISSING','exchange':master.get('exchange_raw') if master else None,'listing_context':'UNKNOWN_NOT_PROVIDED_BY_DNSE_INSTRUMENTS','current_market_disposition':market.get('disposition'),'research_state':state,'reason_code':reason}
    counts=Counter(x['research_state'] for x in records.values()); classes=Counter(x['instrument_class'] for x in records.values()); out={'schema_version':'1.0.0','contract_version':CONTRACT_VERSION,'input_universe':{'candidate_count':len(candidates),'snapshot_identity':canonical_snapshot.get('snapshot_identity')},'reference_ledger':{'source':'DNSE_INSTRUMENTS_CURRENT_REFERENCE','retained_row_count':len(normalized),'duplicate_symbol_row_count':sum(len(items)-1 for items in by.values()),'complete':True},'records':records,'disposition_counts':dict(sorted(counts.items())),'instrument_classes':dict(sorted(classes.items())),'current_research_universe':{'included_count':counts['INCLUDED'],'scope':'CURRENT_DESCRIPTIVE_BREADTH_AND_CROSS_SECTIONAL_SCREENING_ONLY','not_authoritative':True},'promotion_recommendation':{'state':'OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE','reason':'CURRENT_LISTING_STATUS_NOT_PROVIDED_BY_DNSE_INSTRUMENTS'},'authority_boundary':{'historical_constituents':'NOT_CONSTRUCTED','PIT':'BLOCKED','RAW_AS_TRADED':'NOT_PROMOTED','ranking_recommendation_valuation':'NOT_EMITTED','promotion_state':'OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE'}}; d=hashlib.sha256(_canon(out).encode()).hexdigest();out['artifact_sha256']=d;out['artifact_identity']='market_wide_current_research_universe:'+d;return out
