from pathlib import Path
import json
from catalyst_event_research_context import build, review_overlay
from persistent_research_dossier import load_latest_versions
from research_question_tasking import load_latest_tasks

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "operations-review/catalyst-event-research-context-v1-20260820"

def run():
    product=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf-8'))
    scenarios=json.loads((ROOT/'operations-review/expectations-scenario-research-v1-20260820/expectations_scenario_research_artifact.json').read_text(encoding='utf-8'))
    pack=json.loads((ROOT/'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf-8'))
    context=build(product,load_latest_versions(ROOT/'operations-review/persistent-research-dossier-v1-20260820'),load_latest_tasks(ROOT/'operations-review/research-question-tasking-v1-20260820'),scenarios,pack,root=ROOT)
    return context,review_overlay(pack,context)

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True); context,overlay=run()
    (OUT/'catalyst_event_research_context_artifact.json').write_text(json.dumps(context,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (OUT/'catalyst_event_review_pack_overlay.json').write_text(json.dumps(overlay,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(context['artifact_identity'])
