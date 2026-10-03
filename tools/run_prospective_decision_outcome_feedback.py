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


def run_streaming(*, root: str | Path, output: str | Path, result: str | Path | None = None,
                  status: str | Path | None = None, **kwargs) -> dict:
    from feedback_publication_lock import publication_locks
    if status is None:
        # Legacy direct callers used --result as the shared status. Coordinate
        # that pointer too; production explicitly supplies separate attempt IPC.
        status, result = result, None
    # The attempt-local IPC file is not a shared pointer. Hold both target and
    # shared status leases through COMPLETE and status publication.
    with publication_locks(output, status):
        return _run_streaming(root=root, output=output, result=result, status=status, **kwargs)


def _run_streaming(*, root: str | Path, output: str | Path, result: str | Path | None = None,
                  status: str | Path | None = None, state_root: str | Path | None = None,
                  prior_result: str | Path | None = None) -> dict:
    """Resource-bounded builder: streams every source, publishes atomically, returns a small status (never the artifact)."""
    import traceback
    import feedback_resource_guard as guard
    import prospective_feedback_streaming as streaming

    def finish(payload: dict, code: int) -> int:
        payload.setdefault("peak_memory_bytes", guard.peak_memory_bytes())
        payload.setdefault("path", str(output))
        guard.write_child_result(result, payload)
        if status is not None:
            # A failed/conflicting attempt cannot replace a valid COMPLETE pointer.
            prior = guard._read_small_json(Path(status)) or {}
            if code == guard.EXIT_OK or prior.get("status") != "COMPLETED":
                guard.write_child_result(status, payload)
        return code

    prior_summary = None
    if prior_result is not None:
        try:
            prior_summary = (json.loads(Path(prior_result).read_text(encoding="utf-8")) or {}).get("inputs_summary")
        except (OSError, ValueError):
            prior_summary = None
    try:
        built = streaming.build_streaming_feedback(root, output, state_root=state_root, prior_summary=prior_summary)
        payload = {"status": "COMPLETED", **{k: v for k, v in built.items() if k != "contract_version"},
                   "contract_version": built["contract_version"]}
        return {"exit": finish(payload, guard.EXIT_OK), "payload": payload}
    except MemoryError:
        payload = {"status": "RESOURCE_UNAVAILABLE", "reason_code": guard.RESOURCE_MEMORY_LIMIT}
        return {"exit": finish(payload, guard.EXIT_RESOURCE_MEMORY), "payload": payload}
    except streaming.FeedbackStreamError as exc:
        code = {streaming.REASON_SOURCE_INTEGRITY: guard.EXIT_SOURCE_INTEGRITY,
                streaming.REASON_IMMUTABLE_CONFLICT: guard.EXIT_IMMUTABLE_CONFLICT}.get(exc.code, guard.EXIT_COMPUTATION_ERROR)
        payload = {"status": "FAILED", "reason_code": exc.code, "detail": str(exc)[:500]}
        return {"exit": finish(payload, code), "payload": payload}
    except OSError as exc:
        import errno
        if exc.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", -1)):
            payload = {"status": "RESOURCE_UNAVAILABLE", "reason_code": guard.RESOURCE_DISK, "detail": str(exc)[:300]}
            return {"exit": finish(payload, guard.EXIT_RESOURCE_DISK), "payload": payload}
        payload = {"status": "FAILED", "reason_code": guard.COMPUTATION_ERROR, "detail": f"{type(exc).__name__}:{exc}"[:500]}
        return {"exit": finish(payload, guard.EXIT_COMPUTATION_ERROR), "payload": payload}
    except Exception as exc:  # noqa: BLE001 -- anything else is a defect, reported as such, never as "no evidence"
        payload = {"status": "FAILED", "reason_code": guard.COMPUTATION_ERROR,
                   "detail": f"{type(exc).__name__}:{exc}"[:500], "traceback_tail": traceback.format_exc()[-1500:]}
        return {"exit": finish(payload, guard.EXIT_COMPUTATION_ERROR), "payload": payload}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="Repository/artifact root to read; never fetched or mutated.")
    parser.add_argument("--output", help="Immutable feedback artifact path (streamed, resource-bounded).")
    parser.add_argument("--evidence-dir", help="Optional immutable evidence-package directory (legacy in-memory builder).")
    parser.add_argument("--legacy-in-memory", action="store_true", help="Use the original in-memory builder (parity / small corpora only).")
    parser.add_argument("--result", help="Small JSON status sidecar written by the child for the parent.")
    parser.add_argument("--status", help="Shared status pointer, coordinated with immutable publication.")
    parser.add_argument("--state-root", help="Where derived caches/receipts live (default: --root).")
    parser.add_argument("--prior-result", help="Status sidecar of the earlier call, to report FEEDBACK_CALL_RELATION.")
    args = parser.parse_args()
    if args.output is not None and args.evidence_dir is None and not args.legacy_in_memory:
        outcome = run_streaming(root=args.root, output=args.output, result=args.result, status=args.status,
                                state_root=args.state_root, prior_result=args.prior_result)
        sys.exit(outcome["exit"])
    result = run(root=args.root, output=args.output, evidence_dir=args.evidence_dir)
    if args.output is None and args.evidence_dir is None:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
