"""Read-only sector-aware downstream shadow over official canonical activation."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
from fundamental_quality import evaluate_fundamental_quality
from intrinsic_valuation import evaluate_intrinsic_valuation
from relative_valuation import evaluate_relative_valuation
from ssi_securities_pilot import evaluate as evaluate_ssi

VERSION="1.0.0"
SOURCE="official_document_observation"

def _digest(value:Any)->str:return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _records(artifact:Mapping[str,Any],ticker:str)->list[dict[str,Any]]:
 rows=list(((artifact.get('activations') or {}).get(ticker) or {}).get('records') or [])
 for row in rows:
  source=row.get('official_document_source') or {}
  if row.get('source')!=SOURCE or source.get('source_type')!=SOURCE:raise ValueError('shadow_official_source_required')
 return sorted((dict(row) for row in rows),key=lambda r:r['record_id'])
def _lineage(row:Mapping[str,Any])->dict[str,Any]:
 s=row['official_document_source'];return {'canonical_input':row['canonical_metric'],'record_id':row['record_id'],'value':row['value'],'source_type':SOURCE,'document_sha256':s['document_sha256'],'citation_id':s['page_citation_id'],'period':row['period_identity'],'scope':row['statement_scope'],'unit':row['unit'],'formula_version':VERSION}
def _share_facts(rows:list[dict[str,Any]])->list[dict[str,Any]]:
 names={'period_end_shares_outstanding','period_end_outstanding_ordinary_shares','weighted_average_basic_shares_outstanding'}
 return [{'name':'share_basis_fact','state':'available','formula_version':VERSION,'input_lineage':[_lineage(r)],'missing_inputs':[]} for r in rows if r['canonical_metric'] in names]
def _states(values:Mapping[str,Any])->dict[str,list[str]]:
 out={'available':[],'partial':[],'unavailable':[],'inapplicable':[]}
 for name,row in values.items():
  state=row.get('state') or row.get('result_state') or 'unavailable';out.setdefault(state,[]).append(name)
 return {k:sorted(v) for k,v in out.items()}
def build(artifact:Mapping[str,Any])->dict[str,Any]:
 pan,ssi=_records(artifact,'PAN'),_records(artifact,'SSI')
 pan_fq=evaluate_fundamental_quality({'records':pan},'corporate')['models']
 pan_intrinsic=evaluate_intrinsic_valuation({'entity_type':'corporate','financial':{}})['methods']
 pan_relative=evaluate_relative_valuation({'entity_type':'corporate','financial':{}})['methods']
 pan_outputs={**{f'fundamental_quality.{k}':{'state':v['result_state'],'formula_version':v['model_version'],'missing_inputs':v['missing_inputs'],'warnings':v['warnings'],'input_lineage':[]} for k,v in pan_fq.items()},**{f'intrinsic.{k}':{'state':v['state'],'formula_version':v['method_version'],'missing_inputs':v['missing_inputs'],'warnings':v['warnings'],'input_lineage':[]} for k,v in pan_intrinsic.items()},**{f'relative.{k}':{'state':v['state'],'formula_version':v['method_version'],'missing_inputs':v['missing_inputs'],'warnings':v['warnings'],'input_lineage':[]} for k,v in pan_relative.items()}}
 for n,f in enumerate(_share_facts(pan)):pan_outputs[f'share_basis.{n}']=f
 ssi_eval=evaluate_ssi(ssi);ssi_outputs={}
 for name,row in ssi_eval['metrics'].items():
  matches=[r for r in ssi if r['canonical_metric'] in {'brokerage_revenue': 'brokerage_revenue','financial_assets_fvtpl':'proprietary_trading_assets','interest_income_demand_deposits':'interest_income','borrowing_costs':'interest_expense','profit_after_tax_parent':'net_income_attributable_to_parent','total_equity':'shareholders_equity','period_end_outstanding_ordinary_shares':'period_end_shares'}.keys() and name=={'brokerage_revenue': 'brokerage_revenue','financial_assets_fvtpl':'proprietary_trading_assets','interest_income_demand_deposits':'interest_income','borrowing_costs':'interest_expense','profit_after_tax_parent':'net_income_attributable_to_parent','total_equity':'shareholders_equity','period_end_outstanding_ordinary_shares':'period_end_shares'}[r['canonical_metric']]]
  ssi_outputs['securities.'+name]={'state':row['state'],'formula_version':ssi_eval['schema_version'],'missing_inputs':[] if row['state']=='available' else [row['blocker_code']],'warnings':[],'input_lineage':[_lineage(r) for r in matches]}
 for group,result in [('intrinsic',evaluate_intrinsic_valuation({'entity_type':'securities','financial':{}})['methods']),('relative',evaluate_relative_valuation({'entity_type':'securities','financial':{}})['methods'])]:
  for name,row in result.items():ssi_outputs[f'{group}.{name}']={'state':row['state'],'formula_version':row['method_version'],'missing_inputs':row['missing_inputs'],'warnings':row['warnings'],'input_lineage':[]}
 payload={'schema_version':VERSION,'input_source':'phase7c_official_document_canonical_activation_only','input_counts':{'PAN':len(pan),'SSI':len(ssi)},'PAN':{'outputs':pan_outputs,'states':_states(pan_outputs)},'SSI':{'outputs':ssi_outputs,'states':_states(ssi_outputs),'sector_applicability':ssi_eval['applicability']}}
 return replay(payload)
def replay(value:Mapping[str,Any])->dict[str,Any]:
 for ticker in ('PAN','SSI'):
  for row in (value.get(ticker) or {}).get('outputs',{}).values():
   for fact in row.get('input_lineage',[]):
    if fact.get('source_type')!=SOURCE or not fact.get('document_sha256') or not fact.get('citation_id'):raise ValueError('shadow_lineage_invalid')
 return {'schema_version':VERSION,'input_source':value.get('input_source'),'input_counts':dict(value.get('input_counts') or {}),'PAN':{'outputs':dict(sorted(((value.get('PAN') or {}).get('outputs') or {}).items())),'states':dict((value.get('PAN') or {}).get('states') or {})},'SSI':{'outputs':dict(sorted(((value.get('SSI') or {}).get('outputs') or {}).items())),'states':dict((value.get('SSI') or {}).get('states') or {}),'sector_applicability':dict((value.get('SSI') or {}).get('sector_applicability') or {})}}
