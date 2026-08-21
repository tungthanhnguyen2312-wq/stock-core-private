from pathlib import Path
import json
from evidence_aware_candidate_comparison import build
from persistent_research_dossier import load_latest_versions
from research_question_tasking import load_latest_tasks
from run_sector_relative_research_context import run as relative_run
from run_strategy_research_eligibility import run as eligibility_run
from run_catalyst_event_research_context import run as event_run
from run_evidence_aware_research_screener import run as screener_run
from run_market_regime_breadth_context import run as market_run
from run_downside_uncertainty_research_context import run as downside_run
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'operations-review/evidence-aware-candidate-comparison-v1-20260820'
def inputs():
 p=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf8')); r,_=relative_run(); e,_=eligibility_run(); v,_=event_run(); s,_=screener_run(); q=json.loads((ROOT/'operations-review/expectations-scenario-research-v1-20260820/expectations_scenario_research_artifact.json').read_text(encoding='utf8')); pack=json.loads((ROOT/'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf8')); return p,r,e,q,load_latest_versions(ROOT/'operations-review/persistent-research-dossier-v1-20260820'),load_latest_tasks(ROOT/'operations-review/research-question-tasking-v1-20260820'),v,s,pack,market_run(),downside_run()[0]
def make(request, source=None):
 p,r,e,q,d,t,v,s,pack,m,down=source or inputs()
 return build(request,product=p,relative=r,eligibility=e,scenarios=q,dossiers=d,tasks=t,events=v,screener=s,review_pack=pack,market_context=m,downside_context=down)
def pilot_requests():
 p,r,e,q,d,t,v,s,pack,m,down=inputs(); session=p['daily_market_research']['session']; review=[x['ticker'] for x in pack['owner_review_queue']]
 official=next(x['ticker'] for x in p['stock_research'] if x['research_summary']['fundamental_authority']=='OFFICIAL_QUALIFIED'); provider=next(x['ticker'] for x in p['stock_research'] if x['research_summary']['fundamental_authority']=='PROVIDER_RESEARCH')
 up=next(x['ticker'] for x in p['stock_research'] if x['research_summary']['trend_state']=='ABOVE_MA20'); down=next(x['ticker'] for x in p['stock_research'] if x['research_summary']['trend_state']=='AT_OR_BELOW_MA20')
 qual=next(x['ticker'] for x in r['records'] if x.get('relative_context_authority')=='QUALIFIED_CLASSIFICATION'); desc=next(x['ticker'] for x in r['records'] if x.get('relative_context_authority')=='PROVIDER_DESCRIPTIVE_CLASSIFICATION')
 dims=['CURRENT_OBSERVABLE_STATE','RELATIVE_CONTEXT','FUNDAMENTAL_EVIDENCE','RESEARCH_LENS_AVAILABILITY','SCENARIO_COUNTER_THESIS','EVIDENCE_QUALITY']
 return [{"mode":"REVIEW_PACK_SUMMARY","research_session":session,"tickers":review,"dimensions":dims,"selection_rule":"EXISTING_REVIEW_PACK_QUEUE"},{"research_session":session,"tickers":[official,provider],"dimensions":dims,"selection_rule":"FIRST_SORTED_OFFICIAL_AND_PROVIDER_FUNDAMENTAL_AUTHORITY"},{"research_session":session,"tickers":[up,down],"dimensions":dims,"selection_rule":"FIRST_SORTED_OPPOSING_TREND_STATE"},{"research_session":session,"tickers":[qual,desc],"dimensions":dims,"selection_rule":"FIRST_SORTED_QUALIFIED_AND_PROVIDER_DESCRIPTIVE_RELATIVE_CONTEXT"}]
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True); source=inputs(); outputs=[make(x,source) for x in pilot_requests()]; (OUT/'candidate_comparison_pilots.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8'); print([x['output_identity'] for x in outputs])
