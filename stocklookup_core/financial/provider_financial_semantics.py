"""Versioned, fail-closed provider financial semantic eligibility for research only."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
UNKNOWN='UNKNOWN'; EXPLICIT='EXPLICITLY_QUALIFIED'; PROVIDER='PROVIDER_RESEARCH'
def _hash(x:Any):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def contract(observation:Mapping[str,Any])->dict[str,Any]:
 warnings=set(observation.get('warnings') or [])
 scope=UNKNOWN if 'statement_scope_unknown' in warnings else UNKNOWN
 unit=UNKNOWN if 'currency_and_scale_unknown' in warnings else UNKNOWN
 family=observation.get('statement_family'); nature='instant' if family=='balance_sheet' else ('duration' if family in ('income_statement','cash_flow') else UNKNOWN)
 return {'provider':observation.get('provider'),'method':'retained_provider_schema/v1','statement_family':family,'scope':scope,'currency_unit_scale':unit,'reporting_period':observation.get('reporting_period'),'annual_quarterly_identity':observation.get('period_type'),'duration_basis':UNKNOWN if nature=='duration' else 'NOT_APPLICABLE','metric_nature':nature,'qualification_state':UNKNOWN,'evidence_basis':'retained_raw_observation_schema_warnings','allowed_uses':['descriptive_context'],'forbidden_uses':['official_authority','cross_metric_ratio_when_compatibility_unknown','PIT','execution'],'authority_state':PROVIDER,'identity':_hash(dict(observation))}
def eligible(calculation:str, semantics:Mapping[str,Any])->bool:
 required={'growth':['annual_quarterly_identity'],'net_margin':['scope','currency_unit_scale','duration_basis'],'roa':['scope','currency_unit_scale','duration_basis'],'leverage':['scope','currency_unit_scale']}.get(calculation,[])
 return all(semantics.get(x)==EXPLICIT for x in required)
