from pathlib import Path
import json
from prospective_research_learning import freeze,write_immutable,attribute
ROOT=Path(__file__).resolve().parent
def run():
 p=json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf-8'));a=json.loads((ROOT/'operations-review/ai-research-analyst-v1-20260820/ai_research_analyst_artifact.json').read_text(encoding='utf-8'));s=freeze(p,a);return s,attribute(s)
if __name__=='__main__':
 s,a=run();d=ROOT/'operations-review/prospective-research-learning-v1-20260820';write_immutable(d/(s['snapshot_id'].split(':')[1]+'.json'),s);(d/'attribution_status.json').write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');print(s['snapshot_id'])
