"""Owner-facing roadmap execution-state CLI.

Read-only: reports current/next/blocked milestone state from
``docs/ROADMAP_STATE.json`` and cross-checks it against live, local Git/worktree
state. Never mutates the roadmap file, Git, or any worktree.

    python tools/stocklookup_roadmap.py                    human-readable report
    python tools/stocklookup_roadmap.py --json              machine-readable report
    python tools/stocklookup_roadmap.py --check              preflight gate (exit 0 = ON_TRACK)
    python tools/stocklookup_roadmap.py --can-start ID        is milestone ID allowed to start now
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


def _print_human_report(report: res.RoadmapReport, *, repo: Path | None) -> None:
    state = report.state
    current = state.get("current") or {}
    counts = res.summary_counts(state)
    queued_next = list(state.get("queued_next") or [])
    lineage_head = state.get("implementation_lineage_head")
    resolved_lineage = lineage_head
    if repo is not None and lineage_head:
        ok, resolved = res.resolve_checkpoint(repo, lineage_head)
        if ok:
            resolved_lineage = resolved

    print("STOCK LOOKUP ROADMAP")
    print()
    print(f"Overall: {report.overall}")
    print()
    print("Current:")
    current_milestone = current.get("milestone")
    if current_milestone:
        print(f"  {current_milestone} ({current.get('state', 'UNKNOWN')})")
    else:
        print("  NONE")
    print()
    print("Next:")
    print(f"  {queued_next[0]}" if queued_next else "  NONE")
    print()
    print(f"Completed: {counts.get('COMPLETE', 0)}")
    print(f"Blocked: {counts.get('BLOCKED', 0)}")
    print(f"Deferred: {counts.get('DEFERRED', 0)}")
    print()
    print("Implementation lineage:")
    print(f"  {resolved_lineage}" + (f"  (recorded: {lineage_head})" if resolved_lineage != lineage_head else ""))
    print()
    print("DRIFT CHECK:")
    print(f"  {'PASS' if report.overall == 'ON_TRACK' else 'FAIL'}")
    print()
    print("Checks:")
    for category in res.CHECK_CATEGORIES:
        status = report.category_status(category)
        print(f"  {category:<30} {status}")
    print()
    blocked = state.get("blocked_capabilities") or []
    print("Blocked capabilities:")
    if not blocked:
        print("  (none recorded)")
    for entry in blocked:
        print(f"  - {entry.get('capability')}: {entry.get('state')}")
        reason = entry.get("reason")
        if reason:
            print(f"      {reason}")

    non_info = [f for f in report.findings if f.severity != res.INFO]
    if non_info:
        print()
        print("Findings:")
        for f in non_info:
            print(f"  [{f.severity}] {f.code}: {f.message}")


def _report_to_json(report: res.RoadmapReport, *, repo: Path | None) -> dict:
    lineage_head = report.state.get("implementation_lineage_head")
    resolved_lineage = lineage_head
    if repo is not None and lineage_head:
        ok, resolved = res.resolve_checkpoint(repo, lineage_head)
        if ok:
            resolved_lineage = resolved
    return {
        "schema_version": res.SCHEMA_VERSION,
        "overall": report.overall,
        "content_identity": report.content_identity,
        "current": report.state.get("current"),
        "queued_next": report.state.get("queued_next"),
        "summary_counts": res.summary_counts(report.state),
        "implementation_lineage_head": {"recorded": lineage_head, "resolved": resolved_lineage},
        "checks": {category: report.category_status(category) for category in res.CHECK_CATEGORIES},
        "blocked_capabilities": report.state.get("blocked_capabilities"),
        "findings": [
            {"code": f.code, "severity": f.severity, "category": f.category, "message": f.message, "milestone_id": f.milestone_id}
            for f in report.findings
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-file", type=Path, default=res.DEFAULT_STATE_PATH)
    parser.add_argument("--repo", type=Path, default=ROOT, help="Git repository to cross-check against (default: this repository). Pass a nonexistent path to skip Git checks.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable report instead of the human-readable one.")
    parser.add_argument("--check", action="store_true", help="Preflight gate: print PASS/FAIL and exit non-zero on any FAIL-severity finding.")
    parser.add_argument("--can-start", metavar="MILESTONE_ID", help="Report whether MILESTONE_ID is allowed to start now.")
    parser.add_argument("--owner-override", action="store_true", help="With --can-start: allow starting a milestone that is not recorded NEXT (owner override). Never inferred automatically.")
    args = parser.parse_args(argv)

    try:
        state = res.load_state(args.state_file)
    except res.RoadmapStateError as exc:
        print(f"ROADMAP_STATE_LOAD_FAILED: {exc}", file=sys.stderr)
        return 2

    repo = args.repo if args.repo.is_dir() else None

    if args.can_start:
        allowed, reasons = res.can_start(state, args.can_start, owner_override=args.owner_override)
        if args.json:
            print(json.dumps({"milestone_id": args.can_start, "allowed": allowed, "reasons": reasons}, indent=2, sort_keys=True))
        else:
            print("ALLOWED" if allowed else "BLOCKED")
            for reason in reasons:
                print(f"  - {reason}")
        return 0 if allowed else 1

    report = res.evaluate(state, repo=repo)

    if args.json:
        print(json.dumps(_report_to_json(report, repo=repo), indent=2, sort_keys=True))
    else:
        _print_human_report(report, repo=repo)

    if args.check:
        return 0 if report.overall == "ON_TRACK" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
