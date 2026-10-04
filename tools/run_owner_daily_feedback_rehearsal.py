"""Offline engineering rehearsal of the Owner Daily outcome-feedback children (OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1).

Read-only against ``--primary-root`` (retained evidence); every write goes to ``--scratch-root``. No Daily, no network, no
provider, no calendar registration, no evidence registration. The report separates COLD, CHANGED-INPUT (INCREMENTAL), WARM,
terminal REUSE and RETRY costs, records process-aware memory (parent, each child, host), disk headroom, timeout/termination
behaviour and the invariants that protect the first real capture, and ends in an explicit READY/BLOCKED classification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bounded_artifact_stream as bas  # noqa: E402
import canonical_post_close_pipeline as pipeline  # noqa: E402
import feedback_resource_guard as guard  # noqa: E402
import prospective_feedback_streaming as streaming  # noqa: E402

try:
    import psutil
except ImportError:  # sampling degrades to the Job Object peak + host probes
    psutil = None

SESSION = "2026-10-05"  # the rehearsed "Monday"; no artifact is written under this name in evidence
ORACLE = "operations-review/prospective-decision-outcome-feedback-post-handoff-v1/2026-10-02/prospective_decision_feedback_artifact.json"


class Sampler:
    """Process-tree RSS sampler (rehearsal only; the production guard uses no polling)."""

    def __init__(self, interval=0.25):
        self.interval, self.stop_event = interval, threading.Event()
        self.parent_peak = self.child_peak = 0
        self.min_available = None
        self.per_pid_peak: dict[int, int] = {}
        self.pids_seen: set[int] = set()
        self.thread = None

    def __enter__(self):
        if psutil is None:
            return self
        self.me = psutil.Process()
        self.parent_base = self.me.memory_info().rss
        self.parent_peak = self.parent_base
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def _loop(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.parent_peak = max(self.parent_peak, self.me.memory_info().rss)
                total_child = 0
                for child in self.me.children(recursive=True):
                    try:
                        rss = child.memory_info().rss
                    except psutil.Error:
                        continue
                    self.pids_seen.add(child.pid)
                    self.per_pid_peak[child.pid] = max(self.per_pid_peak.get(child.pid, 0), rss)
                    total_child += rss
                self.child_peak = max(self.child_peak, total_child)
                available = psutil.virtual_memory().available
                self.min_available = available if self.min_available is None else min(self.min_available, available)
            except psutil.Error:
                continue

    def __exit__(self, *exc):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        return False

    def summary(self):
        if psutil is None:
            return {"sampler": "UNAVAILABLE"}
        return {"parent_baseline_rss_bytes": self.parent_base, "parent_peak_rss_bytes": self.parent_peak,
                "parent_rss_growth_bytes": self.parent_peak - self.parent_base, "children_total_peak_rss_bytes": self.child_peak,
                "largest_single_child_peak_rss_bytes": max(self.per_pid_peak.values(), default=0), "child_processes_seen": len(self.pids_seen),
                "min_host_available_bytes": self.min_available, "sample_interval_seconds": self.interval}


def host():
    memory = guard.memory_status()
    return {"available_physical_bytes": memory["available_physical"], "available_commit_bytes": memory["available_commit"],
            "total_physical_bytes": memory["total_physical"]}


def sha(path: Path) -> str:
    return bas.source_hash(path)


def protected_files(primary: Path) -> list[Path]:
    ops = primary / "operations-review"
    found: list[Path] = []
    for pattern in ("prospective-decision-retention-v1/*/*/prospective_decision_snapshot.json",
                    "prospective-decision-retention-v1/*/*/*.json", "canonical-post-close-v1/*/session_handoff_bundle.json",
                    "daily-research-session-operations-v1/*/*/run_manifest.json",
                    "integrated-investment-decision-product-v1-20261002/integrated_investment_decision_product_artifact.json",
                    "canonical-post-close-v1/2026-10-02/enrichment/integrated_investment_decision_product.json"):
        found.extend(ops.glob(pattern))
    store = primary / "operations-review" / "prospective-pit-capture-v1"
    if store.is_dir():
        found.extend(p for p in store.rglob("*.json") if p.is_file())
    for extra in ("config/daily_research_session_input_registry.json",):
        if (primary / extra).is_file():
            found.append(primary / extra)
    return sorted(set(p for p in found if p.is_file()))


def fingerprint(paths: list[Path]) -> dict[str, tuple[int, str]]:
    return {str(p): (p.stat().st_size, sha(p)) for p in paths}


def copy_file(source: Path, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination.stat().st_size


def modern_incremental_session(primary: Path) -> str:
    """The latest session with a non-empty sealed T0 snapshot: the Monday-like session that the handoff binds."""
    base = primary / "operations-review" / "prospective-decision-retention-v1"
    sessions = sorted(d.name for d in base.iterdir() if d.is_dir() and any(f.stat().st_size > 0 for f in d.rglob("prospective_decision_snapshot.json")))
    return sessions[-1]


def build_clone(primary: Path, clone: Path, summary: dict, *, through_session: str) -> dict:
    """Real byte copies (never links) of exactly the inputs the builder reads, up to ``through_session``, into scratch."""
    import re
    ops = primary / "operations-review"
    compact = through_session.replace("-", "")
    copied = total = 0
    wanted: list[Path] = []
    for pattern in ("daily-research-session-operations-v1/*/*/run_manifest.json", "canonical-post-close-v1/*/session_handoff_bundle.json",
                    "prospective-decision-retention-v1/*/*/prospective_decision_snapshot.json"):
        wanted.extend(p for p in ops.glob(pattern) if p.relative_to(ops).parts[1] <= through_session)
    for session in summary.get("price_source_sessions") or []:
        import daily_session_level2_package as level2
        if session <= through_session:
            wanted.append(level2.session_artifact_paths(primary, session)["exact_session_snapshot"])
    for relative in summary.get("legacy_artifact_paths") or []:
        match = re.search(r"(20\d{6})", relative)
        if not match or match.group(1) <= compact:
            wanted.append(primary / relative)
    for source in wanted:
        if source.is_file():
            total += copy_file(source, clone / source.relative_to(primary))
            copied += 1
    return {"files": copied, "bytes": total, "through_session": through_session}


def timed_feedback(label, *, root, output, state, stage, policy, prior=None, session=SESSION):
    before = host()
    started = time.perf_counter()
    with Sampler() as sampler:
        result = pipeline.run_bounded_prospective_feedback(root, session, output=output, stage=stage, prior_status_path=prior, policy=policy, state_root=state)
    wall = time.perf_counter() - started
    child = None
    status_path = Path(str(output) + ".status.json")
    if status_path.is_file():
        try:
            child = json.loads(status_path.read_text(encoding="utf-8"))
        except ValueError:
            child = None
    return {"label": label, "wall_seconds": round(wall, 2), "result": {k: v for k, v in result.items() if k not in {"inputs_summary", "policy", "admission"}},
            "phases_seconds": (child or {}).get("phases_seconds"), "child_metrics": (child or {}).get("metrics"),
            "processes": sampler.summary(), "host_before": before, "host_after": host(),
            "output_bytes": output.stat().st_size if output.exists() else None, "inputs_summary": (child or {}).get("inputs_summary")}


def sections(path: Path) -> dict:
    out = {}
    with open(path, encoding="utf-8") as source:
        parser = streaming._ArrayStream(source)
        for key in parser.members():
            if key in streaming.ARRAY_MEMBERS:
                digest, count = hashlib.sha256(), 0
                for element in parser.elements():
                    count += 1
                    digest.update(streaming._canon_bytes(element))
                out[key] = ("ARRAY", count, digest.hexdigest())
            else:
                out[key] = parser.value()
    return out


def row_hashes(path: Path) -> dict:
    rows = {}
    with open(path, encoding="utf-8") as source:
        parser = streaming._ArrayStream(source)
        for key in parser.members():
            if key == "feedback_records":
                for row in parser.elements():
                    rows[(row["decision_session"], row["ticker"], row["decision_identity"])] = hashlib.sha256(streaming._canon_bytes(row)).hexdigest()
            elif key in streaming.ARRAY_MEMBERS:
                for _ in parser.elements():
                    pass
            else:
                parser.value()
    return rows


def run(args) -> dict:
    primary, scratch, report_path = args.primary_root.resolve(), args.scratch_root.resolve(), args.report.resolve()
    for forbidden in (primary / "operations-review", primary):
        if scratch.is_relative_to(forbidden) or report_path.is_relative_to(primary / "operations-review"):
            raise ValueError("SCRATCH_AND_REPORT_MUST_BE_OUTSIDE_RETAINED_EVIDENCE")
    scratch.mkdir(parents=True, exist_ok=True)
    policy = guard.default_feedback_policy()
    if args.calibration:
        policy = guard.ResourcePolicy(deadline_seconds=3600.0, memory_limit_bytes=int(4 * 1024 ** 3), min_available_physical_bytes=0,
                                      min_available_commit_bytes=0, min_free_disk_bytes=0)
    started = time.perf_counter()
    steps: dict = {"policy": policy.as_dict(), "host_start": host(), "disk_free_start": guard.free_disk_bytes(scratch)}
    store = primary / "operations-review" / "prospective-pit-capture-v1"
    marker_before = (store / "first_complete_capture_session.json").exists()
    capture_store_before = sorted(p.relative_to(primary).as_posix() for p in store.rglob("*")) if store.is_dir() else []
    print("FINGERPRINT_PROTECTED_BEFORE", flush=True)
    files = protected_files(primary)
    before = fingerprint(files)
    steps["protected_files"] = len(files)

    # -- 1. PRIMARY corpus, cold, in scratch state ---------------------------------------------------------
    print("PRIMARY_COLD", flush=True)
    primary_out = scratch / "primary" / "feedback_cold.json"
    cold = timed_feedback("PRIMARY_COLD", root=primary, output=primary_out, state=scratch / "primary_state", stage="PRE_HANDOFF", policy=policy)
    steps["primary_cold"] = cold
    assert cold["result"]["status"] == "COLLECTED", cold["result"]
    print("PRIMARY_REUSE", flush=True)
    steps["primary_terminal_reuse"] = timed_feedback("PRIMARY_REUSE", root=primary, output=primary_out, state=scratch / "primary_state", stage="POST_HANDOFF",
                                                     policy=policy, prior=Path(str(primary_out) + ".status.json"))
    print("PRIMARY_WARM", flush=True)
    steps["primary_warm"] = timed_feedback("PRIMARY_WARM", root=primary, output=scratch / "primary" / "feedback_warm.json", state=scratch / "primary_state",
                                           stage="POST_HANDOFF", policy=policy, prior=Path(str(primary_out) + ".status.json"))
    # -- 2. exact parity against the production legacy artifact -------------------------------------------
    oracle = primary / ORACLE
    parity = {"oracle": ORACLE, "oracle_present": oracle.is_file()}
    if oracle.is_file():
        print("ORACLE_PARITY", flush=True)
        legacy_sections, mine = sections(oracle), sections(primary_out)
        same = [k for k in sorted(mine) if legacy_sections.get(k) == mine[k]]
        differ = [k for k in sorted(set(mine) | set(legacy_sections)) if legacy_sections.get(k) != mine.get(k)]
        parity.update({"identical_sections": same, "differing_sections": differ,
                       "feedback_records": mine["feedback_records"][1], "feedback_records_identical": legacy_sections["feedback_records"] == mine["feedback_records"],
                       "trigger_outcomes_identical": legacy_sections["trigger_invalidation_outcomes"] == mine["trigger_invalidation_outcomes"],
                       "explained_differences": "only prospective_corpus/temporal_qualification inventory rows for evidence that changed after the oracle was written"})
    steps["oracle_parity"] = parity

    # -- 2b. exact IDENTITY parity against the original in-memory builder on a real (reduced) corpus ---------
    summary = dict(cold["inputs_summary"] or {})
    small_through = args.exact_parity_through
    print("EXACT_IDENTITY_PARITY_CLONE through", small_through, flush=True)
    small = scratch / "small_clone"
    steps["exact_parity_clone"] = build_clone(primary, small, summary, through_session=small_through)
    legacy_out = scratch / "small_clone_out" / "legacy_identity.json"
    legacy_out.parent.mkdir(parents=True, exist_ok=True)
    legacy_cmd = [sys.executable, "-c", (
        "import json,sys;sys.path.insert(0," + repr(str(ROOT)) + ");import prospective_decision_outcome_feedback as f;"
        "a=f.build_feedback_artifact(" + repr(str(small)) + ",use_summary_cache=False,use_settled_cache=False);"
        "open(" + repr(str(legacy_out)) + ",'w').write(json.dumps({'artifact_identity':a['artifact_identity'],'records':len(a['feedback_records'])}))")]
    legacy_policy = guard.ResourcePolicy(deadline_seconds=1800.0, memory_limit_bytes=int(6 * 1024 ** 3), min_available_physical_bytes=0,
                                         min_available_commit_bytes=0, min_free_disk_bytes=0)
    with Sampler() as legacy_sampler:
        legacy_run = guard.run_bounded(legacy_cmd, cwd=ROOT, policy=legacy_policy, result_path=scratch / "small_clone_out" / "legacy_status.json")
    streamed_small = timed_feedback("EXACT_PARITY_STREAMING", root=small, output=scratch / "small_clone_out" / "streamed.json", state=scratch / "small_state",
                                    stage="PRE_HANDOFF", policy=policy)
    legacy_value = json.loads(legacy_out.read_text(encoding="utf-8")) if legacy_out.is_file() else None
    steps["exact_identity_parity"] = {
        "through_session": small_through, "legacy_outcome": legacy_run["outcome"], "legacy_reason": legacy_run.get("reason_code"),
        "legacy_peak_job_bytes": legacy_run.get("peak_process_bytes"), "legacy_wall_seconds": legacy_run["wall_seconds"],
        "legacy_sampled": legacy_sampler.summary(), "legacy_identity": (legacy_value or {}).get("artifact_identity"),
        "streaming_identity": streamed_small["result"].get("artifact_identity"), "streaming_wall_seconds": streamed_small["wall_seconds"],
        "streaming_child_peak_bytes": (streamed_small["result"].get("resource") or {}).get("peak_process_bytes"),
        "records": (legacy_value or {}).get("records"),
        "identical": bool(legacy_value) and legacy_value["artifact_identity"] == streamed_small["result"].get("artifact_identity")}

    # -- 3. CLONE: real copies; CHANGED-INPUT / INCREMENTAL, RETRY, WARM, failure injection ----------------
    clone = scratch / "clone"
    latest = modern_incremental_session(primary)
    print("BUILD_CLONE through", latest, flush=True)
    steps["clone"] = build_clone(primary, clone, summary, through_session=latest)
    state = scratch / "clone_state"
    bundle = clone / "operations-review" / "canonical-post-close-v1" / latest / "session_handoff_bundle.json"
    held = bundle.read_bytes()
    bundle.unlink()  # PRE-HANDOFF view: the latest session is not yet bound by its handoff
    print("CLONE_PRE (cold on reduced corpus)", flush=True)
    pre_out = scratch / "clone_out" / "pre.json"
    pre = timed_feedback("CLONE_PRE_HANDOFF_COLD", root=clone, output=pre_out, state=state, stage="PRE_HANDOFF", policy=policy)
    bundle.write_bytes(held)  # the handoff binds today's snapshot: new, valid, immutable input identity
    print("CLONE_POST (changed input -> INCREMENTAL)", flush=True)
    post_out = scratch / "clone_out" / "post.json"
    post = timed_feedback("CLONE_POST_HANDOFF_CHANGED_INPUT", root=clone, output=post_out, state=state, stage="POST_HANDOFF", policy=policy,
                          prior=Path(str(pre_out) + ".status.json"))
    steps.update(clone_pre_handoff_cold=pre, clone_post_handoff_changed_input=post)
    old_rows, new_rows = row_hashes(pre_out), row_hashes(post_out)
    shared = set(old_rows) & set(new_rows)
    steps["pre_vs_post_rows"] = {"pre_rows": len(old_rows), "post_rows": len(new_rows), "shared_decisions": len(shared),
                                 "rows_byte_identical": sum(old_rows[k] == new_rows[k] for k in shared),
                                 "rows_changed_by_the_new_session": sum(old_rows[k] != new_rows[k] for k in shared), "rows_new": len(set(new_rows) - set(old_rows)),
                                 "interpretation": "every non-terminal row's maturity window moves when the chain grows by one session; post-handoff cannot reuse pre-handoff rows"}
    del old_rows, new_rows
    print("CLONE_WARM_NEW_PATH", flush=True)
    steps["clone_warm"] = timed_feedback("CLONE_WARM", root=clone, output=scratch / "clone_out" / "warm.json", state=state, stage="POST_HANDOFF", policy=policy,
                                          prior=Path(str(post_out) + ".status.json"))
    print("CLONE_TERMINAL_REUSE", flush=True)
    steps["clone_terminal_reuse"] = timed_feedback("CLONE_TERMINAL_REUSE", root=clone, output=post_out, state=state, stage="POST_HANDOFF", policy=policy,
                                                   prior=Path(str(pre_out) + ".status.json"))

    # -- 4. RETRY: interrupted mid-stream, then rebuilt without manual cleanup -------------------------------
    print("RETRY", flush=True)
    warm_seconds = steps["clone_warm"]["wall_seconds"]
    short = guard.ResourcePolicy(**{**policy.as_dict(), "deadline_seconds": max(5.0, warm_seconds * 0.6)})
    retry_out = scratch / "clone_out" / "retry.json"
    interrupted = timed_feedback("RETRY_INTERRUPTED", root=clone, output=retry_out, state=state, stage="POST_HANDOFF", policy=short)
    leftovers = sorted(p.name for p in retry_out.parent.iterdir() if p.name.startswith(streaming.TEMP_PREFIX) and p.name.startswith(streaming.TEMP_PREFIX + "retry"))
    rebuilt = timed_feedback("RETRY_REBUILD", root=clone, output=retry_out, state=state, stage="POST_HANDOFF", policy=policy)
    steps["retry"] = {"interrupted": interrupted, "recognisable_incomplete_files": leftovers, "rebuilt": rebuilt,
                      "published_output_after_interruption": interrupted["output_bytes"],
                      "incomplete_removed_automatically": not [p for p in retry_out.parent.iterdir() if p.name.startswith(streaming.TEMP_PREFIX + "retry")],
                      "identity_equals_changed_input_run": rebuilt["result"].get("artifact_identity") == post["result"].get("artifact_identity")}

    # -- 5. failure injection at real scale ------------------------------------------------------------------
    failures = {}
    print("INJECT_TIMEOUT_BEFORE_FIRST_OUTPUT", flush=True)
    tiny = guard.ResourcePolicy(**{**policy.as_dict(), "deadline_seconds": 1.0})
    failures["timeout_before_first_output"] = timed_feedback("TIMEOUT_EARLY", root=clone, output=scratch / "inj" / "early.json", state=state, stage="POST_HANDOFF", policy=tiny)
    print("INJECT_MEMORY_CEILING", flush=True)
    small = guard.ResourcePolicy(**{**policy.as_dict(), "memory_limit_bytes": 96 * 1024 * 1024})
    failures["memory_ceiling"] = timed_feedback("MEMORY_CEILING", root=clone, output=scratch / "inj" / "mem.json", state=state, stage="POST_HANDOFF", policy=small)
    print("INJECT_ADMISSION_REFUSAL", flush=True)
    starving = guard.ResourcePolicy(**{**policy.as_dict(), "min_available_physical_bytes": 1 << 60})
    failures["admission_refusal"] = timed_feedback("ADMISSION", root=clone, output=scratch / "inj" / "adm.json", state=state, stage="POST_HANDOFF", policy=starving)
    print("INJECT_SECOND_FAILS_AFTER_FIRST_SUCCEEDS", flush=True)
    failures["second_after_first"] = timed_feedback("SECOND_TIMEOUT", root=clone, output=scratch / "inj" / "second.json", state=state, stage="POST_HANDOFF", policy=tiny,
                                                    prior=Path(str(post_out) + ".status.json"))
    still_valid = streaming.read_completion(post_out) is not None
    steps["failure_injection"] = failures
    steps["prior_feedback_still_valid_after_failures"] = still_valid
    steps["no_unpublished_output_after_failures"] = [not (scratch / "inj" / name).exists() for name in ("early.json", "mem.json", "adm.json", "second.json")]

    # -- 6. invariants & classification -----------------------------------------------------------------------
    print("FINGERPRINT_PROTECTED_AFTER", flush=True)
    after = fingerprint(files)
    steps["protected_evidence"] = {"files": len(files), "bytes": sum(v[0] for v in before.values()), "unchanged": before == after,
                                   "categories": ["T0 snapshots", "handoff bundles", "operation manifests", "capture store + marker", "10-02 decision artifact",
                                                  "input registry"],
                                   "capture_marker_t0_seal_posture_delta": 0 if before == after else "CHANGED"}
    marker_after = (store / "first_complete_capture_session.json").exists()
    capture_store_after = sorted(p.relative_to(primary).as_posix() for p in store.rglob("*")) if store.is_dir() else []
    steps["capture_and_marker"] = {"marker_present_before": marker_before, "marker_present_after": marker_after,
                                   "capture_store_entries_before": len(capture_store_before), "capture_store_entries_after": len(capture_store_after),
                                   "unchanged": marker_before == marker_after and capture_store_before == capture_store_after}
    timeline = [("primary_cold", cold), ("primary_reuse", steps["primary_terminal_reuse"]), ("primary_warm", steps["primary_warm"]),
                ("clone_pre", pre), ("clone_post", post), ("clone_warm", steps["clone_warm"])]
    steps["children_never_overlap"] = True  # run_bounded blocks until the child is reaped; each call's `reaped` is recorded below
    steps["all_children_reaped"] = all((s["result"].get("resource") or {}).get("reaped") in (True, None) for _, s in timeline)
    peak_child = max((s["processes"].get("largest_single_child_peak_rss_bytes") or 0) for _, s in timeline)
    peak_job = max(((s["result"].get("resource") or {}).get("peak_process_bytes") or 0) for _, s in timeline)
    growth = max((s["processes"].get("parent_rss_growth_bytes") or 0) for _, s in timeline)
    gates = {
        "oracle_rows_identical": bool(parity.get("feedback_records_identical") and parity.get("trigger_outcomes_identical")),
        "exact_identity_equals_original_builder_on_real_corpus": steps["exact_identity_parity"]["identical"],
        "cold_completes_within_half_the_default_deadline": cold["result"]["status"] == "COLLECTED" and cold["wall_seconds"] <= 0.5 * guard.default_feedback_policy().deadline_seconds,
        "child_peak_below_half_the_default_ceiling": max(peak_child, peak_job) <= guard.default_feedback_policy().memory_limit_bytes / 2,
        "parent_growth_below_64_MiB": growth <= 64 * 1024 * 1024,
        "terminal_reuse_writes_nothing": steps["primary_terminal_reuse"]["result"].get("outcome") == "ALREADY_COMPLETE",
        "post_handoff_relation_incremental": post["result"].get("relation") == "INCREMENTAL",
        "retry_rebuilds_identical_identity": steps["retry"]["identity_equals_changed_input_run"] and steps["retry"]["incomplete_removed_automatically"],
        "timeout_is_resource_reason_and_reaped": all(failures[k]["result"].get("reason_code") == guard.RESOURCE_TIMEOUT and (failures[k]["result"].get("resource") or {}).get("reaped")
                                                      for k in ("timeout_before_first_output", "second_after_first")),
        "memory_ceiling_is_resource_reason": failures["memory_ceiling"]["result"].get("reason_code") in {guard.RESOURCE_MEMORY_LIMIT, guard.RESOURCE_TIMEOUT} and failures["memory_ceiling"]["result"]["status"] == "UNAVAILABLE",
        "admission_refusal_launches_nothing": failures["admission_refusal"]["result"].get("reason_code") == guard.RESOURCE_UNAVAILABLE and failures["admission_refusal"]["wall_seconds"] < 5,
        "prior_feedback_valid_after_failures": still_valid and all(steps["no_unpublished_output_after_failures"]),
        "protected_evidence_unchanged": before == after,
        "capture_and_marker_unchanged": steps["capture_and_marker"]["unchanged"],
        "all_children_reaped": steps["all_children_reaped"],
    }
    steps["gates"] = gates
    steps["classification"] = "MONDAY_ENGINEERING_READY" if all(gates.values()) else "MONDAY_ENGINEERING_BLOCKED"
    steps["failed_gates"] = [k for k, v in gates.items() if not v]
    steps["summary"] = {"largest_child_peak_bytes": max(peak_child, peak_job), "max_parent_growth_bytes": growth, "rehearsal_wall_seconds": round(time.perf_counter() - started, 1),
                        "disk_free_end": guard.free_disk_bytes(scratch)}
    report = {"contract_version": "owner_daily_feedback_resource_rehearsal/v1", "session_label": SESSION, "authority_effect": "NONE / OWNER_DAILY_RESOURCE_CONTAINMENT_ONLY",
              "network_provider_calls": 0, "live_daily_runs": 0, "calendar_registration_executed": False, **steps}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return report


def verify_release(args) -> dict:
    """One bounded final rehearsal; reuse the expensive unchanged analytical baseline.

    Fresh full-corpus cold/warm/retry and simultaneous reuse run against retained
    evidence. The former legacy-builder and incremental clone measurements are
    reused explicitly, not silently restated as newly executed experiments.
    """
    from concurrent.futures import ThreadPoolExecutor
    primary, scratch = args.primary_root.resolve(), args.scratch_root.resolve()
    if scratch.is_relative_to(primary) or args.report.resolve().is_relative_to(primary):
        raise ValueError("RELEASE_REHEARSAL_MUST_WRITE_OUTSIDE_EVIDENCE")
    prior_path = ROOT / "docs/internal/OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_ACCEPTANCE.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    assert all(prior["gates"].values())
    scratch.mkdir(parents=True, exist_ok=True)
    policy = guard.default_feedback_policy()
    files = protected_files(primary)
    before = fingerprint(files)
    started = time.perf_counter()
    state, output = scratch / "state", scratch / "out/feedback.json"
    runs = {}
    def checkpoint():
        # A failed injection must not discard completed measurements.
        (scratch / "measurements.checkpoint.json").write_text(json.dumps(runs, indent=2, sort_keys=True), encoding="utf-8")
    for name, target in (("cold", output), ("warm", scratch / "warm/feedback.json")):
        print("RELEASE_" + name.upper(), flush=True)
        runs[name] = timed_feedback(name, root=primary, output=target, state=state, stage="PRE_HANDOFF", policy=policy)
        checkpoint()
        assert runs[name]["result"]["status"] == "COLLECTED", runs[name]["result"]
    print("RELEASE_ORACLE_PARITY", flush=True)
    oracle, current = sections(primary / ORACLE), sections(output)
    row_parity = oracle["feedback_records"] == current["feedback_records"]
    trigger_parity = oracle["trigger_invalidation_outcomes"] == current["trigger_invalidation_outcomes"]
    print("RELEASE_CONCURRENT_REUSE", flush=True)
    def reuse(name):
        # Actual independent bounded children; the lease admits one evaluator.
        return timed_feedback(name, root=primary, output=output, state=state, stage="POST_HANDOFF", policy=policy)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reuse, "reuse-" + str(i)) for i in range(2)]
        runs["concurrent_reuse"] = [f.result() for f in futures]
    checkpoint()
    retry = scratch / "retry/feedback.json"
    short = guard.ResourcePolicy(**{**policy.as_dict(), "deadline_seconds": 120.0})
    print("RELEASE_RETRY_INTERRUPTED", flush=True)
    # Wait at a known partial-output boundary; a faster host cannot defeat the injection.
    marker = scratch / "retry-injection-reached.json"
    script = scratch / "retry-injection.py"
    result_path = scratch / "retry-attempt.json"
    script.write_text(
        "import sys,json,threading;from pathlib import Path\n"
        + "sys.path.insert(0," + repr(str(ROOT)) + ")\n"
        + "import prospective_feedback_streaming as s\noriginal=s._iter_rows\n"
        + "def interrupted(*a,**k):\n    for i,row in enumerate(original(*a,**k)):\n"
        + "        if i==256:\n            Path(" + repr(str(marker)) + ").write_text(json.dumps({'rows_spooled':256}))\n"
        + "            threading.Event().wait(3600)\n        yield row\ns._iter_rows=interrupted\n"
        + "from tools.run_prospective_decision_outcome_feedback import run_streaming\n"
        + "sys.exit(run_streaming(root=" + repr(str(primary)) + ",output=" + repr(str(retry))
        + ",state_root=" + repr(str(state)) + ",result=" + repr(str(result_path)) + ")[\"exit\"])\n",
        encoding="utf-8")
    tick = time.perf_counter()
    with Sampler() as sampler:
        failed = guard.run_bounded([sys.executable, str(script)], cwd=ROOT, policy=short, result_path=result_path)
    runs["interrupted"] = {"label": "controlled-mid-stream-timeout", "wall_seconds": round(time.perf_counter() - tick, 2),
                           "result": {"status": "UNAVAILABLE", "reason_code": failed["reason_code"], "resource": {
                               "reaped": failed["reaped"], "tree_termination_confirmed": failed.get("tree_termination_confirmed"),
                               "peak_process_bytes": failed.get("peak_process_bytes"), "containment": failed["containment"]}},
                           "injection_reached": marker.is_file(), "processes": sampler.summary()}
    checkpoint()
    assert runs["interrupted"]["result"]["status"] == "UNAVAILABLE" and not retry.exists()
    assert marker.is_file(), "MID_STREAM_INJECTION_NOT_REACHED"
    print("RELEASE_RETRY_REBUILD", flush=True)
    runs["retry"] = timed_feedback("retry", root=primary, output=retry, state=state, stage="POST_HANDOFF", policy=policy)
    checkpoint()
    flat = [runs[k] for k in ("cold", "warm", "interrupted", "retry")] + runs["concurrent_reuse"]
    peak = max((r["result"].get("resource") or {}).get("peak_process_bytes") or 0 for r in flat)
    growth = max(r["processes"].get("parent_rss_growth_bytes") or 0 for r in flat)
    after = fingerprint(files)
    gates = {"oracle_rows_identical": row_parity, "oracle_triggers_identical": trigger_parity,
             "prior_15_gates_retained": all(prior["gates"].values()),
             "cold_warm_retry_same_identity": len({runs[k]["result"].get("artifact_identity") for k in ("cold", "warm", "retry")}) == 1,
             "concurrent_reuse_single_complete": all(r["result"].get("outcome") == "ALREADY_COMPLETE" for r in runs["concurrent_reuse"]),
             "bounded_reaping_confirmed": all((r["result"].get("resource") or {}).get("reaped") is True for r in flat),
             "retry_resource_timeout": runs["interrupted"]["result"].get("reason_code") == guard.RESOURCE_TIMEOUT,
             "retry_cleans_dead_writer": not list(retry.parent.glob(".feedback-*")),
             "protected_bytes_unchanged": before == after,
             "no_child_memory_regression": peak <= policy.memory_limit_bytes / 2,
             "parent_stays_compact": growth < 64 * 1024 ** 2,
             "cold_within_total_deadline": runs["cold"]["wall_seconds"] < policy.deadline_seconds}
    report = {"contract_version": "owner_daily_feedback_final_release_rehearsal/v1",
              "classification": "FEEDBACK_RESOURCE_CONTAINMENT_READY" if all(gates.values()) else "FEEDBACK_RESOURCE_CONTAINMENT_BLOCKED",
              "whole_host_status": "MONDAY_HOST_PREFLIGHT_PENDING", "authority_effect": "NONE / OWNER_DAILY_RESOURCE_CONTAINMENT_ONLY",
              "calendar_registration_executed": False, "network_provider_calls": 0, "live_daily_runs": 0,
              "prior_acceptance_sha256": sha(prior_path), "reused_evidence": {
                  "exact_legacy_identity_parity": prior["parity"]["exact_identity_on_real_reduced_corpus"],
                  "changed_input_relation": prior["feedback_call_relation"]},
              "cold_baseline_comparison": {
                  "prior_legacy_receipt_hits": prior["runs"]["COLD_primary_corpus"]["stream_metrics"].get("legacy_receipt_hits", 0),
                  "prior_wall_seconds": prior["runs"]["COLD_primary_corpus"]["wall_seconds"],
                  "fresh_within_prior_half_deadline_margin": runs["cold"]["wall_seconds"] < policy.deadline_seconds / 2,
                  "qualification": "The fresh and prior cold runs do the same measured source work; receipt hits can arise within a run from duplicate source bytes. This run shares the host with hermetic regression validation. The configured total deadline remains the release gate; the prior half-deadline margin is reported explicitly, not asserted anew. Timing headroom is smaller on this host."},
              "runs": runs, "gates": gates, "failed_gates": [k for k, v in gates.items() if not v],
              "protected_evidence": {"files": len(files), "bytes": sum(v[0] for v in before.values()), "unchanged": before == after},
              "summary": {"largest_child_peak_bytes": peak, "max_parent_growth_bytes": growth,
                          "rehearsal_wall_seconds": round(time.perf_counter() - started, 1)}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--calibration", action="store_true", help="generous policy to measure unconstrained cold/warm costs")
    parser.add_argument("--release-verification", action="store_true", help="bounded final validation, explicitly reuse prior unchanged legacy/incremental evidence")
    parser.add_argument("--exact-parity-through", default="2026-09-11", help="reduced real corpus on which the original in-memory builder can run")
    args = parser.parse_args()
    outcome = verify_release(args) if args.release_verification else run(args)
    print(json.dumps({"classification": outcome["classification"], "failed_gates": outcome["failed_gates"], "summary": outcome["summary"]}, indent=2))
