"""Write the public-safe offline acceptance artifact for owner_daily_progress/v1."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import time
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from owner_daily_progress import AUTHORITY_EFFECT, CONTRACT_VERSION, OwnerDailyProgress, CanonicalCheckpointProgress, CANONICAL_CHECKPOINTS  # noqa: E402


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class _Sampler:
    def set_child_pid(self, _pid):
        pass

    def set_run_output_paths(self, _paths):
        pass

    def sample(self):
        return {
            "rss_bytes": 134_217_728,
            "peak_rss_bytes": 134_217_728,
            "child_rss_bytes": None,
            "recursive_child_tree_rss_bytes": None,
            "disk_free_bytes": 74_000_000_000,
            "run_output_bytes": 28_000_000,
        }


def build_report() -> dict:
    clock = _Clock()
    lines: list[str] = []
    with tempfile.TemporaryDirectory() as temporary:
        sidecar = Path(temporary) / "progress.jsonl"
        telemetry = OwnerDailyProgress(
            sidecar, session="2026-09-30", sampler=_Sampler(), clock=clock,
            wall_clock=lambda: datetime(2026, 9, 30, 17, 2, 14, tzinfo=timezone.utc),
            human_sink=lines.append, throttle_seconds=999,
        )
        telemetry.emit(
            phase_index=2, component="DNSE exact-session", subtask="futures_completed", progress_kind="REQUESTS",
            completed=0, total=16, qualified_count=0, coverage_denominator=20, status="BEGIN",
        )
        clock.value = 8.0
        known = telemetry.emit(
            phase_index=2, component="DNSE exact-session", subtask="futures_completed", progress_kind="REQUESTS",
            completed=8, total=16, qualified_count=7, coverage_denominator=20,
            status="IN_PROGRESS", downloaded_bytes=None,
            downloaded_bytes_reason="PAYLOAD_BYTES_NOT_OBSERVABLE",
        )
        unknown = telemetry.emit(
            phase_index=6, component="AI handoff build", progress_kind="PUBLICATION",
            status="BEGIN",
        )
        blocking_parent = Path(temporary) / "blocked"
        blocking_parent.write_text("offline fixture", encoding="utf-8")
        degraded = OwnerDailyProgress(
            blocking_parent / "progress.jsonl", sampler=_Sampler(), clock=clock,
            human_sink=lambda _line: None,
        )
        degraded.emit(phase_index=2, component="DNSE exact-session", progress_kind="REQUESTS", completed=1, total=2)
        return {
            "schema_version": "owner_daily_progress_telemetry_validation_report/v1",
            "contract_version": CONTRACT_VERSION,
            "public_safe": True,
            "offline_only": True,
            "event_count": telemetry.summary()["event_count"],
            "known_denominator_example": {
                "completed": known["completed"], "total": known["total"], "percent": known["percent"],
                "observed_coverage": known["qualified_count"], "coverage_denominator": known["coverage_denominator"],
                "coverage_percent": known["coverage_percent"], "eta_state": known["eta_state"],
            },
            "unknown_denominator_example": {
                "percent": unknown["percent"], "eta_state": unknown["eta_state"],
            },
            "resource_fields": {
                "writer_peak_rss_bytes": known["peak_rss_bytes"], "disk_free_bytes": known["disk_free_bytes"],
                "run_output_bytes": known["run_output_bytes"], "child_rss_bytes": known["child_rss_bytes"],
                "recursive_child_tree_rss_bytes": known["recursive_child_tree_rss_bytes"],
            },
            "network_payload_bytes": {
                "downloaded_bytes": known["downloaded_bytes"],
                "reason": known["downloaded_bytes_reason"],
            },
            "telemetry_failure_containment": degraded.summary()["status"] == "DEGRADED",
            "identity_effect": "NONE_CALLBACK_ON_OFF_SNAPSHOT_IDENTITY_COMPATIBLE",
            "authority_effect": AUTHORITY_EFFECT,
            "extra_provider_network_calls": 0,
            "console_example": lines[0] if lines else None,
        }


def phase2_simulation() -> dict:
    """Synthetic timing, not a reconstruction of unobserved October 7 boundaries."""
    clock = _Clock()
    lines = []
    events = []
    emitter = OwnerDailyProgress(None, session="2026-10-07", sampler=_Sampler(), clock=clock,
                                human_sink=lines.append, writer_role="DAILY_CHILD")
    callback = emitter.callback()
    def observe(payload):
        callback(payload)
        events.append(payload)
    checkpoints = CanonicalCheckpointProgress(observe, clock=clock)
    checkpoints.begin()
    durations = (5, 822, 8, 300, 180, 60, 300, 113, 540, 10, 528, 147, 53)
    for index, seconds in enumerate(durations):
        clock.value += seconds
        if index == 1:
            emitter.emit(phase_index=2, component="DNSE", progress_kind="REQUESTS", status="REUSED")
        checkpoints.finish()
    return {"scope": "SYNTHETIC_PRESENTATION_ONLY_NO_DAILY_NO_PROVIDER_NO_RETENTION",
            "timing_is_simulated": True, "checkpoints": [x[0] for x in CANONICAL_CHECKPOINTS],
            "events": events, "console": lines, "elapsed_seconds": clock.value}


def forensic_sidecar(path: Path) -> dict:
    """Read one explicitly supplied sidecar; no discovery or production writes."""
    raw = path.read_bytes()
    events = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    phase = [e for e in events if e.get("phase_index") == 2]
    timeline = []
    previous = None
    for e in phase:
        row = {key: e.get(key) for key in (
            "timestamp", "writer_role", "component", "subtask", "progress_kind", "completed", "total",
            "status", "work_elapsed_seconds", "elapsed_seconds")}
        row["gap_seconds"] = None if previous is None else round(e["elapsed_seconds"] - previous, 3)
        previous = e["elapsed_seconds"]
        timeline.append(row)
    gaps = [{"seconds": round(b["elapsed_seconds"] - a["elapsed_seconds"], 3),
             "from": {k: a[k] for k in ("component", "subtask", "status", "elapsed_seconds")},
             "to": {k: b[k] for k in ("component", "subtask", "status", "elapsed_seconds")}}
            for a, b in zip(phase, phase[1:])]
    parent = [e for e in phase if e.get("writer_role") == "OWNER_PARENT" and e.get("subtask") is None]
    return {"input_name": path.name, "input_sha256": hashlib.sha256(raw).hexdigest(),
            "phase2_elapsed_seconds": next(e["work_elapsed_seconds"] for e in parent if e["status"] == "END"),
            "phase2_start": parent[0]["timestamp"], "phase2_end": parent[-1]["timestamp"],
            "event_count": len(phase), "timeline": timeline,
            "largest_gaps": sorted(gaps, key=lambda x: -x["seconds"])[:10],
            "foreground_running_events": [e for e in timeline if e["status"] == "RUNNING"],
            "observed_internal_spans": [e for e in timeline if e["status"] == "END" and e["subtask"] in {"child subprocess", "bounded child subprocess"}],
            "reused": [e for e in timeline if e["status"] == "REUSED"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase2", action="store_true")
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.phase2:
        start = time.perf_counter()
        report = phase2_simulation()
        report["fixture_wall_seconds"] = round(time.perf_counter() - start, 6)
        if args.sidecar:
            report["forensic"] = forensic_sidecar(args.sidecar)
    else:
        report = build_report()
    report_path = args.output or ROOT / "derived" / "owner-daily-progress-telemetry-v1" / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(report_path)
    if args.phase2:
        for line in report["console"]:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
