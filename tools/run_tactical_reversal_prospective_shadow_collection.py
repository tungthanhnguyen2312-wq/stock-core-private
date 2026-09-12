"""Bounded, deterministic prospective shadow-observation collector.

For one target session (default: the latest genuinely retained tactical session), this:

1. reads the already-produced ``watchlist_tactical_entry_classifier`` artifact for that
   session (never re-invokes the classifier);
2. builds and durably persists one immutable T0 prospective-shadow observation per ticker
   (idempotent -- rerunning against the same retained evidence changes nothing); and
3. matures every previously persisted observation's T+5/T+10/T+20 outcome against whatever
   trading sessions are genuinely retained as of the current run, never fabricating a
   session that has not actually appeared on disk.

No network or provider call, no runtime database write, no classifier invocation, and no
probability/target/sizing output. A missing/incomplete retained-evidence set is reported as
a bounded status, never raised as an unhandled error.
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

import tactical_reversal_prospective_shadow_collection as collection  # noqa: E402


def _future_rows(ticker: str, sessions: list[str], artifacts_by_session: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for session in sessions:
        artifact = artifacts_by_session.get(session)
        record = None
        basis = None
        if artifact is not None:
            record = (artifact.get("records") or {}).get(ticker)
            basis = collection.price_basis_identity_for_artifact(artifact)
        rows.append({"session": session, "record": record, "price_basis_identity": basis})
    return rows


def collect_session(
    *, retained_evidence_root: Path, store_root: Path, session: str, retained_at: str | None = None,
) -> dict[str, Any]:
    sessions = collection.discover_retained_tactical_sessions(retained_evidence_root)
    if session not in sessions:
        return {"blocker": "RETAINED_TACTICAL_ARTIFACT_NOT_FOUND_FOR_SESSION", "session": session}

    current_artifact = collection.load_tactical_artifact(retained_evidence_root, session=session)
    index = sessions.index(session)
    prior_session = sessions[index - 1] if index > 0 else None
    prior_artifact = collection.load_tactical_artifact(retained_evidence_root, session=prior_session) if prior_session else None

    store = collection.ProspectiveShadowObservationStore(store_root)
    persisted = []
    for ticker in sorted((current_artifact.get("records") or {}).keys()):
        observation = collection.build_prospective_observation(
            ticker=ticker, trigger_session=session, current_tactical_artifact=current_artifact,
            prior_session=prior_session, prior_tactical_artifact=prior_artifact,
            prior_evidence_supplied=prior_artifact is not None, retained_at=retained_at,
        )
        saved = store.persist_observation(observation)
        persisted.append(saved["observation_id"])

    return {
        "session": session, "prior_session": prior_session, "ticker_count": len(persisted),
        "observation_ids": persisted, "evidence_mode": collection.evidence_mode_for_session(session),
    }


def mature_all(*, retained_evidence_root: Path, store_root: Path) -> dict[str, Any]:
    """Recompute every observation's outcome against currently-retained future sessions.

    Loads every retained tactical artifact exactly once (not once per observation/session
    pair -- ``discover_retained_tactical_sessions`` returns the *same, monotonically
    growing* session list on every call, so an observation's future-session window can only
    ever be recomputed larger or identical here, never smaller; a prior run's persisted
    outcome is therefore always superseded by this run's recomputation whenever any future
    session exists, making a separate "fall back to a previously-persisted outcome" pass
    unnecessary rather than merely an optimization).
    """
    sessions = collection.discover_retained_tactical_sessions(retained_evidence_root)
    latest = sessions[-1] if sessions else None
    artifacts_by_session = {
        session: collection.load_tactical_artifact(retained_evidence_root, session=session) for session in sessions
    }
    store = collection.ProspectiveShadowObservationStore(store_root)
    outcomes_by_id: dict[str, Any] = {}
    matured = []
    all_observations = []
    for observation_id in store.list_observation_ids():
        observation = store.load_observation(observation_id)
        all_observations.append(observation)
        future_sessions = [item for item in sessions if item > observation["trigger_session"]]
        if not future_sessions:
            continue
        rows = _future_rows(observation["ticker"], future_sessions, artifacts_by_session)
        outcome = collection.mature_outcome(observation, rows, evaluation_as_of_session=latest)
        store.persist_outcome_update(observation_id, outcome)
        outcomes_by_id[observation_id] = outcome
        matured.append(observation_id)
    status = collection.build_collection_status(all_observations, outcomes_by_id)
    return {"matured_observation_ids": matured, "collection_status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-evidence-root", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--session", help="Target session to collect (default: latest retained).")
    parser.add_argument("--retained-at", help="Optional deterministic knowledge-timestamp marker.")
    parser.add_argument("--skip-collect", action="store_true", help="Only mature existing observations.")
    args = parser.parse_args(argv)

    sessions = collection.discover_retained_tactical_sessions(args.retained_evidence_root)
    if not sessions:
        print(json.dumps({"blocker": "NO_RETAINED_TACTICAL_ARTIFACTS_FOUND"}, indent=2))
        return 1

    result: dict[str, Any] = {"retained_sessions_discovered": len(sessions), "latest_retained_session": sessions[-1]}
    if not args.skip_collect:
        target_session = args.session or sessions[-1]
        result["collection"] = collect_session(
            retained_evidence_root=args.retained_evidence_root, store_root=args.store_root,
            session=target_session, retained_at=args.retained_at,
        )
    result["maturation"] = mature_all(retained_evidence_root=args.retained_evidence_root, store_root=args.store_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
