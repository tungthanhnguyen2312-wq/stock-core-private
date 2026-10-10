"""Owner-facing roadmap execution-state CLI.

Queries report current/next/blocked milestone state from
``docs/ROADMAP_STATE.json`` and cross-checks it against live, local Git/worktree
state. Queries never mutate files or Git. Explicit --continue-scope writes only
the current owner-authorized continuation, preserving its prior completion.
Explicit --admit-scope reconciles a current ACTIVE release or preserves a COMPLETE
predecessor, then admits one owner-directed scope with an empty queue. Neither starts runtime work.

    python tools/stocklookup_roadmap.py                    human-readable report
    python tools/stocklookup_roadmap.py --json              machine-readable report
    python tools/stocklookup_roadmap.py --check              preflight gate (exit 0 = ON_TRACK)
    python tools/stocklookup_roadmap.py --can-start ID        is milestone ID allowed to start now
"""
from __future__ import annotations

import argparse
import json
import re
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


def continuation_text(original: str, state: dict, mid: str) -> str:
    """Preserve the exact text of all historical milestones and other metadata."""
    milestone = next(m for m in state["milestones"] if m["milestone_id"] == mid)
    pattern = r'\{\s*"milestone_id":\s*' + re.escape(json.dumps(mid))
    start = re.search(pattern, original).start()
    _, length = json.JSONDecoder().raw_decode(original[start:])
    body = json.dumps(milestone, ensure_ascii=False, indent=2).replace("\n", "\n    ")
    original = original[:start] + body + original[start + length:]
    start = re.search(r'^  "current": ', original, re.MULTILINE).end()
    _, length = json.JSONDecoder().raw_decode(original[start:])
    body = json.dumps(state["current"], ensure_ascii=False, indent=2).replace("\n", "\n  ")
    return original[:start] + body + original[start + length:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-file", type=Path, default=res.DEFAULT_STATE_PATH)
    parser.add_argument("--repo", type=Path, default=ROOT, help="Git repository to cross-check against (default: this repository). Pass a nonexistent path to skip Git checks.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable report instead of the human-readable one.")
    parser.add_argument("--check", action="store_true", help="Preflight gate: print PASS/FAIL and exit non-zero on any FAIL-severity finding.")
    parser.add_argument("--can-start", metavar="MILESTONE_ID", help="Report whether MILESTONE_ID is allowed to start now.")
    parser.add_argument("--owner-override", action="store_true", help="With --can-start: allow starting a milestone that is not recorded NEXT (owner override). Never inferred automatically.")
    parser.add_argument("--continue-scope", metavar="MILESTONE_ID", help="Explicitly resume the current completed subset under an owner-authorized bounded scope expansion; preserve its completion record.")
    parser.add_argument("--scope-note", help="Exact owner directive and bounded scope; required for continuation or admission.")
    parser.add_argument("--admit-scope", metavar="MILESTONE_ID", help="Register and admit an explicitly owner-directed successor after reconciling a verified release.")
    parser.add_argument("--release-current-at", help="Exact verified live starting HEAD; release an ACTIVE current milestone or preserve an already COMPLETE predecessor.")
    args = parser.parse_args(argv)

    try:
        state = res.load_state(args.state_file)
    except res.RoadmapStateError as exc:
        print(f"ROADMAP_STATE_LOAD_FAILED: {exc}", file=sys.stderr)
        return 2

    repo = args.repo if args.repo.is_dir() else None

    if args.admit_scope:
        if (not args.owner_override or not args.scope_note or not args.release_current_at
                or args.continue_scope or args.can_start or repo is None):
            parser.error("admission requires owner override, scope note, repository and exact current release checkpoint")
        mid = args.admit_scope
        current = state.get("current") or {}
        prior_id = current.get("milestone")
        prior = next((m for m in state["milestones"] if m.get("milestone_id") == prior_id), None)
        if (prior is None or prior.get("state") not in {"ACTIVE", "COMPLETE"}
                or current.get("state") != prior.get("state")
                or state.get("queued_next") or any(m.get("milestone_id") == mid for m in state["milestones"])):
            parser.error("admission requires a current ACTIVE or COMPLETE milestone, empty queue and a new exact ID")
        ok, checkpoint = res.resolve_checkpoint(repo, args.release_current_at)
        if not ok or checkpoint != res.git_head(repo) or res.evaluate(state, repo=repo).overall != "ON_TRACK":
            parser.error("verified release must be exact live starting HEAD and roadmap must be ON_TRACK")
        release_active = prior["state"] == "ACTIVE"
        if release_active:
            prior.update(state="COMPLETE", checkpoint=checkpoint,
                         terminal_disposition="IMPLEMENTATION_RELEASED_NO_PRODUCTION_ACTIVATION")
            prior.setdefault("state_history", []).append("COMPLETE")
            prior["notes"] += " Verified release " + checkpoint + "; no production reclaim, activation or automatic successor."
        else:
            valid, prior_checkpoint = res.resolve_checkpoint(repo, prior.get("checkpoint"))
            if not valid or not res.git_is_ancestor(repo, prior_checkpoint, checkpoint):
                parser.error("completed predecessor checkpoint must be reachable from verified live HEAD")
        new = {"milestone_id": mid, "state": "DEFERRED", "starting_checkpoint": checkpoint,
               "candidate_branch": res.git_branch(repo), "dependencies": [prior_id], "unlocks": [],
               "owner_authorized": True, "owner_override": args.scope_note, "authority_effect": "NONE",
               "source_doc": "docs/" + mid.lower() + "_contract.md", "state_history": ["DEFERRED"],
               "checkpoint": None, "terminal_disposition": None, "notes": args.scope_note}
        state["milestones"].insert(0, new)
        allowed, reasons = res.can_start(state, mid, owner_override=True)
        if not allowed:
            parser.error("admission refused: " + ",".join(reasons))
        new["state"] = "ACTIVE"
        new["state_history"].append("ACTIVE")
        state["current"] = {"milestone": mid, "state": "ACTIVE"}
        if res.evaluate(state, repo=repo).overall != "ON_TRACK":
            parser.error("admitted state must remain ON_TRACK; no update written")
        original = args.state_file.read_text(encoding="utf-8")
        # Only the current pointer changes when the predecessor was already complete;
        # its original JSON bytes and completion checkpoint remain historical evidence.
        updated = continuation_text(original, state, prior_id) if release_active else original
        if not release_active:
            start = re.search(r'^  "current": ', updated, re.MULTILINE).end()
            _, length = json.JSONDecoder().raw_decode(updated[start:])
            body = json.dumps(state["current"], ensure_ascii=False, indent=2).replace("\n", "\n  ")
            updated = updated[:start] + body + updated[start + length:]
        body = json.dumps(new, ensure_ascii=False, indent=2).replace("\n", "\n    ")
        updated = updated.replace('"milestones": [\n', '"milestones": [\n    ' + body + ',\n', 1)
        args.state_file.write_bytes(updated.encode("utf-8"))
        print("OWNER_AUTHORIZED_SCOPE_ADMISSION:" + mid)
        return 0

    if args.continue_scope:
        mid = args.continue_scope
        if not args.owner_override or not args.scope_note or args.can_start:
            parser.error("--continue-scope requires --owner-override and --scope-note; cannot combine with --can-start")
        current = state.get("current") or {}
        milestone = next((m for m in state["milestones"] if m.get("milestone_id") == mid), None)
        if (current.get("milestone") != mid or current.get("state") != "COMPLETE"
                or milestone is None or milestone.get("state") != "COMPLETE"
                or state.get("queued_next")):
            parser.error("continuation requires the exact current COMPLETE subset and empty successor queue")
        report = res.evaluate(state, repo=repo)
        if report.overall != "ON_TRACK":
            parser.error("roadmap preflight must be ON_TRACK before scope continuation")
        checkpoint = milestone.get("checkpoint")
        if checkpoint == "HEAD" and repo is not None:
            ok, checkpoint = res.resolve_checkpoint(repo, checkpoint)
            if not ok:
                parser.error("completion checkpoint cannot be resolved")
        milestone.setdefault("scope_continuations", []).append({
            "prior_state": "COMPLETE", "prior_checkpoint": checkpoint,
            "prior_terminal_disposition": milestone.get("terminal_disposition"),
            "prior_owner_override": milestone.get("owner_override"),
            "prior_notes": milestone.get("notes"), "owner_scope_note": args.scope_note,
        })
        milestone["state"] = "ACTIVE"
        milestone["owner_override"] = {"allows_reopen": True, "directive": args.scope_note}
        milestone["checkpoint"] = None
        milestone["terminal_disposition"] = None
        milestone.setdefault("state_history", []).append("ACTIVE")
        milestone["notes"] = args.scope_note
        state["current"]["state"] = "ACTIVE"
        state["last_updated_checkpoint"] = "HEAD"
        if res.evaluate(state, repo=repo).overall != "ON_TRACK":
            parser.error("continued roadmap must remain ON_TRACK; no update written")
        original = args.state_file.read_text(encoding="utf-8")
        args.state_file.write_bytes(continuation_text(original, state, mid).encode("utf-8"))
        print("OWNER_AUTHORIZED_SCOPE_CONTINUATION:" + mid)
        return 0

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
