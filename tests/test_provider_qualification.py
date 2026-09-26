"""Offline fake provider qualification scaffolding (NOT live qualification)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import run_provider_qualification as qual  # noqa: E402
from _provider_build_fixtures import MODE_OFFLINE_FAKE, governed_runtime, protocol_runtime  # noqa: E402


def test_mode_is_explicitly_offline_fake_and_cannot_be_confused_with_live():
    assert qual.MODE == MODE_OFFLINE_FAKE == "OFFLINE_FAKE_PROVIDER_QUALIFICATION"
    assert qual.CONTRACT_VERSION.endswith("offline-fake")


def test_gate_a_tracked_draft_passes_as_unapproved_preflight():
    report = qual.gate_a_tracked_draft()
    assert report["mode"] == MODE_OFFLINE_FAKE
    assert report["live_qualification"] is False
    assert report["verdict"] == "PASS"
    assert report["policy"] == "SECURITY_REVIEW_BLOCKED"


def test_gate_a_fake_runtime_preflight_passes(tmp_path):
    report = qual.gate_a_fake(protocol_runtime(tmp_path))
    assert report["verdict"] == "PASS"
    assert report["live_qualification"] is False


def test_live_gates_cde_are_unavailable():
    for letter in ("C", "D", "E"):
        payload = qual.unavailable_live_gate(letter)
        assert payload["verdict"] == "UNAVAILABLE"
        assert "OWNER_APPROVAL" in payload["reason_codes"][0]


def test_gate_b_fake_protocol_launch_passes(tmp_path):
    report = qual.gate_b_fake(protocol_runtime(tmp_path))
    assert report["mode"] == MODE_OFFLINE_FAKE
    assert report["live_qualification"] is False
    assert report["verdict"] == "PASS", report
    assert report["state"]["state"] == "AVAILABLE"


def test_gate_b_fake_governed_real_worker_reaches_ready(tmp_path):
    # The real vnstock_worker_process.py against fake packages (incl. the tzdata the worker's
    # timezone needs) reaches READY with only the manifest-declared, expected denials.
    runtime = governed_runtime(tmp_path, vnai_probes_owner_profile=False)
    assert qual.gate_a_fake(runtime)["verdict"] == "PASS"
    report = qual.gate_b_fake(runtime)
    assert report["verdict"] == "PASS", report
    assert report["live_qualification"] is False
    state = report["state"]
    assert state["state"] == "AVAILABLE"
    events = state["runtime_info"]["containment"]["events"]
    assert events["unexpected_denial_count"] == 0
    assert set(events["by_reason"]) <= {"PROCESS_CREATION_DENIED", "SOCKET_HOST_NOT_ALLOWLISTED"}
    assert state["runtime_info"]["rate_contract"]["governor_effective_rpm"] <= 20


def test_cli_json_report_never_claims_live_qualification():
    report = qual.run(gate="A")
    dumped = json.dumps(report)
    assert report["live_qualification"] is False
    assert report["provider_build_approved"] is False
    assert "OFFLINE_FAKE_PROVIDER_QUALIFICATION" in dumped
    assert report["verdict"] in ("PASS", "FAIL")
