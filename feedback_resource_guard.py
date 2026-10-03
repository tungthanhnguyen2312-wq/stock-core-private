"""Bounded execution of optional/derived Owner Daily work (OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1).

Outcome feedback is fail-soft; first-capture evidence is not. This module lets the parent Daily run the
feedback child under (1) a pre-admission check, (2) one TOTAL deadline enforced by ``Popen.wait(timeout=...)``
(no polling, no daemon), (3) a kernel-enforced per-process memory ceiling (Windows Job Object; POSIX
``RLIMIT_AS``), and (4) guaranteed termination and reaping. The parent exchanges only paths, identities and a
small status sidecar with the child; it never receives artifact payloads.

Reason codes keep resource outcomes apart from analytical ones. A resource outcome is never an investment or
feedback state and must never be read as negative or neutral evidence.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

RESULT_MAX_BYTES = 256 * 1024
STDERR_TAIL_BYTES = 2000

# -- reason-code vocabulary (disjoint classes) ---------------------------------------------------------
RESOURCE_TIMEOUT = "FEEDBACK_RESOURCE_TIMEOUT"
RESOURCE_MEMORY_LIMIT = "FEEDBACK_RESOURCE_MEMORY_LIMIT"
RESOURCE_UNAVAILABLE = "FEEDBACK_RESOURCE_UNAVAILABLE"          # admission refused (RAM / commit / disk)
RESOURCE_DISK = "FEEDBACK_RESOURCE_DISK_UNAVAILABLE"
COMPUTATION_ERROR = "FEEDBACK_COMPUTATION_ERROR"                 # a defect, never "no evidence"
EVIDENCE_INSUFFICIENT = "FEEDBACK_EVIDENCE_INSUFFICIENT"         # analytical: sources exist but cannot qualify
NOT_MATURE = "FEEDBACK_NOT_MATURE"                               # analytical: horizons still pending
SOURCE_INTEGRITY = "FEEDBACK_SOURCE_INTEGRITY_FAILED"
IMMUTABLE_CONFLICT = "FEEDBACK_IMMUTABLE_OUTPUT_CONFLICT"
RESOURCE_REASONS = frozenset({RESOURCE_TIMEOUT, RESOURCE_MEMORY_LIMIT, RESOURCE_UNAVAILABLE, RESOURCE_DISK})

NT_MEMORY_STATUSES = frozenset({0xC0000017, 0xC0000142, 0xC000009A, 0xC000012D})  # NO_MEMORY, DLL_INIT_FAILED, INSUFFICIENT_RESOURCES, COMMITMENT_LIMIT

EXIT_OK = 0
EXIT_COMPUTATION_ERROR = 30
EXIT_SOURCE_INTEGRITY = 31
EXIT_IMMUTABLE_CONFLICT = 32
EXIT_RESOURCE_MEMORY = 75
EXIT_RESOURCE_DISK = 74
EXIT_REASON = {EXIT_COMPUTATION_ERROR: COMPUTATION_ERROR, EXIT_SOURCE_INTEGRITY: SOURCE_INTEGRITY,
               EXIT_IMMUTABLE_CONFLICT: IMMUTABLE_CONFLICT, EXIT_RESOURCE_MEMORY: RESOURCE_MEMORY_LIMIT,
               EXIT_RESOURCE_DISK: RESOURCE_DISK}


@dataclass(frozen=True)
class ResourcePolicy:
    """Calibrated from measured cold/warm runs (see docs/owner_daily_feedback_resource_containment_contract.md)."""
    deadline_seconds: float
    memory_limit_bytes: int | None
    min_available_physical_bytes: int
    min_available_commit_bytes: int
    min_free_disk_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


GIB = 1024 ** 3
ENV_PREFIX = "STOCKLOOKUP_FEEDBACK_"


def default_feedback_policy(env: Mapping[str, str] | None = None) -> ResourcePolicy:
    """Calibrated defaults (see the contract document for the measurements); explicit overrides are for operators and tests."""
    environment = os.environ if env is None else env

    def number(name: str, default: float) -> float:
        raw = environment.get(ENV_PREFIX + name)
        try:
            return float(raw) if raw not in (None, "") else float(default)
        except ValueError:
            return float(default)

    limit = number("MEMORY_LIMIT_BYTES", CALIBRATED_MEMORY_LIMIT_BYTES)
    return ResourcePolicy(
        deadline_seconds=number("DEADLINE_SECONDS", CALIBRATED_DEADLINE_SECONDS),
        memory_limit_bytes=int(limit) if limit > 0 else None,
        min_available_physical_bytes=int(number("MIN_AVAILABLE_PHYSICAL_BYTES", CALIBRATED_MIN_AVAILABLE_PHYSICAL_BYTES)),
        min_available_commit_bytes=int(number("MIN_AVAILABLE_COMMIT_BYTES", CALIBRATED_MIN_AVAILABLE_COMMIT_BYTES)),
        min_free_disk_bytes=int(number("MIN_FREE_DISK_BYTES", CALIBRATED_MIN_FREE_DISK_BYTES)))


# Placeholders until the measured calibration is recorded (replaced in the calibration commit).
CALIBRATED_DEADLINE_SECONDS = 1800.0
CALIBRATED_MEMORY_LIMIT_BYTES = 3 * GIB
CALIBRATED_MIN_AVAILABLE_PHYSICAL_BYTES = 1 * GIB
CALIBRATED_MIN_AVAILABLE_COMMIT_BYTES = 2 * GIB
CALIBRATED_MIN_FREE_DISK_BYTES = 4 * GIB


# --------------------------------------------------------------------------------------------------
# Host probes
# --------------------------------------------------------------------------------------------------

def memory_status() -> dict[str, Any]:
    """Available physical memory and available commit (page file + RAM) in bytes; ``None`` fields if unknown."""
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {"source": "GlobalMemoryStatusEx", "total_physical": int(status.ullTotalPhys),
                    "available_physical": int(status.ullAvailPhys), "available_commit": int(status.ullAvailPageFile)}
        return {"source": "UNAVAILABLE", "total_physical": None, "available_physical": None, "available_commit": None}
    try:
        values = {}
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                name, _, rest = line.partition(":")
                values[name] = int(rest.split()[0]) * 1024
        available = values.get("MemAvailable")
        commit = (available or 0) + values.get("SwapFree", 0)
        return {"source": "/proc/meminfo", "total_physical": values.get("MemTotal"), "available_physical": available,
                "available_commit": commit if available is not None else None}
    except (OSError, ValueError, IndexError):
        return {"source": "UNAVAILABLE", "total_physical": None, "available_physical": None, "available_commit": None}


def free_disk_bytes(path: Path) -> int | None:
    import shutil
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return int(shutil.disk_usage(probe).free)
    except OSError:
        return None


def peak_memory_bytes() -> int | None:
    """Peak private/committed memory of *this* process (child self-report)."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class COUNTERS(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return int(counters.PeakPagefileUsage)
        return None
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak * (1 if sys.platform == "darwin" else 1024))
    except (ImportError, ValueError):
        return None


def admit(policy: ResourcePolicy, *, output_dir: Path, expected_output_bytes: int) -> dict[str, Any]:
    """Pre-feedback admission. Returns ``admitted`` plus the measured facts; unknown probes do not refuse."""
    memory = memory_status()
    disk = free_disk_bytes(output_dir)
    # Output is written as spool + final (about 2x) before the spool is removed.
    required_disk = policy.min_free_disk_bytes + 2 * max(0, int(expected_output_bytes))
    reasons = []
    if memory["available_physical"] is not None and memory["available_physical"] < policy.min_available_physical_bytes:
        reasons.append("AVAILABLE_PHYSICAL_MEMORY_BELOW_FLOOR")
    if memory["available_commit"] is not None and memory["available_commit"] < policy.min_available_commit_bytes:
        reasons.append("AVAILABLE_COMMIT_BELOW_FLOOR")
    disk_reasons = []
    if disk is not None and disk < required_disk:
        disk_reasons.append("FREE_DISK_BELOW_REQUIRED")
    admitted = not reasons and not disk_reasons
    return {"admitted": admitted,
            "reason_code": None if admitted else (RESOURCE_DISK if disk_reasons and not reasons else RESOURCE_UNAVAILABLE),
            "reasons": reasons + disk_reasons,
            "available_physical_bytes": memory["available_physical"], "available_commit_bytes": memory["available_commit"],
            "free_disk_bytes": disk, "required_disk_bytes": required_disk, "memory_probe": memory["source"],
            "policy": policy.as_dict()}


# --------------------------------------------------------------------------------------------------
# Windows Job Object containment
# --------------------------------------------------------------------------------------------------

class _Job:
    """One job per child: kill-on-close, optional per-process commit ceiling, peak accounting."""

    def __init__(self, memory_limit_bytes: int | None):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                           "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        class ACCOUNTING(ctypes.Structure):
            _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                        ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                        ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                        ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

        self.EXTENDED, self.ACCOUNTING = EXTENDED, ACCOUNTING
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel = kernel
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = EXTENDED()
        flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if memory_limit_bytes:
            flags |= 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY (committed bytes per process)
            info.ProcessMemoryLimit = int(memory_limit_bytes)
        info.BasicLimitInformation.LimitFlags = flags
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.get_last_error()
            kernel.CloseHandle(self.handle)
            raise OSError(error, "SetInformationJobObject failed")

    def assign(self, process_handle: int) -> None:
        if not self.kernel.AssignProcessToJobObject(self.handle, self.wintypes.HANDLE(process_handle)):
            raise OSError(self.ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def terminate(self) -> None:
        self.kernel.TerminateJobObject(self.handle, 1)

    def peak_process_bytes(self) -> int | None:
        info = self.EXTENDED()
        returned = self.wintypes.DWORD()
        if self.kernel.QueryInformationJobObject(self.handle, 9, self.ctypes.byref(info), self.ctypes.sizeof(info), self.ctypes.byref(returned)):
            return int(info.PeakProcessMemoryUsed)
        return None

    def active_processes(self) -> int | None:
        info = self.ACCOUNTING()
        returned = self.wintypes.DWORD()
        if self.kernel.QueryInformationJobObject(self.handle, 1, self.ctypes.byref(info), self.ctypes.sizeof(info), self.ctypes.byref(returned)):
            return int(info.ActiveProcesses)
        return None

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _resume_suspended(process: subprocess.Popen) -> None:
    import ctypes
    from ctypes import wintypes
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    status = ntdll.NtResumeProcess(wintypes.HANDLE(int(process._handle)))
    if status != 0:
        raise OSError(status, "NtResumeProcess failed")


def _read_small_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > RESULT_MAX_BYTES:
            return {"status": "CHILD_RESULT_OVERSIZE"}
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _tail(path: Path) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - STDERR_TAIL_BYTES))
            return handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def run_bounded(command: Sequence[str], *, cwd: str | Path, policy: ResourcePolicy, result_path: Path,
                env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Run ``command`` to completion or until the TOTAL deadline. Always returns a bounded structured result.

    The child is expected to write a small JSON status sidecar at ``result_path``; stdout/stderr go to a
    temporary file (never a pipe, so no drain thread and no deadlock) of which only a short tail is read.
    """
    result_path = Path(result_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result_path.unlink(missing_ok=True)
    except OSError:
        pass
    started = time.perf_counter()
    log = tempfile.NamedTemporaryFile(prefix="feedback-child-", suffix=".log", delete=False)
    log_path = Path(log.name)
    job: _Job | None = None
    containment = "NONE"
    process: subprocess.Popen | None = None
    outcome = "LAUNCH_FAILED"
    try:
        popen_kwargs: dict[str, Any] = {"cwd": str(cwd), "stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL,
                                        "env": dict(env) if env is not None else None}
        if os.name == "nt":
            suspended = False
            try:
                job = _Job(policy.memory_limit_bytes)
                popen_kwargs["creationflags"] = 0x00000004  # CREATE_SUSPENDED: no allocation before containment
                suspended = True
            except OSError:
                job = None
            process = subprocess.Popen(list(command), **popen_kwargs)
            if job is not None and suspended:
                try:
                    job.assign(int(process._handle))
                    _resume_suspended(process)
                    containment = "WINDOWS_JOB_OBJECT_PROCESS_MEMORY" if policy.memory_limit_bytes else "WINDOWS_JOB_OBJECT_KILL_ON_CLOSE"
                except OSError:
                    # Could not contain: never run an uncontained suspended child; kill it and run bounded by time only.
                    process.kill()
                    process.wait()
                    job.close()
                    job = None
                    popen_kwargs.pop("creationflags", None)
                    process = subprocess.Popen(list(command), **popen_kwargs)
                    containment = "DEADLINE_ONLY"
            elif job is None:
                containment = "DEADLINE_ONLY"
        else:
            def limit():
                try:
                    import resource
                    if policy.memory_limit_bytes:
                        # RLIMIT_AS bounds *address space* (shared libraries and thread stacks included), a looser proxy for
                        # committed bytes than the Windows ceiling; the deadline remains the primary bound off Windows.
                        ceiling = max(policy.memory_limit_bytes * 4, policy.memory_limit_bytes + 3 * GIB)
                        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
                except (ImportError, ValueError, OSError):
                    pass

            popen_kwargs["start_new_session"] = True  # own process group => whole-tree kill on timeout/cancel
            if policy.memory_limit_bytes:
                popen_kwargs["preexec_fn"] = limit
            process = subprocess.Popen(list(command), **popen_kwargs)
            containment = "POSIX_RLIMIT_AS" if policy.memory_limit_bytes else "DEADLINE_ONLY"
        try:
            process.wait(timeout=policy.deadline_seconds)  # single total deadline; WaitForSingleObject, not a poll loop
            outcome = "COMPLETED" if process.returncode == 0 else "EXIT_NONZERO"
        except subprocess.TimeoutExpired:
            outcome = "TIMEOUT"
            _terminate(process, job)
        except BaseException:
            # Parent cancellation (KeyboardInterrupt/SystemExit): never leave the child or its tree running.
            _terminate(process, job)
            if job is not None:
                job.close()
            for cleanup in (log.close, lambda: log_path.unlink(missing_ok=True)):
                try:
                    cleanup()
                except OSError:
                    pass
            raise
    except OSError as exc:
        return {"outcome": "LAUNCH_FAILED", "reason_code": COMPUTATION_ERROR, "returncode": None,
                "wall_seconds": round(time.perf_counter() - started, 3), "detail": f"{type(exc).__name__}:{exc}",
                "containment": containment, "reaped": True, "peak_process_bytes": None, "child_result": None, "stderr_tail": ""}
    finally:
        try:
            log.close()
        except OSError:
            pass
    reaped = process is not None and process.poll() is not None
    if not reaped and process is not None:
        _terminate(process, job)
        reaped = process.poll() is not None
    peak = job.peak_process_bytes() if job is not None else None
    active = job.active_processes() if job is not None else 0
    if job is not None:
        job.close()
    child_result = _read_small_json(result_path)
    tail = _tail(log_path)
    try:
        log_path.unlink(missing_ok=True)
    except OSError:
        pass
    reason = None
    if outcome == "TIMEOUT":
        reason = RESOURCE_TIMEOUT
    elif outcome == "EXIT_NONZERO":
        reason = (child_result or {}).get("reason_code") or EXIT_REASON.get(process.returncode)
        if reason is None:
            # A hard allocation failure inside the contained child shows as a non-zero exit near the ceiling, or as an
            # NT "no memory"/"initialisation failed" status when the ceiling is below the interpreter's own start-up commit.
            returncode = (process.returncode or 0) & 0xFFFFFFFF
            if policy.memory_limit_bytes and ((peak and peak >= 0.92 * policy.memory_limit_bytes) or returncode in NT_MEMORY_STATUSES):
                reason = RESOURCE_MEMORY_LIMIT
            else:
                reason = COMPUTATION_ERROR
    elif outcome == "COMPLETED" and (child_result or {}).get("status") not in {"COMPLETED", None}:
        reason = (child_result or {}).get("reason_code")
    return {"outcome": outcome, "reason_code": reason, "returncode": process.returncode if process is not None else None,
            "wall_seconds": round(time.perf_counter() - started, 3), "containment": containment, "reaped": bool(reaped and not active),
            "peak_process_bytes": peak, "child_result": child_result, "stderr_tail": tail,
            "policy": policy.as_dict()}


def _terminate(process: subprocess.Popen, job: _Job | None) -> None:
    """Kill the whole contained tree, then reap. Never leaves a zombie or an orphaned grandchild."""
    try:
        if job is not None and job.handle:
            job.terminate()
        elif os.name == "nt":
            process.kill()
        else:
            import signal
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        pass


# --------------------------------------------------------------------------------------------------
# Child-side helpers
# --------------------------------------------------------------------------------------------------

def write_child_result(path: str | Path | None, value: Mapping[str, Any]) -> None:
    """Atomic, bounded status sidecar. Never raises: a failing status write must not mask the real outcome."""
    if path is None:
        return
    target = Path(path)
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        if len(payload) > RESULT_MAX_BYTES:
            payload = json.dumps({"status": value.get("status"), "reason_code": value.get("reason_code"),
                                  "artifact_identity": value.get("artifact_identity"), "path": value.get("path"),
                                  "truncated": True}).encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".child-result-", suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)
    except OSError:
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
