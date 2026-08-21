from pathlib import Path
import json
from downside_uncertainty_research_context import build_v1,build_v2,review_overlay
from persistent_research_dossier import load_latest_versions
from research_question_tasking import load_latest_tasks
from run_market_regime_breadth_context import run as market_run
from run_sector_relative_research_context import run as relative_run
from run_strategy_research_eligibility import run as eligibility_run
from run_catalyst_event_research_context import run as event_run
from run_price_structure_breakout_context import run as price_run
ROOT=Path(__file__).resolve().parent;OUT_V1=ROOT/'operations-review/downside-uncertainty-research-context-v1-restored-20260820';OUT_V2=ROOT/'operations-review/downside-uncertainty-research-context-v2-20260820'
def write_immutable(path, artifact):
 payload=json.dumps(artifact,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
 if path.exists() and path.read_text(encoding='utf8') != payload: raise ValueError('IMMUTABLE_DOWNSIDE_CONTEXT_CONTENT_CONFLICT')
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(payload,encoding='utf8')
def run():
 p=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf8')); q=json.loads((ROOT/'operations-review/expectations-scenario-research-v1-20260820/expectations_scenario_research_artifact.json').read_text(encoding='utf8')); pack=json.loads((ROOT/'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf8')); args=(p,market_run(),relative_run()[0],eligibility_run()[0],q,event_run()[0],load_latest_versions(ROOT/'operations-review/persistent-research-dossier-v1-20260820'),load_latest_tasks(ROOT/'operations-review/research-question-tasking-v1-20260820'),pack); v1=build_v1(*args);v2=build_v2(*args,price_context=price_run()[0]);return v1,v2,review_overlay(v2,pack)
if __name__=='__main__':
 v1,v2,o=run();v1_hash=v1['artifact_identity'].split(':',1)[1];v2_hash=v2['artifact_identity'].split(':',1)[1];write_immutable(OUT_V1/(v1_hash+'.json'),v1);write_immutable(OUT_V2/(v2_hash+'.json'),v2);write_immutable(OUT_V2/(o['artifact_identity'].split(':',1)[1]+'.json'),o);print(v1['artifact_identity'],v2['artifact_identity'])
