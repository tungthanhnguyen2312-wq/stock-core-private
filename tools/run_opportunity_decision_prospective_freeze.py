"""Foreground-only freeze of a completed governed opportunity-decision session."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
 sys.path.insert(0, str(ROOT))

from current_opportunity_prioritization import replay as replay_opportunity
from daily_opportunity_decision_queue import replay as replay_queue
from daily_research_session_operations import _identity, load_registry
from polymorphic_current_strategy_classification import content_identity as strategy_identity
from prospective_research_learning import freeze_opportunity_decision_context, replay_opportunity_decision_context, write_immutable

OUTPUT_CONTRACT = 'opportunity_decision_prospective_freeze/v1'


def _load(path: Path) -> dict[str, Any]:
 return json.loads(path.read_text(encoding='utf-8'))


def _sha256(path: Path) -> str:
 return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(session: str, root: Path = ROOT) -> tuple[dict[str, Any], Path]:
 registry = load_registry(root)
 entry = ((registry.get('completed_sessions') or {}).get(session) or {}).get('output_artifacts', {}).get('daily_opportunity_decision_queue')
 if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) for key in ('path', 'artifact_identity', 'manifest_path', 'operation_identity')):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_COMPLETED_SESSION_MAPPING_MISSING')
 manifest_path = root / entry['manifest_path']; queue_path = root / entry['path']; output_dir = manifest_path.parent
 if queue_path.parent != output_dir:
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_GOVERNED_OUTPUT_DIRECTORY_MISMATCH')
 paths = {'run_manifest.json': manifest_path, 'ai_research_session_bundle.json': output_dir / 'ai_research_session_bundle.json', 'daily_opportunity_decision_queue_artifact.json': queue_path, 'opportunity_prioritization_artifact.json': output_dir / 'opportunity_prioritization_artifact.json', 'strategy_classification_artifact.json': output_dir / 'strategy_classification_artifact.json'}
 if any(not path.is_file() for path in paths.values()):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_GOVERNED_ARTIFACT_MISSING')
 manifest, bundle, queue = _load(manifest_path), _load(paths['ai_research_session_bundle.json']), _load(queue_path)
 opportunity, strategy = _load(paths['opportunity_prioritization_artifact.json']), _load(paths['strategy_classification_artifact.json'])
 if manifest.get('market_session') != session or manifest.get('operation_identity') != entry['operation_identity'] or _identity(manifest) != entry['operation_identity']:
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_MANIFEST_IDENTITY_MISMATCH')
 if manifest.get('outputs', {}).get('daily_opportunity_decision_queue') != entry['artifact_identity'] or queue.get('artifact_identity') != entry['artifact_identity']:
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_QUEUE_IDENTITY_MISMATCH')
 if bundle.get('operation_identity') != entry['operation_identity']:
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_AI_BUNDLE_LINEAGE_MISMATCH')
 if any(key in value for value in (manifest, bundle, queue) for key in ('human_selection', 'final_human_selection', 'final_human_selection_state')):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_RECORDED_HUMAN_SELECTION_REQUIRES_EXPLICIT_INPUT')
 replay_opportunity(opportunity); replay_queue(queue)
 if strategy_identity(strategy).get('artifact_sha256') != strategy.get('artifact_sha256'):
  raise ValueError('OPPORTUNITY_DECISION_FREEZE_STRATEGY_IDENTITY_MISMATCH')
 snapshot = freeze_opportunity_decision_context(manifest=manifest, opportunity=opportunity, decision_queue=queue, strategy=strategy, source_file_hashes={name: _sha256(path) for name, path in paths.items()})
 replay_opportunity_decision_context(snapshot)
 return snapshot, output_dir


def output_path(snapshot: dict[str, Any], root: Path = ROOT) -> Path:
 operation = snapshot['governed_session']['operation_identity'].split(':', 1)[1]
 return root / 'operations-review' / 'opportunity-decision-prospective-freeze-v1' / snapshot['research_session'] / operation / 'opportunity_decision_prospective_freeze.json'


def main() -> None:
 parser = argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--session', required=True, help='Explicit completed governed session date.')
 args = parser.parse_args()
 snapshot, _ = resolve(args.session)
 path = output_path(snapshot)
 write_immutable(path, snapshot)
 print(snapshot['snapshot_id'])
 print(path)


if __name__ == '__main__':
 main()
