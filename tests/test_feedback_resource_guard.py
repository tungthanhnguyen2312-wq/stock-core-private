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
from pathlib import Path

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
    body = "buf=[]\nwhile True:\n    buf.append(bytearray(64*1024*1024))\n"
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path, policy=_policy(memory_limit_bytes=512 * 1024 * 1024, deadline_seconds=60),
                                result_path=tmp_path / "s.json")
    assert outcome["outcome"] == "EXIT_NONZERO" and outcome["reason_code"] == guard.RESOURCE_MEMORY_LIMIT
    assert outcome["peak_process_bytes"] >= 0.92 * 512 * 1024 * 1024 and outcome["peak_process_bytes"] <= 600 * 1024 * 1024


def test_child_memory_error_is_reported_through_the_status_sidecar(tmp_path):
    result_path = tmp_path / "s.json"
    body = (
        "import json,sys\n"
        f"open({str(result_path)!r},'w').write(json.dumps({{'status':'RESOURCE_UNAVAILABLE','reason_code':{guard.RESOURCE_MEMORY_LIMIT!r}}}))\n"
        "sys.exit(75)\n"
    )
    outcome = guard.run_bounded(_script(tmp_path, body), cwd=tmp_path, policy=SMALL, result_path=result_path)
    assert outcome["reason_code"] == guard.RESOURCE_MEMORY_LIMIT and outcome["child_result"]["status"] == "RESOURCE_UNAVAILABLE"


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


def test_child_status_writer_is_atomic_and_never_raises(tmp_path):
    guard.write_child_result(tmp_path / "a" / "s.json", {"status": "COMPLETED"})
    assert json.loads((tmp_path / "a" / "s.json").read_text()) == {"status": "COMPLETED"}
    guard.write_child_result(tmp_path / "b.json", {"status": "X", "blob": "z" * (guard.RESULT_MAX_BYTES + 5)})
    assert json.loads((tmp_path / "b.json").read_text())["truncated"] is True
    guard.write_child_result(None, {"status": "ignored"})
    guard.write_child_result(tmp_path / "a" / "s.json" / "nested", {"status": "cannot be created"})  # parent is a file: must not raise
    assert not list(tmp_path.rglob(".child-result-*"))
