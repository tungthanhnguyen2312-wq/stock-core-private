"""M1_LIVE_ACCEPTANCE_CORRECTIVE_V1 -- Desktop Owner Daily launcher (tools/run_owner_daily.ps1).

Under Windows PowerShell 5.1 the launcher combined ``$ErrorActionPreference = 'Stop'`` with
``& $python ... 2>&1 | Tee-Object``: the first native stderr line became a terminating
NativeCommandError that killed run_owner_daily.py before it could write its result file or
journal FAILED (the 2026-09-24 acquisition failure). These tests run the REAL launcher under
powershell.exe against a harmless fixture entry script -- no Daily, no provider, no network.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "tools" / "run_owner_daily.ps1"
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None
windows_powershell = pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell 5.1 (the real launcher host)")

FIXTURE = r'''
import json, sys, time
args = sys.argv[1:]
result_path = args[args.index("--result-path") + 1]
mode = MODE
if mode == "stderr_flood":
    for i in range(3000):
        print(f"FLOOD_STDERR_{i:04d}", file=sys.stderr, flush=True)
    print("FLOOD_DONE", flush=True)
    sys.exit(0)
print("FIXTURE_STDOUT_1 before stderr", flush=True)
time.sleep(0.3)
print("FIXTURE_STDERR_1 expected native error text", file=sys.stderr, flush=True)
time.sleep(0.3)
print("FIXTURE_STDOUT_2 after stderr", flush=True)
if mode == "fail_with_result":
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump({"status": "FAILED", "failed_step": "Fixture step", "reason": "FIXTURE_EXPECTED_FAILURE"}, fh)
    sys.exit(3)
if mode == "pass":
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump({"status": "PASS", "session": "2026-09-24", "daily_status": "COMPLETED"}, fh)
    sys.exit(0)
sys.exit(7)  # crash_without_result
'''


def _run_launcher(tmp_path: Path, mode: str) -> tuple[subprocess.CompletedProcess, Path]:
    entry = tmp_path / f"fixture_{mode}.py"
    entry.write_text(FIXTURE.replace("MODE", repr(mode)), encoding="utf-8")
    logs = tmp_path / "logs"
    completed = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER),
         "-EntryScript", str(entry), "-LogDirectory", str(logs), "-NoPause"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    return completed, logs


def _log_text(logs: Path) -> str:
    [log] = list(logs.glob("stock_lookup_daily_*.log"))
    raw = log.read_bytes()
    return raw.decode("utf-16") if raw[:2] == b"\xff\xfe" else raw.decode("utf-8")


@windows_powershell
def test_native_stderr_no_longer_kills_the_orchestrator_and_the_exit_code_is_preserved(tmp_path):
    completed, logs = _run_launcher(tmp_path, "fail_with_result")
    out = completed.stdout
    assert completed.returncode == 3, out + completed.stderr
    lines = ["FIXTURE_STDOUT_1 before stderr", "FIXTURE_STDERR_1 expected native error text", "FIXTURE_STDOUT_2 after stderr"]
    # Parent survived the stderr line: the later stdout line and the child's own result file exist.
    assert [line for line in out.splitlines() if line.startswith("FIXTURE_")] == lines
    assert "NativeCommandError" not in out + completed.stderr
    assert json.loads(next(logs.glob("*.result.json")).read_text(encoding="utf-8"))["status"] == "FAILED"
    # The wrapper reached its own final handling path from that result file.
    assert "FINAL STATUS: FAILED" in out and "REASON: FIXTURE_EXPECTED_FAILURE" in out
    assert [line for line in _log_text(logs).splitlines() if line.startswith("FIXTURE_")] == lines


@windows_powershell
def test_a_run_that_writes_no_result_is_interrupted_with_its_native_exit_code(tmp_path):
    completed, logs = _run_launcher(tmp_path, "crash_without_result")
    assert completed.returncode == 7
    assert "FIXTURE_STDOUT_2 after stderr" in completed.stdout
    assert "FINAL STATUS: INTERRUPTED" in completed.stdout and "NO_RESULT_FILE_WRITTEN" in completed.stdout
    assert not list(logs.glob("*.result.json"))


@windows_powershell
def test_success_after_stderr_output_stays_success(tmp_path):
    completed, _ = _run_launcher(tmp_path, "pass")
    assert completed.returncode == 0
    assert "FINAL STATUS: PASS" in completed.stdout


@windows_powershell
def test_a_high_volume_stderr_stream_neither_hangs_nor_loses_lines(tmp_path):
    completed, logs = _run_launcher(tmp_path, "stderr_flood")
    assert "FLOOD_DONE" in completed.stdout
    logged = _log_text(logs)
    assert sum(1 for line in logged.splitlines() if line.startswith("FLOOD_STDERR_")) == 3000
    # No result file -> never reported as success, even though the fixture exited 0.
    assert completed.returncode == 1 and "FINAL STATUS: INTERRUPTED" in completed.stdout


def test_launcher_scopes_continue_to_the_native_call_and_keeps_the_canonical_route():
    source = LAUNCHER.read_text(encoding="utf-8")
    native_call = "& $python @arguments 2>&1"
    assert source.count(native_call) == 1
    before, after = source.split(native_call)
    # 'Continue' is the preference in force at the native call; the script preference is restored after.
    assert before.rfind("$ErrorActionPreference = 'Continue'") > before.rfind("$ErrorActionPreference = 'Stop'")
    assert "$ErrorActionPreference = $scriptPreference" in after
    assert "[System.Management.Automation.ErrorRecord]" in after.split("Tee-Object")[0]
    # Canonical owner route unchanged when the Desktop CMD passes no seams.
    assert "$entry = Join-Path $PSScriptRoot 'run_owner_daily.py'" in source
    assert r"$logDir = 'C:\Projects\StockLookup\run-logs'" in source
    assert "if (-not $NoPause) { Read-Host 'Press Enter to close' }" in source
    assert "exit $finalExitCode" in source
