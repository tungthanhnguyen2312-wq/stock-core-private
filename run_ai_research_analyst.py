from pathlib import Path
import json
from ai_research_analyst import build,markdown
ROOT=Path(__file__).resolve().parent
def run():return build(json.loads((ROOT/'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf-8')))
if __name__=='__main__':
 d=ROOT/'operations-review/ai-research-analyst-v1-20260820';d.mkdir(parents=True,exist_ok=True);a=run();(d/'ai_research_analyst_artifact.json').write_text(json.dumps(a,indent=2,sort_keys=True)+'\n');(d/'daily_ai_research_brief.md').write_text(markdown(a));print(a['artifact_identity'])
