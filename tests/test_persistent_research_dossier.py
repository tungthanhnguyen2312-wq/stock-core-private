from pathlib import Path
import copy

import pytest

from persistent_research_dossier import build, write_immutable
from run_persistent_research_dossier import inputs


def test_initialization_replay_and_authority_lineage_are_deterministic(tmp_path: Path):
    product, analyst = inputs()
    initial = build(product, analyst)
    prior = {item["ticker"]: item["dossier"] for item in initial["dossiers"]}
    replay = build(product, analyst, previous_by_ticker=prior)
    assert initial["coverage"]["dossiers_dispositioned"] == 523
    assert initial["coverage"]["ai_queue_members"] == 25
    assert initial["coverage"]["open_question_count"] == 523
    assert initial["coverage"]["data_gap_count"] == 523
    assert initial["coverage"]["change_category_counts"] == {"NEW_RESEARCH_STATE": 523}
    assert replay["coverage"]["change_category_counts"] == {"NO_MATERIAL_CHANGE": 523}
    assert [item["ticker"] for item in initial["follow_up_queue"]] == [
        item["ticker"] for item in analyst["research_queue"]
    ]
    assert {item["dossier"]["authority_evidence_tiers"]["fundamental_context"] for item in initial["dossiers"]} >= {
        "OFFICIAL_QUALIFIED", "PROVIDER_RESEARCH"
    }
    path = tmp_path / "immutable.json"
    write_immutable(path, initial["dossiers"][0]["dossier"])
    write_immutable(path, initial["dossiers"][0]["dossier"])
    changed = dict(initial["dossiers"][0]["dossier"])
    changed["ticker"] = "MUTATED"
    with pytest.raises(ValueError, match="IMMUTABLE_DOSSIER_CONTENT_CONFLICT"):
        write_immutable(path, changed)


def test_ai_text_cannot_replace_deterministic_research_facts():
    product, analyst = inputs()
    artifact = build(product, analyst)
    records = {item["ticker"]: item for item in product["stock_research"]}
    for item in artifact["dossiers"]:
        assert item["dossier"]["deterministic_research_state"]["facts"] == records[item["ticker"]]["ai_ready_brief"]["facts"]
        assert item["dossier"]["thesis_hash"]
        assert item["dossier"]["counter_thesis_hash"]
        assert all(question["evidence_field"] for question in item["dossier"]["open_questions"])
        assert all(gap["evidence_field"] for gap in item["dossier"]["data_gaps"])


def test_changed_deterministic_attention_requests_human_review():
    product, analyst = inputs()
    initial = build(product, analyst)
    prior = {item["ticker"]: item["dossier"] for item in initial["dossiers"]}
    changed_product = copy.deepcopy(product)
    changed_product["stock_research"][0]["research_summary"]["attention_descriptors"].append("TEST_CHANGED")
    changed = build(changed_product, analyst, previous_by_ticker=prior)
    first = next(item for item in changed["dossiers"] if item["ticker"] == changed_product["stock_research"][0]["ticker"])
    assert "ATTENTION_STATE_CHANGED" in first["change_set"]["categories"]
    assert first["change_set"]["human_review_required"] is True
