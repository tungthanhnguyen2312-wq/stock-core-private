from __future__ import annotations

import json

import pytest

import owner_daily_journal as journal


SESSION = "2026-09-22"


def test_read_journal_none_when_absent(tmp_path):
    assert journal.read_journal(tmp_path) is None


def test_read_journal_none_when_malformed(tmp_path):
    path = journal.journal_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert journal.read_journal(tmp_path) is None


def test_read_journal_none_when_not_an_object(tmp_path):
    path = journal.journal_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert journal.read_journal(tmp_path) is None


def test_start_run_creates_started_stage_with_fresh_run_id(tmp_path):
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    assert entry["stage"] == journal.STARTED
    assert entry["intended_session"] == SESSION
    assert entry["resolved_session"] is None
    assert entry["run_id"]
    on_disk = journal.read_journal(tmp_path)
    assert on_disk == entry


def test_start_run_supersedes_a_prior_in_flight_run(tmp_path):
    first = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, first["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    second = journal.start_run(tmp_path, intended_session=SESSION)
    assert second["run_id"] != first["run_id"]
    assert second["stage"] == journal.STARTED
    with pytest.raises(journal.OwnerDailyJournalError, match="JOURNAL_RUN_IDENTITY_MISMATCH"):
        journal.advance(tmp_path, first["run_id"], journal.PRODUCER_STATE_RETAINED)


def test_advance_is_monotonic_and_idempotent(tmp_path):
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED, resolved_session=SESSION)
    after_forward = journal.read_journal(tmp_path)
    assert after_forward["stage"] == journal.PRODUCER_STATE_RETAINED
    # Only STARTED (from start_run) and the direct jump to PRODUCER_STATE_RETAINED are recorded
    # -- advance() never backfills intermediate stages it was never asked to record.
    assert len(after_forward["stage_history"]) == 2

    # Re-advancing to an EARLIER (already-passed) stage must be a no-op, never a regression.
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE)
    unchanged = journal.read_journal(tmp_path)
    assert unchanged["stage"] == journal.PRODUCER_STATE_RETAINED
    assert len(unchanged["stage_history"]) == 2

    # Re-advancing to the SAME stage again must also be a no-op.
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED)
    same_again = journal.read_journal(tmp_path)
    assert same_again["stage_history"] == unchanged["stage_history"]


def test_advance_rejects_unknown_stage(tmp_path):
    entry = journal.start_run(tmp_path)
    with pytest.raises(journal.OwnerDailyJournalError, match="JOURNAL_UNKNOWN_STAGE"):
        journal.advance(tmp_path, entry["run_id"], "NOT_A_REAL_STAGE")


def test_advance_refuses_to_reconcile_a_different_session(tmp_path):
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    with pytest.raises(journal.OwnerDailyJournalError, match="JOURNAL_SESSION_IDENTITY_MISMATCH"):
        journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED, resolved_session="2026-09-21")


def test_advance_to_complete_records_attestation_detail(tmp_path):
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    detail = {"session": SESSION, "daily_producer_run_identity": "run:test", "dashboard": {"status": "READY"}}
    final = journal.advance(tmp_path, entry["run_id"], journal.COMPLETE, detail=detail)
    assert final["stage"] == journal.COMPLETE
    assert final["attestation"] == detail


def test_advance_failure_metadata_does_not_move_the_recorded_stage(tmp_path):
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    result = journal.advance(tmp_path, entry["run_id"], journal.INTERRUPTED, detail={"reason": "console closed"})
    assert result["stage"] == journal.LOCAL_COMPLETE  # unchanged -- INTERRUPTED is metadata, not a stage
    assert result["failure"]["stage"] == journal.INTERRUPTED
    assert result["failure"]["detail"]["reason"] == "console closed"


def test_resumable_state_start_fresh_when_no_journal(tmp_path):
    assert journal.resumable_state(tmp_path, intended_session=SESSION) == {"action": "START_FRESH"}


def test_resumable_state_start_fresh_when_session_resolved_and_differs(tmp_path):
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session="2026-09-21")
    result = journal.resumable_state(tmp_path, intended_session=SESSION)
    assert result == {"action": "START_FRESH"}


def test_resumable_state_start_fresh_when_stuck_at_started_with_no_session(tmp_path):
    journal.start_run(tmp_path, intended_session=SESSION)
    result = journal.resumable_state(tmp_path, intended_session=SESSION)
    assert result == {"action": "START_FRESH"}


def test_resumable_state_resume_for_matching_in_flight_session(tmp_path):
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.PRODUCER_STATE_RETAINED)
    result = journal.resumable_state(tmp_path, intended_session=SESSION)
    assert result["action"] == "RESUME"
    assert result["run_id"] == entry["run_id"]
    assert result["stage"] == journal.PRODUCER_STATE_RETAINED
    assert result["resolved_session"] == SESSION


def test_resumable_state_resume_when_intended_session_not_yet_known(tmp_path):
    """The caller may ask before it has resolved today's intended session itself -- a journal
    with a resolved session should still surface as resumable rather than falsely fresh."""
    entry = journal.start_run(tmp_path)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    result = journal.resumable_state(tmp_path, intended_session=None)
    assert result["action"] == "RESUME"
    assert result["resolved_session"] == SESSION


def test_advance_persists_resolved_session_on_a_same_stage_re_advance(tmp_path):
    """Reproduces the exact 2026-09-23 live-Daily incident: a fresh acquisition first marks
    SESSION_RESOLVED reached with NO resolved_session yet (the intended-session estimate is not
    authoritative -- see tools/run_owner_daily.run_workflow's own docstring), then, once Daily
    Producer's own gate confirms the exact session, calls advance() a SECOND time for the SAME
    stage with resolved_session now supplied. Both calls have `target_index == current_index`
    (SAME stage), which previously hit the early-return branch and silently skipped the write
    because it compared the just-mutated in-memory `resolved_session` to itself -- always equal.
    A hard kill any time after this (very common: the owner's Daily window can close mid-
    publication) then left a durable journal that looked exactly like a bare `SESSION_RESOLVED`-
    only run: `_auto_resumable_session` requires a truthy `resolved_session` and would return
    None, so the NEXT ordinary invocation could not auto-resume publication for an analytically
    already-`LOCAL_COMPLETE` session -- it would instead start a brand new Daily and re-run the
    analytical kernel, exactly the outcome `CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_
    PRESENTATION_JOIN_V1` section 2 documents as the intended, NOT the actual, behavior."""
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.SESSION_RESOLVED)
    stage_only = journal.read_journal(tmp_path)
    assert stage_only["stage"] == journal.SESSION_RESOLVED
    assert stage_only["resolved_session"] is None

    confirmed = journal.advance(tmp_path, entry["run_id"], journal.SESSION_RESOLVED, resolved_session=SESSION)
    assert confirmed["resolved_session"] == SESSION
    on_disk = journal.read_journal(tmp_path)
    assert on_disk["resolved_session"] == SESSION
    # Same stage as the prior advance() call, so no THIRD stage_history entry is appended --
    # only STARTED (from start_run) and SESSION_RESOLVED (the first advance) exist; the second
    # advance() call fills in the confirmed identity without moving or duplicating the stage.
    assert on_disk["stage"] == journal.SESSION_RESOLVED
    assert len(on_disk["stage_history"]) == 2

    result = journal.resumable_state(tmp_path, intended_session=SESSION)
    assert result["action"] == "RESUME"
    assert result["resolved_session"] == SESSION


def test_resumable_state_already_complete(tmp_path):
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.LOCAL_COMPLETE, resolved_session=SESSION)
    journal.advance(tmp_path, entry["run_id"], journal.COMPLETE)
    result = journal.resumable_state(tmp_path, intended_session=SESSION)
    assert result == {"action": "ALREADY_COMPLETE", "run_id": entry["run_id"], "resolved_session": SESSION}


def test_journal_is_valid_json_on_disk_at_every_stage(tmp_path):
    entry = journal.start_run(tmp_path, intended_session=SESSION)
    for stage in (journal.LOCAL_COMPLETE, journal.PRODUCER_STATE_RETAINED, journal.PRESENTATION_BOUND,
                 journal.DASHBOARD_PUBLISHED, journal.AI_HANDOFF_PUBLISHED, journal.ACTION_CENTER_READY,
                 journal.COMPLETE):
        journal.advance(tmp_path, entry["run_id"], stage, resolved_session=SESSION if stage == journal.LOCAL_COMPLETE else None)
        raw = journal.journal_path(tmp_path).read_text(encoding="utf-8")
        json.loads(raw)  # must never write malformed JSON, even mid-sequence
    final = journal.read_journal(tmp_path)
    assert final["stage"] == journal.COMPLETE
    assert [row["stage"] for row in final["stage_history"]][:3] == [journal.STARTED, journal.LOCAL_COMPLETE, journal.PRODUCER_STATE_RETAINED]
