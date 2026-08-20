from pathlib import Path
import copy

import pytest

from persistent_research_dossier import load_latest_versions
from research_question_tasking import build, write_immutable
from run_research_question_tasking import DOSSIER_ROOT


def test_baseline_tasks_are_deduplicated_deferred_and_replay_safe(tmp_path: Path):
    dossiers = load_latest_versions(DOSSIER_ROOT)
    initial = build(dossiers)
    previous = {task["task_identity"]: task for task in initial["tasks"]}
    replay = build(dossiers, previous_by_task=previous)
    assert initial["coverage"]["dossiers_dispositioned"] == 523
    assert initial["coverage"]["total_tasks"] == 1046
    assert len({task["task_identity"] for task in initial["tasks"]}) == 1046
    assert initial["coverage"]["status_counts"] == {"OPEN": 523, "DEFERRED_NO_CURRENT_EVIDENCE_ROUTE": 523}
    assert initial["coverage"]["ai_queue_task_coverage"] == 25
    assert {task["task_state_identity"] for task in initial["tasks"]} == {task["task_state_identity"] for task in replay["tasks"]}
    assert all(task["task_status"] != "RESOLVED_BY_QUALIFIED_EVIDENCE" for task in initial["tasks"])
    deferred = [task for task in initial["tasks"] if task["task_status"] == "DEFERRED_NO_CURRENT_EVIDENCE_ROUTE"]
    assert len(deferred) == 523 and all(task["reopen_condition"] for task in deferred)
    assert {task["deferred_reason"] for task in deferred} == {"QUALIFIED_LIQUIDITY_INPUTS_NOT_AVAILABLE"}
    path = tmp_path / "task.json"
    write_immutable(path, initial["tasks"][0])
    changed = dict(initial["tasks"][0]); changed["ticker"] = "MUTATED"
    with pytest.raises(ValueError, match="IMMUTABLE_RESEARCH_TASK_CONTENT_CONFLICT"):
        write_immutable(path, changed)


def test_resolution_requires_existing_authority_and_question_replacement_preserves_history():
    dossiers = load_latest_versions(DOSSIER_ROOT)
    initial = build(dossiers)
    previous = {task["task_identity"]: task for task in initial["tasks"]}
    task = next(item for item in initial["tasks"] if item["task_kind"] == "QUESTION_TO_VERIFY")
    descriptively_resolved = build(dossiers, previous_by_task=previous, evidence_by_task={task["task_identity"]: {
        "authority": "PROVIDER_RESEARCH", "contract_satisfied": True, "descriptive_resolution_allowed": True}})
    changed = next(item for item in descriptively_resolved["tasks"] if item["task_identity"] == task["task_identity"])
    assert changed["task_status"] == "RESOLVED_DESCRIPTIVELY"
    qualified = build(dossiers, previous_by_task=previous, evidence_by_task={task["task_identity"]: {
        "authority": "OFFICIAL_QUALIFIED", "contract_satisfied": True}})
    qualified_task = next(item for item in qualified["tasks"] if item["task_identity"] == task["task_identity"])
    assert qualified_task["task_status"] == "RESOLVED_BY_QUALIFIED_EVIDENCE"
    mutated_dossiers = copy.deepcopy(dossiers)
    ticker = task["ticker"]
    mutated_dossiers[ticker]["open_questions"][0]["claim"] = "What changed in the issuer-specific evidence?"
    replaced = build(mutated_dossiers, previous_by_task=previous)
    old = next(item for item in replaced["tasks"] if item["task_identity"] == task["task_identity"])
    assert old["task_status"] == "SUPERSEDED_BY_NEW_QUESTION"
    assert old["superseded_by_task_identity"] != old["task_identity"]
    missing_dossiers = dict(dossiers)
    missing_dossiers.pop(ticker)
    missing = build(missing_dossiers, previous_by_task=previous)
    retained = next(item for item in missing["tasks"] if item["task_identity"] == task["task_identity"])
    assert retained["dossier_presence"] == "MISSING_FROM_CURRENT_RUN"
