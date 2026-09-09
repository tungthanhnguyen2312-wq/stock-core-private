"""Materialize the deterministic, read-only empirical setup outcome calibration artifact.

Never runs Daily, never acquires provider data, never reconstructs a T0 decision that was not
genuinely retained. Prints only counts/identities unless --output/--evidence-dir is given.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def run(*, root: str | Path = ROOT, output: str | Path | None = None, evidence_dir: str | Path | None = None) -> dict:
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
    args = parser.parse_args()
    result = run(root=args.root, output=args.output, evidence_dir=args.evidence_dir)
    if args.output is None and args.evidence_dir is None:
        print(json.dumps(public_console_summary(result), ensure_ascii=False, indent=2, sort_keys=True))
