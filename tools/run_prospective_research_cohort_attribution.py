"""Foreground first-future descriptive attribution for a frozen entry-relevant cohort.

Joins an immutable prospective_research_learning/cohort_snapshot/v1 T snapshot to
strictly later exact-session price evidence. This is not a backtest, score, or
recommendation engine. Source resolution uses the governed session registry when
that uniquely identifies retained exact-session evidence; ambiguous copies fail closed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from daily_research_session_operations import load_registry
from prospective_research_learning import (
    attribute_prospective_research_cohort_first_future,
    replay_prospective_research_cohort_future_attribution,
    replay_prospective_research_cohort_snapshot,
    write_immutable,
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def output_path(artifact: Mapping[str, Any], root: Path = ROOT) -> Path:
    t_session = artifact['t_session']
    future_session = artifact['future_session']
    return (root / 'operations-review' / 'prospective-research-cohort-future-attribution-v1' /
            f'prospective_research_cohort_future_attribution_{t_session}_to_{future_session}.json')


def _completed(registry: Mapping[str, Any], session: str) -> Mapping[str, Any]:
    completed = (registry.get('completed_sessions') or {}).get(session)
    if not isinstance(completed, Mapping) or completed.get('status') != 'COMPLETED_RETAINED_EVIDENCE':
        raise ValueError('COHORT_ATTRIBUTION_SESSION_NOT_GOVERNED_COMPLETED:' + str(session))
    return completed


def _registered_canonical_attempt_root(root: Path, registry: Mapping[str, Any], session: str) -> Path | None:
    selection = (registry.get('sessions') or {}).get(session) or {}
    marker = f'canonical-post-close-v1/{session}/post-close-attempt-'
    roots: set[str] = set()
    for entry in selection.values() if isinstance(selection, Mapping) else []:
        if not isinstance(entry, Mapping):
            continue
        rel = str(entry.get('path') or '').replace('\\', '/')
        if marker not in rel:
            continue
        remainder = rel.split(marker, 1)[1]
        attempt_id = remainder.split('/', 1)[0]
        if not attempt_id:
            raise ValueError('COHORT_ATTRIBUTION_AMBIGUOUS_REGISTERED_ATTEMPT_ROOT:' + session)
        prefix = rel.split(marker, 1)[0] + marker + attempt_id
        roots.add(prefix)
    if len(roots) > 1:
        raise ValueError('COHORT_ATTRIBUTION_AMBIGUOUS_REGISTERED_ATTEMPT_ROOT:' + session)
    if len(roots) == 1:
        return root / next(iter(roots))
    return None


def _p3f9b_dir_for_session(root: Path, session: str) -> list[Path]:
    nodash = session.replace('-', '')
    found: list[Path] = []
    conventional = root / 'operations-review' / f'p3f9b-market-wide-exact-session-scaleout-{nodash}'
    if conventional.is_dir():
        found.append(conventional)
    canonical = root / 'operations-review' / 'canonical-post-close-v1' / session
    if canonical.is_dir():
        found.extend(sorted(canonical.glob(
            f'post-close-attempt-*/operations-review/p3f9b-market-wide-exact-session-scaleout-{nodash}')))
    return found


def _bundle_paths(directory: Path) -> tuple[Path, Path]:
    snapshot = directory / 'p3f9b_mva_exact_session_snapshot.json'
    scaleout = directory / 'p3f9b_market_wide_exact_session_scaleout_artifact.json'
    if not snapshot.is_file() or not scaleout.is_file():
        raise ValueError('COHORT_ATTRIBUTION_EXACT_SESSION_BUNDLE_INCOMPLETE:' + str(directory))
    return snapshot, scaleout


def _scaleout_identity(path: Path) -> str:
    return str(_load(path).get('snapshot_identity') or '')


def resolve_exact_session_bundle(session: str, root: Path = ROOT, *,
                                 registry: Mapping[str, Any] | None = None,
                                 explicit_snapshot: Path | None = None) -> dict[str, Path]:
    """Resolve one exact-session snapshot+scaleout pair. Fail closed if copies disagree."""
    if explicit_snapshot is not None:
        snapshot = explicit_snapshot if explicit_snapshot.is_absolute() else root / explicit_snapshot
        scaleout = snapshot.with_name('p3f9b_market_wide_exact_session_scaleout_artifact.json')
        if not snapshot.is_file() or not scaleout.is_file():
            raise ValueError('COHORT_ATTRIBUTION_EXPLICIT_EXACT_SESSION_BUNDLE_INCOMPLETE:' + session)
        return {'snapshot': snapshot, 'scaleout': scaleout}
    if registry is None:
        raise ValueError('COHORT_ATTRIBUTION_REGISTRY_REQUIRED_FOR_AUTO_RESOLVE:' + session)
    _completed(registry, session)
    nodash = session.replace('-', '')
    attempt_root = _registered_canonical_attempt_root(root, registry, session)
    if attempt_root is not None:
        directory = (attempt_root / 'operations-review' /
                     f'p3f9b-market-wide-exact-session-scaleout-{nodash}')
        snapshot, scaleout = _bundle_paths(directory)
        return {'snapshot': snapshot, 'scaleout': scaleout}
    candidates = _p3f9b_dir_for_session(root, session)
    if not candidates:
        raise ValueError('COHORT_ATTRIBUTION_EXACT_SESSION_BUNDLE_NOT_FOUND:' + session)
    identities = {_scaleout_identity(_bundle_paths(path)[1]): path for path in candidates}
    if len(identities) != 1:
        raise ValueError('COHORT_ATTRIBUTION_AMBIGUOUS_EXACT_SESSION_SOURCE:' + session)
    snapshot, scaleout = _bundle_paths(next(iter(identities.values())))
    return {'snapshot': snapshot, 'scaleout': scaleout}


def _optional_future_state(root: Path, registry: Mapping[str, Any], session: str) -> dict[str, Any]:
    """Best-effort same-session triage/tactical context. Never fails the attribution."""
    selection = (registry.get('sessions') or {}).get(session) or {}
    loaded: dict[str, Any] = {}
    for name in ('triage', 'tactical'):
        entry = selection.get(name) if isinstance(selection, Mapping) else None
        if not isinstance(entry, Mapping) or not isinstance(entry.get('path'), str):
            continue
        try:
            payload = _load(root / entry['path'])
            if payload.get('artifact_identity') != entry.get('artifact_identity'):
                continue
            loaded[name] = payload
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return loaded


def resolve(snapshot_path: Path, future_session: str, root: Path = ROOT, *,
            registry_path: Path | None = None,
            t_exact_snapshot: Path | None = None,
            future_exact_snapshot: Path | None = None,
            include_future_descriptive_state: bool = True) -> dict[str, Any]:
    snapshot_file = snapshot_path if snapshot_path.is_absolute() else root / snapshot_path
    snapshot = _load(snapshot_file)
    replay_prospective_research_cohort_snapshot(snapshot)
    t_session = snapshot['research_session']
    registry = load_registry(root, registry_path)
    _completed(registry, t_session)
    _completed(registry, future_session)
    t_bundle = resolve_exact_session_bundle(
        t_session, root, registry=registry, explicit_snapshot=t_exact_snapshot)
    future_bundle = resolve_exact_session_bundle(
        future_session, root, registry=registry, explicit_snapshot=future_exact_snapshot)
    future_state = (_optional_future_state(root, registry, future_session)
                    if include_future_descriptive_state else {})
    artifact = attribute_prospective_research_cohort_first_future(
        snapshot=snapshot,
        t_exact_snapshot=_load(t_bundle['snapshot']),
        t_exact_scaleout=_load(t_bundle['scaleout']),
        future_exact_snapshot=_load(future_bundle['snapshot']),
        future_exact_scaleout=_load(future_bundle['scaleout']),
        future_session=future_session,
        future_triage=future_state.get('triage'),
        future_tactical=future_state.get('tactical'),
    )
    replay_prospective_research_cohort_future_attribution(artifact)
    return {
        'artifact': artifact,
        'snapshot_path': snapshot_file,
        't_exact_snapshot': t_bundle['snapshot'],
        'future_exact_snapshot': future_bundle['snapshot'],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True,
                        help='Frozen prospective_research_learning/cohort_snapshot/v1 artifact.')
    parser.add_argument('--future-session', required=True,
                        help='Strictly later governed completed session (YYYY-MM-DD).')
    parser.add_argument('--t-exact-session-snapshot', type=Path,
                        help='Optional explicit T P3F9B snapshot. Scaleout must sit beside it.')
    parser.add_argument('--future-exact-session-snapshot', type=Path,
                        help='Optional explicit future P3F9B snapshot. Scaleout must sit beside it.')
    parser.add_argument('--input-registry', type=Path, help='Explicit governed registry path override.')
    parser.add_argument('--no-future-descriptive-state', action='store_true',
                        help='Omit optional next-session triage/tactical context.')
    args = parser.parse_args()
    result = resolve(
        args.snapshot, args.future_session,
        registry_path=args.input_registry,
        t_exact_snapshot=args.t_exact_session_snapshot,
        future_exact_snapshot=args.future_exact_session_snapshot,
        include_future_descriptive_state=not args.no_future_descriptive_state,
    )
    artifact = result['artifact']
    path = output_path(artifact)
    write_immutable(path, artifact)
    overall = artifact['overall']
    print(f"T_SESSION: {artifact['t_session']}")
    print(f"FUTURE_SESSION: {artifact['future_session']}")
    print(f"FROZEN_SNAPSHOT_IDENTITY: {artifact['frozen_snapshot_identity']}")
    print(f"ARTIFACT_IDENTITY: {artifact['artifact_identity']}")
    print(f"FROZEN_COUNT: {overall['frozen_count']}")
    print(f"OBSERVED_COUNT: {overall['observed_count']}")
    print(f"MISSING_COUNT: {overall['missing_count']}")
    print(f"POSITIVE: {overall['positive']}")
    print(f"NEGATIVE: {overall['negative']}")
    print(f"UNCHANGED: {overall['unchanged']}")
    print(f"MEAN_OBSERVED_RETURN: {overall['mean_observed_return']}")
    print(f"MEDIAN_OBSERVED_RETURN: {overall['median_observed_return']}")
    print(f"STATE_SUMMARIES: {artifact['frozen_triage_state_summaries']}")
    print(f"OUTPUT: {path}")


if __name__ == '__main__':
    main()
