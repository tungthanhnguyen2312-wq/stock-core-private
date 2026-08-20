from pathlib import Path

import pytest

from owner_research_journal import append_event, build, create_event, write_immutable_event
from run_human_research_review_pack import run as review_pack_run


def test_baseline_is_unreviewed_and_system_state_is_unchanged():
    pack = review_pack_run()
    first, replay = build(pack), build(pack)
    assert first["artifact_identity"] == replay["artifact_identity"]
    assert first["target_review_pack_identity"] == pack["artifact_identity"]
    assert first["summary"]["review_candidates"] == 25
    assert first["summary"]["workflow_status_counts"] == {"UNREVIEWED": 25}
    assert all(entry["owner_feedback"]["latest_annotation_identity"] is None for entry in first["owner_overlay"])


def test_events_are_append_only_and_owner_priority_does_not_change_system_queue(tmp_path: Path):
    pack = review_pack_run()
    review = pack["owner_review_queue"][3]
    event = create_event(ticker=review["ticker"], review_pack_identity=pack["artifact_identity"],
                         dossier_identity=review["dossier_identity"], linked_task_identities=[review["unresolved_task"]["task_identity"]],
                         research_session=pack["run_summary"]["research_session"], created_at="2026-08-20T12:00:00+07:00",
                         review_status="NEEDS_EVIDENCE", owner_note="", follow_up_needed=True,
                         evidence_requested="Owner requests cited issuer context.", research_priority_override="HIGH")
    path = tmp_path / "event.json"
    write_immutable_event(path, event); write_immutable_event(path, event)
    assert append_event(tmp_path / "append", event) == append_event(tmp_path / "append", event)
    assert len(list((tmp_path / "append").glob("*.json"))) == 1
    with pytest.raises(ValueError):
        write_immutable_event(path, {**event, "ticker": "MUTATED"})
    overlay = build(pack, [event])
    entry = next(item for item in overlay["owner_overlay"] if item["ticker"] == review["ticker"])
    assert entry["owner_feedback"]["review_status"] == "NEEDS_EVIDENCE"
    assert overlay["owner_overlay"][0]["ticker"] == review["ticker"]
    assert pack["owner_review_queue"][3]["ticker"] == review["ticker"]
    edited = create_event(ticker=review["ticker"], review_pack_identity=pack["artifact_identity"],
                          dossier_identity=review["dossier_identity"], linked_task_identities=[review["unresolved_task"]["task_identity"]],
                          research_session=pack["run_summary"]["research_session"], created_at="2026-08-20T13:00:00+07:00",
                          review_status="REVIEWED", prior_annotation_identity=event["annotation_identity"])
    assert build(pack, [event, edited])["summary"]["workflow_status_counts"]["REVIEWED"] == 1
