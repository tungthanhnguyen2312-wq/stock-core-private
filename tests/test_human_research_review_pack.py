from human_research_review_pack import FORBIDDEN, markdown
from run_human_research_review_pack import run


def test_review_pack_reconciles_and_preserves_structured_boundaries():
    first, replay = run(), run()
    assert first["artifact_identity"] == replay["artifact_identity"]
    summary = first["run_summary"]
    assert summary["eligible_research_cohort"] == 523
    assert summary["owner_review_queue_count"] == 25
    assert summary["task_counts_by_status"] == {"OPEN": 523, "DEFERRED_NO_CURRENT_EVIDENCE_ROUTE": 523}
    assert summary["evidence_authority_counts"] == {"OFFICIAL_QUALIFIED": 11, "PROVIDER_RESEARCH": 512}
    assert len(first["research_task_summary"]["machine_task_lineage"]) == 1046
    assert first["research_task_summary"]["deferred_summary"][0]["affected_ticker_count"] == 523
    for entry in first["owner_review_queue"]:
        assert entry["facts"] and entry["inferences"] and entry["data_gaps"] and entry["question_to_verify"]
        assert entry["unresolved_task"]["evidence_paths"]
        assert all(value is None for key, value in entry["owner_annotation"].items() if key != "system_populated")
    assert not any(term in markdown(first).upper() for term in FORBIDDEN)
    assert first["authority_boundary"]["ai_may_not_change_authority_or_resolve_task"] is True
