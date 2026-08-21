from pathlib import Path
import json
from downside_uncertainty_research_context import build,review_overlay
from persistent_research_dossier import load_latest_versions
from research_question_tasking import load_latest_tasks
from run_market_regime_breadth_context import run as market_run
from run_sector_relative_research_context import run as relative_run
from run_strategy_research_eligibility import run as eligibility_run
from run_catalyst_event_research_context import run as event_run
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'operations-review/downside-uncertainty-research-context-v1-20260820'
def run():
 p=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf8')); q=json.loads((ROOT/'operations-review/expectations-scenario-research-v1-20260820/expectations_scenario_research_artifact.json').read_text(encoding='utf8')); pack=json.loads((ROOT/'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf8'));x=build(p,market_run(),relative_run()[0],eligibility_run()[0],q,event_run()[0],load_latest_versions(ROOT/'operations-review/persistent-research-dossier-v1-20260820'),load_latest_tasks(ROOT/'operations-review/research-question-tasking-v1-20260820'),pack);return x,review_overlay(x,pack)
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True);x,o=run();(OUT/'downside_uncertainty_research_context_artifact.json').write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8');(OUT/'downside_uncertainty_review_pack_overlay.json').write_text(json.dumps(o,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8');print(x['artifact_identity'])
