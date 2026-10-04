"""Monday acceptance-harness rows for the optional feedback children: reported truthfully, never gating capture."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import first_real_session_acceptance as harness
from tests.test_monday_live_readiness import DAY
from tests.test_prospective_pit_capture import capture_session

COLLECTED = {"status": "COLLECTED", "artifact_identity": "prospective_decision_outcome_feedback:x", "outcome": "BUILT", "relation": "INCREMENTAL",
             "resource": {"wall_seconds": 200.0, "reaped": True, "child_peak_bytes": 500_000_000, "peak_process_bytes": 520_000_000, "containment": "WINDOWS_JOB_OBJECT_PROCESS_MEMORY"},
             "policy": {"deadline_seconds": 1200.0}, "admission": {"admitted": True, "free_disk_bytes": 10 ** 10, "available_physical_bytes": 3 * 10 ** 9}}
TIMEOUT = {"status": "UNAVAILABLE", "reason_code": "FEEDBACK_RESOURCE_TIMEOUT", "resource": {"wall_seconds": 1200.1, "reaped": True},
           "policy": {"deadline_seconds": 1200.0}}


def _rows(feedback):
    return {row["capability"]: row for row in harness.feedback_rows(feedback)}


def test_absent_feedback_is_not_evaluable_and_never_gates_capture():
    rows = _rows(None)
    assert set(rows) == {"feedback_pre_handoff", "feedback_post_handoff", "feedback_resource_admission",
                         "feedback_terminal_cache_reuse", "feedback_resource_reason"}
    assert all(row["state"] in {"NOT_EVALUABLE", "OPEN"} or row["state"] == "STILL_BLOCKED" for row in rows.values())
    assert rows["feedback_pre_handoff"]["state"] == "NOT_EVALUABLE"
    assert all(row["details"]["gates_capture"] is False for row in rows.values())


def test_successful_pre_and_post_are_open_and_report_resource_facts():
    rows = _rows({"pre": COLLECTED, "post": COLLECTED})
    assert rows["feedback_pre_handoff"]["state"] == "OPEN" and rows["feedback_post_handoff"]["state"] == "OPEN"
    assert rows["feedback_post_handoff"]["details"]["relation"] == "INCREMENTAL" and rows["feedback_post_handoff"]["details"]["child_peak_bytes"] == 500_000_000
    assert rows["feedback_resource_admission"]["state"] == "OPEN" and rows["feedback_terminal_cache_reuse"]["state"] == "OPEN"
    assert rows["feedback_resource_reason"]["state"] == "OPEN"


def test_a_resource_reason_blocks_only_its_own_feedback_row_and_is_labelled_as_not_evidence():
    rows = _rows({"pre": COLLECTED, "post": TIMEOUT})
    assert rows["feedback_post_handoff"]["state"] == "STILL_BLOCKED" and rows["feedback_pre_handoff"]["state"] == "OPEN"
    reason = rows["feedback_resource_reason"]
    assert reason["state"] == "STILL_BLOCKED" and reason["details"]["reasons"] == {"post": "FEEDBACK_RESOURCE_TIMEOUT"}
    assert reason["details"]["interpretation"] == "RESOURCE_OR_DEFECT_STATUS_IS_NOT_FEEDBACK_EVIDENCE"


def test_capture_and_marker_rows_are_identical_with_and_without_feedback_status(tmp_path):
    root = tmp_path / "fixture"
    capture_session(root, DAY, calendar_days=[DAY])
    pre = tmp_path / "pre.json"
    pre.write_text(json.dumps(TIMEOUT), encoding="utf-8")
    cutoff = DAY + "T12:10:00Z"
    without = harness.collect(root, session=DAY, cutoff=cutoff)
    with_feedback = harness.collect(root, session=DAY, cutoff=cutoff, feedback_status_paths={"pre": pre, "post": None})

    def capture_rows(report):
        return [row for row in report["rows"] if not row["capability"].startswith("feedback_")]

    assert capture_rows(without) == capture_rows(with_feedback)
    assert {r["capability"] for r in with_feedback["rows"]} >= {"feedback_pre_handoff", "feedback_resource_reason"}
    assert next(r for r in with_feedback["rows"] if r["capability"] == "feedback_pre_handoff")["state"] == "STILL_BLOCKED"


def test_oversize_or_unreadable_status_is_ignored(tmp_path):
    big = tmp_path / "big.json"
    big.write_text("{\"x\":\"" + "a" * (300 * 1024) + "\"}", encoding="utf-8")
    assert harness._read_status(big) is None and harness._read_status(tmp_path / "missing.json") is None
