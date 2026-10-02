"""Foreground-only operational telemetry for the Owner Daily command.

This module deliberately owns no Daily result, artifact, source, request, or authority
decision. It writes an external JSONL sidecar and safe human-readable status lines only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import time
from typing import Any, Callable, Mapping
import uuid


CONTRACT_VERSION = "owner_daily_progress/v1"
AUTHORITY_EFFECT = "NONE_OPERATIONAL_OBSERVABILITY_ONLY"
PROGRESS_PATH_ENV = "STOCK_LOOKUP_OWNER_DAILY_PROGRESS_PATH"
RUN_ID_ENV = "STOCK_LOOKUP_OWNER_DAILY_RUN_ID"
RUN_STARTED_AT_ENV = "STOCK_LOOKUP_OWNER_DAILY_RUN_STARTED_AT"
RUN_STARTED_MONOTONIC_ENV = "STOCK_LOOKUP_OWNER_DAILY_RUN_STARTED_MONOTONIC"
RESOURCE_SAMPLE_INTERVAL_SECONDS = 5.0
PHASE_TOTAL = 9
PHASES = {
    1: "Repository preflight",
    2: "Canonical Daily",
    3: "Daily completion verification",
    4: "Producer state publication",
    5: "Dashboard publication",
    6: "AI handoff build",
    7: "Remote verification",
    8: "Personal Action Center",
    9: "Open owner view",
}
PHASES_VI = dict(enumerate((
    "Kiểm tra kho mã & môi trường", "Chạy Daily chuẩn", "Xác minh hoàn tất Daily",
    "Công bố trạng thái Producer", "Công bố Dashboard", "Tạo gói bàn giao AI",
    "Xác minh từ xa", "Trung tâm Hành động Cá nhân", "Mở màn hình dành cho chủ sở hữu",
), 1))
STRUCTURED_CONSOLE_ENV = "STOCK_LOOKUP_OWNER_STRUCTURED_CONSOLE"


def recent_phase_estimates(log_root: Path, *, limit: int = 30, minimum_samples: int = 3) -> dict[int, float]:
    """Bounded P50 of successful ordinary Daily phases; replay is not timing evidence.

    Read only the most recent result names and their same-name bounded JSONL sidecars.
    Never traverse retained artifacts or infer progress from heartbeats.
    """
    samples: dict[int, list[float]] = {i: [] for i in PHASES}
    for path in sorted(log_root.glob("stock_lookup_daily_*.result.json"), reverse=True)[:limit]:
        try:
            if path.stat().st_size > 2 * 1024**2:
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            if result.get("status") != "PASS" or "REUSED" in str(result.get("daily_status", "")):
                continue
            sidecar = path.with_name(path.name.replace(".result.json", ".progress.jsonl"))
            if sidecar.stat().st_size > 16 * 1024**2:
                continue
            durations = {}
            with sidecar.open(encoding="utf-8") as handle:
                for line in handle:
                    event = json.loads(line)
                    phase = event.get("phase_index")
                    duration = event.get("work_elapsed_seconds")
                    if (event.get("writer_role") == "OWNER_PARENT" and event.get("status") == "END"
                            and phase in PHASES and event.get("component") == PHASES[phase]
                            and isinstance(duration, (int, float)) and not isinstance(duration, bool)
                            and math.isfinite(duration) and duration >= 0
                            and (not result.get("session") or event.get("session") == result["session"])
                            and (not (result.get("telemetry") or {}).get("run_id")
                                 or event.get("run_id") == result["telemetry"]["run_id"])):
                        durations[phase] = float(duration)
            for phase, duration in durations.items():
                samples[phase].append(duration)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return {i: statistics.median(values) for i, values in samples.items() if len(values) >= minimum_samples}


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    """The Windows process-memory layout is stable and cached at module scope."""

    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


_WINDOWS_APIS: tuple[Any, Any] | None = None
_WINDOWS_API_UNAVAILABLE = False


def _windows_apis() -> tuple[Any, Any] | None:
    """Load Windows DLL handles once; non-Windows hosts truthfully report unknown."""
    global _WINDOWS_APIS, _WINDOWS_API_UNAVAILABLE
    if os.name != "nt" or _WINDOWS_API_UNAVAILABLE:
        return None
    if _WINDOWS_APIS is None:
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            # ctypes defaults to 32-bit integer arguments/results. HANDLE is pointer-sized;
            # truncating the current pseudo-handle or OpenProcess result on 64-bit Windows
            # makes GetProcessMemoryInfo fail even for our own process.
            kernel32.GetCurrentProcess.argtypes = []
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_int
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), ctypes.c_ulong,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            _WINDOWS_APIS = (kernel32, psapi)
        except Exception:
            _WINDOWS_API_UNAVAILABLE = True
            return None
    return _WINDOWS_APIS


def _memory_for_pid(pid: int) -> tuple[int | None, int | None]:
    """Return current and OS-reported peak working set for one process, if observable."""
    apis = _windows_apis()
    if apis is None:
        return None, None
    kernel32, psapi = apis
    try:
        is_current = pid == os.getpid()
        handle = kernel32.GetCurrentProcess() if is_current else kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
        if not handle:
            return None, None
        try:
            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None, None
            return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
        finally:
            if not is_current:
                kernel32.CloseHandle(handle)
    except Exception:
        return None, None


def _path_size(paths: tuple[Path, ...]) -> int | None:
    """Size only the explicitly registered current-run roots, never a repository-wide tree."""
    if not paths:
        return None
    total = 0
    try:
        for path in paths:
            if path.is_file():
                total += path.stat().st_size
            elif path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        total += child.stat().st_size
        return total
    except OSError:
        return None


def _deduplicated_paths(paths: list[str | Path] | tuple[str | Path, ...]) -> tuple[Path, ...]:
    """Normalize and de-duplicate explicit run roots without discovering any new path."""
    result: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw).expanduser().resolve(strict=False)
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return tuple(result)


def safe_progress_path(progress_path: Path | str | None, *, root: Path) -> Path | None:
    """Return an external sidecar location, or ``None`` when it would dirty the checkout."""
    if progress_path is None:
        return None
    resolved = Path(os.path.abspath(Path(progress_path).expanduser())).resolve(strict=False)
    checkout = Path(root).resolve(strict=False)
    candidate, base = os.path.normcase(str(resolved)), os.path.normcase(str(checkout))
    if candidate == base or candidate.startswith(base.rstrip(os.sep) + os.sep):
        return None
    return resolved


def percent(completed: int | None, total: int | None) -> float | None:
    """Return a display-safe percentage; unknown/zero denominators stay unknown."""
    if completed is None or total is None or total <= 0:
        return None
    return round(min(max(completed, 0), total) * 100.0 / total, 2)


def eta(*, completed: int | None, total: int | None, elapsed_seconds: float | None,
        minimum_elapsed_seconds: float = 2.0) -> tuple[float | None, str, float | None]:
    """Return ETA/rate only for a non-trivial work sample with a real denominator."""
    if total is None or total <= 0 or completed is None or completed <= 0:
        return None, "UNKNOWN", None
    if elapsed_seconds is None or elapsed_seconds < minimum_elapsed_seconds:
        return None, "UNKNOWN", None
    rate = completed / elapsed_seconds
    if rate <= 0:
        return None, "UNKNOWN", None
    remaining = max(total - completed, 0)
    return remaining / rate, "COMPLETE" if remaining == 0 else "KNOWN", rate


@dataclass
class ResourceSampler:
    """Dependency-free, bounded-on-demand resources for the emitting process only."""

    disk_path: Path = Path("C:\\")
    child_pid: int | None = None
    run_output_paths: tuple[Path, ...] = ()

    def set_child_pid(self, pid: int | None) -> None:
        self.child_pid = pid

    def set_run_output_paths(self, paths: list[str | Path] | tuple[str | Path, ...]) -> None:
        self.run_output_paths = _deduplicated_paths(paths)

    def sample(self) -> dict[str, int | None]:
        try:
            disk_free = int(shutil.disk_usage(self.disk_path).free)
        except Exception:
            disk_free = None
        rss, peak = _memory_for_pid(os.getpid())
        return {
            "rss_bytes": rss,
            "peak_rss_bytes": peak,
            "child_rss_bytes": None,
            "recursive_child_tree_rss_bytes": None,
            "disk_free_bytes": disk_free,
            "run_output_bytes": _path_size(self.run_output_paths),
        }


def _format_bytes(value: int | None) -> str | None:
    if value is None:
        return None
    units = ("B", "KB", "MB", "GB", "TB")
    current = float(value)
    for unit in units:
        if current < 1024 or unit == units[-1]:
            return f"{current:.2f} {unit}" if unit != "B" else f"{int(current)} B"
        current /= 1024
    return None


def _format_duration(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    seconds = max(0, int(round(value)))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


class OwnerDailyProgress:
    """Best-effort event writer and compact human sink for one Owner Daily invocation."""

    def __init__(self, progress_path: Path | str | None, *, session: str | None = None,
                 sampler: ResourceSampler | None = None, clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], datetime] | None = None,
                 human_sink: Callable[[str], None] | None = print, throttle_seconds: float = 3.0,
                 run_id: str | None = None, run_started_monotonic: float | None = None,
                 run_started_at: str | None = None, writer_role: str = "OWNER_PARENT") -> None:
        self.progress_path = Path(progress_path) if progress_path is not None else None
        self.session = session
        self.sampler = sampler or ResourceSampler()
        self.clock = clock
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self.human_sink = human_sink
        self.throttle_seconds = throttle_seconds
        now = clock()
        self.run_id = run_id or uuid.uuid4().hex
        self.run_started_monotonic = now if run_started_monotonic is None else run_started_monotonic
        self.run_started_at = run_started_at or self.wall_clock().astimezone(timezone.utc).isoformat()
        self.writer_role = writer_role
        self.event_count = 0
        self.peak_observed_single_process_rss_bytes: int | None = None
        self.maximum_run_output_bytes: int | None = None
        self.final_disk_free_bytes: int | None = None
        self.degraded_reasons: list[str] = []
        self._last_human_at: float | None = None
        self._last_human_percent: float | None = None
        self._display_peak = 0
        self._display_resource_band = None
        self._display_counters = (0, 0)
        self._resource_cache: dict[str, int | None] | None = None
        self._last_resource_sample_at: float | None = None
        self._work_started: dict[tuple[int, str, str, str], float] = {}
        self.phase_estimates: dict[int, float] = {}
        self._human_buckets: dict[tuple[int, str, str, str], int] = {}
        self._human_counter_history: dict[tuple[int, str, str, str], tuple[Any, Any]] = {}
        self._disk_warning = False
        self.active_phase = 1

    def start_view(self, estimates: Mapping[int, float]) -> None:
        self.phase_estimates = dict(estimates)
        if self.human_sink is None:
            return
        if os.environ.get(STRUCTURED_CONSOLE_ENV) == "1":
            self.human_sink("OWNER_DAILY_PRESENTATION=" + json.dumps({
                "session": self.session, "phase_estimates": self.phase_estimates,
            }, ensure_ascii=False))
        else:
            self.human_sink("=" * 60 + "\n STOCK LOOKUP DAILY\n Ngày: " + (self.session or "đang xác định") + "\n" + "=" * 60)
            for phase, label in PHASES_VI.items():
                estimate = self.phase_estimates.get(phase)
                self.human_sink(f"[{phase}/9] {label} | CHỜ | ETA: " +
                                ("~" + _format_duration(estimate) if estimate is not None else "đang ước tính"))

    def set_session(self, session: str | None) -> None:
        if session:
            self.session = session

    def set_child_pid(self, pid: int | None) -> None:
        self.sampler.set_child_pid(pid)

    def set_run_output_paths(self, paths: list[str | Path] | tuple[str | Path, ...]) -> None:
        self.sampler.set_run_output_paths(paths)

    def report_degraded(self, reason: str) -> None:
        self._degrade(reason)

    def child_environment(self) -> dict[str, str]:
        """Return the explicit, same-host run-origin contract for the Daily child."""
        return {
            RUN_ID_ENV: self.run_id,
            RUN_STARTED_AT_ENV: self.run_started_at,
            RUN_STARTED_MONOTONIC_ENV: repr(self.run_started_monotonic),
        }

    def _degrade(self, reason: str) -> None:
        if reason in self.degraded_reasons:
            return
        self.degraded_reasons.append(reason)
        if self.human_sink is not None:
            try:
                self.human_sink(f"TELEMETRY_DEGRADED: {reason}")
            except Exception:
                pass

    def _write(self, event: Mapping[str, Any]) -> None:
        if self.progress_path is None:
            return
        try:
            self.progress_path.parent.mkdir(parents=True, exist_ok=True)
            with self.progress_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
        except Exception as exc:
            self._degrade("PROGRESS_WRITE_FAILED:" + type(exc).__name__)

    @staticmethod
    def _task_key(phase_index: int, component: str, subtask: str | None, progress_kind: str) -> tuple[int, str, str, str]:
        return phase_index, component, subtask or "", progress_kind

    @staticmethod
    def _forces_resource_refresh(status: str | None, completed: int | None, total: int | None) -> bool:
        return status in {"BEGIN", "END", "FAILED"} or (total is not None and completed == total)

    def _record_resources(self, resources: Mapping[str, int | None]) -> None:
        peak = resources.get("peak_rss_bytes") or resources.get("rss_bytes")
        if isinstance(peak, int):
            self.peak_observed_single_process_rss_bytes = max(
                self.peak_observed_single_process_rss_bytes or peak, peak,
            )
        output = resources.get("run_output_bytes")
        if isinstance(output, int):
            self.maximum_run_output_bytes = max(self.maximum_run_output_bytes or output, output)
        disk = resources.get("disk_free_bytes")
        if isinstance(disk, int):
            self.final_disk_free_bytes = disk

    def _resources(self, now: float, *, force: bool = False) -> dict[str, int | None]:
        refresh = (
            force
            or self._resource_cache is None
            or self._last_resource_sample_at is None
            or now - self._last_resource_sample_at >= RESOURCE_SAMPLE_INTERVAL_SECONDS
        )
        if refresh:
            self._resource_cache = dict(self.sampler.sample())
            self._last_resource_sample_at = now
            self._record_resources(self._resource_cache)
        return dict(self._resource_cache or {})

    def _console_alerts(self, event: Mapping[str, Any]) -> tuple[bool, bool]:
        peak = event.get("peak_rss_bytes") or 0
        disk = event.get("disk_free_bytes")
        band = (peak >= 4 * 1024**3, disk is not None and disk < 10 * 1024**3)
        boundary = event.get("status") in {"BEGIN", "END", "FAILED", "WARN", "PASS", "FAIL"}
        resources = boundary or (any(band) and band != self._display_resource_band)
        resources = resources or peak >= self._display_peak + 512 * 1024**2
        counters = (event.get("retry_count") or 0, event.get("failure_count") or 0)
        return resources, boundary or counters != self._display_counters

    @staticmethod
    def _owner_phase(event: Mapping[str, Any]) -> bool:
        return (event.get("writer_role") == "OWNER_PARENT" and not event.get("subtask")
                and event.get("component") == PHASES.get(event.get("phase_index")))

    @staticmethod
    def _acquisition(event: Mapping[str, Any]) -> bool:
        return (event.get("phase_index") == 2 and event.get("progress_kind") == "REQUESTS"
                and "DNSE" in str(event.get("component", "")).upper()
                and isinstance(event.get("total"), int) and event["total"] > 0)

    def _human_line(self, event: Mapping[str, Any]) -> str:
        phase = event["phase_index"]
        status = event.get("status")
        done = status == "END" and self._owner_phase(event)
        state = "XONG" if done else ("LỖI" if status in {"FAILED", "FAIL"} else
                ("CẢNH BÁO" if status == "WARN" else "ĐANG CHẠY"))
        parts = [f"[{phase}/9] {PHASES_VI.get(phase, 'Daily')}", state]
        if done:
            parts.append("Thời gian: " + _format_duration(event.get("work_elapsed_seconds")))
        else:
            measured = event.get("eta_seconds") if self._acquisition(event) and event.get("eta_state") == "KNOWN" else None
            reference = self.phase_estimates.get(phase) if self._owner_phase(event) else None
            remaining = max(reference - (event.get("work_elapsed_seconds") or 0), 0) if reference is not None else None
            estimate = measured if measured is not None else (remaining if remaining else None)
            parts.append("ETA: " + ("~" + _format_duration(estimate) if estimate is not None else "đang ước tính"))
        if self._acquisition(event):
            if status == "REUSED":
                parts.append("DNSE: dùng lại dữ liệu phiên đã hoàn tất")
            else:
                parts.append("DNSE exact-session")
                if event.get("completed") is not None:
                    parts.append(f"Yêu cầu: {event['completed']}/{event['total']} ({event.get('percent') or 0:.1f}%)")
                if event.get("qualified_count") is not None and event.get("coverage_denominator"):
                    parts.append(f"Nến đúng phiên: {event['qualified_count']}/{event['coverage_denominator']} ({event.get('coverage_percent') or 0:.1f}%)")
                counters = []
                for key, label in (("success_count", "Thành công"), ("retry_count", "Retry"), ("failure_count", "Lỗi")):
                    if event.get(key) is not None:
                        counters.append(f"{label}: {event[key]}")
                if counters:
                    parts.append("; ".join(counters))
        disk = event.get("disk_free_bytes")
        if isinstance(disk, int) and disk < 10 * 1024**3:
            parts.append("CẢNH BÁO: dung lượng đĩa thấp")
        return " | ".join(parts)

    def _should_write_human(self, event: Mapping[str, Any], now: float) -> bool:
        disk = event.get("disk_free_bytes")
        warning = isinstance(disk, int) and disk < 10 * 1024**3
        crossed_warning = warning and not self._disk_warning
        self._disk_warning = warning
        if crossed_warning:
            return True
        if self._owner_phase(event):
            return event.get("status") in {"BEGIN", "END", "FAILED", "WARN", "FAIL"}
        if not self._acquisition(event):
            return False
        key = self._task_key(event["phase_index"], event["component"], event.get("subtask"), event["progress_kind"])
        bucket = int((event.get("percent") or 0) // 5)
        previous = self._human_buckets.get(key, -1)
        boundary = event.get("status") in {"BEGIN", "END", "FAILED", "WARN", "REUSED", "COMPLETED"}
        changed = bucket > previous
        counters = (event.get("retry_count"), event.get("failure_count"))
        counter_changed = key in self._human_counter_history and counters != self._human_counter_history[key]
        self._human_counter_history[key] = counters
        if boundary or changed or counter_changed:
            self._human_buckets[key] = bucket
            return True
        return False

    def emit(self, *, phase_index: int, phase_name: str | None = None, component: str | None = None,
             subtask: str | None = None, progress_kind: str = "OTHER", completed: int | None = None,
             total: int | None = None, current_item: str | None = None, success_count: int | None = None,
             retry_count: int | None = None, failure_count: int | None = None,
             qualified_count: int | None = None, coverage_denominator: int | None = None,
             status: str | None = None, reason: str | None = None,
             downloaded_bytes: int | None = None, downloaded_bytes_reason: str | None = None,
             written_bytes: int | None = None, run_output_paths: list[str | Path] | None = None,
             extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Emit an additive operational event; malformed telemetry can never escape this method."""
        try:
            if run_output_paths is not None:
                self.set_run_output_paths(run_output_paths)
            now = self.clock()
            resolved_phase_name = phase_name or PHASES.get(phase_index, "Unknown phase")
            resolved_component = component or resolved_phase_name
            task_key = self._task_key(phase_index, resolved_component, subtask, progress_kind)
            if status == "BEGIN" or task_key not in self._work_started:
                self._work_started[task_key] = now
            work_elapsed = max(0.0, now - self._work_started[task_key])
            resources = self._resources(now, force=self._forces_resource_refresh(status, completed, total))
            elapsed = max(0.0, now - self.run_started_monotonic)
            eta_seconds, eta_state, rate = eta(completed=completed, total=total, elapsed_seconds=work_elapsed)
            event: dict[str, Any] = {
                "contract_version": CONTRACT_VERSION,
                "authority_effect": AUTHORITY_EFFECT,
                "timestamp": self.wall_clock().astimezone(timezone.utc).isoformat(),
                "run_id": self.run_id,
                "run_started_at": self.run_started_at,
                "writer_role": self.writer_role,
                "writer_pid": os.getpid(),
                "session": self.session,
                "session_state": "RESOLVED" if self.session else "UNRESOLVED",
                "phase_index": phase_index,
                "phase_total": PHASE_TOTAL,
                "phase_name": resolved_phase_name,
                "component": resolved_component,
                "subtask": subtask,
                "progress_kind": progress_kind,
                "completed": completed,
                "total": total,
                "percent": percent(completed, total),
                "current_item": current_item,
                "success_count": success_count,
                "retry_count": retry_count,
                "failure_count": failure_count,
                "qualified_count": qualified_count,
                "coverage_denominator": coverage_denominator,
                "coverage_percent": percent(qualified_count, coverage_denominator),
                "rss_bytes": resources.get("rss_bytes"),
                "child_rss_bytes": None,
                "recursive_child_tree_rss_bytes": None,
                "peak_rss_bytes": self.peak_observed_single_process_rss_bytes,
                "downloaded_bytes": downloaded_bytes,
                "downloaded_bytes_reason": downloaded_bytes_reason,
                "written_bytes": written_bytes,
                "run_output_bytes": resources.get("run_output_bytes"),
                "disk_free_bytes": resources.get("disk_free_bytes"),
                "elapsed_seconds": round(elapsed, 3),
                "work_elapsed_seconds": round(work_elapsed, 3),
                "rate_per_second": round(rate, 6) if rate is not None else None,
                "eta_seconds": round(eta_seconds, 3) if eta_seconds is not None else None,
                "eta_state": eta_state,
                "status": status,
                "reason": reason,
            }
            if extra:
                event["extra"] = dict(extra)
            if self._owner_phase(event) and status == "BEGIN":
                self.active_phase = phase_index
            self.event_count += 1
            self._write(event)
            if self.human_sink is not None and self._should_write_human(event, now):
                try:
                    if os.environ.get(STRUCTURED_CONSOLE_ENV) == "1":
                        presentation = dict(event, owner_phase=self._owner_phase(event), owner_line=self._human_line(event))
                        self.human_sink("OWNER_DAILY_PROGRESS=" + json.dumps(presentation, ensure_ascii=False))
                    else:
                        self.human_sink(self._human_line(event))
                    self._last_human_at = now
                    self._last_human_percent = event["percent"]
                except Exception as exc:
                    self._degrade("TERMINAL_WRITE_FAILED:" + type(exc).__name__)
            return event
        except Exception as exc:
            self._degrade("EMIT_FAILED:" + type(exc).__name__)
            return {"contract_version": CONTRACT_VERSION, "status": "TELEMETRY_DEGRADED"}

    def callback(self, *, phase_index: int = 2, phase_name: str | None = None) -> Callable[[Mapping[str, Any]], None]:
        def sink(payload: Mapping[str, Any]) -> None:
            data = dict(payload)
            self.emit(
                phase_index=phase_index,
                phase_name=phase_name,
                component=str(data.pop("component", "Canonical Daily")),
                subtask=data.pop("subtask", None),
                progress_kind=str(data.pop("progress_kind", "OTHER")),
                completed=data.pop("completed", None), total=data.pop("total", None),
                current_item=data.pop("current_item", None), success_count=data.pop("success_count", None),
                retry_count=data.pop("retry_count", None), failure_count=data.pop("failure_count", None),
                qualified_count=data.pop("qualified_count", None),
                coverage_denominator=data.pop("coverage_denominator", None),
                status=data.pop("status", None), reason=data.pop("reason", None),
                downloaded_bytes=data.pop("downloaded_bytes", None),
                downloaded_bytes_reason=data.pop("downloaded_bytes_reason", None),
                written_bytes=data.pop("written_bytes", None), run_output_paths=data.pop("run_output_paths", None),
                extra=data or None,
            )
        return sink

    def _ingest_event_summary(self, event: Mapping[str, Any]) -> None:
        peak = event.get("peak_rss_bytes")
        if isinstance(peak, int):
            self.peak_observed_single_process_rss_bytes = max(
                self.peak_observed_single_process_rss_bytes or peak, peak,
            )
        output = event.get("run_output_bytes")
        if isinstance(output, int):
            self.maximum_run_output_bytes = max(self.maximum_run_output_bytes or output, output)
        disk = event.get("disk_free_bytes")
        if isinstance(disk, int):
            self.final_disk_free_bytes = disk

    def summary(self) -> dict[str, Any]:
        count = self.event_count
        if self.progress_path is not None:
            try:
                count = 0
                with self.progress_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            event = json.loads(line)
                        except (TypeError, ValueError, json.JSONDecodeError):
                            self._degrade("MALFORMED_PROGRESS_LINE")
                            continue
                        if not isinstance(event, Mapping):
                            self._degrade("MALFORMED_PROGRESS_LINE")
                            continue
                        count += 1
                        self._ingest_event_summary(event)
            except Exception as exc:
                self._degrade("PROGRESS_SUMMARY_READ_FAILED:" + type(exc).__name__)
        now = self.clock()
        try:
            self._resources(now, force=True)
        except Exception as exc:
            self._degrade("FINAL_RESOURCE_SAMPLE_FAILED:" + type(exc).__name__)
        elapsed = max(0.0, now - self.run_started_monotonic)
        return {
            "status": "DEGRADED" if self.degraded_reasons else "READY",
            "contract_version": CONTRACT_VERSION,
            "authority_effect": AUTHORITY_EFFECT,
            "run_id": self.run_id,
            "run_started_at": self.run_started_at,
            "progress_path": str(self.progress_path) if self.progress_path is not None else None,
            "elapsed_seconds": round(elapsed, 3),
            "peak_observed_single_process_rss_bytes": self.peak_observed_single_process_rss_bytes,
            "recursive_child_tree_rss_bytes": None,
            "maximum_run_output_bytes": self.maximum_run_output_bytes,
            "final_disk_free_bytes": self.final_disk_free_bytes,
            "event_count": count,
            "warnings": list(self.degraded_reasons),
        }


def progress_from_environment(*, session: str | None = None) -> OwnerDailyProgress | None:
    """Reconstruct the child emitter from the parent-supplied explicit run-origin contract."""
    raw_path = os.environ.get(PROGRESS_PATH_ENV)
    if not raw_path:
        return None
    raw_origin = os.environ.get(RUN_STARTED_MONOTONIC_ENV)
    try:
        origin = float(raw_origin) if raw_origin is not None else None
    except ValueError:
        origin = None
    return OwnerDailyProgress(
        Path(raw_path),
        session=session,
        run_id=os.environ.get(RUN_ID_ENV) or None,
        run_started_monotonic=origin,
        run_started_at=os.environ.get(RUN_STARTED_AT_ENV) or None,
        writer_role="DAILY_CHILD",
    )


def run_observed_subprocess(command: list[str], *, component: str | None = None, session: str | None = None, **kwargs: Any) -> subprocess.CompletedProcess:
    """Foreground wait at 30-second intervals; no thread or additional sidecar writer.

    Only commands without special input/timeout contracts use this adapter. Captured
    pipes are drained by communicate exactly as subprocess.run does.
    """
    if session is None and "--session" in command:
        index = command.index("--session")
        if index + 1 < len(command):
            session = command[index + 1]
    try:
        telemetry = progress_from_environment(session=session)
    except Exception:
        telemetry = None
    if telemetry is None:
        return subprocess.run(command, **kwargs)
    name = component or Path(command[1]).stem.removeprefix("run_").replace("_", " ").capitalize()
    def emit(status: str) -> None:
        telemetry.emit(phase_index=2, component=name, subtask="child subprocess",
                       progress_kind="PIPELINE", status=status)
    capture = kwargs.pop("capture_output", False)
    check = kwargs.pop("check", False)
    if capture:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    emit("BEGIN")
    with subprocess.Popen(command, **kwargs) as child:
        while True:
            try:
                stdout, stderr = child.communicate(timeout=30)
                break
            except subprocess.TimeoutExpired:
                emit("RUNNING")
            except BaseException:
                child.kill()
                child.wait()
                raise
        result = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
    emit("END" if result.returncode == 0 else "FAILED")
    if check:
        result.check_returncode()
    return result
