"""Authority boundary for broad provider research versus official-qualified facts."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
OFFICIAL='OFFICIAL_QUALIFIED'; PROVIDER='PROVIDER_RESEARCH'; BLOCKED='BLOCKED'
ALLOWED=['descriptive_context','provider_series_growth','sector_aware_research','shadow_comparison']
FORBIDDEN=['official_label','historical_pit_claim','execution_actionability','target_price','portfolio_sizing','authoritative_valuation_input']
def _hash(x:Any):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def provider_fact(raw:Mapping[str,Any],metric:str)->dict[str,Any]:
 return {'value':raw.get('raw_value'),'authority_state':PROVIDER,'method':'retained_provider_mapped_observation/v1','source':raw.get('provider'),'reporting_period':raw.get('reporting_period'),'raw_field_identity':raw.get('raw_item_id'),'mapped_canonical_identity':metric,'observed_at':raw.get('scraped_at'),'scope_currency_scale_status':'UNKNOWN_FAIL_CLOSED','warnings':list(raw.get('warnings') or ['scope_currency_scale_unknown']),'allowed_uses':ALLOWED,'forbidden_uses':FORBIDDEN,'official_citation_claim':False,'identity':_hash(dict(raw))}
def readiness(has_metric:bool,metadata_safe:bool)->str:return 'PROVIDER_RESEARCH_READY' if has_metric else BLOCKED
