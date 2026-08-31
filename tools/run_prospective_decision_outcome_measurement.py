"""Run one bounded, deterministic prospective-outcome roll-forward.

Both inputs are explicit.  The runner never creates cases, fetches data, polls,
or infers a completed session from a calendar date.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prospective_decision_outcome_measurement import (  # noqa: E402
    build_outcome_artifact,
    load_genuine_case_envelopes,
    prospective_outcome_context,
)


def _load_sessions(path: str | Path | None) -> list[dict]:
    if path is None:
        return []
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("completed_sessions")
    if not isinstance(value, list):
        raise ValueError("COMPLETED_SESSION_EVIDENCE_MUST_BE_A_LIST")
    return value


def run(*, case_store_root: str | Path | None, completed_session_evidence: str | Path | None = None,
        evaluation_as_of_session: str | None = None) -> dict:
    envelopes = load_genuine_case_envelopes(case_store_root)
    artifact = build_outcome_artifact(envelopes, _load_sessions(completed_session_evidence),
                                      evaluation_as_of_session=evaluation_as_of_session)
    artifact["prospective_outcome_context"] = [prospective_outcome_context(artifact, row["case_id"])
                                                for row in artifact["outcomes"]]
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-store-root", help="Explicit durable prospective-case store. Missing means zero real cases.")
    parser.add_argument("--completed-session-evidence", help="JSON list/object of already-retained completed sessions.")
    parser.add_argument("--evaluation-as-of-session")
    parser.add_argument("--output", help="Optional explicit output path; no default artifact path is used.")
    args = parser.parse_args()
    result = run(case_store_root=args.case_store_root, completed_session_evidence=args.completed_session_evidence,
                 evaluation_as_of_session=args.evaluation_as_of_session)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
