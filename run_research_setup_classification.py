from pathlib import Path
import json
from research_setup_classification import build, consumer_overlays, daily_overlay
from run_price_structure_breakout_context import run as price_run
from run_sector_relative_research_context import run as relative_run

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'operations-review/research-setup-classification-v1-20260820'

def run():
    product = json.loads((ROOT / 'operations-review/mva-daily-investment-research-20260820/mva_daily_investment_research_artifact.json').read_text(encoding='utf8'))
    review = json.loads((ROOT / 'operations-review/human-research-review-pack-v1-20260820/human_research_review_pack_artifact.json').read_text(encoding='utf8'))
    scenarios = json.loads((ROOT / 'operations-review/expectations-scenario-research-v1-20260820/expectations_scenario_research_artifact.json').read_text(encoding='utf8'))
    market = json.loads((ROOT / 'operations-review/market-regime-breadth-context-v1-20260820/market_regime_breadth_context_artifact.json').read_text(encoding='utf8'))
    downside = json.loads((ROOT / 'operations-review/downside-uncertainty-research-context-v2-20260820/downside_uncertainty_research_context_artifact.json').read_text(encoding='utf8'))
    context = build(product, price_run()[0], relative_run()[0], market, downside, scenarios, review)
    return context, daily_overlay(context), *consumer_overlays(context, review, scenarios)

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    context, daily, review, scenario, downside = run()
    for name, artifact in [('research_setup_classification_artifact.json', context), ('research_setup_daily_overlay.json', daily), ('research_setup_review_overlay.json', review), ('research_setup_scenario_fact_overlay.json', scenario), ('research_setup_downside_fact_overlay.json', downside)]:
        (OUT / name).write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf8')
    print(context['artifact_identity'])
