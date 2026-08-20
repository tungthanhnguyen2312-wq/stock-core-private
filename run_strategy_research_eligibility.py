from pathlib import Path
import json
from strategy_research_eligibility import build,review_overlay
from run_sector_relative_research_context import run as run_relative_context
from run_catalyst_event_research_context import run as run_event_context
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'operations-review/strategy-research-eligibility-v1-20260820'
def run():
 p=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf-8'));c,_=run_relative_context();e,_=run_event_context();s=json.loads((ROOT/'operations-review/expectations-scenario-research-v1-20260820/expectations_scenario_research_artifact.json').read_text(encoding='utf-8'));pack=json.loads((ROOT/'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf-8'));a=build(p,c,s,e);return a,review_overlay(pack,a)
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True);a,o=run();(OUT/'strategy_research_eligibility_artifact.json').write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');(OUT/'strategy_research_eligibility_review_overlay.json').write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');print(a['artifact_identity'])
