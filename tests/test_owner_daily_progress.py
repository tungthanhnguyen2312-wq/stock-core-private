"""Offline acceptance tests for owner_daily_progress/v1."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

import daily_session_level2_package as level2
import mva_exact_session_snapshot as snapshotter
import owner_daily_progress as progress
from tools import run_owner_daily as owner_daily


VN = timezone(timedelta(hours=7))


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeSampler:
    def __init__(self, *, rss: int | None = 20, disk: int | None = 30, output: int | None = 40) -> None:
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
    assert "req 8/16 50.0%" in lines[-1] and "exact 7/20 35.0%" in lines[-1]


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
    assert "reused 100" in lines[-1]
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

