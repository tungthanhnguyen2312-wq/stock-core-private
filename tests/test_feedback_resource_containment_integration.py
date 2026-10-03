"""End-to-end failure injection for the bounded outcome-feedback child (OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1).

Real child processes against a fixture evidence root. After every injected failure the invariants that matter to the
first real prospective capture are re-checked: no retained evidence byte changes, no published or half-published
feedback artifact appears, a valid prior feedback artifact stays valid, and Daily's fail-soft contract holds (a bounded
UNAVAILABLE result, never an exception, never a feedback/investment state).
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import canonical_post_close_pipeline as cpc
import feedback_resource_guard as guard
import prospective_feedback_streaming as streaming
from tests.test_prospective_feedback_streaming import _corpus, _legacy_artifact

REPO = Path(__file__).resolve().parents[1]
FAST = guard.ResourcePolicy(deadline_seconds=300, memory_limit_bytes=1 << 30, min_available_physical_bytes=0,
                            min_available_commit_bytes=0, min_free_disk_bytes=0)


def _fingerprint(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture()
def world(tmp_path):
    root = tmp_path / "evidence"
    _corpus(root)
    return root, tmp_path / "state", tmp_path / "out"


def _run(root, state, output, *, stage=cpc.FEEDBACK_STAGE_PRE_HANDOFF, policy=FAST, prior=None):
    return cpc.run_bounded_prospective_feedback(root, "2026-02-10", output=output / "feedback.json", stage=stage,
                                                prior_status_path=prior, policy=policy, state_root=state)


def _patched_child(tmp_path: Path, body: str, root: Path, state: Path, output: Path, policy: guard.ResourcePolicy):
    """Run the real child entry point in a process where one internal step is replaced by failure-injection code."""
    script = tmp_path / "injected_child.py"
    script.write_text(textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(REPO)!r})
        import prospective_feedback_streaming as streaming
        {body}
        from tools.run_prospective_decision_outcome_feedback import run_streaming
        sys.exit(run_streaming(root={str(root)!r}, output={str(output)!r}, result={str(output) + '.status.json'!r}, state_root={str(state)!r})["exit"])
    """), encoding="utf-8")
    return guard.run_bounded([sys.executable, str(script)], cwd=REPO, policy=policy, result_path=Path(str(output) + ".status.json"))


def test_success_is_compact_and_the_parent_never_receives_the_artifact(world):
    root, state, out = world
    result = _run(root, state, out)
    assert result["status"] == "COLLECTED" and result["outcome"] == "BUILT" and result["artifact_identity"].startswith("prospective_decision_outcome_feedback:")
    assert json.loads((out / "feedback.json").read_text(encoding="utf-8"))["artifact_identity"] == result["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]
    assert len(json.dumps(result)) < 20_000 and result["resource"]["reaped"] and result["resource"]["child_peak_bytes"]
    again = _run(root, state, out)
    assert again["outcome"] == "ALREADY_COMPLETE" and again["artifact_identity"] == result["artifact_identity"]
    assert again["relation"] == "NO_PRIOR"  # no earlier status was supplied, so no relation is claimed


def test_timeout_before_first_output_publishes_nothing_and_changes_no_evidence(world):
    root, state, out = world
    before = _fingerprint(root)
    result = _run(root, state, out, policy=guard.ResourcePolicy(**{**FAST.as_dict(), "deadline_seconds": 0.4}))
    assert result["status"] == "UNAVAILABLE" and result["reason_code"] == guard.RESOURCE_TIMEOUT and result["resource"]["reaped"] is True
    assert not (out / "feedback.json").exists() and _fingerprint(root) == before
    assert _run(root, state, out)["status"] == "COLLECTED"  # no manual cleanup needed


def test_timeout_mid_stream_leaves_only_recognisable_incomplete_data_and_a_retry_rebuilds(world, tmp_path):
    root, state, out = world
    before = _fingerprint(root)
    slow = """
        import time
        _original = streaming._iter_rows
        def slow_rows(*a, **k):
            for n, row in enumerate(_original(*a, **k)):
                yield row
                if n == 5:
                    time.sleep(120)
        streaming._iter_rows = slow_rows
    """
    target = out / "feedback.json"
    run = _patched_child(tmp_path, slow, root, state, target, guard.ResourcePolicy(**{**FAST.as_dict(), "deadline_seconds": 8}))
    assert run["outcome"] == "TIMEOUT" and run["reason_code"] == guard.RESOURCE_TIMEOUT and run["reaped"] is True
    assert not target.exists() and streaming.read_completion(target) is None
    leftovers = [p.name for p in out.iterdir() if p.name.startswith(streaming.TEMP_PREFIX)]
    assert leftovers and all(name.endswith((".spool", ".incomplete")) for name in leftovers)  # recognisable, never a result
    assert _fingerprint(root) == before
    rebuilt = _run(root, state, out)
    assert rebuilt["status"] == "COLLECTED" and rebuilt["outcome"] == "BUILT"
    assert [p.name for p in out.iterdir() if p.name.startswith(streaming.TEMP_PREFIX)] == []  # dead writer's temporaries removed automatically
    assert json.loads(target.read_text(encoding="utf-8"))["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object ceiling")
def test_memory_error_inside_the_ceiling_is_a_resource_state_not_a_feedback_state(world, tmp_path):
    root, state, out = world
    hog = """
        _original = streaming._iter_rows
        def hog_rows(*a, **k):
            held = []
            for row in _original(*a, **k):
                held.append(bytearray(256 * 1024 * 1024))
                yield row
        streaming._iter_rows = hog_rows
    """
    run = _patched_child(tmp_path, hog, root, state, out / "feedback.json",
                         guard.ResourcePolicy(**{**FAST.as_dict(), "memory_limit_bytes": 640 * 1024 * 1024, "deadline_seconds": 120}))
    assert run["reason_code"] == guard.RESOURCE_MEMORY_LIMIT and run["reason_code"] in guard.RESOURCE_REASONS
    assert not (out / "feedback.json").exists()
    assert (run["child_result"] or {}).get("status", "RESOURCE_UNAVAILABLE") == "RESOURCE_UNAVAILABLE"


def test_child_defect_is_reported_as_a_defect_with_a_distinct_reason(world, tmp_path):
    root, state, out = world
    boom = """
        def boom(*a, **k):
            raise RuntimeError("injected defect")
            yield
        streaming._iter_rows = boom
    """
    run = _patched_child(tmp_path, boom, root, state, out / "feedback.json", FAST)
    assert run["outcome"] == "EXIT_NONZERO" and run["reason_code"] == guard.COMPUTATION_ERROR
    assert run["child_result"]["status"] == "FAILED" and "injected defect" in run["child_result"]["detail"]
    assert run["reason_code"] not in guard.RESOURCE_REASONS and not (out / "feedback.json").exists()


def test_second_feedback_failure_after_the_first_succeeded_leaves_the_first_valid(world):
    root, state, out = world
    first = cpc.run_bounded_prospective_feedback(root, "2026-02-10", output=out / "pre.json", stage=cpc.FEEDBACK_STAGE_PRE_HANDOFF,
                                                  policy=FAST, state_root=state)
    assert first["status"] == "COLLECTED"
    before = (out / "pre.json").read_bytes()
    second = cpc.run_bounded_prospective_feedback(
        root, "2026-02-10", output=out / "post.json", stage=cpc.FEEDBACK_STAGE_POST_HANDOFF,
        policy=guard.ResourcePolicy(**{**FAST.as_dict(), "deadline_seconds": 0.3}), prior_status_path=Path(first["status_path"]), state_root=state)
    assert second["status"] == "UNAVAILABLE" and second["reason_code"] == guard.RESOURCE_TIMEOUT
    assert (out / "pre.json").read_bytes() == before and streaming.read_completion(out / "pre.json")["artifact_identity"] == first["artifact_identity"]
    assert not (out / "post.json").exists()


def test_post_handoff_reports_incremental_relation_when_new_evidence_arrived(world):
    root, state, out = world
    first = cpc.run_bounded_prospective_feedback(root, "2026-02-10", output=out / "pre.json", stage=cpc.FEEDBACK_STAGE_PRE_HANDOFF,
                                                  policy=FAST, state_root=state)
    from tests.test_prospective_feedback_streaming import _add_modern
    _add_modern(root, "2026-02-20", 12)
    second = cpc.run_bounded_prospective_feedback(root, "2026-02-10", output=out / "post.json", stage=cpc.FEEDBACK_STAGE_POST_HANDOFF,
                                                   policy=FAST, prior_status_path=Path(first["status_path"]), state_root=state)
    assert second["status"] == "COLLECTED" and second["relation"] == "INCREMENTAL"
    same = cpc.run_bounded_prospective_feedback(root, "2026-02-10", output=out / "again.json", stage=cpc.FEEDBACK_STAGE_POST_HANDOFF,
                                                 policy=FAST, prior_status_path=Path(second["status_path"]), state_root=state)
    assert same["relation"] == "IDENTICAL" and same["artifact_identity"] == second["artifact_identity"]


def test_admission_failure_launches_nothing_and_is_a_resource_reason(world, monkeypatch):
    root, state, out = world
    monkeypatch.setattr(guard.subprocess, "Popen", lambda *a, **k: pytest.fail("child must not be launched"))
    refused = _run(root, state, out, policy=guard.ResourcePolicy(**{**FAST.as_dict(), "min_free_disk_bytes": 1 << 60}))
    assert refused["status"] == "UNAVAILABLE" and refused["reason_code"] == guard.RESOURCE_DISK
    assert refused["reason"].startswith("RESOURCE_ADMISSION_REFUSED")


def test_parent_cancellation_terminates_and_reaps_the_child(tmp_path, monkeypatch):
    import tempfile
    temp_logs = lambda: set(Path(tempfile.gettempdir()).glob("feedback-child-*.log"))  # noqa: E731
    logs_before = temp_logs()
    holder = {}
    real_wait = subprocess.Popen.wait

    def cancelling_wait(self, timeout=None):
        if "process" not in holder:
            holder["process"] = self
            raise KeyboardInterrupt
        return real_wait(self, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", cancelling_wait)
    command = [sys.executable, "-c", "import time;time.sleep(300)"]
    with pytest.raises(KeyboardInterrupt):
        guard.run_bounded(command, cwd=tmp_path, policy=guard.ResourcePolicy(**{**FAST.as_dict(), "deadline_seconds": 60}), result_path=tmp_path / "s.json")
    monkeypatch.undo()
    process = holder["process"]
    assert process.poll() is not None  # reaped, not left running
    assert temp_logs() == logs_before  # the child's log is not leaked on cancellation


@pytest.mark.parametrize("exception, expected_exit, reason", [
    (MemoryError(), guard.EXIT_RESOURCE_MEMORY, guard.RESOURCE_MEMORY_LIMIT),
    (OSError(errno.ENOSPC, "No space left on device"), guard.EXIT_RESOURCE_DISK, guard.RESOURCE_DISK),
    (streaming.SourceIntegrityError("x"), guard.EXIT_SOURCE_INTEGRITY, guard.SOURCE_INTEGRITY),
    (streaming.ImmutableOutputConflict("x"), guard.EXIT_IMMUTABLE_CONFLICT, guard.IMMUTABLE_CONFLICT),
    (ValueError("defect"), guard.EXIT_COMPUTATION_ERROR, guard.COMPUTATION_ERROR),
    (OSError(errno.EACCES, "denied"), guard.EXIT_COMPUTATION_ERROR, guard.COMPUTATION_ERROR),
])
def test_child_exit_code_and_reason_mapping_keeps_resource_defect_and_integrity_apart(tmp_path, monkeypatch, exception, expected_exit, reason):
    from tools.run_prospective_decision_outcome_feedback import run_streaming

    def raising(*args, **kwargs):
        raise exception

    monkeypatch.setattr(streaming, "build_streaming_feedback", raising)
    status = tmp_path / "status.json"
    outcome = run_streaming(root=tmp_path, output=tmp_path / "o.json", result=status)
    assert outcome["exit"] == expected_exit and json.loads(status.read_text())["reason_code"] == reason
    assert json.loads(status.read_text())["status"] in {"RESOURCE_UNAVAILABLE", "FAILED"}


def test_corrupted_terminal_caches_never_change_the_result(world):
    root, state, out = world
    first = _run(root, state, out)
    for path in list(state.rglob("*.json")):
        path.write_bytes(b"\x00\xff not json")
    for cache in (root / "operations-review/prospective-decision-outcome-feedback-v1").glob("_*cache.json"):
        cache.write_bytes(b"{")
    second = cpc.run_bounded_prospective_feedback(root, "2026-02-10", output=out / "second.json", stage=cpc.FEEDBACK_STAGE_POST_HANDOFF,
                                                   policy=FAST, state_root=state)
    assert second["artifact_identity"] == first["artifact_identity"]
