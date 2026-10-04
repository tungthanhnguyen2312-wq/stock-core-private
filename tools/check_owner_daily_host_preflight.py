"""Read-only Owner Daily host observation; no acquisition, state writes or process control."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3
CONTRACT_VERSION = "owner_daily_host_preflight/v1"
MODEL_MAIN = "2c6c79224ae2a3a57b50dae7b96666bd2ec09715"
GUIDANCE = ["Close browsers / IDEs / unrelated Python workloads.",
            "Re-run host preflight; launch Daily alone only when READY."]


def _git(root: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=10)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def windows_memory() -> dict:
    """System-wide commit accounting (not the process-limited PageFile fields)."""
    result = dict(total_physical_bytes=None, available_physical_bytes=None,
                  commit_limit_bytes=None, committed_bytes=None, available_commit_bytes=None,
                  memory_source="UNKNOWN")
    if os.name != "nt":
        return result  # V1 bands qualify the Windows owner host only.
    from ctypes import wintypes

    class Performance(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
            "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable",
            "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")] + [
            (n, wintypes.DWORD) for n in ("HandleCount", "ProcessCount", "ThreadCount")]
    info = Performance()
    info.cb = ctypes.sizeof(info)
    api = ctypes.WinDLL("psapi", use_last_error=True).GetPerformanceInfo
    api.argtypes = [ctypes.POINTER(Performance), wintypes.DWORD]
    api.restype = wintypes.BOOL
    if api(ctypes.byref(info), info.cb):
        page = info.PageSize
        result.update(total_physical_bytes=info.PhysicalTotal * page,
                      available_physical_bytes=info.PhysicalAvailable * page,
                      commit_limit_bytes=info.CommitLimit * page, committed_bytes=info.CommitTotal * page,
                      available_commit_bytes=max(0, info.CommitLimit - info.CommitTotal) * page,
                      memory_source="GetPerformanceInfo")
    return result


def windows_inventory() -> dict:
    """Local CIM only; raw command lines are private inputs and never emitted in the result."""
    if os.name != "nt":
        return {"processes": None, "pagefiles": None}
    script = """
$ErrorActionPreference = 'Stop'
$processes = @(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine,WorkingSetSize)
try { $pages = @(Get-CimInstance Win32_PageFileUsage | Select-Object AllocatedBaseSize,CurrentUsage,PeakUsage) }
catch { $pages = $null }
@{processes=$processes;pagefiles=$pages} | ConvertTo-Json -Depth 4 -Compress
"""
    try:
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        return json.loads(p.stdout) if p.returncode == 0 else {"processes": None, "pagefiles": None}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"processes": None, "pagefiles": None}


def process_summary(rows: list[dict] | None, root: Path, *, own_pid: int) -> dict:
    if rows is None:
        return {"writer_observation": "UNKNOWN", "active_writers": [], "largest_processes": []}
    by_pid = {int(r["ProcessId"]): r for r in rows}
    ancestors = set()
    pid = own_pid
    while pid in by_pid and pid not in ancestors:
        ancestors.add(pid)
        pid = int(by_pid[pid].get("ParentProcessId") or 0)
    writers, largest = [], []
    unknown_runtime = False
    # Recognize runtime entry scripts even when invoked with relative paths. Repository-bound
    # Python/PowerShell commands otherwise remain possible writers; never publish their arguments.
    entry = re.compile(r"(?:run_owner_daily|run_daily_producer|operate_stocklookup|daily_analysis_pipeline|stocklookup|daily_producer_pipeline|"
                       r"canonical_daily_operation|release_orchestrator|run_prospective_decision|"
                       r"publish_dashboard|run_daily_research_session)[.](?:py|ps1|cmd)\b", re.I)
    for row in rows:
        pid = int(row["ProcessId"])
        name = str(row.get("Name") or "UNKNOWN")
        command = str(row.get("CommandLine") or "")
        executable = name.lower()
        relevant = any(s in executable for s in ("python", "powershell", "pwsh", "node", "git", "chrome", "msedge", "code", "claude", "codex"))
        safe = {"pid": pid, "name": name, "working_set_bytes": int(row.get("WorkingSetSize") or 0)}
        if relevant:
            largest.append(safe)
        if pid in ancestors:
            continue
        interpreter = any(s in executable for s in ("python", "powershell", "pwsh", "cmd.exe", "node"))
        if interpreter and (not command or "-encodedcommand" in command.lower()):
            unknown_runtime = True
        repo_bound = ("stock-core-private" in command.lower() or str(root).lower() in command.lower())
        # Standalone read-only check itself is not a runtime writer; do not exempt compound commands.
        readonly = (executable.startswith("python") and " -c " not in command and " -m " not in command
                    and re.search(r'(?:^|[\s"/\\])check_owner_daily_host_preflight\.py(?:["\s]|$)', command, re.I))
        if interpreter and not readonly and (entry.search(command) or repo_bound):
            writers.append({**safe, "role": "DAILY_PRODUCER_OR_REPOSITORY_RUNTIME_WRITER"})
    return {"writer_observation": "UNKNOWN" if unknown_runtime else "OBSERVED", "active_writers": sorted(writers, key=lambda r: r["pid"]),
            "largest_processes": sorted(largest, key=lambda r: (-r["working_set_bytes"], r["pid"]))[:10]}


def retained_sizes(root: Path) -> dict:
    """Stat bounded known artifact families only; never load IID/T0 payloads or recurse the store."""
    families = (
        ("iid", "operations-review/canonical-post-close-v1/????-??-??/enrichment/integrated_investment_decision_product.json"),
        ("iid", "operations-review/integrated-investment-decision-product-v1-????????/integrated_investment_decision_product_artifact.json"),
        ("t0", "operations-review/prospective-decision-retention-v1/????-??-??/*/prospective_decision_snapshot.json"),
    )
    candidates = {"iid": [], "t0": []}
    for kind, pattern in families:
        for path in root.glob(pattern):
            try:
                relative = path.relative_to(root).as_posix()
                match = re.search(r'(20\d{2})-?(\d{2})-?(\d{2})', relative)
                if match and path.is_file():
                    candidates[kind].append(("-".join(match.groups()), path.stat().st_size, relative))
            except OSError:
                continue
    result = {}
    for kind, rows in candidates.items():
        # Largest variant on the latest session is conservative and deterministic.
        session, size, path = max(rows) if rows else (None, None, None)
        result[kind] = {"session": session, "file_bytes": size, "path": path,
                        "basis": "FILE_STAT_ONLY_NOT_AUTHORITY_VALIDATION"}
    return result


def repository_observation(root: Path) -> dict:
    head, main = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "refs/heads/main")
    worktrees = _git(root, "worktree", "list", "--porcelain")
    states = []
    dirty = _git(root, "status", "--porcelain", "--untracked-files=no")
    if worktrees is not None:
        for line in worktrees.splitlines():
            if not line.startswith("worktree "):
                continue
            tree = Path(line[9:])
            marker = tree / ".git"
            git_dir = marker if marker.is_dir() else None
            if git_dir is None:
                try:
                    if marker.stat().st_size <= 4096:
                        pointer = marker.read_text(encoding="utf-8").strip()
                        if pointer.startswith("gitdir: "):
                            git_dir = (tree / pointer[8:]).resolve()
                except (OSError, UnicodeError):
                    pass
            states.append({"worktree": str(tree),
                           "tracked_dirty": bool(dirty) if tree.resolve() == root.resolve() and dirty is not None else None,
                           "index_lock_present": (git_dir / "index.lock").exists() if git_dir and git_dir.is_dir() else None})
    return {"head_sha": head, "main_sha": main, "origin_main_sha": _git(root, "rev-parse", "origin/main"),
            "ref_basis": "LOCAL_REFS_NO_FETCH", "worktrees": states,
            "writer_state_observed": worktrees is not None and all(r["index_lock_present"] is not None for r in states)}


def observe(root: Path, retained_root: Path | None = None) -> dict:
    inventory = windows_inventory()
    try:
        disk = shutil.disk_usage("C:\\").free if os.name == "nt" else None
    except OSError:
        disk = None
    return {**windows_memory(), "c_free_bytes": disk, "disk_path": "C:\\",
            "pagefiles": inventory.get("pagefiles"), "pagefile_unit": "CIM_MEGABYTES",
            **process_summary(inventory.get("processes"), root, own_pid=os.getpid()),
            "repository": repository_observation(root),
            "retained": retained_sizes(retained_root or root)}


def evaluate(observation: dict) -> dict:
    """Pure deterministic classification. V1 operator bands, never a numerical score."""
    iid = observation.get("retained", {}).get("iid", {})
    size = iid.get("file_bytes")
    peak = int(size * 5.05) if isinstance(size, int) and size > 0 else None
    factor = max(1.0, peak / (7 * GIB)) if peak is not None else 1.0
    dimensions = {}
    reasons = []

    def dimension(name, value, green, floor, prefix):
        green, floor = int(green), int(floor)
        state = "BLOCKED" if value is None or value < floor else "READY" if value >= green else "AMBER"
        reason = prefix + ("_BLOCKED" if state == "BLOCKED" else "_OK" if state == "READY" else "_LOW")
        dimensions[name] = {"classification": state, "observed_bytes": value,
                            "green_min_bytes": int(green), "blocked_below_bytes": int(floor), "reason": reason}
        reasons.append(reason)

    dimension("commit", observation.get("available_commit_bytes"), 12.0 * GIB * factor, 9.2 * GIB * factor, "COMMIT_HEADROOM")
    dimension("physical", observation.get("available_physical_bytes"), 6 * GIB * factor, 2.5 * GIB * factor, "PHYSICAL_HEADROOM")
    dimension("disk", observation.get("c_free_bytes"), 25 * GIB, 17 * GIB, "DISK_HEADROOM")
    dimensions["physical"]["recommended_amber_min_bytes"] = int(3.5 * GIB * factor)
    repo = observation.get("repository", {})
    writers = observation.get("active_writers", [])
    locks = any(w.get("index_lock_present") for w in repo.get("worktrees", []))
    writer_known = observation.get("writer_observation") == "OBSERVED" and repo.get("writer_state_observed") is True
    writer_reason = "CONCURRENT_WRITER_PRESENT" if writers or locks else "WRITER_STATE_UNKNOWN" if not writer_known else "NO_CONCURRENT_WRITER_OBSERVED"
    dimensions["writers"] = {"classification": "READY" if writer_known and not writers and not locks else "BLOCKED", "reason": writer_reason}
    reasons.append(writer_reason)
    pages = observation.get("pagefiles")
    dimensions["pagefile"] = {"classification": "AMBER" if pages is None else "READY",
                              "reason": "PAGEFILE_STATE_UNKNOWN" if pages is None else "PAGEFILE_STATE_OBSERVED"}
    reasons.append(dimensions["pagefile"]["reason"])
    dimensions["scale_model"] = {"classification": "READY" if peak else "AMBER",
                                 "reason": "SCALE_MODEL_AVAILABLE" if peak else "SCALE_MODEL_UNAVAILABLE"}
    reasons.append(dimensions["scale_model"]["reason"])
    provenance_ready = bool(repo.get("head_sha") and repo.get("main_sha") and repo.get("head_sha") == repo.get("main_sha"))
    dimensions["provenance"] = {"classification": "READY" if provenance_ready else "AMBER",
                                "reason": "CURRENT_MAIN_IDENTIFIED" if provenance_ready else "CURRENT_MAIN_PROVENANCE_UNQUALIFIED"}
    reasons.append(dimensions["provenance"]["reason"])
    states = [r["classification"] for r in dimensions.values()]
    classification = "BLOCKED" if "BLOCKED" in states else "AMBER" if "AMBER" in states else "READY"
    if classification == "READY":
        reasons.append("HOST_PREFLIGHT_READY")
    return {"contract_version": CONTRACT_VERSION, "classification": classification,
            "authority_effect": "NONE / OWNER_DAILY_HOST_PREFLIGHT_ONLY", "dimensions": dimensions,
            "reasons": reasons, "observations": observation,
            "peak_model": {"peak_basis": "MODELED_FROM_RETAINED_CURRENT_MAIN", "modeled_peak_bytes": peak,
                           "modeled_peak_scope": "IID_SIZE_SCALING_ESTIMATE_NOT_DAILY_HIGH_END",
                           "iid_multiplier": 5.05, "band_scale_factor": factor,
                           "memory_band_scaling_reference_bytes": 7 * GIB,
                           "revised_daily_child_working_band_bytes": [int(6.5 * GIB), 8 * GIB],
                           "working_band_high_end_is_floor_not_ceiling": True,
                           "benchmark_provenance": "OWNER_FINAL_REAL_SCALE_RETAINED_BENCHMARK_2026_10_04",
                           "benchmark_main_sha": "bf881cd4cc9453d351389de87ed2312c4a9e0150",
                           "delivery_resident_bytes_approx": int(1.98 * GIB),
                           "delivery_transient_additional_bytes_approx": int(2.88 * GIB),
                           "provenance": "OWNER_FINAL_REAL_SCALE_RETAINED_BENCHMARK_2026_10_04",
                           "forensics_main_sha": MODEL_MAIN, "observed_main_sha": repo.get("main_sha"),
                           "monday_measured_peak_bytes": None,
                           "historical_peak_bytes": 9853145088, "historical_peak_classification": "STALE"},
            "operator_action_required": classification != "READY",
            "operator_guidance": GUIDANCE if classification != "READY" else ["Launch Daily alone; existing evidence/runtime gates still apply."],
            "limitations": ["Point-in-time observation, not a writer lease or a measured Monday peak.",
                            "T0 file size is optional metadata; capture completeness and T0 availability remain independent."]}


def check(root: Path, retained_root: Path | None = None) -> dict:
    return evaluate(observe(Path(root).resolve(), retained_root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--retained-root", type=Path, default=None)
    args = parser.parse_args(argv)
    retained = args.retained_root or (Path(os.environ["STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT"])
                                    if os.environ.get("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT") else None)
    result = check(args.root, retained)
    print(json.dumps(result, indent=2, sort_keys=True))
    return {"READY": 0, "AMBER": 2, "BLOCKED": 3}[result["classification"]]


if __name__ == "__main__":
    raise SystemExit(main())
