from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from tools import check_owner_daily_host_preflight as preflight
from tools import run_owner_daily as owner

GIB = preflight.GIB


def safe_observation():
    return {"available_commit_bytes": 12 * GIB, "available_physical_bytes": 7 * GIB,
            "commit_limit_bytes": 32 * GIB, "committed_bytes": 20 * GIB, "c_free_bytes": 26 * GIB,
            "pagefiles": [{"AllocatedBaseSize": 16000, "CurrentUsage": 1000, "PeakUsage": 2000}],
            "writer_observation": "OBSERVED", "active_writers": [], "largest_processes": [],
            "repository": {"head_sha": "abc", "main_sha": "abc", "writer_state_observed": True,
                           "worktrees": [{"index_lock_present": False, "tracked_dirty": False}]},
            "retained": {"iid": {"file_bytes": int(1.3 * GIB), "session": "2026-10-02"},
                         "t0": {"file_bytes": None}}}


def test_green_ready_and_deterministic_without_t0():
    observation = safe_observation()
    result = preflight.evaluate(observation)
    assert result == preflight.evaluate(copy.deepcopy(observation))
    assert result["classification"] == "READY"
    assert "HOST_PREFLIGHT_READY" in result["reasons"]
    assert result["peak_model"]["peak_basis"] == "MODELED_FROM_RETAINED_CURRENT_MAIN"
    assert result["peak_model"]["monday_measured_peak_bytes"] is None


@pytest.mark.parametrize("field,value,classification,reason", [
    ("available_commit_bytes", 10 * GIB, "AMBER", "COMMIT_HEADROOM_LOW"),
    ("available_physical_bytes", 4 * GIB, "AMBER", "PHYSICAL_HEADROOM_LOW"),
    ("available_physical_bytes", 3 * GIB, "AMBER", "PHYSICAL_HEADROOM_LOW"),
    ("c_free_bytes", 20 * GIB, "AMBER", "DISK_HEADROOM_LOW"),
    ("available_commit_bytes", 8 * GIB, "BLOCKED", "COMMIT_HEADROOM_BLOCKED"),
    ("available_physical_bytes", 2 * GIB, "BLOCKED", "PHYSICAL_HEADROOM_BLOCKED"),
    ("c_free_bytes", 16 * GIB, "BLOCKED", "DISK_HEADROOM_BLOCKED"),
    ("available_commit_bytes", None, "BLOCKED", "COMMIT_HEADROOM_BLOCKED"),
    ("available_physical_bytes", None, "BLOCKED", "PHYSICAL_HEADROOM_BLOCKED"),
    ("c_free_bytes", None, "BLOCKED", "DISK_HEADROOM_BLOCKED"),
])
def test_resource_bands(field, value, classification, reason):
    observation = safe_observation()
    observation[field] = value
    result = preflight.evaluate(observation)
    assert result["classification"] == classification
    assert reason in result["reasons"]


@pytest.mark.parametrize("field,green,floor", [
    ("available_commit_bytes", 12.0, 9.2), ("available_physical_bytes", 6, 2.5), ("c_free_bytes", 25, 17)])
def test_exact_band_boundaries(field, green, floor):
    observation = safe_observation()
    observation[field] = int(green * GIB)
    assert preflight.evaluate(observation)["classification"] == "READY"
    observation[field] = int(green * GIB) - 1
    assert preflight.evaluate(observation)["classification"] == "AMBER"
    observation[field] = int(floor * GIB)
    assert preflight.evaluate(observation)["classification"] == "AMBER"
    observation[field] = int(floor * GIB) - 1
    assert preflight.evaluate(observation)["classification"] == "BLOCKED"


@pytest.mark.parametrize("unknown", ["pagefiles", "model", "main"])
def test_optional_unknowns_require_operator_action(unknown):
    observation = safe_observation()
    reason = {"pagefiles": "PAGEFILE_STATE_UNKNOWN", "model": "SCALE_MODEL_UNAVAILABLE",
              "main": "CURRENT_MAIN_PROVENANCE_UNQUALIFIED"}[unknown]
    if unknown == "model":
        observation["retained"]["iid"]["file_bytes"] = None
    elif unknown == "main":
        observation["repository"]["main_sha"] = None
    else:
        observation[unknown] = None
    result = preflight.evaluate(observation)
    assert result["classification"] == "AMBER"
    assert result["operator_action_required"] is True
    assert reason in result["reasons"]


@pytest.mark.parametrize("cause", ["process", "index_lock", "unknown_process", "unknown_git"])
def test_concurrent_or_unobservable_writer_blocks(cause):
    observation = safe_observation()
    if cause == "process":
        observation["active_writers"] = [{"pid": 32}]
    elif cause == "index_lock":
        observation["repository"]["worktrees"][0]["index_lock_present"] = True
    elif cause == "unknown_process":
        observation["writer_observation"] = "UNKNOWN"
    else:
        observation["repository"]["writer_state_observed"] = False
    assert preflight.evaluate(observation)["classification"] == "BLOCKED"


def test_larger_iid_scales_memory_bands_without_weakening_baseline():
    observation = safe_observation()
    observation["retained"]["iid"]["file_bytes"] = 2 * GIB
    result = preflight.evaluate(observation)
    assert result["peak_model"]["modeled_peak_bytes"] == int(5.05 * 2 * GIB)
    assert result["dimensions"]["commit"]["green_min_bytes"] > 12.0 * GIB
    assert result["classification"] == "BLOCKED"
    observation["retained"]["iid"]["file_bytes"] = 100
    assert preflight.evaluate(observation)["dimensions"]["commit"]["green_min_bytes"] == int(12.0 * GIB)


def test_final_benchmark_provenance_and_other_bands_unchanged():
    result = preflight.evaluate(safe_observation())
    assert result["dimensions"]["physical"]["green_min_bytes"] == 6 * GIB
    assert result["dimensions"]["physical"]["blocked_below_bytes"] == int(2.5 * GIB)
    assert result["dimensions"]["disk"]["green_min_bytes"] == 25 * GIB
    assert result["dimensions"]["disk"]["blocked_below_bytes"] == 17 * GIB
    model = result["peak_model"]
    assert model["revised_daily_child_working_band_bytes"] == [int(6.5 * GIB), 8 * GIB]
    assert model["working_band_high_end_is_floor_not_ceiling"] is True
    assert model["provenance"] == "OWNER_FINAL_REAL_SCALE_RETAINED_BENCHMARK_2026_10_04"
    assert model["monday_measured_peak_bytes"] is None


def test_process_inventory_excludes_own_wrapper_and_never_prints_arguments(tmp_path):
    def process(pid, parent, name, command, memory=100):
        return dict(ProcessId=pid, ParentProcessId=parent, Name=name, CommandLine=command, WorkingSetSize=memory)
    rows = [process(1, 0, "powershell.exe", "run_owner_daily.ps1"),
            process(2, 1, "python.exe", "run_owner_daily.py"),
            process(3, 0, "python.exe", "daily_analysis_pipeline.py --secret DONT_EMIT"),
            process(4, 0, "python.exe", "unrelated.py"),
            process(5, 0, "python.exe", 'tools/check_owner_daily_host_preflight.py'),
            process(6, 0, "python.exe", 'C:/Projects/stock-core-private/tools/writer.py --token DONT_EMIT')]
    result = preflight.process_summary(rows, tmp_path, own_pid=2)
    assert [p["pid"] for p in result["active_writers"]] == [3, 6]
    assert "DONT_EMIT" not in json.dumps(result)
    assert "CommandLine" not in json.dumps(result)


def test_unobservable_runtime_process_is_not_claimed_writer_free(tmp_path):
    result = preflight.process_summary([dict(ProcessId=9, ParentProcessId=0, Name="python.exe",
                                            CommandLine=None, WorkingSetSize=50)], tmp_path, own_pid=2)
    assert result["writer_observation"] == "UNKNOWN"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows local CIM probe")
def test_windows_inventory_real_probe_is_read_only_and_usable():
    result = preflight.windows_inventory()
    assert isinstance(result["processes"], list) and result["processes"]
    assert isinstance(result["pagefiles"], list)


def test_retained_inventory_stats_only_and_chooses_latest_largest(tmp_path, monkeypatch):
    paths = [
        "operations-review/canonical-post-close-v1/2026-10-02/enrichment/integrated_investment_decision_product.json",
        "operations-review/integrated-investment-decision-product-v1-20261002/integrated_investment_decision_product_artifact.json",
        "operations-review/integrated-investment-decision-product-v1-20260903/integrated_investment_decision_product_artifact.json",
        "operations-review/prospective-decision-retention-v1/2026-09-08/hash/prospective_decision_snapshot.json"]
    for p, length in zip(paths, [10, 20, 40, 30]):
        path = tmp_path / p
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * length)
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("must not read artifact"))
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("must not load artifact"))
    result = preflight.retained_sizes(tmp_path)
    assert result["iid"]["session"] == "2026-10-02"
    assert result["iid"]["file_bytes"] == 20
    assert result["t0"]["file_bytes"] == 30


def test_git_provenance_is_local_read_only(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "--allow-empty", "-qm", "fixture"], check=True)
    result = preflight.repository_observation(tmp_path)
    assert result["main_sha"] == result["head_sha"]
    assert result["ref_basis"] == "LOCAL_REFS_NO_FETCH"
    assert result["writer_state_observed"]


def test_tool_no_network_no_repository_or_evidence_writes(tmp_path, monkeypatch, capsys):
    artifact = tmp_path / "evidence.json"
    artifact.write_bytes(b'protected')
    before = {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
              for p in tmp_path.rglob('*') if p.is_file()}
    monkeypatch.setattr(preflight, "observe", lambda *a: safe_observation())
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    monkeypatch.setattr(Path, "write_text", lambda *a, **k: pytest.fail("write forbidden"))
    monkeypatch.setattr(Path, "write_bytes", lambda *a, **k: pytest.fail("write forbidden"))
    assert preflight.main(["--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["contract_version"] == preflight.CONTRACT_VERSION
    assert before == {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                      for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize("classification", ["BLOCKED", "AMBER"])
def test_launcher_stops_before_child_for_nonready(tmp_path, monkeypatch, classification):
    monkeypatch.setattr(preflight, "check", lambda *a: {"classification": classification, "operator_guidance": preflight.GUIDANCE})
    monkeypatch.setattr(owner.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(owner.OwnerDailyError, match="OWNER_DAILY_HOST_PREFLIGHT_" + classification):
        owner._run_daily(tmp_path, tmp_path)


def test_ready_preserves_canonical_child_gate_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "check", lambda *a: {"classification": "READY"})
    class Process:
        def wait(self):
            return 7  # Existing canonical gate still refuses.
    def launch(argv, **kwargs):
        assert argv[2:] == ["daily_analysis_pipeline.py", "--runtime-root", str(tmp_path), "--canonical-post-close"]
        return Process()
    monkeypatch.setattr(owner.subprocess, "Popen", launch)
    with pytest.raises(owner.OwnerDailyError, match="CANONICAL_DAILY_EXIT_7"):
        owner._run_daily(tmp_path, tmp_path)


def test_nonwindows_standalone_fails_closed_without_network_or_bytecode(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX unsupported-host check")
    result = subprocess.run([sys.executable, str(Path(preflight.__file__)), "--root", str(tmp_path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 3
    assert json.loads(result.stdout)["classification"] == "BLOCKED"
    assert list(tmp_path.iterdir()) == []
