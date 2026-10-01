"""Materialize the deterministic, read-only empirical setup outcome calibration artifact.

Never runs Daily, never acquires provider data, never reconstructs a T0 decision that was not
genuinely retained. Prints only counts/identities unless --output/--evidence-dir is given.
"""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from unittest.mock import patch
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import empirical_setup_outcome_calibration as calibration
import prospective_decision_outcome_feedback as feedback
import prospective_decision_retention as retention
from empirical_setup_outcome_calibration import build_calibration_artifact, public_console_summary  # noqa: E402


def _write_immutable(path: Path, value: object) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"IMMUTABLE_ARTIFACT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _report(artifact: dict) -> str:
    lines = [
        "# Empirical Setup Outcome Calibration V1",
        "",
        "Deterministic, prospective-only calibration over the retained corpus. Research policy",
        "thresholds gate presentation; missing future depth is PENDING/INSUFFICIENT, never fabricated.",
        "",
        f"- T0 observations: {artifact['observation_count']}",
        f"- Distinct T0 sessions: {artifact['t0_session_count']}",
        f"- Comparable cohorts (all horizons): {artifact['cohort_count']}",
        f"- Cohorts reaching CALIBRATED_RESEARCH: {artifact['calibrated_research_cohort_count']}",
        "",
        "## Adequacy state counts by horizon",
        "",
    ]
    for horizon, counts in artifact["adequacy_state_counts_by_horizon"].items():
        lines.append(f"- {horizon}: {counts}")
    lines.append("")
    return "\n".join(lines)


def _source_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def retained_acceptance(root, *, baseline_inventory=None, baseline_feedback=None):
    """Read-only acceptance over the existing factory, with original-byte and replay checks.

    Inventory patterns remain owned by the existing bounded discoverers. No recursive scan,
    runtime write, acquisition, or alternate outcome engine is introduced here.
    """
    root = Path(root).resolve()
    source_hashes = {}
    baseline = json.loads(Path(baseline_inventory).read_text(encoding="utf-8")) if baseline_inventory else {}
    for relative, expected in baseline.get("source_hashes", {}).items():
        path = (root / relative).resolve()
        path.relative_to(root)
        digest = _source_digest(path)
        if digest != expected:
            raise ValueError(f"BASELINE_SOURCE_BYTES_CHANGED:{relative}")
        source_hashes[relative] = digest

    def tracked(reader):
        def read(path):
            path = Path(path).resolve()
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                if relative not in source_hashes:
                    source_hashes[relative] = _source_digest(path)
            return reader(path)
        return read

    context = {}
    with patch.object(retention, "_load", tracked(retention._load)), patch.object(feedback, "_load_json", tracked(feedback._load_json)):
        retained = feedback.build_feedback_artifact(root, resolved_context=context)
    artifact = build_calibration_artifact(feedback_artifact=retained, **context)
    replay = build_calibration_artifact(feedback_artifact={**retained, "feedback_records": list(reversed(retained["feedback_records"]))}, **context)
    if replay["artifact_identity"] != artifact["artifact_identity"]:
        raise ValueError("RETAINED_REPLAY_IDENTITY_CHANGED")
    del replay
    changed = [name for name, digest in source_hashes.items() if _source_digest(root / name) != digest]
    if changed:
        raise ValueError(f"RETAINED_SOURCE_MUTATION:{changed}")
    comparison = None
    if baseline_feedback:
        prior = json.loads(Path(baseline_feedback).read_text(encoding="utf-8"))
        key = lambda r: (r["decision_session"], r["ticker"], r["decision_identity"])
        before = {key(r): r for r in prior["feedback_records"]}
        after = {key(r): r for r in retained["feedback_records"]}
        if before.keys() != after.keys():
            raise ValueError("GENUINE_T0_CASE_SET_CHANGED")
        posture_changes = sum(before[k]["research_action_posture"] != after[k]["research_action_posture"] for k in before)
        if posture_changes:
            raise ValueError("IMMUTABLE_T0_POSTURE_CHANGED")
        deltas = {}
        for count in (1, 3, 5, 10, 20):
            field = f"forward_close_return_{count}"
            transitions = Counter()
            return_changes = 0
            for k in before:
                b, a = before[k]["forward_outcomes"]["horizons"][field], after[k]["forward_outcomes"]["horizons"][field]
                transitions[b["status"] + " -> " + a["status"]] += 1
                return_changes += b.get("return") != a.get("return")
            deltas[f"T{count}"] = {"status_transitions": dict(sorted(transitions.items())), "return_value_changes": return_changes}
        comparison = {"same_genuine_t0_case_set": True, "decision_identity_changes": 0, "posture_changes": 0,
            "outcome_deltas": deltas, "explanations": ["ONE_SHARED_GOVERNED_COMPLETED_SESSION_CHAIN_FOR_LEGACY_AND_IMMUTABLE_CASES", "MISSING_OR_INVALID_T0_CLOSE_DISTINGUISHED_BEFORE_PENDING_DEPTH", "FIXED_T0_CONDITION_AND_PRICE_BASIS_FITNESS_REQUIRED", "UNKNOWN_T0_POLICY_VERSIONS_PARTITIONED_WITHOUT_BACKFILL"],
            "before_horizon_coverage": baseline.get("horizon_coverage"), "before_sample_adequacy": baseline.get("sample_adequacy"),
            "before_qualified_denominator_numeric_only": baseline.get("r_denominator"), "unexplained_t0_changes": 0}
    eligible = artifact["calibration_eligibility_distribution"].get(calibration.CALIBRATION_REVIEW_ELIGIBLE, 0)
    report = {"contract_version": "r6_prospective_learning_retained_acceptance/v1",
        "disposition": "CALIBRATION_CAPABILITY_COMPLETE" if eligible else "CALIBRATION_CAPABILITY_COMPLETE / EVIDENCE_ACCUMULATION_PENDING",
        "stack_base": "397c05cf6e47d4bdc5a0a471102dfcb8ac383956", "inventory": artifact["retained_corpus_inventory"],
        "cohort_summary": public_console_summary(artifact), "sample_adequacy_policy": artifact["sample_adequacy_policy"],
        "policy_candidate_dispositions": artifact["policy_calibration_candidates"]["disposition_distribution"],
        "calibration_review_eligible_cohort_count": eligible,
        "human_review_candidate_count": artifact["policy_calibration_candidates"]["human_review_candidate_count"],
        "accumulation_gate": "NEW_IMMUTABLE_T0_WITH_KNOWN_POLICY_AND_FEATURE_VERSIONS; 50_MATURE_OBSERVATIONS_FROM_10_DISTINCT_T0_SESSIONS_PER_COMPARABLE_HORIZON; QUALIFIED_PRICE_BASIS; PREDECLARED_GOVERNED_REVIEW_RULE",
        "source_hashes": dict(sorted(source_hashes.items())), "source_file_count": len(source_hashes),
        "implementation_source_sha256": {name: _source_digest(ROOT / name) for name in ("empirical_setup_outcome_calibration.py", "prospective_decision_outcome_feedback.py", "prospective_decision_outcome_measurement.py", "prospective_decision_retention.py", "integrated_decision_prospective_feedback.py", "integrated_investment_decision_product.py", "tools/run_empirical_setup_outcome_calibration.py")},
        "mutation_check": {"changed_source_files": [], "unchanged": True, "baseline_hashes_unchanged": True},
        "deterministic_replay": {"reversed_input_order_identity_equal": True, "artifact_identity": artifact["artifact_identity"]},
        "before_after": comparison, "authority_effect": "NONE", "automatic_policy_change": False}
    return artifact, report


def run(*, root: str | Path = ROOT, output: str | Path | None = None, evidence_dir: str | Path | None = None, acceptance_output: str | Path | None = None, baseline_inventory=None, baseline_feedback=None) -> dict:
    if acceptance_output is not None:
        artifact, acceptance = retained_acceptance(root, baseline_inventory=baseline_inventory, baseline_feedback=baseline_feedback)
        _write_immutable(Path(acceptance_output), acceptance)
    else:
        artifact = build_calibration_artifact(root=str(root))
    if output is not None:
        _write_immutable(Path(output), artifact)
    if evidence_dir is not None:
        destination = Path(evidence_dir)
        _write_immutable(destination / "empirical_setup_outcome_calibration_artifact.json", artifact)
        _write_immutable(destination / "cohorts.json", {"cohorts": artifact["cohorts"]})
        _write_immutable(destination / "coverage_summary.json", public_console_summary(artifact))
        report = _report(artifact)
        report_path = destination / "REPORT.md"
        if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
            raise ValueError(f"IMMUTABLE_ARTIFACT_CONFLICT:{report_path}")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if not report_path.exists():
            report_path.write_text(report, encoding="utf-8")
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="Repository/artifact root to read; never fetched or mutated.")
    parser.add_argument("--output", help="Optional immutable full calibration artifact path.")
    parser.add_argument("--evidence-dir", help="Optional immutable evidence-package directory.")
    parser.add_argument("--acceptance-output", help="Portable source-hash, mutation and deterministic replay report.")
    parser.add_argument("--baseline-inventory", help="Optional pre-change retained inventory, with source hashes.")
    parser.add_argument("--baseline-feedback", help="Optional pre-change feedback for immutable T0 and outcome comparison.")
    args = parser.parse_args()
    result = run(root=args.root, output=args.output, evidence_dir=args.evidence_dir, acceptance_output=args.acceptance_output, baseline_inventory=args.baseline_inventory, baseline_feedback=args.baseline_feedback)
    if args.output is None and args.evidence_dir is None:
        print(json.dumps(public_console_summary(result), ensure_ascii=False, indent=2, sort_keys=True))
