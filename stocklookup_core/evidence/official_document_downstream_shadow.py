"""Read-only sector-aware downstream shadow over official canonical activation."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
from fundamental_quality import evaluate_fundamental_quality
from stocklookup_core.valuation.intrinsic_valuation import evaluate_intrinsic_valuation
from stocklookup_core.valuation.relative_valuation import evaluate_relative_valuation

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


# Frozen SSI input qualifier, consolidated here from the former root leaf.
SSI_VERSION = "1.1.0"
TICKER = "SSI"
ENTITY_TYPE = "securities"
FROZEN_PERIOD = "2024"
SUPPORTED_PROVIDER_METHODS = {"brokerage_revenue": {"income_statement"}, "margin_lending_balance": {"balance_sheet"}, "proprietary_trading_assets": {"balance_sheet"}, "proprietary_trading_result": {"income_statement"}, "interest_income": {"income_statement"}, "interest_expense": {"income_statement"}, "net_income_attributable_to_parent": {"income_statement"}, "shareholders_equity": {"balance_sheet"}, "period_end_shares": set(), "weighted_average_basic_shares": set()}
OFFICIAL_METRIC_MAP = {"brokerage_revenue":"brokerage_revenue", "financial_assets_fvtpl":"proprietary_trading_assets", "interest_income_demand_deposits":"interest_income", "borrowing_costs":"interest_expense", "profit_after_tax_parent":"net_income_attributable_to_parent", "total_equity":"shareholders_equity", "period_end_outstanding_ordinary_shares":"period_end_shares"}
METRICS = ("brokerage_revenue", "margin_lending_balance", "proprietary_trading_assets", "proprietary_trading_result", "interest_income", "interest_expense", "net_income_attributable_to_parent", "shareholders_equity", "period_end_shares", "weighted_average_basic_shares")


def _unavailable(metric: str, blocker: str) -> dict[str, Any]:
    return {"metric": metric, "state": "unavailable", "value": None, "blocker_code": blocker, "entity_type": ENTITY_TYPE, "period": FROZEN_PERIOD, "lineage": []}


def _official(row: Mapping[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    source=row.get("official_document_source") if isinstance(row.get("official_document_source"), Mapping) else {}
    metric=OFFICIAL_METRIC_MAP.get(str(row.get("canonical_metric") or ""))
    period=(row.get("period_identity") or {}).get("period") if isinstance(row.get("period_identity"), Mapping) else None
    if (not metric or row.get("source")!="official_document_observation" or source.get("source_type")!="official_document_observation" or period!=FROZEN_PERIOD or row.get("statement_scope")!="consolidated" or not source.get("document_sha256") or not source.get("page_citation_id") or row.get("value") is None): return None,None
    unit=row.get("unit")
    if metric in {"period_end_shares","weighted_average_basic_shares"}:
        if unit not in {"shares","number_of_shares"}: return None,None
    elif unit!="VND": return None,None
    return metric,{"metric":metric,"state":"available","value":row["value"],"entity_type":ENTITY_TYPE,"period":FROZEN_PERIOD,"lineage":[{"source_type":"official_document_observation","document_sha256":source["document_sha256"],"citation_id":source["page_citation_id"],"raw_label":source["raw_label"],"page":source["page"],"qualification_version":source["qualification_version"]}]}


def evaluate(records: list[Mapping[str, Any]] | None, *, ticker: str = TICKER, period: str = FROZEN_PERIOD) -> dict[str, Any]:
    """Accept only cited annual consolidated provider or official-document identities."""
    if ticker != TICKER or period != FROZEN_PERIOD:
        return {"schema_version": SSI_VERSION, "state": "unavailable", "reason": "frozen_time_scope_mismatch", "metrics": {m: _unavailable(m, "frozen_time_scope_mismatch") for m in METRICS}}
    accepted: dict[str, dict[str, Any]] = {}
    for row in records or []:
        metric, official=_official(row)
        if official is not None:
            accepted[metric]=official; continue
        metric=str(row.get("metric") or "")
        if metric not in METRICS or row.get("provider") not in {"VCI","KBS"} or row.get("method") not in SUPPORTED_PROVIDER_METHODS[metric]: continue
        if row.get("reporting_period")!=FROZEN_PERIOD or row.get("reporting_frequency")!="annual" or row.get("statement_scope")!="consolidated" or not row.get("observation_id") or not row.get("citation_id") or row.get("value") is None: continue
        if row.get("unit")!="VND" and metric not in {"period_end_shares","weighted_average_basic_shares"}: continue
        if metric in {"period_end_shares","weighted_average_basic_shares"} and row.get("unit")!="shares": continue
        accepted[metric]={"metric":metric,"state":"available","value":row["value"],"entity_type":ENTITY_TYPE,"period":FROZEN_PERIOD,"lineage":[{"source_type":"provider_observation","provider":row["provider"],"observation_id":row["observation_id"],"citation_id":row["citation_id"],"raw_item_id":row.get("raw_item_id"),"method":row["method"]}]}
    metrics={metric:accepted.get(metric,_unavailable(metric,"ssi_fy2024_qualified_annual_identity_missing")) for metric in METRICS}
    return {"schema_version":SSI_VERSION,"ticker":TICKER,"entity_type":ENTITY_TYPE,"frozen_at":"2024-12-31","state":"available" if accepted else "unavailable","applicability":{"fcff_dcf":"inapplicable","net_net":"inapplicable","ev_ebitda":"inapplicable","ev_sales":"inapplicable","corporate_debt":"inapplicable"},"metrics":metrics}

# Preserve the already exported caller binding and the function name/object.
evaluate_ssi = evaluate
