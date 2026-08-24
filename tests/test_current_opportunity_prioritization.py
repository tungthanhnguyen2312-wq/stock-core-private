from __future__ import annotations
import json
from pathlib import Path
from current_opportunity_prioritization import replay

ROOT=Path(__file__).resolve().parents[1]
def test_materialized_priority_contract_replays_and_preserves_lane_boundaries():
 a=json.loads((ROOT/'operations-review/current-opportunity-prioritization-v1-20260824/current_opportunity_prioritization_artifact.json').read_text(encoding='utf8'));replay(a)
 assert a['coverage']['current_official_universe']==1507 and a['coverage']['EXCLUDED']==0
 assert all('global_score' not in row for row in a['records'].values())
 assert all(row['position_sizing_status']=='NOT_EVALUATED' for row in a['records'].values())
 assert a['event_driven_semantic_review']['past_event_satisfies_gate'] is False
 assert a['event_driven_semantic_review']['agm_only_satisfies_gate'] is False
