"""Foreground collection of one completed session's entry-relevant prospective cohort snapshot.

Scales prospective research-state collection from the original HPG/VCB pilot cases to the
deterministic full_universe_entry_candidate_triage entry-relevant cohort (BASE_BUILDING,
BREAKOUT_READY, EARLY_REVERSAL_CANDIDATE -- currently ~95 tickers, never narrowed to the
high-priority review subset). This is a separate, non-blocking step that runs after a session's
Canonical Daily Producer has already completed; a failure here never revises or invalidates the
completed market session, and one malformed ticker never blocks the rest of the cohort.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from daily_producer_pipeline import resolve_latest_registered_completed_session
from daily_research_session_operations import load_registry
from full_universe_entry_candidate_triage import replay as replay_triage
from prospective_research_learning import (
    freeze_prospective_research_cohort,
    replay_prospective_research_cohort_snapshot,
    write_immutable,
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _full_universe_snapshot_id(registry: dict[str, Any], session: str) -> str | None:
    """Best-effort cross-link to the same-session full-universe freeze; never required."""
    try:
        entry = ((registry.get('completed_sessions') or {}).get(session) or {}).get('output_artifacts', {}).get('daily_opportunity_decision_queue')
        manifest = _load(ROOT / entry['manifest_path'])
        return manifest.get('outputs', {}).get('prospective_snapshot')
    except Exception:
        return None


def resolve(session: str, root: Path = ROOT, *, decision_packet_path: Path | None = None,
            registry_path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(root, registry_path)
    completed = (registry.get('completed_sessions') or {}).get(session)
    if not isinstance(completed, dict) or completed.get('status') != 'COMPLETED_RETAINED_EVIDENCE':
        raise ValueError('PROSPECTIVE_COHORT_COLLECTION_SESSION_NOT_GOVERNED_COMPLETED:' + str(session))
    frozen = completed.get('frozen_input_identities') or {}
    triage_entry = ((registry.get('sessions') or {}).get(session) or {}).get('triage')
    if not isinstance(triage_entry, dict) or not isinstance(triage_entry.get('path'), str):
        raise ValueError('PROSPECTIVE_COHORT_COLLECTION_TRIAGE_NOT_REGISTERED:' + str(session))
    triage_path = root / triage_entry['path']
    triage = _load(triage_path)
    if triage.get('artifact_identity') != triage_entry.get('artifact_identity') or triage.get('artifact_identity') != frozen.get('triage'):
        raise ValueError('PROSPECTIVE_COHORT_COLLECTION_TRIAGE_IDENTITY_MISMATCH:' + str(session))
    replay_triage(triage)
    decision_packet = _load(decision_packet_path) if decision_packet_path is not None else None
    snapshot = freeze_prospective_research_cohort(
        session=session, triage=triage, decision_packet=decision_packet,
        registered_source_identities=frozen, full_universe_prospective_snapshot_id=_full_universe_snapshot_id(registry, session),
    )
    replay_prospective_research_cohort_snapshot(snapshot)
    return {'snapshot': snapshot, 'triage_path': triage_path, 'decision_packet_path': decision_packet_path}


def output_path(snapshot: dict[str, Any], root: Path = ROOT) -> Path:
    return root / 'operations-review' / 'prospective-research-cohort-collection-v1' / f"prospective_research_cohort_snapshot_{snapshot['research_session']}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--session', help='Exact governed completed market session (YYYY-MM-DD).')
    mode.add_argument('--latest-completed-session', action='store_true', help='Resolve only from the explicit governed completed-session ledger; never from wall clock.')
    parser.add_argument('--decision-packet-path', type=Path, help='Optional same-session current_research_decision_packet artifact. Omitted proceeds with degraded per-ticker component detail rather than blocking.')
    parser.add_argument('--input-registry', type=Path, help='Explicit governed registry path override.')
    args = parser.parse_args()
    registry = load_registry(ROOT, args.input_registry)
    session = args.session or resolve_latest_registered_completed_session(registry)
    result = resolve(session, decision_packet_path=args.decision_packet_path, registry_path=args.input_registry)
    snapshot = result['snapshot']
    path = output_path(snapshot)
    write_immutable(path, snapshot)
    print(f"SESSION: {session}")
    print(f"SNAPSHOT_ID: {snapshot['snapshot_id']}")
    print(f"COHORT_COUNT: {snapshot['cohort_count']}")
    print(f"STATE_COUNTS: {snapshot['state_counts']}")
    print(f"HIGH_PRIORITY_REVIEW_ELIGIBLE_COUNT: {snapshot['high_priority_review_eligible_count']}")
    print(f"DECISION_PACKET_COVERAGE: {snapshot['decision_packet_coverage']}")
    print(f"OUTPUT: {path}")


if __name__ == '__main__':
    main()
