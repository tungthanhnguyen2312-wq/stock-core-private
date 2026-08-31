"""One bounded current-session Decision Workspace-to-durable-T0 case capture."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from durable_prospective_research_case_store import DurableProspectiveResearchCaseStore  # noqa: E402
from prospective_case_admission_policy import AdmissionPolicyError, apply_admission_policy, retain_admitted_cases  # noqa: E402
from prospective_decision_outcome_measurement import build_outcome_artifact, load_genuine_case_envelopes  # noqa: E402


def _load(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("INPUT_JSON_OBJECT_REQUIRED")
    return value


def _latest(evidence: dict) -> tuple[str, dict]:
    rows = evidence.get("completed_sessions") if "completed_sessions" in evidence else evidence.get("sessions")
    if not isinstance(rows, list): raise ValueError("COMPLETED_SESSION_EVIDENCE_REQUIRED")
    qualified = [row for row in rows if isinstance(row, dict) and isinstance(row.get("session"), str) and (row.get("completed_session_gate") or {}).get("completion_gate_status") == "READY"]
    if not qualified: raise AdmissionPolicyError("CURRENT_SESSION_ACQUISITION_BLOCKED")
    row = max(qualified, key=lambda item: item["session"])
    return row["session"], row


def run(*, completed_session_evidence: dict, workspace_projection: dict, price_evidence: dict, store_root: str | Path,
        admitted_at: str) -> dict:
    session, gate = _latest(completed_session_evidence)
    store = DurableProspectiveResearchCaseStore(store_root)
    admission = apply_admission_policy(workspace_projection, latest_qualified_completed_session=session,
                                       price_evidence=price_evidence, admitted_at=admitted_at, store=store)
    retention = retain_admitted_cases(admission, store)
    outcome = build_outcome_artifact(load_genuine_case_envelopes(store_root), [gate], evaluation_as_of_session=session)
    return {"contract_version": "current_session_prospective_case_capture/v1", "latest_qualified_completed_session": session,
            "session_resolution": {"method": "EXPLICIT_RETAINED_COMPLETED_SESSION_EVIDENCE", "working_date_identity": gate.get("completed_session_gate", {}).get("working_dates"), "qualification_state": "READY"},
            "admission": admission, "retention": retention, "outcome": outcome,
            "operator_status": "PASS" if not retention["errors"] else "PARTIAL_T0_RETENTION_FAILED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-session-evidence", required=True)
    parser.add_argument("--workspace-projection", required=True)
    parser.add_argument("--price-evidence", required=True)
    parser.add_argument("--store-root", required=True)
    parser.add_argument("--admitted-at", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = run(completed_session_evidence=_load(args.completed_session_evidence), workspace_projection=_load(args.workspace_projection),
                     price_evidence=_load(args.price_evidence), store_root=args.store_root, admitted_at=args.admitted_at)
    except AdmissionPolicyError as exc:
        result = {"contract_version": "current_session_prospective_case_capture/v1", "operator_status": str(exc)}
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output: Path(args.output).write_text(text, encoding="utf-8")
    else: print(text, end="")
