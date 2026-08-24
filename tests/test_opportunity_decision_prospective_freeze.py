import copy
import json
from pathlib import Path

import pytest

from prospective_research_learning import freeze_opportunity_decision_context, replay_opportunity_decision_context, write_immutable
from tools.run_opportunity_decision_prospective_freeze import output_path, resolve


ROOT = Path(__file__).resolve().parents[1]
SESSION = '2026-08-24'
HISTORICAL = ROOT / 'operations-review/current-decision-prospective-learning-v1-20260824/current_decision_prospective_snapshot_20260821.json'


def _snapshot():
 return resolve(SESSION)[0]


def test_real_governed_freeze_is_deterministic_and_preserves_three_layers():
 first, second = _snapshot(), _snapshot()
 assert first['snapshot_id'] == second['snapshot_id']
 replay_opportunity_decision_context(first)
 layers = first['layers']
 assert layers['opportunity_signal_state']['record_count'] == 1507
 assert layers['opportunity_signal_state']['governed_universe']['coverage']['current_official_universe'] == 1507
 assert layers['daily_decision_queue']['record_count'] == 1507
 assert len(layers['daily_decision_queue']['full_priority_now']) == 131
 assert layers['daily_decision_queue']['deterministic_review_queue']['count'] > 0
 assert layers['daily_decision_queue']['legacy_comparison']
 assert layers['human_review_selection'] == {
  'status': 'ABSENT_NOT_RECORDED', 'selection_count': 0, 'selection_tickers': [],
  'provenance': {'reason': 'NO_EXPLICIT_FINAL_HUMAN_SELECTION_ARTIFACT_OR_STATE_RECORDED_FOR_GOVERNED_SESSION', 'checked_governed_sources': ['run_manifest.json', 'ai_research_session_bundle.json', 'daily_opportunity_decision_queue_artifact.json'], 'operation_identity': first['governed_session']['operation_identity']},
  'semantic_boundary': 'NOT_INFERRED_FROM_FULL_PRIORITY_NOW_ENTRY_RELEVANT_DETERMINISTIC_REVIEW_QUEUE_OR_STRATEGY_LANE_QUEUE',
 }


def test_priority_wait_multi_strategy_authority_and_no_hindsight_are_preserved():
 snapshot = _snapshot(); layers = snapshot['layers']
 opportunity = {row['ticker']: row for row in layers['opportunity_signal_state']['records']}
 queue = {row['ticker']: row for row in layers['daily_decision_queue']['records']}
 assert queue['ABT']['research_priority_tier'] == 'PRIORITY_NOW'
 assert queue['ABT']['entry_action'] == 'WAIT'
 assert queue['ABT']['entry_relevant'] is False
 assert layers['daily_decision_queue']['deterministic_review_queue']['count'] != layers['human_review_selection']['selection_count']
 assert set(opportunity['HCM']['eligible_strategy_ids']) == {'FUNDAMENTAL_IMPROVEMENT', 'TREND_MOMENTUM'}
 assert set(opportunity['HWS']['eligible_strategy_ids']) == {'BREAKOUT', 'FUNDAMENTAL_IMPROVEMENT'}
 assert 'no_global_score' in layers['daily_decision_queue']['authority_boundary']
 assert 'NOT_POSITION_SIZING_AUTHORITY' not in json.dumps(queue['ABT'])
 assert 'realized_return' not in json.dumps(snapshot).lower()
 assert 'future_price' not in json.dumps(snapshot).lower()


def test_source_mismatch_and_conflicting_immutable_write_fail_closed(tmp_path):
 with pytest.raises(ValueError, match='COMPLETED_SESSION_MAPPING_MISSING'):
  resolve('2026-08-22')
 snapshot, output_dir = resolve(SESSION)
 manifest = json.loads((output_dir / 'run_manifest.json').read_text(encoding='utf-8'))
 opportunity = json.loads((output_dir / 'opportunity_prioritization_artifact.json').read_text(encoding='utf-8'))
 queue = json.loads((output_dir / 'daily_opportunity_decision_queue_artifact.json').read_text(encoding='utf-8'))
 strategy = json.loads((output_dir / 'strategy_classification_artifact.json').read_text(encoding='utf-8'))
 hashes = dict(snapshot['governed_session']['source_file_sha256'])
 changed = copy.deepcopy(queue); changed['artifact_identity'] = 'daily_opportunity_decision_queue:wrong'
 with pytest.raises(ValueError, match='MANIFEST_LINEAGE_MISMATCH'):
  freeze_opportunity_decision_context(manifest=manifest, opportunity=opportunity, decision_queue=changed, strategy=strategy, source_file_hashes=hashes)
 path = tmp_path / 'freeze.json'; write_immutable(path, snapshot); write_immutable(path, snapshot)
 conflicting = copy.deepcopy(snapshot); conflicting['layers']['human_review_selection']['selection_count'] = 1
 with pytest.raises(ValueError, match='IMMUTABLE_SNAPSHOT_CONTENT_CONFLICT'):
  write_immutable(path, conflicting)


def test_2026_08_21_snapshot_is_unchanged_and_output_path_is_session_bound():
 before = HISTORICAL.read_bytes()
 snapshot = _snapshot()
 assert json.loads(before)['snapshot_id'] == 'prospective_research_snapshot:d227f98bfc0f9d79ae20ae0d686d2eab8085ecb014da3bf48345de7db3c3daf1'
 assert output_path(snapshot).parts[-3:] == ('2026-08-24', '4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa', 'opportunity_decision_prospective_freeze.json')
 assert HISTORICAL.read_bytes() == before
