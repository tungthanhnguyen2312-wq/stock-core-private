"""Build the tactical reversal shadow probe-policy counterfactual evaluation artifact.

Research-only. Reconstructs a broad local cohort without any provider/network call and
compares the unchanged classifier's R6/R8 behavior against three T0-only shadow probe
policies. See tactical_reversal_probe_policy_counterfactual_evaluation.py for the method.
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

import tactical_reversal_probe_policy_counterfactual_evaluation as probe  # noqa: E402


def _load_tactical_record(path: Path, *, ticker: str) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    artifact = json.loads(path.read_text(encoding="utf-8"))
    return artifact.get("records", {}).get(ticker)


def _load_pan_case_study(retained_evidence_root: Path) -> Mapping[str, Any] | None:
    """Read PAN's exact retained real daily tactical records for 2026-09-08/09/10.

    These are already-retained real daily production artifacts (not reconstructed), the
    same evidence HISTORICAL_TACTICAL_REPLAY_EVIDENCE_FOUNDATION_V1 used for its PAN
    control. 09-08 is optional context for the persistence candidate; 09-09/09-10 are
    required for the control transition itself.
    """
    base = retained_evidence_root / "operations-review"
    day_08 = _load_tactical_record(base / "watchlist-tactical-entry-decision-v1-20260908" / "watchlist_tactical_entry_classifier_artifact.json", ticker="PAN")
    day_09 = _load_tactical_record(base / "watchlist-tactical-entry-decision-v1-20260909" / "watchlist_tactical_entry_classifier_artifact.json", ticker="PAN")
    day_10 = _load_tactical_record(base / "watchlist-tactical-entry-decision-v1-20260910" / "watchlist_tactical_entry_classifier_artifact.json", ticker="PAN")
    if day_09 is None or day_10 is None:
        return None
    return probe.pan_control_case_study(
        session_2026_09_08=day_08, session_2026_09_09=day_09, session_2026_09_10=day_10,
    )


def write_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True, help="Explicit local runtime root containing vn_stock.db.")
    parser.add_argument("--retained-evidence-root", type=Path, required=True, help="Root holding the retained PAN control operations-review evidence.")
    parser.add_argument("--start", default="2026-07-01", help="Earliest target session (inclusive).")
    parser.add_argument("--end", default="2026-08-25", help="Latest target session (inclusive).")
    parser.add_argument("--out", type=Path, required=True, help="Tracked artifact path in this checkout.")
    args = parser.parse_args(argv)

    pan_case_study = _load_pan_case_study(args.retained_evidence_root)
    artifact = probe.build_from_runtime(
        runtime_root=args.runtime_root, start=args.start, end=args.end, pan_case_study=pan_case_study,
    )
    write_artifact(args.out, artifact)
    print(json.dumps({
        "artifact_identity": artifact["artifact_identity"],
        "cohort_summary": artifact["cohort_summary"],
        "decision": artifact["decision"],
        "pan_case_study_available": pan_case_study is not None,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
