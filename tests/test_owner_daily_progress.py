"""Offline acceptance tests for owner_daily_progress/v1."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

import daily_session_level2_package as level2
import mva_exact_session_snapshot as snapshotter
import owner_daily_progress as progress
from tools import run_owner_daily as owner_daily


VN = timezone(timedelta(hours=7))


@pytest.mark.skipif(os.name != "nt", reason="Windows native process memory API")
def test_native_windows_rss_is_observable_for_current_and_opened_process():
    current_rss, current_peak = progress._memory_for_pid(os.getpid())
    assert current_rss is not None and current_rss > 0
    assert current_peak is not None and current_peak >= current_rss
    # Exercise the real pointer-sized OpenProcess/CloseHandle path as well as the
    # pseudo-handle path, without creating a subprocess or acquiring any data.
    kernel32, psapi = progress._windows_apis()
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, os.getpid())
    assert handle
    try:
        counters = progress.PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = progress.ctypes.sizeof(counters)
        assert psapi.GetProcessMemoryInfo(handle, progress.ctypes.byref(counters), counters.cb)
        assert counters.WorkingSetSize > 0
        assert counters.PeakWorkingSetSize >= counters.WorkingSetSize
    finally:
        assert kernel32.CloseHandle(handle)


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeSampler:
    def __init__(self, *, rss: int | None = 20, disk: int | None = 20 * 1024**3, output: int | None = 40) -> None:
        self.rss, self.disk, self.output = rss, disk, output
        self.child_pid = None

    def set_child_pid(self, pid):
        self.child_pid = pid

    def set_run_output_paths(self, _paths):
        pass

    def sample(self):
        return {
            "rss_bytes": self.rss,
            "peak_rss_bytes": self.rss,
            "child_rss_bytes": None,
            "recursive_child_tree_rss_bytes": None,
            "disk_free_bytes": self.disk,
            "run_output_bytes": self.output,
        }


def _emitter(tmp_path: Path, clock: FakeClock, sampler: FakeSampler | None = None):
    lines: list[str] = []
    sidecar = tmp_path / "stock_lookup_daily_20260930_170214.progress.jsonl"
    return progress.OwnerDailyProgress(
        sidecar, session="2026-09-30", sampler=sampler or FakeSampler(), clock=clock,
        wall_clock=lambda: datetime(2026, 9, 30, 17, 2, 14, tzinfo=VN), human_sink=lines.append,
        throttle_seconds=999,
    ), sidecar, lines


def test_event_schema_percent_and_eta_known_are_operational_only(tmp_path):
    clock = FakeClock(); emitter, sidecar, lines = _emitter(tmp_path, clock)
    emitter.emit(
        phase_index=2, component="DNSE exact-session", subtask="futures_completed", progress_kind="REQUESTS",
        completed=0, total=16, qualified_count=0, coverage_denominator=20, status="BEGIN",
    )
    clock.value = 8.0
    event = emitter.emit(
        phase_index=2, component="DNSE exact-session", subtask="futures_completed", progress_kind="REQUESTS",
        completed=8, total=16, qualified_count=7, coverage_denominator=20, status="IN_PROGRESS",
    )
    required = {
        "contract_version", "authority_effect", "timestamp", "run_id", "writer_role", "writer_pid",
        "session", "session_state", "phase_index", "phase_total",
        "phase_name", "component", "progress_kind", "completed", "total", "percent", "qualified_count",
        "coverage_denominator", "coverage_percent", "rss_bytes", "child_rss_bytes", "peak_rss_bytes",
        "downloaded_bytes", "written_bytes", "run_output_bytes", "disk_free_bytes", "elapsed_seconds", "work_elapsed_seconds",
        "rate_per_second", "eta_seconds", "eta_state", "status", "reason",
    }
    assert required <= event.keys()
    assert event["contract_version"] == progress.CONTRACT_VERSION
    assert event["authority_effect"] == progress.AUTHORITY_EFFECT
    assert event["percent"] == 50.0 and event["coverage_percent"] == 35.0
    assert event["eta_state"] == "KNOWN" and event["eta_seconds"] == 8.0
    assert json.loads(sidecar.read_text(encoding="utf-8").splitlines()[-1]) == event
    assert "Yêu cầu: 8/16 (50.0%)" in lines[-1] and "Nến đúng phiên: 7/20 (35.0%)" in lines[-1]


def test_unknown_or_zero_denominators_and_overcomplete_display_are_safe(tmp_path):
    clock = FakeClock(); emitter, _sidecar, _lines = _emitter(tmp_path, clock); clock.value = 4
    unknown = emitter.emit(phase_index=6, component="GitHub publication", progress_kind="PUBLICATION",
                           completed=None, total=None, status="BEGIN")
    zero = emitter.emit(phase_index=2, component="DNSE", progress_kind="REQUESTS", completed=0, total=0)
    clock.value = 8
    over = emitter.emit(phase_index=2, component="DNSE", progress_kind="REQUESTS", completed=12, total=10)
    assert unknown["percent"] is None and unknown["eta_state"] == "UNKNOWN"
    assert zero["percent"] is None and zero["eta_state"] == "UNKNOWN"
    assert over["percent"] == 100.0 and over["eta_state"] == "COMPLETE"
    assert progress.percent(12, 10) == 100.0


def test_eta_requires_a_meaningful_elapsed_sample():
    assert progress.eta(completed=1, total=10, elapsed_seconds=0.5) == (None, "UNKNOWN", None)
    assert progress.eta(completed=0, total=10, elapsed_seconds=10) == (None, "UNKNOWN", None)


def test_initial_eta_uses_bounded_successful_history_median_and_excludes_resume(tmp_path):
    for index, duration in enumerate((10, 20, 900, 99999)):
        base = tmp_path / f"stock_lookup_daily_2026100{index + 1}"
        base.with_suffix(".result.json").write_text(json.dumps({
            "status": "PASS", "session": "2026-10-02",
            "daily_status": "ALREADY_COMPLETED / REUSED" if index == 3 else "COMPLETED",
        }), encoding="utf-8")
        base.with_suffix(".progress.jsonl").write_text(json.dumps({
            "writer_role": "OWNER_PARENT", "status": "END", "phase_index": 2,
            "component": progress.PHASES[2], "session": "2026-10-02", "work_elapsed_seconds": duration,
        }) + "\n", encoding="utf-8")
    assert progress.recent_phase_estimates(tmp_path) == {2: 20.0}
    assert progress.recent_phase_estimates(tmp_path, limit=2) == {}


def test_nine_vietnamese_rows_and_sparse_phase_output_without_fake_heartbeat_eta(tmp_path):
    clock = FakeClock(); emitter, sidecar, lines = _emitter(tmp_path, clock)
    emitter.start_view({2: 100})
    rows = [line for line in lines if line.startswith("[")]
    assert [line.split("]")[0] for line in rows] == [f"[{i}/9" for i in range(1, 10)]
    assert "ETA: ~00:01:40" in rows[1]
    assert "đang ước tính" in rows[0]
    emitter.emit(phase_index=2, status="BEGIN")
    count = len(lines)
    for tick in (30, 60, 90):
        clock.value = tick
        emitter.emit(phase_index=2, status="RUNNING")
    assert len(lines) == count
    emitter.emit(phase_index=2, status="END")
    assert "XONG" in lines[-1] and "Thời gian: 00:01:30" in lines[-1]
    assert all("\x1b" not in line and "RAM" not in line for line in lines)
    assert len(sidecar.read_text(encoding="utf-8").splitlines()) == 5


def test_write_and_metric_failures_are_degraded_without_raising(tmp_path):
    blocked_parent = tmp_path / "not_a_directory"
    blocked_parent.write_text("fixture", encoding="utf-8")
    clock = FakeClock(4)
    emitter = progress.OwnerDailyProgress(
        blocked_parent / "progress.jsonl", sampler=FakeSampler(rss=None, disk=None, output=None),
        clock=clock, human_sink=lambda _line: None,
    )
    event = emitter.emit(phase_index=2, component="DNSE", progress_kind="REQUESTS", completed=1, total=2)
    assert event["rss_bytes"] is None and event["disk_free_bytes"] is None and event["run_output_bytes"] is None
    summary = emitter.summary()
    assert summary["status"] == "DEGRADED"
    assert any(reason.startswith("PROGRESS_WRITE_FAILED") for reason in summary["warnings"])


def _exact_fetcher(calls: list[str]):
    stamp = int(datetime(2026, 8, 20, 9, tzinfo=VN).timestamp())

    def fetcher(_capability, **kwargs):
        calls.append(kwargs["query"]["symbol"])
        return {"ok": True, "endpoint": "/price/ohlc", "body": {
            "t": [stamp], "o": [1], "h": [1], "l": [1], "c": [1], "v": [10],
        }}
    return fetcher


def test_snapshot_callback_is_identity_compatible_and_does_not_add_requests():
    requested_at = datetime(2026, 8, 20, 16, tzinfo=VN)
    without_calls: list[str] = []
    with_calls: list[str] = []
    baseline = snapshotter.materialize_snapshot(
        candidates=["AAA", "BBB"], requested_at=requested_at, api_key="k", api_secret="s",
        fetcher=_exact_fetcher(without_calls), workers=1,
    )
    events: list[dict] = []
    observed = snapshotter.materialize_snapshot(
        candidates=["AAA", "BBB"], requested_at=requested_at, api_key="k", api_secret="s",
        fetcher=_exact_fetcher(with_calls), workers=1, progress_callback=events.append,
    )
    assert observed == baseline
    assert observed["snapshot_identity"] == baseline["snapshot_identity"]
    assert without_calls == with_calls == ["AAA", "BBB"]
    assert [event["completed"] for event in events] == [0, 1, 2]
    assert events[-1]["total"] == 2 and events[-1]["qualified_count"] == 2
    assert events[-1]["downloaded_bytes"] is None
    assert events[-1]["downloaded_bytes_reason"] == "PAYLOAD_BYTES_NOT_OBSERVABLE"


def test_level2_batch_callbacks_are_structured_and_do_not_parse_console(tmp_path, monkeypatch):
    snapshot = tmp_path / "exact.json"
    snapshot.write_text(json.dumps({"records": {f"T{i:03d}": {} for i in range(201)}}), encoding="utf-8")
    calls: list[list[str]] = []
    events: list[dict] = []
    monkeypatch.setattr(level2, "run_cmd", lambda _root, argv: calls.append(argv))

    level2._materialize_liquidity_batches(tmp_path, snapshot, tmp_path / "liquidity", "2026-09-30", 12, events.append)

    batch_events = [event for event in events if event["subtask"] == "batch_materialization"]
    assert [event["completed"] for event in batch_events] == [0, 1, 2, 3]
    assert all(event["total"] == 3 for event in batch_events)
    assert all(event.get("qualified_count") is None for event in events)
    assert len(calls) == 4 and calls[-1][-1] == "--consolidate"


def test_owner_result_receives_only_additive_operational_telemetry(tmp_path, monkeypatch):
    result_path = tmp_path / "owner.result.json"
    progress_path = tmp_path / "owner.progress.jsonl"
    analytical_identity = "canonical_daily_operation:fixture"
    monkeypatch.setattr(owner_daily, "run_workflow", lambda **_kwargs: {
        "status": "PASS", "session": "2026-09-30", "operation_identity": analytical_identity,
    })
    assert owner_daily.main(["--result-path", str(result_path), "--progress-path", str(progress_path)]) == 0
    written = json.loads(result_path.read_text(encoding="utf-8"))
    assert written["operation_identity"] == analytical_identity
    assert written["telemetry"]["contract_version"] == progress.CONTRACT_VERSION
    assert written["telemetry"]["authority_effect"] == progress.AUTHORITY_EFFECT


def test_replay_emits_begin_and_end_for_all_existing_owner_phases(tmp_path, monkeypatch):
    from tests.test_owner_daily_workflow import SESSION, _ready_dashboard, _write_completion

    _write_completion(tmp_path)
    runtime = tmp_path / "runtime"; runtime.mkdir(); (runtime / "bundle_manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(owner_daily, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(owner_daily, "preflight_consumer_repository", lambda *a, **k: {"head": "consumer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(owner_daily, "preflight_dashboard_repository", lambda *a, **k: {"head": "dashboard", "status": "UP_TO_DATE"})
    monkeypatch.setattr(owner_daily, "commit_daily_state", lambda *a, **k: {"sha": "producer", "status": "NO_CHANGE"})
    monkeypatch.setattr(owner_daily, "_presentation_bound_state", lambda *a, **k: "LEGITIMATE_UNAVAILABLE")
    monkeypatch.setattr(owner_daily, "_verify_dashboard_published", lambda *a, **k: None)
    monkeypatch.setattr(owner_daily, "publish_dashboard_release", _ready_dashboard)
    monkeypatch.setattr(owner_daily, "_verify_ai_handoff_published", lambda *a, **k: None)
    monkeypatch.setattr(owner_daily, "publish_ai_handoff", lambda *a, **k: {"remote": {"remote_sha": "ai"}})
    monkeypatch.setattr(owner_daily, "_verify_action_center_ready", lambda *a, **k: None)
    monkeypatch.setattr(owner_daily, "materialize_action_center", lambda *a, **k: {
        "status": "READY", "session": SESSION, "json_path": "private.json", "view_path": "private.md",
    })
    monkeypatch.setattr(owner_daily, "open_action_center_view", lambda *a, **k: {"status": "READY"})

    clock = FakeClock(); telemetry, sidecar, _lines = _emitter(tmp_path, clock)
    result = owner_daily.run_workflow(
        root=tmp_path, runtime_root=runtime, handoff_repo=tmp_path / "handoff",
        dashboard_web_dir=tmp_path / "dashboard", replay_completed_session=SESSION, telemetry=telemetry,
    )

    assert result["status"] == "PASS"
    events = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    for phase in range(1, 10):
        statuses = [event["status"] for event in events if event["phase_index"] == phase]
        assert "BEGIN" in statuses and "END" in statuses
    begins = [event["phase_index"] for event in events if event["status"] == "BEGIN"]
    assert begins == list(range(1, 10))


class CountingSampler(FakeSampler):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def sample(self):
        self.calls += 1
        return super().sample()


def test_resource_sampling_is_cached_for_more_than_one_hundred_request_events(tmp_path):
    clock = FakeClock()
    sampler = CountingSampler()
    emitter, _sidecar, _lines = _emitter(tmp_path, clock, sampler)
    emitter.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                 completed=0, total=101, status="BEGIN")
    for completed in range(1, 101):
        emitter.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                     completed=completed, total=101, status="IN_PROGRESS")
    emitter.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                 completed=101, total=101, status="COMPLETED")
    assert sampler.calls == 2


def test_resource_refresh_interval_begin_end_and_final_summary_are_forced(tmp_path):
    clock = FakeClock()
    sampler = CountingSampler()
    emitter, _sidecar, _lines = _emitter(tmp_path, clock, sampler)
    emitter.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                 completed=0, total=10, status="BEGIN")
    clock.value = 4.9
    emitter.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                 completed=1, total=10, status="IN_PROGRESS")
    clock.value = 5.0
    emitter.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                 completed=2, total=10, status="IN_PROGRESS")
    emitter.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                 completed=3, total=10, status="END")
    assert sampler.calls == 3
    clock.value = 6.0
    emitter.summary()
    assert sampler.calls == 4


def test_resource_sampler_deduplicates_explicit_current_output_roots(tmp_path):
    root = tmp_path / "attempt"
    sampler = progress.ResourceSampler()
    sampler.set_run_output_paths([root, root, root / ".." / "attempt"])
    assert sampler.run_output_paths == (root.resolve(),)


def test_run_origin_and_work_eta_are_distinct_across_parent_and_child(tmp_path):
    clock = FakeClock(100.0)
    parent, sidecar, _lines = _emitter(tmp_path, clock)
    parent.run_id = "owner-run"
    parent.run_started_monotonic = 100.0
    parent.run_started_at = "2026-09-30T10:00:00+00:00"
    parent.emit(phase_index=1, progress_kind="PIPELINE", status="BEGIN")
    clock.value = 500.0
    child = progress.OwnerDailyProgress(
        sidecar, session="2026-09-30", sampler=FakeSampler(), clock=clock,
        wall_clock=lambda: datetime(2026, 9, 30, 17, 2, 14, tzinfo=VN), human_sink=None,
        run_id=parent.run_id, run_started_monotonic=parent.run_started_monotonic,
        run_started_at=parent.run_started_at, writer_role="DAILY_CHILD",
    )
    child.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
               completed=0, total=8, status="BEGIN")
    clock.value = 508.0
    event = child.emit(phase_index=2, component="DNSE", subtask="requests", progress_kind="REQUESTS",
                       completed=4, total=8, status="IN_PROGRESS")
    assert event["elapsed_seconds"] == 408.0
    assert event["work_elapsed_seconds"] == 8.0
    assert event["eta_seconds"] == 8.0
    events = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert {event["run_id"] for event in events} == {"owner-run"}
    assert [event["writer_role"] for event in events] == ["OWNER_PARENT", "DAILY_CHILD", "DAILY_CHILD"]


def test_reused_snapshot_is_not_rendered_as_request_work(tmp_path):
    clock = FakeClock()
    emitter, _sidecar, lines = _emitter(tmp_path, clock)
    emitter.emit(phase_index=2, component="DNSE exact-session", progress_kind="REQUESTS",
                 completed=100, total=100, qualified_count=98, coverage_denominator=100, status="REUSED")
    assert "dùng lại dữ liệu phiên đã hoàn tất" in lines[-1]
    assert "req 100/100" not in lines[-1]


def test_summary_skips_one_malformed_progress_line_and_keeps_later_events(tmp_path):
    clock = FakeClock()
    emitter, sidecar, _lines = _emitter(tmp_path, clock)
    emitter.emit(phase_index=1, progress_kind="PIPELINE", status="BEGIN")
    with sidecar.open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")
    emitter.emit(phase_index=1, progress_kind="PIPELINE", status="END")
    summary = emitter.summary()
    assert summary["event_count"] == 2
    assert summary["status"] == "DEGRADED"
    assert "MALFORMED_PROGRESS_LINE" in summary["warnings"]


def test_unsafe_progress_path_is_disabled_without_failing_owner_result(tmp_path, monkeypatch):
    root = tmp_path / "producer"
    root.mkdir()
    result_path = tmp_path / "owner.result.json"
    unsafe = root / "would-dirty-checkout.progress.jsonl"
    captured = {}
    monkeypatch.setattr(owner_daily, "ROOT", root)

    def fake_workflow(**kwargs):
        captured["telemetry"] = kwargs["telemetry"]
        return {"status": "PASS", "session": "2026-09-30"}

    monkeypatch.setattr(owner_daily, "run_workflow", fake_workflow)
    assert owner_daily.main(["--result-path", str(result_path), "--progress-path", str(unsafe)]) == 0
    assert not unsafe.exists()
    written = json.loads(result_path.read_text(encoding="utf-8"))
    assert written["telemetry"]["status"] == "DEGRADED"
    assert "UNSAFE_PROGRESS_PATH" in written["telemetry"]["warnings"]


def test_run_daily_passes_shared_child_environment_and_writes_before_popen(tmp_path, monkeypatch):
    from tools import check_owner_daily_host_preflight as host_preflight
    monkeypatch.setattr(host_preflight, "check", lambda *a: {"classification": "READY"})
    events: list[str] = []
    captured = {}

    class Telemetry:
        progress_path = tmp_path / "owner.progress.jsonl"

        def child_environment(self):
            return {
                progress.RUN_ID_ENV: "owner-run",
                progress.RUN_STARTED_AT_ENV: "2026-09-30T10:00:00+00:00",
                progress.RUN_STARTED_MONOTONIC_ENV: "100.0",
            }

        def emit(self, **kwargs):
            events.append(kwargs["status"])

        def set_child_pid(self, _pid):
            events.append("PID_SET")

    class Process:
        pid = 123

        def wait(self):
            assert events == ["CHILD_STARTING", "PID_SET"]
            return 7

    def fake_popen(_argv, **kwargs):
        assert events == ["CHILD_STARTING"]
        captured.update(kwargs["env"])
        return Process()

    monkeypatch.setattr(owner_daily.subprocess, "Popen", fake_popen)
    with pytest.raises(owner_daily.OwnerDailyError, match="CANONICAL_DAILY_EXIT_7"):
        owner_daily._run_daily(tmp_path, tmp_path / "runtime", telemetry=Telemetry())
    assert captured[progress.PROGRESS_PATH_ENV] == str(Telemetry.progress_path)
    assert captured[progress.RUN_ID_ENV] == "owner-run"
    assert captured[progress.RUN_STARTED_MONOTONIC_ENV] == "100.0"
    assert events == ["CHILD_STARTING", "PID_SET", "PID_SET"]


def test_post_close_registers_only_the_current_exact_session_output_root(tmp_path, monkeypatch):
    import canonical_post_close_pipeline as post_close
    import daily_execution_environment as execution_environment

    session = "2026-09-30"
    attempt_root = tmp_path / "current-attempt"
    paths = level2.session_artifact_paths(attempt_root, session)
    captured: list[dict] = []
    monkeypatch.setattr(execution_environment, "missing_retained_inputs", lambda *args, **kwargs: [])
    monkeypatch.setattr(execution_environment, "build_resume_plan", lambda *args, **kwargs: {"provider_required_components": []})
    monkeypatch.setattr(post_close, "resolve_acquisition_root", lambda *args, **kwargs: (attempt_root, {}))

    def fake_ensure(*args, **kwargs):
        paths["exact_session_snapshot"].parent.mkdir(parents=True)
        paths["exact_session_snapshot"].write_text(json.dumps({
            "attempted_candidate_count": 1,
            "exact_session_observed_count": 1,
            "resolved_completed_session": session,
        }), encoding="utf-8")
        paths["session_triage"].parent.mkdir(parents=True)
        paths["session_triage"].write_text(json.dumps({
            "source_market_session": session, "artifact_identity": "triage:test",
        }), encoding="utf-8")

    monkeypatch.setattr(level2, "ensure_exact_session_snapshot", fake_ensure)
    monkeypatch.setattr(level2, "materialize_independent_components", lambda *args, **kwargs: None)
    monkeypatch.setattr(level2, "maybe_build_triage_dependent", lambda *args, **kwargs: {"status": "SKIPPED"})
    post_close.acquire_and_materialize(
        tmp_path, session, tmp_path / "runtime", now=datetime(2026, 9, 30, 16, tzinfo=VN),
        progress_callback=captured.append,
    )
    begin = next(event for event in captured if event["status"] == "BEGIN")
    assert begin["run_output_paths"] == [str(paths["exact_session_snapshot"].parent)]
    assert str(paths["official_universe"].parent) not in begin["run_output_paths"]



def test_compact_heartbeat_retains_resource_sidecar_and_surfaces_threshold(tmp_path):
    clock = FakeClock(); sampler = FakeSampler(disk=20 * 1024**3)
    emitter, sidecar, lines = _emitter(tmp_path, clock, sampler)
    emitter.emit(phase_index=2, component="Prospective decision feedback", status="BEGIN")
    clock.value = 30
    event = emitter.emit(phase_index=2, component="Prospective decision feedback", status="RUNNING")
    assert lines == []
    assert json.loads(sidecar.read_text().splitlines()[-1])["rss_bytes"] == event["rss_bytes"] == 20
    sampler.disk = 9 * 1024**3; clock.value = 60
    emitter.emit(phase_index=2, component="Prospective decision feedback", status="RUNNING")
    assert "CẢNH BÁO: dung lượng đĩa thấp" in lines[-1]
    assert all(word not in lines[-1] for word in ("RAM", "FREE", "OUT", "Prospective"))
    warning_count = len(lines)
    clock.value = 90
    emitter.emit(phase_index=2, component="Prospective decision feedback", status="RUNNING")
    assert len(lines) == warning_count


def test_completion_percentage_is_requests_and_reuse_is_coverage(tmp_path):
    clock = FakeClock(); emitter, _, lines = _emitter(tmp_path, clock)
    kwargs = dict(phase_index=2, component="DNSE exact-session", progress_kind="REQUESTS",
                  completed=1683, total=1683, qualified_count=852, coverage_denominator=1683)
    emitter.emit(**kwargs, status="END")
    assert "Yêu cầu: 1683/1683 (100.0%)" in lines[-1]
    assert "Nến đúng phiên: 852/1683 (50.6%)" in lines[-1] and "ĐANG CHẠY" in lines[-1]
    emitter.emit(**kwargs, status="REUSED")
    assert "dùng lại dữ liệu phiên đã hoàn tất" in lines[-1]
    assert "Yêu cầu:" not in lines[-1]


def test_named_foreground_subprocess_heartbeat_preserves_captured_result(tmp_path, monkeypatch):
    clock = FakeClock(); emitter, _, lines = _emitter(tmp_path, clock)
    monkeypatch.setattr(progress, "progress_from_environment", lambda **_kwargs: emitter)
    class Child:
        returncode = 0
        calls = 0
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def communicate(self, timeout):
            assert timeout == 30
            self.calls += 1
            if self.calls == 1:
                clock.value = 30
                raise progress.subprocess.TimeoutExpired("fixture", timeout)
            return "retained stdout", "retained stderr"
    monkeypatch.setattr(progress.subprocess, "Popen", lambda *a, **k: Child())
    result = progress.run_observed_subprocess(["python", "fixture.py"], component="Prospective decision feedback",
                                             capture_output=True, text=True)
    assert result.stdout == "retained stdout" and result.stderr == "retained stderr" and result.returncode == 0
    assert lines == []


def test_local_complete_checkpoint_is_distinct_from_owner_terminal(capsys):
    from canonical_daily_operation import print_daily_operation_handoff
    print_daily_operation_handoff({"daily_operation_state": "LOCAL_COMPLETE", "session": "2026-10-01"})
    output = capsys.readouterr().out
    assert "DAILY_OPERATION_STATE=LOCAL_COMPLETE" in output
    assert "CANONICAL_DAILY_LOCAL_COMPLETE - wrapper publication/verification phases still pending" in output


def test_retry_changes_and_failure_surface_without_repeating_healthy_counters(tmp_path):
    clock = FakeClock(); emitter, _, lines = _emitter(tmp_path, clock, FakeSampler(disk=20 * 1024**3))
    kwargs = dict(phase_index=2, component="DNSE exact-session", progress_kind="REQUESTS", total=100,
                  success_count=1, failure_count=0)
    emitter.emit(**kwargs, completed=1, retry_count=0, status="BEGIN")
    clock.value = 30
    emitter.emit(**kwargs, completed=2, retry_count=0, status="RUNNING")
    assert "retry" not in lines[-1]
    emitter.emit(**kwargs, completed=3, retry_count=1, status="IN_PROGRESS")
    assert "Retry: 1" in lines[-1]
    emitter.emit(**kwargs, completed=4, retry_count=1, status="FAILED")
    assert "LỖI" in lines[-1] and "RAM" not in lines[-1] and "Retry: 1" in lines[-1]


def test_subprocess_without_telemetry_uses_original_runner(monkeypatch):
    monkeypatch.setattr(progress, "progress_from_environment", lambda **_kwargs: None)
    expected = progress.subprocess.CompletedProcess(["fixture"], 7, "stdout", "stderr")
    calls = []
    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return expected
    monkeypatch.setattr(progress.subprocess, "run", runner)
    assert progress.run_observed_subprocess(["fixture"], capture_output=True, text=True) is expected
    assert calls == [(["fixture"], {"capture_output": True, "text": True})]


def test_periodic_sampler_never_walks_output_tree(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(progress, "_path_size", lambda paths: calls.append(paths) or 123)
    sampler = progress.ResourceSampler(disk_path=tmp_path, run_output_paths=(tmp_path,))
    for _ in range(10):
        sample = sampler.sample()
        assert sample["disk_free_bytes"] is not None
        assert sample["run_output_bytes"] is None
    assert not calls
    sampler.sample_output_size()
    assert sampler.sample()["run_output_bytes"] == 123
    assert len(calls) == 1


def test_phase_boundary_sizing_configurable(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(progress, "_path_size", lambda paths: calls.append(paths) or 123)
    sampler = progress.ResourceSampler(disk_path=tmp_path, run_output_paths=(tmp_path,))
    emitter = progress.OwnerDailyProgress(tmp_path / "diagnostics.jsonl", sampler=sampler, human_sink=None)
    emitter._resources(0, force=True, size_outputs=True)
    for t in (6, 12, 18):
        emitter._resources(t)
    assert len(calls) == 1
    sampler.size_outputs_at_boundaries = False
    emitter._resources(24, force=True, size_outputs=True)
    assert len(calls) == 1


def test_request_completion_resource_refresh_is_not_tree_size_boundary(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(progress, "_path_size", lambda paths: calls.append(paths) or 123)
    sampler = progress.ResourceSampler(disk_path=tmp_path, run_output_paths=(tmp_path,))
    emitter = progress.OwnerDailyProgress(tmp_path / "diagnostic.jsonl", sampler=sampler, human_sink=None)
    for _ in range(10):
        emitter.emit(phase_index=2, component="DNSE request", progress_kind="REQUESTS", completed=1, total=1, status="END")
    assert not calls
    emitter.emit(phase_index=2, status="BEGIN")
    emitter.emit(phase_index=2, status="END")
    assert len(calls) == 2


# OWNER_DAILY_HOST_CAPACITY_AND_PREFLIGHT_CORRECTIVE_20261005 -- the 2026-10-05 run showed
# "[2/9] Chạy Daily chuẩn | ĐANG CHẠY" before the mandatory host gate reported BLOCKED.
def _fresh_workflow_fixture(tmp_path, monkeypatch, classification):
    from functools import partial
    from tools import check_owner_daily_host_preflight as host_preflight

    monkeypatch.setattr(owner_daily, "_resolve_intended_session", lambda: "2026-10-05")
    monkeypatch.setattr(owner_daily, "_auto_resumable_session", lambda *a, **k: None)
    monkeypatch.setattr(owner_daily, "preflight_repository", lambda *a, **k: {"head": "producer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(owner_daily, "preflight_consumer_repository", lambda *a, **k: {"head": "consumer", "status": "UP_TO_DATE"})
    monkeypatch.setattr(owner_daily, "preflight_dashboard_repository", lambda *a, **k: {"head": "dashboard", "status": "UP_TO_DATE"})
    calls: list[str] = []

    def check(*_args):
        calls.append("host_preflight")
        return {"classification": classification, "operator_guidance": host_preflight.GUIDANCE}

    monkeypatch.setattr(host_preflight, "check", check)
    monkeypatch.setattr(owner_daily, "run_workflow", partial(owner_daily.run_workflow, root=tmp_path))
    return calls


@pytest.mark.parametrize("classification", ["BLOCKED", "AMBER"])
def test_canonical_daily_never_begins_before_host_preflight_accepts(tmp_path, monkeypatch, classification):
    calls = _fresh_workflow_fixture(tmp_path, monkeypatch, classification)
    monkeypatch.setattr(owner_daily.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch"))
    result_path, sidecar = tmp_path / "logs" / "owner.result.json", tmp_path / "logs" / "owner.progress.jsonl"

    assert owner_daily.main(["--result-path", str(result_path), "--progress-path", str(sidecar),
                             "--runtime-root", str(tmp_path / "runtime")]) == 1

    assert calls == ["host_preflight"]
    events = [(e["phase_index"], e["status"]) for e in map(json.loads, sidecar.read_text(encoding="utf-8").splitlines())]
    assert events == [(1, "BEGIN"), (1, "FAILED")]
    written = json.loads(result_path.read_text(encoding="utf-8"))
    assert written["status"] == "FAILED" and written["failed_step"] == "Host preflight"
    assert written["reason"] == "OWNER_DAILY_HOST_PREFLIGHT_" + classification
    # Nested telemetry health is explicit and can never be read as the run outcome.
    assert written["telemetry"]["telemetry_health"] == written["telemetry"]["status"] == "READY"
    assert written["telemetry"]["status_scope"] == progress.STATUS_SCOPE == "TELEMETRY_SIDECAR_HEALTH_ONLY_NOT_RUN_OUTCOME"


def test_ready_host_gate_closes_phase_one_before_canonical_daily_begins_and_is_not_rerun(tmp_path, monkeypatch):
    calls = _fresh_workflow_fixture(tmp_path, monkeypatch, "READY")

    class Process:
        pid = 4242

        def wait(self):
            return 7  # The existing canonical child gate still refuses; nothing downstream runs.

    def launch(*_a, **_k):
        calls.append("popen")
        return Process()

    monkeypatch.setattr(owner_daily.subprocess, "Popen", launch)
    result_path, sidecar = tmp_path / "logs" / "owner.result.json", tmp_path / "logs" / "owner.progress.jsonl"

    assert owner_daily.main(["--result-path", str(result_path), "--progress-path", str(sidecar),
                             "--runtime-root", str(tmp_path / "runtime")]) == 1

    assert calls == ["host_preflight", "popen"]
    events = [(e["phase_index"], e["status"]) for e in map(json.loads, sidecar.read_text(encoding="utf-8").splitlines())]
    assert events[:3] == [(1, "BEGIN"), (1, "END"), (2, "BEGIN")]
    assert (2, "FAILED") in events
    written = json.loads(result_path.read_text(encoding="utf-8"))
    assert written["status"] == "FAILED" and written["reason"] == "CANONICAL_DAILY_EXIT_7"


def test_telemetry_summary_health_fields_are_consistent_when_degraded(tmp_path):
    emitter, _sidecar, _lines = _emitter(tmp_path, FakeClock())
    emitter.report_degraded("UNSAFE_PROGRESS_PATH")
    summary = emitter.summary()
    assert summary["status"] == summary["telemetry_health"] == "DEGRADED"
    assert summary["status_scope"] == progress.STATUS_SCOPE
