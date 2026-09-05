"""Materialize retained-only prospective decision feedback without acquisition or policy mutation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prospective_decision_outcome_feedback import build_feedback_artifact, evidence_views  # noqa: E402


def _write_immutable(path: Path, value: object) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"IMMUTABLE_ARTIFACT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _report(artifact: dict) -> str:
    corpus = artifact["prospective_corpus"]
    coverage = artifact["forward_outcome_coverage"]["horizons"]
    return "\n".join([
        "# Prospective Decision Outcome Feedback & Policy Diagnostics V1",
        "",
        "`PARTIAL_BY_EVIDENCE`: retained-only downstream research diagnostics; no policy mutation.",
        "",
        f"- Genuine decision artifacts: {corpus['genuine_artifact_count']}",
        f"- Genuine decisions: {corpus['genuine_decision_count']}",
        f"- Qualified sessions: {', '.join(corpus['unique_sessions']) or 'none'}",
        f"- T+1 coverage: {coverage.get('forward_close_return_1', {})}",
        f"- T+5 coverage: {coverage.get('forward_close_return_5', {})}",
        "- Close excursion fields are `CLOSE_MFE` / `CLOSE_MAE`, never intraday MFE/MAE.",
        "- Feedback is downstream only; current daily decisions are not read or changed by this artifact.",
        "",
    ])


def run(*, root: str | Path = ROOT, output: str | Path | None = None, evidence_dir: str | Path | None = None) -> dict:
    artifact = build_feedback_artifact(root)
    if output is not None:
        _write_immutable(Path(output), artifact)
    if evidence_dir is not None:
        destination = Path(evidence_dir)
        _write_immutable(destination / "prospective_decision_feedback_artifact.json", artifact)
        for name, view in evidence_views(artifact).items():
            _write_immutable(destination / name, view)
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
    parser.add_argument("--output", help="Optional immutable feedback artifact path.")
    parser.add_argument("--evidence-dir", help="Optional immutable evidence-package directory.")
    args = parser.parse_args()
    result = run(root=args.root, output=args.output, evidence_dir=args.evidence_dir)
    if args.output is None and args.evidence_dir is None:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
