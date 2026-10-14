"""Compact resume handoff from the native roadmap query.

Ordinary mode does not open docs/STATE.md, docs/DECISIONS.md, or docs/ROADMAP.md.
``--historical`` is the explicit request to read those preserved files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import roadmap_execution_state as res  # noqa: E402


def _historical_handoff() -> dict:
    """Explicit history read. This is not the ordinary bootstrap path."""
    state = ROOT / "docs" / "STATE.md"
    roadmap = ROOT / "docs" / "ROADMAP.md"

    def line(rows: list[str], prefix: str) -> str:
        for row in rows:
            if row.startswith(prefix):
                return row.split(":", 1)[1].strip()
        raise ValueError(f"missing_canonical_state:{prefix}")

    roadmap_text = roadmap.read_text(encoding="utf-8")
    state_rows = state.read_text(encoding="utf-8").splitlines()
    return {
        "historical_files_read": True,
        "active_phase": line(state_rows, "- Active phase"),
        "active_milestone": line(state_rows, "- Active milestone"),
        "production_state": line(state_rows, "- Production state"),
        "p0_exit_gates": [row[2:] for row in roadmap_text.splitlines() if row.startswith("- Exit gates:")],
    }


def build_handoff(*, historical: bool = False, repo: Path | None = None,
                  state_file: Path | None = None, lane_id: str | None = None) -> dict:
    if historical:
        return _historical_handoff()
    repo = repo or ROOT
    state_path = state_file or repo / "docs" / "ROADMAP_STATE.json"
    try:
        state = res.load_state(state_path)
    except res.RoadmapStateError:
        state = {}
    current = state.get("current") or {}
    milestone_id = current.get("milestone")
    milestone = next((item for item in state.get("milestones") or [] if item.get("milestone_id") == milestone_id), {})
    head = res.git_head(repo)
    branch = res.git_branch(repo)
    if head is None:
        tracked_status = "UNKNOWN"
        dirty_count: int | str = "UNKNOWN"
        report_overall = "UNKNOWN"
        git_verification = res.GIT_VERIFICATION_UNAVAILABLE
    else:
        dirty = res.git_dirty_tracked(repo)
        tracked_status = "DIRTY" if dirty else "CLEAN"
        dirty_count = len(dirty)
        # A resume summary is not another repository-wide preflight. Preserve the
        # native GIT_NOT_CHECKED verdict; the explicit CLI below supplies live proof.
        report = res.evaluate(state, repo=None) if state else None
        report_overall = report.overall if report else "UNKNOWN"
        git_verification = report.git_verification if report else res.GIT_VERIFICATION_UNAVAILABLE
    notes = milestone.get("notes") if isinstance(milestone.get("notes"), str) and milestone.get("notes") else "UNKNOWN"
    lane_scope = None
    if lane_id is not None:
        lane = res.lane_by_id(state, lane_id)
        live = res.check_lane(state, lane_id, repo=repo)
        if live["errors"]:
            raise res.RoadmapStateError(";".join(live["errors"]))
        lane_scope = {key: lane.get(key) for key in (
            "milestone_id", "responsible_agent", "state", "worktree", "branch", "base_sha",
            "checkpoint", "domain", "allowed_paths", "shared_paths", "required_checks")}
        lane_scope.update(scope_check_errors=live["errors"], runtime_authorized=False)
    return {
        "historical_files_read": False,
        "repo": str(repo),
        "branch": branch or ("DETACHED" if head else "UNKNOWN"),
        "producer_head": head or "UNKNOWN",
        "worktree_tracked_status": tracked_status,
        "tracked_dirty_count": dirty_count,
        "native_milestone": milestone_id or "UNKNOWN",
        "native_milestone_state": current.get("state") or "UNKNOWN",
        "overall": report_overall,
        "git_verification": git_verification,
        "implementation_lineage_head": state.get("implementation_lineage_head", "UNKNOWN"),
        "queued_next": list(state.get("queued_next") or []),
        "intended_next_action": notes,
        "pending_tests": list(res.LOCAL_FAST),
        "hosted_ci": "UNKNOWN",
        "owner_gates": {
            "owner_authorized": milestone.get("owner_authorized", "UNKNOWN"),
            "authority_effect": milestone.get("authority_effect", "UNKNOWN"),
            "exact_head_merge": "REQUIRED",
        },
        "facts_not_checked": ["consumer_head", "dashboard_head", "hosted_ci", "disk_free", "untracked_files",
                              "native_git_checkpoints", "other_lane_heads"],
        "coordinator_state_file": str(state_path),
        "coordinator_revision": (state.get("development_control") or {}).get("revision"),
        "lane_scope": lane_scope,
        "native_preflight_argv": ["python", "tools/stocklookup_roadmap.py", "--repo", str(repo),
                                  "--state-file", str(state_path), "--check", "--json"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", action="store_true", help="Read preserved STATE.md and ROADMAP.md. Not the ordinary path.")
    parser.add_argument("--repo", type=Path, help="Registered source worktree to summarize.")
    parser.add_argument("--state-file", type=Path, help="Exact Owner-designated coordinator state; never infer a copied lane registry.")
    parser.add_argument("--lane", help="Exact native lane ID; check only that lane's live scope.")
    args = parser.parse_args(argv)
    if args.historical and (args.state_file or args.lane):
        parser.error("historical handoff cannot supply lane admission")
    print(json.dumps(build_handoff(historical=args.historical, repo=args.repo,
                                  state_file=args.state_file, lane_id=args.lane), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
