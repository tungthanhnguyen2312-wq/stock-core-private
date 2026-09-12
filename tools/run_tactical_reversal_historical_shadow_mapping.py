"""Bulk-populate BOOTSTRAP_NON_PROSPECTIVE shadow observations from already-retained evidence.

Uses only local retained ``watchlist_tactical_entry_classifier`` artifacts -- never a
provider/network call -- to exercise the same T0-observation / T+5/T+10/T+20-maturation
machinery ``TACTICAL_REVERSAL_PROSPECTIVE_SHADOW_COLLECTION_V1`` built, across every
historical session already on disk. Every resulting observation's ``evidence_mode`` is
``BOOTSTRAP_NON_PROSPECTIVE`` by construction (all retained sessions are on or before the
2026-09-11 activation boundary as of this milestone); none of this ever counts toward
prospective validation.

Also emits a descriptive-metrics summary (T5/T10/T20 lower-low rate, MAE, MFE, confirmation
lag) broken out by cohort (full R8 control, Candidate A, Candidate B), as a methodology
consistency check against ``TACTICAL_REVERSAL_PROBE_POLICY_COUNTERFACTUAL_EVALUATION_V1``'s
separately-computed figures -- recomputed from this repository's actual currently-retained
evidence, never hard-coded.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for path in (ROOT, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import tactical_reversal_prospective_shadow_collection as collection  # noqa: E402
from run_tactical_reversal_prospective_shadow_collection import collect_session, mature_all  # noqa: E402


def run(*, retained_evidence_root: Path, store_root: Path, retained_at: str | None = None) -> dict[str, Any]:
    sessions = collection.discover_retained_tactical_sessions(retained_evidence_root)
    if not sessions:
        return {"blocker": "NO_RETAINED_TACTICAL_ARTIFACTS_FOUND"}

    per_session = []
    for session in sessions:
        result = collect_session(
            retained_evidence_root=retained_evidence_root, store_root=store_root,
            session=session, retained_at=retained_at,
        )
        per_session.append({"session": session, "ticker_count": result.get("ticker_count"), "evidence_mode": result.get("evidence_mode")})

    maturation = mature_all(retained_evidence_root=retained_evidence_root, store_root=store_root)

    store = collection.ProspectiveShadowObservationStore(store_root)
    observations = [store.load_observation(oid) for oid in store.list_observation_ids()]
    non_bootstrap = [item for item in observations if item["evidence_mode"] != collection.BOOTSTRAP_NON_PROSPECTIVE]
    if non_bootstrap:
        raise AssertionError(
            f"HISTORICAL_MAPPING_INVARIANT_VIOLATED: {len(non_bootstrap)} observation(s) with "
            f"evidence_mode != BOOTSTRAP_NON_PROSPECTIVE found in a historical-only mapping run"
        )

    outcomes_by_id = store.latest_outcome_updates_by_observation()

    summary = collection.historical_descriptive_summary(observations, outcomes_by_id)
    status = collection.build_collection_status(observations, outcomes_by_id)

    return {
        "retained_sessions_discovered": len(sessions), "sessions": per_session,
        "total_bootstrap_observations": len(observations),
        "all_observations_confirmed_bootstrap_non_prospective": True,
        "maturation": {"matured_observation_ids_count": len(maturation.get("matured_observation_ids", []))},
        "collection_status": status,
        "historical_descriptive_summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-evidence-root", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--retained-at", help="Optional deterministic knowledge-timestamp marker.")
    parser.add_argument("--out", type=Path, help="Optional path to also write the full JSON result.")
    args = parser.parse_args(argv)

    result = run(retained_evidence_root=args.retained_evidence_root, store_root=args.store_root, retained_at=args.retained_at)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if "blocker" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
