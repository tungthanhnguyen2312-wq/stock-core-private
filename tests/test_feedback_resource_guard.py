"""Containment tests for the bounded feedback child: deadline, termination/reaping, memory ceiling, admission, IPC size.

OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1. Real child processes are used on purpose: the guarantees under test
(wait-with-timeout, whole-tree kill, kernel memory ceiling) are properties of the OS interaction, not of mocks.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import ctypes
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

import feedback_resource_guard as guard

SMALL = guard.ResourcePolicy(deadline_seconds=30, memory_limit_bytes=None, min_available_physical_bytes=0,
                             min_available_commit_bytes=0, min_free_disk_bytes=0)


def _script(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "child.py"
    path.write_text(body, encoding="utf-8")
    return [sys.executable, str(path)]


def _policy(**changes):
    values = {**SMALL.as_dict(), **changes}
    return guard.ResourcePolicy(**values)


def _pid_alive(pid: int) -> bool:
    import prospective_feedback_streaming as streaming
    return streaming._pid_alive(pid)


def test_completed_child_returns_a_small_structured_result_and_is_reaped(tmp_path):
    result_path = tmp_path / "status.json"
    command = _script(tmp_path, f"import json,sys;open({str(result_path)!r},'w').write(json.dumps({{'status':'COMPLETED','artifact_identity':'x'}}))")
    outcome = guard.run_bounded(command, cwd=tmp_path, policy=_policy(memory_limit_bytes=1 << 30), result_path=result_path)
    assert outcome["outcome"] == "COMPLETED" and outcome["returncode"] == 0 and outcome["reason_code"] is None
    assert outcome["child_result"] == {"status": "COMPLETED", "artifact_identity": "x"} and outcome["reaped"] is True
    if os.name == "nt":
        assert outcome["containment"] == "WINDOWS_JOB_OBJECT_PROCESS_MEMORY" and outcome["peak_process_bytes"]


def test_total_deadline_terminates_and_reaps_the_whole_process_tree(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    body = (
        "import subprocess,sys,time\n"
        f"g=subprocess.Popen([sys.executable,'-c','import time;time.sleep(300)'])\n"
        f"open({str(pid_file)!r},'w').write(str(g.pid))\n"
        "time.sleep(300)\n"
    )
    started = time.perf_counter()
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path, policy=_policy(deadline_seconds=3), result_path=tmp_path / "s.json")
    elapsed = time.perf_counter() - started
    assert outcome["outcome"] == "TIMEOUT" and outcome["reason_code"] == guard.RESOURCE_TIMEOUT
    assert 3 <= elapsed < 20 and outcome["reaped"] is True
    deadline = time.time() + 10
    grandchild = int(pid_file.read_text()) if pid_file.exists() else None
    if grandchild is not None and os.name == "nt":  # job object kills the tree; POSIX uses a process group
        while _pid_alive(grandchild) and time.time() < deadline:
            time.sleep(0.2)
        assert not _pid_alive(grandchild)


def test_nonzero_exit_maps_to_a_distinct_defect_reason_not_a_resource_or_evidence_state(tmp_path):
    outcome = guard.run_bounded(_script(tmp_path, "import sys;sys.exit(30)"), cwd=tmp_path, policy=SMALL, result_path=tmp_path / "s.json")
    assert outcome["outcome"] == "EXIT_NONZERO" and outcome["reason_code"] == guard.COMPUTATION_ERROR
    assert outcome["reason_code"] not in guard.RESOURCE_REASONS
    other = guard.run_bounded(_script(tmp_path, "import sys;sys.exit(75)"), cwd=tmp_path, policy=SMALL, result_path=tmp_path / "s.json")
    assert other["reason_code"] == guard.RESOURCE_MEMORY_LIMIT


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object ceiling")
def test_memory_ceiling_is_enforced_by_the_kernel_and_reported_as_a_memory_resource_reason(tmp_path):
    body = "buf=[]\nwhile True:\n    buf.append(bytearray(8*1024*1024))\n"
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path, policy=_policy(memory_limit_bytes=512 * 1024 * 1024, deadline_seconds=60),
                                result_path=tmp_path / "s.json")
    assert outcome["outcome"] == "EXIT_NONZERO" and outcome["reason_code"] == guard.RESOURCE_MEMORY_LIMIT
    assert outcome["peak_process_bytes"] >= 0.92 * 512 * 1024 * 1024 and outcome["peak_process_bytes"] <= 600 * 1024 * 1024


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object allocation notifications")
@pytest.mark.parametrize("chunk_mib", [128, 256, 512])
def test_large_denied_allocation_is_a_resource_failure_even_with_low_peak(tmp_path, chunk_mib):
    body = f"buf=[]\nwhile True:\n    buf.append(bytearray({chunk_mib}*1024*1024))\n"
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path,
                                policy=_policy(memory_limit_bytes=512 * 1024 * 1024), result_path=tmp_path / "s.json")
    assert outcome["reason_code"] == guard.RESOURCE_MEMORY_LIMIT
    assert 0 < outcome["peak_process_bytes"] < 0.92 * 512 * 1024 * 1024
    assert outcome["reaped"] and outcome["tree_termination_confirmed"]


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object memory accounting")
def test_high_peak_is_not_proof_of_a_memory_failure(tmp_path):
    body = "buf=bytearray(480*1024*1024)\nraise ValueError('TEST_FIXTURE ordinary defect')\n"
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path,
                                policy=_policy(memory_limit_bytes=512 * 1024 * 1024), result_path=tmp_path / "s.json")
    assert outcome["reason_code"] == guard.COMPUTATION_ERROR
    assert 0.92 * 512 * 1024 * 1024 <= outcome["peak_process_bytes"] <= 512 * 1024 * 1024
    assert outcome["reaped"] and outcome["tree_termination_confirmed"]


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object allocation notifications")
@pytest.mark.parametrize("finish,reason", [
    ("pass", None),
    ("sys.exit(30)", guard.COMPUTATION_ERROR),
    ("import threading;threading.Event().wait(300)", guard.RESOURCE_TIMEOUT),
])
def test_caught_limit_event_does_not_override_success_explicit_defect_or_timeout(tmp_path, finish, reason):
    body = "import sys\ntry:\n    bytearray(512*1024*1024)\nexcept MemoryError:\n    " + finish + "\n"
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path,
                                policy=_policy(memory_limit_bytes=512 * 1024 * 1024, deadline_seconds=1),
                                result_path=tmp_path / "s.json")
    assert outcome["reason_code"] == reason
    assert outcome["reaped"] and outcome["tree_termination_confirmed"]


def test_child_memory_error_is_reported_through_the_status_sidecar(tmp_path):
    result_path = tmp_path / "s.json"
    body = (
        "import json,sys\n"
        f"open({str(result_path)!r},'w').write(json.dumps({{'status':'RESOURCE_UNAVAILABLE','reason_code':{guard.RESOURCE_MEMORY_LIMIT!r}}}))\n"
        "sys.exit(75)\n"
    )
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path, policy=SMALL, result_path=result_path)
    assert outcome["reason_code"] == guard.RESOURCE_MEMORY_LIMIT and outcome["child_result"]["status"] == "RESOURCE_UNAVAILABLE"


def _queued_job(events, *, active=0, clear_on_zero=True):
    """Inject only OS event delivery/accounting; exercise the real event consumer on every platform."""
    queue = deque(events)
    state = [active]
    waits = []
    def receive(port, message, key, overlap, timeout):
        waits.append(timeout)
        if not queue:
            return False
        value, completion_key = queue.popleft()
        message._obj.value = value
        key._obj.value = completion_key
        if value == 4 and clear_on_zero:
            state[0] = 0
        return True
    job = object.__new__(guard._Job)
    job.ctypes = ctypes
    job.wintypes = SimpleNamespace(DWORD=ctypes.c_uint32)
    job.port = 1
    job.kernel = SimpleNamespace(GetQueuedCompletionStatus=receive)
    job.memory_limit_exceeded = False
    job.active_processes = lambda: state[0]
    return job, queue, waits


@pytest.mark.parametrize("events,expected", [
    ([(6, 1), (9, 1), (7, 1), (4, 1)], True),
    ([(4, 1), (10, 1)], True),
    ([(9, 99), (7, 1), (4, 1)], False),
    ([], False),
])
def test_already_empty_job_keeps_positive_limit_events_without_waiting(events, expected):
    job, queue, waits = _queued_job(events)
    assert job.wait_empty(1) is True
    assert job.memory_limit_exceeded is expected and not queue
    assert waits and all(wait == 0 for wait in waits)


def test_waiting_job_keeps_limit_events_before_and_after_tree_zero():
    job, queue, waits = _queued_job([(9, 1), (4, 1), (10, 1)], active=1)
    assert job.wait_empty(1) is True
    assert job.memory_limit_exceeded and not queue
    assert waits[0] > 0 and waits[-1] == 0


def test_limit_event_never_substitutes_for_confirmed_empty_tree():
    job, _, _ = _queued_job([(9, 1), (4, 1)], active=None, clear_on_zero=False)
    assert job.wait_empty(1) is False
    assert job.memory_limit_exceeded


def test_event_drain_uses_the_existing_shared_cleanup_budget(monkeypatch):
    job, queue, waits = _queued_job([(7, 1)] * 100)
    ticks = iter([0, 0.1, 0.2, 0.3, 1.1])
    monkeypatch.setattr(guard.time, "perf_counter", lambda: next(ticks))
    assert job.wait_empty(1) is True
    assert queue and len(waits) == 3 and waits == [0, 0, 0]


def test_oversize_child_status_is_never_ingested(tmp_path):
    result_path = tmp_path / "s.json"
    body = f"open({str(result_path)!r},'w').write('{{\"x\":\"' + 'a'*{guard.RESULT_MAX_BYTES + 10} + '\"}}')"
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path, policy=SMALL, result_path=result_path)
    assert outcome["child_result"] == {"status": "CHILD_RESULT_OVERSIZE"}


def test_unlaunchable_command_is_a_defect_not_a_hang(tmp_path):
    outcome = guard.run_bounded([str(tmp_path / "does-not-exist.exe")], cwd=tmp_path, policy=SMALL, result_path=tmp_path / "s.json")
    assert outcome["outcome"] == "LAUNCH_FAILED" and outcome["reason_code"] == guard.COMPUTATION_ERROR and outcome["reaped"]


def test_stale_status_from_a_previous_run_cannot_be_mistaken_for_this_runs_result(tmp_path):
    result_path = tmp_path / "s.json"
    result_path.write_text(json.dumps({"status": "COMPLETED", "artifact_identity": "stale"}), encoding="utf-8")
    outcome = guard.run_bounded(_script(tmp_path, "import sys;sys.exit(30)"), cwd=tmp_path, policy=SMALL, result_path=result_path)
    assert outcome["child_result"] is None and outcome["reason_code"] == guard.COMPUTATION_ERROR


# -- admission --------------------------------------------------------------------------------------------

def test_admission_refuses_on_insufficient_memory_commit_or_disk_with_distinct_reasons(tmp_path):
    huge = 1 << 60
    assert guard.admit(_policy(min_available_physical_bytes=huge), output_dir=tmp_path, expected_output_bytes=0)["reason_code"] == guard.RESOURCE_UNAVAILABLE
    assert guard.admit(_policy(min_available_commit_bytes=huge), output_dir=tmp_path, expected_output_bytes=0)["reason_code"] == guard.RESOURCE_UNAVAILABLE
    disk = guard.admit(_policy(min_free_disk_bytes=huge), output_dir=tmp_path, expected_output_bytes=0)
    assert disk["admitted"] is False and disk["reason_code"] == guard.RESOURCE_DISK
    ok = guard.admit(SMALL, output_dir=tmp_path, expected_output_bytes=1000)
    assert ok["admitted"] is True and ok["reason_code"] is None
    assert {guard.RESOURCE_TIMEOUT, guard.RESOURCE_UNAVAILABLE, guard.RESOURCE_MEMORY_LIMIT, guard.RESOURCE_DISK}.isdisjoint(
        {guard.COMPUTATION_ERROR, guard.EVIDENCE_INSUFFICIENT, guard.NOT_MATURE})


def test_default_policy_is_bounded_and_overridable():
    policy = guard.default_feedback_policy({})
    assert 0 < policy.deadline_seconds <= 3600 and policy.memory_limit_bytes and policy.min_free_disk_bytes > 0
    custom = guard.default_feedback_policy({"STOCKLOOKUP_FEEDBACK_DEADLINE_SECONDS": "12", "STOCKLOOKUP_FEEDBACK_MEMORY_LIMIT_BYTES": "0"})
    assert custom.deadline_seconds == 12 and custom.memory_limit_bytes is None
    assert guard.default_feedback_policy({"STOCKLOOKUP_FEEDBACK_DEADLINE_SECONDS": "bad"}).deadline_seconds == policy.deadline_seconds


@pytest.mark.skipif(os.name != "nt", reason="Windows degraded containment")
def test_windows_job_unavailable_exposes_deadline_only_and_unknown_tree(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError("injected Job Object unavailable")
    monkeypatch.setattr(guard, "_Job", unavailable)
    done = guard.run_bounded(_script(tmp_path, "pass"), cwd=tmp_path, policy=SMALL, result_path=tmp_path / "done.json")
    assert done["outcome"] == "COMPLETED" and done["immediate_child_reaped"]
    assert done["containment"] == "DEADLINE_ONLY" and done["containment_degraded"]
    assert done["tree_termination_confirmed"] is None and done["peak_process_bytes"] is None
    timed = guard.run_bounded(_script(tmp_path, "import threading;threading.Event().wait(300)"), cwd=tmp_path,
                              policy=_policy(deadline_seconds=1), result_path=tmp_path / "timeout.json")
    assert timed["outcome"] == "TIMEOUT" and timed["immediate_child_reaped"]
    assert timed["reason_code"] == guard.CHILD_REAP_UNCONFIRMED and timed["reaped"] is False


@pytest.mark.skipif(os.name != "nt", reason="Windows Job accounting")
def test_unknown_job_tree_accounting_cannot_be_reported_safely_reaped(tmp_path, monkeypatch):
    monkeypatch.setattr(guard._Job, "wait_empty", lambda *a: False)
    run = guard.run_bounded(_script(tmp_path, "pass"), cwd=tmp_path, policy=SMALL, result_path=tmp_path / "s.json")
    assert run["outcome"] == "COMPLETED" and run["immediate_child_reaped"]
    assert run["reaped"] is False and run["reason_code"] == guard.CHILD_REAP_UNCONFIRMED


def test_child_status_writer_is_atomic_and_never_raises(tmp_path):
    guard.write_child_result(tmp_path / "a" / "s.json", {"status": "COMPLETED"})
    assert json.loads((tmp_path / "a" / "s.json").read_text()) == {"status": "COMPLETED"}
    guard.write_child_result(tmp_path / "b.json", {"status": "X", "blob": "z" * (guard.RESULT_MAX_BYTES + 5)})
    assert json.loads((tmp_path / "b.json").read_text())["truncated"] is True
    guard.write_child_result(None, {"status": "ignored"})
    guard.write_child_result(tmp_path / "a" / "s.json" / "nested", {"status": "cannot be created"})  # parent is a file: must not raise
    assert not list(tmp_path.rglob(".child-result-*"))
