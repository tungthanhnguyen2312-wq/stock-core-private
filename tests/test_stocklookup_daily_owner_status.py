"""DAILY_OWNER_FLOW_POST_CLOSE_STABILIZATION_GATE_V1: `stocklookup.py daily` must not slap a
generic FAILED_PRODUCER trailer on top of a daily_analysis_pipeline.py run that already printed
a clean, complete owner-facing status for a known not-ready session-gate stage (its exit code 2 --
see canonical_daily_operation.NOT_READY_STAGES)."""
from __future__ import annotations

import stocklookup


def test_exit_code_2_is_silent_no_redundant_failed_producer_message():
    assert stocklookup._producer_failure_message(2) is None


def test_exit_code_0_is_silent():
    assert stocklookup._producer_failure_message(0) is None


def test_exit_code_1_still_reports_failed_producer():
    message = stocklookup._producer_failure_message(1)
    assert message is not None
    assert "FAILED_PRODUCER" in message
    assert "RECOVERY_ACTION" in message


def test_other_nonzero_exit_codes_still_report_failed_producer():
    for code in (3, 127, -1):
        message = stocklookup._producer_failure_message(code)
        assert message is not None and "FAILED_PRODUCER" in message
