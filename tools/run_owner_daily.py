"""Safe, versioned owner workflow for Canonical Daily, AI Git handoff, and Action Center.

The desktop .cmd only calls the paired PowerShell presentation script. This module is
deliberately testable and contains the workflow gates. Its Action Center step may use the
existing optional local portfolio contract, but no private artifact reaches Git publication.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME = ROOT.parent / "dashboard-runtime"
DEFAULT_HANDOFF_REPO = ROOT.parent / "stocklookup-ai-handoffs"
DAILY_STATE_ALLOWLIST = ("config/daily_research_session_input_registry.json",)
SESSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class OwnerDailyError(RuntimeError):
    def __init__(self, step: str, reason: str, hint: str = "") -> None:
        super().__init__(reason)
        self.step, self.reason, self.hint = step, reason, hint


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", check=False)
    if result.returncode:
        raise OwnerDailyError("Repository preflight", "GIT_" + args[0].upper() + ":" +
                              (result.stderr.strip() or result.stdout.strip()),
                              "Resolve the Git error and run again.")
    return result.stdout.strip()


def _tracked_changes(root: Path) -> list[str]:
    return [line for line in _git(root, "status", "--porcelain", "--untracked-files=no").splitlines() if line]


def preflight_repository(root: Path, *, expected_name: str, expected_remote_fragment: str) -> dict[str, str]:
    """Synchronize a clean main checkout only by safe fast-forward; never discard work."""
    root = root.resolve()
    if root.name != expected_name or not (root / ".git").exists():
        raise OwnerDailyError("Repository preflight", "WRONG_REPOSITORY", f"Expected {expected_name} checkout.")
    remote = _git(root, "remote", "get-url", "origin")
    if expected_remote_fragment not in remote:
        raise OwnerDailyError("Repository preflight", "WRONG_ORIGIN", "Restore the configured private origin.")
    _git(root, "fetch", "origin")
    if _git(root, "branch", "--show-current") != "main":
        raise OwnerDailyError("Repository preflight", "BRANCH_IS_NOT_MAIN", "Switch to main without discarding work.")
    dirty = _tracked_changes(root)
    if dirty:
        raise OwnerDailyError("Repository preflight", "UNEXPECTED_TRACKED_CHANGES:" + ";".join(dirty),
                              "Commit, stash, or otherwise resolve the tracked work before Daily.")
    head, remote_head = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "origin/main")
    if head == remote_head:
        return {"head": head, "status": "UP_TO_DATE"}
    # --is-ancestor uses its nonzero exit code as a relationship result, not a Git failure.
    is_behind = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", head, remote_head,
                                ], capture_output=True, check=False).returncode == 0
    is_ahead = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", remote_head, head,
                               ], capture_output=True, check=False).returncode == 0
    if not is_behind or is_ahead:
        raise OwnerDailyError("Repository preflight", "UNSAFE_GIT_DIVERGENCE",
                              "Integrate main safely before running Daily; no reset or rebase was attempted.")
    _git(root, "pull", "--ff-only", "origin", "main")
    return {"head": _git(root, "rev-parse", "HEAD"), "status": "FAST_FORWARDED"}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OwnerDailyError("Daily completion verification", "INVALID_JSON:" + str(path),
                              "Retain a valid canonical completion artifact.") from exc
    if not isinstance(value, dict):
        raise OwnerDailyError("Daily completion verification", "JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _operation_records(root: Path) -> list[tuple[dict[str, Any], Path]]:
    base = root / "operations-review" / "canonical-daily-operation-v1"
    return [(_load(path), path) for path in base.glob("*/*/daily_operation_record.json")]


def verify_daily_completion(root: Path, runtime_root: Path, *, session: str | None = None) -> dict[str, Any]:
    registry = _load(root / DAILY_STATE_ALLOWLIST[0])
    records = [(record, path) for record, path in _operation_records(root)
               if session is None or record.get("session") == session]
    if not records:
        raise OwnerDailyError("Daily completion verification", "CANONICAL_COMPLETION_RECORD_NOT_FOUND")
    record, path = max(records, key=lambda row: row[1].stat().st_mtime)
    resolved = str(record.get("session") or "")
    completed = (registry.get("completed_sessions") or {}).get(resolved) or {}
    required = {
        "daily_operation_state": "LOCAL_COMPLETE", "daily_producer_status": "COMPLETED",
        "runtime_release_status": "READY", "trusted_subset_status": "READY",
    }
    bad = [f"{key}={record.get(key)!r}" for key, expected in required.items() if record.get(key) != expected]
    if (not SESSION_RE.fullmatch(resolved) or completed.get("status") != "COMPLETED_RETAINED_EVIDENCE"
            or completed.get("trading_day_valid") is not True
            or str((record.get("acquisition") or {}).get("resolved_completed_session") or "") != resolved
            or not record.get("daily_producer_run_identity") or not record.get("daily_producer_operation_identity")
            or not record.get("operation_identity") or bad):
        raise OwnerDailyError("Daily completion verification", "CANONICAL_GATE_FAILED:" + ";".join(bad),
                              "Do not publish until canonical Daily records all READY/COMPLETED gates.")
    runtime_manifest = runtime_root / "bundle_manifest.json"
    if not runtime_manifest.is_file():
        raise OwnerDailyError("Daily completion verification", "RUNTIME_RELEASE_MANIFEST_MISSING")
    source_candidates = list((root / "operations-review" / "daily-research-session-operations-v1" / resolved).glob("*/ai_research_bundle_manifest.json"))
    operation_id = record["daily_producer_operation_identity"]
    source_candidates = [p for p in source_candidates if _load(p).get("operation_identity") == operation_id]
    if len(source_candidates) != 1:
        raise OwnerDailyError("Daily completion verification", "AI_HANDOFF_OPERATION_AMBIGUOUS_OR_MISSING")
    return {"session": resolved, "record": record, "record_path": path,
            "source": source_candidates[0].parent, "operation_id": operation_id}


def commit_daily_state(root: Path, session: str) -> dict[str, str]:
    changed = _tracked_changes(root)
    if not changed:
        return {"status": "NO_CHANGE", "sha": _git(root, "rev-parse", "HEAD")}
    paths = {line[3:].replace("\\", "/") for line in changed}
    unexpected = sorted(paths.difference(DAILY_STATE_ALLOWLIST))
    if unexpected:
        raise OwnerDailyError("Producer state publication", "UNEXPECTED_POST_DAILY_DIFF:" + ",".join(unexpected),
                              "Only the governed Daily registry may change before this commit.")
    registry = _load(root / DAILY_STATE_ALLOWLIST[0])
    row = (registry.get("completed_sessions") or {}).get(session) or {}
    if row.get("status") != "COMPLETED_RETAINED_EVIDENCE":
        raise OwnerDailyError("Producer state publication", "REGISTRY_SESSION_NOT_COMPLETED")
    _git(root, "add", "--", *DAILY_STATE_ALLOWLIST)
    _git(root, "commit", "-m", f"daily: retain {session} completed session")
    _git(root, "push", "origin", "main")
    return {"status": "COMMITTED", "sha": _git(root, "rev-parse", "HEAD")}


def _run_daily(root: Path, runtime_root: Path) -> None:
    result = subprocess.run([sys.executable, "-u", "daily_analysis_pipeline.py", "--runtime-root", str(runtime_root),
                             "--canonical-post-close"], cwd=root, check=False)
    if result.returncode:
        raise OwnerDailyError("Canonical Daily", f"CANONICAL_DAILY_EXIT_{result.returncode}",
                              "Read the log; no state or AI publication was attempted.")


def publish_ai_handoff(root: Path, handoff_repo: Path, completion: Mapping[str, Any]) -> dict[str, Any]:
    from ai_handoff_publication import publish, verify_remote_publication
    preflight_repository(handoff_repo, expected_name="stocklookup-ai-handoffs", expected_remote_fragment="stocklookup-ai-handoffs")
    source = Path(completion["source"])
    needed = ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json")
    if any(not (source / name).is_file() for name in needed):
        raise OwnerDailyError("AI handoff build", "AI_HANDOFF_REQUIRED_FILE_MISSING")
    daily_brief = source / "daily_integrated_decision_brief_artifact.json"
    previous = None
    published = publish(handoff_repo, source, str(completion["session"]),
                        producer_checkpoint=_git(root, "rev-parse", "HEAD"), push=True,
                        daily_integrated_decision_brief=daily_brief if daily_brief.is_file() else None,
                        previous=previous)
    return {"publication": published, "remote": verify_remote_publication(handoff_repo, published)}


def materialize_action_center(root: Path, session: str) -> dict[str, Any]:
    """Use the released local-only Action Center; it never enters either Git publication path."""
    import personal_investment_decision_action_center as action_center
    try:
        artifact = action_center.evaluate_from_retained_artifacts(
            repo_root=root, session=session, requested_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        json_path = action_center.write_private_artifact(artifact)
        markdown_path = action_center.write_markdown(artifact)
    except Exception as exc:  # The core Daily and AI handoff have already passed at this point.
        return {"status": "PARTIAL", "reason": f"ACTION_CENTER_MATERIALIZATION_FAILED:{type(exc).__name__}:{exc}"}
    return {
        "status": "READY", "session": artifact.get("session"),
        "portfolio_status": (artifact.get("portfolio") or {}).get("status"),
        "json_path": str(json_path), "view_path": str(markdown_path),
        "identity": artifact.get("artifact_identity"),
    }


def open_action_center_view(path: str) -> dict[str, str]:
    """Opening the local Markdown is convenience only, never a Daily data gate."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows owner launcher contract.
    except Exception as exc:
        return {"status": "READY_VIEW_OPEN_FAILED", "reason": f"VIEW_OPEN_FAILED:{type(exc).__name__}:{exc}"}
    return {"status": "READY"}


def run_workflow(*, root: Path = ROOT, runtime_root: Path = DEFAULT_RUNTIME,
                 handoff_repo: Path = DEFAULT_HANDOFF_REPO, replay_completed_session: str | None = None) -> dict[str, Any]:
    root, runtime_root, handoff_repo = root.resolve(), runtime_root.resolve(), handoff_repo.resolve()
    producer = preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private")
    if replay_completed_session:
        completion = verify_daily_completion(root, runtime_root, session=replay_completed_session)
        daily_status = "ALREADY_COMPLETED / REUSED"
    else:
        _run_daily(root, runtime_root)
        completion = verify_daily_completion(root, runtime_root)
        daily_status = "COMPLETED"
    producer_state = commit_daily_state(root, str(completion["session"]))
    handoff = publish_ai_handoff(root, handoff_repo, completion)
    action_center = materialize_action_center(root, str(completion["session"]))
    if action_center["status"] == "PARTIAL":
        return {"status": "PARTIAL", "session": completion["session"], "daily_status": daily_status,
                "producer_preflight": producer, "producer_state": producer_state,
                "ai_handoff": handoff, "action_center": action_center}
    action_center["view_open"] = open_action_center_view(str(action_center["view_path"]))
    return {"status": "PASS", "session": completion["session"], "daily_status": daily_status,
            "producer_preflight": producer, "producer_state": producer_state,
            "ai_handoff": handoff, "action_center": action_center}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--handoff-repo", type=Path, default=DEFAULT_HANDOFF_REPO)
    parser.add_argument("--replay-completed-session", default=None, help="Validate/publish an already completed session without acquisition.")
    parser.add_argument("--result-path", type=Path, required=True)
    args = parser.parse_args(argv)
    result: dict[str, Any]
    code = 0
    try:
        result = run_workflow(runtime_root=args.runtime_root, handoff_repo=args.handoff_repo,
                              replay_completed_session=args.replay_completed_session)
        if result["status"] == "PARTIAL":
            code = 3
    except OwnerDailyError as exc:
        code = 1
        result = {"status": "FAILED", "failed_step": exc.step, "reason": exc.reason, "hint": exc.hint}
    args.result_path.parent.mkdir(parents=True, exist_ok=True)
    args.result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("OWNER_DAILY_RESULT=" + str(args.result_path))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
