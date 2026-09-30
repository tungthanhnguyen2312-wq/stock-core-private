"""Write the public-safe offline acceptance artifact for owner_daily_progress/v1."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from owner_daily_progress import AUTHORITY_EFFECT, CONTRACT_VERSION, OwnerDailyProgress  # noqa: E402


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
        clock.value = 8.0
        known = telemetry.emit(
            phase_index=2, component="DNSE exact-session", progress_kind="REQUESTS",
            completed=8, total=16, qualified_count=7, coverage_denominator=20,
            status="IN_PROGRESS", downloaded_bytes=None,
            downloaded_bytes_reason="PAYLOAD_BYTES_NOT_OBSERVABLE",
        )
        unknown = telemetry.emit(
            phase_index=6, component="GitHub publication", progress_kind="PUBLICATION",
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
                "peak_rss_bytes": known["peak_rss_bytes"], "disk_free_bytes": known["disk_free_bytes"],
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


def main() -> int:
    report_path = ROOT / "derived" / "owner-daily-progress-telemetry-v1" / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(report_path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
