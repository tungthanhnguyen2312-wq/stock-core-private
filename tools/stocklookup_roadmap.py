"""Owner-facing roadmap execution-state CLI.

Queries report current/next/blocked milestone state from
``docs/ROADMAP_STATE.json`` and cross-checks it against live, local Git/worktree
state. Queries never mutate files or Git. Explicit --continue-scope writes only
the current owner-authorized continuation, preserving its prior completion.
Explicit --admit-scope reconciles a current ACTIVE release or preserves a COMPLETE
predecessor, then admits one owner-directed scope with an empty queue. Neither starts runtime work.

    python tools/stocklookup_roadmap.py                    human-readable report
    python tools/stocklookup_roadmap.py --json              machine-readable report
    python tools/stocklookup_roadmap.py --check              preflight gate (exit 0 = ON_TRACK with live Git)
    python tools/stocklookup_roadmap.py --worktrees          classify worktrees; removes nothing
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
    if report.overall == "ON_TRACK":
        drift = "PASS"
    elif report.overall == res.OVERALL_GIT_NOT_CHECKED:
        drift = res.OVERALL_GIT_NOT_CHECKED
    else:
        drift = "FAIL"
    print(f"  {drift}")
    print(f"Git verification: {report.git_verification}")
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

    if repo is not None:
        bootstrap = res.build_bootstrap(repo)
        counts = bootstrap["worktrees"]
        print("Bootstrap:")
        print(f"  focused_selection_count: {bootstrap['focused_selection_count']}")
        print(
            "  worktrees: "
            + " ".join(f"{key}={counts[key]}" for key in (
                "registered", "ancestor_of_head", "tracked_clean", "tracked_dirty", "unmerged", "status_unknown",
            ))
        )
        print("  do_not_open: " + ", ".join(bootstrap["do_not_open"]))

    non_info = [f for f in report.findings if f.severity != res.INFO]
    if non_info:
        print()
        print("Findings:")
        for f in non_info:
            print(f"  [{f.severity}] {f.code}: {f.message}")


def _report_to_json(report: res.RoadmapReport, *, repo: Path | None) -> dict:
    control = report.state.get("development_control")
    control = control if isinstance(control, dict) else {}
    lanes = control.get("lanes")
    lanes = lanes if isinstance(lanes, list) else []
    lineage_head = report.state.get("implementation_lineage_head")
    resolved_lineage = lineage_head
    if repo is not None and lineage_head:
        ok, resolved = res.resolve_checkpoint(repo, lineage_head)
        if ok:
            resolved_lineage = resolved
    return {
        "schema_version": res.SCHEMA_VERSION,
        "overall": report.overall,
        "git_verification": report.git_verification,
        "content_identity": report.content_identity,
        "bootstrap": res.build_bootstrap(repo) if repo is not None else {
            "do_not_open": list(res.DO_NOT_OPEN),
            "local_fast": list(res.LOCAL_FAST),
            "focused_selection_count": "UNKNOWN",
            "worktrees": "UNKNOWN",
        },
        "current": report.state.get("current"),
        "development_control": {
            "schema": control.get("schema"),
            "revision": control.get("revision"),
            "host_observations": ("AVAILABLE" if repo is not None and res.coordinator_host_available(report.state, repo)
                                  else "SKIPPED_NON_COORDINATOR_CLONE") if report.state.get("development_control") else "NOT_INITIALIZED",
            "lanes": [{k: l.get(k) for k in ("milestone_id", "responsible_agent", "branch", "state", "mode", "checkpoint")}
                      for l in lanes if isinstance(l, dict)],
            "runtime_authorized": False,
        },
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


def _offline_mutation_allowed(report: res.RoadmapReport) -> bool:
    """Scope continuation may run without live Git. ``--check`` still rejects that case."""
    return not report.has_fail() and report.overall in {"ON_TRACK", res.OVERALL_GIT_NOT_CHECKED}


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


def _control_text(original: str, control: dict) -> str:
    """Change only the optional extension, preserving legacy/history bytes."""
    match = re.search(r'^  "development_control": ', original, re.MULTILINE)
    body = json.dumps(control, ensure_ascii=False, indent=2, allow_nan=False).replace("\n", "\n  ")
    if match:
        _, length = json.JSONDecoder().raw_decode(original[match.end():])
        return original[:match.end()] + body + original[match.end() + length:]
    end = original.rfind("}")
    return original[:end].rstrip() + ',\n  "development_control": ' + body + "\n}\n"


def _write_control(path: Path, original: str, control: dict) -> None:
    """Process-released lock plus compare-and-swap and fsynced atomic replacement.

    No retry/poll loop. A crash leaves either the old or new complete JSON; OS releases
    the lock. Lock metadata lives in the OS temp directory, never a second state registry.
    """
    import hashlib
    import os
    import tempfile

    key = hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / ("stocklookup-roadmap-" + key + ".lock")
    with lock_path.open("a+b") as lock:
        if lock.seek(0, 2) == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if path.read_bytes() != original.encode("utf-8"):
                raise res.RoadmapStateError("LANE_STATE_CHANGED_RELOAD_REQUIRED")
            content = _control_text(original, control).encode("utf-8")
            fd, name = tempfile.mkstemp(prefix=".roadmap-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        finally:
            lock.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def lane_command(args, state: dict, repo: Path | None) -> dict:
    if repo is None:
        raise res.RoadmapStateError("LANE_LIVE_REPOSITORY_REQUIRED")
    if args.check_lane:
        return res.check_lane(state, args.check_lane, repo=repo)
    if args.integration_plan:
        receipts = json.loads(args.review_receipt.read_text(encoding="utf-8")) if args.review_receipt else None
        return res.integration_plan(state, repo=repo, main_sha=args.main_sha, receipts=receipts, candidate_id=args.candidate_lane)
    if not args.owner_override or not args.scope_note or not args.scope_note.strip() or not args.agent or not args.agent.strip():
        raise res.RoadmapStateError("LANE_EXPLICIT_OWNER_DIRECTIVE_AND_AGENT_REQUIRED")
    if args.state_file.resolve() != (repo / "docs/ROADMAP_STATE.json").resolve():
        raise res.RoadmapStateError("LANE_MUTATION_REQUIRES_COORDINATOR_NATIVE_STATE")
    # Capture the exact bytes used to construct this mutation before any validation;
    # a concurrent coordinator update during Git checks must fail CAS, never be lost.
    original = args.state_file.read_bytes().decode("utf-8")
    state = json.loads(original)
    if not res.git_head(repo) or res.evaluate(state, repo=repo).overall != "ON_TRACK":
        raise res.RoadmapStateError("LANE_NATIVE_ROADMAP_NOT_ON_TRACK")
    control = state.get("development_control")
    if args.init_lanes:
        if control:
            raise res.RoadmapStateError("LANE_COORDINATOR_ALREADY_INITIALIZED")
        control = {"schema": res.LANE_SCHEMA, "revision": 0, "history": [], "lanes": [],
                   "integration_agent": args.agent, "integration_branch": res.git_branch(repo),
                   "integration_worktree": str(repo.resolve())}
        event = {"operation": "INIT", "owner_note": args.scope_note, "agent": args.agent}
    else:
        if not control:
            raise res.RoadmapStateError("LANE_COORDINATOR_NOT_INITIALIZED")
        if (res._path_key(str(repo)) != res._path_key(control["integration_worktree"])
                or res.git_branch(repo) != control["integration_branch"] or args.agent != control["integration_agent"]):
            raise res.RoadmapStateError("LANE_ONLY_BOUND_INTEGRATION_OWNER_MAY_MUTATE")
        if args.admit_lane:
            lane = json.loads(args.lane_spec.read_text(encoding="utf-8")) if args.lane_spec else None
            if not isinstance(lane, dict) or lane.get("milestone_id") != args.admit_lane:
                raise res.RoadmapStateError("LANE_EXACT_SPEC_REQUIRED")
            # Caller cannot inject state, checkpoints, authority or leases through a spec.
            allowed = {"milestone_id", "responsible_agent", "branch", "worktree", "base_sha", "domain",
                       "mode", "allowed_paths", "shared_paths", "lease_note", "dependencies",
                       "provides", "consumes", "required_checks"}
            if set(lane) - allowed:
                raise res.RoadmapStateError("LANE_SPEC_RESERVED_FIELDS")
            if any(l["milestone_id"] == args.admit_lane for l in control["lanes"]):
                raise res.RoadmapStateError("LANE_DUPLICATE_ID")
            lane.update(state="ADMITTED", checkpoint=None, authority_effect="NONE",
                        admission_authority={"kind": "EXPLICIT_OWNER_DIRECTIVE", "note": args.scope_note,
                                             "integration_agent": args.agent}, history=[])
            control["lanes"].append(lane)
            errors = res.validate_development_control(state)
            if errors:
                raise res.RoadmapStateError(";".join(errors))
            checked = res.check_lane(state, args.admit_lane, repo=repo)
            if checked["errors"] or not checked["clean"] or checked["head"] != lane["base_sha"]:
                raise res.RoadmapStateError("LANE_ADMISSION_REQUIRES_CLEAN_EXACT_BASE:" + ";".join(checked["errors"]))
            event = {"operation": "ADMIT", "milestone_id": args.admit_lane}
        else:
            lane = res.lane_by_id(state, args.transition_lane)
            checked = res.check_lane(state, args.transition_lane, repo=repo)
            if checked["errors"]:
                raise res.RoadmapStateError(";".join(checked["errors"]))
            target = args.lane_state
            transitions = {"ADMITTED": {"ACTIVE", "ABANDONED"}, "ACTIVE": {"PAUSED", "REVIEW_READY", "ABANDONED"},
                           "PAUSED": {"ACTIVE", "ABANDONED"}, "REVIEW_READY": {"COMPLETE_LOCAL", "ACTIVE", "MERGED_RELEASED"},
                           "COMPLETE_LOCAL": {"ACTIVE", "MERGED_RELEASED"}}
            if target not in transitions.get(lane["state"], set()):
                raise res.RoadmapStateError("LANE_INVALID_TRANSITION")
            if target == "ACTIVE" and checked["unmet_dependencies"]:
                raise res.RoadmapStateError("LANE_DEPENDENCIES_UNSATISFIED")
            if target in {"PAUSED", "REVIEW_READY", "COMPLETE_LOCAL", "MERGED_RELEASED"}:
                if not res._full_sha(repo, args.checkpoint_at) or args.checkpoint_at != checked["head"] or not checked["clean"]:
                    raise res.RoadmapStateError("LANE_EXACT_CLEAN_CHECKPOINT_REQUIRED")
                lane["checkpoint"] = args.checkpoint_at
            if target in {"REVIEW_READY", "COMPLETE_LOCAL", "MERGED_RELEASED"} and lane["mode"] != "IMPLEMENTATION":
                raise res.RoadmapStateError("LANE_SHADOW_PROMOTION_FORBIDDEN")
            if target == "MERGED_RELEASED":
                receipt = json.loads(args.review_receipt.read_text(encoding="utf-8")) if args.review_receipt else {}
                # The recorded review must be from the exact pre-merge main/candidates.
                plan = res.integration_plan(state, repo=repo, main_sha=args.main_sha, receipts=receipt, candidate_id=lane["milestone_id"])
                # main has advanced after review; re-run the metadata plan at release SHA,
                # then require an exact post-merge receipt and all CI/integration checks.
                if plan["errors"]:
                    raise res.RoadmapStateError("LANE_RELEASE_REQUIRES_POST_MERGE_REVIEW:" + ";".join(plan["errors"]))
                if not res.git_is_ancestor(repo, lane["checkpoint"], args.main_sha):
                    raise res.RoadmapStateError("LANE_CHECKPOINT_NOT_ON_MAIN")
                if not receipt.get("owner_merge_directive") or not receipt.get("post_merge_ci_evidence"):
                    raise res.RoadmapStateError("LANE_OWNER_MERGE_AND_POST_MERGE_CI_REQUIRED")
                lane["release_sha"] = args.main_sha
            prior = lane["state"]
            lane["state"] = target
            event = {"operation": "TRANSITION", "milestone_id": lane["milestone_id"], "from": prior,
                     "to": target, "checkpoint": lane["checkpoint"]}
            lane["history"].append(dict(event, owner_note=args.scope_note))
    event.update(owner_note=args.scope_note, agent=args.agent, observed_head=res.git_head(repo))
    control["revision"] += 1
    control["history"].append(dict(event, revision=control["revision"]))
    state["development_control"] = control
    errors = res.validate_development_control(state)
    if errors:
        raise res.RoadmapStateError(";".join(errors))
    _write_control(args.state_file, original, control)
    return {"operation": event, "revision": control["revision"], "authority_effect": "NONE",
            "merge_authorized": False, "runtime_authorized": False}


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
    parser.add_argument("--complete-local-scope", metavar="MILESTONE_ID", help="Owner-authorized local implementation closeout only; no main release or successor.")
    parser.add_argument("--checkpoint-at", help="Exact full live implementation HEAD for local closeout.")
    parser.add_argument("--worktrees", action="store_true", help="Print worktree class, HEAD, branch and tracked-dirty count. Does not remove worktrees.")
    lanes = parser.add_mutually_exclusive_group()
    lanes.add_argument("--init-lanes", action="store_true", help="Owner-bind this checkout as the single lane coordinator.")
    lanes.add_argument("--admit-lane", metavar="ID", help="Admit exact disjoint source-development scope; no worktree creation.")
    lanes.add_argument("--transition-lane", metavar="ID", help="Record one lane lifecycle/checkpoint without changing legacy current.")
    lanes.add_argument("--check-lane", metavar="ID", help="Read-only branch, worktree, ownership and checkpoint validation.")
    lanes.add_argument("--integration-plan", action="store_true", help="Read-only exact-main integration order and review gate.")
    parser.add_argument("--agent", help="Recorded integration owner identity (attestation, not authentication).")
    parser.add_argument("--lane-spec", type=Path, help="Exact admission specification; not an execution-state registry.")
    parser.add_argument("--lane-state", choices=sorted(res.LANE_STATES))
    parser.add_argument("--main-sha", help="Full independently observed remote main; verified by ls-remote without fetching.")
    parser.add_argument("--review-receipt", type=Path, help="Exact-plan reviewer/test evidence receipt; grants no merge authority.")
    parser.add_argument("--candidate-lane", help="Plan one candidate; dependent successors remain separately gated.")
    args = parser.parse_args(argv)

    try:
        state = res.load_state(args.state_file)
    except res.RoadmapStateError as exc:
        print(f"ROADMAP_STATE_LOAD_FAILED: {exc}", file=sys.stderr)
        return 2

    repo = args.repo if args.repo.is_dir() else None

    if state.get("development_control") and (args.admit_scope or args.continue_scope or args.complete_local_scope):
        parser.error("coordinated mode requires scoped lane operations; legacy history remains preserved")

    if args.init_lanes or args.admit_lane or args.transition_lane or args.check_lane or args.integration_plan:
        if args.admit_scope or args.continue_scope or args.complete_local_scope or args.can_start or args.worktrees:
            parser.error("lane operations cannot be combined with legacy operations")
        try:
            result = lane_command(args, state, repo)
        except (res.RoadmapStateError, OSError, ValueError, TypeError, KeyError) as exc:
            print("LANE_OPERATION_REFUSED:" + str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if result.get("errors") else 0

    if args.complete_local_scope:
        if (not args.owner_override or not args.scope_note or not args.checkpoint_at
                or args.admit_scope or args.continue_scope or args.can_start or repo is None):
            parser.error("local closeout requires explicit owner directive, exact checkpoint and live repository only")
        mid = args.complete_local_scope
        current = state.get("current") or {}
        milestone = next((m for m in state["milestones"] if m.get("milestone_id") == mid), None)
        if (milestone is None or current != {"milestone": mid, "state": "ACTIVE"}
                or milestone.get("state") != "ACTIVE" or state.get("queued_next")):
            parser.error("local closeout requires exact current ACTIVE milestone and empty queue")
        ok, checkpoint = res.resolve_checkpoint(repo, args.checkpoint_at)
        status_code, status, _ = res.git_run(repo, "status", "--porcelain")
        if (not ok or checkpoint != args.checkpoint_at or checkpoint != res.git_head(repo)
                or status_code != 0 or any(line and not line.startswith("??") for line in status.splitlines())
                or res.evaluate(state, repo=repo).overall != "ON_TRACK"):
            parser.error("local closeout requires exact live HEAD, tracked-clean repository and ON_TRACK roadmap")
        milestone.update(state="COMPLETE", checkpoint=checkpoint,
                         terminal_disposition="LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED")
        milestone.setdefault("state_history", []).append("COMPLETE")
        milestone["notes"] += " Local closeout: " + args.scope_note + "; no main release, authority promotion or successor."
        state["current"]["state"] = "COMPLETE"
        if res.evaluate(state, repo=repo).overall != "ON_TRACK":
            parser.error("local completion must remain ON_TRACK; no state written")
        original = args.state_file.read_text(encoding="utf-8")
        args.state_file.write_bytes(continuation_text(original, state, mid).encode("utf-8"))
        print("OWNER_AUTHORIZED_LOCAL_CLOSEOUT:" + mid + ":" + checkpoint)
        return 0

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
        if not _offline_mutation_allowed(report):
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
        if not _offline_mutation_allowed(res.evaluate(state, repo=repo)):
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

    if args.worktrees and not args.json:
        if repo is None:
            print("WORKTREES: UNKNOWN")
        else:
            classified = res.classify_worktrees(repo)
            print("class\thead\tbranch\ttracked_dirty_count\tpath")
            for row in classified["rows"]:
                print(f"{row['class']}\t{row['head']}\t{row['branch']}\t{row['tracked_dirty_count']}\t{row['path']}")
        if not args.check:
            return 0

    report = res.evaluate(state, repo=repo)

    if args.json:
        print(json.dumps(_report_to_json(report, repo=repo), indent=2, sort_keys=True))
    else:
        _print_human_report(report, repo=repo)

    if args.check:
        return 0 if report.overall == "ON_TRACK" and report.git_verification == res.GIT_VERIFICATION_VERIFIED else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
